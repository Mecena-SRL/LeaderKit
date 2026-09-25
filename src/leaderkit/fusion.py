"""Generatore delle composizioni Fusion (testo Lua, formato .comp/.setting).

Le grafiche non sono file statici: vengono scritte per ogni elemento con la
risoluzione e il frame rate reali della timeline. Le dimensioni sono in unità
normalizzate di Fusion (1.0 = larghezza immagine), quindi il disegno è
identico in HD, UHD o DCI; le posizioni verticali che devono stare su un
cerchio vengono corrette per l'aspect ratio del raster.

Lo stesso codice produce anche i title template (.setting) del .drfx, con i
campi di testo esposti nell'Inspector.
"""

from collections import OrderedDict

# Geometria del leader (unità di larghezza). Il cerchio sta dentro un
# mascherino Scope 2.39 anche su raster 1.78/1.85 (docs §A, nota Terburg).
RING_D = 0.36
INNER_RING_D = RING_D * 0.86
LINE_W = 0.0025
LINE_GREY = 0.62
FONT = "Open Sans"


class FuID(str):
    pass


class Link(object):
    def __init__(self, op, source="Output"):
        self.op = op
        self.source = source


class Expr(object):
    def __init__(self, value, expression):
        self.value = value
        self.expression = expression


def lua_string(text):
    out = ['"']
    for ch in text:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            continue
        elif ord(ch) < 32:
            out.append("\\%03d" % ord(ch))
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def lua_value(v):
    if isinstance(v, FuID):
        return "FuID { %s }" % lua_string(v)
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        text = repr(round(v, 9))
        return text
    if isinstance(v, str):
        return lua_string(v)
    if isinstance(v, (list, tuple)):
        return "{ " + ", ".join(lua_value(x) for x in v) + " }"
    raise TypeError("Valore non serializzabile: %r" % (v,))


class Tool(object):
    def __init__(self, name, reg_id, inputs, pos=(0, 0)):
        self.name = name
        self.reg_id = reg_id
        self.inputs = OrderedDict(inputs)
        self.pos = pos

    def to_lua(self, indent):
        pad = "\t" * indent
        lines = ["%s%s = %s {" % (pad, self.name, self.reg_id), "%s\tInputs = {" % pad]
        for key, val in self.inputs.items():
            k = key if key.isidentifier() else "[%s]" % lua_string(key)
            if isinstance(val, Link):
                body = "SourceOp = %s, Source = %s, " % (lua_string(val.op), lua_string(val.source))
            elif isinstance(val, Expr):
                body = "Value = %s, Expression = %s, " % (lua_value(val.value),
                                                          lua_string(val.expression))
            else:
                body = "Value = %s, " % lua_value(val)
            lines.append("%s\t\t%s = Input { %s}," % (pad, k, body))
        lines.append("%s\t}," % pad)
        lines.append("%s\tViewInfo = OperatorInfo { Pos = { %d, %d } }," % (pad, self.pos[0], self.pos[1]))
        lines.append("%s}," % pad)
        return "\n".join(lines)


class Graph(object):
    """Grafo lineare: una base e una pila di layer uniti in Merge successivi."""

    def __init__(self, width, height, frame_format_from_host=False):
        self.width = int(width)
        self.height = int(height)
        self.host_format = frame_format_from_host
        self.tools = []
        self.exposed = []  # (tool, input, nome in Inspector)
        self._n = 0
        self._top = None

    @property
    def aspect(self):
        return float(self.width) / float(self.height)

    def _name(self, prefix):
        self._n += 1
        return "LK%s%d" % (prefix, self._n)

    def _pos(self):
        return (110 * len(self.tools), 50 * (len(self.tools) % 3))

    def _format_inputs(self):
        return [("Width", self.width), ("Height", self.height),
                ("UseFrameFormatSettings", 1 if self.host_format else 0)]

    def add(self, tool):
        self.tools.append(tool)
        return tool

    def background(self, rgb=(0.0, 0.0, 0.0), alpha=1.0, mask=None, name=None):
        inputs = self._format_inputs() + [
            ("TopLeftRed", float(rgb[0])), ("TopLeftGreen", float(rgb[1])),
            ("TopLeftBlue", float(rgb[2])), ("TopLeftAlpha", float(alpha))]
        if mask is not None:
            inputs.append(("EffectMask", Link(mask.name, "Mask")))
        return self.add(Tool(name or self._name("Bg"), "Background", inputs, self._pos()))

    def ellipse(self, diameter, border=None, center=(0.5, 0.5)):
        inputs = [("Filter", FuID("Fast Gaussian")), ("SoftEdge", 0.0),
                  ("MaskWidth", self.width), ("MaskHeight", self.height),
                  ("PixelAspect", (1, 1)), ("ClippingMode", FuID("None")),
                  ("Center", tuple(center)), ("Width", float(diameter)), ("Height", float(diameter))]
        if border is not None:
            inputs += [("Solid", 0), ("BorderWidth", float(border))]
        return self.add(Tool(self._name("Ellipse"), "EllipseMask", inputs, self._pos()))

    def rectangle(self, width, height, center=(0.5, 0.5)):
        inputs = [("Filter", FuID("Fast Gaussian")), ("SoftEdge", 0.0),
                  ("MaskWidth", self.width), ("MaskHeight", self.height),
                  ("PixelAspect", (1, 1)), ("ClippingMode", FuID("None")),
                  ("Center", tuple(center)), ("Width", float(width)), ("Height", float(height))]
        return self.add(Tool(self._name("Rect"), "RectangleMask", inputs, self._pos()))

    def text(self, text, size, center=(0.5, 0.5), rgb=(1.0, 1.0, 1.0), style="Bold",
             expose=None, line_spacing=None):
        inputs = self._format_inputs() + [
            ("Center", tuple(center)), ("Font", FONT), ("Style", style),
            ("Size", float(size)), ("StyledText", text),
            ("Red1", float(rgb[0])), ("Green1", float(rgb[1])), ("Blue1", float(rgb[2]))]
        if line_spacing is not None:
            inputs.append(("LineSpacing", float(line_spacing)))
        tool = self.add(Tool(self._name("Text"), "TextPlus", inputs, self._pos()))
        if expose:
            self.exposed.append((tool.name, "StyledText", expose))
        return tool

    def transform(self, source, angle_expr, pivot=(0.5, 0.5)):
        inputs = [("Center", (0.5, 0.5)), ("Pivot", tuple(pivot)),
                  ("Angle", Expr(0.0, angle_expr)), ("Input", Link(source.name))]
        return self.add(Tool(self._name("Xf"), "Transform", inputs, self._pos()))

    def layer(self, tool):
        """Mette ``tool`` sopra la pila corrente con un Merge."""
        if self._top is None:
            self._top = tool
            return tool
        merge = Tool(self._name("Merge"), "Merge", [
            ("Background", Link(self._top.name)), ("Foreground", Link(tool.name)),
            ("PerformDepthMerge", 0)], self._pos())
        self.add(merge)
        self._top = merge
        return merge

    def shape(self, mask, grey=LINE_GREY):
        return self.layer(self.background((grey, grey, grey), 1.0, mask))

    @property
    def output(self):
        return self._top

    # --- serializzazione -------------------------------------------------

    def to_comp(self, duration):
        """Testo .comp per TimelineItem.ImportFusionComp()."""
        body = [t.to_lua(2) for t in self.tools]
        body.append(Tool("MediaOut1", "MediaOut", [
            ("Index", "0"), ("Input", Link(self.output.name))], self._pos()).to_lua(2))
        last = max(int(duration) - 1, 0)
        return ("Composition {\n\tCurrentTime = 0,\n\tRenderRange = { 0, %d },\n"
                "\tGlobalRange = { 0, %d },\n\tHiQ = true,\n\tTools = ordered() {\n%s\n\t},\n}\n"
                % (last, last, "\n".join(body)))

    def to_macro(self, macro_name):
        """Testo .setting (title template Edit page) con input esposti."""
        inner = "\n".join(t.to_lua(4) for t in self.tools)
        inputs = []
        for i, (op, src, label) in enumerate(self.exposed, 1):
            inputs.append('\t\t\t\tInput%d = InstanceInput { SourceOp = %s, Source = %s, Name = %s, },'
                          % (i, lua_string(op), lua_string(src), lua_string(label)))
        return ("{\n\tTools = ordered() {\n\t\t%s = MacroOperator {\n\t\t\tCtrlWZoom = false,\n"
                "\t\t\tInputs = ordered() {\n%s\n\t\t\t},\n"
                "\t\t\tOutputs = {\n\t\t\t\tMainOutput1 = InstanceOutput { SourceOp = %s, Source = \"Output\", },\n"
                "\t\t\t},\n\t\t\tViewInfo = GroupInfo { Pos = { 0, 0 } },\n"
                "\t\t\tTools = ordered() {\n%s\n\t\t\t},\n\t\t},\n\t},\n\tActiveTool = %s\n}\n"
                % (macro_name, "\n".join(inputs), lua_string(self.output.name), inner,
                   lua_string(macro_name)))


# --- grafiche ------------------------------------------------------------

def _leader_base(g):
    g.layer(g.background((0.0, 0.0, 0.0), 1.0))
    g.shape(g.rectangle(1.0, LINE_W))                         # croce orizzontale
    g.shape(g.rectangle(LINE_W, 1.0 / g.aspect))              # croce verticale
    g.shape(g.ellipse(RING_D, border=LINE_W * 1.6), 0.85)     # cerchio esterno
    g.shape(g.ellipse(INNER_RING_D, border=LINE_W), 0.85)     # cerchio interno


def _sweep(g, nominal, phase):
    """Braccio rotante: un giro per secondo nominale, ancorato all'inizio clip."""
    r = RING_D / 2.0
    arm = g.rectangle(LINE_W * 1.6, r, center=(0.5, 0.5 + (r / 2.0) * g.aspect))
    bg = g.background((0.9, 0.9, 0.9), 1.0, arm)
    expr = "-360*((time-comp.RenderStart)+%d)/%d" % (int(phase), int(nominal))
    g.layer(g.transform(bg, expr))


def countdown_digit(width, height, nominal, digit, sweep=True, phase=0):
    g = Graph(width, height)
    _leader_base(g)
    if sweep:
        _sweep(g, nominal, phase)
    g.layer(g.text(str(digit), 0.30))
    return g


def picture_start(width, height):
    g = Graph(width, height)
    _leader_base(g)
    g.layer(g.text("PICTURE\nSTART", 0.075, line_spacing=1.0))
    return g


def pop_frame(width, height, style="two"):
    g = Graph(width, height)
    if style == "white":
        g.layer(g.background((1.0, 1.0, 1.0), 1.0))
        return g
    _leader_base(g)
    g.layer(g.text("2", 0.30))
    return g


def slate(width, height, heading, title, lines, host_format=False):
    g = Graph(width, height, host_format)
    g.layer(g.background((0.0, 0.0, 0.0), 1.0))
    g.layer(g.text(heading, 0.028, center=(0.5, 0.86), rgb=(0.7, 0.7, 0.7),
                   expose="Heading"))
    g.layer(g.text(title, 0.065, center=(0.5, 0.75), expose="Title"))
    g.shape(g.rectangle(0.6, LINE_W, center=(0.5, 0.665)), 0.5)
    g.layer(g.text("\n".join(lines), 0.026, center=(0.5, 0.38), style="Regular",
                   expose="Details", line_spacing=1.15))
    return g


def card(width, height, text, subtitle="", host_format=False):
    g = Graph(width, height, host_format)
    g.layer(g.background((0.0, 0.0, 0.0), 1.0))
    g.layer(g.text(text, 0.07, expose="Text"))
    g.layer(g.text(subtitle, 0.024, center=(0.5, 0.36), rgb=(0.7, 0.7, 0.7),
                   style="Regular", expose="Subtitle"))
    return g


def graph_for_element(element, plan):
    """Grafo Fusion per un Element del layout (None = nero puro, niente comp)."""
    w, h = plan.width, plan.height
    kind = element.kind
    if kind == "countdown":
        return countdown_digit(w, h, plan.rate.nominal, element.params["digit"],
                               element.params.get("sweep", True), element.params.get("phase", 0))
    if kind == "picture_start":
        return picture_start(w, h)
    if kind == "pop":
        return pop_frame(w, h, element.params.get("style", "two"))
    if kind == "slate":
        return slate(w, h, plan.slate_heading, plan.slate_title, plan.slate_lines)
    if kind == "card":
        sub = "LFOA %s  ·  DURATION %s" % (plan.tc(plan.lfoa), plan.slate_values.get("duration", ""))
        return card(w, h, element.params.get("text", "END OF PROGRAM"), sub)
    return None


# --- title template del .drfx ---------------------------------------------

def drfx_templates():
    """{nome file .setting: testo} per Edit > Titles > LeaderKit."""
    return OrderedDict([
        ("LeaderKit Slate.setting", slate(
            1920, 1080, "LEADERKIT", "TITLE",
            ["DIRECTOR   —", "EDITOR   —", "COLORIST   —", "DATE   —", "VERSION   —",
             "DURATION   —", "FRAME RATE   —", "RESOLUTION   —"],
            host_format=True).to_macro("LeaderKitSlate")),
        ("LeaderKit End Card.setting", card(
            1920, 1080, "END OF PROGRAM", "", host_format=True).to_macro("LeaderKitEndCard")),
    ])
