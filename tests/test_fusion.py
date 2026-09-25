import os
import shutil
import subprocess

import pytest

from conftest import PRESETS_DIR
from leaderkit import fusion, layout, presets
from leaderkit.timecode import FrameRate

LUA = shutil.which("lua5.4") or shutil.which("lua") or shutil.which("lua5.3")

# Stub dei costruttori Fusion: esegue il file e verifica i collegamenti.
CHECKER = r"""
local tools, order, links = {}, {}, {}
local function ctor(kind) return function(t) t.__kind = kind; return t end end
setmetatable(_G, {__index = function(_, k) return ctor(k) end})
function ordered() return function(t) return t end end
function FuID(t) return t[1] end
local src = io.read("a")
local chunk = assert(load("return " .. src, "comp", "t"))
local root = chunk()
local function scan(tbl)
  for name, tool in pairs(tbl) do
    if type(tool) == "table" and tool.__kind then
      tools[name] = tool.__kind
      if tool.Tools then scan(tool.Tools) end
      for _, inp in pairs(tool.Inputs or {}) do
        if type(inp) == "table" and inp.SourceOp then links[#links + 1] = inp.SourceOp end
      end
      for _, out in pairs(tool.Outputs or {}) do
        if type(out) == "table" and out.SourceOp then links[#links + 1] = out.SourceOp end
      end
    end
  end
end
scan(root.Tools)
for _, op in ipairs(links) do
  if not tools[op] then error("SourceOp mancante: " .. op) end
end
local n = 0 for _ in pairs(tools) do n = n + 1 end
print(n)
"""


def run_lua(text):
    proc = subprocess.run([LUA, "-e", CHECKER], input=text.encode("utf-8"),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.returncode == 0, proc.stderr.decode()
    return int(proc.stdout.decode().strip())


def all_graphs():
    preset = presets.load_file(os.path.join(PRESETS_DIR, "cinema_dcp.json"))
    for fps, df, w, h in [("24", False, 1920, 1080), ("25", False, 3840, 2160),
                          ("29.97", True, 1998, 1080)]:
        plan = layout.build_plan(preset, FrameRate.parse(fps, df), w, h, 1000,
                                 {"title": 'Il "film"\\ test'})
        for e in plan.elements:
            g = fusion.graph_for_element(e, plan)
            if g is not None:
                yield e, plan, g


def test_graphs_exist_for_non_black():
    kinds = {e.kind for e, _, _ in all_graphs()}
    assert kinds == {"slate", "picture_start", "countdown", "pop", "card"}


def test_comp_uses_timeline_resolution_and_fps():
    for e, plan, g in all_graphs():
        text = g.to_comp(e.duration)
        assert "Width = Input { Value = %d, }" % plan.width in text
        assert "Height = Input { Value = %d, }" % plan.height in text
        assert "MediaOut1 = MediaOut" in text
        if e.kind == "countdown" and e.params["sweep"]:
            assert "/%d\"" % plan.rate.nominal in text


def test_sweep_phase_after_picture_start():
    for e, plan, g in all_graphs():
        if e.kind == "countdown" and e.params["digit"] == 8:
            assert "+1)/%d" % plan.rate.nominal in g.to_comp(e.duration)


def test_lua_string_escaping():
    assert fusion.lua_string('a"b\\c\nd') == '"a\\"b\\\\c\\nd"'


@pytest.mark.skipif(LUA is None, reason="interprete lua non disponibile")
def test_generated_lua_is_valid_and_linked():
    for e, plan, g in all_graphs():
        assert run_lua(g.to_comp(e.duration)) == len(g.tools) + 1
    for name, text in fusion.drfx_templates().items():
        assert run_lua(text) >= 4, name
