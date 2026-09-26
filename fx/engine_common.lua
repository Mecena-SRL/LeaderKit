-- LeaderKit engine, parte comune: eseguita dai bottoni dei generatori LeaderKit.
-- LK_MODE = "generate" | "remove" | "burnin" (impostato dal bottone). Il build
-- concatena questo modulo con engine_burnin.lua e engine.lua (Genera) secondo il modo:
-- "Rimuovi" incorpora solo questa parte.
-- Tutto viene ricalcolato sul frame rate e sul drop-frame reali della timeline.

local MODE = LK_MODE or "generate"
local PREFIX = "leaderkit"
local POP_TRACK = "LeaderKit Pop"
local TAIL_NAME = "LeaderKit Tail"
local LOGO_TRACK = "LeaderKit Logo"          -- tracce dei loghi della 0.10: solo per ripulirle
local GFX_TRACK = "LeaderKit Grafica"
local BURN_NAME = "LeaderKit Burn-in"
local BURN_TRACK = "LeaderKit Burn-in"
HEAD_NAME = "LeaderKit Head"

local report, warnings = {}, {}
local function log(s) report[#report + 1] = tostring(s); print("[LeaderKit] " .. tostring(s)) end
local function warn(s) warnings[#warnings + 1] = tostring(s); print("[LeaderKit] ATTENZIONE: " .. tostring(s)) end

local c = comp or (fusion and fusion:GetCurrentComp())

local function show(title)
  local text = table.concat(report, "\n")
  if #warnings > 0 then text = text .. "\n\nATTENZIONE:\n- " .. table.concat(warnings, "\n- ") end
  print("[LeaderKit] " .. title .. "\n" .. text)
  local home = os.getenv("HOME") or os.getenv("USERPROFILE")
  if home then
    local sep = package.config:sub(1, 1)
    local f = io.open(home .. sep .. "Desktop" .. sep .. "LeaderKit-riepilogo.txt", "w")
    if f then f:write(title .. "\n\n" .. text .. "\n"); f:close() end
  end
  local shown = false
  for _, target in ipairs({ c, fusion and fusion:GetCurrentComp() }) do
    if not shown and target then
      shown = pcall(function()
        target:AskUser(title, { { "Esito", "Text", Default = text, Lines = 18, Wrap = true } })
      end)
    end
  end
end

-- ---------------------------------------------------------------- timecode
local function makeRate(fpsText, dfText)
  local fps = tonumber(string.match(tostring(fpsText), "[%d%.]+")) or 24
  local nominal = math.floor(fps + 0.5)
  local ntsc = math.abs(fps - nominal) > 0.001
  local df = (tostring(dfText) == "1" or string.find(tostring(fpsText), "DF") ~= nil)
  if not (ntsc and (nominal == 30 or nominal == 60)) then df = false end
  local drop = 0
  if df then drop = (nominal == 30) and 2 or 4 end
  return { fps = fps, nominal = nominal, ntsc = ntsc, df = df, drop = drop }
end

local function tcToFrames(tc, r)
  local h, m, s, f = string.match(tc, "(%d+)[:;](%d+)[:;](%d+)[:;.](%d+)")
  h, m, s, f = tonumber(h), tonumber(m), tonumber(s), tonumber(f)
  local frames = ((h * 60 + m) * 60 + s) * r.nominal + f
  if r.drop > 0 then
    local totalMin = h * 60 + m
    frames = frames - r.drop * (totalMin - math.floor(totalMin / 10))
  end
  return frames
end

local function framesToTc(frames, r)
  frames = math.floor(frames + 0.5)
  if frames < 0 then return "-" .. framesToTc(-frames, r) end
  local n = r.nominal
  if r.drop > 0 then
    local per10 = n * 600 - r.drop * 9
    local perMin = n * 60 - r.drop
    local d = math.floor(frames / per10)
    local m = frames % per10
    if m > r.drop then
      frames = frames + r.drop * 9 * d + r.drop * math.floor((m - r.drop) / perMin)
    else
      frames = frames + r.drop * 9 * d
    end
  end
  local sep = (r.drop > 0) and ";" or ":"
  return string.format("%02d:%02d:%02d%s%02d", math.floor(frames / (n * 3600)),
    math.floor(frames / (n * 60)) % 60, math.floor(frames / n) % 60, sep, frames % n)
end

-- Le liste restituite dall'API di Resolve possono contenere anche campi
-- numerici (contatori): si tengono solo gli oggetti.
local function listOf(t)
  local out = {}
  if type(t) ~= "table" then return out end
  local keys = {}
  for k in pairs(t) do keys[#keys + 1] = k end
  table.sort(keys, function(a, b)
    if type(a) == type(b) and (type(a) == "number" or type(a) == "string") then return a < b end
    return type(a) < type(b)
  end)
  for _, k in ipairs(keys) do
    local v = t[k]
    if type(v) == "userdata" or type(v) == "table" then
      out[#out + 1] = v
    elseif type(k) == "userdata" or type(k) == "table" then
      out[#out + 1] = k
    end
  end
  return out
end

-- ---------------------------------------------------------------- controlli
local function findTool(cmp, name)
  if not cmp then return nil end
  local t = cmp:FindTool(name)
  if t then return t end
  for _, x in ipairs(listOf(cmp:GetToolList(false))) do
    if x.Name == name then return x end
  end
  return nil
end

-- pannello: il nodo "LK" della composizione del bottone ("tool" puo' essere un altro nodo)
local lk = findTool(c, "LK") or tool
local function get(name, default)
  if not lk then return default end
  local ok, v = pcall(function() return lk:GetInput(name) end)
  if ok and v ~= nil then return v end
  return default
end
local function set(tool, name, value)
  if tool then pcall(function() tool:SetInput(name, value) end) end
end

-- ---------------------------------------------------------------- Resolve
local resolve = nil
pcall(function() local host = fusion or fu; resolve = host:GetResolve() end)
if not resolve then pcall(function() resolve = Resolve() end) end
if not resolve then pcall(function() resolve = bmd.scriptapp("Resolve") end) end
if not resolve then log("API di Resolve non raggiungibile."); show("LeaderKit"); return end
local project = resolve:GetProjectManager():GetCurrentProject()
local tl = project and project:GetCurrentTimeline()
if not tl then log("Nessuna timeline attiva."); show("LeaderKit"); return end
local pool = project:GetMediaPool()
local r = makeRate(tl:GetSetting("timelineFrameRate"), tl:GetSetting("timelineDropFrameTimecode"))
local W, H = tl:GetSetting("timelineResolutionWidth"), tl:GetSetting("timelineResolutionHeight")

-- nomi delle tracce in cache (le chiamate all'API sono lente con molti clip);
-- trackNamesChanged() va chiamata dopo AddTrack / SetTrackName
local trackNameCache = {}
local function trackName(kind, t)
  local key = kind .. t
  local v = trackNameCache[key]
  if v == nil then v = tl:GetTrackName(kind, t) or ""; trackNameCache[key] = v end
  return v
end
local function trackNamesChanged() trackNameCache = {} end

local function allItems(kind)
  local out = {}
  for t = 1, tl:GetTrackCount(kind) do
    for _, it in ipairs(listOf(tl:GetItemListInTrack(kind, t))) do out[#out + 1] = { item = it, track = t } end
  end
  return out
end

local function isLeaderKit(entry, kind)
  local name = entry.item:GetName() or ""
  if name == TAIL_NAME or name == HEAD_NAME or name == BURN_NAME then return true end
  if string.sub(name, 1, 10) == "LeaderKit_" then return true end
  if kind == "audio" and trackName("audio", entry.track) == POP_TRACK then return true end
  if kind == "video" then
    local tn = trackName("video", entry.track)
    if tn == LOGO_TRACK or tn == LOGO_TRACK .. " 2" or tn == LOGO_TRACK .. " Titolo" or tn == GFX_TRACK
      or tn == BURN_TRACK then return true end
  end
  return false
end

local function cleanup()
  local nm = 0
  for frame, info in pairs(tl:GetMarkers() or {}) do
    if type(info) == "table" and string.sub(tostring(info.customData or ""), 1, #PREFIX) == PREFIX then
      if tl:DeleteMarkerAtFrame(frame) then nm = nm + 1 end
    end
  end
  local doomed = {}
  for _, e in ipairs(allItems("audio")) do
    if isLeaderKit(e, "audio") then doomed[#doomed + 1] = e.item end
  end
  for _, e in ipairs(allItems("video")) do
    local tn = trackName("video", e.track)
    if e.item:GetName() == TAIL_NAME or tn == LOGO_TRACK or tn == LOGO_TRACK .. " 2"
      or tn == LOGO_TRACK .. " Titolo" or tn == GFX_TRACK or tn == BURN_TRACK then
      doomed[#doomed + 1] = e.item
    end
  end
  if #doomed > 0 then tl:DeleteClips(doomed, false) end
  return nm, #doomed
end

if MODE == "remove" then
  local nm, ni = cleanup()
  log(string.format("Rimossi %d marker e %d clip LeaderKit (audio, coda, taratura, burn-in). Il clip Head resta.", nm, ni))
  show("LeaderKit — Rimuovi")
  return
end
