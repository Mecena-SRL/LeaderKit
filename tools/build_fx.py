#!/usr/bin/env python3
"""Build di LeaderKit come generatori Fusion (Edit > Generators > LeaderKit).

    python3 tools/build_fx.py   ->  dist/LeaderKit.drfx

* LeaderKit Head: slate + countdown + 2-pop in un solo clip. La fine del clip
  e' il FFOA; tutto e' calcolato a ogni fotogramma dal frame rate e dalla
  risoluzione della timeline. Parametri e bottoni nell'Inspector.
* LeaderKit Tail: tail pop + END OF PROGRAM; inserita dal bottone "Genera".

Convenzioni verificate in Resolve 21 (probe): GroupOperator, nodo Custom
"LK" come pannello di controllo, testi letti con .Value, espressioni con
comp:GetPrefs / comp.RenderStart / comp.RenderEnd / time.
"""

import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from leaderkit import __version__  # noqa: E402
from leaderkit.fusion import lua_string  # noqa: E402

FPS = 'math.floor(comp:GetPrefs("Comp.FrameFormat.Rate") + 0.5)'
REM = '(comp.RenderEnd - time + 1)'                  # fotogrammi al FFOA (1 = ultimo)
ELAPSED = '(time - comp.RenderStart)'                # fotogrammi dall'inizio clip
ASPECT = '(comp:GetPrefs("Comp.FrameFormat.Width") / comp:GetPrefs("Comp.FrameFormat.Height"))'
CD = 'LK.CountFrom'

RING_D = 0.36
LINE_W = 0.0025


def e(expr):
    """Sostituisce i segnaposto nelle espressioni."""
    return (expr.replace("FPS", FPS).replace("REM", REM).replace("ELAPSED", ELAPSED)
            .replace("ASPECT", ASPECT).replace("CD", CD))


class G(object):
    """Grafo di un generatore: nodi come testo Lua."""

    def __init__(self):
        self.tools = []
        self.x = 0

    def _add(self, name, reg, inputs, extra=""):
        body = []
        for key, val in inputs:
            k = key if key.isidentifier() else "[%s]" % lua_string(key)
            if isinstance(val, tuple) and val[0] == "expr":
                v = "Expression = %s, " % lua_string(val[1])
            elif isinstance(val, tuple) and val[0] == "link":
                v = "SourceOp = %s, Source = %s, " % (lua_string(val[1]), lua_string(val[2]))
            else:
                v = "Value = %s, " % val
            body.append("\t\t\t\t\t\t%s = Input { %s}," % (k, v))
        self.x += 110
        self.tools.append("\t\t\t\t%s = %s {\n\t\t\t\t\tCtrlWShown = false,\n\t\t\t\t\tNameSet = true,\n"
                          "\t\t\t\t\tInputs = {\n%s\n\t\t\t\t\t},\n"
                          "\t\t\t\t\tViewInfo = OperatorInfo { Pos = { %d, %d } },\n%s\t\t\t\t},\n"
                          % (name, reg, "\n".join(body), self.x, 0, extra))
        return name

    CREATOR = [("GlobalOut", "100000"), ("Width", "1920"), ("Height", "1080"),
               ("UseFrameFormatSettings", "1")]

    def background(self, name, grey=0.0, mask=None, alpha=1.0, color=None, scale=1.0):
        if color:
            rgb = [("expr", "LK.%s%s * %s" % (color, ch, scale)) for ch in ("Red", "Green", "Blue")]
        else:
            rgb = [repr(grey)] * 3
        ins = self.CREATOR + [("TopLeftRed", rgb[0]), ("TopLeftGreen", rgb[1]),
                              ("TopLeftBlue", rgb[2]), ("TopLeftAlpha", repr(alpha))]
        if mask:
            ins.append(("EffectMask", ("link", mask, "Mask")))
        return self._add(name, "Background", ins)

    def mask(self, name, kind, width, height, center=None, border=None):
        ins = [("Filter", 'FuID { "Fast Gaussian" }'), ("SoftEdge", "0"),
               ("MaskWidth", "1920"), ("MaskHeight", "1080"), ("PixelAspect", "{ 1, 1 }"),
               ("UseFrameFormatSettings", "1"), ("ClippingMode", 'FuID { "None" }'),
               ("Width", width), ("Height", height)]
        if center:
            ins.append(("Center", center))
        if border:
            ins += [("Solid", "0"), ("BorderWidth", border)]
        return self._add(name, kind, ins)

    def text(self, name, styled, size, y=0.5, grey=1.0, style="Bold", spacing=None):
        rgb = [("expr", "LK.Text%s * %s" % (ch, grey)) for ch in ("Red", "Green", "Blue")]
        ins = self.CREATOR + [
            ("Center", "{ 0.5, %s }" % y), ("Font", '"Open Sans"'), ("Style", lua_string(style)),
            ("Size", repr(size)), ("StyledText", styled),
            ("Red1", rgb[0]), ("Green1", rgb[1]), ("Blue1", rgb[2]),
            ("VerticalJustificationNew", "3"), ("HorizontalJustificationNew", "3")]
        if spacing:
            ins.append(("LineSpacing", repr(spacing)))
        return self._add(name, "TextPlus", ins)

    def merge(self, name, bg, fg, blend=None):
        ins = [("Background", ("link", bg, "Output")), ("Foreground", ("link", fg, "Output")),
               ("PerformDepthMerge", "0")]
        if blend:
            ins.append(("Blend", ("expr", blend)))
        return self._add(name, "Merge", ins)

    def transform(self, name, src, angle):
        return self._add(name, "Transform", [("Input", ("link", src, "Output")),
                                             ("Angle", ("expr", angle))])

    def controls(self, values, user_controls):
        ins = [(k, v) for k, v in values]
        return self._add("LK", "Custom", ins,
                         "\t\t\t\t\tUserControls = ordered() {\n%s\t\t\t\t\t},\n" % user_controls)


def uc_text(name, label, lines=1, read_only=False):
    return ("\t\t\t\t\t\t%s = { LINKID_DataType = \"Text\", INPID_InputControl = \"TextEditControl\", "
            "TEC_Lines = %d, TEC_Wrap = true, TEC_ReadOnly = %s, LINKS_Name = %s, },\n"
            % (name, lines, "true" if read_only else "false", lua_string(label)))


def uc_combo(name, label, items):
    opts = " ".join("{ CCS_AddString = %s }," % lua_string(i) for i in items)
    return ("\t\t\t\t\t\t%s = { %s LINKID_DataType = \"Number\", INPID_InputControl = \"ComboControl\", "
            "CC_LabelPosition = \"Horizontal\", INP_Integer = true, LINKS_Name = %s, },\n"
            % (name, opts, lua_string(label)))


def uc_slider(name, label, lo, hi, default, integer=True):
    return ("\t\t\t\t\t\t%s = { LINKID_DataType = \"Number\", INPID_InputControl = \"SliderControl\", "
            "INP_Integer = %s, INP_MinScale = %s, INP_MaxScale = %s, INP_MinAllowed = %s, "
            "INP_MaxAllowed = %s, INP_Default = %s, LINKS_Name = %s, },\n"
            % (name, "true" if integer else "false", lo, hi, lo, hi * 10, default, lua_string(label)))


def uc_check(name, label, default):
    return ("\t\t\t\t\t\t%s = { LINKID_DataType = \"Number\", INPID_InputControl = \"CheckboxControl\", "
            "INP_Integer = true, INP_Default = %d, CBC_TriState = false, LINKS_Name = %s, },\n"
            % (name, default, lua_string(label)))


def uc_color(prefix, label, group, default):
    out = ""
    for i, ch in enumerate(("Red", "Green", "Blue")):
        name = ("ICS_Name = %s, " % lua_string(label)) if i == 0 else ""
        out += ("\t\t\t\t\t\t%s%s = { LINKID_DataType = \"Number\", INPID_InputControl = \"ColorControl\", "
                "%sLINKS_Name = %s, IC_ControlGroup = %d, IC_ControlID = %d, INP_Default = %s, "
                "INP_MinScale = 0, INP_MaxScale = 1, CLRC_ShowWheel = false, },\n"
                % (prefix, ch, name, lua_string(label), group, i, repr(default[i])))
    return out


COLOR_DEFAULTS = [("Text", "Colore testo", (1.0, 1.0, 1.0)), ("Bg", "Colore sfondo", (0.0, 0.0, 0.0)),
                  ("Accent", "Colore grafica leader", (0.85, 0.85, 0.85))]


COLOR_GROUP_BASE = 11


def color_controls():
    return "".join(uc_color(p, label, COLOR_GROUP_BASE + i, d) for i, (p, label, d) in enumerate(COLOR_DEFAULTS))


def control_group(src):
    for i, (p, _, _) in enumerate(COLOR_DEFAULTS):
        if src.startswith(p) and src[len(p):] in ("Red", "Green", "Blue"):
            return COLOR_GROUP_BASE + i
    return None


def color_values():
    vals = []
    for p, _, d in COLOR_DEFAULTS:
        for ch, v in zip(("Red", "Green", "Blue"), d):
            vals.append((p + ch, repr(v)))
    return vals


def color_inputs():
    return [p + ch for p, _, _ in COLOR_DEFAULTS for ch in ("Red", "Green", "Blue")]


def uc_label(name, label):
    return ("\t\t\t\t\t\t%s = { LINKID_DataType = \"Number\", INPID_InputControl = \"LabelControl\", "
            "LBLC_DropDownButton = false, INP_External = false, INP_Passive = true, LINKS_Name = %s, },\n"
            % (name, lua_string(label)))


def uc_button(name, label, code):
    return ("\t\t\t\t\t\t%s = { LINKID_DataType = \"Number\", INPID_InputControl = \"ButtonControl\", "
            "INP_Integer = false, INP_External = false, LINKS_Name = %s, BTNCS_Execute = %s, },\n"
            % (name, lua_string(label), lua_string(code)))


def leader_stack(g, prefix, digit_expr, sweep_vis=None, cd=CD):
    """Cerchi, croce, braccio rotante e cifra centrale. Ritorna il nodo in cima."""
    r = RING_D / 2.0
    g.mask(prefix + "RingO", "EllipseMask", repr(RING_D), repr(RING_D), border=repr(LINE_W * 1.6))
    g.mask(prefix + "RingI", "EllipseMask", repr(RING_D * 0.86), repr(RING_D * 0.86), border=repr(LINE_W))
    g.mask(prefix + "LineH", "RectangleMask", "1", repr(LINE_W))
    g.mask(prefix + "LineV", "RectangleMask", repr(LINE_W), ("expr", e("1 / ASPECT")))
    g.background(prefix + "RingOBg", mask=prefix + "RingO", color="Accent")
    g.background(prefix + "RingIBg", mask=prefix + "RingI", color="Accent")
    g.background(prefix + "LineHBg", mask=prefix + "LineH", color="Accent", scale=0.7)
    g.background(prefix + "LineVBg", mask=prefix + "LineV", color="Accent", scale=0.7)
    top = g.merge(prefix + "M1", prefix + "RingOBg", prefix + "RingIBg")
    top = g.merge(prefix + "M2", top, prefix + "LineHBg")
    top = g.merge(prefix + "M3", top, prefix + "LineVBg")
    if sweep_vis:
        g.mask(prefix + "Arm", "RectangleMask", repr(LINE_W * 1.6), repr(r),
               center=("expr", e("Point(0.5, 0.5 + %s * ASPECT)" % (r / 2.0))))
        g.background(prefix + "ArmBg", mask=prefix + "Arm", color="Accent")
        g.transform(prefix + "Sweep", prefix + "ArmBg",
                    e("-360 * math.fmod(%s * FPS - REM, FPS) / FPS" % cd))
        top = g.merge(prefix + "M4", top, prefix + "Sweep", e(sweep_vis))
    g.text(prefix + "Digit", ("expr", e(digit_expr)), 0.30)
    return g.merge(prefix + "M5", top, prefix + "Digit")


def group(name, g, output, inputs):
    gid = "".join(ch for ch in name if ch.isalnum())
    def inst(i, src):
        grp = control_group(src)
        extra = (" ControlGroup = %d," % grp) if grp else ""
        return ("\t\t\t\tInput%d = InstanceInput { SourceOp = \"LK\", Source = %s,%s },"
                % (i, lua_string(src), extra))
    ins = "\n".join(inst(i, src) for i, src in enumerate(inputs, 1))
    return ("{\n\tTools = ordered() {\n\t\t%s = GroupOperator {\n\t\t\tCtrlWZoom = false,\n"
            "\t\t\tInputs = ordered() {\n%s\n\t\t\t},\n"
            "\t\t\tOutputs = {\n\t\t\t\tMainOutput1 = InstanceOutput { SourceOp = %s, Source = \"Output\", },\n\t\t\t},\n"
            "\t\t\tViewInfo = GroupInfo { Pos = { 0, 0 }, Flags = { AllowPan = false, AutoSnap = true, "
            "RemoveRouters = true }, Size = { 900, 300, 450, 24 }, Direction = \"Horizontal\", "
            "PipeStyle = \"Direct\", Scale = 1, Offset = { 0, 0 } },\n"
            "\t\t\tTools = ordered() {\n%s\t\t\t},\n\t\t},\n\t},\n\tActiveTool = %s\n}\n"
            % (gid, ins, lua_string(output), "".join(g.tools), lua_string(gid)))


def engine(mode, std=None):
    std = std or load_standards()
    with open(os.path.join(ROOT, "fx", "engine.lua")) as fh:
        body = fh.read()
    return ('LK_MODE = "%s"\n' % mode
            + "LK_PRESETS = %s\n" % lua_literal(std["presets"])
            + "LK_SLOTS = %s\n" % lua_literal(std["slots"])
            + "local function __leaderkit_main()\n" + body + "\nend\n"
            + "local __ok, __err = xpcall(__leaderkit_main, debug and debug.traceback or tostring)\n"
            + "if not __ok then\n"
            + "  print('[LeaderKit] ERRORE: ' .. tostring(__err))\n"
            + "  pcall(function() local cc = comp or fusion:GetCurrentComp(); cc:AskUser('LeaderKit - errore', "
            + "{ { 'Errore', 'Text', Default = tostring(__err), Lines = 14, Wrap = true } }) end)\n"
            + "end\n")


STANDARDS = os.path.join(ROOT, "fx", "standards.json")


def load_standards():
    import json
    with open(STANDARDS, encoding="utf-8") as fh:
        return json.load(fh)


def lua_literal(v):
    """Valore Python -> letterale Lua (per la tabella dei preset nel motore)."""
    if v is None:
        return "nil"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return lua_string(v)
    if isinstance(v, list):
        return "{ " + ", ".join(lua_literal(x) for x in v) + " }"
    if isinstance(v, dict):
        return "{ " + ", ".join("[%s] = %s" % (lua_string(k), lua_literal(x))
                                for k, x in v.items() if not k.startswith("_")) + " }"
    raise TypeError(v)


def pv(presets, field, default=0, fn=None):
    """Espressione: valore del preset corrente (LK.Preset) per un campo."""
    vals = []
    for p in presets:
        v = p.get(field, default)
        if fn:
            v = fn(p)
        if isinstance(v, bool):
            v = 1 if v else 0
        vals.append(lua_literal(v if v is not None else default))
    return "({ %s })[math.floor(LK.Preset + 1.5)]" % ", ".join(vals)


# Campi che l'utente puo' personalizzare (checkbox "Personalizza durate").
CUSTOM_FIELDS = [("bars", "BarsSec"), ("slate", "SlateSec"), ("gap", "GapSec"),
                 ("countdown", "CountFrom"), ("tail", "TailSec")]


def field(presets, key):
    """Valore effettivo: preset o personalizzato."""
    for k, inp in CUSTOM_FIELDS:
        if k == key:
            return "iif(LK.Custom > 0.5, LK.%s, %s)" % (inp, pv(presets, key))
    return pv(presets, key)


HEAD_INPUTS = [
    "SecPreset", "Preset", "Reel", "DurMode", "Slot", "ProgramTC",
    "Custom", "BarsSec", "SlateSec", "GapSec", "CountFrom", "TailSec",
    "SecSlate", "Title", "Director", "Editor", "Colorist", "Version", "Date", "Note", "Duration", "Info",
    "SecLook"] + color_inputs() + [
    "SecAudio", "PopLevel", "BeepEach",
    "SecTimeline", "MarkersOn", "MarkerKind", "MarkerEvery", "TailOn", "Generate", "Remove", "Guide",
]


def bars_stack(g):
    """Barre 100% a pieno raster (DPP: bianco, giallo, ciano, verde, magenta, rosso, blu, nero)."""
    colors = [(1, 1, 1), (1, 1, 0), (0, 1, 1), (0, 1, 0), (1, 0, 1), (1, 0, 0), (0, 0, 1), (0, 0, 0)]
    top = None
    for i, (rr, gg, bb) in enumerate(colors):
        cx = (i + 0.5) / 8.0
        g.mask("Bar%dM" % i, "RectangleMask", repr(1 / 8.0 + 0.001), ("expr", e("1 / ASPECT")),
               center="{ %s, 0.5 }" % repr(cx))
        g._add("Bar%d" % i, "Background", G.CREATOR + [
            ("TopLeftRed", repr(float(rr))), ("TopLeftGreen", repr(float(gg))),
            ("TopLeftBlue", repr(float(bb))), ("TopLeftAlpha", "1.0"),
            ("EffectMask", ("link", "Bar%dM" % i, "Mask"))])
        top = "Bar%d" % i if top is None else g.merge("BarsM%d" % i, top, "Bar%d" % i)
    return top


def clock_stack(g, remaining_expr):
    """Orologio ident (DPP): cerchio, lancetta a scatti di 1\", secondi al FFOA."""
    cx, d = 0.80, 0.20
    r = d / 2.0
    g.mask("CkRing", "EllipseMask", repr(d), repr(d), center="{ %s, 0.5 }" % cx, border=repr(LINE_W * 1.6))
    g.background("CkRingBg", mask="CkRing", color="Accent")
    g.mask("CkArm", "RectangleMask", repr(LINE_W * 2), repr(r * 0.9),
           center=("expr", e("Point(%s, 0.5 + %s * ASPECT)" % (cx, r * 0.45))))
    g.background("CkArmBg", mask="CkArm", color="Accent")
    g._add("CkSweep", "Transform", [("Input", ("link", "CkArmBg", "Output")),
                                    ("Center", "{ %s, 0.5 }" % cx), ("Pivot", "{ %s, 0.5 }" % cx),
                                    ("Angle", ("expr", e("-6 * math.floor((REM - 1) / FPS)")))])
    top = g.merge("CkM1", "CkRingBg", "CkSweep")
    g._add("CkDigit", "TextPlus", G.CREATOR + [
        ("Center", "{ %s, 0.5 }" % cx), ("Font", '"Open Sans"'), ("Style", '"Bold"'), ("Size", "0.06"),
        ("StyledText", ("expr", e(remaining_expr))),
        ("Red1", ("expr", "LK.TextRed")), ("Green1", ("expr", "LK.TextGreen")), ("Blue1", ("expr", "LK.TextBlue")),
        ("VerticalJustificationNew", "3"), ("HorizontalJustificationNew", "3")])
    return g.merge("CkM2", top, "CkDigit")


def head(std=None):
    std = std or load_standards()
    P = std["presets"]
    B, S, GP, C = (field(P, "bars"), field(P, "slate"), field(P, "gap"), field(P, "countdown"))
    CLOCK = pv(P, "clock")
    POP = pv(P, "pop")
    FL_ON = pv(P, "sync_flash", fn=lambda p: 1 if p.get("sync_flash") else 0)
    FL_BEFORE = pv(P, "sync_flash", fn=lambda p: (p.get("sync_flash") or {}).get("before_s", 0))
    FL_FR = pv(P, "sync_flash", fn=lambda p: (p.get("sync_flash") or {}).get("frames_at_25", 0))
    HEADLEN = "(%s + %s + %s + %s)" % (B, S, GP, C)
    SYNCREM = "math.floor(%s * FPS + 0.5)" % FL_BEFORE
    SYNCFR = "math.max(1, math.floor(%s * FPS / 25 + 0.5))" % FL_FR

    g = G()
    uc = (uc_label("SecPreset", "LeaderKit %s" % __version__)
          + uc_combo("Preset", "Standard", [p["name"] for p in P])
          + uc_slider("Reel", "Rullo (cinema: FFOA a N:00:08:00)", 1, 23, 1)
          + uc_combo("DurMode", "Durata programma", ["Libera (fine dei tuoi clip)", "Fissa: slot standard",
                                                     "Fissa: personalizzata"])
          + uc_combo("Slot", "Slot standard", [s_[0] for s_ in std["slots"]])
          + uc_text("ProgramTC", "Durata personalizzata (HH:MM:SS:FF)")
          + uc_check("Custom", "Personalizza le durate del leader", 0)
          + uc_slider("BarsSec", "Barre (s)", 0, 60, 0)
          + uc_slider("SlateSec", "Slate (s)", 0, 30, 8)
          + uc_slider("GapSec", "Nero prima del programma (s)", 0, 10, 2)
          + uc_slider("CountFrom", "Countdown da (0 = nessuno)", 0, 11, 8)
          + uc_slider("TailSec", "Coda (s)", 0, 30, 8)
          + uc_label("SecSlate", "Slate")
          + uc_text("Title", "Titolo") + uc_text("Director", "Regia")
          + uc_text("Editor", "Montaggio") + uc_text("Colorist", "Color")
          + uc_text("Version", "Versione") + uc_text("Date", "Data")
          + uc_text("Note", "Note (riga libera)")
          + uc_text("Duration", "Durata (da Genera)", read_only=True)
          + uc_text("Info", "TC (da Genera)", read_only=True)
          + uc_label("SecLook", "Aspetto") + color_controls()
          + uc_label("SecAudio", "Audio (tono 1 kHz)")
          + uc_combo("PopLevel", "Livello pop", ["Dallo standard", "-20 dBFS (SMPTE / USA)", "-18 dBFS (EBU / Europa)"])
          + uc_check("BeepEach", "Bip anche su 8..3 (non standard)", 0)
          + uc_label("SecTimeline", "Timeline")
          + uc_check("MarkersOn", "Marker a intervalli", 1)
          + uc_combo("MarkerKind", "Tipo marker", ["Dallo standard", "Fine rullo", "Break"])
          + uc_slider("MarkerEvery", "Ogni (minuti, 0 = dallo standard)", 0, 60, 0, integer=False)
          + uc_check("TailOn", "Inserisci la coda", 1)
          + uc_button("Generate", "Genera sulla timeline", engine("generate", std))
          + uc_button("Remove", "Rimuovi elementi generati", engine("remove", std))
          + uc_text("Guide", "Guida timecode (da Genera)", lines=6, read_only=True))
    g.controls([("Preset", "0"), ("Reel", "1"), ("DurMode", "0"), ("Slot", "3"), ("ProgramTC", '"00:00:30:00"'),
                ("Custom", "0"), ("BarsSec", "0"), ("SlateSec", "8"), ("GapSec", "2"), ("CountFrom", "8"),
                ("TailSec", "8"), ("Note", '""'),
                ("Guide", '"Metti il blocco dove inizia il leader e premi Genera"')] + color_values() + [
                ("Title", '"TITOLO"'), ("Director", '""'), ("Editor", '""'),
                ("Colorist", '""'), ("Version", '"v1"'), ("Date", '""'),
                ("Duration", '"premi Genera"'), ("Info", '""'),
                ("PopLevel", "0"), ("BeepEach", "0"),
                ("MarkersOn", "1"), ("MarkerKind", "0"), ("MarkerEvery", "0"), ("TailOn", "1")], uc)

    g.background("Bg", color="Bg")
    # Barre
    bars = bars_stack(g)
    top = g.merge("MBars", "Bg", bars, e("iif(REM > (%s + %s + %s) * FPS, 1, 0)" % (S, GP, C)))
    # Slate (con orologio opzionale)
    slate_x = "iif(%s > 0.5, 0.40, 0.5)" % CLOCK
    heading = pv(P, "heading")
    # righe fisse dello standard; quelle con {ffoa}, {sync}... le compila Genera in LK.Info
    lines = pv(P, "slate_lines", fn=lambda p: "\n".join(l for l in p.get("slate_lines", []) if "{" not in l))
    g._add("SHeading", "TextPlus", G.CREATOR + [
        ("Center", ("expr", "Point(%s, 0.86)" % slate_x)), ("Font", '"Open Sans"'), ("Style", '"Bold"'),
        ("Size", "0.026"), ("StyledText", ("expr", 'Text(%s .. "  ·  LEADERKIT")' % heading)),
        ("Red1", ("expr", "LK.TextRed * 0.65")), ("Green1", ("expr", "LK.TextGreen * 0.65")),
        ("Blue1", ("expr", "LK.TextBlue * 0.65")),
        ("VerticalJustificationNew", "3"), ("HorizontalJustificationNew", "3")])
    g._add("STitle", "TextPlus", G.CREATOR + [
        ("Center", ("expr", "Point(%s, 0.75)" % slate_x)), ("Font", '"Open Sans"'), ("Style", '"Bold"'),
        ("Size", "0.065"), ("StyledText", ("expr", "string.upper(LK.Title.Value)")),
        ("Red1", ("expr", "LK.TextRed")), ("Green1", ("expr", "LK.TextGreen")), ("Blue1", ("expr", "LK.TextBlue")),
        ("VerticalJustificationNew", "3"), ("HorizontalJustificationNew", "3")])
    g.mask("SRule", "RectangleMask", "0.6", repr(LINE_W), center=("expr", "Point(%s, 0.665)" % slate_x))
    g.background("SRuleBg", mask="SRule", color="Accent", scale=0.6)
    details = ('"DIRECTOR   " .. LK.Director.Value .. "\\nEDITOR   " .. LK.Editor.Value'
               ' .. "\\nCOLORIST   " .. LK.Colorist.Value .. "\\nDATE   " .. LK.Date.Value'
               ' .. "\\nVERSION   " .. LK.Version.Value .. "\\nDURATION   " .. LK.Duration.Value'
               ' .. "\\nFRAME RATE   " .. string.format("%g fps", comp:GetPrefs("Comp.FrameFormat.Rate"))'
               ' .. "\\nRESOLUTION   " .. comp:GetPrefs("Comp.FrameFormat.Width") .. " x "'
               ' .. comp:GetPrefs("Comp.FrameFormat.Height") .. "\\n" .. LK.Note.Value'
               ' .. "\\n\\n" .. LK.Info.Value .. "\\n" .. ' + lines)
    g._add("SDetails", "TextPlus", G.CREATOR + [
        ("Center", ("expr", "Point(%s, 0.38)" % slate_x)), ("Font", '"Open Sans"'), ("Style", '"Regular"'),
        ("Size", "0.022"), ("StyledText", ("expr", "Text(%s)" % details)), ("LineSpacing", "1.1"),
        ("Red1", ("expr", "LK.TextRed")), ("Green1", ("expr", "LK.TextGreen")), ("Blue1", ("expr", "LK.TextBlue")),
        ("VerticalJustificationNew", "3"), ("HorizontalJustificationNew", "3")])
    s_ = g.merge("SM1", "SHeading", "STitle")
    s_ = g.merge("SM2", s_, "SRuleBg")
    s_ = g.merge("SM3", s_, "SDetails")
    clock = clock_stack(g, 'Text(tostring(math.ceil(REM / FPS)))')
    s_ = g.merge("SM4", s_, clock, "iif(%s > 0.5, 1, 0)" % CLOCK)
    top = g.merge("MSlate", top, s_, e("iif(REM <= (%s + %s + %s) * FPS and REM > (%s + %s) * FPS, 1, 0)"
                                        % (S, GP, C, GP, C)))
    # Countdown + 2-pop
    CDX = C
    lead = leader_stack(g, "L", 'Text(iif(REM < %s * FPS and REM >= 2 * FPS, tostring(math.ceil(REM / FPS)), ""))' % CDX,
                        sweep_vis="iif(REM < %s * FPS and REM > 2 * FPS, 1, 0)" % CDX, cd=CDX)
    top = g.merge("MLeader", top, lead,
                  e("iif(%s > 0 and REM <= %s * FPS and (REM > 2 * FPS or (REM == 2 * FPS and %s > 0.5)), 1, 0)"
                    % (CDX, CDX, POP)))
    g.text("PicStart", ("expr", 'Text("PICTURE\\nSTART")'), 0.075, spacing=1.0)
    top = g.merge("MPicStart", top, "PicStart", e("iif(%s > 0 and REM == %s * FPS, 1, 0)" % (CDX, CDX)))
    # Sync flash (DPP / Sky / digital clap)
    g._add("Flash", "Background", G.CREATOR + [("TopLeftRed", "1.0"), ("TopLeftGreen", "1.0"),
                                               ("TopLeftBlue", "1.0"), ("TopLeftAlpha", "1.0")])
    top = g.merge("MFlash", top, "Flash", e("iif(%s > 0.5 and REM <= %s and REM > %s - %s, 1, 0)"
                                            % (FL_ON, SYNCREM, SYNCREM, SYNCFR)))
    # Indicazione della durata prima di Genera
    g.text("Warn", ("expr", e("Text(\"Premi GENERA nell'Inspector: il blocco diventa di \" .. %s .. \" secondi\")"
                              % HEADLEN)), 0.03, y=0.08, grey=1.0)
    top = g.merge("MWarn", top, "Warn",
                  e("iif(math.abs((comp.RenderEnd - comp.RenderStart + 1) - %s * FPS) > 0.5, 1, 0)" % HEADLEN))
    return group("LeaderKit Head", g, top, HEAD_INPUTS)


TAIL_INPUTS = ["TailPop", "TailFlash", "CardFrom", "CardTo", "CardText", "Info"]


def tail(std=None):
    g = G()
    uc = (uc_check("TailPop", "Tail pop a +2\"", 1) + uc_check("TailFlash", "Flash (clap) a +2\"", 0)
          + uc_slider("CardFrom", "Card da (s)", 0, 30, 4, integer=False)
          + uc_slider("CardTo", "Card fino a (s)", 0, 30, 7, integer=False)
          + uc_text("CardText", "Testo card") + uc_text("Info", "Info (da Genera)") + color_controls())
    g.controls([("TailPop", "1"), ("TailFlash", "0"), ("CardFrom", "4"), ("CardTo", "7"),
                ("CardText", '"END OF PROGRAM"'), ("Info", '""')] + color_values(), uc)
    g.background("Bg", color="Bg")
    lead = leader_stack(g, "T", 'Text("2")')
    top = g.merge("MPop", "Bg", lead, e("iif(LK.TailPop > 0.5 and ELAPSED == 2 * FPS - 1, 1, 0)"))
    g._add("Flash", "Background", G.CREATOR + [("TopLeftRed", "1.0"), ("TopLeftGreen", "1.0"),
                                               ("TopLeftBlue", "1.0"), ("TopLeftAlpha", "1.0")])
    top = g.merge("MFlash", top, "Flash", e("iif(LK.TailFlash > 0.5 and ELAPSED == 2 * FPS - 1, 1, 0)"))
    g.text("CardText", ("expr", "Text(LK.CardText.Value)"), 0.07)
    g.text("CardSub", ("expr", "Text(LK.Info.Value)"), 0.024, y=0.36, grey=0.7, style="Regular")
    card = g.merge("CM1", "CardText", "CardSub")
    top = g.merge("MCard", top, card, e("iif(ELAPSED >= LK.CardFrom * FPS and ELAPSED < LK.CardTo * FPS, 1, 0)"))
    return group("LeaderKit Tail", g, top, TAIL_INPUTS + color_inputs())


def build():
    out = os.path.join(ROOT, "dist")
    os.makedirs(out, exist_ok=True)
    files = [("LeaderKit Head.setting", head()), ("LeaderKit Tail.setting", tail())]
    path = os.path.join(out, "LeaderKit-%s.drfx" % __version__)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in files:
            zf.writestr("Edit/Generators/LeaderKit/" + name, text)
            with open(os.path.join(out, name), "w") as fh:
                fh.write(text)
    return path


if __name__ == "__main__":
    print(build())
