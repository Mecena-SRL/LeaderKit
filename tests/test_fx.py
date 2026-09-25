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


def frames(setting, fps, w, h, n, preset, cd=8):
    out = subprocess.run([LUA, os.path.join(ROOT, "tests", "lua_harness.lua"), setting,
                          str(fps), str(w), str(h), str(n), str(preset), str(cd)],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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


@pytest.mark.parametrize("fps,nominal,w,h", [(24, 24, 1920, 1080), (25, 25, 3840, 2160),
                                             (23.976, 24, 1998, 1080), (29.97, 30, 3840, 1920),
                                             (59.94, 60, 1920, 1080)])
def test_head_cinema(built, fps, nominal, w, h):
    n = 18 * nominal                       # clip di 18": slate 8" + nero 2" + leader 8"
    rows = frames(os.path.join(built, "LeaderKit Head.setting"), fps, w, h, n, 0)
    ffoa = n                               # il fotogramma dopo il clip
    for r in rows:
        rem = ffoa - r["t"]
        slate, leader = on(r, "MSlate.Blend"), on(r, "MLeader.Blend")
        ps, digit = on(r, "MPicStart.Blend"), r["LDigit.StyledText"]
        assert slate == (rem > 10 * nominal)
        assert ps == (rem == 8 * nominal)                       # Picture Start: 1 fotogramma
        assert leader == (2 * nominal <= rem <= 8 * nominal)
        if 2 * nominal < rem < 8 * nominal:
            assert digit == str(-(-rem // nominal))             # 8..3
            assert on(r, "LM4.Blend")                           # braccio visibile
        elif rem == 2 * nominal:
            assert digit == "2" and not on(r, "LM4.Blend")      # 2-pop: 1 fotogramma
        else:
            assert digit == ""
        assert not on(r, "MWarn.Blend")
    # proporzioni: braccio e croce seguono l'aspect ratio del raster
    assert rows[0]["LLineV.Height"].startswith(str(h / w)[:6])


def test_head_rai(built):
    n = 8 * 25
    rows = frames(os.path.join(built, "LeaderKit Head.setting"), 25, 1920, 1080, n, 1)
    for r in rows:
        rem = n - r["t"]
        assert on(r, "MSlate.Blend") == (rem > 75)               # ident 5", poi 3" di nero
        assert not on(r, "MLeader.Blend") and not on(r, "MPicStart.Blend")
    assert "LOUDNESS -23 LUFS" in rows[0]["SDetails.StyledText"]
    assert "1920 x 1080" in rows[0]["SDetails.StyledText"]
    assert "25 fps" in rows[0]["SDetails.StyledText"]


def test_head_length_hint(built):
    # blocco appena trascinato (5"): mostra la durata che avra' dopo Genera
    rows = frames(os.path.join(built, "LeaderKit Head.setting"), 24, 1920, 1080, 120, 0)
    assert all(on(r, "MWarn.Blend") for r in rows)
    assert "diventa di 18 secondi" in rows[0]["Warn.StyledText"]
    rows = frames(os.path.join(built, "LeaderKit Head.setting"), 24, 1920, 1080, 18 * 24, 0)
    assert not any(on(r, "MWarn.Blend") for r in rows)


def test_slate_text(built):
    rows = frames(os.path.join(built, "LeaderKit Head.setting"), 23.976, 1920, 1080, 480, 0)
    d = rows[0]["SDetails.StyledText"]
    assert "DIRECTOR   Regista" in d and "23.976 fps" in d and "FFOA 01:00:08:00" in d
    assert rows[0]["STitle.StyledText"] == "IL FILM"


@pytest.mark.parametrize("fps,nominal", [(24, 24), (25, 25), (29.97, 30)])
def test_tail(built, fps, nominal):
    n = 8 * nominal
    rows = frames(os.path.join(built, "LeaderKit Tail.setting"), fps, 1920, 1080, n, 0)
    for r in rows:
        # tail pop a LFOA + 2": primo fotogramma della coda = LFOA + 1
        assert on(r, "MPop.Blend") == (r["t"] == 2 * nominal - 1)
        assert on(r, "MCard.Blend") == (r["t"] >= 3 * nominal)
    rows = frames(os.path.join(built, "LeaderKit Tail.setting"), fps, 1920, 1080, n, 1)
    assert not any(on(r, "MPop.Blend") or on(r, "MCard.Blend") for r in rows)


def run_engine(**kw):
    args = [LUA, os.path.join(ROOT, "tests", "engine_harness.lua"), os.path.join(ROOT, "fx", "engine.lua")]
    for k, v in kw.items():
        args.append("%s=%s" % (k, v))
    out = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert out.returncode == 0, out.stderr.decode() + out.stdout.decode()
    result = {}
    for line in out.stdout.decode().splitlines():
        if line.startswith("RESULT "):
            k, _, v = line[7:].partition("=")
            result.setdefault(k, []).append(v)
    return result, out.stdout.decode()


@pytest.mark.parametrize("fps,df,variant,marks", [("24", "0", 1, "abs_incl"), ("25", "0", 2, "rel_incl"),
                                                   ("29.97", "1", 3, "abs_incl")])
def test_engine_cinema(fps, df, variant, marks):
    # blocco da 5" a inizio timeline, programma lasciato a 18" (spazio giusto)
    res, log = run_engine(fps=fps, df=df, preset=0, head=5, progstart=18, program=125,
                          variant=variant, marks=marks)
    sep = ";" if df == "1" else ":"
    nominal = {"24": 24, "25": 25, "29.97": 30}[fps]
    assert res["starttc"][-1] == "00:59:50%s00" % sep, log
    start, dur, title = res["head"][0].split("|")
    assert start == "00:59:50%s00" % sep and int(dur) == 18 * nominal   # allungato da 5" a 18"
    assert title == "Il film"                                         # parametri ricopiati
    markers = dict(m.split("|", 1) for m in res["marker"])
    assert markers["FFOA"] == "01:00:08%s00" % sep
    assert markers["2-POP"] == "01:00:06%s00" % sep
    assert res["pop"][0] == "01:00:06%s00|1" % sep and len(res["pop"]) == 2
    assert "Fine rullo 1" not in markers
    tail = res["tail"][0]
    assert tail.startswith("preset=0")
    assert "Coda: " in log and "allungala a mano" not in log
    # 125" nominali; in drop-frame 3750 fotogrammi si scrivono 00:02:05;04
    assert res["duration"] == (["00:02:05;04"] if df == "1" else ["00:02:05:00"])
    assert "programma da 01:00:08%s00" % sep in res["guide"][0]


def test_engine_not_enough_space():
    res, log = run_engine(fps="24", df="0", preset=0, head=5, progstart=5, program=60)
    assert "servono altri 00:00:13:00" in log
    assert "Sposta il programma a 01:00:18:00" in log
    assert "pop" not in res and "tail" not in res
    assert res["head"][0].split("|")[1] == str(5 * 24)              # blocco non toccato


def test_engine_marks_not_supported():
    res, log = run_engine(fps="25", df="0", preset=0, head=5, progstart=20, program=60, marks="none")
    assert "ignora In/Out" in log                                     # avviso onesto, nessun crash


def test_engine_reels_and_regenerate():
    res, log = run_engine(fps="24", df="0", preset=0, head=5, progstart=18, program=45 * 60,
                          runs=2, usermarker=1)
    names = [m.split("|", 1)[0] for m in res["marker"]]
    assert names.count("Fine rullo 1") == 1 and names.count("Fine rullo 2") == 1
    assert names.count("FFOA") == 1 and "nota utente" in names
    assert len(res["pop"]) == 2 and len(res["tail"]) == 1            # rigenerato senza doppioni
    assert len(res["head"]) == 1


def test_engine_rai_and_remove():
    # slate di default 8" (RAI chiede almeno 5") + 3" di nero = 11"
    res, log = run_engine(fps="25", df="0", preset=1, head=5, progstart=11, program=30, remove=1)
    assert res["starttc"][-1] == "09:59:49:00", log
    assert res["head"][0].split("|")[1] == str(11 * 25)
    assert res.get("pop", []) == []
    assert res["after_remove_markers"] == ["0"]


def test_engine_beep_each_second():
    res, log = run_engine(fps="25", df="0", preset=0, head=5, progstart=18, program=60, beep=1)
    pops = [p.split("|")[0] for p in res["pop"]]
    # bip su 8..3 + 2-pop + tail pop
    assert pops[:7] == ["01:00:00:00", "01:00:01:00", "01:00:02:00", "01:00:03:00",
                        "01:00:04:00", "01:00:05:00", "01:00:06:00"], pops
    assert len(pops) == 8
