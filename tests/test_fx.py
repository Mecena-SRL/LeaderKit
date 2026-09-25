"""Test dei generatori Fusion (LeaderKit Head/Tail) e del motore Lua dei bottoni.

Le espressioni vengono estratte dal .setting ed eseguite fotogramma per
fotogramma con lua5.4 e un comp simulato (tests/lua_harness.lua); il motore
(fx/engine.lua) gira su un Resolve simulato (tests/engine_harness.lua).
"""

import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUA = shutil.which("lua5.4")
pytestmark = pytest.mark.skipif(LUA is None, reason="serve lua5.4")

sys.path.insert(0, os.path.join(ROOT, "tools"))
import build_fx  # noqa: E402


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    build_fx.build()
    return os.path.join(ROOT, "dist")


STD = build_fx.load_standards()
IDX = dict((p["id"], i) for i, p in enumerate(STD["presets"]))


def frames(setting, fps, w, h, n, preset, cd=8, tail=(1, 0, 4, 7)):
    args = [LUA, os.path.join(ROOT, "tests", "lua_harness.lua"), setting, str(fps), str(w), str(h), str(n),
            str(preset), str(cd)] + [str(x) for x in tail]
    out = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert out.returncode == 0, out.stderr.decode()
    rows = []
    for line in out.stdout.decode().splitlines():
        parts = line.split("\t")
        row = {"t": int(parts[0])}
        for p in parts[1:]:
            k, _, v = p.partition("=")
            row[k] = v
        rows.append(row)
    return rows


def on(row, key):
    return float(row[key]) > 0.5


HEAD = lambda built: os.path.join(built, "LeaderKit Head.setting")  # noqa: E731
TAIL = lambda built: os.path.join(built, "LeaderKit Tail.setting")  # noqa: E731


@pytest.mark.parametrize("fps,nominal,w,h", [(24, 24, 1920, 1080), (25, 25, 3840, 2160),
                                             (23.976, 24, 1998, 1080), (29.97, 30, 3840, 1920),
                                             (59.94, 60, 1920, 1080)])
def test_head_cinema(built, fps, nominal, w, h):
    n = 18 * nominal                       # slate 8" + nero 2" + countdown 8"
    rows = frames(HEAD(built), fps, w, h, n, IDX["cinema_dcp"])
    for r in rows:
        rem = n - r["t"]
        assert on(r, "MSlate.Blend") == (10 * nominal < rem <= 18 * nominal)
        assert on(r, "MPicStart.Blend") == (rem == 8 * nominal)
        assert on(r, "MLeader.Blend") == (2 * nominal <= rem <= 8 * nominal)
        assert not on(r, "MBars.Blend") and not on(r, "MFlash.Blend")
        digit = r["LDigit.StyledText"]
        if 2 * nominal < rem < 8 * nominal:
            assert digit == str(-(-rem // nominal))
            assert on(r, "LM4.Blend")
        elif rem == 2 * nominal:
            assert digit == "2" and not on(r, "LM4.Blend")
        else:
            assert digit == ""
        assert not on(r, "MWarn.Blend")
    assert rows[0]["LLineV.Height"].startswith(str(h / w)[:6])


def test_head_dpp(built):
    n = 30 * 25                            # barre 20" + clock 7" + nero 3"
    rows = frames(HEAD(built), 25, 1920, 1080, n, IDX["dpp_uk"], cd=0)
    for r in rows:
        rem = n - r["t"]
        assert on(r, "MBars.Blend") == (rem > 250)
        assert on(r, "MSlate.Blend") == (75 < rem <= 250)
        assert not on(r, "MLeader.Blend")
        # sync DPP: 2 fotogrammi bianchi a 09:59:57:06 = 69 fotogrammi prima del FFOA
        assert on(r, "MFlash.Blend") == (rem in (69, 68)), rem
        assert not on(r, "MWarn.Blend")
    assert on(rows[300], "SM4.Blend")      # orologio visibile nella slate
    assert rows[n - 100]["CkDigit.StyledText"] == "4"
    assert "BROADCAST UK" in rows[300]["SHeading.StyledText"]


def test_head_flash_scales_with_fps(built):
    n = 30 * 50
    rows = frames(HEAD(built), 50, 1920, 1080, n, IDX["dpp_uk"], cd=0)
    flash = [n - r["t"] for r in rows if on(r, "MFlash.Blend")]
    assert flash == [138, 137, 136, 135]   # 09:59:57:12 @50, 4 fotogrammi (variante SVT)


def test_head_rai(built):
    n = 8 * 25
    rows = frames(HEAD(built), 25, 1920, 1080, n, IDX["rai_spot"], cd=0)
    for r in rows:
        rem = n - r["t"]
        assert on(r, "MSlate.Blend") == (rem > 75)
        assert not on(r, "MLeader.Blend") and not on(r, "MPicStart.Blend") and not on(r, "MFlash.Blend")
    assert "LOUDNESS -23,0 LUFS" in rows[0]["SDetails.StyledText"]
    assert "1920 x 1080" in rows[0]["SDetails.StyledText"]


def test_head_length_hint(built):
    rows = frames(HEAD(built), 24, 1920, 1080, 120, IDX["cinema_dcp"])
    assert all(on(r, "MWarn.Blend") for r in rows)
    assert "diventa di 18 secondi" in rows[0]["Warn.StyledText"]
    rows = frames(HEAD(built), 25, 1920, 1080, 120, IDX["dpp_uk"], cd=0)
    assert "diventa di 30 secondi" in rows[0]["Warn.StyledText"]


def test_slate_text(built):
    rows = frames(HEAD(built), 23.976, 1920, 1080, 480, IDX["cinema_dcp"])
    d = rows[0]["SDetails.StyledText"]
    assert "DIRECTOR   Regista" in d and "23.976 fps" in d and "FFOA 01:00:08:00" in d
    assert rows[0]["STitle.StyledText"] == "IL FILM"


@pytest.mark.parametrize("fps,nominal", [(24, 24), (25, 25), (29.97, 30)])
def test_tail(built, fps, nominal):
    n = 8 * nominal
    rows = frames(TAIL(built), fps, 1920, 1080, n, 0, tail=(1, 0, 4, 7))
    for r in rows:
        assert on(r, "MPop.Blend") == (r["t"] == 2 * nominal - 1)
        assert on(r, "MCard.Blend") == (4 * nominal <= r["t"] < 7 * nominal)
        assert not on(r, "MFlash.Blend")
    rows = frames(TAIL(built), fps, 1920, 1080, n, 0, tail=(0, 1, 0, 0))
    assert [r["t"] for r in rows if on(r, "MFlash.Blend")] == [2 * nominal - 1]
    assert not any(on(r, "MPop.Blend") or on(r, "MCard.Blend") for r in rows)


@pytest.fixture(scope="module")
def code(tmp_path_factory):
    d = tmp_path_factory.mktemp("code")
    paths = {}
    for mode in ("generate", "remove"):
        p = d / ("%s.lua" % mode)
        p.write_text(build_fx.engine(mode))
        paths[mode] = str(p)
    return paths


def run_engine(code, **kw):
    args = [LUA, os.path.join(ROOT, "tests", "engine_harness.lua"), code["generate"],
            "removecode=%s" % code["remove"]]
    for k, v in kw.items():
        if k == "preset":
            v = IDX.get(v, v)
        args.append("%s=%s" % (k, v))
    out = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    text = out.stdout.decode()
    assert out.returncode == 0, out.stderr.decode() + text
    assert "ERRORE" not in text, text
    result = {}
    for line in text.splitlines():
        if line.startswith("RESULT "):
            k, _, v = line[7:].partition("=")
            result.setdefault(k, []).append(v)
    return result, text


def markers_of(res):
    out = {}
    for m in res.get("marker", []):
        name, tc, dur = m.split("|")
        out[name] = (tc, int(dur))
    return out


@pytest.mark.parametrize("fps,df,variant,marks", [("24", "0", 1, "abs_incl"), ("25", "0", 2, "rel_incl"),
                                                   ("29.97", "1", 1, "abs_incl")])
def test_engine_cinema(code, fps, df, variant, marks):
    res, log = run_engine(code, fps=fps, df=df, preset="cinema_dcp", head=5, progstart=18, program=125,
                          variant=variant, marks=marks)
    sep = ";" if df == "1" else ":"
    nominal = {"24": 24, "25": 25, "29.97": 30}[fps]
    assert res["starttc"][-1] == "00:59:50%s00" % sep, log
    start, dur, title = res["head"][0].split("|")
    assert start == "00:59:50%s00" % sep and int(dur) == 18 * nominal
    assert title == "Il film"
    m = markers_of(res)
    assert m["FFOA"][0] == "01:00:08%s00" % sep and m["2-POP"][0] == "01:00:06%s00" % sep
    assert m["SLATE"][0] == "00:59:50%s00" % sep
    assert res["pop"][0] == "01:00:06%s00|1" % sep and len(res["pop"]) == 2
    assert "start=" in res["tail"][0] and "dur=%d" % (8 * nominal) in res["tail"][0] and "pop=1" in res["tail"][0]
    assert res["duration"] == (["00:02:05;04"] if df == "1" else ["00:02:05:00"])
    assert "programma da 01:00:08%s00" % sep in res["guide"][0]
    assert "CONTROLLI" in log and "Il programma inizia esattamente al FFOA" in log
    if fps == "29.97":
        assert "NTSC" in log                                   # avviso DCP


def test_engine_dpp_bars_sync(code):
    res, log = run_engine(code, fps="25", df="0", preset="dpp_uk", head=5, progstart=30, program=600)
    assert res["starttc"][-1] == "09:59:30:00", log
    m = markers_of(res)
    assert m["BARS"][0] == "09:59:30:00" and m["CLOCK"][0] == "09:59:50:00"
    assert m["SYNC"][0] == "09:59:57:06" and m["FFOA"][0] == "10:00:00:00"
    pops = res["pop"]
    assert "09:59:30:00|500" in pops                          # 20" di tono di line-up
    assert "09:59:57:06|1" in pops                            # tono del sync
    assert "dur=25" in res["tail"][0]                         # 1" di nero
    assert "Frame rate 25 previsto" in log


def test_engine_rai_slot(code):
    # contenitore 30" (slot index 3), montato esatto
    res, log = run_engine(code, fps="25", df="0", preset="rai_spot", head=5, progstart=8, program=30,
                          durmode=1, slot=3)
    m = markers_of(res)
    assert res["starttc"][-1] == "09:59:52:00", log
    assert m["LFOA"][0] == "10:00:29:24" and m["CONTENITORE"][0] == "10:00:00:01"
    assert "riempie esattamente il contenitore" in log
    assert "dur=75" in res["tail"][0]


def test_engine_rai_slot_too_long(code):
    res, log = run_engine(code, fps="25", df="0", preset="rai_spot", head=5, progstart=8, program=31,
                          durmode=1, slot=3)
    assert "piu' lungo del contenitore di 25 fotogrammi" in log
    assert "Coda non inserita" in log and "tail" not in res


def test_engine_custom_container_empty(code):
    # documentario 52' senza montato: si crea il contenitore da riempire
    res, log = run_engine(code, fps="25", df="0", preset="review", head=5, progstart=0, program=0,
                          durmode=2, programtc="00:52:00:00")
    m = markers_of(res)
    assert m["LFOA"][0] == "01:51:59:24"
    assert "Contenitore vuoto" in log
    assert "start=01:52:00:00" in res["tail"][0]


def test_engine_netflix(code):
    res, log = run_engine(code, fps="24", df="0", preset="netflix", head=5, progstart=1, program=60)
    assert res["starttc"][-1] == "00:59:59:00", log
    assert res["head"][0].split("|")[1] == "24"                # 1" di nero
    assert "pop" not in res and "dur=24" in res["tail"][0]


def test_engine_music_clap(code):
    res, log = run_engine(code, fps="25", df="0", preset="music", head=5, progstart=11, program=200)
    m = markers_of(res)
    assert m["SYNC"][0] == "00:59:58:00" and "TAIL CLAP" in m
    assert "flash=1" in res["tail"][0]


def test_engine_not_enough_space(code):
    res, log = run_engine(code, fps="24", df="0", preset="cinema_dcp", head=5, progstart=5, program=60)
    assert "mancano 00:00:13:00" in log and "Sposta il programma a 01:00:18:00" in log
    assert "pop" not in res and "tail" not in res
    assert res["head"][0].split("|")[1] == str(5 * 24)


def test_engine_marks_not_supported(code):
    res, log = run_engine(code, fps="25", df="0", preset="cinema_dcp", head=5, progstart=20, program=60, marks="none")
    assert "ignora In/Out" in log


def test_engine_reels_and_regenerate(code):
    res, log = run_engine(code, fps="24", df="0", preset="cinema_dcp", head=5, progstart=18, program=45 * 60,
                          runs=2, usermarker=1)
    names = [x.split("|", 1)[0] for x in res["marker"]]
    assert names.count("Fine rullo 1") == 1 and names.count("Fine rullo 2") == 1
    assert names.count("FFOA") == 1 and "nota utente" in names
    assert len(res["pop"]) == 2 and len(res["tail"]) == 1 and len(res["head"]) == 1


def test_engine_remove(code):
    res, log = run_engine(code, fps="25", df="0", preset="rai_spot", head=5, progstart=8, program=30, remove=1)
    assert res["after_remove_markers"] == ["0"]


def test_engine_beep_each_second(code):
    res, log = run_engine(code, fps="25", df="0", preset="cinema_dcp", head=5, progstart=18, program=60, beep=1)
    pops = sorted(p.split("|")[0] for p in res["pop"])
    assert pops[:7] == ["01:00:00:00", "01:00:01:00", "01:00:02:00", "01:00:03:00",
                        "01:00:04:00", "01:00:05:00", "01:00:06:00"], pops
    assert len(pops) == 8
