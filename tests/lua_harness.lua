-- Harness per i test: carica un .setting, estrae le espressioni e le valuta
-- fotogramma per fotogramma con un comp simulato. Uso:
--   lua harness.lua <file.setting> <fps> <width> <height> <frames> <preset> <countFrom>
local path, fps, W, H, N, preset, cd = arg[1], tonumber(arg[2]), tonumber(arg[3]), tonumber(arg[4]),
  tonumber(arg[5]), tonumber(arg[6]), tonumber(arg[7])
local src = io.open(path):read("a")
setmetatable(_G, { __index = function(_, k) return function(t) t.__kind = k; return t end end })
function ordered() return function(t) return t end end
function FuID(t) return t[1] end
local root = load("return " .. src)()
local grp
for _, v in pairs(root.Tools) do grp = v end
local exprs = {}
for name, tool in pairs(grp.Tools) do
  for inp, v in pairs(tool.Inputs or {}) do
    if type(v) == "table" and v.Expression then exprs[#exprs + 1] = { name .. "." .. inp, v.Expression } end
  end
end
setmetatable(_G, nil)
local function textval(v) return { Value = v } end
local LK = { Preset = preset, CountFrom = cd, Reel = 1, Title = textval("Il film"),
  Director = textval("Regista"), Editor = textval("Montatore"), Colorist = textval("Colorista"),
  Version = textval("v1"), Date = textval("2026-09-25"), Duration = textval("00:01:00:00"),
  Info = textval("FFOA 01:00:08:00") }
local comp = { RenderStart = 0, RenderEnd = N - 1 }
function comp:GetPrefs(k)
  if k == "Comp.FrameFormat.Rate" then return fps end
  if k == "Comp.FrameFormat.Width" then return W end
  if k == "Comp.FrameFormat.Height" then return H end
end
local env = { comp = comp, LK = LK, math = math, string = string, tostring = tostring,
  iif = function(c, a, b) if c then return a else return b end end,
  Text = function(s) return tostring(s) end,
  Point = function(x, y) return x .. "," .. y end }
local compiled = {}
for _, ex in ipairs(exprs) do
  local code = ex[2]
  if code:sub(1, 1) == ":" then code = code:sub(2) else code = "return " .. code end
  local fn, err = load(code, ex[1], "t", env)
  if not fn then error(ex[1] .. ": " .. err) end
  compiled[#compiled + 1] = { ex[1], fn }
end
table.sort(compiled, function(a, b) return a[1] < b[1] end)
for t = 0, N - 1 do
  env.time = t
  local row = {}
  for _, c in ipairs(compiled) do
    local ok, v = pcall(c[2])
    if not ok then error(string.format("frame %d %s: %s", t, c[1], v)) end
    row[#row + 1] = c[1] .. "=" .. tostring(v):gsub("\n", "|")
  end
  print(t .. "\t" .. table.concat(row, "\t"))
end
