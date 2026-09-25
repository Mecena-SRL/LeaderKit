#!/usr/bin/env python3
"""Build del .drfx di prova: Edit > Generators > LeaderKit > LeaderKit Probe."""

import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
from leaderkit.fusion import Expr, FuID, Link, Tool, lua_string  # noqa: E402

BUTTON = os.environ.get("PROBE_BUTTON", "button.lua")
NAME = os.environ.get("PROBE_NAME", "LeaderKit Probe")
MACRO = NAME.replace(" ", "")

FF = [("UseFrameFormatSettings", 1), ("Width", 1920), ("Height", 1080)]


def text(name, center, size, expr, pos):
    return Tool(name, "TextPlus", FF + [
        ("Center", center), ("Font", "Open Sans"), ("Style", "Bold"), ("Size", size),
        ("StyledText", Expr("", expr))], pos)


def merge(name, bg, fg, pos):
    return Tool(name, "Merge", [("Background", Link(bg)), ("Foreground", Link(fg)),
                                ("PerformDepthMerge", 0)], pos)


def build():
    with open(os.path.join(HERE, BUTTON)) as fh:
        button = fh.read()
    tools = [
        Tool("LKBg", "Background", FF + [("TopLeftRed", 0.0), ("TopLeftGreen", 0.0),
                                         ("TopLeftBlue", 0.0), ("TopLeftAlpha", 1.0),
                                         ("LKTitle", "Titolo di prova")], (0, 0)),
        Tool("LKRing", "EllipseMask", [("Filter", FuID("Fast Gaussian")), ("SoftEdge", 0.0),
                                       ("MaskWidth", 1920), ("MaskHeight", 1080),
                                       ("PixelAspect", (1, 1)), ("UseFrameFormatSettings", 1),
                                       ("ClippingMode", FuID("None")), ("Center", (0.5, 0.5)),
                                       ("Width", 0.36), ("Height", 0.36), ("Solid", 0),
                                       ("BorderWidth", 0.004)], (0, 60)),
        Tool("LKRingBg", "Background", FF + [("TopLeftRed", 0.8), ("TopLeftGreen", 0.8),
                                             ("TopLeftBlue", 0.8), ("TopLeftAlpha", 1.0),
                                             ("EffectMask", Link("LKRing", "Mask"))], (110, 60)),
        text("LKDigit", (0.5, 0.5), 0.30,
             ": local fps = math.floor(comp:GetPrefs('Comp.FrameFormat.Rate') + 0.5); "
             "return Text(tostring(math.floor((comp.RenderEnd - time) / fps) + 1))", (220, 0)),
        text("LKFormat", (0.5, 0.92), 0.035,
             ": return Text(string.format('A) %dx%d @ %.3f fps', "
             "comp:GetPrefs('Comp.FrameFormat.Width'), comp:GetPrefs('Comp.FrameFormat.Height'), "
             "comp:GetPrefs('Comp.FrameFormat.Rate')))", (220, 60)),
        text("LKFrame", (0.5, 0.86), 0.035,
             ": return Text(string.format('B) frame %d di %d (range %d-%d)', "
             "time - comp.RenderStart, comp.RenderEnd - comp.RenderStart + 1, "
             "comp.RenderStart, comp.RenderEnd))", (220, 120)),
        text("LKTitleText", (0.5, 0.12), 0.045, ": return Text('C) ' .. LKBg.LKTitle)", (220, 180)),
        merge("LKM1", "LKBg", "LKRingBg", (330, 0)),
        merge("LKM2", "LKM1", "LKDigit", (440, 0)),
        merge("LKM3", "LKM2", "LKFormat", (550, 0)),
        merge("LKM4", "LKM3", "LKFrame", (660, 0)),
        merge("LKM5", "LKM4", "LKTitleText", (770, 0)),
    ]
    inner = "\n".join(t.to_lua(4) for t in tools)
    user_controls = (
        "\t\t\t\t\tUserControls = ordered() {\n"
        "\t\t\t\t\t\tLKTitle = { LINKS_Name = \"Titolo\", LINKID_DataType = \"Text\", "
        "INPID_InputControl = \"TextEditControl\", TEC_Lines = 1, ICS_ControlPage = \"Controls\", },\n"
        "\t\t\t\t\t\tLKTest = { LINKS_Name = \"Test timeline\", LINKID_DataType = \"Number\", "
        "INPID_InputControl = \"ButtonControl\", INP_Integer = false, INP_External = false, "
        "ICS_ControlPage = \"Controls\", BTNCS_Execute = %s, },\n"
        "\t\t\t\t\t},\n") % lua_string(button)
    # UserControls va dentro il blocco del Background LKBg.
    marker = "\t\t\t\tLKBg = Background {\n"
    inner = inner.replace(marker, marker + user_controls, 1)
    setting = (
        "{\n\tTools = ordered() {\n\t\t" + MACRO + " = MacroOperator {\n"
        "\t\t\tCtrlWZoom = false,\n\t\t\tInputs = ordered() {\n"
        "\t\t\t\tInput1 = InstanceInput { SourceOp = \"LKBg\", Source = \"LKTitle\", Name = \"Titolo\", },\n"
        "\t\t\t\tInput2 = InstanceInput { SourceOp = \"LKBg\", Source = \"LKTest\", Name = \"Test timeline\", },\n"
        "\t\t\t},\n\t\t\tOutputs = {\n"
        "\t\t\t\tMainOutput1 = InstanceOutput { SourceOp = \"LKM5\", Source = \"Output\", },\n"
        "\t\t\t},\n\t\t\tViewInfo = GroupInfo { Pos = { 0, 0 } },\n"
        "\t\t\tTools = ordered() {\n%s\n\t\t\t},\n\t\t},\n\t},\n"
        "\tActiveTool = \"" + MACRO + "\"\n}\n") % inner
    out_dir = os.path.join(ROOT, "dist")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, NAME.replace(" ", "-") + ".drfx")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Edit/Generators/LeaderKit/%s.setting" % NAME, setting)
    with open(os.path.join(out_dir, NAME + ".setting"), "w") as fh:
        fh.write(setting)
    return path


if __name__ == "__main__":
    print(build())
