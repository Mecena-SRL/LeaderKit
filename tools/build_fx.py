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

    def dissolve(self, name, bg, fg, mix):
        """Interruttore: con Mix 0 o 1 Fusion calcola solo l'ingresso attivo."""
        return self._add(name, "Dissolve", [("Background", ("link", bg, "Output")),
                                            ("Foreground", ("link", fg, "Output")), ("Mix", ("expr", mix))])

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


def uc_combo(name, label, items, on_change=None):
    opts = " ".join("{ CCS_AddString = %s }," % lua_string(i) for i in items)
    extra = ("INPS_ExecuteOnChange = %s, " % lua_string(on_change)) if on_change else ""
    return ("\t\t\t\t\t\t%s = { %s LINKID_DataType = \"Number\", INPID_InputControl = \"ComboControl\", "
            "CC_LabelPosition = \"Horizontal\", INP_Integer = true, %sLINKS_Name = %s, },\n"
            % (name, opts, extra, lua_string(label)))


def uc_file(name, label):
    """Campo percorso con pulsante Sfoglia (importazione del file)."""
    return ("\t\t\t\t\t\t%s = { LINKID_DataType = \"Text\", INPID_InputControl = \"FileControl\", "
            "FC_IsSaver = false, FC_ClipBrowse = false, "
            "FCS_FilterString = \"Immagini (*.png *.jpg *.tif *.tga *.exr *.dpx)|*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.tga;*.exr;*.dpx\", "
            "LINKS_Name = %s, },\n" % (name, lua_string(label)))


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
                  ("Accent", "Colore grafica leader", (0.85, 0.85, 0.85)),
                  ("Hi", "Colore evidenza (titoli di sezione)", (0.96, 0.74, 0.30))]


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


def uc_label(name, label, fold=0):
    """Intestazione di sezione; con fold > 0 diventa una sezione richiudibile di 'fold' voci."""
    drop = ("LBLC_DropDownButton = true, LBLC_NumInputs = %d, " % fold) if fold else "LBLC_DropDownButton = false, "
    return ("\t\t\t\t\t\t%s = { LINKID_DataType = \"Number\", INPID_InputControl = \"LabelControl\", "
            "%sINP_External = false, INP_Passive = true, LINKS_Name = %s, },\n"
            % (name, drop, lua_string(label)))


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
    g.mask(prefix + "LineV", "RectangleMask", repr(LINE_W), "1")
    g.background(prefix + "RingOBg", mask=prefix + "RingO", color="Accent")
    g.background(prefix + "RingIBg", mask=prefix + "RingI", color="Accent")
    g.background(prefix + "LineHBg", mask=prefix + "LineH", color="Accent", scale=0.7)
    g.background(prefix + "LineVBg", mask=prefix + "LineV", color="Accent", scale=0.7)
    top = g.merge(prefix + "M1", prefix + "RingOBg", prefix + "RingIBg")
    top = g.merge(prefix + "M2", top, prefix + "LineHBg")
    top = g.merge(prefix + "M3", top, prefix + "LineVBg")
    if sweep_vis:
        g.mask(prefix + "Arm", "RectangleMask", repr(LINE_W * 1.6), ("expr", e("%s * ASPECT" % r)),
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


def tables(std):
    """Tabelle comuni a grafica e motore: preset, categorie e slot."""
    presets = std["presets"]
    cats = [p.get("category", "custom") for p in presets]
    return presets, cats, std["slots"]


SLOT_INPUTS = [("cinema", "SlotCinema", "Slot cinema"), ("tv", "SlotTV", "Slot TV"),
               ("spot", "SlotSpot", "Slot spot"), ("streaming", "SlotStream", "Slot streaming")]
BREAKS = ["Nessuno", "Automatici (AVMSD: 1 ogni 30')", "1 break", "2 break", "3 break", "4 break", "5 break", "6 break"]


def engine(mode, std=None):
    std = std or load_standards()
    presets, cats, slots = tables(std)
    with open(os.path.join(ROOT, "fx", "engine.lua")) as fh:
        body = fh.read()
    with open(os.path.join(ROOT, "fx", "overlay.lua")) as fh:
        overlay = fh.read()
    return ('LK_MODE = "%s"\n' % mode
            + "LK_PRESETS = %s\n" % lua_literal(presets)
            + "LK_SLOTS = %s\n" % lua_literal(slots)
            + "LK_SLOT_INPUTS = %s\n" % lua_literal(dict((c, i) for c, i, _ in SLOT_INPUTS))
            + "LK_PARAMS = %s\n" % lua_literal(param_names())
            + "LK_FRAMELINES = %s\n" % lua_literal([[k, lab + ":1", ar, 1 if k in ("FL185", "FL239") else 0]
                                                          for k, lab, ar in FRAMELINES])
            + "LK_CALIBRATION = %s\n" % lua_literal([k for k, _, _ in CALIBRATION])
            + "LK_BURN_PHASES = %s\n" % lua_literal(burn_phase_table())
            + "LK_BURN_FIELDS = %s\n" % lua_literal([k for k, _ in BURN_FIELDS])
            + overlay + "\n"
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
    """Valore effettivo: dal preset, o dal pannello se lo standard e' personalizzato."""
    for k, inp in CUSTOM_FIELDS:
        if k == key:
            is_custom = pv(presets, "category", fn=lambda p: 1 if p.get("category") == "custom" else 0)
            return "iif(LK.Custom > 0.5 and %s > 0.5, LK.%s, %s)" % (is_custom, inp, pv(presets, key))
    return pv(presets, key)


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
CALIBRATION = [("CalStars", "Griglie di risoluzione 1-4 px (nitidezza, scalatura)", 1), ("CalCenter", "Mirino centrale", 1),
               ("CalGrey", "Scala di grigi", 1), ("CalColor", "Patch di colore RGBCMY", 1),
               ("CalRamps", "Rampe B/N, R, G, B", 1), ("CalBlue", "Verifica blu (filtro Wratten 47B)", 1),
               ("CalContour", "Sfera sfumata (contouring)", 1), ("CalPeak", "Bianco di picco e neri (PLUGE)", 1),
               ("CalLabels", "Etichette fps / risoluzione", 1)]
LOGO_POS = ["In alto a destra", "In alto a sinistra", "In basso a destra", "In basso a sinistra", "Al centro"]


def param_names():
    """Parametri del pannello da ricopiare quando Genera ricrea il blocco."""
    skip = ("Generate", "Remove", "Guide", "Duration", "Info", "ColorInfo", "DateToday")
    return [src for src, _ in head_inputs() if not src.startswith("Sec") and src not in skip]


def head_inputs():
    """(input, scheda) nell'ordine dell'Inspector."""
    prog = ["SecPreset", "Preset", "Reel", "DurSel", "SecSlots"] + [i for _, i, _ in SLOT_INPUTS] + [
        "ProgramTC", "Breaks", "MarkersOn", "MarkerEvery", "TailOn", "Generate", "Remove", "Guide", "Duration",
        "Info", "SecCustom", "Custom", "BarsSec", "SlateSec", "GapSec", "CountFrom", "TailSec"]
    out = [(x, "Progetto") for x in prog]
    out += [(f, "Produzione") for f, _, _ in PRODUCTION_FIELDS] + [("DateAuto", "Produzione"), ("DateToday", "Produzione")]
    out += [(f, "Post") for f, _, _ in POST_FIELDS] + [("Phase", "Post")]
    out += [(f, "Post") for f, _, _ in STATUSES] + [("Note", "Post")]
    out += [(x, "Tecnico") for x in ("SecGuides", "Guides", "GuidesSlate")] + [(f, "Tecnico") for f, _, _ in FRAMELINES]
    out += [(x, "Tecnico") for x in ("SafeAction", "SafeTitle", "SecTech", "ColorInfo", "AudioFormat",
                                     "SecAudio", "PopLevel", "BeepEach")]
    out += [("SecLook", "Aspetto")] + [(c, "Aspetto") for c in color_inputs()]
    out += [(x, "Aspetto") for x in ("SecLogo", "Logo", "LogoPos", "LogoSize", "Logo2", "LogoPos2", "LogoSize2",
                                     "LogoOnTail")]
    out += [("CalOn", "Taratura")] + [(f, "Taratura") for f, _, _ in CALIBRATION]
    return out


def visibility_script(std):
    """Lua eseguito quando cambiano standard o durata: mostra solo le voci pertinenti.

    Agisce sugli input del nodo LK e su quelli del gruppo (Inspector della pagina Edit).
    Se una versione di Resolve non lo supporta, le voci restano tutte visibili e il
    motore usa solo quelle pertinenti.
    """
    presets, cats, _ = tables(std)
    has_pop = [1 if (p.get("pop") or p.get("sync_flash")) else 0 for p in presets]
    index = dict((src, i) for i, (src, _) in enumerate(head_inputs(), 1))
    rules = {
        "Reel": 'cat == "cinema"',
        "SlotCinema": 'dur == 1 and cat == "cinema"', "SlotTV": 'dur == 1 and cat == "tv"',
        "SlotSpot": 'dur == 1 and cat == "spot"', "SlotStream": 'dur == 1 and cat == "streaming"',
        "SecSlots": "dur == 1", "ProgramTC": "dur == 2",
        "Breaks": 'cat == "tv" or cat == "streaming"',
        "MarkersOn": 'cat == "cinema" or cat == "custom"', "MarkerEvery": 'cat == "cinema" or cat == "custom"',
        "SecCustom": 'cat == "custom"', "Custom": 'cat == "custom"', "BarsSec": 'cat == "custom"',
        "SlateSec": 'cat == "custom"', "GapSec": 'cat == "custom"', "CountFrom": 'cat == "custom"',
        "TailSec": 'cat == "custom"', "PopLevel": "pop", "BeepEach": "pop",
    }
    lines = ["local t = tool",
             "if not t then return end",
             "local cats = %s" % lua_literal(cats),
             "local pops = %s" % lua_literal(has_pop),
             "local p = math.floor((t:GetInput('Preset') or 0) + 1.5)",
             "local cat = cats[p] or 'cinema'",
             "local pop = (pops[p] or 0) == 1",
             "local dur = math.floor((t:GetInput('DurSel') or 0) + 0.5)",
             "local grp = nil",
             "pcall(function() grp = t:GetAttrs().TOOLH_GroupParent end)",
             "local function vis(name, gin, on)",
             "  pcall(function() t[name]:SetAttrs({ INPB_IC_Visible = on }) end)",
             "  if grp then pcall(function() grp[gin]:SetAttrs({ INPB_IC_Visible = on }) end) end",
             "end"]
    for name, cond in rules.items():
        lines.append("vis(%s, %s, (%s) and true or false)" % (lua_string(name), lua_string("Input%d" % index[name]), cond))
    return "\n".join(lines)


TODAY = ('(function() local ok, d = pcall(function() return os.date("%d/%m/%Y") end); '
         'if ok and d then return d end; return "" end)()')


def slate_details():
    """Righe della slate: solo i campi compilati (+ dati tecnici calcolati)."""
    parts = []
    for f, _, lab in PRODUCTION_FIELDS + POST_FIELDS:
        if f == "Date":
            parts.append('iif(LK.DateAuto > 0.5, "DATE   " .. %s .. "\\n", '
                         'iif(LK.Date.Value == "", "", "DATE   " .. LK.Date.Value .. "\\n"))' % TODAY)
        elif lab:
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
        g.mask("Bar%dM" % i, "RectangleMask", repr(1 / 8.0 + 0.001), "1",
               center="{ %s, 0.5 }" % repr(cx))
        g._add("Bar%d" % i, "Background", G.CREATOR + [
            ("TopLeftRed", repr(float(rr))), ("TopLeftGreen", repr(float(gg))),
            ("TopLeftBlue", repr(float(bb))), ("TopLeftAlpha", "1.0"),
            ("EffectMask", ("link", "Bar%dM" % i, "Mask"))])
        top = "Bar%d" % i if top is None else g.merge("BarsM%d" % i, top, "Bar%d" % i)
    return top


def clock_stack(g, remaining_expr):
    """Orologio ident (DPP): cerchio, lancetta a scatti di 1\", secondi al FFOA."""
    cx, d = 0.92, 0.10
    r = d / 2.0
    g.mask("CkRing", "EllipseMask", repr(d), repr(d), center="{ %s, 0.11 }" % cx, border=repr(LINE_W * 1.6))
    g.background("CkRingBg", mask="CkRing", color="Accent")
    g.mask("CkArm", "RectangleMask", repr(LINE_W * 2), ("expr", e("%s * ASPECT" % (r * 0.9))),
           center=("expr", e("Point(%s, 0.11 + %s * ASPECT)" % (cx, r * 0.45))))
    g.background("CkArmBg", mask="CkArm", color="Accent")
    g._add("CkSweep", "Transform", [("Input", ("link", "CkArmBg", "Output")),
                                    ("Center", "{ %s, 0.11 }" % cx), ("Pivot", "{ %s, 0.11 }" % cx),
                                    ("Angle", ("expr", e("-6 * math.floor((REM - 1) / FPS)")))])
    top = g.merge("CkM1", "CkRingBg", "CkSweep")
    g._add("CkDigit", "TextPlus", G.CREATOR + [
        ("Center", "{ %s, 0.11 }" % cx), ("Font", '"Open Sans"'), ("Style", '"Bold"'), ("Size", "0.045"),
        ("StyledText", ("expr", e(remaining_expr))),
        ("Red1", ("expr", "LK.TextRed")), ("Green1", ("expr", "LK.TextGreen")), ("Blue1", ("expr", "LK.TextBlue")),
        ("VerticalJustificationNew", "3"), ("HorizontalJustificationNew", "3")])
    return g.merge("CkM2", top, "CkDigit")


# ------------------------------------------------------------------ slate a pannelli
# Ogni testo e' centrato nel suo punto (come negli slate generator piu' diffusi):
# nessuna dipendenza dall'allineamento a sinistra di Text+.
NARROW = "math.min(1, ASPECT / 1.6)"          # su 4:3 / verticale tutto si riduce


def cap_size(cap):
    """Size di Text+ per un'altezza delle maiuscole pari a 'cap' (frazione dell'altezza)."""
    return e("2 * (%s) / ASPECT * %s" % (cap, NARROW))


DATE_EXPR = 'iif(LK.DateAuto > 0.5, %s, LK.Date.Value)'


def slate_columns():
    phase = "({ %s })[math.floor(LK.Phase + 1.5)]" % ", ".join(lua_string(x) for x in PHASES)
    status = " .. ".join('iif(LK.%s < 0.5, "", "%s " .. ({ "-", "TEMP", "FINAL" })[math.floor(LK.%s + 1.5)] .. "  ")'
                         % (f, lab, f) for f, _, lab in STATUSES)
    prod = [("PRODUCTION", "LK.Production.Value"), ("PRODUCER", "LK.Producer.Value"),
            ("CLIENT", "LK.Client.Value"), ("AGENCY", "LK.Agency.Value"), ("CODE", "LK.Code.Value"),
            ("EPISODE / REEL", "LK.Episode.Value"), ("LANGUAGE", "LK.Language.Value"),
            ("DATE", DATE_EXPR % TODAY)]
    post = [("EDITOR", "LK.Editor.Value"), ("COLORIST", "LK.Colorist.Value"), ("SOUND", "LK.Sound.Value"),
            ("VFX", "LK.VFXBy.Value"), ("VERSION", "LK.Version.Value"),
            ("PHASE", 'iif(LK.Phase < 0.5, "", %s)' % phase), ("STATUS", "(%s)" % status)]
    tech = [("DURATION", "LK.Duration.Value"),
            ("FORMAT", 'comp:GetPrefs("Comp.FrameFormat.Width") .. " x " .. comp:GetPrefs("Comp.FrameFormat.Height") '
                       '.. "   " .. string.format("%.2f:1", comp:GetPrefs("Comp.FrameFormat.Width") / '
                       'comp:GetPrefs("Comp.FrameFormat.Height"))'),
            ("FRAME RATE", 'string.format("%g fps", comp:GetPrefs("Comp.FrameFormat.Rate"))'),
            ("COLOR", "LK.ColorInfo.Value"), ("AUDIO", "LK.AudioFormat.Value")]
    return [("PRODUCTION", 0.19, prod), ("POST", 0.5, post), ("TECHNICAL", 0.81, tech)]


def transparent(g, name):
    return g._add(name, "Background", G.CREATOR + [("TopLeftRed", "0"), ("TopLeftGreen", "0"),
                                                  ("TopLeftBlue", "0"), ("TopLeftAlpha", "0")])


def text_node(g, name, center, size, styled, rgb, style="Bold"):
    g._add(name, "TextPlus", G.CREATOR + [
        ("Center", ("expr", center)), ("Font", '"Open Sans"'), ("Style", lua_string(style)),
        ("Size", ("expr", size)), ("StyledText", ("expr", styled)),
        ("Red1", ("expr", rgb[0])), ("Green1", ("expr", rgb[1])), ("Blue1", ("expr", rgb[2])),
        ("VerticalJustificationNew", "3"), ("HorizontalJustificationNew", "3")])
    return name


def tint(prefix, k=1.0):
    return ["LK.%s%s * %s" % (prefix, ch, k) for ch in ("Red", "Green", "Blue")]


def slate_stack(g, P):
    heading = pv(P, "heading")
    static = pv(P, "slate_lines", fn=lambda p: "\\n".join(l for l in p.get("slate_lines", []) if "{" not in l))
    top = transparent(g, "SBase")
    # pannelli dietro alle colonne (sfondo leggermente piu' chiaro) con filo colorato in alto
    PY1 = 0.645
    rows = []
    for _, _, fields in slate_columns():
        cnt = " + ".join('iif((%s) ~= "", 1, 0)' % v for _, v in fields)
        rows.append("math.ceil((%s) / 2)" % cnt)
    bottom = "(0.54 - (math.max(1, %s) - 1) * 0.083 - 0.075)" % ", ".join(rows)
    for i, (_, cx, _) in enumerate(slate_columns()):
        g.mask("SPan%dM" % i, "RectangleMask", "0.295", ("expr", "%s - %s" % (PY1, bottom)),
               center=("expr", "Point(%s, (%s + %s) / 2)" % (cx, PY1, bottom)))
        g._add("SPan%d" % i, "Background", G.CREATOR + [
            ("TopLeftRed", ("expr", "math.min(1, LK.BgRed + 0.045)")),
            ("TopLeftGreen", ("expr", "math.min(1, LK.BgGreen + 0.045)")),
            ("TopLeftBlue", ("expr", "math.min(1, LK.BgBlue + 0.045)")), ("TopLeftAlpha", "1"),
            ("EffectMask", ("link", "SPan%dM" % i, "Mask"))])
        g.mask("SPanL%dM" % i, "RectangleMask", "0.295", repr(LINE_W), center="{ %s, %s }" % (cx, PY1))
        g.background("SPanL%d" % i, mask="SPanL%dM" % i, color="Hi")
        top = g.merge("SPM%d" % i, top, "SPan%d" % i)
        top = g.merge("SPL%d" % i, top, "SPanL%d" % i)
    # intestazione, titolo, regia, filo
    text_node(g, "SHeading", "Point(0.5, 0.925)", cap_size(0.016),
              'Text(%s .. "   ·   LEADERKIT")' % heading, tint("Hi"))
    top = g.merge("SMH", top, "SHeading")
    title_size = e("math.min(2 * 0.068 / ASPECT * %s, 1.9 / math.max(1, string.len(LK.Title.Value)))" % NARROW)
    text_node(g, "STitle", "Point(0.5, 0.815)", title_size, "Text(string.upper(LK.Title.Value))", tint("Text"))
    top = g.merge("SMT", top, "STitle")
    text_node(g, "SDirector", "Point(0.5, 0.735)", cap_size(0.024),
              'Text(iif(LK.Director.Value == "", "", "DIRECTED BY   " .. string.upper(LK.Director.Value)))',
              tint("Text", 0.9), style="Regular")
    top = g.merge("SMD", top, "SDirector")
    g.mask("SRule", "RectangleMask", "0.18", repr(LINE_W * 1.2), center="{ 0.5, 0.69 }")
    g.background("SRuleBg", mask="SRule", color="Hi")
    top = g.merge("SMR", top, "SRuleBg")
    # colonne: intestazione + campi impacchettati in 2 sotto-colonne (i campi vuoti non lasciano buchi)
    for ci, (title, cx, fields) in enumerate(slate_columns()):
        text_node(g, "SCol%d" % ci, "Point(%s, 0.605)" % cx, cap_size(0.015), 'Text("%s")' % title, tint("Hi"))
        top = g.merge("SMC%d" % ci, top, "SCol%d" % ci)
        vals = ["(%s)" % v for _, v in fields]
        count = " + ".join('iif(%s ~= "", 1, 0)' % v for v in vals)
        for fi, (label, v) in enumerate(fields):
            k = " + ".join(['0'] + ['iif(%s ~= "", 1, 0)' % x for x in vals[:fi]])
            # ultimo campo di un numero dispari: centrato nella colonna
            x = ("iif(((%s) %% 2 == 0) and ((%s) == (%s) - 1), %s, %s + iif((%s) %% 2 == 0, -0.072, 0.072))"
                 % (k, k, count, cx, cx, k))
            y = "0.54 - math.floor((%s) / 2) * 0.083" % k
            lab = text_node(g, "SL%d_%d" % (ci, fi), "Point(%s, %s)" % (x, y), cap_size(0.0115),
                            'Text(iif(%s == "", "", "%s"))' % (v, label), tint("Text", 0.5))
            val = text_node(g, "SV%d_%d" % (ci, fi), "Point(%s, %s - 0.033)" % (x, y),
                            e("2 * 0.019 / ASPECT * %s * math.min(1, 9.3 * ASPECT / math.max(1, string.len(%s)))" % (NARROW, v)),
                            "Text(%s)" % v, tint("Text"), style="Semibold")
            top = g.merge("SML%d_%d" % (ci, fi), top, lab)
            top = g.merge("SMV%d_%d" % (ci, fi), top, val)
    # piede: timecode calcolati, righe fisse dello standard, note
    text_node(g, "SFoot", "Point(0.5, math.max(0.07, %s - 0.075))" % bottom, cap_size(0.015),
              'Text(LK.Info.Value .. iif(%s == "", "", "\\n" .. %s) .. iif(LK.Note.Value == "", "", "\\n" .. LK.Note.Value))'
              % (static, static), tint("Text", 0.75), style="Regular")
    top = g.merge("SMF", top, "SFoot")
    return top


def head(std=None):
    std = std or load_standards()
    P, CATS, SLOTS = tables(std)
    B, S, GP, C = (field(P, "bars"), field(P, "slate"), field(P, "gap"), field(P, "countdown"))
    CLOCK = pv(P, "clock")
    POP = pv(P, "pop")
    FL_ON = pv(P, "sync_flash", fn=lambda p: 1 if p.get("sync_flash") else 0)
    FL_BEFORE = pv(P, "sync_flash", fn=lambda p: (p.get("sync_flash") or {}).get("before_s", 0))
    FL_FR = pv(P, "sync_flash", fn=lambda p: (p.get("sync_flash") or {}).get("frames_at_25", 0))
    HEADLEN = "(%s + %s + %s + %s)" % (B, S, GP, C)
    SYNCREM = "math.floor(%s * FPS + 0.5)" % FL_BEFORE
    SYNCFR = "math.max(1, math.floor(%s * FPS / 25 + 0.5))" % FL_FR
    vis = visibility_script(std)

    # --- controlli, per scheda
    prog = (uc_label("SecPreset", "LeaderKit %s" % __version__)
            + uc_combo("Preset", "Standard", [p["name"] for p in P], on_change=vis)
            + uc_slider("Reel", "Rullo (cinema: FFOA a N:00:08:00)", 1, 23, 1)
            + uc_combo("DurSel", "Durata programma", ["Libera (fine dei tuoi clip)", "Slot dello standard",
                                                     "Personalizzata"], on_change=vis)
            + uc_label("SecSlots", "Slot (si usa quello della categoria dello standard)", fold=len(SLOT_INPUTS)))
    for cat, inp, label in SLOT_INPUTS:
        prog += uc_combo(inp, label, [x[0] for x in SLOTS[cat]])
    prog += (uc_text("ProgramTC", "Durata personalizzata (HH:MM:SS:FF)")
             + uc_combo("Breaks", "Break pubblicitari (TV)", BREAKS)
             + uc_check("MarkersOn", "Marker di fine rullo", 1)
             + uc_slider("MarkerEvery", "Rullo ogni (minuti, 0 = dallo standard)", 0, 60, 0, integer=False)
             + uc_check("TailOn", "Inserisci la coda", 1)
             + uc_button("Generate", "Genera sulla timeline", engine("generate", std))
             + uc_button("Remove", "Rimuovi elementi generati", engine("remove", std))
             + uc_text("Guide", "Guida timecode", lines=6, read_only=True)
             + uc_text("Duration", "Durata programma (calcolata)", read_only=True)
             + uc_text("Info", "Timecode (calcolati)", lines=2, read_only=True)
             + uc_label("SecCustom", "Durate del leader (solo standard Personalizzato)", fold=6)
             + uc_check("Custom", "Personalizza le durate", 0)
             + uc_slider("BarsSec", "Barre (s)", 0, 60, 0) + uc_slider("SlateSec", "Slate (s)", 0, 30, 8)
             + uc_slider("GapSec", "Nero prima del programma (s)", 0, 10, 2)
             + uc_slider("CountFrom", "Countdown da (0 = nessuno)", 0, 11, 8)
             + uc_slider("TailSec", "Coda (s)", 0, 30, 8))
    today_code = ('pcall(function() tool:SetInput("Date", os.date("%d/%m/%Y")) end)')
    prod = "".join(uc_text(f, label) for f, label, _ in PRODUCTION_FIELDS)
    prod += (uc_check("DateAuto", "Data sempre aggiornata (data del render)", 1)
             + uc_button("DateToday", "Oggi", today_code))
    post = "".join(uc_text(f, label) for f, label, _ in POST_FIELDS)
    post += uc_combo("Phase", "Fase di lavorazione", PHASES)
    post += "".join(uc_combo(f, label, STATUS_VALUES) for f, label, _ in STATUSES)
    post += uc_text("Note", "Note (riga libera)")
    tech = (uc_label("SecGuides", "Frame lines e safe area (immagine creata da Genera, sul countdown)")
            + uc_check("Guides", "Mostra le frame lines", 1) + uc_check("GuidesSlate", "Anche sulla slate", 0)
            + "".join(uc_check(f, "Frame line " + lab + ":1", 1 if f in ("FL185", "FL239") else 0) for f, lab, _ in FRAMELINES)
            + uc_check("SafeAction", "Safe action 93% (EBU R95)", 0) + uc_check("SafeTitle", "Safe graphics 90%", 0)
            + uc_label("SecTech", "Dati tecnici")
            + uc_text("ColorInfo", "Spazio colore (letto da Genera)", read_only=True)
            + uc_text("AudioFormat", "Formato audio (es. 5.1 + stereo, 24 bit 48 kHz)")
            + uc_label("SecAudio", "Audio (tono 1 kHz)")
            + uc_combo("PopLevel", "Livello pop", ["Dallo standard", "-20 dBFS (SMPTE / USA)", "-18 dBFS (EBU / Europa)"])
            + uc_check("BeepEach", "Bip anche su 8..3 (non standard)", 0))
    look = (uc_label("SecLook", "Colori") + color_controls()
            + uc_label("SecLogo", "Logo (inserito da Genera sopra la slate, traccia LeaderKit Logo)")
            + uc_file("Logo", "File del logo")
            + uc_combo("LogoPos", "Posizione", LOGO_POS)
            + uc_slider("LogoSize", "Dimensione (%)", 5, 100, 12, integer=False)
            + uc_file("Logo2", "Secondo logo (cliente, distributore...)")
            + uc_combo("LogoPos2", "Posizione del secondo logo", LOGO_POS)
            + uc_slider("LogoSize2", "Dimensione del secondo logo (%)", 5, 100, 12, integer=False)
            + uc_check("LogoOnTail", "Anche sulla coda", 0))
    cal = (uc_check("CalOn", "Strumenti di taratura sul countdown (immagine creata da Genera)", 1)
           + "".join(uc_check(f, label, d) for f, label, d in CALIBRATION))
    uc = (on_page("Progetto", prog) + on_page("Produzione", prod) + on_page("Post", post)
          + on_page("Tecnico", tech) + on_page("Aspetto", look) + on_page("Taratura", cal))

    values = [("Preset", "0"), ("Reel", "1"), ("DurSel", "0"), ("ProgramTC", '"00:00:30:00"'), ("Breaks", "0"),
              ("Custom", "0"), ("BarsSec", "0"), ("SlateSec", "8"), ("GapSec", "2"), ("CountFrom", "8"),
              ("TailSec", "8"), ("MarkersOn", "1"), ("MarkerEvery", "0"), ("TailOn", "1"),
              ("Guide", '"Metti il blocco dove inizia il leader (anche a timeline vuota) e premi Genera"'),
              ("Duration", '"premi Genera"'), ("Info", '""'), ("Title", '"TITOLO"'), ("Version", '"v1"'),
              ("DateAuto", "1"), ("Phase", "0"), ("Note", '""'), ("Guides", "1"), ("GuidesSlate", "0"),
              ("SafeAction", "0"), ("SafeTitle", "0"), ("ColorInfo", '""'), ("AudioFormat", '""'),
              ("PopLevel", "0"), ("BeepEach", "0"), ("Logo", '""'), ("LogoPos", "0"), ("LogoSize", "12"),
              ("Logo2", '""'), ("LogoPos2", "1"), ("LogoSize2", "12"),
              ("LogoOnTail", "0"), ("CalOn", "1")]
    values += [(i, str(std.get("slot_defaults", {}).get(c, 0))) for c, i, _ in SLOT_INPUTS]
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
    g.merge("BarsFull", "Bg", bars)
    top = g.dissolve("MBars", "Bg", "BarsFull", e("iif(REM > (%s + %s + %s) * FPS, 1, 0)" % (S, GP, C)))
    # slate: titolo grande, regia, tre pannelli (produzione / lavorazione / tecnico), piede con i timecode
    s_ = slate_stack(g, P)
    clock = clock_stack(g, 'Text(tostring(math.ceil(REM / FPS)))')
    s_ = g.merge("SM4", s_, clock, "iif(%s > 0.5, 1, 0)" % CLOCK)
    SLATEVIS = "(REM <= (%s + %s + %s) * FPS and REM > (%s + %s) * FPS)" % (S, GP, C, GP, C)
    g.merge("SlateFull", "Bg", s_)
    top = g.dissolve("MSlate", top, "SlateFull", e("iif(%s, 1, 0)" % SLATEVIS))
    # countdown + 2-pop, sopra gli strumenti di taratura
    LEADVIS = "(%s > 0 and REM <= %s * FPS and (REM > 2 * FPS or (REM == 2 * FPS and %s > 0.5)))" % (C, C, POP)
    lead = leader_stack(g, "L", 'Text(iif(REM < %s * FPS and REM >= 2 * FPS, tostring(math.ceil(REM / FPS)), ""))' % C,
                        sweep_vis="iif(REM < %s * FPS and REM > 2 * FPS, 1, 0)" % C, cd=C)
    g.merge("LeadFull", "Bg", lead)
    top = g.dissolve("MLeader", top, "LeadFull", e("iif(%s, 1, 0)" % LEADVIS))
    g.text("PicStart", ("expr", 'Text("PICTURE\\nSTART")'), 0.075, spacing=1.0)
    top = g.merge("MPicStart", top, "PicStart", e("iif(%s > 0 and REM == %s * FPS, 1, 0)" % (C, C)))
    g._add("Flash", "Background", G.CREATOR + [("TopLeftRed", "1.0"), ("TopLeftGreen", "1.0"),
                                               ("TopLeftBlue", "1.0"), ("TopLeftAlpha", "1.0")])
    top = g.merge("MFlash", top, "Flash", e("iif(%s > 0.5 and REM <= %s and REM > %s - %s, 1, 0)"
                                            % (FL_ON, SYNCREM, SYNCREM, SYNCFR)))
    g.text("Warn", ("expr", e("Text(\"Premi GENERA nell'Inspector: il blocco diventa di \" .. %s .. \" secondi\")"
                              % HEADLEN)), 0.03, y=0.08, grey=1.0)
    top = g.merge("MWarn", top, "Warn",
                  e("iif(math.abs((comp.RenderEnd - comp.RenderStart + 1) - %s * FPS) > 0.5, 1, 0)" % HEADLEN))
    return group("LeaderKit", g, top, head_inputs())


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


# ------------------------------------------------------------------ burn-in (copie di lavoro)
BURN_NAME = "LeaderKit Burn-in"
BURN_FIELDS = [("BRec", "Record TC (timeline)"), ("BSrc", "Source TC (clip)"),
               ("BAtc", "TC audio e sound roll (verifica sync)"), ("BFrame", "Contatore fotogrammi"),
               ("BClip", "Nome clip"), ("BScene", "Scena / shot / take"), ("BCam", "Camera"),
               ("BReel", "Reel / roll / card"), ("BDate", "Data (ripresa, o oggi)"), ("BTitle", "Titolo / produzione"),
               ("BVersion", "Versione / fase"), ("BColor", "Spazio colore / LUT"), ("BFormat", "Formato (fps, risoluzione)"),
               ("BWater", "Watermark al centro"), ("BBig", "Record TC grande (suono / VO / doppiaggio)")]
FRAME_MODES = ["Per clip da 1001 (VFX)", "Per clip da 0", "Programma da 0"]
# fase: (nome, campi attivi, modo contatore)
BURN_PHASES = [
    ("Scarico / verifica DIT", ["BSrc", "BClip", "BReel", "BCam", "BDate", "BFormat", "BColor"], 1),
    ("Sync audio-video", ["BSrc", "BAtc", "BClip", "BScene", "BCam", "BReel"], 1),
    ("Giornalieri (produzione / regia)", ["BSrc", "BClip", "BScene", "BCam", "BReel", "BDate", "BTitle", "BWater"], 1),
    ("Montaggio / offline review", ["BRec", "BSrc", "BClip", "BTitle", "BVersion", "BDate", "BWater"], 2),
    ("VFX (pull / review)", ["BSrc", "BFrame", "BClip", "BReel", "BVersion", "BFormat"], 0),
    ("Color review", ["BRec", "BSrc", "BClip", "BVersion", "BColor", "BFormat"], 2),
    ("Suono / mix / VO / doppiaggio", ["BRec", "BBig", "BFrame", "BTitle", "BVersion"], 2),
    ("Approvazione cliente", ["BRec", "BTitle", "BVersion", "BDate", "BWater"], 2),
    ("Personalizzato (scegli i campi)", None, None),
]
BURN_POS = ["Nelle bande (del mascherino, o bande proprie)", "Dentro l'immagine (safe 90%)"]
MATTES = [("Nessuno (formato nativo)", 0), ("1.33:1 (4:3)", 4.0 / 3.0), ("1.37:1 (Academy)", 1.37),
          ("1.43:1 (IMAX)", 1.43), ("1.66:1", 1.66), ("1.78:1 (16:9)", 16.0 / 9.0), ("1.85:1 (Flat)", 1.85),
          ("1.90:1 (IMAX digitale / DCI full)", 1.9), ("2.00:1 (Univisium)", 2.0), ("2.20:1 (70 mm)", 2.2),
          ("2.35:1", 2.35), ("2.39:1 (Scope)", 2.39), ("2.76:1 (Ultra Panavision 70)", 2.76),
          ("Personalizzato (slider)", -1)]


def burn_phase_table():
    """Per il motore: fase -> { campi = {...}, frame = modo } (nil per Personalizzato)."""
    out = []
    for _, fields, fm in BURN_PHASES:
        out.append(None if fields is None else {"fields": fields, "frame": fm})
    return out


def burn_phase_script():
    """Cambiando la fase si impostano le spunte dei campi (poi modificabili)."""
    lines = ["local t = tool", "if not t then return end",
             "local p = math.floor((t:GetInput('BPhase') or 0) + 1.5)",
             "local phases = %s" % lua_literal([[f for f in (fields or [])] if fields is not None else False
                                                for _, fields, _ in BURN_PHASES]),
             "local modes = %s" % lua_literal([fm if fm is not None else -1 for _, _, fm in BURN_PHASES]),
             "local on = phases[p]",
             "if not on then return end",
             "local set = {}",
             "for _, k in ipairs(on) do set[k] = true end",
             "for _, k in ipairs(%s) do pcall(function() t:SetInput(k, set[k] and 1 or 0) end) end"
             % lua_literal([k for k, _ in BURN_FIELDS]),
             "pcall(function() t:SetInput('BFrameMode', modes[p]) end)"]
    return "\n".join(lines)


CAP = "(LK.BSize * 0.01)"
MR = ("iif(math.floor(LK.BMatte + 0.5) == %d, LK.BMatteRatio, (({ %s })[math.floor(LK.BMatte + 1.5)] or 0))"
      % (len(MATTES) - 1, ", ".join(repr(max(r, 0)) for _, r in MATTES)))
LB = "iif(%s > ASPECT + 0.01, (1 - ASPECT / %s) / 2, 0)" % (MR, MR)          # bande del letterbox
PB = "iif(%s > 0 and %s < ASPECT - 0.01, (1 - %s / ASPECT) / 2, 0)" % (MR, MR, MR)   # bande laterali
IN_MATTE = "(%s >= 3.2 * %s)" % (LB, CAP)                                   # il testo sta nel mascherino
BAND = "iif(LK.BPos > 0.5, 0, iif(%s, %s, 4.6 * %s))" % (IN_MATTE, LB, CAP)


def burn_lookup(corner, line):
    """Espressione: riga 'line' dell'angolo 'corner' per il fotogramma corrente.

    LK.Seg contiene una riga per segmento:
    rec_da|rec_a|src|passo|fps_src|drop_src|audio|contatore|TL|TR|BL|BR
    con i segnaposto {REC} {SRC} {ATC} {FRM} calcolati qui a ogni fotogramma."""
    return (
        "(function() "
        "local function tc(f, n, d) f = math.floor(f + 0.5); if f < 0 then return '--:--:--:--' end; "
        "if d > 0 then local p10, pm = n * 600 - d * 9, n * 60 - d; local q, m = math.floor(f / p10), f %% p10; "
        "if m > d then f = f + d * 9 * q + d * math.floor((m - d) / pm) else f = f + d * 9 * q end end; "
        "return string.format('%%02d:%%02d:%%02d%%s%%02d', math.floor(f / (n * 3600)), math.floor(f / (n * 60)) %% 60, "
        "math.floor(f / n) %% 60, d > 0 and ';' or ':', f %% n) end; "
        "local rec = LK.RecStart + (time - comp.RenderStart); "
        "local tn, td = math.max(1, LK.TlFps), LK.TlDrop; "
        "for l in string.gmatch(LK.Seg.Value, '[^\\n]+') do "
        "local a, b, sv, st, sn, sd, au, fr, t1, t2, t3, t4 = string.match(l, "
        "'^(%%-?%%d+)|(%%-?%%d+)|(%%-?[%%d%%.]+)|([%%d%%.]+)|(%%d+)|(%%d+)|(%%-?%%d+)|(%%-?%%d+)|([^|]*)|([^|]*)|([^|]*)|([^|]*)$'); "
        "a, b = a and (a + 0), b and (b + 0); "
        "if a and rec >= a and rec < b then "
        "local e = rec - a; "
        "local txt = ({ t1, t2, t3, t4 })[%d] or ''; "
        "local parts = {}; for x in string.gmatch(txt .. '~', '([^~]*)~') do parts[#parts + 1] = x end; "
        "txt = parts[%d] or ''; "
        "txt = string.gsub(txt, '{REC}', tc(rec, tn, td)); "
        "txt = string.gsub(txt, '{SRC}', tc((sv + 0) < 0 and -1 or (sv + 0) + e * (st + 0), (sn + 0), (sd + 0))); "
        "txt = string.gsub(txt, '{ATC}', tc((au + 0) < 0 and -1 or (au + 0) + e, tn, td)); "
        "txt = string.gsub(txt, '{FRM}', tostring(fr + e)); "
        "return txt end end; return '' end)()" % (corner, line))


def burnin(std=None):
    g = G()
    phase_script = burn_phase_script()
    main = (uc_label("SecBurn", "LeaderKit Burn-in %s" % __version__)
            + uc_combo("BPhase", "Fase di lavoro", [x[0] for x in BURN_PHASES], on_change=phase_script)
            + uc_button("BUpdate", "Aggiorna dai metadati", engine("burnin", std))
            + uc_text("BInfo", "Esito", lines=4, read_only=True)
            + uc_text("BTitleText", "Titolo / produzione (vuoto = dalla slate)")
            + uc_text("BVersionText", "Versione / fase")
            + uc_text("BWaterText", "Watermark")
            + uc_text("BRecipient", "Destinatario (screener)"))
    fields = ("".join(uc_check(k, label, 0) for k, label in BURN_FIELDS)
              + uc_combo("BFrameMode", "Contatore fotogrammi", FRAME_MODES))
    look = (uc_combo("BMatte", "Mascherino (su timeline di lavoro 16:9)", [m for m, _ in MATTES])
            + uc_slider("BMatteRatio", "Rapporto personalizzato (x:1)", 1, 3, 2.39, integer=False)
            + uc_slider("BMatteAlpha", "Opacita' del mascherino", 0, 1, 1, integer=False)
            + uc_combo("BPos", "Posizione dei dati", BURN_POS)
            + uc_slider("BSize", "Altezza testo (% del quadro)", 1, 5, 1.8, integer=False)
            + uc_slider("BBandAlpha", "Opacita' delle bande", 0, 1, 0.75, integer=False)
            + uc_slider("BWaterAlpha", "Opacita' watermark", 0, 1, 0.18, integer=False)
            + uc_text("Seg", "Dati dei clip (da Aggiorna)", lines=2, read_only=True))
    uc = on_page("Burn-in", main) + on_page("Campi", fields) + on_page("Aspetto", look)
    d = dict((k, 0) for k, _ in BURN_FIELDS)
    for k in BURN_PHASES[2][1]:
        d[k] = 1
    values = [("BPhase", "2"), ("BTitleText", '""'), ("BVersionText", '""'), ("BWaterText", '"CONFIDENZIALE"'),
              ("BRecipient", '""'), ("BInfo", '"Metti il clip sopra il montato (V3/V4) e premi Aggiorna"'),
              ("BFrameMode", "1"), ("BPos", "0"), ("BMatte", "0"), ("BMatteRatio", "2.39"), ("BMatteAlpha", "1"), ("BSize", "1.8"), ("BBandAlpha", "0.75"), ("BWaterAlpha", "0.18"),
              ("Seg", '""'), ("RecStart", "0"), ("TlFps", "24"), ("TlDrop", "0")]
    values += [(k, str(v)) for k, v in d.items()]
    uc += ("\t\t\t\t\t\tRecStart = { LINKID_DataType = \"Number\", INPID_InputControl = \"SliderControl\", "
           "INP_Integer = true, INP_External = false, IC_Visible = false, LINKS_Name = \"RecStart\", },\n"
           "\t\t\t\t\t\tTlFps = { LINKID_DataType = \"Number\", INPID_InputControl = \"SliderControl\", "
           "INP_Integer = true, INP_External = false, IC_Visible = false, LINKS_Name = \"TlFps\", },\n"
           "\t\t\t\t\t\tTlDrop = { LINKID_DataType = \"Number\", INPID_InputControl = \"SliderControl\", "
           "INP_Integer = true, INP_External = false, IC_Visible = false, LINKS_Name = \"TlDrop\", },\n")
    g.controls(values, uc)
    g._add("Bg", "Background", G.CREATOR + [("TopLeftRed", "0"), ("TopLeftGreen", "0"), ("TopLeftBlue", "0"),
                                             ("TopLeftAlpha", "0")])
    band = e(BAND)
    lb, pb = e(LB), e(PB)
    # mascherino: bande sopra/sotto (letterbox) o ai lati (pillarbox), opache
    for nm, w, h, c in (("MatT", "1.02", lb, "Point(0.5, 1 - (%s) / 2)" % lb), ("MatB", "1.02", lb, "Point(0.5, (%s) / 2)" % lb),
                        ("MatL", pb, "1.02", "Point((%s) / 2, 0.5)" % pb), ("MatR", pb, "1.02", "Point(1 - (%s) / 2, 0.5)" % pb)):
        g.mask(nm + "M", "RectangleMask", ("expr", w) if w != "1.02" else w, ("expr", h) if h != "1.02" else h,
               center=("expr", c))
        g._add(nm, "Background", G.CREATOR + [("TopLeftRed", "0"), ("TopLeftGreen", "0"), ("TopLeftBlue", "0"),
                                              ("TopLeftAlpha", ("expr", "LK.BMatteAlpha")),
                                              ("EffectMask", ("link", nm + "M", "Mask"))])
    top = "Bg"
    for i, nm in enumerate(("MatT", "MatB", "MatL", "MatR")):
        top = g.merge("MM%d" % i, top, nm)
    # bande proprie semitrasparenti quando il mascherino non c'e' (o e' troppo sottile)
    own = e("iif(LK.BPos < 0.5 and not %s, LK.BBandAlpha, 0)" % IN_MATTE)
    for nm, cy in (("BandT", "1 - (%s) / 2" % band), ("BandB", "(%s) / 2" % band)):
        g.mask(nm + "M", "RectangleMask", "1.02", ("expr", band), center=("expr", "Point(0.5, %s)" % cy))
        g._add(nm, "Background", G.CREATOR + [("TopLeftRed", "0"), ("TopLeftGreen", "0"), ("TopLeftBlue", "0"),
                                              ("TopLeftAlpha", ("expr", own)),
                                              ("EffectMask", ("link", nm + "M", "Mask"))])
    top = g.merge("MB1", top, "BandT")
    top = g.merge("MB2", top, "BandB")
    size = e("2 * %s / ASPECT" % CAP)
    half = "0.9 * %s" % CAP
    # angoli: 1 alto-sx, 2 alto-dx, 3 basso-sx, 4 basso-dx; due righe centrate nella loro cella
    for corner, (hx, vy) in enumerate([(-1, -1), (1, -1), (-1, 1), (1, 1)], 1):
        for line in (1, 2):
            x = "0.2" if hx < 0 else "0.8"
            sign = "+" if line == 1 else "-"
            if vy < 0:
                y = e("iif(LK.BPos > 0.5, 0.93 %s %s, 1 - (%s) / 2 %s %s)" % (sign, half, BAND, sign, half))
            else:
                y = e("iif(LK.BPos > 0.5, 0.07 %s %s, (%s) / 2 %s %s)" % (sign, half, BAND, sign, half))
            nm = "T%d%d" % (corner, line)
            g._add(nm, "TextPlus", G.CREATOR + [
                ("Center", ("expr", "Point(%s, %s)" % (x, y))), ("Font", '"Open Sans"'), ("Style", '"Bold"'),
                ("Size", ("expr", size)), ("StyledText", ("expr", "Text(%s)" % burn_lookup(corner, line))),
                ("Red1", "1"), ("Green1", "1"), ("Blue1", "1"),
                ("VerticalJustificationNew", "3"), ("HorizontalJustificationNew", "3")])
            top = g.merge("M" + nm, top, nm)
    # record TC grande (in basso al centro)
    g._add("Big", "TextPlus", G.CREATOR + [
        ("Center", ("expr", e("Point(0.5, iif(LK.BPos > 0.5, 0.15, (%s) + 0.055))" % BAND))),
        ("Font", '"Open Sans"'), ("Style", '"Bold"'), ("Size", ("expr", e("5 * %s / ASPECT" % CAP))),
        ("StyledText", ("expr", "Text(%s)" % burn_lookup(4, 3))),
        ("Red1", "1"), ("Green1", "1"), ("Blue1", "1"),
        ("VerticalJustificationNew", "3"), ("HorizontalJustificationNew", "3")])
    top = g.merge("MBig", top, "Big", "iif(LK.BBig > 0.5, 1, 0)")
    g._add("Water", "TextPlus", G.CREATOR + [
        ("Center", "{ 0.5, 0.5 }"), ("Font", '"Open Sans"'), ("Style", '"Bold"'), ("Size", "0.06"),
        ("StyledText", ("expr", 'Text(string.upper(LK.BWaterText.Value) .. iif(LK.BRecipient.Value == "", "", "\\n" .. LK.BRecipient.Value))')),
        ("Red1", "1"), ("Green1", "1"), ("Blue1", "1"),
        ("VerticalJustificationNew", "3"), ("HorizontalJustificationNew", "3")])
    top = g.merge("MWater", top, "Water", "iif(LK.BWater > 0.5, LK.BWaterAlpha, 0)")
    inputs = ([(x, "Burn-in") for x in ("SecBurn", "BPhase", "BUpdate", "BInfo", "BTitleText", "BVersionText",
                                        "BWaterText", "BRecipient")]
              + [(k, "Campi") for k, _ in BURN_FIELDS] + [("BFrameMode", "Campi")]
              + [(x, "Aspetto") for x in ("BMatte", "BMatteRatio", "BMatteAlpha", "BPos", "BSize", "BBandAlpha", "BWaterAlpha", "Seg")])
    return group(BURN_NAME, g, top, inputs)


def build():
    out = os.path.join(ROOT, "dist")
    os.makedirs(out, exist_ok=True)
    std = load_standards()
    files = [("LeaderKit.setting", head(std)), ("LeaderKit Tail.setting", tail(std)),
             ("LeaderKit Burn-in.setting", burnin(std))]
    path = os.path.join(out, "LeaderKit-%s.drfx" % __version__)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, text in files:
            zf.writestr("Edit/Generators/LeaderKit/" + name, text)
            with open(os.path.join(out, name), "w") as fh:
                fh.write(text)
    return path




if __name__ == "__main__":
    print(build())
