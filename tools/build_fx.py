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
import re
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
    """inputs: lista di nomi o di (nome, scheda dell'Inspector)."""
    gid = "".join(ch for ch in name if ch.isalnum())

    def inst(i, item):
        src, page = item if isinstance(item, tuple) else (item, None)
        grp = control_group(src)
        extra = (" ControlGroup = %d," % grp) if grp else ""
        if page:
            extra += " Page = %s," % lua_string(page)
        return ("\t\t\t\tInput%d = InstanceInput { SourceOp = \"LK\", Source = %s,%s },"
                % (i, lua_string(src), extra))
    ins = "\n".join(inst(i, item) for i, item in enumerate(inputs, 1))
    return ("{\n\tTools = ordered() {\n\t\t%s = GroupOperator {\n\t\t\tCtrlWZoom = false,\n"
            "\t\t\tInputs = ordered() {\n%s\n\t\t\t},\n"
            "\t\t\tOutputs = {\n\t\t\t\tMainOutput1 = InstanceOutput { SourceOp = %s, Source = \"Output\", },\n\t\t\t},\n"
            "\t\t\tViewInfo = GroupInfo { Pos = { 0, 0 }, Flags = { AllowPan = false, AutoSnap = true, "
            "RemoveRouters = true }, Size = { 900, 300, 450, 24 }, Direction = \"Horizontal\", "
            "PipeStyle = \"Direct\", Scale = 1, Offset = { 0, 0 } },\n"
            "\t\t\tTools = ordered() {\n%s\t\t\t},\n\t\t},\n\t},\n\tActiveTool = %s\n}\n"
            % (gid, ins, lua_string(output), "".join(g.tools), lua_string(gid)))


def on_page(page, controls_text):
    """Mette i controlli (testo UserControls) nella scheda indicata."""
    return re.sub(r"LINKS_Name = ", 'ICS_ControlPage = %s, LINKS_Name = ' % lua_string(page), controls_text)


def family_tables(std, family):
    """Preset e durate della famiglia (tabelle Lua del motore)."""
    by_id = dict((p["id"], p) for p in std["presets"])
    slots = dict((s_[0], s_[1]) for s_ in std["slots"])
    presets = [by_id[i] for i in family["presets"]]
    durations = []
    for d in family["durations"]:
        if d == "free":
            durations.append({"kind": "free", "label": "Libera (fine dei tuoi clip)"})
        elif d == "custom":
            durations.append({"kind": "custom", "label": "Personalizzata (HH:MM:SS:FF)"})
        else:
            durations.append({"kind": "slot", "label": d, "seconds": slots[d]})
    return presets, durations


def engine(mode, std=None, family=None):
    std = std or load_standards()
    family = family or std["families"][0]
    presets, durations = family_tables(std, family)
    with open(os.path.join(ROOT, "fx", "engine.lua")) as fh:
        body = fh.read()
    return ('LK_MODE = "%s"\n' % mode
            + "LK_PRESETS = %s\n" % lua_literal(presets)
            + "LK_DURATIONS = %s\n" % lua_literal(durations)
            + "LK_DUR_DEFAULT = %d\n" % family.get("default_duration", 0)
            + "LK_PARAMS = %s\n" % lua_literal(param_names(family))
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


def field(presets, key, custom=False):
    """Valore effettivo: preset o (se la famiglia lo consente) personalizzato."""
    if custom:
        for k, inp in CUSTOM_FIELDS:
            if k == key:
                return "iif(LK.Custom > 0.5, LK.%s, %s)" % (inp, pv(presets, key))
    return pv(presets, key)


# ---------------------------------------------------------------- schede e campi

PAGES = ["Progetto", "Produzione", "Post", "Tecnico", "Aspetto", "Taratura"]

PRODUCTION_FIELDS = [("Title", "Titolo", None), ("Production", "Produzione", "PRODUCTION"),
                     ("Producer", "Produttore", "PRODUCER"), ("Director", "Regia", "DIRECTOR"),
                     ("Client", "Cliente / inserzionista", "CLIENT"), ("Agency", "Agenzia", "AGENCY"),
                     ("Code", "Codice (Ad-ID / Clock / Auditel)", "CODE"),
                     ("Episode", "Episodio / rullo", "EPISODE"), ("Language", "Lingua / versione", "LANGUAGE"),
                     ("Date", "Data", "DATE")]
POST_FIELDS = [("Editor", "Montaggio", "EDITOR"), ("Colorist", "Color", "COLORIST"),
               ("Sound", "Suono / mix", "SOUND"), ("VFXBy", "VFX", "VFX"), ("Version", "Versione", "VERSION")]
PHASES = ["—", "OFFLINE", "ONLINE / CONFORM", "GRADING", "MIX", "MASTER", "CONSEGNA"]
STATUSES = [("StColor", "Stato color", "COLOR"), ("StSound", "Stato suono", "SOUND"),
            ("StVFX", "Stato VFX", "VFX"), ("StMusic", "Stato musica", "MUSIC"), ("StTitles", "Stato titoli", "TITLES")]
STATUS_VALUES = ["—", "TEMP", "FINAL"]
FRAMELINES = [("FL133", "1.33", 4.0 / 3.0), ("FL166", "1.66", 1.66), ("FL178", "1.78", 16.0 / 9.0),
              ("FL185", "1.85", 1.85), ("FL200", "2.00", 2.0), ("FL220", "2.20", 2.2), ("FL239", "2.39", 2.39)]
CALIBRATION = [("CalStars", "Stelle di fuoco negli angoli", 1), ("CalCenter", "Mirino centrale", 1),
               ("CalGrey", "Scala di grigi", 1), ("CalColor", "Patch di colore RGBCMY", 1),
               ("CalRamps", "Rampe B/N, R, G, B", 1), ("CalBlue", "Verifica blu (filtro Wratten 47B)", 1),
               ("CalContour", "Sfera sfumata (contouring)", 1), ("CalPeak", "Bianco di picco", 1),
               ("CalLabels", "Etichette fps / risoluzione", 1)]
LOGO_POS = ["In alto a destra", "In alto a sinistra", "In basso a destra", "In basso a sinistra", "Al centro"]


def param_names(family):
    """Parametri del pannello da ricopiare quando Genera ricrea il blocco."""
    skip = ("Generate", "Remove", "Guide", "Duration", "Info", "ColorInfo")
    return [src for src, _ in head_inputs(family, True) if not src.startswith("Sec") and src not in skip]


def head_inputs(family, has_pop=True):
    durs = family["durations"]
    out = [("SecPreset", "Progetto"), ("Preset", "Progetto")]
    if family.get("reel"):
        out.append(("Reel", "Progetto"))
    out.append(("DurSel", "Progetto"))
    if "custom" in durs:
        out.append(("ProgramTC", "Progetto"))
    if family.get("custom_leader"):
        out += [(x, "Progetto") for x in ("Custom", "BarsSec", "SlateSec", "GapSec", "CountFrom", "TailSec")]
    if family.get("markers"):
        out += [("MarkersOn", "Progetto"), ("MarkerEvery", "Progetto")]
        if len(family["markers"]) > 1:
            out.append(("MarkerKind", "Progetto"))
    out += [(x, "Progetto") for x in ("TailOn", "Generate", "Remove", "Guide", "Duration", "Info")]
    out += [(f, "Produzione") for f, _, _ in PRODUCTION_FIELDS]
    out += [(f, "Post") for f, _, _ in POST_FIELDS] + [("Phase", "Post")]
    out += [(f, "Post") for f, _, _ in STATUSES] + [("Note", "Post")]
    out += [(x, "Tecnico") for x in ("SecGuides", "Guides", "GuidesSlate")] + [(f, "Tecnico") for f, _, _ in FRAMELINES]
    out += [(x, "Tecnico") for x in ("SafeAction", "SafeTitle", "SecTech", "ColorInfo", "AudioFormat", "SecAudio")]
    if has_pop:
        out += [("PopLevel", "Tecnico"), ("BeepEach", "Tecnico")]
    out += [("SecLook", "Aspetto")] + [(c, "Aspetto") for c in color_inputs()]
    out += [(x, "Aspetto") for x in ("SecLogo", "Logo", "LogoPos", "LogoSize", "LogoOnTail")]
    out += [("CalOn", "Taratura")] + [(f, "Taratura") for f, _, _ in CALIBRATION]
    return out


def rect(g, name, cx, cy, w, hfrac, color=None, rgb=None, border=None):
    """Rettangolo: w in frazione di larghezza, hfrac in frazione di altezza, centro (cx, cy)."""
    g.mask(name + "M", "RectangleMask", repr(w), ("expr", e("%s / ASPECT" % repr(hfrac))),
           center="{ %s, %s }" % (repr(cx), repr(cy)), border=border)
    if rgb is not None:
        return g._add(name, "Background", G.CREATOR + [
            ("TopLeftRed", repr(float(rgb[0]))), ("TopLeftGreen", repr(float(rgb[1]))),
            ("TopLeftBlue", repr(float(rgb[2]))), ("TopLeftAlpha", "1.0"),
            ("EffectMask", ("link", name + "M", "Mask"))])
    return g.background(name, mask=name + "M", color=color or "Accent")


def chain(g, prefix, names):
    top = names[0]
    for i, n_ in enumerate(names[1:]):
        top = g.merge("%s%d" % (prefix, i), top, n_)
    return top


def transparent(g, name):
    return g._add(name, "Background", G.CREATOR + [("TopLeftRed", "0"), ("TopLeftGreen", "0"),
                                                  ("TopLeftBlue", "0"), ("TopLeftAlpha", "0")])


def layer(g, base, fg, name, blend):
    return g.merge(name, base, fg, blend)


def calibration_stack(g):
    """Strumenti di taratura del leader digitale (ispirati a SMPTE RP 428-6)."""
    top = transparent(g, "CalBase")
    # stelle di fuoco: 12 raggi, poi copiate nei 4 angoli
    prev = None
    for k in range(12):
        nm = "StarR%d" % k
        ins = [("Filter", 'FuID { "Fast Gaussian" }'), ("SoftEdge", "0"), ("MaskWidth", "1920"),
               ("MaskHeight", "1080"), ("PixelAspect", "{ 1, 1 }"), ("UseFrameFormatSettings", "1"),
               ("ClippingMode", 'FuID { "None" }'), ("Width", "0.0022"), ("Height", "0.075"),
               ("Angle", repr(k * 15.0))]
        if prev:
            ins.append(("EffectMask", ("link", prev, "Mask")))
        g._add(nm, "RectangleMask", ins)
        prev = nm
    g.background("StarBg", mask=prev, color="Text", scale=0.9)
    stars = None
    for i, (x, y) in enumerate([(0.05, 0.88), (0.95, 0.88), (0.05, 0.12), (0.95, 0.12)]):
        t = g._add("StarT%d" % i, "Transform", [("Input", ("link", "StarBg", "Output")),
                                               ("Center", "{ %s, %s }" % (x, y))])
        stars = t if stars is None else g.merge("StarsM%d" % i, stars, t)
    top = layer(g, top, stars, "CalL1", "iif(LK.CalStars > 0.5, 1, 0)")
    # mirino centrale
    c1 = rect(g, "CtrBox", 0.5, 0.5, 0.03, 0.053, color="Accent", border=repr(LINE_W))
    c2 = rect(g, "CtrIn", 0.5, 0.5, 0.012, 0.021, color="Accent", border=repr(LINE_W))
    top = layer(g, top, g.merge("CtrM", c1, c2), "CalL2", "iif(LK.CalCenter > 0.5, 1, 0)")
    # scala di grigi (11 gradini)
    greys = [rect(g, "Grey%d" % i, 0.735 + i * 0.02, 0.66, 0.02, 0.05, rgb=(i / 10.0,) * 3) for i in range(11)]
    top = layer(g, top, chain(g, "GreyM", greys), "CalL3", "iif(LK.CalGrey > 0.5, 1, 0)")
    # patch di colore
    cols = [(1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0), (0, 1, 1), (1, 0, 1)]
    patches = [rect(g, "Col%d" % i, 0.75 + i * 0.037, 0.52, 0.035, 0.07, rgb=c) for i, c in enumerate(cols)]
    top = layer(g, top, chain(g, "ColM", patches), "CalL4", "iif(LK.CalColor > 0.5, 1, 0)")
    # rampe (Background orizzontale nero -> colore)
    ramps = []
    for i, c in enumerate([(1, 1, 1), (1, 0, 0), (0, 1, 0), (0, 0, 1)]):
        nm = "Ramp%d" % i
        g.mask(nm + "M", "RectangleMask", "0.22", ("expr", e("0.045 / ASPECT")),
               center="{ 0.155, %s }" % repr(0.66 - i * 0.055))
        g._add(nm, "Background", G.CREATOR + [
            ("Type", 'FuID { "Horizontal" }'),
            ("TopLeftRed", "0"), ("TopLeftGreen", "0"), ("TopLeftBlue", "0"), ("TopLeftAlpha", "1"),
            ("TopRightRed", repr(float(c[0]))), ("TopRightGreen", repr(float(c[1]))),
            ("TopRightBlue", repr(float(c[2]))), ("TopRightAlpha", "1"),
            ("EffectMask", ("link", nm + "M", "Mask"))])
        ramps.append(nm)
    top = layer(g, top, chain(g, "RampM", ramps), "CalL5", "iif(LK.CalRamps > 0.5, 1, 0)")
    # verifica del blu: blu, magenta, ciano, bianco hanno lo stesso canale blu
    blue = [rect(g, "Blu%d" % i, 0.80 + (i % 2) * 0.03, 0.86 - (i // 2) * 0.053, 0.03, 0.053, rgb=c)
            for i, c in enumerate([(1, 0, 1), (0, 1, 1), (1, 1, 1), (0, 0, 1)])]
    top = layer(g, top, chain(g, "BluM", blue), "CalL6", "iif(LK.CalBlue > 0.5, 1, 0)")
    # sfera sfumata (contouring)
    g._add("SphM", "EllipseMask", [("Filter", 'FuID { "Fast Gaussian" }'), ("SoftEdge", "0.035"),
                                   ("MaskWidth", "1920"), ("MaskHeight", "1080"), ("PixelAspect", "{ 1, 1 }"),
                                   ("UseFrameFormatSettings", "1"), ("ClippingMode", 'FuID { "None" }'),
                                   ("Width", "0.06"), ("Height", "0.06"), ("Center", "{ 0.16, 0.86 }")])
    g._add("Sph", "Background", G.CREATOR + [("TopLeftRed", "1"), ("TopLeftGreen", "1"), ("TopLeftBlue", "1"),
                                             ("TopLeftAlpha", "1"), ("EffectMask", ("link", "SphM", "Mask"))])
    top = layer(g, top, "Sph", "CalL7", "iif(LK.CalContour > 0.5, 1, 0)")
    # bianco di picco
    pk = rect(g, "Peak", 0.24, 0.86, 0.03, 0.053, rgb=(1, 1, 1))
    top = layer(g, top, pk, "CalL8", "iif(LK.CalPeak > 0.5, 1, 0)")
    # etichette: fps e classe di risoluzione
    lab = ('Text(string.format("%g/SEC", comp:GetPrefs("Comp.FrameFormat.Rate")) .. "   " .. '
           'iif(comp:GetPrefs("Comp.FrameFormat.Width") >= 7680, "8K", iif(comp:GetPrefs("Comp.FrameFormat.Width") >= 3800, "4K", '
           'iif(comp:GetPrefs("Comp.FrameFormat.Width") >= 1900, "2K / HD", "SD"))))')
    g._add("CalLab", "TextPlus", G.CREATOR + [
        ("Center", "{ 0.155, 0.36 }"), ("Font", '"Open Sans"'), ("Style", '"Bold"'), ("Size", "0.022"),
        ("StyledText", ("expr", lab)), ("Red1", ("expr", "LK.TextRed")), ("Green1", ("expr", "LK.TextGreen")),
        ("Blue1", ("expr", "LK.TextBlue")), ("VerticalJustificationNew", "3"), ("HorizontalJustificationNew", "3")])
    top = layer(g, top, "CalLab", "CalL9", "iif(LK.CalLabels > 0.5, 1, 0)")
    return top


def guides_stack(g):
    """Frame lines dei rapporti d'aspetto e safe area, calcolate sul raster reale."""
    top = transparent(g, "GdBase")
    for key, label, ar in FRAMELINES:
        a = repr(ar)
        ww = "iif(%s >= ASPECT, 1, %s / ASPECT)" % (a, a)
        hw = "iif(%s >= ASPECT, 1 / %s, 1 / ASPECT)" % (a, a)
        g._add(key + "M", "RectangleMask", [
            ("Filter", 'FuID { "Fast Gaussian" }'), ("SoftEdge", "0"), ("MaskWidth", "1920"),
            ("MaskHeight", "1080"), ("PixelAspect", "{ 1, 1 }"), ("UseFrameFormatSettings", "1"),
            ("ClippingMode", 'FuID { "None" }'), ("Width", ("expr", e(ww))), ("Height", ("expr", e(hw))),
            ("Solid", "0"), ("BorderWidth", repr(LINE_W))])
        g.background(key + "Bg", mask=key + "M", color="Accent")
        g._add(key + "T", "TextPlus", G.CREATOR + [
            ("Center", ("expr", e("Point(0.5 - (%s) / 2 + 0.025, 0.5 + (%s) * ASPECT / 2 - 0.03)" % (ww, hw)))),
            ("Font", '"Open Sans"'), ("Style", '"Bold"'), ("Size", "0.014"), ("StyledText", lua_string(label + ":1")),
            ("Red1", ("expr", "LK.AccentRed")), ("Green1", ("expr", "LK.AccentGreen")), ("Blue1", ("expr", "LK.AccentBlue")),
            ("VerticalJustificationNew", "3"), ("HorizontalJustificationNew", "3")])
        one = g.merge(key + "L", key + "Bg", key + "T")
        top = layer(g, top, one, key + "X", "iif(LK.%s > 0.5, 1, 0)" % key)
    for key, pct in (("SafeAction", 0.93), ("SafeTitle", 0.90)):
        g._add(key + "M", "RectangleMask", [
            ("Filter", 'FuID { "Fast Gaussian" }'), ("SoftEdge", "0"), ("MaskWidth", "1920"),
            ("MaskHeight", "1080"), ("PixelAspect", "{ 1, 1 }"), ("UseFrameFormatSettings", "1"),
            ("ClippingMode", 'FuID { "None" }'), ("Width", repr(pct)), ("Height", ("expr", e("%s / ASPECT" % pct))),
            ("Solid", "0"), ("BorderWidth", repr(LINE_W * 0.7))])
        g.background(key + "Bg", mask=key + "M", color="Accent", scale=0.6)
        top = layer(g, top, key + "Bg", key + "X", "iif(LK.%s > 0.5, 1, 0)" % key)
    return top


def slate_details():
    """Righe della slate: solo i campi compilati (+ dati tecnici calcolati)."""
    parts = []
    for f, _, lab in PRODUCTION_FIELDS + POST_FIELDS:
        if lab:
            parts.append('iif(LK.%s.Value == "", "", "%s   " .. LK.%s.Value .. "\\n")' % (f, lab, f))
    phase = "({ %s })[math.floor(LK.Phase + 1.5)]" % ", ".join(lua_string(x) for x in PHASES)
    parts.append('iif(LK.Phase < 0.5, "", "PHASE   " .. %s .. "\\n")' % phase)
    st = " .. ".join('iif(LK.%s < 0.5, "", "%s " .. ({ "—", "TEMP", "FINAL" })[math.floor(LK.%s + 1.5)] .. "   ")'
                     % (f, lab, f) for f, _, lab in STATUSES)
    parts.append("(%s) .. \"\\n\"" % st)
    parts.append('"DURATION   " .. LK.Duration.Value .. "\\n"')
    parts.append('"FRAME RATE   " .. string.format("%g fps", comp:GetPrefs("Comp.FrameFormat.Rate")) .. '
                 '"   ·   " .. comp:GetPrefs("Comp.FrameFormat.Width") .. " x " .. comp:GetPrefs("Comp.FrameFormat.Height") .. "\\n"')
    parts.append('iif(LK.ColorInfo.Value == "", "", LK.ColorInfo.Value .. "\\n")')
    parts.append('iif(LK.AudioFormat.Value == "", "", "AUDIO   " .. LK.AudioFormat.Value .. "\\n")')
    parts.append('iif(LK.Note.Value == "", "", LK.Note.Value .. "\\n")')
    parts.append('"\\n" .. LK.Info.Value')
    return " .. ".join(parts)


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
    cx, d = 0.88, 0.14
    r = d / 2.0
    g.mask("CkRing", "EllipseMask", repr(d), repr(d), center="{ %s, 0.2 }" % cx, border=repr(LINE_W * 1.6))
    g.background("CkRingBg", mask="CkRing", color="Accent")
    g.mask("CkArm", "RectangleMask", repr(LINE_W * 2), repr(r * 0.9),
           center=("expr", e("Point(%s, 0.2 + %s * ASPECT)" % (cx, r * 0.45))))
    g.background("CkArmBg", mask="CkArm", color="Accent")
    g._add("CkSweep", "Transform", [("Input", ("link", "CkArmBg", "Output")),
                                    ("Center", "{ %s, 0.2 }" % cx), ("Pivot", "{ %s, 0.2 }" % cx),
                                    ("Angle", ("expr", e("-6 * math.floor((REM - 1) / FPS)")))])
    top = g.merge("CkM1", "CkRingBg", "CkSweep")
    g._add("CkDigit", "TextPlus", G.CREATOR + [
        ("Center", "{ %s, 0.2 }" % cx), ("Font", '"Open Sans"'), ("Style", '"Bold"'), ("Size", "0.045"),
        ("StyledText", ("expr", e(remaining_expr))),
        ("Red1", ("expr", "LK.TextRed")), ("Green1", ("expr", "LK.TextGreen")), ("Blue1", ("expr", "LK.TextBlue")),
        ("VerticalJustificationNew", "3"), ("HorizontalJustificationNew", "3")])
    return g.merge("CkM2", top, "CkDigit")


def head(std=None, family=None):
    std = std or load_standards()
    family = family or std["families"][0]
    P, DUR = family_tables(std, family)
    CUST = bool(family.get("custom_leader"))
    B, S, GP, C = (field(P, "bars", CUST), field(P, "slate", CUST), field(P, "gap", CUST), field(P, "countdown", CUST))
    CLOCK = pv(P, "clock")
    POP = pv(P, "pop")
    FL_ON = pv(P, "sync_flash", fn=lambda p: 1 if p.get("sync_flash") else 0)
    FL_BEFORE = pv(P, "sync_flash", fn=lambda p: (p.get("sync_flash") or {}).get("before_s", 0))
    FL_FR = pv(P, "sync_flash", fn=lambda p: (p.get("sync_flash") or {}).get("frames_at_25", 0))
    HEADLEN = "(%s + %s + %s + %s)" % (B, S, GP, C)
    SYNCREM = "math.floor(%s * FPS + 0.5)" % FL_BEFORE
    SYNCFR = "math.max(1, math.floor(%s * FPS / 25 + 0.5))" % FL_FR
    has_pop = any(p.get("pop") or p.get("sync_flash") or p.get("tail_pop") or p.get("tail_flash") for p in P)

    # --- controlli, per scheda
    prog = (uc_label("SecPreset", "%s %s" % (family["name"], __version__))
            + uc_combo("Preset", "Standard", [p["name"] for p in P]))
    if family.get("reel"):
        prog += uc_slider("Reel", "Rullo (FFOA a N:00:08:00)", 1, 23, 1)
    prog += uc_combo("DurSel", "Durata programma", [d["label"] for d in DUR])
    if "custom" in family["durations"]:
        prog += uc_text("ProgramTC", "Durata personalizzata (HH:MM:SS:FF)")
    if CUST:
        prog += (uc_check("Custom", "Personalizza le durate del leader", 0)
                 + uc_slider("BarsSec", "Barre (s)", 0, 60, 0) + uc_slider("SlateSec", "Slate (s)", 0, 30, 8)
                 + uc_slider("GapSec", "Nero prima del programma (s)", 0, 10, 2)
                 + uc_slider("CountFrom", "Countdown da (0 = nessuno)", 0, 11, 8)
                 + uc_slider("TailSec", "Coda (s)", 0, 30, 8))
    kinds = family.get("markers", [])
    if kinds:
        label = {"reel": "Marker di fine rullo", "break": "Marker di break"}[kinds[0]] if len(kinds) == 1 else "Marker a intervalli"
        prog += (uc_check("MarkersOn", label, 1)
                 + uc_slider("MarkerEvery", "Ogni (minuti, 0 = dallo standard)", 0, 60, 0, integer=False))
        if len(kinds) > 1:
            prog += uc_combo("MarkerKind", "Tipo marker", ["Dallo standard", "Fine rullo", "Break"])
    prog += (uc_check("TailOn", "Inserisci la coda", 1)
             + uc_button("Generate", "Genera sulla timeline", engine("generate", std, family))
             + uc_button("Remove", "Rimuovi elementi generati", engine("remove", std, family))
             + uc_text("Guide", "Guida timecode", lines=6, read_only=True)
             + uc_text("Duration", "Durata programma (calcolata)", read_only=True)
             + uc_text("Info", "Timecode (calcolati)", lines=2, read_only=True))
    prod = "".join(uc_text(f, label) for f, label, _ in PRODUCTION_FIELDS)
    post = "".join(uc_text(f, label) for f, label, _ in POST_FIELDS)
    post += uc_combo("Phase", "Fase di lavorazione", PHASES)
    post += "".join(uc_combo(f, label, STATUS_VALUES) for f, label, _ in STATUSES)
    post += uc_text("Note", "Note (riga libera)")
    tech = (uc_label("SecGuides", "Frame lines e safe area (sul countdown)")
            + uc_check("Guides", "Mostra le frame lines", 1) + uc_check("GuidesSlate", "Anche sulla slate", 0)
            + "".join(uc_check(f, "Frame line " + lab + ":1", 1 if f in ("FL185", "FL239") else 0) for f, lab, _ in FRAMELINES)
            + uc_check("SafeAction", "Safe action 93% (EBU R95)", 0) + uc_check("SafeTitle", "Safe graphics 90%", 0)
            + uc_label("SecTech", "Dati tecnici")
            + uc_text("ColorInfo", "Spazio colore (letto da Genera)", read_only=True)
            + uc_text("AudioFormat", "Formato audio (es. 5.1 + stereo, 24 bit 48 kHz)")
            + uc_label("SecAudio", "Audio (tono 1 kHz)" if has_pop else "Audio: questo standard non prevede sync pop"))
    if has_pop:
        tech += (uc_combo("PopLevel", "Livello pop", ["Dallo standard", "-20 dBFS (SMPTE / USA)", "-18 dBFS (EBU / Europa)"])
                 + uc_check("BeepEach", "Bip anche su 8..3 (non standard)", 0))
    look = (uc_label("SecLook", "Colori") + color_controls()
            + uc_label("SecLogo", "Logo (inserito da Genera sopra la slate)")
            + uc_text("Logo", "File del logo (percorso PNG/TIFF/JPG)")
            + uc_combo("LogoPos", "Posizione", LOGO_POS)
            + uc_slider("LogoSize", "Dimensione (%)", 5, 100, 20, integer=False)
            + uc_check("LogoOnTail", "Anche sulla coda", 0))
    cal = (uc_check("CalOn", "Strumenti di taratura sul countdown", 1)
           + "".join(uc_check(f, label, d) for f, label, d in CALIBRATION))
    uc = (on_page("Progetto", prog) + on_page("Produzione", prod) + on_page("Post", post)
          + on_page("Tecnico", tech) + on_page("Aspetto", look) + on_page("Taratura", cal))

    values = [("Preset", "0"), ("Reel", "1"), ("DurSel", str(family.get("default_duration", 0))),
              ("ProgramTC", '"00:00:30:00"'), ("Custom", "0"), ("BarsSec", "0"), ("SlateSec", "8"),
              ("GapSec", "2"), ("CountFrom", "8"), ("TailSec", "8"),
              ("MarkersOn", "1"), ("MarkerKind", "0"), ("MarkerEvery", "0"), ("TailOn", "1"),
              ("Guide", '"Metti il blocco dove inizia il leader (anche a timeline vuota) e premi Genera"'),
              ("Duration", '"premi Genera"'), ("Info", '""'), ("Title", '"TITOLO"'), ("Version", '"v1"'),
              ("Phase", "0"), ("Note", '""'), ("Guides", "1"), ("GuidesSlate", "0"),
              ("SafeAction", "0"), ("SafeTitle", "0"), ("ColorInfo", '""'), ("AudioFormat", '""'),
              ("PopLevel", "0"), ("BeepEach", "0"), ("Logo", '""'), ("LogoPos", "0"), ("LogoSize", "20"),
              ("LogoOnTail", "0"), ("CalOn", "1")]
    values += [(f, '""') for f, _, _ in PRODUCTION_FIELDS + POST_FIELDS if f not in ("Title", "Version")]
    values += [(f, "0") for f, _, _ in STATUSES]
    values += [(f, "1" if f in ("FL185", "FL239") else "0") for f, _, _ in FRAMELINES]
    values += [(f, str(d)) for f, _, d in CALIBRATION]
    values += color_values()

    g = G()
    g.controls(values, uc)
    g.background("Bg", color="Bg")
    # barre
    bars = bars_stack(g)
    top = g.merge("MBars", "Bg", bars, e("iif(REM > (%s + %s + %s) * FPS, 1, 0)" % (S, GP, C)))
    # slate
    heading = pv(P, "heading")
    lines = pv(P, "slate_lines", fn=lambda p: "\n".join(l for l in p.get("slate_lines", []) if "{" not in l))
    g._add("SHeading", "TextPlus", G.CREATOR + [
        ("Center", "{ 0.5, 0.88 }"), ("Font", '"Open Sans"'), ("Style", '"Bold"'), ("Size", "0.024"),
        ("StyledText", ("expr", 'Text(%s .. "  ·  LEADERKIT")' % heading)),
        ("Red1", ("expr", "LK.TextRed * 0.65")), ("Green1", ("expr", "LK.TextGreen * 0.65")),
        ("Blue1", ("expr", "LK.TextBlue * 0.65")),
        ("VerticalJustificationNew", "3"), ("HorizontalJustificationNew", "3")])
    g._add("STitle", "TextPlus", G.CREATOR + [
        ("Center", "{ 0.5, 0.78 }"), ("Font", '"Open Sans"'), ("Style", '"Bold"'),
        ("Size", "0.06"), ("StyledText", ("expr", "string.upper(LK.Title.Value)")),
        ("Red1", ("expr", "LK.TextRed")), ("Green1", ("expr", "LK.TextGreen")), ("Blue1", ("expr", "LK.TextBlue")),
        ("VerticalJustificationNew", "3"), ("HorizontalJustificationNew", "3")])
    g.mask("SRule", "RectangleMask", "0.6", repr(LINE_W), center="{ 0.5, 0.705 }")
    g.background("SRuleBg", mask="SRule", color="Accent", scale=0.6)
    g._add("SDetails", "TextPlus", G.CREATOR + [
        ("Center", "{ 0.5, 0.40 }"), ("Font", '"Open Sans"'), ("Style", '"Regular"'),
        ("Size", "0.019"), ("StyledText", ("expr", "Text(%s .. \"\\n\" .. %s)" % (slate_details(), lines))),
        ("LineSpacing", "1.05"),
        ("Red1", ("expr", "LK.TextRed")), ("Green1", ("expr", "LK.TextGreen")), ("Blue1", ("expr", "LK.TextBlue")),
        ("VerticalJustificationNew", "3"), ("HorizontalJustificationNew", "3")])
    s_ = g.merge("SM1", "SHeading", "STitle")
    s_ = g.merge("SM2", s_, "SRuleBg")
    s_ = g.merge("SM3", s_, "SDetails")
    clock = clock_stack(g, 'Text(tostring(math.ceil(REM / FPS)))')
    s_ = g.merge("SM4", s_, clock, "iif(%s > 0.5, 1, 0)" % CLOCK)
    SLATEVIS = "(REM <= (%s + %s + %s) * FPS and REM > (%s + %s) * FPS)" % (S, GP, C, GP, C)
    top = g.merge("MSlate", top, s_, e("iif(%s, 1, 0)" % SLATEVIS))
    # countdown + 2-pop, sopra gli strumenti di taratura
    LEADVIS = "(%s > 0 and REM <= %s * FPS and (REM > 2 * FPS or (REM == 2 * FPS and %s > 0.5)))" % (C, C, POP)
    cal = calibration_stack(g)
    top = g.merge("MCal", top, cal, e("iif(LK.CalOn > 0.5 and %s, 1, 0)" % LEADVIS))
    lead = leader_stack(g, "L", 'Text(iif(REM < %s * FPS and REM >= 2 * FPS, tostring(math.ceil(REM / FPS)), ""))' % C,
                        sweep_vis="iif(REM < %s * FPS and REM > 2 * FPS, 1, 0)" % C, cd=C)
    top = g.merge("MLeader", top, lead, e("iif(%s, 1, 0)" % LEADVIS))
    g.text("PicStart", ("expr", 'Text("PICTURE\\nSTART")'), 0.075, spacing=1.0)
    top = g.merge("MPicStart", top, "PicStart", e("iif(%s > 0 and REM == %s * FPS, 1, 0)" % (C, C)))
    # frame lines e safe area
    guides = guides_stack(g)
    top = g.merge("MGuides", top, guides, e("iif(LK.Guides > 0.5 and (%s or (LK.GuidesSlate > 0.5 and %s)), 1, 0)"
                                            % (LEADVIS, SLATEVIS)))
    # sync flash
    g._add("Flash", "Background", G.CREATOR + [("TopLeftRed", "1.0"), ("TopLeftGreen", "1.0"),
                                               ("TopLeftBlue", "1.0"), ("TopLeftAlpha", "1.0")])
    top = g.merge("MFlash", top, "Flash", e("iif(%s > 0.5 and REM <= %s and REM > %s - %s, 1, 0)"
                                            % (FL_ON, SYNCREM, SYNCREM, SYNCFR)))
    # durata prima di Genera
    g.text("Warn", ("expr", e("Text(\"Premi GENERA nell'Inspector: il blocco diventa di \" .. %s .. \" secondi\")"
                              % HEADLEN)), 0.03, y=0.08, grey=1.0)
    top = g.merge("MWarn", top, "Warn",
                  e("iif(math.abs((comp.RenderEnd - comp.RenderStart + 1) - %s * FPS) > 0.5, 1, 0)" % HEADLEN))
    return group(family["name"], g, top, head_inputs(family, has_pop))


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
    std = load_standards()
    files = [("%s.setting" % f["name"], head(std, f)) for f in std["families"]]
    files.append(("LeaderKit Tail.setting", tail(std)))
    path = os.path.join(out, "LeaderKit-%s.drfx" % __version__)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in files:
            zf.writestr("Edit/Generators/LeaderKit/" + name, text)
            with open(os.path.join(out, name), "w") as fh:
                fh.write(text)
    return path


if __name__ == "__main__":
    print(build())
