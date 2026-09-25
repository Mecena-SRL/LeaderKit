-- LeaderKit probe 2: prova le varianti di API che servono al plugin definitivo.
local report = {}
local function log(s) report[#report + 1] = tostring(s); print("[LeaderKit probe 2] " .. tostring(s)) end
local function try(label, fn)
  local ok, res = pcall(fn)
  if ok then log(label .. ": " .. tostring(res)) else log(label .. ": ERRORE " .. tostring(res)) end
  return ok and res or nil
end
local c = comp or (fusion and fusion:GetCurrentComp())
local home = os.getenv("HOME") or os.getenv("USERPROFILE") or "."
local sep = package.config:sub(1, 1)

local function finish()
  local path = home .. sep .. "Desktop" .. sep .. "LeaderKit-probe2.txt"
  local f = io.open(path, "w")
  if not f then path = home .. sep .. "LeaderKit-probe2.txt"; f = io.open(path, "w") end
  if f then f:write(table.concat(report, "\n") .. "\n"); f:close() end
  pcall(function()
    c:AskUser("LeaderKit probe 2", { { "Risultato", "Text",
      Default = table.concat(report, "\n") .. "\n\nReport: " .. path, Lines = 30, Wrap = true } })
  end)
end

-- 1) Lettura dei parametri dell'Inspector
log("== Parametri Inspector ==")
try("tool name", function() return tool and tool.Name end)
try("tool:GetInput('LKTitle')", function() return tool:GetInput("LKTitle") end)
try("tool:GetInput('Input1')", function() return tool:GetInput("Input1") end)
try("tool.LKTitle[0]", function() return tool.LKTitle[0] end)
try("FindTool('LKBg'):GetInput('LKTitle')", function() return c:FindTool("LKBg"):GetInput("LKTitle") end)
try("tool list", function()
  local names = {}
  for _, t in pairs(c:GetToolList(false)) do names[#names + 1] = t.Name .. "(" .. t.ID .. ")" end
  return table.concat(names, ", ")
end)

local resolve = Resolve()
local project = resolve:GetProjectManager():GetCurrentProject()
local tl = project:GetCurrentTimeline()
local pool = project:GetMediaPool()
local fps = math.floor((tonumber(tl:GetSetting("timelineFrameRate")) or 24) + 0.5)
local item = tl:GetCurrentVideoItem()
if not item then log("metti la testina sul generatore e riprova"); finish(); return end
local start, dur = item:GetStart(), item:GetDuration()
log(string.format("clip: '%s' start %d durata %d fine(escl.) %d", item:GetName(), start, dur, start + dur))

-- 2) Pop audio: varianti di AppendToTimeline
log("== Pop audio ==")
local wav = home .. sep .. "LeaderKit_probe_pop.wav"
local clip = nil
for _, folderClip in pairs(pool:GetCurrentFolder():GetClipList() or {}) do
  if folderClip:GetName() == "LeaderKit_probe_pop.wav" then clip = folderClip end
end
if not clip then
  local r = pool:ImportMedia({ wav }); clip = r and r[1]
end
if not clip then log("WAV non trovato: rilancia prima il probe 1"); finish(); return end
try("WAV Frames", function() return clip:GetClipProperty("Frames") end)
try("WAV Duration", function() return clip:GetClipProperty("Duration") end)
local track = tl:GetTrackCount("audio")
if tl:GetTrackName("audio", track) ~= "LeaderKit Pop" then
  tl:AddTrack("audio", "mono"); track = tl:GetTrackCount("audio"); tl:SetTrackName("audio", track, "LeaderKit Pop")
end
try("traccia audio " .. track .. " tipo", function() return tl:GetTrackSubType("audio", track) end)
local base = start + dur + fps  -- oltre la fine del clip, 1 s di distanza tra varianti
local variants = {
  { "a) start0 end1 mediaType2", { startFrame = 0, endFrame = 1, mediaType = 2 } },
  { "b) start0 end0 senza mediaType", { startFrame = 0, endFrame = 0 } },
  { "c) start0 end1 senza mediaType", { startFrame = 0, endFrame = 1 } },
  { "d) senza start/end", {} },
  { "e) start0 end1 mediaType2 traccia 1", { startFrame = 0, endFrame = 1, mediaType = 2, track1 = true } },
}
for i, v in ipairs(variants) do
  local rec = base + (i - 1) * fps
  local info = { mediaPoolItem = clip, recordFrame = rec, trackIndex = v[2].track1 and 1 or track }
  for k, val in pairs(v[2]) do if k ~= "track1" then info[k] = val end end
  local res = try(v[1], function()
    local r = pool:AppendToTimeline({ info })
    if not r or not r[1] then return "nil" end
    local s = {}
    for _, it in pairs(r) do s[#s + 1] = string.format("start %d (rec %d) dur %d", it:GetStart(), rec, it:GetDuration()) end
    return table.concat(s, " | ")
  end)
end

-- 3) Inserire un generatore LeaderKit dopo il clip (per la coda)
log("== Generatore via API ==")
local function tc(frames)
  local f = frames % fps; local s = math.floor(frames / fps)
  return string.format("%02d:%02d:%02d:%02d", math.floor(s / 3600), math.floor(s / 60) % 60, s % 60, f)
end
local target = base + 8 * fps
try("SetCurrentTimecode " .. tc(target), function() return tl:SetCurrentTimecode(tc(target)) end)
try("GetCurrentTimecode", function() return tl:GetCurrentTimecode() end)
local gen = try("InsertFusionGeneratorIntoTimeline('LeaderKit Probe 2')", function()
  return tl:InsertFusionGeneratorIntoTimeline("LeaderKit Probe 2")
end)
if gen then
  try("  nuovo generatore", function()
    return string.format("start %d (atteso %d) durata %d", gen:GetStart(), target, gen:GetDuration())
  end)
  try("  GetFusionCompCount", function() return gen:GetFusionCompCount() end)
  try("  scrittura parametro nel nuovo clip", function()
    local gc = gen:GetFusionCompByIndex(1)
    local bg = gc:FindTool("LKBg")
    if not bg then return "LKBg non trovato; tool: " .. #gc:GetToolList(false) end
    bg:SetInput("LKTitle", "SCRITTO DAL BOTTONE")
    return bg:GetInput("LKTitle")
  end)
end
try("InsertFusionGeneratorIntoTimeline('LeaderKit Probe') (nome v1)", function()
  return tl:InsertFusionGeneratorIntoTimeline("LeaderKit Probe") ~= nil
end)

-- 4) Start timecode (reimposta lo stesso valore: nessuna modifica reale)
log("== Start TC ==")
try("SetStartTimecode(stesso valore)", function() return tl:SetStartTimecode(tl:GetStartTimecode()) end)
finish()
