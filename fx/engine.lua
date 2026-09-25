-- LeaderKit engine: eseguito dai bottoni del generatore "LeaderKit Head".
-- LK_MODE = "generate" | "remove" (impostato dal bottone).
-- Tutto viene ricalcolato sul frame rate e sul drop-frame reali della timeline.

local MODE = LK_MODE or "generate"
local PREFIX = "leaderkit"
local POP_TRACK = "LeaderKit Pop"
local TAIL_NAME = "LeaderKit Tail"
local HEAD_NAME = "LeaderKit Head"

local report, warnings = {}, {}
local function log(s) report[#report + 1] = tostring(s); print("[LeaderKit] " .. tostring(s)) end
local function warn(s) warnings[#warnings + 1] = tostring(s); print("[LeaderKit] ATTENZIONE: " .. tostring(s)) end

local c = comp or (fusion and fusion:GetCurrentComp())

local function show(title)
  local text = table.concat(report, "\n")
  if #warnings > 0 then text = text .. "\n\nATTENZIONE:\n- " .. table.concat(warnings, "\n- ") end
  pcall(function()
    c:AskUser(title, { { "Esito", "Text", Default = text, Lines = 18, Wrap = true, ReadOnly = true } })
  end)
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

-- ---------------------------------------------------------------- controlli
local function findTool(cmp, name)
  if not cmp then return nil end
  local t = cmp:FindTool(name)
  if t then return t end
  for _, x in pairs(cmp:GetToolList(false) or {}) do
    if x.Name == name then return x end
  end
  return nil
end

local lk = tool
if not lk or not pcall(function() return lk:GetInput("Preset") end) then lk = findTool(c, "LK") end
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

local function allItems(kind)
  local out = {}
  for t = 1, tl:GetTrackCount(kind) do
    for _, it in pairs(tl:GetItemListInTrack(kind, t) or {}) do out[#out + 1] = { item = it, track = t } end
  end
  return out
end

local function isLeaderKit(entry, kind)
  local name = entry.item:GetName() or ""
  if name == TAIL_NAME or name == HEAD_NAME then return true end
  if string.sub(name, 1, 10) == "LeaderKit_" then return true end
  if kind == "audio" and tl:GetTrackName("audio", entry.track) == POP_TRACK then return true end
  return false
end

local function cleanup()
  local nm = 0
  for frame, info in pairs(tl:GetMarkers() or {}) do
    if string.sub(tostring(info.customData or ""), 1, #PREFIX) == PREFIX then
      if tl:DeleteMarkerAtFrame(frame) then nm = nm + 1 end
    end
  end
  local doomed = {}
  for _, e in ipairs(allItems("audio")) do
    if isLeaderKit(e, "audio") then doomed[#doomed + 1] = e.item end
  end
  for _, e in ipairs(allItems("video")) do
    if e.item:GetName() == TAIL_NAME then doomed[#doomed + 1] = e.item end
  end
  if #doomed > 0 then tl:DeleteClips(doomed, false) end
  return nm, #doomed
end

if MODE == "remove" then
  local nm, ni = cleanup()
  log(string.format("Rimossi %d marker e %d clip LeaderKit (pop e coda). Il clip Head resta.", nm, ni))
  show("LeaderKit — Rimuovi")
  return
end

-- ---------------------------------------------------------------- generate
local head = tl:GetCurrentVideoItem()
if not head or head:GetName() ~= HEAD_NAME then
  -- ripiego: il primo LeaderKit Head sulla timeline
  head = nil
  for _, e in ipairs(allItems("video")) do
    if e.item:GetName() == HEAD_NAME then head = e.item; break end
  end
end
if not head then
  log("Non trovo il clip LeaderKit Head: mettici sopra la testina e riprova.")
  show("LeaderKit"); return
end

local preset = math.floor(get("Preset", 0) + 0.5)   -- 0 Cinema/DCP, 1 Spot RAI
local reel = math.floor(get("Reel", 1) + 0.5)
local countFrom = math.floor(get("CountFrom", 8) + 0.5)
local markersOn = get("MarkersOn", preset == 0 and 1 or 0) > 0.5
local markerKind = math.floor(get("MarkerKind", 0) + 0.5)   -- 0 rullo, 1 break
local markerEvery = get("MarkerEvery", 20)
local tailOn = get("TailOn", 1) > 0.5
local n = r.nominal

local nm, ni = cleanup()
if nm + ni > 0 then log(string.format("Pulizia: tolti %d marker e %d clip della generazione precedente.", nm, ni)) end

-- 1) Start timecode: la fine del clip Head e' il FFOA del preset.
local ffoaTc = (preset == 0) and string.format("%02d:00:08:00", reel) or "10:00:00:00"
local ffoaTarget = tcToFrames(ffoaTc, r)
local offset = head:GetStart() + head:GetDuration() - tl:GetStartFrame()
local newStart = ffoaTarget - offset
if newStart < 0 then
  warn("Il clip Head e' troppo lontano dall'inizio timeline per portare il FFOA a " .. framesToTc(ffoaTarget, r))
else
  local ok = tl:SetStartTimecode(framesToTc(newStart, r))
  if not ok then warn("SetStartTimecode non riuscito: start TC non modificato") end
end
local ffoa = head:GetStart() + head:GetDuration()
log(string.format("Timeline %s — %s fps%s, %sx%s", tl:GetName(), tostring(r.fps), r.df and " DF" or "", W, H))
log("FFOA " .. framesToTc(ffoa, r) .. "  (start timeline " .. tl:GetStartTimecode() .. ")")

local headSec = head:GetDuration() / n
if preset == 0 and head:GetDuration() < countFrom * n then
  warn(string.format("Il clip Head dura %.1f\": servono almeno %d\" per il countdown (meglio %d\" con la slate).",
    headSec, countFrom, countFrom + 10))
elseif preset == 1 and head:GetDuration() < 8 * n then
  warn(string.format("Il clip Head dura %.1f\": RAI chiede ident >= 5\" + 3\" di nero (almeno 8\").", headSec))
end
if preset == 0 and r.ntsc then
  warn("Il digital cinema non supporta frequenze NTSC (23.976/29.97): per il DCP vanno convertite.")
end
if preset == 1 and (n ~= 25 or tostring(W) ~= "1920" or tostring(H) ~= "1080") then
  warn("RAI richiede 1920x1080 a 25 fps (1080i25).")
end

-- 2) Programma: i clip dopo il FFOA che non sono LeaderKit.
local lfoa = nil
for _, kind in ipairs({ "video", "audio" }) do
  for _, e in ipairs(allItems(kind)) do
    if not isLeaderKit(e, kind) and e.item:GetStart() >= ffoa then
      local last = e.item:GetStart() + e.item:GetDuration() - 1
      if not lfoa or last > lfoa then lfoa = last end
    end
  end
end
local durTc = "—"
if lfoa then
  durTc = framesToTc(lfoa - ffoa + 1, r)
  log("LFOA " .. framesToTc(lfoa, r) .. "  durata programma " .. durTc)
else
  warn("Nessun clip dopo il LeaderKit Head: coda, LFOA e marker di rullo non generati.")
end

-- 3) Pop audio (WAV generato, 1 kHz -20 dBFS, rifilato a 1 fotogramma).
local home = os.getenv("HOME") or os.getenv("USERPROFILE") or "."
local sep = package.config:sub(1, 1)
local WAV_NAME = "LeaderKit_pop_1kHz_-20dBFS.wav"
local cacheDir = home .. sep .. ".leaderkit"
pcall(function() bmd.createdir(cacheDir) end)
local wavPath = cacheDir .. sep .. WAV_NAME
do  -- se la cartella non e' scrivibile, ripiega sulla home
  local probe = io.open(wavPath, "ab")
  if probe then probe:close() else wavPath = home .. sep .. WAV_NAME end
end

local function writeWav(path)
  local f = io.open(path, "rb")
  if f then
    local size = f:seek("end"); f:close()
    if size and size > 1000 then return true end
  end
  local sr, total, tone, amp = 48000, 48000, 12000, 0.1 * 32767
  local function le(v, bytes)
    local t = {}
    for i = 1, bytes do t[i] = string.char(v % 256); v = math.floor(v / 256) end
    return table.concat(t)
  end
  local parts = {}
  for i = 0, total - 1 do
    local v = 0
    if i < tone then v = math.floor(amp * math.sin(2 * math.pi * 1000 * i / sr) + 0.5) end
    if v < 0 then v = v + 65536 end
    parts[#parts + 1] = le(v, 2)
  end
  local data = table.concat(parts)
  f = io.open(path, "wb")
  if not f then return false end
  f:write("RIFF", le(36 + #data, 4), "WAVEfmt ", le(16, 4), le(1, 2), le(1, 2), le(sr, 4),
    le(sr * 2, 4), le(2, 2), le(16, 2), "data", le(#data, 4), data)
  f:close()
  return true
end

local function popClip()
  if not writeWav(wavPath) then return nil end
  local root = pool:GetRootFolder()
  local folder = nil
  for _, sub in pairs(root:GetSubFolderList() or {}) do
    if sub:GetName() == "LeaderKit" then folder = sub end
  end
  if not folder then folder = pool:AddSubFolder(root, "LeaderKit") end
  if folder then
    for _, clip in pairs(folder:GetClipList() or {}) do
      if clip:GetName() == WAV_NAME then return clip end
    end
  end
  local prev = pool:GetCurrentFolder()
  if folder then pool:SetCurrentFolder(folder) end
  local items = pool:ImportMedia({ wavPath })
  if prev then pool:SetCurrentFolder(prev) end
  return items and items[1]
end

local popTrack = nil
local function ensurePopTrack()
  if popTrack then return popTrack end
  for t = 1, tl:GetTrackCount("audio") do
    if tl:GetTrackName("audio", t) == POP_TRACK then popTrack = t end
  end
  if not popTrack then
    tl:AddTrack("audio", "mono")
    popTrack = tl:GetTrackCount("audio")
    tl:SetTrackName("audio", popTrack, POP_TRACK)
  end
  return popTrack
end

-- Varianti di AppendToTimeline: la prima che produce 1 fotogramma esatto vince.
local VARIANTS = {
  { startFrame = 0, endFrame = 1, mediaType = 2 },
  { startFrame = 0, endFrame = 0, mediaType = 2 },
  { startFrame = 0, endFrame = 1 },
  { startFrame = 0, endFrame = 0 },
}
local goodVariant = nil
local function placePop(frame, label)
  local clip = popClip()
  if not clip then warn("Tono di sync non importato (" .. wavPath .. ")"); return false end
  local track = ensurePopTrack()
  local list = goodVariant and { goodVariant } or VARIANTS
  for _, v in ipairs(list) do
    local info = { mediaPoolItem = clip, recordFrame = frame, trackIndex = track }
    for k, val in pairs(v) do info[k] = val end
    local res = pool:AppendToTimeline({ info })
    if res and res[1] then
      local ok = true
      for _, it in pairs(res) do
        if it:GetStart() ~= frame or it:GetDuration() ~= 1 then ok = false end
      end
      if ok then goodVariant = v; log(label .. " " .. framesToTc(frame, r)); return true end
      tl:DeleteClips(res, false)
    end
  end
  warn(label .. ": pop audio non posizionato (API AppendToTimeline). Marker aggiunto comunque.")
  return false
end

local function marker(frame, color, name, note, tag)
  local ok = tl:AddMarker(frame - tl:GetStartFrame(), color, name, note, 1, PREFIX .. ":" .. tag)
  if not ok then warn("Marker '" .. name .. "' non aggiunto a " .. framesToTc(frame, r)) end
end

-- 4) Testa: 2-pop (solo Cinema/DCP)
local popTc = "—"
if preset == 0 then
  local pop = ffoa - 2 * n
  popTc = framesToTc(pop, r)
  placePop(pop, "2-pop")
  marker(pop, "Cyan", "2-POP", "2-pop " .. popTc .. " — 1 kHz -20 dBFS", "pop")
end
marker(ffoa, "Blue", "FFOA", "First frame of action " .. framesToTc(ffoa, r), "ffoa")

-- 5) Coda + marker di programma
if lfoa then
  marker(lfoa, "Blue", "LFOA", "Last frame of action " .. framesToTc(lfoa, r), "lfoa")
  if tailOn then
    local playhead = tl:GetCurrentTimecode()
    tl:SetCurrentTimecode(framesToTc(lfoa + 1, r))
    local tail = tl:InsertFusionGeneratorIntoTimeline(TAIL_NAME)
    if playhead then tl:SetCurrentTimecode(playhead) end
    if tail then
      if tail:GetStart() ~= lfoa + 1 then
        warn("La coda e' stata inserita a " .. framesToTc(tail:GetStart(), r) .. " invece che a " .. framesToTc(lfoa + 1, r))
      end
      local tc = tail:GetFusionCompByIndex(1)
      local tlk = findTool(tc, "LK")
      set(tlk, "Preset", preset)
      set(tlk, "Info", "LFOA " .. framesToTc(lfoa, r) .. "  ·  DURATION " .. durTc)
      log(string.format("Coda: %s → %s (%d\"; allunga il clip per una coda piu' lunga)",
        framesToTc(tail:GetStart(), r), framesToTc(tail:GetStart() + tail:GetDuration() - 1, r),
        math.floor(tail:GetDuration() / n)))
      if preset == 0 then
        if tail:GetDuration() >= 2 * n then
          local tp = lfoa + 2 * n
          placePop(tp, "Tail pop")
          marker(tp, "Cyan", "TAIL POP", "Tail pop " .. framesToTc(tp, r), "tailpop")
        else
          warn("Coda troppo corta per il tail pop a LFOA +2\"")
        end
      end
    else
      warn("Non riesco a inserire il generatore '" .. TAIL_NAME .. "' (e' installato?)")
    end
  end
  if markersOn and markerEvery and markerEvery > 0 then
    local step = math.floor(markerEvery * 60 * n + 0.5)
    local k, frame = 1, ffoa + step
    while frame < lfoa do
      if markerKind == 0 then
        marker(frame, "Red", "Fine rullo " .. k, string.format("Cambio rullo %d → %d a %s", k, k + 1, framesToTc(frame, r)), "reel:" .. k)
      else
        marker(frame, "Yellow", "Break " .. k, "Break " .. k .. " a " .. framesToTc(frame, r), "break:" .. k)
      end
      k = k + 1
      frame = frame + step
    end
    log(string.format("Marker %s ogni %g': %d", markerKind == 0 and "fine rullo" or "break", markerEvery, k - 1))
  end
end

-- 6) Dati calcolati nella slate
set(lk, "Duration", durTc)
local info = "FFOA " .. framesToTc(ffoa, r)
if preset == 0 then info = info .. "  ·  2-POP " .. popTc end
if lfoa then info = info .. "  ·  LFOA " .. framesToTc(lfoa, r) end
if r.df then info = info .. "  ·  DROP-FRAME" end
set(lk, "Info", info)

show("LeaderKit — Genera")
