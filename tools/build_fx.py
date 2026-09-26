#!/usr/bin/env python3
"""Build di LeaderKit come generatori Fusion (Edit > Generators > LeaderKit).

    python3 tools/build_fx.py   ->  dist/LeaderKit-<versione>.drfx

* LeaderKit (head): barre, slate, countdown e 2-pop in un solo clip. La fine del
  clip e' il FFOA; tutto e' calcolato a ogni fotogramma dal frame rate e dalla
  risoluzione della timeline. Parametri e bottoni nell'Inspector.
* LeaderKit Tail: tail pop + END OF PROGRAM; inserita dal bottone "Genera".
* LeaderKit Burn-in: dati dei clip sulle copie di lavoro.

Convenzioni verificate in Resolve 21 (probe): GroupOperator, nodo Custom
"LK" come pannello di controllo, testi letti con .Value, espressioni con
comp:GetPrefs / comp.RenderStart / comp.RenderEnd / time.

Prestazioni: Fusion calcola solo i rami richiesti. Ogni elemento facoltativo
passa da un "gate" (Dissolve con Mix 0/1: con 0 il ramo non viene calcolato),
i testi sono raccolti in pochi Text+ a piu' righe e le forme dello stesso
colore usano un solo Background con le maschere in catena.
"""

import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from leaderkit import __version__  # noqa: E402
from leaderkit.fusion import lua_string  # noqa: E402

RING_D = 0.36
LINE_W = 0.0025

# ------------------------------------------------------------------ espressioni
# Segnaposto usabili nelle espressioni: diventano variabili locali calcolate una
# sola volta per espressione (comp:GetPrefs e' lento, prima veniva chiamato ~1000
# volte per fotogramma).
_TOKENS = [
    ("_FPS", 'local _FPS = math.floor(comp:GetPrefs("Comp.FrameFormat.Rate") + 0.5)', ()),
    ("_REM", "local _REM = comp.RenderEnd - time + 1", ()),              # fotogrammi al FFOA (1 = ultimo)
    ("_EL", "local _EL = time - comp.RenderStart", ()),                  # fotogrammi dall'inizio del clip
    ("_W", 'local _W = comp:GetPrefs("Comp.FrameFormat.Width")', ()),
    ("_H", 'local _H = comp:GetPrefs("Comp.FrameFormat.Height")', ()),
    ("_A", "local _A = _W / _H", ("_W", "_H")),
    ("_N", "local _N = math.min(1, _A / 1.6)", ("_A",)),                # su 4:3 / verticale tutto si riduce
]


def _uses(code, tok):
    return re.search(r"(?<![\w.])%s(?!\w)" % tok, code) is not None


def ex(body, pre=""):
    """Espressione Fusion. 'pre' = istruzioni Lua eseguite prima di 'return body'."""
    code = pre + " " + body
    need = set()
    for tok, _, deps in reversed(_TOKENS):
        if tok in need or _uses(code, tok):
            need.add(tok)
            need.update(deps)
    decl = [d for tok, d, _ in _TOKENS if tok in need]
    if not decl and not pre.strip():
        return body
    return "(function() %s %s return %s end)()" % (" ".join(decl), pre, body)


def X(body, pre=""):
    return ("expr", ex(body, pre))


def _v(x):
    """Valore di un input: tupla (expr/link), numero letterale o espressione Lua."""
    if isinstance(x, tuple):
        return x
    try:
        float(x)
        return x
    except ValueError:
        return ("expr", x)


def tint(prefix, k=1.0):
    return ["LK.%s%s * %s" % (prefix, ch, k) for ch in ("Red", "Green", "Blue")]


class G(object):
    """Grafo di un generatore: nodi come testo Lua."""

    CREATOR = [("GlobalOut", "100000"), ("Width", "1920"), ("Height", "1080"),
               ("UseFrameFormatSettings", "1"), ("Depth", "1")]          # 8 bit: grafica, basta e avanza

    def __init__(self):
        self.tools = []
        self.kinds = {}
        self.x = 0

    def _add(self, name, reg, inputs, extra=""):
        assert name not in self.kinds, name
        self.kinds[name] = reg
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

    def background(self, name, color=None, scale=1.0, rgb=None, alpha="1", mask=None):
        if rgb is None:
            rgb = tint(color, scale) if color else ["0", "0", "0"]
        ins = self.CREATOR + [("TopLeftRed", _v(rgb[0])), ("TopLeftGreen", _v(rgb[1])),
                              ("TopLeftBlue", _v(rgb[2])), ("TopLeftAlpha", _v(alpha))]
        if mask:
            ins.append(("EffectMask", ("link", mask, "Mask")))
        return self._add(name, "Background", ins)

    def mask(self, name, kind, width, height, center=None, border=None, chain=None, level=None):
        """Maschera; 'chain' = maschera precedente (unione): tante forme, un solo Background."""
        ins = [("Filter", 'FuID { "Fast Gaussian" }'), ("SoftEdge", "0"),
               ("MaskWidth", "1920"), ("MaskHeight", "1080"), ("PixelAspect", "{ 1, 1 }"),
               ("UseFrameFormatSettings", "1"), ("ClippingMode", 'FuID { "None" }'),
               ("Width", _v(width)), ("Height", _v(height))]
        if center:
            ins.append(("Center", _v(center)))
        if border:
            ins += [("Solid", "0"), ("BorderWidth", _v(border))]
        if level:
            ins.append(("Level", _v(level)))
        if chain:
            ins.append(("EffectMask", ("link", chain, "Mask")))
        return self._add(name, kind, ins)

    def text(self, name, center, size, styled, rgb, style="Bold", align="c", spacing=None):
        """Text+; align: "c" centro, "l" ancorato a sinistra, "r" a destra, oppure (anchor, justify) in Lua."""
        ins = self.CREATOR + [
            ("Center", _v(center)), ("Font", '"Open Sans"'), ("Style", lua_string(style)),
            ("Size", _v(size)), ("StyledText", _v(styled)),
            ("Red1", _v(rgb[0])), ("Green1", _v(rgb[1])), ("Blue1", _v(rgb[2])),
            ("VerticalJustificationNew", "3")]
        if align == "l":
            ins += [("HorizontalLeftCenterRight", "-1"), ("HorizontalJustificationNew", "0")]
        elif align == "r":
            ins += [("HorizontalLeftCenterRight", "1"), ("HorizontalJustificationNew", "1")]
        elif isinstance(align, tuple):
            ins += [("HorizontalLeftCenterRight", _v(align[0])), ("HorizontalJustificationNew", _v(align[1]))]
        else:
            ins.append(("HorizontalJustificationNew", "3"))
        if spacing:
            ins.append(("LineSpacing", repr(spacing)))
        return self._add(name, "TextPlus", ins)

    def merge(self, name, bg, fg, center=None, size=None):
        ins = [("Background", ("link", bg, "Output")), ("Foreground", ("link", fg, "Output")),
               ("PerformDepthMerge", "0")]
        if center:
            ins.append(("Center", _v(center)))
        if size:
            ins.append(("Size", _v(size)))
        return self._add(name, "Merge", ins)

    def chain(self, name, nodes):
        """Testi uno sull'altro (l'area calcolata e' solo quella dei testi); ritorna il nodo in cima."""
        top = nodes[0]
        for i, n in enumerate(nodes[1:], 1):
            top = self.merge("%s%d" % (name, i), top, n)
        return top

    def dissolve(self, name, bg, fg, mix):
        """Interruttore: con Mix 0 o 1 Fusion calcola solo l'ingresso attivo."""
        return self._add(name, "Dissolve", [("Background", ("link", bg, "Output")),
                                            ("Foreground", ("link", fg, "Output")), ("Mix", _v(mix))])

    def gate(self, name, bg, layers, cond, mix="1"):
        """Livelli sopra 'bg' solo quando 'cond' e' vera: altrimenti non vengono calcolati.
        layers: nomi di nodi o (nodo, center, size) per posizionare un'immagine (loghi)."""
        top = bg
        for i, lay in enumerate(layers, 1):
            node, center, size = lay if isinstance(lay, tuple) else (lay, None, None)
            top = self.merge("%sM%d" % (name, i), top, node, center, size)
        return self.dissolve(name, bg, top, ex("((%s) and (%s) or 0)" % (cond, mix)))

    def transform(self, name, src, angle, pivot=None):
        ins = [("Input", ("link", src, "Output"))]
        if pivot:
            ins.append(("Pivot", pivot))
        ins.append(("Angle", _v(angle)))
        return self._add(name, "Transform", ins)

    def loader(self, name):
        """Immagine scelta dall'utente: il file viene impostato da script (Scegli... / Genera)."""
        return self._add(name, "Loader", [], "\t\t\t\t\tClips = { },\n")

    def controls(self, values, user_controls):
        return self._add("LK", "Custom", list(values),
                         "\t\t\t\t\tUserControls = ordered() {\n%s\t\t\t\t\t},\n" % user_controls)


# ------------------------------------------------------------------ controlli dell'Inspector
def uc_text(name, label, lines=1, read_only=False, on_change=None):
    extra = ("INPS_ExecuteOnChange = %s, " % lua_string(on_change)) if on_change else ""
    return ("\t\t\t\t\t\t%s = { LINKID_DataType = \"Text\", INPID_InputControl = \"TextEditControl\", "
            "TEC_Lines = %d, TEC_Wrap = true, TEC_ReadOnly = %s, %sLINKS_Name = %s, },\n"
            % (name, lines, "true" if read_only else "false", extra, lua_string(label)))


def uc_hidden(name, kind="Number"):
    """Input di servizio (scritto da Genera / Aggiorna / Scegli), mai mostrato."""
    ctl = "TextEditControl" if kind == "Text" else "SliderControl"
    return ("\t\t\t\t\t\t%s = { LINKID_DataType = \"%s\", INPID_InputControl = \"%s\", INP_External = false, "
            "IC_Visible = false, LINKS_Name = %s, },\n" % (name, kind, ctl, lua_string(name)))


def uc_combo(name, label, items, on_change=None):
    opts = " ".join("{ CCS_AddString = %s }," % lua_string(i) for i in items)
    extra = ("INPS_ExecuteOnChange = %s, " % lua_string(on_change)) if on_change else ""
    return ("\t\t\t\t\t\t%s = { %s LINKID_DataType = \"Number\", INPID_InputControl = \"ComboControl\", "
            "CC_LabelPosition = \"Horizontal\", INP_Integer = true, %sLINKS_Name = %s, },\n"
            % (name, opts, extra, lua_string(label)))


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


COLOR_DEFAULTS = [("Text", "Testo", (1.0, 1.0, 1.0)), ("Bg", "Sfondo", (0.0, 0.0, 0.0)),
                  ("Accent", "Grafica del leader", (0.85, 0.85, 0.85)),
                  ("Hi", "Evidenza (titoli di sezione)", (0.96, 0.74, 0.30))]
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


def on_page(page, controls_text):
    """Mette i controlli (testo UserControls) nella scheda indicata."""
    return re.sub(r"LINKS_Name = ", 'ICS_ControlPage = %s, LINKS_Name = ' % lua_string(page), controls_text)


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


# ------------------------------------------------------------------ standard e motore
STANDARDS = os.path.join(ROOT, "fx", "standards.json")


def load_standards():
    import json
    with open(STANDARDS, encoding="utf-8") as fh:
        return json.load(fh)


def tables(std):
    """Tabelle comuni a grafica e motore: preset, categorie e slot."""
    presets = std["presets"]
    cats = [p.get("category", "custom") for p in presets]
    return presets, cats, std["slots"]


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


def fx_source(name):
    with open(os.path.join(ROOT, "fx", name), encoding="utf-8") as fh:
        return fh.read()


SLOT_INPUTS = [("cinema", "SlotCinema", "Slot cinema"), ("tv", "SlotTV", "Slot TV"),
               ("spot", "SlotSpot", "Slot spot"), ("streaming", "SlotStream", "Slot streaming")]
BREAKS = ["Nessuno", "Automatici (AVMSD: 1 ogni 30')", "1 break", "2 break", "3 break", "4 break", "5 break", "6 break"]


def engine(mode, std=None):
    """Script di un bottone: parte comune + moduli che servono al modo (Rimuovi resta piccolo)."""
    std = std or load_standards()
    presets, cats, slots = tables(std)
    head = 'LK_MODE = "%s"\n' % mode
    body = fx_source("engine_common.lua")
    libs = ""
    if mode in ("generate", "burnin"):
        head += ("LK_BURN_PHASES = %s\n" % lua_literal(burn_phase_table())
                 + "LK_BURN_FIELDS = %s\n" % lua_literal([k for k, _ in BURN_FIELDS]))
        body += "\n" + fx_source("engine_burnin.lua")
    if mode == "generate":
        head += ("LK_PRESETS = %s\n" % lua_literal(presets)
                 + "LK_SLOTS = %s\n" % lua_literal(slots)
                 + "LK_SLOT_INPUTS = %s\n" % lua_literal(dict((c, i) for c, i, _ in SLOT_INPUTS))
                 + "LK_PARAMS = %s\n" % lua_literal(param_names())
                 + "LK_CALIBRATION = %s\n" % lua_literal([k for k, _, _ in CALIBRATION])
                 + "LK_DIALS = %s\n" % lua_literal({"b": list(DIAL_B), "c": list(DIAL_C)}))
        libs = fx_source("overlay.lua") + "\n" + fx_source("image.lua") + "\n"
        body += "\n" + fx_source("engine.lua")
    return (head + libs
            + "local function __leaderkit_main()\n" + body + "\nend\n"
            + "local __ok, __err = xpcall(__leaderkit_main, debug and debug.traceback or tostring)\n"
            + "if not __ok then\n"
            + "  print('[LeaderKit] ERRORE: ' .. tostring(__err))\n"
            + "  pcall(function() local cc = comp or fusion:GetCurrentComp(); cc:AskUser('LeaderKit - errore', "
            + "{ { 'Errore', 'Text', Default = tostring(__err), Lines = 14, Wrap = true } }) end)\n"
            + "end\n")


# immagini dentro i generatori: (campo, bottone Scegli, Loader, larghezza, altezza, nome)
IMAGES = [("Logo", "LogoPick", "Logo1Ld", "LogoW", "LogoH", "Logo"),
          ("Logo2", "Logo2Pick", "Logo2Ld", "Logo2W", "Logo2H", "Secondo logo"),
          ("TitleImage", "TitlePick", "TitleLd", "TitleW", "TitleH", "Titolo in PNG")]


def image_script(key, call):
    """Script per 'Scegli...' (call = pick) o per il cambio del campo (call = sync)."""
    _, _, ld, wk, hk, label = [im for im in IMAGES if im[0] == key][0]
    args = ", ".join(lua_string(x) for x in (key, ld, wk, hk))
    tail = (", %s" % lua_string(label)) if call == "pick" else ""
    return (fx_source("image.lua")
            + "\npcall(function() LK_IMAGE.%s(comp or fusion:GetCurrentComp(), tool, %s%s) end)\n" % (call, args, tail))


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
            return "((LK.Custom > 0.5 and %s > 0.5) and LK.%s or %s)" % (is_custom, inp, pv(presets, key))
    return pv(presets, key)


PAGES = ["Progetto", "Dati", "Aspetto", "Guide", "Tecnico"]

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
SAFE_AREAS = [("SafeAction", 0.93, "SAFE ACTION 93%"), ("SafeTitle", 0.90, "SAFE TITLE 90%")]
GUIDE_KEYS = ["FLTL"] + [k for k, _, _ in FRAMELINES] + [k for k, _, _ in SAFE_AREAS]
CALIBRATION = [("CalStars", "Griglie di risoluzione 1-4 px (nitidezza, scalatura)", 1), ("CalCenter", "Mirino centrale", 1),
               ("CalGrey", "Scala di grigi", 1), ("CalColor", "Patch di colore RGBCMY", 1),
               ("CalRamps", "Rampe B/N, R, G, B", 1), ("CalBlue", "Verifica blu (filtro Wratten 47B)", 1),
               ("CalContour", "Sfera sfumata (contouring)", 1), ("CalPeak", "Bianco di picco e neri (PLUGE)", 1),
               ("CalLabels", "Etichette fps / risoluzione", 1)]
LOGO_POS = ["In alto a destra", "In alto a sinistra", "In basso a destra", "In basso a sinistra", "Al centro"]
END_DOT_POS = ["In alto a destra (cue mark)", "Al centro", "In alto a sinistra"]
HIDDEN_NUM = ["LogoW", "LogoH", "Logo2W", "Logo2H", "TitleW", "TitleH"]


def param_names():
    """Parametri del pannello da ricopiare quando Genera ricrea il blocco."""
    skip = ("Generate", "Remove", "Guide", "Duration", "Info", "ColorInfo", "DateToday",
            "LogoPick", "Logo2Pick", "TitlePick")
    return [src for src, _ in head_inputs() if not src.startswith("Sec") and src not in skip]


def head_inputs():
    """(input, scheda) nell'ordine dell'Inspector."""
    prog = ["SecPreset", "Preset", "Reel", "DurSel", "SecSlots"] + [i for _, i, _ in SLOT_INPUTS] + [
        "ProgramTC", "Breaks", "MarkersOn", "MarkerEvery", "TailOn", "Generate", "Remove", "Guide", "Duration",
        "Info", "SecCustom", "Custom", "BarsSec", "SlateSec", "GapSec", "CountFrom", "TailSec"]
    out = [(x, "Progetto") for x in prog]
    data = (["SecProd"] + [f for f, _, _ in PRODUCTION_FIELDS] + ["DateAuto", "DateToday", "SecPost"]
            + [f for f, _, _ in POST_FIELDS] + ["Phase"] + [f for f, _, _ in STATUSES] + ["Note"])
    out += [(x, "Dati") for x in data]
    look = (["SecStyle", "SlateStyle", "TitleImage", "TitlePick", "TitleImageSize",
             "SecLogo", "Logo", "LogoPick", "LogoPos", "LogoSize", "Logo2", "Logo2Pick", "LogoPos2", "LogoSize2",
             "LogoOnTail", "SecLook"] + color_inputs())
    out += [(x, "Aspetto") for x in look]
    guides = (["SecGuides", "GuidesSlate", "GuidesCd", "FLTL"] + [f for f, _, _ in FRAMELINES]
              + [k for k, _, _ in SAFE_AREAS] + ["SecEnd", "EndDot", "EndDotPos", "EndDotSize"])
    out += [(x, "Guide") for x in guides]
    tech = (["SecTech", "ColorInfo", "AudioFormat", "SecAudio", "PopLevel", "BeepEach", "SecCal", "CalOn"]
            + [f for f, _, _ in CALIBRATION])
    out += [(x, "Tecnico") for x in tech]
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
DATE_EXPR = '(LK.DateAuto > 0.5 and %s or LK.Date.Value)'
NO_TITLE_IMG = '(LK.TitleImage.Value == "" or LK.TitleW < 1)'
PHASE_EXPR = "({ %s })[math.floor(LK.Phase + 1.5)]" % ", ".join(lua_string(x) for x in PHASES)


def cap_size(cap):
    """Size di Text+ per un'altezza delle maiuscole pari a 'cap' (frazione dell'altezza)."""
    return "2 * (%s) / _A * _N" % cap


def status_expr():
    return "(%s)" % " .. ".join('(LK.%s < 0.5 and "" or ("%s " .. ({ "-", "TEMP", "FINAL" })[math.floor(LK.%s + 1.5)] .. "   "))'
                                 % (f, lab, f) for f, _, lab in STATUSES)


ANY_STATUS = "(%s)" % " or ".join("LK.%s > 0.5" % f for f, _, _ in STATUSES)
STATIC_LINES = None      # righe fisse della slate dello standard (impostate in head())


def slate_columns():
    prod = [("COMPANY", "LK.Production.Value"), ("PRODUCER", "LK.Producer.Value"),
            ("CLIENT", "LK.Client.Value"), ("AGENCY", "LK.Agency.Value"), ("CODE", "LK.Code.Value"),
            ("EPISODE / REEL", "LK.Episode.Value"), ("LANGUAGE", "LK.Language.Value"),
            ("DATE", DATE_EXPR % TODAY)]
    post = [("EDITOR", "LK.Editor.Value"), ("COLORIST", "LK.Colorist.Value"), ("SOUND", "LK.Sound.Value"),
            ("VFX", "LK.VFXBy.Value"), ("VERSION", "LK.Version.Value"),
            ("PHASE", '(LK.Phase < 0.5 and "" or %s)' % PHASE_EXPR)]
    tech = [("DURATION", "LK.Duration.Value"),
            ("FORMAT", 'string.format("%d × %d   %.2f:1", _W, _H, _A)'),
            ("FRAME RATE", 'string.format("%g fps", comp:GetPrefs("Comp.FrameFormat.Rate"))'),
            ("COLOR", "LK.ColorInfo.Value"), ("AUDIO", "LK.AudioFormat.Value")]
    return [("PRODUCTION", 0.19, prod), ("POST", 0.5, post), ("TECHNICAL", 0.81, tech)]


def info_groups():
    cols = slate_columns()
    prod, post, tech = [c[2] for c in cols]
    first = [("DIRECTOR", "LK.Director.Value")] + [f for f in prod if f[0] != "DATE"]
    return [first, post + [("STATUS", status_expr())], tech + [("DATE", DATE_EXPR % TODAY)], [("NOTE", "LK.Note.Value")]]


def info_fn(maxlines=16):
    """Lua: local function INFO() -> { s = righe 'ETICHETTA   valore', n = numero di righe }."""
    adds = []
    for grp in info_groups():
        adds += ["a(%s, %s)" % (lua_string(lab), v) for lab, v in grp] + ["pend = true"]
    return ("local function INFO() local s, n, pend = '', 0, false "
            "local function a(l, v) v = tostring(v or '') if v ~= '' and n < %d then "
            "if pend and n > 0 then s = s .. '\\n' n = n + 1 end pend = false "
            "s = s .. (n > 0 and '\\n' or '') .. l .. '   ' .. v n = n + 1 end end "
            "%s return { s = s, n = n } end " % (maxlines, " ".join(adds)))


def cols_fn():
    """Lua: local function COLS() -> colonne { l = etichette, v = valori, n = righe }, valore piu' lungo."""
    parts = []
    for _, _, fields in slate_columns():
        parts.append("col({ %s })" % ", ".join("{ %s, %s }" % (lua_string(lab), v) for lab, v in fields))
    return ("local function COLS() local ml = 1 "
            "local function col(list) local l, v, n = '', '', 0 "
            "for i = 1, #list do local x = tostring(list[i][2] or '') if x ~= '' then n = n + 1 "
            "l = l .. (n > 1 and '\\n' or '') .. list[i][1] v = v .. (n > 1 and '\\n' or '') .. x "
            "if string.len(x) > ml then ml = string.len(x) end end end return { l = l, v = v, n = n } end "
            "return { %s }, ml end " % ", ".join(parts))


# ------------------------------------------------------------------ elementi grafici
def bars_stack(g):
    """Barre 100% a pieno raster (DPP: bianco, giallo, ciano, verde, magenta, rosso, blu, nero)."""
    colors = [(1, 1, 0), (0, 1, 1), (0, 1, 0), (1, 0, 1), (1, 0, 0), (0, 0, 1), (0, 0, 0)]
    top = g.background("Bar0", rgb=["1", "1", "1"])
    for i, (rr, gg, bb) in enumerate(colors, 1):
        cx = (i + 0.5) / 8.0
        g.mask("Bar%dM" % i, "RectangleMask", repr(1 / 8.0 + 0.001), "1", center="{ %s, 0.5 }" % repr(cx))
        g.background("Bar%d" % i, rgb=[repr(float(rr)), repr(float(gg)), repr(float(bb))], mask="Bar%dM" % i)
        top = g.merge("BarsM%d" % i, top, "Bar%d" % i)
    return top


def leader_stack(g, prefix, base, digit_expr, sweep_vis=None, cd=None):
    """Cerchi e croce (un solo Background), braccio rotante e cifra centrale sopra 'base'."""
    r = RING_D / 2.0
    g.mask(prefix + "RingO", "EllipseMask", repr(RING_D), repr(RING_D), border=repr(LINE_W * 1.6))
    g.mask(prefix + "RingI", "EllipseMask", repr(RING_D * 0.86), repr(RING_D * 0.86), border=repr(LINE_W),
           chain=prefix + "RingO")
    g.mask(prefix + "LineH", "RectangleMask", "1", X("%s * _A" % LINE_W), chain=prefix + "RingI")
    g.mask(prefix + "LineV", "RectangleMask", repr(LINE_W), "1", chain=prefix + "LineH")
    g.background(prefix + "Rings", color="Accent", mask=prefix + "LineV")
    top = g.merge(prefix + "M1", base, prefix + "Rings")
    if sweep_vis:
        g.mask(prefix + "Arm", "RectangleMask", repr(LINE_W * 1.6), X("%s * _A" % r),
               center=X("Point(0.5, 0.5 + %s * _A)" % (r / 2.0)))
        g.background(prefix + "ArmBg", color="Accent", mask=prefix + "Arm")
        g.transform(prefix + "Sweep", prefix + "ArmBg", ex("-360 * math.fmod((%s) * _FPS - _REM, _FPS) / _FPS" % cd))
        top = g.gate(prefix + "ArmG", top, [prefix + "Sweep"], sweep_vis)
    g.text(prefix + "Digit", "{ 0.5, 0.5 }", "0.30", X(digit_expr), tint("Text"))
    return g.merge(prefix + "M5", top, prefix + "Digit")


def clock_layers(g):
    """Orologio ident (DPP): cerchio, lancetta a scatti di 1\", secondi al FFOA."""
    cx, d = 0.92, 0.10
    r = d / 2.0
    g.mask("CkRing", "EllipseMask", repr(d), repr(d), center="{ %s, 0.11 }" % cx, border=repr(LINE_W * 1.6))
    g.background("CkRingBg", color="Accent", mask="CkRing")
    g.mask("CkArm", "RectangleMask", repr(LINE_W * 2), X("%s * _A" % (r * 0.9)),
           center=X("Point(%s, 0.11 + %s * _A)" % (cx, r * 0.45)))
    g.background("CkArmBg", color="Accent", mask="CkArm")
    g.transform("CkSweep", "CkArmBg", ex("-6 * math.floor((_REM - 1) / _FPS)"), pivot="{ %s, 0.11 }" % cx)
    g.text("CkDigit", "{ %s, 0.11 }" % cx, "0.045", X("Text(tostring(math.ceil(_REM / _FPS)))"), tint("Text"))
    return ["CkRingBg", "CkSweep", "CkDigit"]


def hand(g, name, cx, cy, r0, r1, width, angle, color="Hi"):
    """Lancetta da r0 a r1 (frazioni dell'altezza) sopra il centro (cx, cy), ruotata di 'angle' gradi."""
    g.mask(name + "M", "RectangleMask", repr(width), repr(r1 - r0), center="{ %s, %s }" % (cx, cy + (r0 + r1) / 2))
    g.background(name + "Bg", color=color, mask=name + "M")
    return g.transform(name, name + "Bg", ex(angle), pivot="{ %s, %s }" % (cx, cy))


def status_chips(g, prefix, y, pre=""):
    """Stato dei reparti: COLOR · FINAL (verde) / TEMP (colore evidenza), affiancati e centrati."""
    n = " + ".join("(LK.%s > 0.5 and 1 or 0)" % f for f, _, _ in STATUSES)
    nodes = []
    for i, (f, _, lab) in enumerate(STATUSES):
        k = " + ".join(["0"] + ["(LK.%s > 0.5 and 1 or 0)" % x for x, _, _ in STATUSES[:i]])
        fin = "LK.%s > 1.5" % f
        rgb = ["((%s) and 0.40 or LK.HiRed)" % fin, "((%s) and 0.85 or LK.HiGreen)" % fin,
               "((%s) and 0.45 or LK.HiBlue)" % fin]
        nodes.append(g.text("%s%d" % (prefix, i),
                            X("Point(0.5 + ((%s) - ((%s) - 1) / 2) * 0.135, %s)" % (k, n, y), pre),
                            X(cap_size(0.0135)),
                            ex('Text(LK.%s > 0.5 and ("%s  ·  " .. ({ "-", "TEMP", "FINAL" })[math.floor(LK.%s + 1.5)]) or "")'
                               % (f, lab, f)), rgb))
    return g.chain(prefix + "C", nodes)


def footer_text(static):
    return 'Text(LK.Info.Value .. ((%s) == "" and "" or ("\\n" .. %s)))' % (static, static)


# ------------------------------------------------------------------ stili della slate
SLATE_STYLES = ["Pannelli (produzione / post / tecnico)", "Quadrante (fotogrammi, dati a destra)",
                "Orologio (titolo e dati a destra)", "Minimale (titolo al centro)"]
# riquadro del titolo in PNG per stile: (x, y, larghezza, altezza, ancora) in frazioni del quadro;
# ancora "center" = x e' il centro, "left" = x e' il bordo sinistro.
TITLE_BOXES = [(0.5, 0.815, 0.60, 0.11, "center"), (0.53, 0.845, 0.42, 0.10, "left"),
               (0.58, 0.80, 0.38, 0.16, "left"), (0.5, 0.60, 0.70, 0.18, "center")]
DIAL_B = (0.27, 0.5, 0.36)         # quadrante: centro x (W), centro y (H), raggio (H)
DIAL_C = (0.28, 0.5, 0.31)         # orologio

PANEL_W = 0.295
PANEL_TOP = 0.645
T_CAP = 0.0145                     # altezza delle maiuscole nelle tabelle dei pannelli
LABEL_COL = 0.108                  # larghezza della colonna etichette (frazione della larghezza)


def slate_panels(g, P, base, static):
    """Pannelli: titolo, regia, tre pannelli (produzione / post / tecnico) come tabelle
    etichetta-valore (2 Text+ per pannello), stato dei reparti e piede con i timecode."""
    heading = pv(P, "heading")
    cols = slate_columns()
    # capienza in caratteri della colonna valori, poi riduzione (mai sotto il 70%) se un valore e' lungo
    capw = (PANEL_W - 0.032 - LABEL_COL) * 0.714 / (0.55 * T_CAP)
    geo = (cols_fn() + "local C, ml = COLS() "
           "local f = math.min(1, math.max(0.7, %s * _A / _N / ml)) "
           "local cap = %s * _N * f local pitch = 1.9 * cap "
           "local ty = %s - 0.062 "
           "local bottom = ty - math.max(1, C[1].n, C[2].n, C[3].n) * pitch - 0.03 "
           % (repr(capw), T_CAP, PANEL_TOP))
    fill, line = None, None
    for i, (_, cx, _) in enumerate(cols):
        fill = g.mask("SPan%dM" % i, "RectangleMask", repr(PANEL_W), X("%s - bottom" % PANEL_TOP, geo),
                      center=X("Point(%s, (%s + bottom) / 2)" % (cx, PANEL_TOP), geo), chain=fill)
        line = g.mask("SPanL%dM" % i, "RectangleMask", repr(PANEL_W), repr(LINE_W),
                      center="{ %s, %s }" % (cx, PANEL_TOP), chain=line)
    line = g.mask("SRuleM", "RectangleMask", "0.18", repr(LINE_W * 1.2), center="{ 0.5, 0.69 }", chain=line)
    g.background("SPanFill", rgb=["math.min(1, LK.BgRed + 0.045)", "math.min(1, LK.BgGreen + 0.045)",
                                  "math.min(1, LK.BgBlue + 0.045)"], mask=fill)
    g.background("SAccent", color="Hi", mask=line)
    top = g.merge("SMP", base, "SPanFill")
    top = g.merge("SMA", top, "SAccent")
    # intestazione, titolo, regia
    g.text("SHeading", "{ 0.5, 0.925 }", X(cap_size(0.016)), ex('Text(%s .. "   ·   LEADERKIT")' % heading), tint("Hi"))
    title_size = X("math.min(2 * 0.068 / _A * _N, 1.9 / math.max(1, string.len(LK.Title.Value)))")
    g.text("STitle", "{ 0.5, 0.815 }", title_size,
           ex('Text(%s and string.upper(LK.Title.Value) or "")' % NO_TITLE_IMG), tint("Text"))
    g.text("SDirector", "{ 0.5, 0.735 }", X(cap_size(0.024)),
           ex('Text(LK.Director.Value == "" and "" or ("DIRECTED BY   " .. string.upper(LK.Director.Value)))'),
           tint("Text", 0.9), style="Regular")
    top = g.merge("SMH", top, g.chain("SHd", ["SHeading", "STitle", "SDirector"]))
    # colonne: intestazione, etichette e valori allineati riga per riga (solo i campi compilati)
    for i, (title, cx, _) in enumerate(cols):
        xl = cx - PANEL_W / 2 + 0.016
        g.text("SCol%d" % i, "{ %s, %s }" % (xl, PANEL_TOP - 0.032), X(cap_size(0.0125)), 'Text("%s")' % title,
               tint("Hi"), align="l")
        block_y = "ty - C[%d].n * pitch / 2" % (i + 1)
        g.text("SLab%d" % i, X("Point(%s, %s)" % (xl, block_y), geo), X("2 * cap / _A", geo),
               ex("Text(C[%d].l)" % (i + 1), geo), tint("Text", 0.55), style="Regular", align="l")
        g.text("SVal%d" % i, X("Point(%s, %s)" % (xl + LABEL_COL, block_y), geo), X("2 * cap / _A", geo),
               ex("Text(C[%d].v)" % (i + 1), geo), tint("Text"), style="Semibold", align="l")
        top = g.merge("SMC%d" % i, top, g.chain("SCo%d" % i, ["SCol%d" % i, "SLab%d" % i, "SVal%d" % i]))
    # stato dei reparti sotto i pannelli, poi il piede
    top = g.merge("SMS", top, status_chips(g, "SSt", "bottom - 0.05", geo))
    g.text("SFoot", X("Point(0.5, math.max(0.05, bottom - (%s and 0.13 or 0.075)))" % ANY_STATUS, geo),
           X(cap_size(0.015)),
           ex('Text(LK.Info.Value .. ((%s) == "" and "" or ("\\n" .. %s)) .. (LK.Note.Value == "" and "" or ("\\n" .. LK.Note.Value)))'
              % (static, static)), tint("Text", 0.75), style="Regular")
    return g.merge("SMF", top, "SFoot")


def info_block(g, name, x, y0, cap, ymin):
    """Lista dei dati (una riga per campo compilato) in un solo Text+ allineato a sinistra, tra y0
    (prima riga) e ymin: con molti campi il testo si riduce per restarci."""
    pre = info_fn(28) + ("local I = INFO() local c = math.min(%s * _N, (%s - %s) / (1.9 * math.max(0, I.n - 1) + 1)) "
                         % (cap, y0, ymin))
    return g.text(name, X("Point(%s, %s - (I.n - 1) * 1.9 * c / 2)" % (x, y0), pre),
                  X("2 * c / _A", pre), ex("Text(I.s)", pre), tint("Text", 0.92), style="Regular", align="l")


def common_footer(g, name, static):
    return g.text(name, "{ 0.5, 0.07 }", X(cap_size(0.0135)), ex(footer_text(static)), tint("Text", 0.7),
                  style="Regular")


def slate_style_b(g, P, base, static):
    """Quadrante: a sinistra il quadrante dei fotogrammi del secondo (disegnato da Genera in PNG)
    con la tacca che gira; a destra titolo, dati e fotogrammi al FFOA."""
    cx, cy, r = DIAL_B
    top = g.merge("BMh", base, hand(g, "BHand", cx, cy, r * 0.66, r * 0.785, 0.007,
                                    "-360 * (_FPS - 1 - ((_REM - 1) % _FPS)) / _FPS"))
    g.text("BSec", "{ %s, %s }" % (cx, cy + 0.03), X(cap_size(0.16)), ex("Text(tostring(math.ceil(_REM / _FPS)))"),
           tint("Text"))
    g.text("BFps", "{ %s, %s }" % (cx, cy - 0.17), X(cap_size(0.022)),
           'Text(string.format("SEC / %g FPS", comp:GetPrefs("Comp.FrameFormat.Rate")))', tint("Text", 0.8))
    x = 0.53
    g.text("BTitle", "{ %s, 0.845 }" % x,
           X("math.min(2 * 0.05 / _A * _N, 0.8 / math.max(1, string.len(LK.Title.Value)))"),
           ex('Text(%s and string.upper(LK.Title.Value) or "")' % NO_TITLE_IMG), tint("Text"), align="l")
    g.text("BHead", "{ %s, 0.765 }" % x, X(cap_size(0.016)), "Text(%s)" % pv(P, "heading"), tint("Hi"), align="l")
    info_block(g, "BInfo", x, "0.70", 0.0175, "0.19")
    g.text("BFrames", "{ %s, 0.125 }" % x, X(cap_size(0.062)), ex("Text(tostring(_REM))"), tint("Text", 0.85),
           style="Light", align="l")
    g.text("BFramesL", "{ %s, 0.058 }" % x, X(cap_size(0.016)), 'Text("frames to FFOA")', tint("Text", 0.6),
           style="Regular", align="l")
    common_footer(g, "Foot1", static)
    return g.merge("BMt", top, g.chain("BTx", ["BSec", "BFps", "BTitle", "BHead", "BInfo", "BFrames", "BFramesL",
                                               "Foot1"]))


def slate_style_c(g, P, base, static):
    """Orologio: cerchio con lancetta dei secondi al FFOA (tacche disegnate da Genera in PNG);
    a destra titolo (testo o PNG), intestazione e dati."""
    cx, cy, r = DIAL_C
    g.mask("CRing", "EllipseMask", X("%s * 2 / _A" % r), X("%s * 2 / _A" % r), center="{ %s, %s }" % (cx, cy),
           border=repr(LINE_W * 0.8))
    g.mask("CHub", "EllipseMask", X("%s * 0.56 / _A" % r), X("%s * 0.56 / _A" % r), center="{ %s, %s }" % (cx, cy),
           border=repr(LINE_W * 0.8), chain="CRing")
    g.background("CRingBg", color="Accent", mask="CHub")
    top = g.merge("CMr", base, "CRingBg")
    top = g.merge("CMa", top, hand(g, "CHand", cx, cy, r * 0.30, r * 0.93, 0.0022,
                                   "-6 * math.floor((_REM - 1) / _FPS)", color="Text"))
    g.text("CSec", "{ %s, %s }" % (cx, cy), X(cap_size(0.05)), ex("Text(tostring(math.ceil(_REM / _FPS)))"),
           tint("Text"))
    x = 0.58
    g.text("CTitle", "{ %s, 0.80 }" % x,
           X("math.min(2 * 0.06 / _A * _N, 0.75 / math.max(1, string.len(LK.Title.Value)))"),
           ex('Text(%s and string.upper(LK.Title.Value) or "")' % NO_TITLE_IMG), tint("Hi"), align="l")
    g.text("CHead", "{ %s, 0.69 }" % x, X(cap_size(0.016)), "Text(%s)" % pv(P, "heading"), tint("Text", 0.8),
           align="l")
    info_block(g, "CInfo", x, "0.625", 0.017, "0.12")
    common_footer(g, "Foot2", static)
    return g.merge("CMt", top, g.chain("CTx", ["CSec", "CTitle", "CHead", "CInfo", "Foot2"]))


def slate_style_d(g, P, base, static):
    """Minimale: titolo grande al centro, regia, filo, una riga di dati essenziali e i timecode."""
    g.mask("DRule", "RectangleMask", "0.12", repr(LINE_W * 1.2), center="{ 0.5, 0.42 }")
    g.background("DRuleBg", color="Hi", mask="DRule")
    top = g.merge("DMr", base, "DRuleBg")
    g.text("DHead", "{ 0.5, 0.80 }", X(cap_size(0.016)), "Text(%s)" % pv(P, "heading"), tint("Hi"))
    g.text("DTitle", "{ 0.5, 0.60 }", X("math.min(2 * 0.09 / _A * _N, 2.2 / math.max(1, string.len(LK.Title.Value)))"),
           ex('Text(%s and string.upper(LK.Title.Value) or "")' % NO_TITLE_IMG), tint("Text"))
    g.text("DDir", "{ 0.5, 0.47 }", X(cap_size(0.024)),
           ex('Text(LK.Director.Value == "" and "" or ("DIRECTED BY   " .. string.upper(LK.Director.Value)))'),
           tint("Text", 0.85), style="Regular")
    parts = ["LK.Version.Value", "LK.Duration.Value", DATE_EXPR % TODAY,
             'string.format("%g fps", comp:GetPrefs("Comp.FrameFormat.Rate"))',
             'string.format("%d × %d", _W, _H)', "LK.ColorInfo.Value", "LK.AudioFormat.Value"]
    line = ("(function() local s = '' local function a(v) v = tostring(v or '') "
            "if v ~= '' then if s ~= '' then s = s .. '   ·   ' end s = s .. v end end "
            + " ".join("a(%s)" % p for p in parts) + " return s end)()")
    g.text("DLine", "{ 0.5, 0.36 }", X(cap_size(0.016)), ex("Text(%s)" % line), tint("Text", 0.9), style="Regular")
    who = ("(function() local s = '' local function a(l, v) if v ~= '' then if s ~= '' then s = s .. '      ' end "
           "s = s .. l .. '  ' .. v end end a('PRODUCTION', LK.Production.Value) a('PRODUCER', LK.Producer.Value) "
           "a('EDITOR', LK.Editor.Value) a('CLIENT', LK.Client.Value) return s end)()")
    g.text("DWho", "{ 0.5, 0.31 }", X(cap_size(0.0135)), "Text(%s)" % who, tint("Text", 0.65), style="Regular")
    common_footer(g, "Foot3", static)
    top = g.merge("DMt", top, g.chain("DTx", ["DHead", "DTitle", "DDir", "DLine", "DWho", "Foot3"]))
    return g.merge("DMs", top, status_chips(g, "DSt", "0.21"))


# ------------------------------------------------------------------ immagini (logo, titolo in PNG)
def logo_pre(sfx):
    """Lua: riquadro del logo largo LogoSize% del quadro (alto al massimo meta'), margini 3.5% / 4%."""
    w, h, pos, size = "Logo%sW" % sfx, "Logo%sH" % sfx, "LogoPos%s" % sfx, "LogoSize%s" % sfx
    return ("local iw, ih = math.max(1, LK.%s), math.max(1, LK.%s) local bw = LK.%s / 100 * _W "
            "local s = math.min(bw / iw, bw * 0.5 / ih) local dw, dh = iw * s, ih * s "
            "local mx, my = 0.035 * _W, 0.04 * _H local p = math.floor(LK.%s + 0.5) "
            "local x = ({ _W - mx - dw / 2, mx + dw / 2, _W - mx - dw / 2, mx + dw / 2, _W / 2 })[p + 1] or _W / 2 "
            "local y = ({ _H - my - dh / 2, _H - my - dh / 2, my + dh / 2, my + dh / 2, _H / 2 })[p + 1] or _H / 2 "
            % (w, h, size, pos))


def logo_layer(sfx, loader):
    pre = logo_pre(sfx)
    return (loader, X("Point(x / _W, y / _H)", pre), X("s", pre))


def logo_cond(sfx):
    return 'LK.Logo%s.Value ~= "" and LK.Logo%sW > 0 and LK.Logo%sH > 0' % (sfx, sfx, sfx)


def title_image_layer():
    boxes = "{ %s }" % ", ".join("{ %s, %s, %s, %s, %d }" % (x, y, w, h, 1 if a == "left" else 0)
                                  for x, y, w, h, a in TITLE_BOXES)
    pre = ("local b = (%s)[math.floor(LK.SlateStyle + 0.5) + 1] or { 0.5, 0.8, 0.6, 0.12, 0 } "
           "local k = LK.TitleImageSize / 100 local iw, ih = math.max(1, LK.TitleW), math.max(1, LK.TitleH) "
           "local s = math.min(b[3] * _W * k / iw, b[4] * _H * k / ih) "
           "local x = (b[5] > 0.5) and (b[1] * _W + iw * s / 2) or b[1] * _W " % boxes)
    return ("TitleLd", X("Point(x / _W, b[2])", pre), X("s", pre))


# ------------------------------------------------------------------ frame lines e safe area
GUIDE_CAP = 0.014


def guides_layer(g):
    """Frame lines (formato della timeline e formati scelti) e safe area: contorni a pixel interi,
    con l'etichetta 'formato · risoluzione reale nella timeline'. Un solo Background per le linee."""
    fmts = [("FLTL", None, None)] + [(k, lab + ":1", ar) for k, lab, ar in FRAMELINES]
    flist = "{ %s }" % ", ".join("{ LK.%s, %s }" % (k, repr(ar) if ar else "0") for k, _, ar in fmts)
    lw = "local lw = math.max(1, math.floor(_H / 1080 * 2 + 0.5)) "
    pos = ("local cap = %s * _H local pad = 0.008 * _H local st = 1.9 * cap " % GUIDE_CAP)
    chain, labels = None, []
    for i, (key, lab, ar) in enumerate(fmts, 1):
        geo = ("local ar = %s local aw, ah = _W, _H "
               "if ar > _A + 0.005 then ah = 2 * math.floor(_W / ar / 2 + 0.5) "
               "elseif ar < _A - 0.005 then aw = 2 * math.floor(_H * ar / 2 + 0.5) end "
               % (repr(ar) if ar else "_A")) + lw + "local on = LK.%s > 0.5 " % key
        chain = g.mask("G%sM" % key, "RectangleMask", X("on and (aw - lw) / _W or 0", geo),
                       X("on and (ah - lw) / _H or 0", geo), border=X("lw / _W", geo), chain=chain,
                       level=X("on and 1 or 0", geo))
        # etichette dentro le linee: letterbox sotto la linea alta (affiancate se piu' d'una), pillarbox in
        # basso accanto alla linea sinistra, formato pieno in basso a sinistra (impilate)
        cls = ("local function cls(a) if a == 0 then return 3 end "
               "if a > _A + 0.005 then return 1 elseif a < _A - 0.005 then return 2 end return 3 end "
               "local me = cls(%s) " % (repr(ar) if ar else "0"))
        stack = ("local F = %s local k, nfull = 0, 0 for j = 1, #F do if F[j][1] > 0.5 then "
                 "local cj = cls(F[j][2]) if j < %d and cj == me then k = k + 1 end "
                 "if cj == 3 then nfull = nfull + 1 end end end " % (flist, i))
        where = ("local x, y = (lw + pad) / _W, (lw + pad + cap / 2 + k * st) / _H "
                 "if me == 1 then x = (lw + pad + k * 19 * cap) / _W y = 1 - ((_H - ah) / 2 + lw + pad + cap / 2) / _H "
                 "elseif me == 2 then x = ((_W - aw) / 2 + lw + pad) / _W "
                 "y = (lw + pad + cap / 2 + (nfull + k) * st) / _H end ")
        if ar:
            label = 'on and string.format("%s  ·  %%d × %%d", aw, ah) or ""' % lab
        else:
            label = 'on and string.format("TIMELINE %.2f:1  ·  %d × %d", _A, aw, ah) or ""'
        labels.append(g.text("G%sT" % key, X("Point(x, y)", geo + cls + stack + pos + where), X("2 * %s / _A" % GUIDE_CAP),
                             ex("Text(%s)" % label, geo), tint("Accent", 0.95),
                             align="l"))
    for key, pct, lab in SAFE_AREAS:
        geo = ("local aw, ah = 2 * math.floor(_W * %s / 2 + 0.5), 2 * math.floor(_H * %s / 2 + 0.5) " % (pct, pct)
               + lw + "local on = LK.%s > 0.5 " % key)
        chain = g.mask("G%sM" % key, "RectangleMask", X("on and (aw - lw) / _W or 0", geo),
                       X("on and (ah - lw) / _H or 0", geo), border=X("lw / _W", geo), chain=chain,
                       level=X("on and 1 or 0", geo))
        pre = geo + pos
        labels.append(g.text("G%sT" % key, X("Point(((_W - aw) / 2 + lw + pad) / _W, 1 - ((_H - ah) / 2 + lw + pad + cap / 2) / _H)", pre),
                             X("2 * %s / _A" % GUIDE_CAP), ex('Text(on and "%s" or "")' % lab, pre),
                             tint("Accent", 0.7), align="l"))
    g.background("GLines", color="Accent", scale=0.8, mask=chain)
    return g.merge("GLay", "GLines", g.chain("GLab", labels))


# ------------------------------------------------------------------ generatore di testa
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
    SYNCREM = "math.floor(%s * _FPS + 0.5)" % FL_BEFORE
    SYNCFR = "math.max(1, math.floor(%s * _FPS / 25 + 0.5))" % FL_FR
    BARSVIS = "(_REM > (%s + %s + %s) * _FPS)" % (S, GP, C)
    SLATEVIS = "(_REM <= (%s + %s + %s) * _FPS and _REM > (%s + %s) * _FPS)" % (S, GP, C, GP, C)
    LEADVIS = "(%s > 0 and _REM <= %s * _FPS and (_REM > 2 * _FPS or (_REM == 2 * _FPS and %s > 0.5)))" % (C, C, POP)
    ANY_GUIDE = "((%s) > 0.5)" % " + ".join("LK.%s" % k for k in GUIDE_KEYS)
    GUIDEVIS = "(%s and ((%s and LK.GuidesSlate > 0.5) or (%s and LK.GuidesCd > 0.5)))" % (ANY_GUIDE, SLATEVIS, LEADVIS)
    static = pv(P, "slate_lines", fn=lambda p: "\n".join(x for x in p.get("slate_lines", []) if "{" not in x))
    vis = visibility_script(std)

    # --- controlli, per scheda
    prog = (uc_label("SecPreset", "LeaderKit %s" % __version__)
            + uc_combo("Preset", "Standard", [p["name"] for p in P], on_change=vis)
            + uc_slider("Reel", "Rullo (FFOA a N:00:08:00)", 1, 23, 1)
            + uc_combo("DurSel", "Durata programma", ["Libera (fine dei tuoi clip)", "Slot dello standard",
                                                     "Personalizzata"], on_change=vis)
            + uc_label("SecSlots", "Slot (quello della categoria dello standard)", fold=len(SLOT_INPUTS)))
    for cat, inp, label in SLOT_INPUTS:
        prog += uc_combo(inp, label, [x[0] for x in SLOTS[cat]])
    prog += (uc_text("ProgramTC", "Durata (HH:MM:SS:FF)")
             + uc_combo("Breaks", "Break pubblicitari", BREAKS)
             + uc_check("MarkersOn", "Marker di fine rullo", 1)
             + uc_slider("MarkerEvery", "Rullo ogni (min, 0 = standard)", 0, 60, 0, integer=False)
             + uc_check("TailOn", "Inserisci la coda", 1)
             + uc_button("Generate", "Genera sulla timeline", engine("generate", std))
             + uc_button("Remove", "Rimuovi elementi generati", engine("remove", std))
             + uc_text("Guide", "Esito", lines=6, read_only=True)
             + uc_text("Duration", "Durata del programma", read_only=True)
             + uc_text("Info", "Timecode", lines=2, read_only=True)
             + uc_label("SecCustom", "Durate del leader (standard Personalizzato)", fold=6)
             + uc_check("Custom", "Personalizza le durate", 0)
             + uc_slider("BarsSec", "Barre (s)", 0, 60, 0) + uc_slider("SlateSec", "Slate (s)", 0, 30, 8)
             + uc_slider("GapSec", "Nero prima del programma (s)", 0, 10, 2)
             + uc_slider("CountFrom", "Countdown da (0 = nessuno)", 0, 11, 8)
             + uc_slider("TailSec", "Coda (s)", 0, 30, 8))
    today_code = 'pcall(function() tool:SetInput("Date", os.date("%d/%m/%Y")) end)'
    data = uc_label("SecProd", "Produzione") + "".join(uc_text(f, label) for f, label, _ in PRODUCTION_FIELDS)
    data += (uc_check("DateAuto", "Data sempre aggiornata (data del render)", 1)
             + uc_button("DateToday", "Oggi", today_code)
             + uc_label("SecPost", "Post-produzione"))
    data += "".join(uc_text(f, label) for f, label, _ in POST_FIELDS)
    data += uc_combo("Phase", "Fase di lavorazione", PHASES)
    data += "".join(uc_combo(f, label, STATUS_VALUES) for f, label, _ in STATUSES)
    data += uc_text("Note", "Note (riga libera)")
    look = (uc_label("SecStyle", "Slate")
            + uc_combo("SlateStyle", "Stile", SLATE_STYLES)
            + uc_text("TitleImage", "Titolo in PNG (file)", on_change=image_script("TitleImage", "sync"))
            + uc_button("TitlePick", "Scegli il titolo in PNG...", image_script("TitleImage", "pick"))
            + uc_slider("TitleImageSize", "Dimensione del titolo in PNG (%)", 20, 200, 100, integer=False)
            + uc_label("SecLogo", "Loghi (sulla slate; anche sulla coda se vuoi)")
            + uc_text("Logo", "Logo (file)", on_change=image_script("Logo", "sync"))
            + uc_button("LogoPick", "Scegli il logo...", image_script("Logo", "pick"))
            + uc_combo("LogoPos", "Posizione", LOGO_POS)
            + uc_slider("LogoSize", "Larghezza (% del quadro)", 5, 100, 12, integer=False)
            + uc_text("Logo2", "Secondo logo (file)", on_change=image_script("Logo2", "sync"))
            + uc_button("Logo2Pick", "Scegli il secondo logo...", image_script("Logo2", "pick"))
            + uc_combo("LogoPos2", "Posizione del secondo logo", LOGO_POS)
            + uc_slider("LogoSize2", "Larghezza del secondo logo (%)", 5, 100, 12, integer=False)
            + uc_check("LogoOnTail", "Loghi anche sulla coda", 0)
            + uc_label("SecLook", "Colori") + color_controls())
    guide = (uc_label("SecGuides", "Frame lines e safe area (sotto i testi, a pixel interi)")
             + uc_check("GuidesSlate", "Sulla slate", 1) + uc_check("GuidesCd", "Sul countdown", 1)
             + uc_check("FLTL", "Formato della timeline", 0)
             + "".join(uc_check(f, "Frame line " + lab + ":1", 0) for f, lab, _ in FRAMELINES)
             + uc_check("SafeAction", "Safe action 93% (EBU R95)", 0) + uc_check("SafeTitle", "Safe title 90%", 0)
             + uc_label("SecEnd", "Ultimo fotogramma del leader (il programma parte al successivo)")
             + uc_check("EndDot", "Pallino sull'ultimo fotogramma", 0)
             + uc_combo("EndDotPos", "Posizione del pallino", END_DOT_POS)
             + uc_slider("EndDotSize", "Diametro del pallino (% dell'altezza)", 1, 20, 5, integer=False))
    tech = (uc_label("SecTech", "Dati tecnici")
            + uc_text("ColorInfo", "Spazio colore (letto da Genera)", read_only=True)
            + uc_text("AudioFormat", "Formato audio (es. 5.1 + stereo, 24 bit 48 kHz)")
            + uc_label("SecAudio", "Audio (tono 1 kHz)")
            + uc_combo("PopLevel", "Livello pop", ["Dallo standard", "-20 dBFS (SMPTE / USA)", "-18 dBFS (EBU / Europa)"])
            + uc_check("BeepEach", "Bip anche su 8..3 (non standard)", 0)
            + uc_label("SecCal", "Taratura sul countdown (immagine creata da Genera)")
            + uc_check("CalOn", "Strumenti di taratura", 1)
            + "".join(uc_check(f, label, d) for f, label, d in CALIBRATION))
    hidden = "".join(uc_hidden(k) for k in HIDDEN_NUM)
    uc = (on_page("Progetto", prog) + on_page("Dati", data) + on_page("Aspetto", look)
          + on_page("Guide", guide) + on_page("Tecnico", tech) + hidden)

    values = [("Preset", "0"), ("Reel", "1"), ("DurSel", "0"), ("ProgramTC", '"00:00:30:00"'), ("Breaks", "0"),
              ("Custom", "0"), ("BarsSec", "0"), ("SlateSec", "8"), ("GapSec", "2"), ("CountFrom", "8"),
              ("TailSec", "8"), ("MarkersOn", "1"), ("MarkerEvery", "0"), ("TailOn", "1"),
              ("Guide", '"Metti il blocco dove inizia il leader (anche a timeline vuota) e premi Genera"'),
              ("Duration", '"premi Genera"'), ("Info", '""'), ("Title", '"TITOLO"'), ("Version", '"v1"'),
              ("DateAuto", "1"), ("Phase", "0"), ("Note", '""'), ("GuidesSlate", "1"), ("GuidesCd", "1"),
              ("FLTL", "0"), ("SafeAction", "0"), ("SafeTitle", "0"), ("EndDot", "0"), ("EndDotPos", "0"),
              ("EndDotSize", "5"), ("ColorInfo", '""'), ("AudioFormat", '""'),
              ("PopLevel", "0"), ("BeepEach", "0"), ("Logo", '""'), ("LogoPos", "0"), ("LogoSize", "12"),
              ("Logo2", '""'), ("LogoPos2", "1"), ("LogoSize2", "12"),
              ("SlateStyle", "0"), ("TitleImage", '""'), ("TitleImageSize", "100"),
              ("LogoOnTail", "0"), ("CalOn", "1")]
    values += [(i, str(std.get("slot_defaults", {}).get(c, 0))) for c, i, _ in SLOT_INPUTS]
    values += [(f, '""') for f, _, _ in PRODUCTION_FIELDS + POST_FIELDS if f not in ("Title", "Version")]
    values += [(f, "0") for f, _, _ in STATUSES]
    values += [(f, "0") for f, _, _ in FRAMELINES]
    values += [(f, str(d)) for f, _, d in CALIBRATION]
    values += [(k, "0") for k in HIDDEN_NUM]
    values += color_values()

    g = G()
    g.controls(values, uc)
    g.loader("TitleLd")
    g.loader("Logo1Ld")
    g.loader("Logo2Ld")
    g.background("Bg", color="Bg")
    # barre
    top = g.dissolve("MBars", "Bg", bars_stack(g), ex("(%s) and 1 or 0" % BARSVIS))
    # frame lines e safe area subito sopra lo sfondo, sotto slate e countdown
    base = g.gate("MGuides", "Bg", [guides_layer(g)], GUIDEVIS)
    # slate: quattro stili alternati, poi titolo in PNG, loghi e orologio ident
    s_ = slate_panels(g, P, base, static)
    for i, fn in ((1, slate_style_b), (2, slate_style_c), (3, slate_style_d)):
        s_ = g.dissolve("SStyle%d" % i, s_, fn(g, P, base, static), "(math.floor(LK.SlateStyle + 0.5) == %d) and 1 or 0" % i)
    s_ = g.gate("STitleImg", s_, [title_image_layer()], 'LK.TitleImage.Value ~= "" and LK.TitleW > 0 and LK.TitleH > 0')
    s_ = g.gate("SLogo1", s_, [logo_layer("", "Logo1Ld")], logo_cond(""))
    s_ = g.gate("SLogo2", s_, [logo_layer("2", "Logo2Ld")], logo_cond("2"))
    s_ = g.gate("SClock", s_, clock_layers(g), "%s > 0.5" % CLOCK)
    top = g.dissolve("MSlate", top, s_, ex("(%s) and 1 or 0" % SLATEVIS))
    # countdown + 2-pop, sopra le frame lines (la taratura PNG di Genera sta sulla traccia sopra)
    lead = leader_stack(g, "L", base, 'Text((_REM < %s * _FPS and _REM >= 2 * _FPS) and tostring(math.ceil(_REM / _FPS)) or "")' % C,
                        sweep_vis="_REM < %s * _FPS and _REM > 2 * _FPS" % C, cd=C)
    top = g.dissolve("MLeader", top, lead, ex("(%s) and 1 or 0" % LEADVIS))
    g.text("PicStart", "{ 0.5, 0.5 }", "0.075", 'Text("PICTURE\\nSTART")', tint("Text"), spacing=1.0)
    top = g.gate("MPicStart", top, ["PicStart"], "%s > 0 and _REM == %s * _FPS" % (C, C))
    g.background("Flash", rgb=["1", "1", "1"])
    top = g.gate("MFlash", top, ["Flash"], "%s > 0.5 and _REM <= %s and _REM > %s - %s" % (FL_ON, SYNCREM, SYNCREM, SYNCFR))
    # pallino sull'ultimo fotogramma del leader: il programma inizia al fotogramma successivo
    dot = ("local m = 0.09 local p = math.floor(LK.EndDotPos + 0.5) "
           "local x = ({ 1 - m / _A, 0.5, m / _A })[p + 1] or (1 - m / _A) "
           "local y = ({ 1 - m, 0.5, 1 - m })[p + 1] or (1 - m) ")
    g.mask("EndDotM", "EllipseMask", X("LK.EndDotSize / 100 / _A"), X("LK.EndDotSize / 100 / _A"),
           center=X("Point(x, y)", dot))
    g.background("EndDotBg", color="Text", mask="EndDotM")
    top = g.gate("MEndDot", top, ["EndDotBg"], "LK.EndDot > 0.5 and _REM == 1")
    g.text("Warn", "{ 0.5, 0.08 }", "0.03", ex("Text(\"Premi GENERA nell'Inspector: il blocco diventa di \" .. %s .. \" secondi\")" % HEADLEN),
           tint("Text"))
    top = g.gate("MWarn", top, ["Warn"],
                 "math.abs((comp.RenderEnd - comp.RenderStart + 1) - %s * _FPS) > 0.5" % HEADLEN)
    return group("LeaderKit", g, top, head_inputs())


# ------------------------------------------------------------------ coda
TAIL_INPUTS = ([(x, "Coda") for x in ("TailPop", "TailFlash", "CardFrom", "CardTo", "CardText", "Info")]
               + [(x, "Logo") for x in ("Logo", "LogoPick", "LogoPos", "LogoSize", "Logo2", "Logo2Pick",
                                        "LogoPos2", "LogoSize2")]
               + [(c, "Coda") for c in color_inputs()])


def tail(std=None):
    g = G()
    coda = (uc_check("TailPop", "Tail pop a +2\"", 1) + uc_check("TailFlash", "Flash (clap) a +2\"", 0)
            + uc_slider("CardFrom", "Card da (s)", 0, 30, 4, integer=False)
            + uc_slider("CardTo", "Card fino a (s)", 0, 30, 7, integer=False)
            + uc_text("CardText", "Testo card") + uc_text("Info", "Info (da Genera)"))
    logo = (uc_text("Logo", "Logo (file)", on_change=image_script("Logo", "sync"))
            + uc_button("LogoPick", "Scegli il logo...", image_script("Logo", "pick"))
            + uc_combo("LogoPos", "Posizione", LOGO_POS)
            + uc_slider("LogoSize", "Larghezza (% del quadro)", 5, 100, 12, integer=False)
            + uc_text("Logo2", "Secondo logo (file)", on_change=image_script("Logo2", "sync"))
            + uc_button("Logo2Pick", "Scegli il secondo logo...", image_script("Logo2", "pick"))
            + uc_combo("LogoPos2", "Posizione del secondo logo", LOGO_POS)
            + uc_slider("LogoSize2", "Larghezza del secondo logo (%)", 5, 100, 12, integer=False))
    uc = (on_page("Coda", coda + color_controls()) + on_page("Logo", logo)
          + "".join(uc_hidden(k) for k in HIDDEN_NUM[:4]))
    g.controls([("TailPop", "1"), ("TailFlash", "0"), ("CardFrom", "4"), ("CardTo", "7"),
                ("CardText", '"END OF PROGRAM"'), ("Info", '""'), ("Logo", '""'), ("LogoPos", "0"),
                ("LogoSize", "12"), ("Logo2", '""'), ("LogoPos2", "1"), ("LogoSize2", "12")]
               + [(k, "0") for k in HIDDEN_NUM[:4]] + color_values(), uc)
    g.loader("Logo1Ld")
    g.loader("Logo2Ld")
    g.background("Bg", color="Bg")
    lead = leader_stack(g, "T", "Bg", 'Text("2")')
    top = g.dissolve("MPop", "Bg", lead, ex("(LK.TailPop > 0.5 and _EL == 2 * _FPS - 1) and 1 or 0"))
    g.background("Flash", rgb=["1", "1", "1"])
    top = g.gate("MFlash", top, ["Flash"], "LK.TailFlash > 0.5 and _EL == 2 * _FPS - 1")
    g.text("CardText", "{ 0.5, 0.5 }", "0.07", "Text(LK.CardText.Value)", tint("Text"))
    g.text("CardSub", "{ 0.5, 0.36 }", "0.024", "Text(LK.Info.Value)", tint("Text", 0.7), style="Regular")
    top = g.gate("MCard", top, [g.chain("CardC", ["CardText", "CardSub"])],
                 "_EL >= LK.CardFrom * _FPS and _EL < LK.CardTo * _FPS")
    top = g.gate("TLogo1", top, [logo_layer("", "Logo1Ld")], logo_cond(""))
    top = g.gate("TLogo2", top, [logo_layer("2", "Logo2Ld")], logo_cond("2"))
    return group("LeaderKit Tail", g, top, TAIL_INPUTS)


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
BURN_POS = ["Ai bordi (nelle bande del mascherino, se c'e')", "Dentro l'immagine (safe 90%)"]
MATTES = [("Nessuno (formato della timeline)", 0), ("1.33:1 (4:3)", 4.0 / 3.0), ("1.37:1 (Academy)", 1.37),
          ("1.43:1 (IMAX)", 1.43), ("1.66:1", 1.66), ("1.78:1 (16:9)", 16.0 / 9.0), ("1.85:1 (Flat)", 1.85),
          ("1.90:1 (IMAX digitale / DCI full)", 1.9), ("2.00:1 (Univisium)", 2.0), ("2.20:1 (70 mm)", 2.2),
          ("2.35:1", 2.35), ("2.39:1 (Scope)", 2.39), ("2.76:1 (Ultra Panavision 70)", 2.76),
          ("Personalizzato (slider)", -1)]
IDX_REC = 18                       # record di LK.SegIdx: inizio relativo (10 cifre) + posizione della riga (8)


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


# Geometria del burn-in, calcolata in ogni espressione (solo aritmetica: la risoluzione e' quella
# scritta da Genera / Aggiorna, comp:GetPrefs solo se manca).
BURN_GEO = (
    'local W = LK.TlW > 0 and LK.TlW or comp:GetPrefs("Comp.FrameFormat.Width") '
    'local H = LK.TlH > 0 and LK.TlH or comp:GetPrefs("Comp.FrameFormat.Height") '
    "local AR = W / H local mi = math.floor(LK.BMatte + 0.5) "
    "local MR = (mi == %d) and LK.BMatteRatio or (({ %s })[mi + 1] or 0) "
    # immagine attiva in pixel interi e pari (es. 1920 x 804 per 2.39 su 1920 x 1080)
    "local LB = (MR > AR + 0.01) and (H - 2 * math.floor(W / MR / 2 + 0.5)) / (2 * H) or 0 "
    "local PB = (MR > 0 and MR < AR - 0.01) and (W - 2 * math.floor(H * MR / 2 + 0.5)) / (2 * W) or 0 "
    "local CAP = LK.BSize * 0.01 local INSIDE = LK.BPos > 0.5 "
    "local LBOX = (not INSIDE) and LB > 0 local PBOX = (not INSIDE) and PB > 0 "
    "local SINGLE = LBOX and LB < 3.2 * CAP "                      # banda sottile: una riga sola
    "local CAPE = SINGLE and math.min(CAP, LB / 1.7) or CAP "
    "local EDGE = (not INSIDE) and not LBOX and not PBOX "        # senza mascherino: ai bordi del quadro
    "local BAND = 4.6 * CAP "
    % (len(MATTES) - 1, ", ".join(repr(max(r, 0)) for _, r in MATTES)))

# Riga del fotogramma corrente: ricerca binaria su LK.SegIdx (O(log n) anche con migliaia di
# tagli), con i segnaposto {REC} {SRC} {ATC} {FRM} calcolati qui. Solo funzioni sicure nelle
# espressioni di Fusion (niente tonumber: le cifre si convertono con "+ 0").
BURN_ROW = (
    "local function tc(f, n, d) f = math.floor(f + 0.5) if f < 0 then return '--:--:--:--' end "
    "if d > 0 then local p10, pm = n * 600 - d * 9, n * 60 - d local q, m = math.floor(f / p10), f % p10 "
    "if m > d then f = f + d * 9 * q + d * math.floor((m - d) / pm) else f = f + d * 9 * q end end "
    "return string.format('%02d:%02d:%02d%s%02d', math.floor(f / (n * 3600)), math.floor(f / (n * 60)) % 60, "
    "math.floor(f / n) % 60, d > 0 and ';' or ':', f % n) end "
    "local function ROW() "
    "local idx, seg = LK.SegIdx.Value, LK.Seg.Value local e0 = time - comp.RenderStart "
    "local rec = LK.RecStart + e0 local line = nil local n = math.floor(string.len(idx) / " + str(IDX_REC) + ") "
    "if n > 0 then "
    "if string.sub(idx, 1, 10) + 0 <= e0 then local lo, hi = 1, n "
    "while lo < hi do local mid = math.floor((lo + hi + 1) / 2) "
    "if string.sub(idx, mid * 18 - 17, mid * 18 - 8) + 0 <= e0 then lo = mid else hi = mid - 1 end end "
    "line = string.match(seg, '^[^\\n]+', string.sub(idx, lo * 18 - 7, lo * 18) + 0) end "
    "else for l in string.gmatch(seg, '[^\\n]+') do local a, b = string.match(l, '^(%-?%d+)|(%-?%d+)|') "
    "if a and rec >= a + 0 and rec < b + 0 then line = l break end end end "
    "if not line then return nil end "
    "local a, b, sv, st, sn, sd, au, fr, t1, t2, t3, t4 = string.match(line, "
    "'^(%-?%d+)|(%-?%d+)|(%-?[%d%.]+)|([%d%.]+)|(%d+)|(%d+)|(%-?%d+)|(%-?%d+)|([^|]*)|([^|]*)|([^|]*)|([^|]*)$') "
    "if not a or rec < a + 0 or rec >= b + 0 then return nil end "
    "local e = rec - a local tn, td = math.max(1, LK.TlFps), LK.TlDrop "
    "local function sub(txt) "
    "txt = string.gsub(txt, '{REC}', tc(rec, tn, td)) "
    "txt = string.gsub(txt, '{SRC}', tc((sv + 0) < 0 and -1 or (sv + 0) + e * (st + 0), (sn + 0), (sd + 0))) "
    "txt = string.gsub(txt, '{ATC}', tc((au + 0) < 0 and -1 or (au + 0) + e, tn, td)) "
    "txt = string.gsub(txt, '{FRM}', tostring(fr + e)) return txt end "
    "return { t1, t2, t3, t4 }, sub end "
    # testo di un angolo: due righe, o una sola nelle bande sottili del mascherino
    "local function CORNER(k) local r, sub = ROW() if not r then return '' end "
    "local parts = {} for x in string.gmatch((r[k] or '') .. '~', '([^~]*)~') do parts[#parts + 1] = x end "
    "local p1, p2 = parts[1] or '', parts[2] or '' local s "
    "if SINGLE then s = p1 .. ((p1 ~= '' and p2 ~= '') and '     ' or '') .. p2 "
    "elseif p1 ~= '' and p2 ~= '' then s = p1 .. '\\n' .. p2 else s = p1 .. p2 end "
    "return sub(s) end "
    "local function BIG() local r, sub = ROW() if not r then return '' end "
    "local parts = {} for x in string.gmatch((r[4] or '') .. '~', '([^~]*)~') do parts[#parts + 1] = x end "
    "return sub(parts[3] or '') end ")


def burn_x(hx):
    """Ascissa: bande laterali (pillarbox), bordo (margine), o celle centrate."""
    margin = "(INSIDE and 0.05 or 0.02)"
    if hx < 0:
        return "(PBOX and PB / 2 or (LK.BAlign < 0.5 and %s or 0.2))" % margin
    return "(PBOX and 1 - PB / 2 or (LK.BAlign < 0.5 and 1 - %s or 0.8))" % margin


def burn_y(top):
    """Ordinata del blocco (una o due righe) di un angolo."""
    if top:
        return ("(LBOX and 1 - LB / 2 or (PBOX and 0.95 - 0.9 * CAPE or (INSIDE and 0.93 or 1 - BAND / 2)))")
    return "(LBOX and LB / 2 or (PBOX and 0.05 + 0.9 * CAPE or (INSIDE and 0.07 or BAND / 2)))"


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
    look = (uc_combo("BMatte", "Mascherino", [m for m, _ in MATTES])
            + uc_slider("BMatteRatio", "Rapporto personalizzato (x:1)", 1, 3, 2.39, integer=False)
            + uc_slider("BMatteAlpha", "Opacita' del mascherino", 0, 1, 1, integer=False)
            + uc_combo("BPos", "Posizione dei dati", BURN_POS)
            + uc_combo("BAlign", "Allineamento dei dati", ["Ai bordi (sinistra / destra)", "Centrati nelle celle"])
            + uc_slider("BSize", "Altezza testo (% del quadro)", 1, 5, 1.8, integer=False)
            + uc_check("BBands", "Bande semitrasparenti dietro ai dati (senza mascherino)", 0)
            + uc_slider("BBandAlpha", "Opacita' delle bande", 0, 1, 0.6, integer=False)
            + uc_slider("BWaterAlpha", "Opacita' watermark", 0, 1, 0.18, integer=False))
    uc = on_page("Burn-in", main) + on_page("Campi", fields) + on_page("Aspetto", look)
    uc += (uc_hidden("Seg", "Text") + uc_hidden("SegIdx", "Text")
           + "".join(uc_hidden(k) for k in ("RecStart", "TlFps", "TlDrop", "TlW", "TlH")))
    d = dict((k, 0) for k, _ in BURN_FIELDS)
    for k in BURN_PHASES[2][1]:
        d[k] = 1
    values = [("BPhase", "2"), ("BTitleText", '""'), ("BVersionText", '""'), ("BWaterText", '"CONFIDENZIALE"'),
              ("BRecipient", '""'), ("BInfo", '"Metti il clip sopra il montato (V3/V4) e premi Aggiorna"'),
              ("BFrameMode", "1"), ("BPos", "0"), ("BAlign", "0"), ("BMatte", "0"), ("BMatteRatio", "2.39"),
              ("BMatteAlpha", "1"), ("BSize", "1.8"), ("BBands", "0"), ("BBandAlpha", "0.6"), ("BWaterAlpha", "0.18"),
              ("Seg", '""'), ("SegIdx", '""'), ("RecStart", "0"), ("TlFps", "24"), ("TlDrop", "0"),
              ("TlW", "0"), ("TlH", "0")]
    values += [(k, str(v)) for k, v in d.items()]
    g.controls(values, uc)

    def bx(body):
        return ("expr", "(function() %s return %s end)()" % (BURN_GEO, body))

    def bt(body):
        return ("expr", "(function() %s %s return %s end)()" % (BURN_GEO, BURN_ROW, body))

    g.background("Bg", rgb=["0", "0", "0"], alpha="0")
    # mascherino: bande sopra/sotto (letterbox) o ai lati (pillarbox), un solo Background
    g.mask("MatTM", "RectangleMask", "1.02", bx("LB"), center=bx("Point(0.5, 1 - LB / 2)"))
    g.mask("MatBM", "RectangleMask", "1.02", bx("LB"), center=bx("Point(0.5, LB / 2)"), chain="MatTM")
    g.mask("MatLM", "RectangleMask", bx("PB"), "1.02", center=bx("Point(PB / 2, 0.5)"), chain="MatBM")
    g.mask("MatRM", "RectangleMask", bx("PB"), "1.02", center=bx("Point(1 - PB / 2, 0.5)"), chain="MatLM")
    g.background("Mat", alpha=("expr", "LK.BMatteAlpha"), mask="MatRM")
    top = g.dissolve("GMat", "Bg", g.merge("GMatM1", "Bg", "Mat"), bx("(LB > 0 or PB > 0) and 1 or 0"))
    # bande semitrasparenti facoltative (spente di default)
    g.mask("BandTM", "RectangleMask", "1.02", bx("BAND"), center=bx("Point(0.5, 1 - BAND / 2)"))
    g.mask("BandBM", "RectangleMask", "1.02", bx("BAND"), center=bx("Point(0.5, BAND / 2)"), chain="BandTM")
    g.background("Band", alpha=("expr", "LK.BBandAlpha"), mask="BandBM")
    top = g.dissolve("GBand", top, g.merge("GBandM1", top, "Band"), bx("(EDGE and LK.BBands > 0.5) and 1 or 0"))
    # angoli: 1 alto-sx, 2 alto-dx, 3 basso-sx, 4 basso-dx; un Text+ per angolo (due righe)
    corners = []
    for corner, (hx, is_top) in enumerate([(-1, True), (1, True), (-1, False), (1, False)], 1):
        nm = "T%d" % corner
        maxw = "(PBOX and 0.9 * PB or 0.46)"
        size = ("(function() local s = CORNER(%d) local m = 1 for l in string.gmatch(s, '[^\\n]+') do "
                "if string.len(l) > m then m = string.len(l) end end "
                "return math.min(2 * CAPE / AR, %s / (0.5 * m)) end)()" % (corner, maxw))
        g._add(nm, "TextPlus", G.CREATOR + [
            ("Center", bx("Point(%s, %s)" % (burn_x(hx), burn_y(is_top)))), ("Font", '"Open Sans"'),
            ("Style", '"Bold"'), ("Size", bt(size)), ("StyledText", bt("Text(CORNER(%d))" % corner)),
            ("Red1", "1"), ("Green1", "1"), ("Blue1", "1"),
            ("HorizontalLeftCenterRight", bx("(PBOX or LK.BAlign > 0.5) and 0 or %d" % hx)),
            ("HorizontalJustificationNew", bx("(PBOX or LK.BAlign > 0.5) and 3 or %d" % (0 if hx < 0 else 1))),
            ("VerticalJustificationNew", "3")])
        corners.append(nm)
    top = g.merge("MTop", top, g.chain("TTop", corners[:2]))
    top = g.merge("MBottom", top, g.chain("TBot", corners[2:]))
    # record TC grande (in basso al centro)
    g._add("Big", "TextPlus", G.CREATOR + [
        ("Center", bx("Point(PBOX and 1 - PB / 2 or 0.5, PBOX and 0.16 or (LBOX and LB + 0.06 or "
                      "(INSIDE and 0.15 or BAND + 0.055)))")),
        ("Font", '"Open Sans"'), ("Style", '"Bold"'),
        ("Size", bx("PBOX and math.min(10 * CAP / AR, 0.9 * PB / 4.8) or 10 * CAP / AR")),
        ("StyledText", bt("Text(BIG())")),
        ("Red1", "1"), ("Green1", "1"), ("Blue1", "1"),
        ("VerticalJustificationNew", "3"), ("HorizontalJustificationNew", "3")])
    top = g.gate("MBig", top, ["Big"], "LK.BBig > 0.5")
    g.text("Water", "{ 0.5, 0.5 }", "0.06",
           'Text(string.upper(LK.BWaterText.Value) .. (LK.BRecipient.Value == "" and "" or ("\\n" .. LK.BRecipient.Value)))',
           ["1", "1", "1"])
    top = g.gate("MWater", top, ["Water"], "LK.BWater > 0.5", mix="LK.BWaterAlpha")
    inputs = ([(x, "Burn-in") for x in ("SecBurn", "BPhase", "BUpdate", "BInfo", "BTitleText", "BVersionText",
                                        "BWaterText", "BRecipient")]
              + [(k, "Campi") for k, _ in BURN_FIELDS] + [("BFrameMode", "Campi")]
              + [(x, "Aspetto") for x in ("BMatte", "BMatteRatio", "BMatteAlpha", "BPos", "BAlign", "BSize",
                                          "BBands", "BBandAlpha", "BWaterAlpha")])
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
