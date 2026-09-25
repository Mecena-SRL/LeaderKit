import os

import pytest

from conftest import PRESETS_DIR
from leaderkit import layout, presets
from leaderkit.timecode import FrameRate

CINEMA = presets.load_file(os.path.join(PRESETS_DIR, "cinema_dcp.json"))
RAI = presets.load_file(os.path.join(PRESETS_DIR, "spot_rai.json"))

# Le combinazioni fps/risoluzione richieste + i drop-frame.
COMBOS = [
    ("24", False, 1920, 1080),
    ("25", False, 3840, 2160),
    ("23.976", False, 1998, 1080),
    ("29.97", True, 1920, 1080),
    ("59.94", True, 3840, 2160),
    ("48", False, 4096, 1716),
]


def plan_for(preset, rate, w, h, seconds=125, **options):
    return layout.build_plan(preset, rate, w, h, seconds * rate.nominal + 7,
                             {"title": "Test", "director": "Regia"}, options)


def assert_contiguous(elements):
    for a, b in zip(elements, elements[1:]):
        assert a.end == b.start or b.start > a.end  # testa e coda sono separate dal programma


@pytest.mark.parametrize("fps,df,w,h", COMBOS)
def test_cinema_head_is_frame_accurate(fps, df, w, h):
    r = FrameRate.parse(fps, df)
    p = plan_for(CINEMA, r, w, h)
    sep = ";" if df else ":"
    assert p.tc(p.ffoa) == "01:00:08%s00" % sep
    # 2-pop: 1 fotogramma, esattamente 2 secondi nominali prima del FFOA.
    pop = [a for a in p.audio if a.start < p.ffoa][0]
    assert p.ffoa - pop.start == 2 * r.nominal
    assert p.tc(pop.start) == "01:00:06%s00" % sep
    assert pop.duration == 1
    # Picture Start a 01:00:00:00, un solo fotogramma.
    ps = [e for e in p.elements if e.kind == "picture_start"][0]
    assert p.tc(ps.start) == "01:00:00%s00" % sep and ps.duration == 1
    # Countdown 8..3: ogni cifra termina esattamente al secondo successivo.
    digits = [e for e in p.elements if e.kind == "countdown"]
    assert [e.params["digit"] for e in digits] == [8, 7, 6, 5, 4, 3]
    for e in digits:
        assert e.end == p.ffoa - (e.params["digit"] - 1) * r.nominal
    assert digits[0].duration == r.nominal - 1 and digits[0].params["phase"] == 1
    assert all(e.duration == r.nominal for e in digits[1:])
    # Nero tra pop e FFOA, niente buchi da slate a FFOA.
    head = p.head_elements()
    assert head[-1].kind == "black" and head[-1].end == p.ffoa
    for a, b in zip(head, head[1:]):
        assert a.end == b.start
    assert p.tc(p.start) == "00:59:50%s00" % sep
    assert head[0].kind == "slate" and head[0].duration == 8 * r.nominal


@pytest.mark.parametrize("fps,df,w,h", COMBOS)
def test_cinema_tail_symmetric(fps, df, w, h):
    r = FrameRate.parse(fps, df)
    p = plan_for(CINEMA, r, w, h)
    tail_pop = [a for a in p.audio if a.start > p.lfoa][0]
    head_pop = [a for a in p.audio if a.start < p.ffoa][0]
    assert tail_pop.start - p.lfoa == p.ffoa - head_pop.start == 2 * r.nominal
    tail = p.tail_elements()
    assert tail[0].start == p.lfoa + 1
    for a, b in zip(tail, tail[1:]):
        assert a.end == b.start
    assert tail[-1].end == p.lfoa + 1 + 8 * r.nominal
    card = [e for e in tail if e.kind == "card"][0]
    assert card.params["text"] == "END OF PROGRAM"
    assert p.end == p.lfoa + 1 + 8 * r.nominal


@pytest.mark.parametrize("fps,df,w,h", COMBOS)
def test_rai_layout(fps, df, w, h):
    r = FrameRate.parse(fps, df)
    p = plan_for(RAI, r, w, h, seconds=30, target_duration="30s")
    sep = ";" if df else ":"
    assert p.tc(p.ffoa) == "10:00:00%s00" % sep
    head = p.head_elements()
    assert [e.kind for e in head] == ["slate", "black"]
    assert head[0].duration == 5 * r.nominal           # ident >= 5"
    assert head[1].duration == 3 * r.nominal           # 3" di nero
    assert p.tc(head[0].start) == "09:59:52%s00" % sep
    tail = p.tail_elements()
    assert [e.kind for e in tail] == ["black"] and tail[0].duration == 3 * r.nominal
    assert p.audio == []
    # 30" + 7 fotogrammi: il controllo durata deve segnalare +7.
    assert p.duration_delta == 7
    assert any("+7 fotogrammi" in w_ for w_ in p.warnings)


def test_same_preset_two_timelines_differ_natively():
    a = plan_for(CINEMA, FrameRate.parse("24"), 1920, 1080)
    b = plan_for(CINEMA, FrameRate.parse("25"), 3840, 2160)
    assert a.ffoa - [x for x in a.audio if x.start < a.ffoa][0].start == 48
    assert b.ffoa - [x for x in b.audio if x.start < b.ffoa][0].start == 50
    assert (a.width, a.height) == (1920, 1080) and (b.width, b.height) == (3840, 2160)


def test_reel_markers_and_hour_per_reel():
    r = FrameRate.parse("24")
    p = layout.build_plan(CINEMA, r, 1920, 1080, 45 * 60 * 24, {}, {"reel": 2})
    assert p.tc(p.ffoa) == "02:00:08:00"
    reels = [m for m in p.markers if m.custom_data.startswith("leaderkit:reel")]
    assert [m.name for m in reels] == ["Fine rullo 1", "Fine rullo 2"]
    assert reels[0].frame - p.ffoa == 20 * 60 * 24
    assert all(m.color == "Red" for m in reels)
    assert all(m.custom_data.startswith("leaderkit:") for m in p.markers)


def test_break_markers_override():
    r = FrameRate.parse("29.97", True)
    p = layout.build_plan(RAI, r, 1920, 1080, 12 * 60 * 30, {},
                          {"markers_enabled": True, "marker_kind": "break", "marker_every": "5m"})
    breaks = [m for m in p.markers if m.name.startswith("Break")]
    assert len(breaks) == 2
    assert breaks[0].frame - p.ffoa == 5 * 60 * 30
    assert breaks[0].color == "Yellow"


def test_warnings():
    p = plan_for(CINEMA, FrameRate.parse("23.976"), 1920, 1080)
    assert any("digital cinema" in w for w in p.warnings)
    p = plan_for(RAI, FrameRate.parse("24"), 3840, 2160, seconds=30)
    assert any("25" in w for w in p.warnings)
    assert any("3840x2160" in w for w in p.warnings)


def test_slate_values_auto():
    r = FrameRate.parse("25")
    p = layout.build_plan(CINEMA, r, 3840, 2160, 90 * 25, {"title": "Il film", "fps": "hack"})
    assert p.slate_title == "Il film"
    assert p.slate_values["fps"] == "25 fps"
    assert p.slate_values["duration"] == "00:01:30:00"
    assert "RESOLUTION   3840 × 2160" in p.slate_lines
    assert any(l.startswith("FFOA 01:00:08:00") for l in p.slate_lines)


def test_no_head_no_tail():
    r = FrameRate.parse("25")
    p = layout.build_plan(CINEMA, r, 1920, 1080, 100, {},
                          {"include_head": False, "include_tail": False})
    assert p.elements == [] and p.audio == []
    assert p.start == p.ffoa


def test_bad_preset_detected():
    bad = dict(CINEMA)
    bad["head"] = [{"type": "slate", "start": "-1s", "duration": "3s"}]
    with pytest.raises(layout.LayoutError):
        layout.build_plan(bad, FrameRate.parse("25"), 1920, 1080, 100)
    with pytest.raises(presets.PresetError):
        presets.validate({"schema": 1, "id": "x", "name": "x", "ffoa_tc": "01:00:00:00",
                          "head": [{"type": "nope"}]})


def test_load_all_user_override(tmp_path):
    import json
    user = dict(RAI)
    user.pop("_path")
    user["name"] = "Spot RAI (mio)"
    (tmp_path / "rai.json").write_text(json.dumps(user))
    (tmp_path / "broken.json").write_text("{")
    found, errors = presets.load_all([PRESETS_DIR, str(tmp_path)])
    names = [p["name"] for p in found]
    assert "Spot RAI (mio)" in names and "Spot RAI" not in names
    assert len(errors) == 1
