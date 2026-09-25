"""Resolve finto, sufficiente a esercitare resolve_ops senza DaVinci.

``end_inclusive`` e ``record_relative`` simulano le due interpretazioni
possibili di AppendToTimeline, per verificare l'auto-calibrazione.
"""

import os

from leaderkit.timecode import FrameRate, frames_to_tc, tc_to_frames


class Clip(object):
    def __init__(self, name, frames, kind="video", timeline=None, path=None):
        self.name = name
        self.frames = frames
        self.kind = kind
        self.timeline = timeline
        self.path = path

    def GetName(self):
        return self.name

    def GetClipProperty(self, key):
        if key == "Frames":
            return str(self.frames)
        if key == "Type":
            return "Timeline" if self.timeline else ("Audio" if self.kind == "audio" else "Still")
        return ""


class Folder(object):
    def __init__(self, name):
        self.name = name
        self.clips = []
        self.subs = []

    def GetName(self):
        return self.name

    def GetClipList(self):
        return list(self.clips)

    def GetSubFolderList(self):
        return list(self.subs)


class Item(object):
    def __init__(self, timeline, mpi, offset, duration, kind):
        self.timeline = timeline
        self.mpi = mpi
        self.offset = offset
        self.duration = duration
        self.kind = kind
        self.comps = []
        self.color = None

    def GetStart(self):
        return self.timeline.start + self.offset

    def GetDuration(self):
        return self.duration

    def GetEnd(self):
        return self.GetStart() + self.duration

    def GetMediaPoolItem(self):
        return self.mpi

    def GetName(self):
        return self.mpi.GetName()

    def ImportFusionComp(self, path):
        with open(path, "rb") as fh:
            self.comps.append(fh.read().decode("utf-8"))
        return object()

    def SetClipColor(self, color):
        self.color = color
        return True


class Timeline(object):
    def __init__(self, project, name):
        self.project = project
        self.name = name
        self.settings = {}
        self.rate = project.rate
        self.start = tc_to_frames("01:00:00:00", self.rate)
        self.tracks = {"video": [["Video 1", []]], "audio": [["Audio 1", []]]}
        self.markers = {}
        self.mpi = Clip(name, 0, timeline=self)

    # impostazioni
    def GetName(self):
        return self.name

    def GetSetting(self, key):
        if key in self.settings:
            return self.settings[key]
        return self.project.GetSetting(key)

    def SetSetting(self, key, value):
        self.settings[key] = value
        return True

    def GetMediaPoolItem(self):
        self.mpi.frames = self.GetEndFrame() - self.start
        return self.mpi

    def GetStartFrame(self):
        return self.start

    def GetEndFrame(self):
        ends = [i.GetEnd() for k in self.tracks for t in self.tracks[k] for i in t[1]]
        return max(ends) if ends else self.start

    def SetStartTimecode(self, tc):
        self.start = tc_to_frames(tc, self.rate)
        return True

    def GetStartTimecode(self):
        return frames_to_tc(self.start, self.rate)

    # tracce
    def GetTrackCount(self, kind):
        return len(self.tracks[kind])

    def AddTrack(self, kind, sub=None):
        self.tracks[kind].append(["%s %d" % (kind.title(), len(self.tracks[kind]) + 1), []])
        return True

    def DeleteTrack(self, kind, index):
        del self.tracks[kind][index - 1]
        return True

    def GetTrackName(self, kind, index):
        return self.tracks[kind][index - 1][0]

    def SetTrackName(self, kind, index, name):
        self.tracks[kind][index - 1][0] = name
        return True

    def GetItemListInTrack(self, kind, index):
        return sorted(self.tracks[kind][index - 1][1], key=lambda i: i.offset)

    def DeleteClips(self, items, ripple=False):
        for kind in self.tracks:
            for t in self.tracks[kind]:
                t[1] = [i for i in t[1] if i not in items]
        return True

    # marker (frameId relativo all'inizio timeline, come da README Resolve)
    def AddMarker(self, frame, color, name, note, duration, custom):
        if frame in self.markers or frame < 0:
            return False
        self.markers[frame] = {"color": color, "name": name, "note": note,
                               "duration": duration, "customData": custom}
        return True

    def GetMarkers(self):
        return dict(self.markers)

    def DeleteMarkerAtFrame(self, frame):
        return self.markers.pop(frame, None) is not None

    # helper di test
    def items(self, kind, track_name):
        for name, items in self.tracks[kind]:
            if name == track_name:
                return sorted(items, key=lambda i: i.offset)
        return []

    def add_clip(self, mpi, offset, duration, kind="video", track=1):
        item = Item(self, mpi, offset, duration, kind)
        self.tracks[kind][track - 1][1].append(item)
        return item


class MediaPool(object):
    def __init__(self, project, end_inclusive=True, record_relative=False):
        self.project = project
        self.root = Folder("Master")
        self.current = self.root
        self.end_inclusive = end_inclusive
        self.record_relative = record_relative
        self.appends = 0

    def GetRootFolder(self):
        return self.root

    def AddSubFolder(self, parent, name):
        f = Folder(name)
        parent.subs.append(f)
        return f

    def GetCurrentFolder(self):
        return self.current

    def SetCurrentFolder(self, folder):
        self.current = folder
        return True

    def ImportMedia(self, items):
        out = []
        for it in items:
            if isinstance(it, dict):
                pattern = it["FilePath"]
                count = it["EndIndex"] - it["StartIndex"] + 1
                first = pattern % it["StartIndex"]
                assert os.path.exists(first) and os.path.exists(pattern % it["EndIndex"])
                base = os.path.basename(pattern).split("%")[0]
                clip = Clip("%s[%05d-%05d].png" % (base, it["StartIndex"], it["EndIndex"]), count)
            else:
                assert os.path.exists(it)
                clip = Clip(os.path.basename(it), 48, kind="audio", path=it)
            self.current.clips.append(clip)
            out.append(clip)
        return out

    def CreateEmptyTimeline(self, name):
        tl = Timeline(self.project, name)
        self.project.timelines.append(tl)
        self.root.clips.append(tl.mpi)
        return tl

    def AppendToTimeline(self, infos):
        self.appends += 1
        tl = self.project.current
        out = []
        for info in infos:
            mpi = info["mediaPoolItem"]
            start, end = info["startFrame"], info["endFrame"]
            dur = end - start + (1 if self.end_inclusive else 0)
            if end >= mpi.frames + (0 if self.end_inclusive else 1):
                dur = mpi.frames - start  # la sorgente finisce prima
            rec = info["recordFrame"]
            offset = rec if self.record_relative else rec - tl.start
            media_type = info.get("mediaType")
            track = info["trackIndex"]
            if mpi.timeline is not None and media_type is None:
                out.append(tl.add_clip(mpi, offset, dur, "video", track))
                out.append(tl.add_clip(mpi, offset, dur, "audio", track))
            elif media_type == 2:
                out.append(tl.add_clip(mpi, offset, dur, "audio", track))
            else:
                out.append(tl.add_clip(mpi, offset, dur, "video", track))
        return out


class Project(object):
    def __init__(self, fps="24", drop=False, width=1920, height=1080, **pool_kw):
        self.rate = FrameRate.parse(fps, drop)
        self.settings = {"timelineFrameRate": fps,
                         "timelineDropFrameTimecode": "1" if drop else "0",
                         "timelineResolutionWidth": str(width),
                         "timelineResolutionHeight": str(height)}
        self.timelines = []
        self.pool = MediaPool(self, **pool_kw)
        self.current = None

    def GetSetting(self, key):
        return self.settings.get(key, "")

    def GetMediaPool(self):
        return self.pool

    def GetCurrentTimeline(self):
        return self.current

    def SetCurrentTimeline(self, tl):
        self.current = tl
        return True

    def GetTimelineCount(self):
        return len(self.timelines)

    def GetTimelineByIndex(self, i):
        return self.timelines[i - 1]

    def new_program_timeline(self, name, seconds, offset=0):
        tl = self.pool.CreateEmptyTimeline(name)
        clip = Clip("A001_C001.mov", 100000)
        tl.add_clip(clip, offset, int(seconds * self.rate.nominal), "video")
        tl.add_clip(clip, offset, int(seconds * self.rate.nominal), "audio")
        self.current = tl
        return tl


class Resolve(object):
    def __init__(self, project):
        self.project = project

    def GetProjectManager(self):
        return self

    def GetCurrentProject(self):
        return self.project
