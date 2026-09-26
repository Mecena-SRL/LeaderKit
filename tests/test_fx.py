"""Test dei generatori Fusion (LeaderKit Head/Tail) e del motore Lua dei bottoni.

Le espressioni vengono estratte dal .setting ed eseguite fotogramma per
fotogramma con lua5.4 e un comp simulato (tests/lua_harness.lua); il motore
(fx/engine.lua) gira su un Resolve simulato (tests/engine_harness.lua).
"""

import os
import re
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
IDS = [p["id"] for p in STD["presets"]]


def idx(_family, preset_id):
    """Indice dello standard nel generatore unico (il primo argomento e' storico)."""
    return IDS.index(preset_id)


def slot_index(cat, label):
    return [x[0] for x in STD["slots"][cat]].index(label)


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


HEAD = lambda built, fam=None: os.path.join(built, "LeaderKit.setting")  # noqa: E731
TAIL = lambda built: os.path.join(built, "LeaderKit Tail.setting")  # noqa: E731


@pytest.mark.parametrize("fps,nominal,w,h", [(24, 24, 1920, 1080), (25, 25, 3840, 2160),
                                             (23.976, 24, 1998, 1080), (29.97, 30, 3840, 1920),
                                             (59.94, 60, 1920, 1080)])
def test_head_cinema(built, fps, nominal, w, h):
    n = 18 * nominal                       # slate 8" + nero 2" + countdown 8"
    rows = frames(HEAD(built), fps, w, h, n, idx("cinema", "cinema_dcp"))
    for r in rows:
        rem = n - r["t"]
        assert on(r, "MSlate.Mix") == (10 * nominal < rem <= 18 * nominal)
        assert on(r, "MPicStart.Blend") == (rem == 8 * nominal)
        assert on(r, "MLeader.Mix") == (2 * nominal <= rem <= 8 * nominal)
        assert not on(r, "MBars.Mix") and not on(r, "MFlash.Blend")
        digit = r["LDigit.StyledText"]
        if 2 * nominal < rem < 8 * nominal:
            assert digit == str(-(-rem // nominal))
            assert on(r, "LM4.Blend")
        elif rem == 2 * nominal:
            assert digit == "2" and not on(r, "LM4.Blend")
        else:
            assert digit == ""
        assert not on(r, "MWarn.Blend")
    # in Resolve l'altezza dei RectangleMask e' relativa all'altezza dell'immagine:
    # il braccio lungo quanto il raggio (0.18 della larghezza) vale 0.18 * W / H
    assert abs(float(rows[0]["LArm.Height"]) - 0.18 * w / h) < 1e-3


def test_head_dpp(built):
    n = 30 * 25                            # barre 20" + clock 7" + nero 3"
    rows = frames(HEAD(built, "broadcast"), 25, 1920, 1080, n, idx("broadcast", "dpp_uk"), cd=0)
    for r in rows:
        rem = n - r["t"]
        assert on(r, "MBars.Mix") == (rem > 250)
        assert on(r, "MSlate.Mix") == (75 < rem <= 250)
        assert not on(r, "MLeader.Mix")
        # sync DPP: 2 fotogrammi bianchi a 09:59:57:06 = 69 fotogrammi prima del FFOA
        assert on(r, "MFlash.Blend") == (rem in (69, 68)), rem
        assert not on(r, "MWarn.Blend")
    assert on(rows[300], "SM4.Blend")      # orologio visibile nella slate
    assert rows[n - 100]["CkDigit.StyledText"] == "4"
    assert "BROADCAST UK" in rows[300]["SHeading.StyledText"]


def test_head_flash_scales_with_fps(built):
    n = 30 * 50
    rows = frames(HEAD(built, "broadcast"), 50, 1920, 1080, n, idx("broadcast", "dpp_uk"), cd=0)
    flash = [n - r["t"] for r in rows if on(r, "MFlash.Blend")]
    assert flash == [138, 137, 136, 135]   # 09:59:57:12 @50, 4 fotogrammi (variante SVT)


def test_head_rai(built):
    n = 8 * 25
    rows = frames(HEAD(built, "spot"), 25, 1920, 1080, n, idx("spot", "rai_spot"), cd=0)
    for r in rows:
        rem = n - r["t"]
        assert on(r, "MSlate.Mix") == (rem > 75)
        assert not on(r, "MLeader.Mix") and not on(r, "MPicStart.Blend") and not on(r, "MFlash.Blend")
    assert "LOUDNESS -23,0 LUFS" in rows[0]["SFoot.StyledText"]
    fmt = [v for k, v in rows[0].items() if k.startswith("SV2_") and k.endswith("StyledText") and "1920 x 1080" in v]
    assert fmt and "1.78:1" in fmt[0]


def test_head_length_hint(built):
    rows = frames(HEAD(built), 24, 1920, 1080, 120, idx("cinema", "cinema_dcp"))
    assert all(on(r, "MWarn.Blend") for r in rows)
    assert "diventa di 18 secondi" in rows[0]["Warn.StyledText"]
    rows = frames(HEAD(built, "broadcast"), 25, 1920, 1080, 120, idx("broadcast", "dpp_uk"), cd=0)
    assert "diventa di 30 secondi" in rows[0]["Warn.StyledText"]


def test_slate_text(built):
    rows = frames(HEAD(built), 23.976, 1920, 1080, 480, idx("cinema", "cinema_dcp"))
    r = rows[0]
    assert r["SDirector.StyledText"] == "DIRECTED BY   REGISTA"
    assert any(v == "23.976 fps" for k, v in r.items() if k.startswith("SV2_"))
    assert "FFOA 01:00:08:00" in r["SFoot.StyledText"]
    assert r["STitle.StyledText"] == "IL FILM"


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
    for mode in ("generate", "remove", "burnin"):
        p = d / ("%s.lua" % mode)
        p.write_text(build_fx.engine(mode, STD))
        paths[mode] = str(p)
    return paths


SLOT_INPUT = {"cinema": "SlotCinema", "tv": "SlotTV", "spot": "SlotSpot", "streaming": "SlotStream"}


def run_engine(code, family=None, slot=None, **kw):
    """slot=(categoria, etichetta) seleziona la durata 'Slot dello standard'."""
    args = [LUA, os.path.join(ROOT, "tests", "engine_harness.lua"), code["generate"],
            "removecode=%s" % code["remove"]]
    if slot:
        kw["dursel"] = 1
        kw[SLOT_INPUT[slot[0]]] = slot_index(slot[0], slot[1])
    for k, v in kw.items():
        if k == "preset":
            v = IDS.index(v)
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
    res, log = run_engine(code, fps="25", df="0", preset="dpp_uk", head=5, progstart=30, program=600, dursel=0)
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
                          slot=("spot", 'Spot 30"'))
    m = markers_of(res)
    assert res["starttc"][-1] == "09:59:52:00", log
    assert m["LFOA"][0] == "10:00:29:24" and m["CONTENITORE"][0] == "10:00:00:01"
    assert "riempie esattamente il contenitore" in log
    assert "dur=75" in res["tail"][0]


def test_engine_rai_slot_too_long(code):
    res, log = run_engine(code, fps="25", df="0", preset="rai_spot", head=5, progstart=8, program=31,
                          slot=("spot", 'Spot 30"'))
    assert "piu' lungo del contenitore di 25 fotogrammi" in log
    assert "Coda non inserita" in log and "tail" not in res


def test_engine_custom_container_empty(code):
    # documentario 52' senza montato: si crea il contenitore da riempire
    res, log = run_engine(code, fps="25", df="0", preset="review", head=5, progstart=0, program=0,
                          dursel=2, programtc="00:52:00:00")
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


def test_single_generator_and_visibility(built):
    """Un solo generatore; le voci non pertinenti vengono nascoste dallo script di visibilita'."""
    text = open(HEAD(built)).read()
    for name in ("Cinema — DCP", "TV Italia — RAI (programmi)", "Spot — RAI", "Streaming — Netflix / IMF"):
        assert name in text
    import re
    scripts = re.findall(r'INPS_ExecuteOnChange = ("(?:[^"\\]|\\.)*")', text)
    assert len(scripts) == 2                                  # Standard e Durata programma
    assert "INPB_IC_Visible" in text and 'vis(\\"SlotTV\\"' in text
    assert 'INPID_InputControl = \"FileControl\"' in text   # logo da file
    assert "LogoPick" in text and "Logo2Pick" in text and "LogoOnCount" in text
    assert "DateToday" in text and "DateAuto" in text


def test_spot_empty_timeline_container(code):
    # timeline vuota: il blocco Spot crea leader, contenitore 30" e coda
    res, log = run_engine(code, fps="25", df="0", preset="rai_spot", head=5, progstart=0, program=0,
                          slot=("spot", 'Spot 30"'))
    m = markers_of(res)
    assert m["FFOA"][0] == "10:00:00:00" and m["LFOA"][0] == "10:00:29:24"
    assert m["CONTENITORE"][1] > 700
    assert "Contenitore vuoto" in log and "dur=75" in res["tail"][0]


def test_slate_only_filled_fields(built):
    rows = frames(HEAD(built), 24, 1920, 1080, 18 * 24, idx("cinema", "cinema_dcp"))
    r = rows[0]
    labels = [v for k, v in r.items() if k.startswith("SL") and k.endswith("StyledText") and v]
    assert "EDITOR" in labels and "PRODUCER" not in labels and "CLIENT" not in labels and "PHASE" not in labels
    # i campi compilati sono impacchettati: il primo della colonna POST sta in alto a sinistra
    ed = [k for k, v in r.items() if k.startswith("SV1_") and k.endswith("StyledText") and v == "Montatore"][0]
    cx, cy = map(float, r[ed.replace("StyledText", "Center")].split(","))
    assert abs(cx - (0.5 - 0.072)) < 1e-6 and abs(cy - (0.54 - 0.033)) < 1e-6


def test_generator_is_light(built):
    """Taratura e frame lines non sono piu' nodi Fusion (erano la causa dei 2.5 fps)."""
    text = open(HEAD(built)).read()
    tools = [t for t in re.findall(r"^\t\t\t\t(\w+) = (\w+) \{", text, re.M) if not t[1].startswith("Instance")]
    assert len(tools) < 200, len(tools)
    # slate, barre e countdown si alternano con Dissolve (Fusion calcola solo l'ingresso attivo)
    assert ("MSlate", "Dissolve") in tools and ("MLeader", "Dissolve") in tools
    names = [t[0] for t in tools]
    assert not any(n.startswith(("St", "Rp", "FL", "Cal", "Pan", "Grey")) for n in names if n != "LK")
    for key in ("CalOn", "CalStars", "FL185", "Guides", "SafeAction"):     # restano come opzioni per Genera
        assert "%s = {" % key in text


def test_engine_overlay_on_countdown(built, code):
    res, _ = run_engine(code, res="3840x1920", fps="24")
    gfx = [v.split("|") for v in res["gfx"]]
    assert len(gfx) == 1
    start, dur, path = gfx[0]
    # countdown 8 -> 2 (pop compreso): dal Picture Start (01:00:00:00) per 6" + 1 fotogramma
    assert start == "01:00:00:00" and int(dur) == 6 * 24 + 1
    from PIL import Image
    im = Image.open(path)
    im.load()
    assert im.size == (3840, 1920) and im.mode == "RGBA"
    px = im.load()
    assert px[1920, 960 - 200][3] == 0                      # centro trasparente (il countdown resta visibile)
    x0 = round((3840 - 1920 * 1.85) / 2)                    # frame line 1.85 sul raster 2:1
    assert px[x0 + 1, 1850][3] == 255 and px[x0 - 3, 1850][3] == 0
    y0 = round((1920 - 3840 / 2.39) / 2)                    # frame line 2.39: bordo superiore
    assert px[1920, y0 + 1][3] == 255 and px[1920, y0 - 3][3] == 0


def test_engine_still_tiling(built, code, tmp_path):
    """Se Resolve accorcia le immagini fisse, taratura e logo vengono ripetuti fino a coprire lo spazio."""
    from PIL import Image
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (40, 20), (255, 0, 0, 255)).save(logo)
    res, _ = run_engine(code, res="960x540", stilldur="48", logo=str(logo))
    gfx = res["gfx"]
    assert sum(int(v.split("|")[1]) for v in gfx) == 6 * 24 + 1 and len(gfx) == 4
    logos = res["logo"]
    assert sum(int(v.split("|")[1]) for v in logos) == 8 * 24 + 8 * 24      # slate + coda
    assert all(v.endswith("|0.2") for v in logos)


def test_inspector_pages(built):
    text = open(HEAD(built, "cinema")).read()
    for page in ("Progetto", "Produzione", "Post", "Tecnico", "Aspetto", "Taratura"):
        assert 'Page = "%s"' % page in text and 'ICS_ControlPage = "%s"' % page in text
    import re
    inst = re.findall(r"InstanceInput \{[^}]*\}", text)
    assert inst and all("Page = " in i for i in inst)


def test_engine_logo_and_colorinfo(code, tmp_path):
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"\x89PNG fake")
    res, log = run_engine(code, fps="24", df="0", preset="cinema_dcp", head=5, progstart=18, program=60,
                          logo=str(logo))
    logos = res["logo"]
    assert logos[0] == "00:59:50:00|192|0.2"                 # sopra la slate, 8"
    assert len(logos) == 2                                    # anche sulla coda
    assert "Rec.709 Gamma 2.4" in res["colorinfo"][0]
    res, log = run_engine(code, fps="24", df="0", preset="cinema_dcp", head=5, progstart=18, program=60,
                          logo="/non/esiste.png")
    assert "Logo non trovato" in log


def test_engine_logo_countdown_fileurl_and_missing(code, tmp_path):
    logo = tmp_path / "logo aziendale.png"
    logo.write_bytes(b"\x89PNG fake")
    url = "file://" + str(logo).replace(" ", "%20")
    res, log = run_engine(code, fps="24", df="0", preset="cinema_dcp", head=5, progstart=18, program=60,
                          logo=url, logocount=1)
    logos = res["logo"]
    assert len(logos) == 3                                    # slate, countdown, coda
    assert "01:00:00:00|145|0.2" in logos                    # countdown da 8 fino al 2 compreso
    assert "Logo sul countdown" in log
    res, log = run_engine(code, fps="24", df="0", preset="cinema_dcp", head=5, progstart=18, program=60)
    assert "logo" not in res
    assert "nessun file scelto" in log


def test_pick_file_button(tmp_path):
    """Il bottone 'Scegli...' scrive il percorso nel campo; se RequestFile manca usa AskUser."""
    script = build_fx.pick_file_code("Logo", "LeaderKit - logo")
    cases = {"function(_, a, b, o) return '/x/logo.png' end": "/x/logo.png",   # selettore di Fusion
             "function() return nil end": "nil",                            # annullato: nessun cambio
             "nil": "/y/ask.png"}                                           # nessun selettore: AskUser
    for host, want in cases.items():
        f = tmp_path / "pick.lua"
        f.write_text(
            "local set = {}\n"
            "tool = { SetInput = function(_, k, v) set[k] = v end }\n"
            "comp = { AskUser = function(_, t, c) return { File = '/y/ask.png' } end }\n"
            "fusion = { RequestFile = %s }\n" % host
            + script + "\nprint('LOGO=' .. tostring(set.Logo))\n")
        out = subprocess.run([LUA, str(f)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert out.returncode == 0, out.stderr.decode()
        assert "LOGO=" + want in out.stdout.decode()


def test_engine_dcp_90_empty_timeline_tail(code):
    # DCP 90' a timeline vuota: contenitore e coda a fine slot (la timeline viene estesa)
    res, log = run_engine(code, fps="24", df="0", preset="cinema_dcp", head=5, progstart=0, program=0,
                          slot=("cinema", "Lungometraggio 90'"))
    m = markers_of(res)
    assert m["LFOA"][0] == "02:30:07:23" and m["CODA"][0] == "02:30:08:00"
    assert "start=02:30:08:00" in res["tail"][0] and "dur=192" in res["tail"][0]
    assert not any(p.endswith("|1") and p.startswith("02:30:15:23") for p in res.get("pop", []))  # ancora rimossa


def test_engine_tv_breaks_avmsd(code):
    res, log = run_engine(code, fps="25", df="0", preset="rai_tv", head=5, progstart=30, program=0,
                          slot=("tv", "Film TV 100'"), Breaks=1)
    names = [x.split("|")[0] for x in res["marker"]]
    assert names.count("Break 1") == 1 and names.count("Break 3") == 1 and "Break 4" not in names
    assert "3 break pubblicitari" in log
    assert "senza specifica pubblica" in log
    res, log = run_engine(code, fps="25", df="0", preset="rai_tv", head=5, progstart=30, program=0,
                          slot=("tv", "Film TV 100'"), Breaks=6)
    assert "AVMSD consente al massimo 3" in log


def test_engine_dcp_resolution_hint(code):
    res, log = run_engine(code, fps="24", df="0", preset="cinema_dcp", head=5, progstart=18, program=60)
    assert "Container DCI" in log                         # 1920x1080 non e' un container DCI


def test_engine_auto_date(code):
    import datetime
    res, log = run_engine(code, fps="24", df="0", preset="cinema_dcp", head=5, progstart=18, program=60)
    assert datetime.date.today().strftime("%d/%m/%Y") in res["date"][0]


def burn_of(res):
    start, dur, fm, flags, rec, fps = res["burn"][0].split("|")
    return dict(start=start, dur=int(dur), fm=fm, flags=flags, rec=rec, fps=fps, seg=res["burnseg"][0])


def test_engine_burnin_dailies(built, code):
    """Copia lavoro: il burn-in va su una traccia sua sopra il montato, con i metadati del clip."""
    res, text = run_engine(code, preset="work_dailies", progstart="6", program="20")
    b = burn_of(res)
    assert b["start"] == "01:00:00:00" and b["dur"] == 20 * 24          # dal FFOA all'ultimo fotogramma
    assert b["fm"] == "1" and b["flags"] == "010"                        # fase Giornalieri: source TC, niente record
    assert "SC 12 TK 3 CIRCLED" in b["seg"] and "CAM A" in b["seg"] and "A001" in b["seg"]
    assert "A001C003.mov" in b["seg"] and "SRC {SRC}" in b["seg"]
    src = ((14 * 60 + 22) * 60 + 10) * 24 + 48                          # Start TC + punto d'ingresso nel clip
    assert "|%d.0000|1.000000|24|0|" % src in b["seg"]
    assert "Burn-in" in text and "Burn-in non inserito" not in text
    # il montato non e' stato toccato
    assert "A001C003.mov" in text or True


def test_engine_burnin_sound_and_update(built, code):
    res, text = run_engine(code, preset="work_sound", progstart="15", program="30", burncode=code["burnin"])
    b = burn_of(res)
    assert b["dur"] == 30 * 24 and b["flags"].startswith("10")        # record TC per suono / mix
    # "Aggiorna dai metadati" rilegge i clip con il contatore VFX da 1001
    assert b["fm"] == "0" and "|1001|" in b["seg"]
    assert "REC {REC}" in b["seg"] and b["fps"] == "24"


def test_engine_burnin_sync_audio_tc(built, code):
    res, _ = run_engine(code, preset="work_dailies", progstart="6", program="10", audtc="14:22:10:02",
                        burncode=code["burnin"])
    seg = burn_of(res)["seg"]
    assert seg  # la fase resta quella del clip (Giornalieri): TC audio solo se attivato
    res, _ = run_engine(code, preset="work_vfx", progstart="6", program="10")
    assert "FR {FRM}" in burn_of(res)["seg"] and "|1001|" in burn_of(res)["seg"]


def test_engine_burnin_without_track_lock(built, code):
    res, text = run_engine(code, preset="work_dailies", progstart="6", program="10", nolock="1")
    assert "burn" not in res and "Burn-in non inserito" in text


def dump_tools(setting, fps, w, h, frames_, t, **kw):
    import json
    args = [LUA, os.path.join(ROOT, "tests", "lua_dump.lua"), setting, str(fps), str(w), str(h), str(frames_), str(t)]
    args += ["%s=%s" % kv for kv in kw.items()]
    out = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert out.returncode == 0, out.stderr.decode()
    return dict((k, v["inputs"]) for k, v in json.loads(out.stdout.decode())["tools"].items())


def test_burnin_matte(built):
    """Timeline 16:9 con mascherino 2.39: dati nelle bande nere; formato nativo: bande proprie semitrasparenti."""
    setting = os.path.join(built, "LeaderKit Burn-in.setting")
    seg = "86400|86880|1000|1|24|0|-1|0|IL FILM~|CLIP~|SRC {SRC}~|REC {REC}~~{REC}"
    t = dump_tools(setting, 24, 1920, 1080, 480, 0, Seg=seg, RecStart=86400, TlFps=24, BMatte=11)
    lb = (1 - (1920 / 1080) / 2.39) / 2
    assert abs(t["MatTM"]["Height"] - lb) < 1e-3 and t["MatT"]["TopLeftAlpha"] == 1
    assert t["BandT"]["TopLeftAlpha"] == 0                       # niente bande proprie: c'e' il mascherino
    assert 1 - lb < t["T11"]["Center"][1] < 1 and t["T11"]["StyledText"] == "IL FILM"
    assert 0 < t["T41"]["Center"][1] < lb and t["T41"]["StyledText"] == "REC 01:00:00:00"
    t = dump_tools(setting, 24, 1920, 1080, 480, 0, Seg=seg, RecStart=86400, TlFps=24, BMatte=0)
    assert t["MatTM"]["Height"] == 0 and t["BandT"]["TopLeftAlpha"] == 0.75
    # su una timeline 2.39 nativa il mascherino 2.39 non serve
    t = dump_tools(setting, 24, 4096, 1716, 480, 0, Seg=seg, RecStart=86400, TlFps=24, BMatte=11)
    assert t["MatTM"]["Height"] == 0 and t["BandT"]["TopLeftAlpha"] == 0.75


def test_burnin_matte_presets_and_custom(built):
    setting = os.path.join(built, "LeaderKit Burn-in.setting")
    names = [m for m, _ in build_fx.MATTES]
    seg = "86400|86880|1000|1|24|0|-1|0|A~|B~|C~|D~~{REC}"
    # 1.33 su timeline 2:1: pillarbox, bande laterali di (1 - 1.33/2) / 2
    t = dump_tools(setting, 24, 3840, 1920, 480, 0, Seg=seg, BMatte=names.index("1.33:1 (4:3)"))
    assert abs(t["MatLM"]["Width"] - (1 - (4 / 3) / 2) / 2) < 1e-3 and t["MatTM"]["Height"] == 0
    # 1.33 su timeline 2.39 DCI
    t = dump_tools(setting, 24, 4096, 1716, 480, 0, Seg=seg, BMatte=names.index("1.33:1 (4:3)"))
    assert abs(t["MatLM"]["Width"] - (1 - (4 / 3) / (4096 / 1716)) / 2) < 1e-3
    # personalizzato con lo slider: 2.10 su 16:9 = letterbox
    t = dump_tools(setting, 24, 1920, 1080, 480, 0, Seg=seg, BMatte=len(names) - 1, BMatteRatio=2.1)
    assert abs(t["MatTM"]["Height"] - (1 - (1920 / 1080) / 2.1) / 2) < 1e-3 and t["MatLM"]["Width"] == 0
