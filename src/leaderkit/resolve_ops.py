"""Applicazione del Plan a DaVinci Resolve tramite l'API di scripting.

Scelte tecniche (vedi README, sezione "Come funziona"):

* frame rate, drop-frame e risoluzione si leggono dalla timeline
  (``Timeline.GetSetting``) con ripiego sul progetto;
* ogni elemento del leader è un clip della sequenza PNG nera posizionato con
  ``MediaPool.AppendToTimeline`` (recordFrame/trackIndex) su una traccia
  dedicata "LeaderKit"; sopra si importa la composizione Fusion generata;
* il posizionamento viene verificato con GetStart/GetDuration: se questa
  versione di Resolve interpreta endFrame/recordFrame con un offset diverso,
  il primo clip lo misura, viene rifatto e l'offset vale per il resto;
* marker con ``customData`` = "leaderkit:<tipo>" per rigenerarli o
  cancellarli senza toccare quelli dell'utente.
"""

import os
import tempfile

from . import fusion, layout, media, paths
from .timecode import FrameRate, frames_to_tc

TRACK_VIDEO = "LeaderKit"
TRACK_AUDIO = "LeaderKit Pop"
MEDIA_FOLDER = "LeaderKit"
CLIP_COLOR = "Orange"
MIN_SEQUENCE_SECONDS = 10


class ResolveError(RuntimeError):
    pass


def _call(obj, name, *args):
    fn = getattr(obj, name, None)
    if fn is None:
        raise ResolveError("API %s non disponibile in questa versione di Resolve" % name)
    return fn(*args)


# --- lettura impostazioni -------------------------------------------------

def timeline_format(project, timeline):
    """(FrameRate, width, height) reali della timeline."""
    def get(key):
        value = None
        if timeline is not None:
            try:
                value = timeline.GetSetting(key)
            except Exception:
                value = None
        if value in (None, ""):
            value = project.GetSetting(key)
        return value

    fps = get("timelineFrameRate")
    df_raw = get("timelineDropFrameTimecode")
    drop = None
    if df_raw not in (None, ""):
        drop = str(df_raw).strip().lower() in ("1", "true", "yes")
    rate = FrameRate.parse(fps)
    if drop and not rate.drop_frame and rate.is_ntsc and rate.nominal % 30 == 0:
        rate = FrameRate(rate.exact, True)
    elif drop is False and rate.drop_frame:
        rate = FrameRate(rate.exact, False)
    try:
        width = int(float(get("timelineResolutionWidth")))
        height = int(float(get("timelineResolutionHeight")))
    except (TypeError, ValueError):
        raise ResolveError("Impossibile leggere la risoluzione della timeline")
    return rate, width, height


# --- media pool -------------------------------------------------------------

def _folder(media_pool):
    root = media_pool.GetRootFolder()
    for sub in root.GetSubFolderList() or []:
        if sub.GetName() == MEDIA_FOLDER:
            return sub
    folder = media_pool.AddSubFolder(root, MEDIA_FOLDER)
    if not folder:
        raise ResolveError("Impossibile creare la cartella '%s' nel Media Pool" % MEDIA_FOLDER)
    return folder


def _clip_frames(mpi):
    for key in ("Frames", "End"):
        try:
            value = mpi.GetClipProperty(key)
            if value not in (None, ""):
                return int(str(value).split()[0])
        except Exception:
            pass
    return 0


def _with_folder(media_pool, folder, fn):
    previous = media_pool.GetCurrentFolder()
    media_pool.SetCurrentFolder(folder)
    try:
        return fn()
    finally:
        if previous:
            media_pool.SetCurrentFolder(previous)


def black_sequence_item(media_pool, width, height, frames_needed, nominal, log):
    """MediaPoolItem della sequenza nera (importata una volta per progetto)."""
    folder = _folder(media_pool)
    tag = "%s%dx%d_" % (media.SEQUENCE_PREFIX, width, height)
    for clip in folder.GetClipList() or []:
        if clip.GetName().startswith(tag) and _clip_frames(clip) >= frames_needed:
            return clip
    count = max(frames_needed, MIN_SEQUENCE_SECONDS * nominal)
    seq_dir, files = media.ensure_black_sequence(paths.cache_dir(), width, height, count)
    log("Sequenza nera %dx%d (%d fotogrammi) in %s" % (width, height, count, seq_dir))
    pattern = os.path.join(seq_dir, "%s%dx%d_%%05d.png" % (media.SEQUENCE_PREFIX, width, height))

    def do_import():
        items = media_pool.ImportMedia([{"FilePath": pattern, "StartIndex": 0,
                                         "EndIndex": count - 1}])
        if not items:
            items = media_pool.ImportMedia([seq_dir])
        return items

    items = _with_folder(media_pool, folder, do_import) or []
    for clip in items:
        if clip.GetName().startswith(tag):
            return clip
    if items:
        return items[0]
    raise ResolveError("Import della sequenza nera fallito (%s)" % pattern)


def pop_item(media_pool, tone_hz, level_dbfs):
    folder = _folder(media_pool)
    name = media.pop_wav_name(tone_hz, level_dbfs)
    for clip in folder.GetClipList() or []:
        if clip.GetName() == name:
            return clip
    path = media.ensure_pop_wav(paths.cache_dir(), tone_hz, level_dbfs)
    items = _with_folder(media_pool, folder, lambda: media_pool.ImportMedia([path])) or []
    if not items:
        raise ResolveError("Import del tono di sync fallito (%s)" % path)
    return items[0]


def timeline_media_item(media_pool, timeline):
    """MediaPoolItem di una timeline (per annidarla nella timeline di consegna)."""
    fn = getattr(timeline, "GetMediaPoolItem", None)
    if fn is not None:
        item = fn()
        if item:
            return item
    name = timeline.GetName()
    stack = [media_pool.GetRootFolder()]
    while stack:
        folder = stack.pop()
        for clip in folder.GetClipList() or []:
            try:
                if clip.GetName() == name and "timeline" in str(clip.GetClipProperty("Type")).lower():
                    return clip
            except Exception:
                pass
        stack.extend(folder.GetSubFolderList() or [])
    raise ResolveError("Timeline '%s' non trovata nel Media Pool" % name)


# --- posizionamento ---------------------------------------------------------

class Placer(object):
    """AppendToTimeline con verifica al fotogramma e auto-calibrazione."""

    def __init__(self, media_pool, timeline, log):
        self.media_pool = media_pool
        self.timeline = timeline
        self.log = log
        self.end_bias = 0     # endFrame = start + durata - 1 + end_bias
        self.record_bias = 0
        self.calibrated = False

    def place(self, mpi, record, duration, track, media_type=None, source_start=0,
              strict=True):
        """Posiziona e verifica. Con strict=False (programma annidato) una durata
        più corta del richiesto viene accettata: la sorgente è finita prima."""
        for attempt in (0, 1):
            info = {"mediaPoolItem": mpi, "startFrame": source_start,
                    "endFrame": source_start + duration - 1 + self.end_bias,
                    "recordFrame": record + self.record_bias, "trackIndex": track}
            if media_type:
                info["mediaType"] = media_type
            items = self.media_pool.AppendToTimeline([info]) or []
            if not items:
                raise ResolveError("AppendToTimeline fallito a %s" % record)
            item = items[0]
            got_start, got_dur = item.GetStart(), item.GetDuration()
            if got_start == record and got_dur == duration:
                self.calibrated = True
                return item
            if not strict and got_start == record and 0 < got_dur < duration:
                return item
            if self.calibrated or attempt:
                raise ResolveError("Clip posizionato a %d (+%d) invece di %d (+%d)"
                                   % (got_start, got_dur, record, duration))
            self.log("Calibrazione API: offset recordFrame %+d, endFrame %+d"
                     % (record - got_start, duration - got_dur))
            self.record_bias += record - got_start
            self.end_bias += duration - got_dur
            self.timeline.DeleteClips(items, False)
        raise ResolveError("Posizionamento non riuscito")


def _ensure_track(timeline, kind, name, sub_type=None):
    count = timeline.GetTrackCount(kind)
    for i in range(1, count + 1):
        if timeline.GetTrackName(kind, i) == name:
            return i
    ok = timeline.AddTrack(kind, sub_type) if sub_type else timeline.AddTrack(kind)
    if not ok:
        raise ResolveError("Impossibile aggiungere una traccia %s" % kind)
    index = timeline.GetTrackCount(kind)
    timeline.SetTrackName(kind, index, name)
    return index


def _is_leaderkit_item(timeline, kind, track, item):
    if (timeline.GetTrackName(kind, track) or "").startswith(TRACK_VIDEO):
        return True
    try:
        mpi = item.GetMediaPoolItem()
        return bool(mpi) and mpi.GetName().startswith("LeaderKit_")
    except Exception:
        return False


def program_range(timeline):
    """(primo fotogramma, ultimo fotogramma) dei clip non LeaderKit."""
    first, last = None, None
    for kind in ("video", "audio"):
        for track in range(1, timeline.GetTrackCount(kind) + 1):
            for item in timeline.GetItemListInTrack(kind, track) or []:
                if _is_leaderkit_item(timeline, kind, track, item):
                    continue
                s = item.GetStart()
                e = s + item.GetDuration() - 1
                first = s if first is None else min(first, s)
                last = e if last is None else max(last, e)
    return first, last


def remove_leaderkit(timeline, log):
    """Cancella marker, clip e tracce creati da LeaderKit. Restituisce i conteggi."""
    markers = timeline.GetMarkers() or {}
    n_markers = 0
    for frame, info in list(markers.items()):
        if str(info.get("customData", "")).startswith(layout.CUSTOM_DATA_PREFIX):
            if timeline.DeleteMarkerAtFrame(frame):
                n_markers += 1
    n_items = 0
    for kind in ("video", "audio"):
        doomed = []
        for track in range(1, timeline.GetTrackCount(kind) + 1):
            for item in timeline.GetItemListInTrack(kind, track) or []:
                if _is_leaderkit_item(timeline, kind, track, item):
                    doomed.append(item)
        if doomed:
            timeline.DeleteClips(doomed, False)
            n_items += len(doomed)
        for track in range(timeline.GetTrackCount(kind), 0, -1):
            name = timeline.GetTrackName(kind, track) or ""
            if name.startswith(TRACK_VIDEO) and not (timeline.GetItemListInTrack(kind, track) or []):
                fn = getattr(timeline, "DeleteTrack", None)
                if fn is not None:
                    fn(kind, track)
    log("Rimossi %d marker e %d clip LeaderKit" % (n_markers, n_items))
    return n_markers, n_items


def _unique_timeline_name(project, base):
    names = set()
    for i in range(1, int(project.GetTimelineCount() or 0) + 1):
        tl = project.GetTimelineByIndex(i)
        if tl:
            names.add(tl.GetName())
    if base not in names:
        return base
    n = 2
    while "%s %d" % (base, n) in names:
        n += 1
    return "%s %d" % (base, n)


def _set_start(timeline, frame, rate):
    tc = frames_to_tc(frame, rate)
    if not _call(timeline, "SetStartTimecode", tc):
        raise ResolveError("Impossibile impostare lo start timecode %s" % tc)
    got = timeline.GetStartFrame()
    if got != frame:
        raise ResolveError("Start timecode impostato a %s ma la timeline parte da %s"
                           % (tc, frames_to_tc(got, rate)))


# --- generazione --------------------------------------------------------------

def generate(resolve, preset, slate_values, options, log=print):
    """Genera leader, slate, coda e marker. Restituisce il Plan applicato."""
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        raise ResolveError("Nessun progetto aperto")
    source = project.GetCurrentTimeline()
    if not source:
        raise ResolveError("Nessuna timeline attiva")
    media_pool = project.GetMediaPool()
    rate, width, height = timeline_format(project, source)
    log("Timeline '%s': %s, %dx%d" % (source.GetName(), rate.label(), width, height))
    mode = options.get("mode", "new_timeline")

    if mode == "in_place":
        remove_leaderkit(source, log)
        first, last = program_range(source)
        if first is None:
            raise ResolveError("La timeline è vuota: niente programma su cui calcolare FFOA/LFOA")
        plan = layout.build_plan(preset, rate, width, height, last - first + 1,
                                 slate_values, options)
        head_len = plan.ffoa - plan.start
        room = first - source.GetStartFrame()
        if room < head_len:
            raise ResolveError(
                "Servono %s prima del primo clip (ce ne sono %s). Lascia spazio in testa "
                "oppure usa la modalità 'Nuova timeline'."
                % (frames_to_tc(head_len, rate), frames_to_tc(room, rate)))
        if plan.ffoa - room < 0:
            raise ResolveError("Il primo clip è troppo lontano dall'inizio timeline (%s): "
                               "avvicinalo o usa la modalità 'Nuova timeline'"
                               % frames_to_tc(room, rate))
        _set_start(source, plan.ffoa - room, rate)
        timeline = source
        first_now, last_now = program_range(timeline)
        if first_now != plan.ffoa:
            raise ResolveError("Dopo il cambio di start TC il FFOA è a %s invece di %s"
                               % (frames_to_tc(first_now, rate), plan.tc(plan.ffoa)))
        placer = Placer(media_pool, timeline, log)
        _place_elements(placer, timeline, media_pool, plan, plan.elements, log)
        _place_audio(placer, timeline, media_pool, plan, plan.audio, log)
    else:
        estimate = _clip_frames_or(timeline_media_item(media_pool, source),
                                   int(source.GetEndFrame() - source.GetStartFrame()))
        plan = layout.build_plan(preset, rate, width, height, max(estimate, 1),
                                 slate_values, options)
        program_mpi = timeline_media_item(media_pool, source)
        name = _unique_timeline_name(project, "%s — LeaderKit %s" % (source.GetName(), preset["name"]))
        timeline = media_pool.CreateEmptyTimeline(name)
        if not timeline:
            raise ResolveError("Impossibile creare la timeline '%s'" % name)
        project.SetCurrentTimeline(timeline)
        _copy_format(source, timeline, rate, width, height, log)
        _set_start(timeline, plan.start, rate)
        placer = Placer(media_pool, timeline, log)
        # Prima la testa (calibra l'API), poi il programma, poi la coda sulla
        # durata reale del programma annidato.
        head = [e for e in plan.elements if e.start < plan.ffoa]
        _place_elements(placer, timeline, media_pool, plan, head, log)
        _place_audio(placer, timeline, media_pool, plan,
                     [a for a in plan.audio if a.start < plan.ffoa], log)
        program = placer.place(program_mpi, plan.ffoa, max(estimate, 1), 1, strict=False)
        real = program.GetDuration()
        if real != plan.program_duration:
            plan = layout.build_plan(preset, rate, width, height, real, slate_values, options)
        log("Programma annidato su V1/A1: %s → %s" % (plan.tc(plan.ffoa), plan.tc(plan.lfoa)))
        _place_elements(placer, timeline, media_pool, plan,
                        [e for e in plan.elements if e.start > plan.lfoa], log)
        _place_audio(placer, timeline, media_pool, plan,
                     [a for a in plan.audio if a.start > plan.lfoa], log)

    _place_markers(timeline, plan, log)
    log(plan.summary())
    return plan


def _clip_frames_or(mpi, fallback):
    frames = _clip_frames(mpi)
    return frames if frames > 0 else fallback


def _copy_format(source, timeline, rate, width, height, log):
    """La nuova timeline eredita frame rate e risoluzione della sorgente."""
    got_rate, got_w, got_h = timeline_format_safe(timeline)
    if (got_rate, got_w, got_h) == (rate, width, height):
        return
    timeline.SetSetting("useCustomSettings", "1")
    timeline.SetSetting("timelineFrameRate", rate.label_number())
    timeline.SetSetting("timelineDropFrameTimecode", "1" if rate.drop_frame else "0")
    timeline.SetSetting("timelineResolutionWidth", str(width))
    timeline.SetSetting("timelineResolutionHeight", str(height))
    got_rate, got_w, got_h = timeline_format_safe(timeline)
    if (got_rate, got_w, got_h) != (rate, width, height):
        raise ResolveError("La nuova timeline non accetta %s %dx%d (risulta %s %sx%s)"
                           % (rate.label(), width, height, got_rate, got_w, got_h))
    log("Impostazioni personalizzate copiate sulla nuova timeline")


def timeline_format_safe(timeline):
    try:
        rate = FrameRate.parse(timeline.GetSetting("timelineFrameRate"),
                               str(timeline.GetSetting("timelineDropFrameTimecode")) == "1")
        return (rate, int(float(timeline.GetSetting("timelineResolutionWidth"))),
                int(float(timeline.GetSetting("timelineResolutionHeight"))))
    except Exception:
        return (None, None, None)


def _place_elements(placer, timeline, media_pool, plan, elements, log):
    if not elements:
        return
    longest = max(e.duration for e in plan.elements)
    black = black_sequence_item(media_pool, plan.width, plan.height, longest,
                                plan.rate.nominal, log)
    vtrack = _ensure_track(timeline, "video", TRACK_VIDEO)
    comp_dir = tempfile.mkdtemp(prefix="leaderkit-comps-")
    for i, element in enumerate(elements):
        item = placer.place(black, element.start, element.duration, vtrack, media_type=1)
        try:
            item.SetClipColor(CLIP_COLOR)
        except Exception:
            pass
        graph = fusion.graph_for_element(element, plan)
        if graph is None:
            continue
        path = os.path.join(comp_dir, "%03d_%s.comp" % (i, element.kind))
        with open(path, "wb") as fh:
            fh.write(graph.to_comp(element.duration).encode("utf-8"))
        if not item.ImportFusionComp(path):
            plan.warnings.append("Composizione Fusion non importata su %s a %s"
                                 % (element.kind, plan.tc(element.start)))
    log("Posizionati %d elementi video sulla traccia '%s'" % (len(elements), TRACK_VIDEO))


def _place_audio(placer, timeline, media_pool, plan, events, log):
    if not events:
        return
    atrack = _ensure_track(timeline, "audio", TRACK_AUDIO, "mono")
    for a in events:
        clip = pop_item(media_pool, a.tone_hz, a.level_dbfs)
        placer.place(clip, a.start, a.duration, atrack, media_type=2)
    log("Posizionati %d pop sulla traccia '%s'" % (len(events), TRACK_AUDIO))


def _place_markers(timeline, plan, log):
    start = timeline.GetStartFrame()
    added = 0
    for m in plan.markers:
        if timeline.AddMarker(m.frame - start, m.color, m.name, m.note, m.duration, m.custom_data):
            added += 1
        else:
            plan.warnings.append("Marker '%s' non aggiunto a %s" % (m.name, plan.tc(m.frame)))
    log("Aggiunti %d marker" % added)
