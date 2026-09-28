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

LINE_W = 0.0025
# Interlinea dei Text+ a piu' righe rispetto all'altezza delle maiuscole di cap_size(): misurata in
# Resolve 21 (le maiuscole sono ~0.44 * Size * larghezza, la riga di Open Sans 1.36 em).
PITCH = 1.65
OUTLINE = [("Red2", "0"), ("Green2", "0"), ("Blue2", "0"), ("Alpha2", "1")]   # elemento 2 di Text+: contorno

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
    ("_PX", "local _PX = 1 / _H", ("_H",)),                              # un pixel in frazioni dell'altezza
    # diametro del cerchio del countdown (frazione della larghezza): min(0.62 H, 0.40 W), come la taratura
    ("_RD", "local _RD = math.min(0.62 / _A, 0.40)", ("_A",)),
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

    def text(self, name, center, size, styled, rgb, style="Bold", align="c", spacing=None, outline=None):
        """Text+; align: "c" centro, "l" ancorato a sinistra, "r" a destra, oppure (anchor, justify) in Lua.
        outline: (acceso, spessore) del contorno nero (elemento 2 di Text+), valori o espressioni."""
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
        if outline:
            ins += [("Enabled2", _v(outline[0])), ("Thickness2", _v(outline[1]))] + OUTLINE
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
GUIDE_COLOR = ("Guide", "Colore delle guide", (1.0, 1.0, 1.0))
GUIDE_GROUP = COLOR_GROUP_BASE + len(COLOR_DEFAULTS)


def color_controls():
    return "".join(uc_color(p, label, COLOR_GROUP_BASE + i, d) for i, (p, label, d) in enumerate(COLOR_DEFAULTS))


def control_group(src):
    for i, (p, _, _) in enumerate(COLOR_DEFAULTS + [GUIDE_COLOR]):
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
                 + "LK_GUIDES = %s\n" % lua_literal([[k, "ar", ar] for k, _, ar in FRAMELINES]
                                                    + [[k, "safe", pct] for k, pct, _ in SAFE_AREAS])
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
POST_FIELDS = [("Editor", "Montaggio", "EDITOR"), ("AsstEditor", "Assistente al montaggio", "ASSISTANT EDITOR"),
               ("Colorist", "Color", "COLORIST"),
               ("Sound", "Suono / mix", "SOUND"), ("VFXBy", "VFX", "VFX"), ("Version", "Versione", "VERSION")]
PHASES = ["—", "OFFLINE", "ONLINE / CONFORM", "GRADING", "MIX", "MASTER", "CONSEGNA"]
STATUSES = [("StColor", "Stato color", "COLOR"), ("StSound", "Stato suono", "SOUND"),
            ("StVFX", "Stato VFX", "VFX"), ("StMusic", "Stato musica", "MUSIC"), ("StTitles", "Stato titoli", "TITLES")]
STATUS_VALUES = ["—", "TEMP", "FINAL"]
FRAMELINES = [("FL133", "1.33", 4.0 / 3.0), ("FL166", "1.66", 1.66), ("FL178", "1.78", 16.0 / 9.0),
              ("FL185", "1.85", 1.85), ("FL200", "2.00", 2.0), ("FL220", "2.20", 2.2), ("FL239", "2.39", 2.39)]
SAFE_AREAS = [("SafeAction", 0.93, "SAFE ACTION 93%"), ("SafeTitle", 0.90, "SAFE TITLE 90%")]
GUIDE_KEYS = ["FLTL"] + [k for k, _, _ in FRAMELINES] + [k for k, _, _ in SAFE_AREAS]
# strumenti di taratura (SMPTE RP 428-6, EBU Tech 3325, ITU-R BT.814): chiave -> modulo di fx/overlay.lua
CALIBRATION = [("CalStars", "Stelle di Siemens negli angoli (fuoco)", 1),
               ("CalRes", "Righe 1-4 px e registrazione RGB (nitidezza, scalatura, convergenza)", 1),
               ("CalDiag", "Righe di 1 px annidate (mappatura 1:1 dei pixel)", 1),
               ("CalGamma", "Verifica del gamma (righe di 1 px e grigio del gamma)", 1),
               ("CalGrey", "Scala di grigi e neri 0-10%", 1), ("CalColor", "Colori RGBCMY 100% / 75%", 1),
               ("CalChecker", "ColorChecker 24 (sRGB)", 1), ("CalSkin", "Toni della pelle (scala Monk)", 1),
               ("CalRamps", "Rampe B/N, R, G, B", 1),
               ("CalBlue", "Verifica del blu (filtro Wratten 47B)", 1),
               ("CalContour", "Sfera divisa: alte luci e ombre (contouring)", 1),
               ("CalPeak", "Riferimenti del bianco (95% nel 100%) e del nero (5% nel 0%)", 1),
               ("CalEdge", "Bordo del raster, angoli e scale di overscan", 1),
               ("CalCenter", "Mirino centrale", 1), ("CalLabels", "Fotogrammi al secondo e risoluzione", 1)]
GAMMA_REFS = ["Dallo spazio colore di uscita", "2.2 (sRGB, web)", "2.4 (Rec.709 / BT.1886)", "2.6 (DCI, cinema)"]
LOGO_POS = ["In alto a destra", "In alto a sinistra", "In basso a destra", "In basso a sinistra", "Al centro"]
END_DOT_POS = ["In alto a destra (cue mark)", "Al centro", "In alto a sinistra"]
HIDDEN_NUM = ["LogoW", "LogoH", "Logo2W", "Logo2H", "TitleW", "TitleH"]
# immagini create da Genera e caricate nei Loader (percorso e dimensioni in pixel, input di servizio)
GEN_IMAGES = [("CalImage", "CalLd", "CalW", "CalH"), ("DialBImage", "DialBLd", "DialBW", "DialBH"),
              ("DialCImage", "DialCLd", "DialCW", "DialCH")]
HIDDEN_GEN = [k for im in GEN_IMAGES for k in im[2:]]


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
             "LogoOnTail", "SecCd", "CdLogo", "CdLogoSize", "CdInfo"] + [k for k, _, _, _ in CD_FIELDS]
            + ["SecLook"] + color_inputs())
    out += [(x, "Aspetto") for x in look]
    guides = (["SecGuides", "GuidesSlate", "GuidesCd", "FLTL"] + [f for f, _, _ in FRAMELINES]
              + [k for k, _, _ in SAFE_AREAS] + [GUIDE_COLOR[0] + ch for ch in ("Red", "Green", "Blue")]
              + ["SecEnd", "EndDot", "EndDotPos", "EndDotSize"])
    out += [(x, "Guide") for x in guides]
    tech = (["SecTech", "ColorInfo", "AudioFormat", "SecAudio", "PopLevel", "BeepEach", "SecCal", "CalOn", "CalGammaRef"]
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


def cap_size(cap, px=None):
    """Size di Text+ per un'altezza delle maiuscole pari a 'cap' (frazione dell'altezza).
    px: altezza minima delle maiuscole in pixel (leggibilita' su SD / 480p)."""
    if px:
        return "2 * math.max((%s) * _N, %s * _PX) / _A" % (cap, repr(px / 0.88))
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
    post = [("EDITOR", "LK.Editor.Value"), ("ASST. EDITOR", "LK.AsstEditor.Value"),
            ("COLORIST", "LK.Colorist.Value"), ("SOUND", "LK.Sound.Value"),
            ("VFX", "LK.VFXBy.Value"), ("VERSION", "LK.Version.Value"),
            ("PHASE", '(LK.Phase < 0.5 and "" or %s)' % PHASE_EXPR)]
    tech = [("DURATION", "LK.Duration.Value"),
            ("FORMAT", 'string.format("%d × %d   %.2f:1", _W, _H, _A)'),
            ("FRAME RATE", 'string.format("%g fps", comp:GetPrefs("Comp.FrameFormat.Rate"))'),
            ("COLOR", "LK.ColorInfo.Value"), ("AUDIO", "LK.AudioFormat.Value")]
    return [("PRODUCTION", 0.19, prod), ("POST", 0.5, post), ("TECHNICAL", 0.81, tech)]


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


def leader_stack(g, prefix, base, digit_expr, sweep_vis=None, cd=None, extras=()):
    """Cerchi e croce (un solo Background), braccio rotante e cifra centrale sopra 'base'.
    extras: (nome, livelli, condizione) messi sotto la cifra, ognuno con il suo gate."""
    g.mask(prefix + "RingO", "EllipseMask", X("_RD"), X("_RD"), border=repr(LINE_W * 1.6))
    g.mask(prefix + "RingI", "EllipseMask", X("_RD * 0.86"), X("_RD * 0.86"), border=repr(LINE_W),
           chain=prefix + "RingO")
    g.mask(prefix + "LineH", "RectangleMask", "1", X("%s * _A" % LINE_W), chain=prefix + "RingI")
    g.mask(prefix + "LineV", "RectangleMask", repr(LINE_W), "1", chain=prefix + "LineH")
    g.background(prefix + "Rings", color="Accent", mask=prefix + "LineV")
    top = g.merge(prefix + "M1", base, prefix + "Rings")
    if sweep_vis:
        g.mask(prefix + "Arm", "RectangleMask", repr(LINE_W * 1.6), X("_RD / 2 * _A"),
               center=X("Point(0.5, 0.5 + _RD / 4 * _A)"))
        g.background(prefix + "ArmBg", color="Accent", mask=prefix + "Arm")
        g.transform(prefix + "Sweep", prefix + "ArmBg", ex("-360 * math.fmod((%s) * _FPS - _REM, _FPS) / _FPS" % cd))
        top = g.gate(prefix + "ArmG", top, [prefix + "Sweep"], sweep_vis)
    for name, layers, cond in extras:
        top = g.gate(name, top, layers, cond)
    g.text(prefix + "Digit", "{ 0.5, 0.5 }", X("_RD * 0.30 / 0.36"), X(digit_expr), tint("Text"))
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


def info_groups(status=True):
    cols = slate_columns()
    prod, post, tech = [c[2] for c in cols]
    first = [("DIRECTOR", "LK.Director.Value")] + [f for f in prod if f[0] != "DATE"]
    second = post + ([("STATUS", status_expr())] if status else [])
    return [first, second, tech + [("DATE", DATE_EXPR % TODAY)], [("NOTE", "LK.Note.Value")]]


# Troncamento con "…" a m caratteri, senza spezzare i caratteri UTF-8 (niente string.byte:
# nelle espressioni di Fusion si usano solo le funzioni di string gia' provate).
CUT_FN = ("local function CUT(s, m) m = math.max(3, math.floor(m)) if string.len(s) <= m then return s end "
          "local k = m - 1 while k > 1 and string.match(s, '^[\\128-\\191]', k + 1) do k = k - 1 end "
          "return string.sub(s, 1, k) .. '…' end ")
# larghezza media di un carattere rispetto all'altezza delle maiuscole del modello (Open Sans, misurata):
# etichette maiuscole 0.80, testo misto 0.68, maiuscole Bold 0.72
CW_MIX, CW_CAPS = 0.68, 0.74
PX_MIN = 7                         # altezza minima delle maiuscole in pixel (modello): leggibile anche a 480p


def info_fn():
    """Lua: local function INFO() -> righe 'ETICHETTA   valore' (i gruppi separati da una riga vuota)."""
    adds = []
    for grp in info_groups(status=False):
        adds += ["a(%s, %s)" % (lua_string(lab), v) for lab, v in grp] + ["pend = true"]
    return ("local function INFO() local L, pend = {}, false "
            "local function a(l, v) v = tostring(v or '') if v ~= '' then "
            "if pend and #L > 0 then L[#L + 1] = '' end pend = false L[#L + 1] = l .. '   ' .. v end end "
            "%s return L end " % " ".join(adds))


def col_fn(fields):
    """Lua: local function COL() -> righe compilate di una colonna dei pannelli { {etichetta, valore}, ... }."""
    items = ", ".join("{ %s, %s }" % (lua_string(lab), v) for lab, v in fields)
    return ("local function COL() local L, list = {}, { %s } "
            "for i = 1, #list do local x = tostring(list[i][2] or '') if x ~= '' then L[#L + 1] = { list[i][1], x } end end "
            "return L end " % items)


def fit_cap(cap, width, chars, factor=CW_MIX, px=PX_MIN):
    """Lua: altezza delle maiuscole (frazione di H) che non supera 'cap', sta in 'width' (frazione di W)
    per 'chars' caratteri e non scende sotto 'px' pixel."""
    return ("math.max(math.min((%s) * _N, (%s) * _A / (%s * math.max(1, %s))), %s * _PX)"
            % (cap, width, factor, chars, px))


def text_fit(g, name, center, cap, width, text, rgb, style="Bold", px=PX_MIN, factor=None, align="c", pre=""):
    """Text+ di una riga (o poche) che si riduce per stare in 'width' (frazione di W), mai sotto 'px'."""
    factor = factor or (CW_CAPS if style == "Bold" else CW_MIX)
    p = pre + "local _T = %s local _ML = 1 for l in string.gmatch(_T, '[^\\n]+') do " \
              "if string.len(l) > _ML then _ML = string.len(l) end end " % text
    p += "local _C = %s " % fit_cap(cap, width, "_ML", factor, px)
    return g.text(name, X(center, p) if "Point(" in center else center, X("2 * _C / _A", p), ex("Text(_T)", p),
                  rgb, style=style, align=align)


def hand(g, name, cx, cy, rexpr, f0, f1, width, angle, color="Hi"):
    """Lancetta da f0 a f1 del raggio R (espressione, frazione dell'altezza) attorno a (cx, cy)."""
    pre = "local R = %s " % rexpr
    g.mask(name + "M", "RectangleMask", repr(width), X("R * %s" % repr(f1 - f0), pre),
           center=X("Point(%s, %s + R * %s)" % (cx, cy, repr((f0 + f1) / 2)), pre))
    g.background(name + "Bg", color=color, mask=name + "M")
    return g.transform(name, name + "Bg", ex(angle), pivot="{ %s, %s }" % (cx, cy))


def status_chips(g, prefix, y, pre="", chain=True, cx="0.5", width="0.94"):
    """Stato dei reparti: COLOR · FINAL (verde) / TEMP (colore evidenza), affiancati e centrati in cx,
    nella larghezza 'width' (frazione di W). Se alla grandezza minima non stanno in una riga vanno su due."""
    n = " + ".join("(LK.%s > 0.5 and 1 or 0)" % f for f, _, _ in STATUSES)
    geo = pre + ("local _n = %s local _w = %s local _C = math.min(0.0135 * _N, 0.135 * _A * 0.86 / (%s * 13)) "
                 "local _pr = math.max(1, _n) local _need = %s * 13 * math.max(_C, 6.5 * _PX) / 0.86 / _A "
                 "if _need * _n > _w and _n > 2 then _pr = math.ceil(_n / 2) end "
                 "local _st = math.min(0.135, _w / math.max(1, _pr)) "
                 "_C = math.max(math.min(_C, _st * 0.86 * _A / (%s * 13)), 6.5 * _PX) "
                 % (n, width, CW_CAPS, CW_CAPS, CW_CAPS))
    nodes = []
    for i, (f, _, lab) in enumerate(STATUSES):
        k = " + ".join(["0"] + ["(LK.%s > 0.5 and 1 or 0)" % x for x, _, _ in STATUSES[:i]])
        fin = "LK.%s > 1.5" % f
        rgb = ["((%s) and 0.40 or LK.HiRed)" % fin, "((%s) and 0.85 or LK.HiGreen)" % fin,
               "((%s) and 0.45 or LK.HiBlue)" % fin]
        pos = geo + ("local _k = %s local _row = math.floor(_k / _pr) local _col = _k - _row * _pr "
                     "local _nr = (_row == 0) and math.min(_pr, _n) or (_n - _pr) " % k)
        nodes.append(g.text("%s%d" % (prefix, i),
                            X("Point(%s + (_col - (_nr - 1) / 2) * _st, %s - _row * %s * _C)" % (cx, y, PITCH + 0.6), pos),
                            X("2 * _C / _A", geo),
                            ex('Text(LK.%s > 0.5 and ("%s  ·  " .. ({ "-", "TEMP", "FINAL" })[math.floor(LK.%s + 1.5)]) or "")'
                               % (f, lab, f)), rgb))
    return g.chain(prefix + "C", nodes) if chain else nodes


def footer_text(static):
    return 'Text(LK.Info.Value .. ((%s) == "" and "" or ("\\n" .. %s)))' % (static, static)


def footer(g, name, static, note=False, top=None, x="0.5", width="0.94"):
    """Piede: timecode (FFOA / 2-POP / LFOA) e righe fisse dello standard. Ancorato in basso (sopra il
    margine del 3.5%) o, con 'top', sotto quell'ordinata; si riduce per stare nella larghezza."""
    s = 'LK.Info.Value .. (_S == "" and "" or ("\\n" .. _S))'
    if note:
        s += ' .. (LK.Note.Value == "" and "" or ("\\n" .. LK.Note.Value))'
    pre = ("local _S = %s local _T = %s local _n, _ML = 0, 1 for l in string.gmatch(_T, '[^\\n]+') do _n = _n + 1 "
           "if string.len(l) > _ML then _ML = string.len(l) end end _n = math.max(1, _n) " % (static, s))
    pre += "local _C = %s " % fit_cap("0.0135", width, "_ML", CW_MIX, 6.5)
    y = ("(%s) - _C / 2 - (_n - 1) * %s * _C / 2" % (top, PITCH)) if top else \
        ("0.035 + _C / 2 + (_n - 1) * %s * _C / 2" % PITCH)
    return g.text(name, X("Point(%s, %s)" % (x, y), pre), X("2 * _C / _A", pre), ex("Text(_T)", pre),
                  tint("Text", 0.72), style="Regular")


# ------------------------------------------------------------------ stili della slate
SLATE_STYLES = ["Pannelli (produzione / post / tecnico)", "Quadrante (fotogrammi, dati a destra)",
                "Orologio (titolo e dati a destra)", "Minimale (titolo al centro)"]
# riquadro del titolo in PNG per stile: (x, y, larghezza, altezza, ancora) in frazioni del quadro;
# ancora "center" = x e' il centro, "left" = x e' il bordo sinistro.
TITLE_BOXES = [(0.5, 0.815, 0.60, 0.11, "center"), (0.53, 0.845, 0.42, 0.10, "left"),
               (0.58, 0.80, 0.38, 0.16, "left"), (0.5, 0.60, 0.70, 0.18, "center")]
# quadranti: centro x (W), centro y (H), raggio (espressione, frazione di H): stretti sui formati stretti
DIAL_B = (0.27, 0.5, "math.min(0.36, 0.22 * _A)")
DIAL_C = (0.28, 0.5, "math.min(0.31, 0.20 * _A)")

PANEL_W = 0.295
PANEL_TOP = 0.645
PANEL_ROWS = 8                     # pannelli ad altezza fissa: 8 righe (la colonna piu' lunga)
T_CAP = 0.0145                     # altezza delle maiuscole nelle tabelle dei pannelli
TABLE_TOP = PANEL_TOP - 0.062      # prima riga delle tabelle
PANEL_BOTTOM = round(TABLE_TOP - PANEL_ROWS * PITCH * T_CAP - 0.03, 4)


def slate_panels(g, P, base, static):
    """Pannelli: titolo, regia, tre pannelli (produzione / post / tecnico) come tabelle
    etichetta-valore (2 Text+ per pannello), stato dei reparti e piede con i timecode.

    Leggero: pannelli ad altezza fissa (maschere senza espressioni) e ogni Text+ legge solo
    i campi della sua colonna. La colonna delle etichette e' larga quanto l'etichetta piu' lunga,
    i valori troppo lunghi per il pannello vengono troncati con "…"."""
    heading = pv(P, "heading")
    cols = slate_columns()
    fill, line = None, None
    height = PANEL_TOP - PANEL_BOTTOM
    for i, (_, cx, _) in enumerate(cols):
        fill = g.mask("SPan%dM" % i, "RectangleMask", repr(PANEL_W), repr(height),
                      center="{ %s, %s }" % (cx, (PANEL_TOP + PANEL_BOTTOM) / 2), chain=fill)
        line = g.mask("SPanL%dM" % i, "RectangleMask", repr(PANEL_W), repr(LINE_W),
                      center="{ %s, %s }" % (cx, PANEL_TOP), chain=line)
    line = g.mask("SRuleM", "RectangleMask", "0.18", repr(LINE_W * 1.2), center="{ 0.5, 0.69 }", chain=line)
    g.background("SPanFill", rgb=["math.min(1, LK.BgRed + 0.045)", "math.min(1, LK.BgGreen + 0.045)",
                                  "math.min(1, LK.BgBlue + 0.045)"], mask=fill)
    g.background("SAccent", color="Hi", mask=line)
    top = g.merge("SMP", base, "SPanFill")
    top = g.merge("SMA", top, "SAccent")
    # intestazione, titolo, regia
    text_fit(g, "SHeading", "{ 0.5, 0.925 }", "0.016", "0.9", '%s .. "   ·   LEADERKIT"' % heading, tint("Hi"))
    title_size = X("math.max(math.min(2 * 0.068 / _A * _N, 1.9 / math.max(1, string.len(LK.Title.Value))), 2 * 12 * _PX / _A)")
    g.text("STitle", "{ 0.5, 0.815 }", title_size,
           ex('Text(%s and string.upper(LK.Title.Value) or "")' % NO_TITLE_IMG), tint("Text"))
    text_fit(g, "SDirector", "{ 0.5, 0.735 }", "0.024", "0.9",
             '(LK.Director.Value == "" and "" or ("DIRECTED BY   " .. string.upper(LK.Director.Value)))',
             tint("Text", 0.9), style="Regular", factor=CW_CAPS)
    top = g.merge("SMH", top, g.chain("SHd", ["SHeading", "STitle", "SDirector"]))
    # colonne: intestazione, etichette e valori allineati riga per riga
    texts = []
    inner = PANEL_W - 0.032
    for i, (title, cx, fields) in enumerate(cols):
        xl = cx - PANEL_W / 2 + 0.016
        pre = (col_fn(fields) + CUT_FN + "local L = COL() local n, mll, mlv = #L, 1, 1 "
               "for i = 1, n do mll = math.max(mll, string.len(L[i][1])) mlv = math.max(mlv, string.len(L[i][2])) end "
               "local PW = %s * _A local cap0 = %s * _N "
               "local f = math.max(0.7, math.min(1, %d / math.max(1, n), PW / ((0.80 * mll + 1.2 + %s * mlv) * cap0))) "
               "local cap = math.max(cap0 * f, %s * _PX) local LW = (0.80 * mll + 1.2) * cap "
               "local mc = (PW - LW) / (%s * cap) local l, v = '', '' "
               "for i = 1, n do l = l .. (i > 1 and '\\n' or '') .. L[i][1] v = v .. (i > 1 and '\\n' or '') .. CUT(L[i][2], mc) end "
               "local pitch = %s * cap "
               % (repr(inner), T_CAP, PANEL_ROWS, CW_MIX, PX_MIN, CW_MIX, PITCH))
        block_y = "%s - (n - 1) * pitch / 2" % TABLE_TOP
        g.text("SCol%d" % i, "{ %s, %s }" % (xl, PANEL_TOP - 0.032), X(cap_size(0.0125, 6.5)), 'Text("%s")' % title,
               tint("Hi"), align="l")
        g.text("SLab%d" % i, X("Point(%s, %s)" % (xl, block_y), pre), X("2 * cap / _A", pre),
               ex("Text(l)", pre), tint("Text", 0.55), style="Regular", align="l")
        g.text("SVal%d" % i, X("Point(%s + LW / _A, %s)" % (xl, block_y), pre), X("2 * cap / _A", pre),
               ex("Text(v)", pre), tint("Text"), style="Semibold", align="l")
        texts += ["SCol%d" % i, "SLab%d" % i, "SVal%d" % i]
    top = g.merge("SMC", top, g.chain("SCo", texts))
    # stato dei reparti sotto i pannelli, poi il piede (sotto lo stato)
    chips = status_chips(g, "SSt", repr(PANEL_BOTTOM - 0.05), chain=False)
    foot = footer(g, "SFoot", static, note=True,
                  top="%s - (%s and 0.085 or 0.04)" % (PANEL_BOTTOM, ANY_STATUS))
    return g.merge("SMB", top, g.chain("SBt", chips + [foot]))


def info_block(g, name, x, x1, y0, cap, ymin):
    """Dati (una riga 'ETICHETTA   valore' per campo compilato) tra y0 (prima riga) e ymin, da x a x1:
    su due colonne se in una sola diventerebbero troppo piccoli; righe troppo lunghe troncate con "…".
    Ritorna i due Text+ (colonne)."""
    pre = (info_fn() + CUT_FN +
           "local L = INFO() local n = #L local W1, HH = (%s - %s) * _A, %s - %s "
           "local function ML(a, b) local m = 1 for i = a, b do m = math.max(m, string.len(L[i])) end return m end "
           "local ea, sb, cw = n, n + 1, W1 "
           "local c = math.min(%s * _N, HH / (%s * math.max(0, n - 1) + 1), W1 / (%s * ML(1, n))) "
           "if n > 8 and c < 0.8 * %s * _N then "
           "local best, bd = nil, 1e9 for i = 2, n - 1 do "
           "if L[i] == '' and math.abs(i - (n + 1) / 2) < bd then best, bd = i, math.abs(i - (n + 1) / 2) end end "
           "if best then ea, sb = best - 1, best + 1 else ea = math.floor(n / 2) sb = ea + 1 end "
           "cw = W1 / 2 - 0.015 * _A "
           "c = math.min(%s * _N, HH / (%s * math.max(ea, n - sb + 1) - %s + 1), cw / (%s * math.max(ML(1, ea), ML(sb, n)))) end "
           "c = math.max(c, %s * _PX) local mc = cw / (%s * c) "
           "local function J(a, b) local s = '' for i = a, b do s = s .. (i > a and '\\n' or '') .. CUT(L[i], mc) end return s end "
           % (x1, x, y0, ymin, cap, PITCH, CW_MIX, cap, cap, PITCH, PITCH, CW_MIX, PX_MIN, CW_MIX))
    out = []
    for k, (a, b, xx) in enumerate([("1", "ea", x), ("sb", "n", "%s + (%s - %s) / 2 + 0.0075" % (x, x1, x))]):
        nm = name if k == 0 else name + "2"
        rows = "(%s - %s + 1)" % (b, a)
        g.text(nm, X("Point(%s, %s - (%s - 1) * %s * c / 2)" % (xx, y0, rows, PITCH), pre),
               X("2 * c / _A", pre), ex("Text(%s <= %s and J(%s, %s) or '')" % (a, b, a, b), pre),
               tint("Text", 0.92), style="Regular", align="l")
        out.append(nm)
    return out


def dial_layer(ld, kind):
    """PNG del quadrante (disegnato da Genera) centrato sul quadrante, alla scala del quadro."""
    cx, cy, r = DIAL_B if kind == "b" else DIAL_C
    pre = "local R = %s local S = 2 * math.ceil(R * _H * 1.04 + 2) " % r
    key = "Dial%s" % kind.upper()
    return (ld, X("Point(%s, %s)" % (cx, cy)), X("S / math.max(1, LK.%sW)" % key, pre))


def dial_cond(kind):
    key = "Dial%s" % kind.upper()
    return 'LK.%sImage.Value ~= "" and LK.%sW > 0' % (key, key)


def slate_style_b(g, P, base, static):
    """Quadrante: a sinistra il quadrante dei fotogrammi del secondo (PNG di Genera nel Loader DialBLd)
    con la tacca che gira, i secondi e i fotogrammi al FFOA; a destra titolo, standard, dati e stato."""
    cx, cy, r = DIAL_B
    R = "local R = %s " % r
    top = g.gate("BDial", base, [dial_layer("DialBLd", "b")], dial_cond("b"))
    # senza PNG (Genera non ancora premuto): la corona resta comunque visibile
    g.mask("BRingO", "EllipseMask", X("R * 2 / _A", R), X("R * 2 / _A", R), center="{ %s, %s }" % (cx, cy),
           border=repr(LINE_W * 1.6))
    g.mask("BRingI", "EllipseMask", X("R * 1.6 / _A", R), X("R * 1.6 / _A", R), center="{ %s, %s }" % (cx, cy),
           border=repr(LINE_W), chain="BRingO")
    g.background("BRingBg", color="Accent", mask="BRingI")
    top = g.gate("BRingG", top, ["BRingBg"], "not (%s)" % dial_cond("b"))
    top = g.merge("BMh", top, hand(g, "BHand", cx, cy, r, 0.66, 0.785, 0.007,
                                   "-360 * (_FPS - 1 - ((_REM - 1) % _FPS)) / _FPS"))
    g.text("BFps", X("Point(%s, %s + 0.43 * R)" % (cx, cy), R), X("2 * math.max(0.052 * R, 6.5 * _PX) / _A", R),
           'Text(string.format("SEC / %g FPS", comp:GetPrefs("Comp.FrameFormat.Rate")))', tint("Text", 0.8))
    g.text("BSec", X("Point(%s, %s + 0.08 * R)" % (cx, cy), R), X("2 * 0.40 * R / _A", R),
           ex("Text(tostring(math.ceil(_REM / _FPS)))"), tint("Text"))
    g.text("BFrames", X("Point(%s, %s - 0.27 * R)" % (cx, cy), R), X("2 * 0.13 * R / _A", R),
           ex("Text(tostring(_REM))"), tint("Text", 0.85), style="Light")
    g.text("BFramesL", X("Point(%s, %s - 0.43 * R)" % (cx, cy), R), X("2 * math.max(0.045 * R, 6.5 * _PX) / _A", R),
           'Text("FRAMES TO FFOA")', tint("Text", 0.6), style="Regular")
    x, x1 = 0.53, 0.97
    g.text("BTitle", "{ %s, 0.845 }" % x,
           X("math.max(math.min(2 * 0.05 / _A * _N, 1.15 / math.max(1, string.len(LK.Title.Value))), 2 * 9 * _PX / _A)"),
           ex('Text(%s and string.upper(LK.Title.Value) or "")' % NO_TITLE_IMG), tint("Text"), align="l")
    text_fit(g, "BHead", "{ %s, 0.765 }" % x, "0.016", repr(x1 - x), pv(P, "heading"), tint("Hi"), align="l")
    info = info_block(g, "BInfo", x, x1, "0.70", 0.0175, "0.28")
    chips = status_chips(g, "BSt", "0.225", chain=False, cx=repr((x + x1) / 2), width=repr(x1 - x))
    foot = footer(g, "Foot1", static)
    return g.merge("BMt", top, g.chain("BTx", ["BFps", "BSec", "BFrames", "BFramesL", "BTitle", "BHead"] + info
                                       + chips + [foot]))


def slate_style_c(g, P, base, static):
    """Orologio: cerchio con lancetta dei secondi al FFOA (tacche e numeri: PNG di Genera nel Loader
    DialCLd); a destra titolo (testo o PNG), intestazione, dati e stato."""
    cx, cy, r = DIAL_C
    R = "local R = %s " % r
    g.mask("CRing", "EllipseMask", X("R * 2 / _A", R), X("R * 2 / _A", R), center="{ %s, %s }" % (cx, cy),
           border=repr(LINE_W * 0.8))
    g.mask("CHub", "EllipseMask", X("R * 0.56 / _A", R), X("R * 0.56 / _A", R), center="{ %s, %s }" % (cx, cy),
           border=repr(LINE_W * 0.8), chain="CRing")
    g.background("CRingBg", color="Accent", mask="CHub")
    top = g.merge("CMr", base, "CRingBg")
    top = g.gate("CDial", top, [dial_layer("DialCLd", "c")], dial_cond("c"))
    top = g.merge("CMa", top, hand(g, "CHand", cx, cy, r, 0.30, 0.93, 0.0022,
                                   "-6 * math.floor((_REM - 1) / _FPS)", color="Text"))
    g.text("CSec", "{ %s, %s }" % (cx, cy), X("2 * 0.15 * R / _A", R), ex("Text(tostring(math.ceil(_REM / _FPS)))"),
           tint("Text"))
    x, x1 = 0.58, 0.97
    g.text("CTitle", "{ %s, 0.80 }" % x,
           X("math.max(math.min(2 * 0.06 / _A * _N, 1.0 / math.max(1, string.len(LK.Title.Value))), 2 * 9 * _PX / _A)"),
           ex('Text(%s and string.upper(LK.Title.Value) or "")' % NO_TITLE_IMG), tint("Hi"), align="l")
    text_fit(g, "CHead", "{ %s, 0.69 }" % x, "0.016", repr(x1 - x), pv(P, "heading"), tint("Text", 0.8), align="l")
    info = info_block(g, "CInfo", x, x1, "0.625", 0.017, "0.28")
    chips = status_chips(g, "CSt", "0.225", chain=False, cx=repr((x + x1) / 2), width=repr(x1 - x))
    foot = footer(g, "Foot2", static)
    return g.merge("CMt", top, g.chain("CTx", ["CSec", "CTitle", "CHead"] + info + chips + [foot]))


def slate_style_d(g, P, base, static):
    """Minimale: titolo grande al centro, regia, filo, una riga di dati essenziali e i timecode."""
    g.mask("DRule", "RectangleMask", "0.12", repr(LINE_W * 1.2), center="{ 0.5, 0.42 }")
    g.background("DRuleBg", color="Hi", mask="DRule")
    top = g.merge("DMr", base, "DRuleBg")
    text_fit(g, "DHead", "{ 0.5, 0.80 }", "0.016", "0.9", pv(P, "heading"), tint("Hi"))
    g.text("DTitle", "{ 0.5, 0.60 }",
           X("math.max(math.min(2 * 0.09 / _A * _N, 2.2 / math.max(1, string.len(LK.Title.Value))), 2 * 12 * _PX / _A)"),
           ex('Text(%s and string.upper(LK.Title.Value) or "")' % NO_TITLE_IMG), tint("Text"))
    text_fit(g, "DDir", "{ 0.5, 0.47 }", "0.024", "0.9",
             '(LK.Director.Value == "" and "" or ("DIRECTED BY   " .. string.upper(LK.Director.Value)))',
             tint("Text", 0.85), style="Regular", factor=CW_CAPS)
    parts = ["LK.Version.Value", "LK.Duration.Value", DATE_EXPR % TODAY,
             'string.format("%g fps", comp:GetPrefs("Comp.FrameFormat.Rate"))',
             'string.format("%d × %d", _W, _H)', "LK.ColorInfo.Value", "LK.AudioFormat.Value"]
    line = ("(function() local s = '' local function a(v) v = tostring(v or '') "
            "if v ~= '' then if s ~= '' then s = s .. '   ·   ' end s = s .. v end end "
            + " ".join("a(%s)" % p for p in parts) + " return s end)()")
    text_fit(g, "DLine", "{ 0.5, 0.36 }", "0.016", "0.94", line, tint("Text", 0.9), style="Regular")
    who = ("(function() local s = '' local function a(l, v) if v ~= '' then if s ~= '' then s = s .. '      ' end "
           "s = s .. l .. '  ' .. v end end a('PRODUCTION', LK.Production.Value) a('PRODUCER', LK.Producer.Value) "
           "a('EDITOR', LK.Editor.Value) a('CLIENT', LK.Client.Value) return s end)()")
    text_fit(g, "DWho", "{ 0.5, 0.31 }", "0.0135", "0.94", who, tint("Text", 0.65), style="Regular", px=6.5)
    foot = footer(g, "Foot3", static)
    top = g.merge("DMt", top, g.chain("DTx", ["DHead", "DTitle", "DDir", "DLine", "DWho", foot]))
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


# ------------------------------------------------------------------ logo e dati sul countdown
# spunta, etichetta, default, (etichetta sullo schermo, valore) per i ruoli della seconda riga
CD_FIELDS = [("CdTitle", "Titolo", 1, None), ("CdVersion", "Versione", 0, None),
             ("CdDirector", "Regia", 1, ("DIRECTOR", "LK.Director.Value")),
             ("CdProduction", "Produzione", 1, ("PRODUCTION", "LK.Production.Value")),
             ("CdEditor", "Montaggio", 1, ("EDITOR", "LK.Editor.Value")),
             ("CdAsst", "Assistente al montaggio", 1, ("ASST. EDITOR", "LK.AsstEditor.Value")),
             ("CdColorist", "Color", 0, ("COLORIST", "LK.Colorist.Value")),
             ("CdSound", "Suono", 0, ("SOUND", "LK.Sound.Value")),
             ("CdCode", "Codice", 0, ("CODE", "LK.Code.Value")),
             ("CdDate", "Data", 0, ("DATE", DATE_EXPR % TODAY))]
# spazio libero sopra e sotto il cerchio del countdown (frazione dell'altezza)
CD_SPACE = "local SP = math.max(0.02, (1 - _RD * _A) / 2) "
BOX_LW = "local blw = math.max(1, math.floor(_H / 1080 * 2 + 0.5)) "
# riquadro del logo (pixel): alto 0.72 dello spazio sopra il cerchio x la dimensione scelta (al massimo il 14%
# del lato corto), largo quanto serve al logo (da quadrato a 2.6 volte l'altezza, mai piu' del cerchio)
CD_LOGO = (CD_SPACE + BOX_LW + "local iw, ih = math.max(1, LK.LogoW), math.max(1, LK.LogoH) "
           "local bh = math.min(0.72 * SP * _H, 0.2 * math.min(_W, _H)) * math.min(1.4, math.max(0.2, LK.CdLogoSize / 100)) "
           "bh = math.max(8, math.floor(bh / 2 + 0.5) * 2) "
           "local pad = math.floor(0.13 * bh + 0.5) local lh = bh - 2 * pad local lw = lh * iw / ih "
           "local mw = math.min(2.6 * bh, _RD * _W) - 2 * pad if lw > mw then lw = mw lh = lw * ih / iw end "
           "local bw = math.max(bh, math.floor((lw + 2 * pad) / 2 + 0.5) * 2) local cy = 1 - SP / 2 ")


def cd_data_pre():
    """Lua: dati sotto il cerchio (titolo / versione, poi i ruoli scelti) e il loro riquadro in pixel,
    stretto sul testo. I ruoli vanno due per riga o uno per riga, come vengono piu' grandi."""
    roles = " ".join("r(LK.%s, %s, %s)" % (key, lua_string(lab), v) for key, _, _, rv in CD_FIELDS if rv
                     for lab, v in [rv])
    return (CD_SPACE + BOX_LW +
            "local R, a = {}, '' "
            "local function r(on, l, v) v = tostring(v or '') if on > 0.5 and v ~= '' then R[#R + 1] = l .. '  ' .. v end end "
            "if LK.CdTitle > 0.5 and LK.Title.Value ~= '' then a = string.upper(LK.Title.Value) end "
            "if LK.CdVersion > 0.5 and LK.Version.Value ~= '' then a = a .. (a ~= '' and '   ·   ' or '') .. LK.Version.Value end "
            + roles + " "
            "local MW, MH = _RD * _W * 0.98, math.min(0.80 * SP * _H, 0.36 * math.min(_W, _H)) local pad = 0.12 * MH "
            "local function lay(k) local s, n, ml = a, (a ~= '' and 1 or 0), string.len(a) "
            "for i = 1, #R, k do local l = R[i] if k == 2 and R[i + 1] then l = l .. '      ' .. R[i + 1] end "
            "s = s .. (s ~= '' and '\\n' or '') .. l n = n + 1 ml = math.max(ml, string.len(l)) end "
            "local c = math.min(0.018 * _N * _H, (MH - 2 * pad) / (0.88 + %s * math.max(0, n - 1)), "
            "(MW - 2 * pad) / (0.70 * math.max(1, ml))) return s, n, ml, c end "
            "local s1, n1, m1, c1 = lay(2) local s2, n2, m2, c2 = lay(1) "
            "local S, N, ML, CP = s1, n1, m1, c1 if c2 > c1 * 1.12 then S, N, ML, CP = s2, n2, m2, c2 end "
            "CP = math.max(CP, 6.5) "
            "local dw = math.floor(math.min(MW, 0.70 * ML * CP + 2 * pad + 0.6 * CP) / 2 + 0.5) * 2 "
            "local dh = math.floor(math.min(MH, (0.88 + %s * math.max(0, N - 1)) * CP + 2 * pad) / 2 + 0.5) * 2 "
            % (PITCH, PITCH))


def countdown_extras(g):
    """Logo sopra il cerchio e dati sotto, ognuno in un riquadro nero con il bordo nel colore della
    grafica (come i moduli della taratura), sopra frame lines e taratura; nella colonna del cerchio."""
    logo_on = "LK.CdLogo > 0.5 and " + logo_cond("")
    info_on = "LK.CdInfo > 0.5"
    data = cd_data_pre()
    # riquadri: un Background nero e uno per i bordi, maschere in catena accese dal loro interruttore
    g.mask("CdBoxLF", "RectangleMask", X("bw / _W", CD_LOGO), X("bh / _H", CD_LOGO), center=X("Point(0.5, cy)", CD_LOGO),
           level=X("(%s) and 1 or 0" % logo_on))
    g.mask("CdBoxDF", "RectangleMask", X("dw / _W", data), X("dh / _H", data), center=X("Point(0.5, SP / 2)", data),
           level=X("(%s and N > 0) and 1 or 0" % info_on, data), chain="CdBoxLF")
    g.mask("CdBoxLB", "RectangleMask", X("(bw - blw) / _W", CD_LOGO), X("(bh - blw) / _H", CD_LOGO),
           center=X("Point(0.5, cy)", CD_LOGO), border=X("blw / _W", CD_LOGO), level=X("(%s) and 1 or 0" % logo_on))
    g.mask("CdBoxDB", "RectangleMask", X("(dw - blw) / _W", data), X("(dh - blw) / _H", data),
           center=X("Point(0.5, SP / 2)", data), border=X("blw / _W", data),
           level=X("(%s and N > 0) and 1 or 0" % info_on, data), chain="CdBoxLB")
    g.background("CdBoxFill", rgb=["0", "0", "0"], mask="CdBoxDF")
    g.background("CdBoxLine", color="Accent", mask="CdBoxDB")
    logo = ("Logo1Ld", X("Point(0.5, cy)", CD_LOGO), X("lw / iw", CD_LOGO))
    g.text("CdText", X("Point(0.5, SP / 2)", data), X("2 * CP / _W", data), ex("Text(S)", data), tint("Text", 0.92))
    return [("CdBoxG", ["CdBoxFill", "CdBoxLine"], "(%s) or (%s)" % (logo_on, info_on)),
            ("CdLogoG", [logo], logo_on),
            ("CdInfoG", ["CdText"], info_on)]


# ------------------------------------------------------------------ frame lines e safe area
GUIDE_CAP = 0.014


def guides_layer(g):
    """Frame lines (formato della timeline e formati scelti) e safe area: contorni a pixel interi,
    con l'etichetta 'formato · risoluzione reale nella timeline'. Un solo Background per le linee."""
    fmts = [("FLTL", None, None)] + [(k, lab + ":1", ar) for k, lab, ar in FRAMELINES]
    flist = "{ %s }" % ", ".join("{ LK.%s, %s }" % (k, repr(ar) if ar else "0") for k, _, ar in fmts)
    lw = "local lw = math.max(1, math.floor(_H / 1080 * 2 + 0.5)) "
    pos = ("local cap = %s * _H local pad = 0.008 * _H local st = %s * cap " % (GUIDE_CAP, PITCH))
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
        # le etichette partono dopo il triangolo d'angolo della taratura (0.022 del lato corto)
        where = ("local tri = 0.026 * math.min(_W, _H) local x, y = (lw + pad) / _W, (lw + pad + cap / 2 + k * st) / _H "
                 "if me == 1 then x = (lw + pad + tri + k * 19 * cap) / _W y = 1 - ((_H - ah) / 2 + lw + pad + cap / 2) / _H "
                 "elseif me == 2 then x = ((_W - aw) / 2 + lw + pad) / _W "
                 "y = (lw + pad + cap / 2 + (nfull + k) * st) / _H end ")
        if ar:
            label = 'on and string.format("%s  ·  %%d × %%d", aw, ah) or ""' % lab
        else:
            label = 'on and string.format("TIMELINE %.2f:1  ·  %d × %d", _A, aw, ah) or ""'
        labels.append(g.text("G%sT" % key, X("Point(x, y)", geo + cls + stack + pos + where), X("2 * %s / _A" % GUIDE_CAP),
                             ex("Text(%s)" % label, geo), tint("Guide"), align="l", outline=("1", "0.1")))
    for key, pct, lab in SAFE_AREAS:
        geo = ("local aw, ah = 2 * math.floor(_W * %s / 2 + 0.5), 2 * math.floor(_H * %s / 2 + 0.5) " % (pct, pct)
               + lw + "local on = LK.%s > 0.5 " % key)
        chain = g.mask("G%sM" % key, "RectangleMask", X("on and (aw - lw) / _W or 0", geo),
                       X("on and (ah - lw) / _H or 0", geo), border=X("lw / _W", geo), chain=chain,
                       level=X("on and 1 or 0", geo))
        pre = geo + pos
        labels.append(g.text("G%sT" % key, X("Point(((_W - aw) / 2 + lw + pad) / _W, 1 - ((_H - ah) / 2 + lw + pad + cap / 2) / _H)", pre),
                             X("2 * %s / _A" % GUIDE_CAP), ex('Text(on and "%s" or "")' % lab, pre),
                             tint("Guide", 0.85), align="l", outline=("1", "0.1")))
    g.background("GLines", color="Guide", mask=chain)
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
            + uc_label("SecCd", "Countdown: logo sopra il cerchio, dati sotto")
            + uc_check("CdLogo", "Logo sopra il countdown (riquadro nero)", 0)
            + uc_slider("CdLogoSize", "Dimensione del riquadro del logo (%)", 20, 140, 70, integer=False)
            + uc_check("CdInfo", "Dati sotto il countdown (riquadro nero)", 0)
            + "".join(uc_check(k, "  " + lab, d) for k, lab, d, _ in CD_FIELDS)
            + uc_label("SecLook", "Colori") + color_controls())
    guide = (uc_label("SecGuides", "Frame lines e safe area (a pixel interi)")
             + uc_check("GuidesSlate", "Sulla slate (sotto i testi)", 1)
             + uc_check("GuidesCd", "Sul countdown e la taratura (Genera impagina la taratura dentro)", 1)
             + uc_check("FLTL", "Formato della timeline", 0)
             + "".join(uc_check(f, "Frame line " + lab + ":1", 0) for f, lab, _ in FRAMELINES)
             + uc_check("SafeAction", "Safe action 93% (EBU R95)", 0) + uc_check("SafeTitle", "Safe title 90%", 0)
             + uc_color(GUIDE_COLOR[0], GUIDE_COLOR[1], GUIDE_GROUP, GUIDE_COLOR[2])
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
            + uc_combo("CalGammaRef", "Gamma di riferimento", GAMMA_REFS)
            + "".join(uc_check(f, label, d) for f, label, d in CALIBRATION))
    hidden = "".join(uc_hidden(k) for k in HIDDEN_NUM + HIDDEN_GEN) + "".join(uc_hidden(im[0], "Text") for im in GEN_IMAGES)
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
              ("LogoOnTail", "0"), ("CalOn", "1"), ("CalGammaRef", "0"), ("CdLogo", "0"), ("CdLogoSize", "70"), ("CdInfo", "0")]
    values += [(k, str(d)) for k, _, d, _ in CD_FIELDS]
    values += [(i, str(std.get("slot_defaults", {}).get(c, 0))) for c, i, _ in SLOT_INPUTS]
    values += [(f, '""') for f, _, _ in PRODUCTION_FIELDS + POST_FIELDS if f not in ("Title", "Version")]
    values += [(f, "0") for f, _, _ in STATUSES]
    values += [(f, "0") for f, _, _ in FRAMELINES]
    values += [(f, str(d)) for f, _, d in CALIBRATION]
    values += [(k, "0") for k in HIDDEN_NUM + HIDDEN_GEN] + [(im[0], '""') for im in GEN_IMAGES]
    values += color_values() + [(GUIDE_COLOR[0] + ch, repr(v)) for ch, v in zip(("Red", "Green", "Blue"), GUIDE_COLOR[2])]

    g = G()
    g.controls(values, uc)
    g.loader("TitleLd")
    g.loader("Logo1Ld")
    g.loader("Logo2Ld")
    for _, ld, _, _ in GEN_IMAGES:
        g.loader(ld)
    g.background("Bg", color="Bg")
    # barre
    top = g.dissolve("MBars", "Bg", bars_stack(g), ex("(%s) and 1 or 0" % BARSVIS))
    # frame lines e safe area: sulla slate subito sopra lo sfondo (sotto i testi); sul countdown sopra
    # la taratura (PNG di Genera nel Loader CalLd, a tutto quadro) e sotto cerchio, riquadri e cifra
    guides = guides_layer(g)
    base = g.gate("MGuides", "Bg", [guides], "%s and LK.GuidesSlate > 0.5" % ANY_GUIDE)
    cal_on = ('LK.CalOn > 0.5 and LK.CalImage.Value ~= "" and LK.CalW > 0 and LK.CalH > 0 '
              'and math.abs(LK.CalW / LK.CalH - _A) < 0.01')
    cbase = g.gate("MCal", "Bg", [("CalLd", X("Point(0.5, 0.5)"), X("_W / math.max(1, LK.CalW)"))], cal_on)
    cbase = g.gate("MGuidesCd", cbase, [guides], "%s and LK.GuidesCd > 0.5" % ANY_GUIDE)
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
    lead = leader_stack(g, "L", cbase, 'Text((_REM < %s * _FPS and _REM >= 2 * _FPS) and tostring(math.ceil(_REM / _FPS)) or "")' % C,
                        sweep_vis="_REM < %s * _FPS and _REM > 2 * _FPS" % C, cd=C, extras=countdown_extras(g))
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
    "local AR = W / H local REF = math.min(W, H) local mi = math.floor(LK.BMatte + 0.5) "
    "local MR = (mi == %d) and LK.BMatteRatio or (({ %s })[mi + 1] or 0) "
    # immagine attiva in pixel interi e pari (es. 1920 x 804 per 2.39 su 1920 x 1080)
    "local LB = (MR > AR + 0.01) and (H - 2 * math.floor(W / MR / 2 + 0.5)) / (2 * H) or 0 "
    "local PB = (MR > 0 and MR < AR - 0.01) and (W - 2 * math.floor(H * MR / 2 + 0.5)) / (2 * W) or 0 "
    # maiuscole (frazione di H): percentuale del lato corto, mai sotto 9 px; MINC = minimo nelle bande
    "local CAP = math.max(LK.BSize / 100 * REF, 9) / H local MINC = math.max(0.011 * REF, 8) / H "
    "local INSIDE = LK.BPos > 0.5 "
    % (len(MATTES) - 1, ", ".join(repr(max(r, 0)) for _, r in MATTES)))

# Impaginazione, calcolata solo con numeri: le lunghezze massime dei testi di ogni blocco (su tutto il
# programma) le scrive Aggiorna in LK.BLens, cosi' la grandezza non cambia a ogni stacco e non serve
# rileggere la riga del fotogramma. Modi: EDGE ai bordi del quadro, IN dentro l'immagine (safe),
# LB2 / LB1 nelle bande del letterbox (due righe o una), PB nelle bande laterali (righe impilate).
# Se una banda e' troppo stretta per un testo leggibile i dati vanno dentro l'immagine.
BURN_LAY = (
    "local LN = {} for a, b, c, d, e in string.gmatch(LK.BLens.Value, '(%%d+),(%%d+),(%%d+),(%%d+),(%%d+)') do "
    "LN[#LN + 1] = { a + 0, b + 0, c + 0, d + 0, e + 0 } end "
    "for k = #LN + 1, 5 do LN[k] = { 22, 34, 20, 2, 3 } end "
    "local C5 = LN[5][1] > 0 "
    "local WID = { C5 and 0.33 or 0.46, C5 and 0.33 or 0.46, 0.46, 0.46, 0.28 } "
    "local function FITW(i, w) local c = 9 for k = 1, 5 do if LN[k][i] > 0 then "
    "c = math.min(c, w[k] * AR / (%s * LN[k][i])) end end return c end "
    "local MODE, C = 'EDGE', 0 "
    "if INSIDE or (LB <= 0 and PB <= 0) then MODE, C = (INSIDE and 'IN' or 'EDGE'), math.min(CAP, FITW(1, WID)) "
    "elseif LB > 0 then local c2 = math.min(CAP, LB / 3.2, FITW(1, WID)) local c1 = math.min(CAP, LB / 1.7, FITW(2, WID)) "
    "if c2 >= MINC and c2 >= 0.9 * c1 then MODE, C = 'LB2', c2 elseif c1 >= MINC then MODE, C = 'LB1', c1 "
    "else MODE, C = 'IN', math.min(CAP, FITW(1, WID)) end "
    "else local w = 0.9 * PB local cp = math.min(CAP, FITW(3, { w, w, w, w, w })) "
    "if cp >= MINC then MODE, C = 'PB', cp else MODE, C = 'EDGE', math.min(CAP, FITW(1, WID)) end end "
    "local PC = %s * C local function HB(n) return (math.max(1, n) - 1) * PC + 0.88 * C end "
    % (0.76, PITCH))

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
    "local P12 = '^(%-?%d+)|(%-?%d+)|(%-?[%d%.]+)|([%d%.]+)|(%d+)|(%d+)|(%-?%d+)|(%-?%d+)|([^|]*)|([^|]*)|([^|]*)|([^|]*)' "
    "local a, b, sv, st, sn, sd, au, fr, t1, t2, t3, t4, t5 = string.match(line, P12 .. '|([^|]*)$') "
    "if not a then a, b, sv, st, sn, sd, au, fr, t1, t2, t3, t4 = string.match(line, P12 .. '$') t5 = '' end "
    "if not a or rec < a + 0 or rec >= b + 0 then return nil end "
    "local e = rec - a local tn, td = math.max(1, LK.TlFps), LK.TlDrop "
    "local function sub(txt) "
    "txt = string.gsub(txt, '{REC}', tc(rec, tn, td)) "
    "txt = string.gsub(txt, '{SRC}', tc((sv + 0) < 0 and -1 or (sv + 0) + e * (st + 0), (sn + 0), (sd + 0))) "
    "txt = string.gsub(txt, '{ATC}', tc((au + 0) < 0 and -1 or (au + 0) + e, tn, td)) "
    "txt = string.gsub(txt, '{FRM}', tostring(fr + e)) return txt end "
    "return { t1, t2, t3, t4, t5 }, sub end "
    # testo di un blocco (k = 5: alto centro): due righe, una sola nelle bande sottili, righe impilate
    # (separate da "  ·  ") nelle bande laterali
    "local function CORNER(k) local r, sub = ROW() if not r then return '' end "
    "local parts = {} for x in string.gmatch((r[k] or '') .. '~', '([^~]*)~') do parts[#parts + 1] = x end "
    "local p1, p2 = parts[1] or '', parts[2] or '' local s = '' "
    "if MODE == 'PB' then for q in string.gmatch(p1 .. '  ·  ' .. p2 .. '  ·  ', '(.-)  ·  ') do "
    "if q ~= '' then s = s .. (s ~= '' and '\\n' or '') .. q end end "
    "elseif MODE == 'LB1' then s = p1 .. ((p1 ~= '' and p2 ~= '') and '     ' or '') .. p2 "
    "elseif p1 ~= '' and p2 ~= '' then s = p1 .. '\\n' .. p2 else s = p1 .. p2 end "
    "return sub(s) end "
    "local function BIG() local r, sub = ROW() if not r then return '' end "
    "local parts = {} for x in string.gmatch((r[4] or '') .. '~', '([^~]*)~') do parts[#parts + 1] = x end "
    "return sub(parts[3] or '') end ")


def burn_x(hx):
    """Ascissa: bande laterali (PB), bordo (margine), o celle centrate."""
    margin = "(MODE == 'IN' and 0.05 or 0.02)"
    if hx < 0:
        return "(MODE == 'PB' and (LK.BAlign < 0.5 and 0.05 * PB or PB / 2) or (LK.BAlign < 0.5 and %s or 0.2))" % margin
    return "(MODE == 'PB' and (LK.BAlign < 0.5 and 1 - 0.05 * PB or 1 - PB / 2) or (LK.BAlign < 0.5 and 1 - %s or 0.8))" % margin


def burn_xc():
    """Alto centro: al centro del quadro, o nella banda sinistra sotto il primo blocco (PB)."""
    return "(MODE == 'PB' and PB / 2 or 0.5)"


def burn_y(k):
    """Ordinata del blocco k (1 alto-sx, 2 alto-dx, 3 basso-sx, 4 basso-dx, 5 alto centro)."""
    if k in (1, 2, 5):
        pb = "0.96 - HB(LN[%d][5]) / 2" % k if k != 5 else "0.96 - HB(LN[1][5]) - 1.4 * C - HB(LN[5][5]) / 2"
        return ("(MODE == 'PB' and (%s) or ((MODE == 'LB2' or MODE == 'LB1') and 1 - LB + math.min(LB / 2, 0.075) or "
                "(MODE == 'IN' and 0.93 or 1 - 2.3 * C)))" % pb)
    return ("(MODE == 'PB' and (0.04 + HB(LN[%d][5]) / 2) or ((MODE == 'LB2' or MODE == 'LB1') and LB - math.min(LB / 2, 0.075) or "
            "(MODE == 'IN' and 0.07 or 2.3 * C)))" % k)


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
            + uc_check("BOutline", "Contorno nero sui dati (leggibili anche sul bianco)", 1)
            + uc_slider("BOutlineW", "Spessore del contorno", 0, 0.3, 0.08, integer=False)
            + uc_slider("BWaterAlpha", "Opacita' watermark", 0, 1, 0.18, integer=False))
    uc = on_page("Burn-in", main) + on_page("Campi", fields) + on_page("Aspetto", look)
    uc += (uc_hidden("Seg", "Text") + uc_hidden("SegIdx", "Text") + uc_hidden("BLens", "Text")
           + "".join(uc_hidden(k) for k in ("RecStart", "TlFps", "TlDrop", "TlW", "TlH")))
    d = dict((k, 0) for k, _ in BURN_FIELDS)
    for k in BURN_PHASES[2][1]:
        d[k] = 1
    values = [("BPhase", "2"), ("BTitleText", '""'), ("BVersionText", '""'), ("BWaterText", '"CONFIDENZIALE"'),
              ("BRecipient", '""'), ("BInfo", '"Metti il clip sopra il montato (V3/V4) e premi Aggiorna"'),
              ("BFrameMode", "1"), ("BPos", "0"), ("BAlign", "0"), ("BMatte", "0"), ("BMatteRatio", "2.39"),
              ("BMatteAlpha", "1"), ("BSize", "1.8"), ("BBands", "0"), ("BBandAlpha", "0.6"), ("BWaterAlpha", "0.18"),
              ("BOutline", "1"), ("BOutlineW", "0.08"),
              ("Seg", '""'), ("SegIdx", '""'), ("BLens", '""'), ("RecStart", "0"), ("TlFps", "24"), ("TlDrop", "0"),
              ("TlW", "0"), ("TlH", "0")]
    values += [(k, str(v)) for k, v in d.items()]
    g.controls(values, uc)

    def bx(body):
        return ("expr", "(function() %s return %s end)()" % (BURN_GEO, body))

    def bl(body):
        return ("expr", "(function() %s %s return %s end)()" % (BURN_GEO, BURN_LAY, body))

    def bt(body):
        return ("expr", "(function() %s %s %s return %s end)()" % (BURN_GEO, BURN_LAY, BURN_ROW, body))

    g.background("Bg", rgb=["0", "0", "0"], alpha="0")
    # mascherino: bande sopra/sotto (letterbox) o ai lati (pillarbox), un solo Background
    g.mask("MatTM", "RectangleMask", "1.02", bx("LB"), center=bx("Point(0.5, 1 - LB / 2)"))
    g.mask("MatBM", "RectangleMask", "1.02", bx("LB"), center=bx("Point(0.5, LB / 2)"), chain="MatTM")
    g.mask("MatLM", "RectangleMask", bx("PB"), "1.02", center=bx("Point(PB / 2, 0.5)"), chain="MatBM")
    g.mask("MatRM", "RectangleMask", bx("PB"), "1.02", center=bx("Point(1 - PB / 2, 0.5)"), chain="MatLM")
    g.background("Mat", alpha=("expr", "LK.BMatteAlpha"), mask="MatRM")
    top = g.dissolve("GMat", "Bg", g.merge("GMatM1", "Bg", "Mat"), bx("(LB > 0 or PB > 0) and 1 or 0"))
    # bande semitrasparenti facoltative (spente di default)
    g.mask("BandTM", "RectangleMask", "1.02", bl("4.6 * C"), center=bl("Point(0.5, 1 - 2.3 * C)"))
    g.mask("BandBM", "RectangleMask", "1.02", bl("4.6 * C"), center=bl("Point(0.5, 2.3 * C)"), chain="BandTM")
    g.background("Band", alpha=("expr", "LK.BBandAlpha"), mask="BandBM")
    top = g.dissolve("GBand", top, g.merge("GBandM1", top, "Band"),
                     bl("(MODE == 'EDGE' and LK.BBands > 0.5) and 1 or 0"))
    # angoli: 1 alto-sx, 2 alto-dx, 3 basso-sx, 4 basso-dx; un Text+ per angolo (due righe)
    outline = [("Enabled2", ("expr", "LK.BOutline")), ("Thickness2", ("expr", "LK.BOutlineW"))] + OUTLINE
    corners = []
    for corner, hx in enumerate([-1, 1, -1, 1, 0], 1):
        nm = "T%d" % corner
        if hx == 0:
            center = bl("Point(%s, %s)" % (burn_xc(), burn_y(corner)))
            align = [("HorizontalJustificationNew", "3")]
        else:
            center = bl("Point(%s, %s)" % (burn_x(hx), burn_y(corner)))
            # ancorati al bordo (anche nelle bande laterali), o centrati nelle celle: solo il pannello
            align = [("HorizontalLeftCenterRight", ("expr", "LK.BAlign > 0.5 and 0 or %d" % hx)),
                     ("HorizontalJustificationNew", ("expr", "LK.BAlign > 0.5 and 3 or %d" % (0 if hx < 0 else 1)))]
        g._add(nm, "TextPlus", G.CREATOR + [
            ("Center", center), ("Font", '"Open Sans"'),
            ("Style", '"Bold"'), ("Size", bl("2 * C / AR")), ("StyledText", bt("Text((CORNER(%d)))" % corner)),
            ("Red1", "1"), ("Green1", "1"), ("Blue1", "1"), ("VerticalJustificationNew", "3")] + align + outline)
        corners.append(nm)
    top = g.merge("MTop", top, g.chain("TTop", [corners[0], corners[4], corners[1]]))
    top = g.merge("MBottom", top, g.chain("TBot", corners[2:4]))
    # record TC grande (in basso al centro)
    g._add("Big", "TextPlus", G.CREATOR + [
        ("Center", bl("Point(MODE == 'PB' and 1 - PB / 2 or 0.5, MODE == 'PB' and 0.5 or "
                      "((MODE == 'LB2' or MODE == 'LB1') and LB + 0.06 or (MODE == 'IN' and 0.15 or 4.6 * C + 0.055)))")),
        ("Font", '"Open Sans"'), ("Style", '"Bold"'),
        ("Size", bl("MODE == 'PB' and math.min(10 * CAP / AR, 0.9 * PB / 4.8) or 10 * CAP / AR")),
        ("StyledText", bt("Text(BIG())")),
        ("Red1", "1"), ("Green1", "1"), ("Blue1", "1"),
        ("VerticalJustificationNew", "3"), ("HorizontalJustificationNew", "3")] + outline)
    top = g.gate("MBig", top, ["Big"], "LK.BBig > 0.5")
    g.text("Water", "{ 0.5, 0.5 }", "0.06",
           'Text(string.upper(LK.BWaterText.Value) .. (LK.BRecipient.Value == "" and "" or ("\\n" .. LK.BRecipient.Value)))',
           ["1", "1", "1"])
    top = g.gate("MWater", top, ["Water"], "LK.BWater > 0.5", mix="LK.BWaterAlpha")
    inputs = ([(x, "Burn-in") for x in ("SecBurn", "BPhase", "BUpdate", "BInfo", "BTitleText", "BVersionText",
                                        "BWaterText", "BRecipient")]
              + [(k, "Campi") for k, _ in BURN_FIELDS] + [("BFrameMode", "Campi")]
              + [(x, "Aspetto") for x in ("BMatte", "BMatteRatio", "BMatteAlpha", "BPos", "BAlign", "BSize",
                                          "BBands", "BBandAlpha", "BOutline", "BOutlineW", "BWaterAlpha")])
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
