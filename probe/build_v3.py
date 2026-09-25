#!/usr/bin/env python3
"""Test 3: generatori costruiti con le convenzioni dei template funzionanti
(GroupOperator, nodo Custom come pannello di controllo, GlobalOut sui
generatori, espressioni semplici senza ':').

    python3 probe/build_v3.py   ->  dist/LeaderKit-Test-3.drfx
"""

import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
from leaderkit.fusion import lua_string  # noqa: E402

CREATOR = ("GlobalOut = Input { Value = 119, }, Width = Input { Value = 1920, }, "
           "Height = Input { Value = 1080, }, UseFrameFormatSettings = Input { Value = 1, }, "
           "[\"Gamut.SLogVersion\"] = Input { Value = FuID { \"SLog2\" }, }, ")


def text(name, center_y, size, value=None, expr=None, pos=0):
    styled = "StyledText = Input { Value = %s, }, " % lua_string(value) if expr is None else \
        "StyledText = Input { Expression = %s, }, " % lua_string(expr)
    return ("\t\t\t\t%s = TextPlus {\n\t\t\t\t\tCtrlWShown = false,\n\t\t\t\t\tNameSet = true,\n"
            "\t\t\t\t\tInputs = { %sCenter = Input { Value = { 0.5, %s }, }, %s"
            "Font = Input { Value = \"Open Sans\", }, Style = Input { Value = \"Bold\", }, "
            "Size = Input { Value = %s, }, VerticalJustificationNew = Input { Value = 3, }, "
            "HorizontalJustificationNew = Input { Value = 3, }, },\n"
            "\t\t\t\t\tViewInfo = OperatorInfo { Pos = { %d, 0 } },\n\t\t\t\t},\n"
            % (name, CREATOR, repr(center_y), styled, repr(size), pos))


def background(name, grey, mask=None, pos=0):
    m = "EffectMask = Input { SourceOp = %s, Source = \"Mask\", }, " % lua_string(mask) if mask else ""
    return ("\t\t\t\t%s = Background {\n\t\t\t\t\tCtrlWShown = false,\n\t\t\t\t\tNameSet = true,\n"
            "\t\t\t\t\tInputs = { %sTopLeftRed = Input { Value = %s, }, TopLeftGreen = Input { Value = %s, }, "
            "TopLeftBlue = Input { Value = %s, }, TopLeftAlpha = Input { Value = 1, }, %s},\n"
            "\t\t\t\t\tViewInfo = OperatorInfo { Pos = { %d, 60 } },\n\t\t\t\t},\n"
            % (name, CREATOR, grey, grey, grey, m, pos))


def ellipse(name, pos=0):
    return ("\t\t\t\t%s = EllipseMask {\n\t\t\t\t\tCtrlWShown = false,\n\t\t\t\t\tNameSet = true,\n"
            "\t\t\t\t\tInputs = { Filter = Input { Value = FuID { \"Fast Gaussian\" }, }, "
            "MaskWidth = Input { Value = 1920, }, MaskHeight = Input { Value = 1080, }, "
            "PixelAspect = Input { Value = { 1, 1 }, }, UseFrameFormatSettings = Input { Value = 1, }, "
            "ClippingMode = Input { Value = FuID { \"None\" }, }, Width = Input { Value = 0.36, }, "
            "Height = Input { Value = 0.36, }, Solid = Input { Value = 0, }, "
            "BorderWidth = Input { Value = 0.004, }, },\n"
            "\t\t\t\t\tViewInfo = OperatorInfo { Pos = { %d, 120 } },\n\t\t\t\t},\n" % (name, pos))


def merge(name, bg, fg, pos=0):
    return ("\t\t\t\t%s = Merge {\n\t\t\t\t\tCtrlWShown = false,\n"
            "\t\t\t\t\tInputs = { Background = Input { SourceOp = %s, Source = \"Output\", }, "
            "Foreground = Input { SourceOp = %s, Source = \"Output\", }, "
            "PerformDepthMerge = Input { Value = 0, }, },\n"
            "\t\t\t\t\tViewInfo = OperatorInfo { Pos = { %d, 30 } },\n\t\t\t\t},\n"
            % (name, lua_string(bg), lua_string(fg), pos))


def controls(values, user_controls):
    return ("\t\t\t\tLKControls = Custom {\n\t\t\t\t\tCtrlWShown = false,\n\t\t\t\t\tNameSet = true,\n"
            "\t\t\t\t\tInputs = { %s},\n\t\t\t\t\tViewInfo = OperatorInfo { Pos = { 0, 180 } },\n"
            "\t\t\t\t\tUserControls = ordered() { %s },\n\t\t\t\t},\n" % (values, user_controls))


def group(name, tools, output, inputs=()):
    gid = "".join(ch for ch in name if ch.isalnum())
    ins = "\n".join("\t\t\t\tInput%d = InstanceInput { SourceOp = \"LKControls\", Source = %s, },"
                    % (i, lua_string(src)) for i, src in enumerate(inputs, 1))
    return ("{\n\tTools = ordered() {\n\t\t%s = GroupOperator {\n\t\t\tCtrlWZoom = false,\n"
            "\t\t\tInputs = ordered() {\n%s\n\t\t\t},\n"
            "\t\t\tOutputs = {\n\t\t\t\tMainOutput1 = InstanceOutput { SourceOp = %s, Source = \"Output\", },\n\t\t\t},\n"
            "\t\t\tViewInfo = GroupInfo { Pos = { 0, 0 }, Flags = { AllowPan = false, AutoSnap = true, "
            "RemoveRouters = true }, Size = { 600, 200, 300, 24 }, Direction = \"Horizontal\", "
            "PipeStyle = \"Direct\", Scale = 1, Offset = { 0, 0 } },\n"
            "\t\t\tTools = ordered() {\n%s\t\t\t},\n\t\t},\n\t},\n\tActiveTool = %s\n}\n"
            % (gid, ins, lua_string(output), "".join(tools), lua_string(gid)))


TITLE_UC = ("Title = { TEC_ReadOnly = false, LINKID_DataType = \"Text\", LINKS_Name = \"Titolo\", "
            "INPID_InputControl = \"TextEditControl\", TEC_Lines = 1, TEC_Wrap = true, }, "
            "Seconds = { LINKID_DataType = \"Number\", LINKS_Name = \"Countdown da\", "
            "INPID_InputControl = \"SliderControl\", INP_Integer = true, INP_MinScale = 2, "
            "INP_MaxScale = 11, INP_Default = 8, }, "
            "Preset = { { CCS_AddString = \"Cinema / DCP\" }, { CCS_AddString = \"Spot RAI\" }, "
            "LINKID_DataType = \"Number\", INPID_InputControl = \"ComboControl\", "
            "CC_LabelPosition = \"Horizontal\", INP_Integer = false, LINKS_Name = \"Preset\", }")
TITLE_VALUES = "Title = Input { Value = \"TITOLO DI PROVA\", }, Seconds = Input { Value = 8, }, Preset = Input { Value = 0, }, "


def tests():
    out = []
    # A: solo testo statico
    out.append(("A", group("LK3 Test A", [text("TxtA", 0.5, 0.08, "A  TESTO STATICO")], "TxtA")))
    # B: testo + pannello parametri, espressione semplice sul titolo
    out.append(("B", group("LK3 Test B", [
        controls(TITLE_VALUES, TITLE_UC),
        text("TxtB", 0.5, 0.08, expr="string.upper(\"B  \" .. LKControls.Title.Value)"),
        text("TxtB2", 0.35, 0.04, expr="Text(\"preset \" .. iif(LKControls.Preset == 0, \"CINEMA\", \"RAI\") .. \"  countdown da \" .. LKControls.Seconds)", pos=110),
        merge("MrgB", "TxtB", "TxtB2", 220)], "MrgB", ["Title", "Preset", "Seconds"])))
    # C: sfondo nero + testo
    out.append(("C", group("LK3 Test C", [
        background("BgC", 0), text("TxtC", 0.5, 0.08, "C  SFONDO + TESTO", pos=110),
        merge("MrgC", "BgC", "TxtC", 220)], "MrgC")))
    # D: cerchio (maschera) + testo
    out.append(("D", group("LK3 Test D", [
        ellipse("RingD"), background("RingBgD", 0.8, "RingD", 110),
        text("TxtD", 0.5, 0.06, "D  CERCHIO", pos=220), merge("MrgD", "RingBgD", "TxtD", 330)], "MrgD")))
    # E: countdown con fps fisso 24 (espressione semplice)
    out.append(("E", group("LK3 Test E", [
        text("TxtE", 0.5, 0.3, expr="Text(floor((comp.RenderEnd - time) / 24) + 1)"),
        text("TxtE2", 0.15, 0.035, expr="Text(\"E  frame \" .. time .. \" fine \" .. comp.RenderEnd)", pos=110),
        merge("MrgE", "TxtE", "TxtE2", 220)], "MrgE")))
    # F: fps e risoluzione letti dal comp
    out.append(("F", group("LK3 Test F", [
        text("TxtF", 0.5, 0.05, expr="Text(\"F  \" .. comp:GetPrefs(\"Comp.FrameFormat.Width\") .. \"x\" .. "
                                     "comp:GetPrefs(\"Comp.FrameFormat.Height\") .. \" @ \" .. "
                                     "comp:GetPrefs(\"Comp.FrameFormat.Rate\"))")], "TxtF")))
    return out


def build():
    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    path = os.path.join(ROOT, "dist", "LeaderKit-Test-3.drfx")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for letter, text_ in tests():
            name = "LK3 Test %s.setting" % letter
            zf.writestr("Edit/Generators/LeaderKit/" + name, text_)
            with open(os.path.join(ROOT, "dist", name), "w") as fh:
                fh.write(text_)
    return path


if __name__ == "__main__":
    print(build())
