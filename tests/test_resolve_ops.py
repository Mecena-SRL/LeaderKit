import os

import pytest

import fake_resolve as fr
from conftest import PRESETS_DIR
from leaderkit import presets, resolve_ops
from leaderkit.timecode import FrameRate, frames_to_tc

CINEMA = presets.load_file(os.path.join(PRESETS_DIR, "cinema_dcp.json"))
RAI = presets.load_file(os.path.join(PRESETS_DIR, "spot_rai.json"))
SLATE = {"title": "Prova", "director": "Regista", "editor": "Montatore",
         "colorist": "Colorista", "date": "2026-09-25", "version": "v1"}


@pytest.fixture(autouse=True)
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("LEADERKIT_CACHE", str(tmp_path / "cache"))


def tc(tl, frame):
    return frames_to_tc(frame, tl.rate)


@pytest.mark.parametrize("fps,drop,w,h,end_inclusive,record_relative", [
    ("24", False, 1920, 1080, True, False),
    ("25", False, 3840, 2160, True, False),
    ("25", False, 3840, 2160, False, False),   # endFrame esclusivo -> calibrazione
    ("29.97", True, 1920, 1080, True, True),   # recordFrame relativo -> calibrazione
])
def test_new_timeline_cinema(fps, drop, w, h, end_inclusive, record_relative):
    project = fr.Project(fps, drop, w, h, end_inclusive=end_inclusive,
                         record_relative=record_relative)
    src = project.new_program_timeline("Rullo 1", 70)
    plan = resolve_ops.generate(fr.Resolve(project), CINEMA, SLATE, {}, log=lambda m: None)
    tl = project.current
    assert tl is not src and tl.name.startswith("Rullo 1 — LeaderKit")
    sep = ";" if drop else ":"
    n = tl.rate.nominal
    assert tl.GetStartTimecode() == "00:59:50%s00" % sep

    program = tl.GetItemListInTrack("video", 1)
    assert len(program) == 1 and program[0].mpi is src.mpi
    assert tc(tl, program[0].GetStart()) == "01:00:08%s00" % sep
    assert program[0].GetDuration() == 70 * n
    assert plan.program_duration == 70 * n

    video = tl.items("video", "LeaderKit")
    # Contiguità: dalla slate al FFOA e dal LFOA+1 alla fine coda.
    head = [i for i in video if i.GetStart() < program[0].GetStart()]
    tail = [i for i in video if i.GetStart() > program[0].GetStart()]
    for a, b in zip(head, head[1:]):
        assert a.GetEnd() == b.GetStart()
    assert head[-1].GetEnd() == program[0].GetStart()
    assert tail[0].GetStart() == program[0].GetEnd()
    assert tail[-1].GetEnd() - program[0].GetEnd() == 8 * n
    assert all(i.color == "Orange" for i in video)

    # Composizioni Fusion alla risoluzione reale.
    with_comp = [i for i in video if i.comps]
    assert len(with_comp) == 1 + 1 + 6 + 1 + 1 + 1   # slate, PS, 8..3, pop, tail pop, card
    for i in with_comp:
        assert "Width = Input { Value = %d, }" % w in i.comps[0]
        assert "Height = Input { Value = %d, }" % h in i.comps[0]
    slate = head[0]
    assert "Prova" in slate.comps[0] and "Regista" in slate.comps[0]
    assert "%d fps" % n in slate.comps[0] or tl.rate.label() in slate.comps[0]

    pops = tl.items("audio", "LeaderKit Pop")
    assert [tc(tl, p.GetStart()) for p in pops][0] == "01:00:06%s00" % sep
    assert all(p.GetDuration() == 1 for p in pops)
    assert program[0].GetStart() - pops[0].GetStart() == 2 * n
    assert pops[1].GetStart() - (program[0].GetEnd() - 1) == 2 * n

    names = {m["name"]: tl.GetStartFrame() + f for f, m in tl.GetMarkers().items()}
    assert tc(tl, names["FFOA"]) == "01:00:08%s00" % sep
    assert names["LFOA"] == program[0].GetEnd() - 1
    assert all(m["customData"].startswith("leaderkit:") for m in tl.GetMarkers().values())


def test_in_place_regenerate_keeps_user_markers():
    project = fr.Project("25", False, 1920, 1080)
    src = project.new_program_timeline("Spot", 30, offset=20 * 25)
    src.AddMarker(100 + 20 * 25, "Green", "nota utente", "", 1, "")
    log = []
    resolve_ops.generate(fr.Resolve(project), RAI, SLATE,
                         {"mode": "in_place", "target_duration": "30s"}, log=log.append)
    assert project.current is src
    first, last = resolve_ops.program_range(src)
    assert tc(src, first) == "10:00:00:00"
    assert tc(src, last) == "10:00:29:24"
    video = src.items("video", "LeaderKit")
    assert [i.GetDuration() for i in video] == [125, 75, 75]  # ident 5", nero 3", nero 3"
    assert tc(src, video[0].GetStart()) == "09:59:52:00"

    # Seconda esecuzione: nessun duplicato, marker utente intatto.
    resolve_ops.generate(fr.Resolve(project), RAI, SLATE, {"mode": "in_place"}, log=log.append)
    assert len(src.items("video", "LeaderKit")) == 3
    user = [m for m in src.GetMarkers().values() if m["name"] == "nota utente"]
    assert len(user) == 1
    assert sum(1 for m in src.GetMarkers().values() if m["name"] == "FFOA") == 1

    resolve_ops.remove_leaderkit(src, log.append)
    assert [m["name"] for m in src.GetMarkers().values()] == ["nota utente"]
    assert src.items("video", "LeaderKit") == []
    assert resolve_ops.program_range(src)[0] == first


def test_in_place_needs_room():
    project = fr.Project("24", False, 1920, 1080)
    project.new_program_timeline("Rullo", 60, offset=0)
    with pytest.raises(resolve_ops.ResolveError) as exc:
        resolve_ops.generate(fr.Resolve(project), CINEMA, SLATE, {"mode": "in_place"},
                             log=lambda m: None)
    assert "Nuova timeline" in str(exc.value)


def test_same_preset_two_timelines():
    """Stesso preset su 24p HD e 25p UHD: output nativo e al fotogramma su entrambe."""
    results = {}
    for fps, w, h in (("24", 1920, 1080), ("25", 3840, 2160)):
        project = fr.Project(fps, False, w, h)
        project.new_program_timeline("Film", 90)
        resolve_ops.generate(fr.Resolve(project), CINEMA, SLATE, {}, log=lambda m: None)
        tl = project.current
        pop = tl.items("audio", "LeaderKit Pop")[0]
        ffoa = tl.GetItemListInTrack("video", 1)[0].GetStart()
        results[fps] = (ffoa - pop.GetStart(), tc(tl, pop.GetStart()))
    assert results == {"24": (48, "01:00:06:00"), "25": (50, "01:00:06:00")}


def test_timeline_format_prefers_timeline_settings():
    project = fr.Project("24", False, 1920, 1080)
    tl = project.new_program_timeline("x", 1)
    tl.settings.update({"timelineFrameRate": "59.94", "timelineDropFrameTimecode": "1",
                        "timelineResolutionWidth": "3840", "timelineResolutionHeight": "2160"})
    rate, w, h = resolve_ops.timeline_format(project, tl)
    assert rate == FrameRate.parse("59.94", True) and (w, h) == (3840, 2160)


def test_drop_flag_ignored_for_non_ntsc():
    project = fr.Project("25", False, 1920, 1080)
    tl = project.new_program_timeline("x", 1)
    tl.settings["timelineDropFrameTimecode"] = "1"
    rate, _, _ = resolve_ops.timeline_format(project, tl)
    assert rate == FrameRate.parse("25")
    tl.settings.update({"timelineFrameRate": "29.97 DF", "timelineDropFrameTimecode": "0"})
    assert not resolve_ops.timeline_format(project, tl)[0].drop_frame
