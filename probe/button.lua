-- LeaderKit probe: eseguito dal bottone nell'Inspector. Verifica cosa si può
-- fare dalla timeline e scrive un report sul Desktop.
local report = {}
local function log(s) report[#report + 1] = tostring(s); print("[LeaderKit probe] " .. tostring(s)) end
local function try(label, fn)
  local ok, res = pcall(fn)
  if ok then log(label .. ": " .. tostring(res)) else log(label .. ": ERRORE " .. tostring(res)) end
  return ok and res or nil
end

local c = comp or (fusion and fusion:GetCurrentComp())
log("comp disponibile: " .. tostring(c ~= nil) .. " | tool disponibile: " .. tostring(tool ~= nil))
if c then
  try("comp frame format", function()
    return string.format("%sx%s @ %s fps", tostring(c:GetPrefs("Comp.FrameFormat.Width")),
      tostring(c:GetPrefs("Comp.FrameFormat.Height")), tostring(c:GetPrefs("Comp.FrameFormat.Rate")))
  end)
  try("comp render range", function()
    local a = c:GetAttrs()
    return tostring(a.COMPN_RenderStart) .. " - " .. tostring(a.COMPN_RenderEnd)
  end)
end
if tool then
  try("valore Inspector 'Titolo'", function() return tool:GetInput("LKTitle") end)
end

local resolve = nil
try("Resolve()", function() resolve = Resolve(); return resolve ~= nil end)
if not resolve then try("bmd.scriptapp", function() resolve = bmd.scriptapp("Resolve"); return resolve ~= nil end) end

local function finish()
  local home = os.getenv("HOME") or os.getenv("USERPROFILE") or "."
  local sep = package.config:sub(1, 1)
  local path = home .. sep .. "Desktop" .. sep .. "LeaderKit-probe.txt"
  local f = io.open(path, "w")
  if not f then path = home .. sep .. "LeaderKit-probe.txt"; f = io.open(path, "w") end
  if f then f:write(table.concat(report, "\n") .. "\n"); f:close() end
  local text = table.concat(report, "\n") .. "\n\nReport salvato in: " .. path
  if c then pcall(function()
    c:AskUser("LeaderKit probe", { { "Risultato", "Text", Default = text, Lines = 24, Wrap = true } })
  end) end
end

if not resolve then log("Resolve API NON raggiungibile dal bottone"); finish(); return end
try("versione Resolve", function() return resolve:GetVersionString() end)
local project = resolve:GetProjectManager():GetCurrentProject()
local tl = project and project:GetCurrentTimeline()
if not tl then log("nessuna timeline"); finish(); return end
local fps = tonumber(tl:GetSetting("timelineFrameRate")) or 24
local nominal = math.floor(fps + 0.5)
try("timeline", function()
  return string.format("%s | %s fps | DF=%s | %sx%s | start %s (%s)", tl:GetName(),
    tl:GetSetting("timelineFrameRate"), tostring(tl:GetSetting("timelineDropFrameTimecode")),
    tl:GetSetting("timelineResolutionWidth"), tl:GetSetting("timelineResolutionHeight"),
    tl:GetStartTimecode(), tostring(tl:GetStartFrame()))
end)

local item = try("GetCurrentVideoItem", function() return tl:GetCurrentVideoItem() end)
if not item then log("nessun clip sotto la testina: metti la testina sul generatore e riprova"); finish(); return end
local start, dur = item:GetStart(), item:GetDuration()
log(string.format("clip sotto la testina: '%s' start %d durata %d", tostring(item:GetName()), start, dur))
local popFrame = start + dur - 2 * nominal
log("2-pop atteso a fotogramma " .. popFrame .. " (fine clip - 2 s)")

try("AddMarker (frameId relativo)", function()
  return tl:AddMarker(popFrame - tl:GetStartFrame(), "Cyan", "LK probe 2-pop", "test", 1, "leaderkit:probe")
end)
try("GetMarkers contiene il marker", function()
  for k, v in pairs(tl:GetMarkers()) do
    if v.customData == "leaderkit:probe" then return "si, frameId " .. tostring(k) end
  end
  return "no"
end)

-- WAV 16 bit mono 48 kHz: 0,25 s di 1 kHz a -20 dBFS + silenzio fino a 1 s.
local home = os.getenv("HOME") or os.getenv("USERPROFILE") or "."
local sep = package.config:sub(1, 1)
local wav = home .. sep .. "LeaderKit_probe_pop.wav"
try("scrittura WAV", function()
  local sr, n, tone = 48000, 48000, 12000
  local amp = 0.1 * 32767
  local parts = {}
  local function le(v, bytes)
    local t = {}
    for i = 1, bytes do t[i] = string.char(v % 256); v = math.floor(v / 256) end
    return table.concat(t)
  end
  for i = 0, n - 1 do
    local v = 0
    if i < tone then v = math.floor(amp * math.sin(2 * math.pi * 1000 * i / sr) + 0.5) end
    if v < 0 then v = v + 65536 end
    parts[#parts + 1] = le(v, 2)
  end
  local data = table.concat(parts)
  local f = assert(io.open(wav, "wb"))
  f:write("RIFF", le(36 + #data, 4), "WAVEfmt ", le(16, 4), le(1, 2), le(1, 2), le(sr, 4),
          le(sr * 2, 4), le(2, 2), le(16, 2), "data", le(#data, 4), data)
  f:close()
  return wav
end)
local pool = project:GetMediaPool()
local clips = try("ImportMedia WAV", function() return pool:ImportMedia({ wav }) end)
local clip = clips and clips[1]
if clip then
  local track = nil
  try("AddTrack audio mono", function()
    tl:AddTrack("audio", "mono"); track = tl:GetTrackCount("audio")
    tl:SetTrackName("audio", track, "LeaderKit Pop"); return track
  end)
  local placed = try("AppendToTimeline pop (endFrame=startFrame)", function()
    return pool:AppendToTimeline({ { mediaPoolItem = clip, startFrame = 0, endFrame = 0,
      recordFrame = popFrame, trackIndex = track, mediaType = 2 } })
  end)
  if placed and placed[1] then
    log(string.format("pop posizionato: start %d (atteso %d), durata %d (attesa 1)",
      placed[1]:GetStart(), popFrame, placed[1]:GetDuration()))
  end
end
finish()
