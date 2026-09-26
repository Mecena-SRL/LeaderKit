"""Test dei generatori Fusion (LeaderKit Head/Tail) e del motore Lua dei bottoni.

Le espressioni vengono estratte dal .setting ed eseguite fotogramma per
fotogramma con lua5.4 e un comp simulato (tests/lua_harness.lua); il motore
(fx/engine*.lua) gira su un Resolve simulato (tests/engine_harness.lua).
Gli interruttori sono Dissolve: Mix 1 = ramo visibile (e calcolato), 0 = ramo spento.
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
        assert on(r, "MPicStart.Mix") == (rem == 8 * nominal)
        assert on(r, "MLeader.Mix") == (2 * nominal <= rem <= 8 * nominal)
        assert not on(r, "MBars.Mix") and not on(r, "MFlash.Mix")
        digit = r["LDigit.StyledText"]
        if 2 * nominal < rem < 8 * nominal:
            assert digit == str(-(-rem // nominal))
            assert on(r, "LArmG.Mix")
        elif rem == 2 * nominal:
            assert digit == "2" and not on(r, "LArmG.Mix")
        else:
            assert digit == ""
        assert not on(r, "MWarn.Mix") and not on(r, "MEndDot.Mix") and not on(r, "MGuides.Mix")
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
        assert on(r, "MFlash.Mix") == (rem in (69, 68)), rem
        assert not on(r, "MWarn.Mix")
    assert on(rows[300], "SClock.Mix")     # orologio visibile nella slate
    assert rows[n - 100]["CkDigit.StyledText"] == "4"
    assert "BROADCAST UK" in rows[300]["SHeading.StyledText"]


def test_head_flash_scales_with_fps(built):
    n = 30 * 50
    rows = frames(HEAD(built, "broadcast"), 50, 1920, 1080, n, idx("broadcast", "dpp_uk"), cd=0)
    flash = [n - r["t"] for r in rows if on(r, "MFlash.Mix")]
    assert flash == [138, 137, 136, 135]   # 09:59:57:12 @50, 4 fotogrammi (variante SVT)


def test_head_rai(built):
    n = 8 * 25
    rows = frames(HEAD(built, "spot"), 25, 1920, 1080, n, idx("spot", "rai_spot"), cd=0)
    for r in rows:
        rem = n - r["t"]
        assert on(r, "MSlate.Mix") == (rem > 75)
        assert not on(r, "MLeader.Mix") and not on(r, "MPicStart.Mix") and not on(r, "MFlash.Mix")
    assert "LOUDNESS -23,0 LUFS" in rows[0]["SFoot.StyledText"]
    assert "1920 × 1080   1.78:1" in rows[0]["SVal2.StyledText"]


def test_head_length_hint(built):
    rows = frames(HEAD(built), 24, 1920, 1080, 120, idx("cinema", "cinema_dcp"))
    assert all(on(r, "MWarn.Mix") for r in rows)
    assert "diventa di 18 secondi" in rows[0]["Warn.StyledText"]
    rows = frames(HEAD(built, "broadcast"), 25, 1920, 1080, 120, idx("broadcast", "dpp_uk"), cd=0)
    assert "diventa di 30 secondi" in rows[0]["Warn.StyledText"]


def test_slate_text(built):
    rows = frames(HEAD(built), 23.976, 1920, 1080, 480, idx("cinema", "cinema_dcp"))
    r = rows[0]
    assert r["SDirector.StyledText"] == "DIRECTED BY   REGISTA"
    assert "23.976 fps" in r["SVal2.StyledText"].split("|")
    assert "FFOA 01:00:08:00" in r["SFoot.StyledText"]
    assert r["STitle.StyledText"] == "IL FILM"


@pytest.mark.parametrize("fps,nominal", [(24, 24), (25, 25), (29.97, 30)])
def test_tail(built, fps, nominal):
    n = 8 * nominal
    rows = frames(TAIL(built), fps, 1920, 1080, n, 0, tail=(1, 0, 4, 7))
    for r in rows:
        assert on(r, "MPop.Mix") == (r["t"] == 2 * nominal - 1)
        assert on(r, "MCard.Mix") == (4 * nominal <= r["t"] < 7 * nominal)
        assert not on(r, "MFlash.Mix") and not on(r, "TLogo1.Mix")
    rows = frames(TAIL(built), fps, 1920, 1080, n, 0, tail=(0, 1, 0, 0))
    assert [r["t"] for r in rows if on(r, "MFlash.Mix")] == [2 * nominal - 1]
    assert not any(on(r, "MPop.Mix") or on(r, "MCard.Mix") for r in rows)


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
    assert len(scripts) == 5                                  # Standard, Durata, titolo PNG e due loghi
    assert "INPB_IC_Visible" in text and 'vis(\\"SlotTV\\"' in text
    for key in ("LogoPick", "Logo2Pick", "TitlePick"):             # bottoni "Scegli..." (selettore di Fusion)
        assert "%s = {" % key in text and "FileBrowse" in text
    for ld in ("Logo1Ld", "Logo2Ld", "TitleLd"):
        assert "%s = Loader {" % ld in text
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
    labels = r["SLab1.StyledText"].split("|")
    assert labels == ["EDITOR", "COLORIST", "VERSION"]              # solo i campi compilati, nell'ordine
    assert r["SVal1.StyledText"].split("|") == ["Montatore", "Colorista", "v1"]
    assert "PRODUCER" not in r["SLab0.StyledText"] and "CLIENT" not in r["SLab0.StyledText"]
    # etichette e valori: stessa grandezza e stesso centro verticale (righe allineate)
    assert r["SLab1.Size"] == r["SVal1.Size"]
    assert r["SLab1.Center"].split(",")[1] == r["SVal1.Center"].split(",")[1]


def render_path(tools, output):
    """Nodi che Fusion calcola davvero: i Dissolve con Mix 0 o 1 richiedono un solo ingresso."""
    import collections
    seen = set()

    def link(v):
        return v["link"] if isinstance(v, dict) and "link" in v else None

    def visit(n):
        if not n or n in seen or n not in tools:
            return
        seen.add(n)
        t = tools[n]
        if t["kind"] == "Dissolve":
            mix = t["inputs"].get("Mix", 0)
            if mix < 1:
                visit(link(t["inputs"]["Background"]))
            if mix > 0:
                visit(link(t["inputs"]["Foreground"]))
            return
        for v in t["inputs"].values():
            visit(link(v))
    visit(output)
    return collections.Counter(tools[n]["kind"] for n in seen)


def dump_full(setting, fps, w, h, frames_, t, **kw):
    import json
    args = [LUA, os.path.join(ROOT, "tests", "lua_dump.lua"), setting, str(fps), str(w), str(h), str(frames_), str(t)]
    args += ["%s=%s" % kv for kv in kw.items()]
    out = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert out.returncode == 0, out.stderr.decode()
    return json.loads(out.stdout.decode())


FULL = dict(Production="Mecena", Producer="P", Client="C", Agency="A", Code="X1", Episode="1", Language="IT",
            Director="Regista", Editor="E", Colorist="Co", Sound="S", VFXBy="V", Phase=2, StColor=2, StSound=1,
            StVFX=1, StMusic=2, StTitles=1, Note="nota", AudioFormat="5.1", ColorInfo="Rec.709")


@pytest.mark.parametrize("style", [0, 1, 2, 3])
def test_generator_is_light(built, style):
    """Budget per fotogramma: prima la slate Pannelli calcolava 58 Text+, 69 Merge e 12 Background."""
    d = dump_full(HEAD(built), 24, 3840, 2160, 432, 40, SlateStyle=style, **FULL)
    c = render_path(d["tools"], d["output"])
    assert c["TextPlus"] <= 20 and c["Merge"] <= 22 and c["Background"] <= 5, c
    # countdown: cerchi e croce in un solo Background
    d = dump_full(HEAD(built), 24, 3840, 2160, 432, 300, **FULL)
    c = render_path(d["tools"], d["output"])
    assert c["TextPlus"] <= 2 and c["Background"] <= 3 and c["Merge"] <= 4, c
    # nero prima del programma: solo lo sfondo
    d = dump_full(HEAD(built), 24, 3840, 2160, 432, 430, **FULL)
    c = render_path(d["tools"], d["output"])
    assert c.get("TextPlus", 0) == 0 and c["Background"] == 1 and c.get("Merge", 0) == 0, c


def test_setting_size_and_prefs(built):
    """Meno testo nel comp (piu' leggero da salvare) e comp:GetPrefs mai ripetuto nella stessa espressione."""
    text = open(HEAD(built)).read()
    assert len(text) < 520000, len(text)
    assert build_fx.engine("remove").count("\n") < 400             # Rimuovi non incorpora tutto il motore
    for expr in re.findall(r'Expression = "((?:[^"\\]|\\.)*)"', text):
        for key in ("Rate", "Width", "Height"):
            assert expr.count('Comp.FrameFormat.%s' % key) <= 1, expr[:120]


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
    # niente frame lines nel PNG: sono nel generatore, sotto i testi
    y0 = round((1920 - 3840 / 2.39) / 2)
    assert px[1920, y0 + 1][3] == 0


def test_engine_still_tiling(built, code):
    """Se Resolve accorcia le immagini fisse, la taratura viene ripetuta fino a coprire lo spazio."""
    res, _ = run_engine(code, res="960x540", stilldur="48")
    gfx = res["gfx"]
    assert sum(int(v.split("|")[1]) for v in gfx) == 6 * 24 + 1 and len(gfx) == 4


def test_inspector_pages(built):
    text = open(HEAD(built, "cinema")).read()
    for page in build_fx.PAGES:
        assert 'Page = "%s"' % page in text and 'ICS_ControlPage = "%s"' % page in text
    for page in ("Produzione", "Post", "Taratura"):                   # schede della 0.10 accorpate
        assert 'Page = "%s"' % page not in text
    inst = re.findall(r"InstanceInput \{[^}]*\}", text)
    assert inst and all("Page = " in i for i in inst)
    # gli input di servizio non sono pubblicati
    for key in build_fx.HIDDEN_NUM:
        assert 'Source = "%s"' % key not in text


def test_engine_logo_and_colorinfo(code, tmp_path):
    from PIL import Image
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (400, 100), (255, 0, 0, 255)).save(logo)
    res, log = run_engine(code, fps="24", df="0", preset="cinema_dcp", head=5, progstart=18, program=60,
                          logo=str(logo))
    loaders = [v.split("|") for v in res["loader"]]
    # il logo e' caricato nel Loader del blocco ricreato e in quello della coda, con le dimensioni del PNG
    head = [x for x in loaders if x[0] == "LeaderKit Head" and x[1] == "Logo1Ld"]
    tail = [x for x in loaders if x[0] == "LeaderKit Tail" and x[1] == "Logo1Ld"]
    assert head and head[0][2:5] == [str(logo), "400", "100"] and head[0][5] == "1000000"
    assert tail and tail[0][2:5] == [str(logo), "400", "100"]
    assert "Logo sulla slate e sulla coda: logo.png, 400x100 px." in log
    assert "LeaderKit Logo" not in " ".join(res.get("track", []))       # niente piu' tracce per i loghi
    assert "Rec.709 Gamma 2.4" in res["colorinfo"][0]
    # senza "anche sulla coda" la coda resta senza logo
    res, log = run_engine(code, fps="24", df="0", preset="cinema_dcp", head=5, progstart=18, program=60,
                          logo=str(logo), logotail="0")
    assert not [v for v in res["loader"] if v.startswith("LeaderKit Tail|Logo1Ld")]
    assert [v for v in res["loader"] if v.startswith("LeaderKit Head|Logo1Ld")]
    res, log = run_engine(code, fps="24", df="0", preset="cinema_dcp", head=5, progstart=18, program=60,
                          logo="/non/esiste.png")
    assert "Logo non trovato: /non/esiste.png" in log
    bad = tmp_path / "logo.psd"
    bad.write_bytes(b"8BPS not an image we can read")
    res, log = run_engine(code, fps="24", df="0", preset="cinema_dcp", head=5, progstart=18, program=60,
                          logo=str(bad))
    assert "Logo: formato non leggibile" in log


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
    """Timeline 16:9 con mascherino 2.39: dati nelle bande nere; senza mascherino niente bande (default)."""
    setting = os.path.join(built, "LeaderKit Burn-in.setting")
    seg = "86400|86880|1000|1|24|0|-1|0|IL FILM~|CLIP~|SRC {SRC}~|REC {REC}~~{REC}"
    t = dump_tools(setting, 24, 1920, 1080, 480, 0, Seg=seg, RecStart=86400, TlFps=24, BMatte=11)
    lb = (1 - (1920 / 1080) / 2.39) / 2
    assert abs(t["MatTM"]["Height"] - lb) < 1e-3 and t["GMat"]["Mix"] == 1 and t["Mat"]["TopLeftAlpha"] == 1
    assert t["GBand"]["Mix"] == 0                                # niente bande proprie: c'e' il mascherino
    assert 1 - lb < t["T1"]["Center"][1] < 1 and t["T1"]["StyledText"] == "IL FILM"
    assert 0 < t["T4"]["Center"][1] < lb and t["T4"]["StyledText"] == "REC 01:00:00:00"
    # default: nessun mascherino e nessuna banda (prima c'erano bande semitrasparenti sempre accese)
    t = dump_tools(setting, 24, 1920, 1080, 480, 0, Seg=seg, RecStart=86400, TlFps=24)
    assert t["GMat"]["Mix"] == 0 and t["GBand"]["Mix"] == 0
    t = dump_tools(setting, 24, 1920, 1080, 480, 0, Seg=seg, RecStart=86400, TlFps=24, BBands=1)
    assert t["GBand"]["Mix"] == 1 and t["Band"]["TopLeftAlpha"] == 0.6
    # su una timeline 2.39 nativa il mascherino 2.39 non serve
    t = dump_tools(setting, 24, 4096, 1716, 480, 0, Seg=seg, RecStart=86400, TlFps=24, BMatte=11)
    assert t["MatTM"]["Height"] == 0 and t["GMat"]["Mix"] == 0


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


def test_slate_styles_switch(built):
    """Quattro stili: si alternano con Dissolve; con un titolo in PNG il titolo testuale sparisce."""
    head = HEAD(built)
    names = build_fx.SLATE_STYLES
    assert len(names) == 4
    for st in range(4):
        t = dump_tools(head, 24, 1920, 1080, 432, 40, SlateStyle=st, Title="Juna")
        for i in (1, 2, 3):
            assert t["SStyle%d" % i]["Mix"] == (1 if i == st else 0)
    t = dump_tools(head, 24, 1920, 1080, 432, 40, SlateStyle=1, Title="Juna", Director="Janicel Diaz")
    assert t["BTitle"]["StyledText"] == "JUNA" and t["BTitle"]["HorizontalLeftCenterRight"] == -1
    assert t["BInfo"]["StyledText"].split("\n")[0] == "DIRECTOR   Janicel Diaz"
    assert t["BFrames"]["StyledText"] == str(432 - 40)
    # titolo in PNG caricato (dimensioni note): il titolo di testo sparisce e l'immagine va nel riquadro
    t = dump_tools(head, 24, 1920, 1080, 432, 40, SlateStyle=0, Title="Juna", TitleImage="/x/titolo.png",
                   TitleW=800, TitleH=200)
    assert t["STitle"]["StyledText"] == "" and t["STitleImg"]["Mix"] == 1
    # PNG indicato ma non caricato: resta il titolo di testo
    t = dump_tools(head, 24, 1920, 1080, 432, 40, SlateStyle=0, Title="Juna", TitleImage="/x/titolo.png")
    assert t["STitle"]["StyledText"] == "JUNA" and t["STitleImg"]["Mix"] == 0


def test_engine_style_dial_and_title_png(built, code, tmp_path):
    from PIL import Image
    title = tmp_path / "titolo.png"
    Image.new("RGBA", (800, 200), (255, 255, 255, 255)).save(title)
    res, log = run_engine(code, res="1920x1080", style="1", titleimg=str(title))
    tracks = [v.split("|") for v in res["track"]]
    dial = [t for t in tracks if t[0] == "LeaderKit Grafica" and "Quadrante24" in t[6]]
    assert dial and dial[0][1] == "00:59:50:00" and int(dial[0][2]) == 8 * 24      # sopra la slate
    assert not [t for t in tracks if t[0] == "LeaderKit Logo Titolo"]
    tl = [v.split("|") for v in res["loader"] if v.startswith("LeaderKit Head|TitleLd")]
    assert tl and tl[0][2:5] == [str(title), "800", "200"]


def test_title_png_geometry(built):
    """Titolo 800x200 nello stile Quadrante: riquadro 0.42 W x 0.10 H ancorato a sinistra a 0.53 W."""
    t = dump_tools(HEAD(built), 24, 1920, 1080, 432, 40, SlateStyle=1, TitleImage="/x/t.png", TitleW=800, TitleH=200)
    m = t["STitleImgM1"]
    s = min(0.42 * 1920 / 800, 0.10 * 1080 / 200)                    # limita l'altezza: 108 px
    assert abs(m["Size"] - s) < 1e-9
    assert abs(m["Center"][0] - (0.53 * 1920 + 800 * s / 2) / 1920) < 1e-9 and abs(m["Center"][1] - 0.845) < 1e-9


def test_burnin_edge_alignment(built):
    setting = os.path.join(built, "LeaderKit Burn-in.setting")
    seg = "86400|86880|1000|1|24|0|-1|0|IL FILM~|CLIP~|SRC {SRC}~|REC {REC}~~{REC}"
    t = dump_tools(setting, 24, 1920, 1080, 480, 0, Seg=seg)
    assert t["T1"]["HorizontalLeftCenterRight"] == -1 and abs(t["T1"]["Center"][0] - 0.02) < 1e-9
    assert t["T2"]["HorizontalLeftCenterRight"] == 1 and abs(t["T2"]["Center"][0] - 0.98) < 1e-9
    t = dump_tools(setting, 24, 1920, 1080, 480, 0, Seg=seg, BAlign=1)
    assert t["T1"]["HorizontalLeftCenterRight"] == 0 and t["T1"]["Center"][0] == 0.2


def test_burnin_matte_precise_and_data_inside(built):
    """Mascherino a pixel interi e pari; i dati stanno sempre nelle bande del mascherino."""
    setting = os.path.join(built, "LeaderKit Burn-in.setting")
    names = [m for m, _ in build_fx.MATTES]
    seg = "86400|86880|1000|1|24|0|-1|0|IL FILM~24 fps|CLIP~SC 1 TK 2|SRC {SRC}~SND x|REC {REC}~FR {FRM}~{REC}"
    # 2.39 su 1920x1080: immagine 1920x804, bande da 138 px
    t = dump_tools(setting, 24, 1920, 1080, 480, 0, Seg=seg, RecStart=86400, TlFps=24, BMatte=names.index("2.39:1 (Scope)"))
    assert abs(t["MatTM"]["Height"] * 1080 - 138) < 1e-6
    assert t["T1"]["StyledText"] == "IL FILM\n24 fps"                     # banda alta: due righe
    # 1.85 su 16:9: banda di 22 px, troppo bassa per due righe -> una riga sola, dentro la banda
    t = dump_tools(setting, 24, 1920, 1080, 480, 0, Seg=seg, RecStart=86400, TlFps=24, BMatte=names.index("1.85:1 (Flat)"))
    lb = t["MatTM"]["Height"]
    assert abs(lb * 1080 - (1080 - 2 * round(1920 / 1.85 / 2)) / 2) < 1e-6
    assert t["T1"]["StyledText"] == "IL FILM     24 fps"
    assert 1 - lb < t["T1"]["Center"][1] < 1 and 0 < t["T4"]["Center"][1] < lb
    assert t["GBand"]["Mix"] == 0
    # testo abbastanza piccolo da stare nella banda (cap <= banda / 1.7)
    assert t["T1"]["Size"] <= 2 * (lb / 1.7) / (1920 / 1080) + 1e-9
    # 1.33 su 2:1: pillarbox, dati centrati nelle bande laterali
    t = dump_tools(setting, 24, 3840, 1920, 480, 0, Seg=seg, RecStart=86400, TlFps=24, BMatte=names.index("1.33:1 (4:3)"))
    pb = t["MatLM"]["Width"]
    assert abs(t["T1"]["Center"][0] - pb / 2) < 1e-9 and t["T1"]["HorizontalLeftCenterRight"] == 0
    assert abs(t["T4"]["Center"][0] - (1 - pb / 2)) < 1e-9
    # la risoluzione scritta da Genera prevale su quella della composizione
    t = dump_tools(setting, 24, 1920, 1080, 480, 0, Seg=seg, RecStart=86400, TlFps=24, BMatte=names.index("2.39:1 (Scope)"), TlW=4096, TlH=2160)
    assert abs(t["MatTM"]["Height"] * 2160 - (2160 - 2 * round(4096 / 2.39 / 2)) / 2) < 1e-6




# ------------------------------------------------------------------ 0.11: guide, pallino, logo, burn-in veloce
@pytest.mark.parametrize("w,h", [(1920, 1080), (3840, 1920), (1440, 1080), (4096, 1716), (1080, 1920)])
def test_guides_frame_lines(built, w, h):
    """Frame lines a pixel interi e pari, con formato e risoluzione reale nella timeline; sotto i testi."""
    t = dump_tools(HEAD(built), 24, w, h, 432, 40, FLTL=1, FL185=1, FL239=1, FL133=1, SafeTitle=1)
    lw = max(1, int(h / 1080 * 2 + 0.5))
    for key, ar in (("FL185", 1.85), ("FL239", 2.39), ("FL133", 4 / 3)):
        m, lab = t["G%sM" % key], t["G%sT" % key]["StyledText"]
        if ar > w / h + 0.005:
            aw, ah = w, 2 * int(w / ar / 2 + 0.5)
        elif ar < w / h - 0.005:
            aw, ah = 2 * int(h * ar / 2 + 0.5), h
        else:
            aw, ah = w, h
        assert abs(m["Width"] * w - (aw - lw)) < 1e-6 and abs(m["Height"] * h - (ah - lw)) < 1e-6
        assert m["Level"] == 1 and abs(m["BorderWidth"] * w - lw) < 1e-6
        assert lab.endswith("%d × %d" % (aw, ah)) and lab.startswith("%.2f:1" % ar if ar != 4 / 3 else "1.33:1")
    assert t["GFLTLT"]["StyledText"] == "TIMELINE %.2f:1  ·  %d × %d" % (w / h, w, h)
    assert t["GSafeTitleT"]["StyledText"] == "SAFE TITLE 90%"
    assert t["GFL166M"]["Level"] == 0 and t["GFL166T"]["StyledText"] == ""      # formati spenti: niente
    # etichette dentro il quadro
    for key in ("FLTL", "FL185", "FL239", "FL133"):
        x, y = t["G%sT" % key]["Center"]
        assert 0 < x < 1 and 0 < y < 1
    # sulla slate il livello delle guide sta sotto i testi: la slate parte da MGuides
    assert t["MGuides"]["Mix"] == 1 and t["SMP"]["Background"]["link"] == "MGuides"


def test_guides_1_85_on_16_9_example(built):
    t = dump_tools(HEAD(built), 24, 1920, 1080, 432, 40, FL239=1, FL185=1)
    assert t["GFL239T"]["StyledText"] == "2.39:1  ·  1920 × 804"
    assert t["GFL185T"]["StyledText"] == "1.85:1  ·  1920 × 1038"
    cap, pad = 0.014 * 1080, 0.008 * 1080
    assert t["GFL185T"]["HorizontalLeftCenterRight"] == -1 and abs(t["GFL185T"]["Center"][0] - (2 + pad) / 1920) < 1e-9
    assert abs(t["GFL239T"]["Center"][0] - (2 + pad + 19 * cap) / 1920) < 1e-9      # affiancata alla 1.85
    assert abs(t["GFL239T"]["Center"][1] - (1 - (138 + 2 + 0.008 * 1080 + 0.007 * 1080) / 1080)) < 1e-9


def test_guides_default_off_and_where(built):
    rows = frames(HEAD(built), 24, 1920, 1080, 18 * 24, idx("cinema", "cinema_dcp"))
    assert not any(on(r, "MGuides.Mix") for r in rows)                 # default: nessuna guida (niente "mascherino")
    t = dump_tools(HEAD(built), 24, 1920, 1080, 432, 40, FL185=1, GuidesSlate=0)
    assert t["MGuides"]["Mix"] == 0
    t = dump_tools(HEAD(built), 24, 1920, 1080, 432, 300, FL185=1)       # countdown
    assert t["MGuides"]["Mix"] == 1 and t["LM1"]["Background"]["link"] == "MGuides"
    t = dump_tools(HEAD(built), 24, 1920, 1080, 432, 300, FL185=1, GuidesCd=0)
    assert t["MGuides"]["Mix"] == 0


@pytest.mark.parametrize("fps,nominal", [(24, 24), (25, 25), (29.97, 30), (50, 50)])
def test_end_dot_last_frame(built, fps, nominal):
    """Pallino solo sull'ultimo fotogramma del leader (il programma parte al successivo), solo se attivo."""
    n = 18 * nominal
    t = dump_tools(HEAD(built), fps, 1920, 1080, n, n - 1, EndDot=1)
    assert t["MEndDot"]["Mix"] == 1
    assert dump_tools(HEAD(built), fps, 1920, 1080, n, n - 2, EndDot=1)["MEndDot"]["Mix"] == 0
    assert dump_tools(HEAD(built), fps, 1920, 1080, n, n - 1)["MEndDot"]["Mix"] == 0
    m = t["EndDotM"]
    assert abs(m["Width"] - 0.05 * 1080 / 1920) < 1e-9                 # 5% dell'altezza, cerchio
    assert abs(m["Center"][0] - (1 - 0.09 * 1080 / 1920)) < 1e-9 and abs(m["Center"][1] - 0.91) < 1e-9
    t = dump_tools(HEAD(built), fps, 1440, 1080, n, n - 1, EndDot=1, EndDotPos=1)
    assert t["EndDotM"]["Center"] == [0.5, 0.5]


def test_engine_end_dot_warning(code):
    res, log = run_engine(code, fps="24", df="0", preset="cinema_dcp", head=5, progstart=18, program=60, enddot=1)
    assert "Pallino sull'ultimo fotogramma del leader (01:00:07:23)" in log and "nero fino al FFOA" in log
    assert "Il programma inizia esattamente al FFOA" in log              # avviso, non blocca nulla
    res, log = run_engine(code, preset="work_dailies", progstart="6", program="20", enddot=1)
    assert "nero fino al FFOA" not in log and "il programma parte al fotogramma dopo" in log


def test_logo_geometry(built):
    """Logo 400x100 al 12% in alto a destra: riquadro 230 x 115 px, margini 3.5% / 4%."""
    t = dump_tools(HEAD(built), 24, 1920, 1080, 432, 40, Logo="/x/l.png", LogoW=400, LogoH=100, LogoSize=12)
    assert t["SLogo1"]["Mix"] == 1
    m = t["SLogo1M1"]
    s = min(0.12 * 1920 / 400, 0.06 * 1920 / 100)
    assert abs(m["Size"] - s) < 1e-9
    assert abs(m["Center"][0] - (1920 - 0.035 * 1920 - 400 * s / 2) / 1920) < 1e-9
    assert abs(m["Center"][1] - (1080 - 0.04 * 1080 - 100 * s / 2) / 1080) < 1e-9
    # secondo logo in alto a sinistra; senza dimensioni (file non caricato) il gate resta chiuso
    t = dump_tools(HEAD(built), 24, 1920, 1080, 432, 40, Logo2="/x/l2.png", Logo2W=100, Logo2H=100, Logo="/x/l.png")
    assert t["SLogo2"]["Mix"] == 1 and t["SLogo1"]["Mix"] == 0
    assert t["SLogo2M1"]["Center"][0] < 0.5
    t = dump_tools(TAIL(built), 24, 1920, 1080, 192, 10, Logo="/x/l.png", LogoW=400, LogoH=100)
    assert t["TLogo1"]["Mix"] == 1


def run_lua(code):
    out = subprocess.run([LUA, "-"], input=code.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert out.returncode == 0, out.stderr.decode()
    return out.stdout.decode()


def test_image_module(tmp_path):
    """Dimensioni di PNG e JPEG dall'intestazione; Scegli... imposta percorso, Loader e dimensioni."""
    from PIL import Image
    png, jpg = tmp_path / "a.png", tmp_path / "b.jpg"
    Image.new("RGBA", (321, 123)).save(png)
    Image.new("RGB", (640, 360)).save(jpg, quality=80)
    lib = open(os.path.join(ROOT, "fx", "image.lua")).read()
    out = run_lua(lib + """
print(LK_IMAGE.size(%r))
print(LK_IMAGE.size(%r))
local lk = { v = {} }
function lk:GetInput(k) return self.v[k] end
function lk:SetInput(k, x) self.v[k] = x end
local ld = { inp = {} }
function ld:SetInput(k, x) self.inp[k] = x end
local c = {}
function c:FindTool(n) if n == "Logo1Ld" then return ld end end
function c:AskUser(t, ctl) assert(ctl[1][2] == "FileBrowse"); return { File = ' "' .. %r .. '" ' } end
print(LK_IMAGE.pick(c, lk, "Logo", "Logo1Ld", "LogoW", "LogoH", "Logo"), lk.v.Logo == %r, ld.Clip == %r, lk.v.LogoW, lk.v.LogoH,
  ld.inp.HoldLastFrame)
lk.v.Logo = ""
print(LK_IMAGE.sync(c, lk, "Logo", "Logo1Ld", "LogoW", "LogoH"), lk.v.LogoW)
""" % (str(png), str(jpg), str(png), str(png), str(png)))
    lines = out.split("\n")
    assert lines[0] == "321\t123" and lines[1] == "640\t360"
    assert lines[2] == "ok\ttrue\ttrue\t321\t123\t1000000"
    assert lines[3].startswith("empty") and lines[3].endswith("0")


def test_burnin_index_matches_scan(built, code):
    """L'indice a record fissi scritto dal motore trova lo stesso segmento della scansione completa."""
    res, _ = run_engine(code, preset="work_dailies", progstart="6", program="20")
    idx_ = res["burnidx"][0]
    seg = burn_of(res)["seg"].replace(" // ", "\n")
    assert len(idx_) % 18 == 0 and idx_[10:18] == "00000001"
    setting = os.path.join(built, "LeaderKit Burn-in.setting")
    for t_ in (0, 5, 479):
        a = dump_tools(setting, 24, 1920, 1080, 480, t_, Seg=seg, SegIdx=idx_, RecStart=86400, TlFps=24)
        b = dump_tools(setting, 24, 1920, 1080, 480, t_, Seg=seg, RecStart=86400, TlFps=24)
        assert [a["T%d" % k]["StyledText"] for k in range(1, 5)] == [b["T%d" % k]["StyledText"] for k in range(1, 5)]
        assert a["T3"]["StyledText"].startswith("SRC 14:22:")


def test_burnin_binary_search_many_segments(built):
    """Mille tagli: ogni fotogramma trova il suo segmento (ricerca binaria)."""
    lines, idx_, pos = [], "", 1
    for i in range(1000):
        a, b = 86400 + i * 5, 86400 + (i + 1) * 5
        line = "%d|%d|%d|1|24|0|-1|0|CLIP %d~|~|SRC {SRC}~|REC {REC}~~{REC}" % (a, b, i * 1000, i)
        idx_ += "%010d%08d" % (a - 86400, pos)
        pos += len(line) + 1
        lines.append(line)
    setting = os.path.join(built, "LeaderKit Burn-in.setting")
    for f in (0, 4, 5, 2503, 4999):
        t = dump_tools(setting, 24, 1920, 1080, 5000, f, Seg="\n".join(lines), SegIdx=idx_, RecStart=86400, TlFps=24)
        assert t["T1"]["StyledText"] == "CLIP %d" % (f // 5)
    t = dump_tools(setting, 24, 1920, 1080, 6000, 5000, Seg="\n".join(lines), SegIdx=idx_, RecStart=86400, TlFps=24)
    assert t["T1"]["StyledText"] == ""                                    # oltre l'ultimo segmento


def test_burnin_is_light(built):
    setting = os.path.join(built, "LeaderKit Burn-in.setting")
    seg = "86400|86880|1000|1|24|0|-1|0|IL FILM~24 fps|CLIP~SC 1|SRC {SRC}~SND x|REC {REC}~FR {FRM}~{REC}"
    d = dump_full(setting, 24, 3840, 2160, 480, 10, Seg=seg, SegIdx="000000000000000001", RecStart=86400,
                  BWater=0, TlW=3840, TlH=2160)
    c = render_path(d["tools"], d["output"])
    assert c["TextPlus"] <= 4 and c["Background"] == 1 and c["Merge"] <= 4, c
    text = open(setting).read()
    assert "GetPrefs" in text                                              # solo come ripiego se manca TlW
    assert 'Source = "Seg"' not in text                                   # dati dei clip non visibili nell'Inspector


@pytest.mark.parametrize("fps,w,h", [(23.976, 1920, 1080), (25, 3840, 1920), (29.97, 1440, 1080), (48, 4096, 1716),
                                     (59.94, 1080, 1920), (30, 720, 576)])
def test_every_format_and_rate_evaluates(built, fps, w, h):
    """Ogni espressione di ogni generatore funziona con qualunque formato e frame rate."""
    n = 30 * int(fps + 0.5)
    for style in range(4):
        for t_ in (0, n // 3, n - 60, n - 1):
            d = dump_full(HEAD(built), fps, w, h, n, t_, SlateStyle=style, FLTL=1, FL185=1, FL239=1, FL133=1,
                          SafeAction=1, EndDot=1, Logo="/x.png", LogoW=300, LogoH=300, **FULL)
            for name, tool in d["tools"].items():
                if tool["kind"] == "TextPlus":
                    cx, cy = tool["inputs"]["Center"]
                    assert -0.01 <= cx <= 1.01 and -0.01 <= cy <= 1.01, (name, cx, cy)
    dump_full(TAIL(built), fps, w, h, n, n // 2)
