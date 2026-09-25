#!/usr/bin/env python3
"""Build dei .drfx di prova (Edit > Generators > LeaderKit).

    python3 probe/build_probe.py

* LeaderKit-Probe-3.drfx: grafica statica + bottone "Test timeline" (button3.lua)
* LeaderKit-Test-Grafica.drfx: 6 generatori, uno per tecnica di espressione.
  In Fusion un nodo che fallisce rende nera tutta l'uscita, quindi ogni
  tecnica sta in un generatore separato: quelli neri indicano cosa non va.
"""

import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
from leaderkit.fusion import Expr, FuID, Link, Tool, lua_string  # noqa: E402

RANGE = [("GlobalIn", 0), ("GlobalOut", 100000)]
FF = RANGE + [("UseFrameFormatSettings", 1), ("Width", 1920), ("Height", 1080)]


def background(name, grey, mask=None, extra=()):
    inputs = FF + [("TopLeftRed", grey), ("TopLeftGreen", grey), ("TopLeftBlue", grey),
                   ("TopLeftAlpha", 1.0)] + list(extra)
    if mask:
        inputs.append(("EffectMask", Link(mask, "Mask")))
    return Tool(name, "Background", inputs, (0, 0))


def ring():
    return Tool("LKRing", "EllipseMask", [
        ("Filter", FuID("Fast Gaussian")), ("SoftEdge", 0.0), ("MaskWidth", 1920),
        ("MaskHeight", 1080), ("PixelAspect", (1, 1)), ("UseFrameFormatSettings", 1),
        ("ClippingMode", FuID("None")), ("Center", (0.5, 0.5)), ("Width", 0.36),
        ("Height", 0.36), ("Solid", 0), ("BorderWidth", 0.004)], (0, 60))


def text(name, value, center=(0.5, 0.5), size=0.06, extra=()):
    return Tool(name, "TextPlus", FF + [
        ("Center", center), ("Font", "Open Sans"), ("Style", "Bold"), ("Size", size),
        ("StyledText", value)] + list(extra), (220, 0))


def merge(name, bg, fg, extra=()):
    return Tool(name, "Merge", [("Background", Link(bg)), ("Foreground", Link(fg)),
                                ("PerformDepthMerge", 0)] + list(extra), (330, 0))


def base_tools(extra_bg=()):
    return [background("LKBg", 0.0, extra=extra_bg), ring(),
            background("LKRingBg", 0.8, "LKRing"), merge("LKM0", "LKBg", "LKRingBg")]


def macro(name, tools, output, inputs=(), user_controls=None):
    macro_id = name.replace(" ", "").replace("-", "")
    inner = "\n".join(t.to_lua(4) for t in tools)
    if user_controls:
        head = "\t\t\t\tLKBg = Background {\n"
        inner = inner.replace(head, head + user_controls, 1)
    ins = "\n".join('\t\t\t\tInput%d = InstanceInput { SourceOp = %s, Source = %s, Name = %s, },'
                    % (i, lua_string(op), lua_string(src), lua_string(label))
                    for i, (op, src, label) in enumerate(inputs, 1))
    return ("{\n\tTools = ordered() {\n\t\t%s = MacroOperator {\n\t\t\tCtrlWZoom = false,\n"
            "\t\t\tInputs = ordered() {\n%s\n\t\t\t},\n\t\t\tOutputs = {\n"
            "\t\t\t\tMainOutput1 = InstanceOutput { SourceOp = %s, Source = \"Output\", },\n"
            "\t\t\t},\n\t\t\tViewInfo = GroupInfo { Pos = { 0, 0 } },\n"
            "\t\t\tTools = ordered() {\n%s\n\t\t\t},\n\t\t},\n\t},\n\tActiveTool = %s\n}\n"
            % (macro_id, ins, lua_string(output), inner, lua_string(macro_id)))


def probe3():
    with open(os.path.join(HERE, "button3.lua")) as fh:
        button = fh.read()
    controls = (
        "\t\t\t\t\tUserControls = ordered() {\n"
        "\t\t\t\t\t\tLKTitle = { LINKS_Name = \"Titolo\", LINKID_DataType = \"Text\", "
        "INPID_InputControl = \"TextEditControl\", TEC_Lines = 1, ICS_ControlPage = \"Controls\", },\n"
        "\t\t\t\t\t\tLKNum = { LINKS_Name = \"Numero (slider)\", LINKID_DataType = \"Number\", "
        "INPID_InputControl = \"SliderControl\", INP_Default = 8, INP_MinScale = 0, INP_MaxScale = 20, "
        "INP_Integer = true, ICS_ControlPage = \"Controls\", },\n"
        "\t\t\t\t\t\tLKCombo = { LINKS_Name = \"Preset (menu)\", LINKID_DataType = \"Number\", "
        "INPID_InputControl = \"ComboControl\", INP_Default = 0, INP_Integer = true, "
        "ICS_ControlPage = \"Controls\", { CCS_AddString = \"Cinema / DCP\" }, "
        "{ CCS_AddString = \"Spot RAI\" }, },\n"
        "\t\t\t\t\t\tLKTest = { LINKS_Name = \"Test timeline\", LINKID_DataType = \"Number\", "
        "INPID_InputControl = \"ButtonControl\", INP_Integer = false, INP_External = false, "
        "ICS_ControlPage = \"Controls\", BTNCS_Execute = %s, },\n"
        "\t\t\t\t\t},\n") % lua_string(button)
    tools = base_tools([("LKTitle", "Titolo di prova"), ("LKNum", 8), ("LKCombo", 0)]) + [
        text("LKLabel", "LEADERKIT PROBE 3\nmetti la testina qui e premi Test timeline",
             size=0.04),
        merge("LKM1", "LKM0", "LKLabel")]
    return macro("LeaderKit Probe 3", tools, "LKM1",
                 [("LKLabel", "StyledText", "Testo (nativo Text+)"), ("LKBg", "LKTitle", "Titolo (personalizzato)"),
                  ("LKBg", "LKNum", "Numero (slider)"), ("LKBg", "LKCombo", "Preset (menu)"),
                  ("LKBg", "LKTest", "Test timeline")], controls)


TESTS = [
    ("A", "statico, nessuna espressione", "A  STATICO", None, None),
    ("B", "espressione semplice numerica (time)", "B  ESPRESSIONE SEMPLICE",
     ("Size", Expr(0.06, "0.06 + 0*time")), None),
    ("C", "espressione Lua ':' con Text() e time", "",
     ("StyledText", Expr("", ': return Text("C  frame " .. tostring(time))')), None),
    ("D", "espressione Lua con comp.RenderStart/RenderEnd", "",
     ("StyledText", Expr("", ': return Text("D  range " .. tostring(comp.RenderStart)'
                               ' .. "-" .. tostring(comp.RenderEnd))')), None),
    ("E", "espressione Lua con comp:GetPrefs (fps/risoluzione)", "",
     ("StyledText", Expr("", ': return Text("E  " .. tostring(comp:GetPrefs("Comp.FrameFormat.Width"))'
                               ' .. "x" .. tostring(comp:GetPrefs("Comp.FrameFormat.Height"))'
                               ' .. " @ " .. tostring(comp:GetPrefs("Comp.FrameFormat.Rate")))')), None),
    ("F", "espressione semplice su Blend con comp.RenderEnd (visibile solo nell'ultimo secondo)",
     "F  ULTIMO SECONDO", None, ("Blend", Expr(1.0, "iif(comp.RenderEnd - time < 24, 1, 0)"))),
]


def test_generator(letter, desc, label, text_extra, merge_extra):
    t = text("LKText", label, size=0.06)
    if text_extra:
        t.inputs[text_extra[0]] = text_extra[1]
    tools = base_tools() + [
        text("LKDesc", "Test %s: %s" % (letter, desc), center=(0.5, 0.12), size=0.025),
        merge("LKM1", "LKM0", "LKDesc"), t,
        merge("LKM2", "LKM1", "LKText", [merge_extra] if merge_extra else [])]
    return macro("LK2 Test %s" % letter, tools, "LKM2")


def solid(tag, with_range):
    """Solo un Background rosso, collegato direttamente all'uscita."""
    inputs = [("UseFrameFormatSettings", 1), ("Width", 1920), ("Height", 1080),
              ("TopLeftRed", 1.0), ("TopLeftGreen", 0.0), ("TopLeftBlue", 0.0), ("TopLeftAlpha", 1.0)]
    if with_range:
        inputs = RANGE + inputs
    return macro("LK2 Controllo %s" % tag, [Tool("LKBg", "Background", inputs, (0, 0))], "LKBg")


def write_drfx(name, files):
    out = os.path.join(ROOT, "dist")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, name)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, text_ in files:
            zf.writestr("Edit/Generators/LeaderKit/" + fname, text_)
            with open(os.path.join(out, fname), "w") as fh:
                fh.write(text_)
    return path


def build():
    return [write_drfx("LeaderKit-Probe-3.drfx", [("LeaderKit Probe 3.setting", probe3())]),
            write_drfx("LeaderKit-Test-Grafica-2.drfx",
                       [("LK2 Test %s.setting" % t[0], test_generator(*t)) for t in TESTS]
                       + [("LK2 Controllo Z1.setting", solid("Z1", False)),
                          ("LK2 Controllo Z2.setting", solid("Z2", True))])]


if __name__ == "__main__":
    for p in build():
        print(p)
