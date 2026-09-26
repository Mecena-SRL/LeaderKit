-- Valuta un .setting a un fotogramma e stampa in JSON tutti i nodi con gli input
-- risolti (valori ed espressioni). Uso:
--   lua lua_dump.lua <file.setting> <fps> <w> <h> <frames> <t> [chiave=valore ...]
local path, fps, W, H, N, T = arg[1], tonumber(arg[2]), tonumber(arg[3]), tonumber(arg[4]),
  tonumber(arg[5]), tonumber(arg[6])
local src = io.open(path):read("a")
setmetatable(_G, { __index = function(_, k) return function(t) t.__kind = k; return t end end })
function ordered() return function(t) return t end end
function FuID(t) return { __fuid = t[1] } end
local root = load("return " .. src)()
setmetatable(_G, nil)
local grp, grpName
for k, v in pairs(root.Tools) do grp, grpName = v, k end
local function textval(v) return { Value = v } end
local LK = {}
for k, v in pairs(grp.Tools.LK.Inputs or {}) do
  if type(v) == "table" and v.Value ~= nil then
    if type(v.Value) == "string" then LK[k] = textval(v.Value) else LK[k] = v.Value end
  end
end
for i = 7, #arg do
  local k, v = arg[i]:match("([^=]+)=(.*)")
  -- i campi di testo del pannello restano testo anche se il valore sembra un numero
  if tonumber(v) and type(LK[k]) ~= "table" then LK[k] = tonumber(v) else LK[k] = textval(v) end
end
local comp = { RenderStart = 0, RenderEnd = N - 1 }
function comp:GetPrefs(k)
  if k == "Comp.FrameFormat.Rate" then return fps end
  if k == "Comp.FrameFormat.Width" then return W end
  if k == "Comp.FrameFormat.Height" then return H end
end
local env = { comp = comp, LK = LK, math = math, string = string, tostring = tostring, time = T,
  pcall = pcall, os = os,
  iif = function(c, a, b) if c then return a else return b end end,
  Text = function(s) return tostring(s) end,
  Point = function(x, y) return { x, y } end }
local function enc(v)
  local t = type(v)
  if t == "number" then return string.format("%.10g", v) end
  if t == "string" then return string.format("%q", v):gsub("\\\n", "\\n") end
  if t == "boolean" then return v and "true" or "false" end
  if t == "table" then
    if v.__fuid then return enc(v.__fuid) end
    if #v > 0 then local o = {}; for _, x in ipairs(v) do o[#o + 1] = enc(x) end; return "[" .. table.concat(o, ",") .. "]" end
    local o = {}
    for k, x in pairs(v) do if type(k) == "string" and k ~= "__kind" then o[#o + 1] = enc(k) .. ":" .. enc(x) end end
    return "{" .. table.concat(o, ",") .. "}"
  end
  return "null"
end
local out = {}
for name, tool in pairs(grp.Tools) do
  local ins = {}
  for k, v in pairs(tool.Inputs or {}) do
    if type(v) == "table" then
      if v.Expression then
        local code = v.Expression
        if code:sub(1, 1) == ":" then code = code:sub(2) else code = "return " .. code end
        local fn = assert(load(code, name .. "." .. k, "t", env))
        local ok, r = pcall(fn)
        if not ok then error(name .. "." .. k .. ": " .. tostring(r)) end
        ins[k] = r
      elseif v.SourceOp then
        ins[k] = { link = v.SourceOp, src = v.Source }
      else
        ins[k] = v.Value
      end
    end
  end
  out[#out + 1] = enc(name) .. ":{" .. '"kind":' .. enc(tool.__kind) .. ',"inputs":' .. enc(ins) .. "}"
end
local outName
for _, o in pairs(grp.Outputs or {}) do outName = o.SourceOp end
print('{"output":' .. enc(outName) .. ',"tools":{' .. table.concat(out, ",") .. "}}")
