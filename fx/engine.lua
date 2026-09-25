-- LeaderKit engine: eseguito dai bottoni del generatore "LeaderKit Head".
-- LK_MODE = "generate" | "remove" (impostato dal bottone).
-- Tutto viene ricalcolato sul frame rate e sul drop-frame reali della timeline.

local MODE = LK_MODE or "generate"
local PREFIX = "leaderkit"
local POP_TRACK = "LeaderKit Pop"
local TAIL_NAME = "LeaderKit Tail"
local LOGO_TRACK = "LeaderKit Logo"
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
    for _, it in ipairs(listOf(tl:GetItemListInTrack(kind, t))) do out[#out + 1] = { item = it, track = t } end
  end
  return out
end

local function isLeaderKit(entry, kind)
  local name = entry.item:GetName() or ""
  if name == TAIL_NAME or name == HEAD_NAME then return true end
  if string.sub(name, 1, 10) == "LeaderKit_" then return true end
  if kind == "audio" and tl:GetTrackName("audio", entry.track) == POP_TRACK then return true end
  if kind == "video" and tl:GetTrackName("video", entry.track) == LOGO_TRACK then return true end
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
    if e.item:GetName() == TAIL_NAME or tl:GetTrackName("video", e.track) == LOGO_TRACK then
      doomed[#doomed + 1] = e.item
    end
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
local checks = {}
local function ok(s) checks[#checks + 1] = "✓ " .. s end
local function bad(s) checks[#checks + 1] = "⚠ " .. s; warnings[#warnings + 1] = s end

local function isHeadItem(item)
  if not item then return false end
  local okk, has = pcall(function()
    local cmp = item:GetFusionCompByIndex(1)
    local t = findTool(cmp, "LK")
    return t ~= nil and t:GetInput("DurSel") ~= nil
  end)
  if okk and has then return true end
  local nm = item:GetName() or ""
  return string.find(nm, "LeaderKit", 1, true) ~= nil and nm ~= TAIL_NAME
end

local head = tl:GetCurrentVideoItem()
if not isHeadItem(head) then
  head = nil
  for _, e in ipairs(allItems("video")) do
    if isHeadItem(e.item) then head = e.item; break end
  end
end
if not head then
  log("Non trovo il blocco LeaderKit Head: mettici sopra la testina e riprova.")
  show("LeaderKit"); return
end
HEAD_NAME = head:GetName()   -- nome del template installato (serve per ricrearlo)

-- ---------------------------------------------------------------- standard
local presets = LK_PRESETS or {}
local durations = LK_DURATIONS or { { kind = "free" } }
local presetIdx = math.floor(get("Preset", 0) + 0.5)
local P = presets[presetIdx + 1] or presets[1] or {}
local custom = (get("Custom", 0) or 0) > 0.5
local function dur(key, input)
  if custom then return get(input, P[key] or 0) end
  return P[key] or 0
end
local n = r.nominal
local barsSec, slateSec, gapSec = dur("bars", "BarsSec"), dur("slate", "SlateSec"), dur("gap", "GapSec")
local countFrom = math.floor(dur("countdown", "CountFrom") + 0.5)
local tailSec = dur("tail", "TailSec")
local reel = math.floor(get("Reel", 1) + 0.5)
local tailOn = get("TailOn", 1) > 0.5 and tailSec > 0
local popChoice = math.floor(get("PopLevel", 0) + 0.5)          -- 0 standard, 1 -20, 2 -18
local popLevel = (popChoice == 1) and -20 or ((popChoice == 2) and -18 or (P.pop_dbfs or -20))
local beepEach = get("BeepEach", 0) > 0.5
local markersOn = get("MarkersOn", 1) > 0.5
local kindChoice = math.floor(get("MarkerKind", 0) + 0.5)       -- 0 standard, 1 rullo, 2 break
local pm = P.markers or {}
local markerKind = (kindChoice == 1) and "reel" or ((kindChoice == 2) and "break" or (pm.kind or "none"))
local markerEvery = get("MarkerEvery", 0)
if not markerEvery or markerEvery <= 0 then markerEvery = pm.every_min or 0 end
local durSel = durations[math.floor(get("DurSel", LK_DUR_DEFAULT or 0) + 0.5) + 1] or durations[1]

local headLen = math.floor((barsSec + slateSec + gapSec + countFrom) * n + 0.5)
local tailLen = math.floor(tailSec * n + 0.5)
if headLen < 1 then
  log("Lo standard scelto non ha leader in testa (durata 0): niente da generare in testa.")
  headLen = 1
end

local PARAMS = LK_PARAMS or { "Preset", "Reel", "DurSel", "ProgramTC", "Title", "Director", "Editor",
  "Colorist", "Version", "Date", "Note", "TextRed", "TextGreen", "TextBlue", "BgRed", "BgGreen", "BgBlue",
  "AccentRed", "AccentGreen", "AccentBlue" }
local COLORS = { "TextRed", "TextGreen", "TextBlue", "BgRed", "BgGreen", "BgBlue", "AccentRed", "AccentGreen", "AccentBlue" }

local nm, ni = cleanup()
if nm + ni > 0 then log(string.format("Pulizia: tolti %d marker e %d clip della generazione precedente.", nm, ni)) end

local function trackOf(item)
  for t = 1, tl:GetTrackCount("video") do
    for _, it in ipairs(listOf(tl:GetItemListInTrack("video", t))) do
      if it:GetStart() == item:GetStart() and it:GetName() == item:GetName() then return t end
    end
  end
  return nil
end

-- Inserisce un generatore a [start, start+len) impostando In/Out della timeline;
-- prova le convenzioni possibili e tiene quella che da' la durata esatta.
local markMode = nil
local function insertExact(name, start, len)
  local modes = markMode and { markMode } or {
    { rel = false, incl = true }, { rel = true, incl = true },
    { rel = false, incl = false }, { rel = true, incl = false } }
  local last = nil
  for _, m in ipairs(modes) do
    local base = m.rel and tl:GetStartFrame() or 0
    local inF, outF = start - base, start + len - base - (m.incl and 1 or 0)
    pcall(function() tl:ClearMarkInOut("all") end)
    local okMarks = false
    pcall(function() okMarks = tl:SetMarkInOut(inF, outF, "all") end)
    tl:SetCurrentTimecode(framesToTc(start, r))
    local it = tl:InsertFusionGeneratorIntoTimeline(name)
    pcall(function() tl:ClearMarkInOut("all") end)
    if it then
      if it:GetStart() == start and it:GetDuration() == len then markMode = m; return it, true end
      last = it
      if not okMarks then return it, false end
      tl:DeleteClips({ it }, false)
      last = nil
    end
  end
  if last then return last, false end
  tl:SetCurrentTimecode(framesToTc(start, r))
  return tl:InsertFusionGeneratorIntoTimeline(name), false
end

local function lkOf(item)
  local okk, cmp = pcall(function() return item:GetFusionCompByIndex(1) end)
  if okk then return findTool(cmp, "LK") end
  return nil
end

-- ---------------------------------------------------------------- 1) blocco Head
local S = head:GetStart()
local headTrack = trackOf(head)
local userBefore, programFirst = nil, nil
for _, kind in ipairs({ "video", "audio" }) do
  for _, e in ipairs(allItems(kind)) do
    local st = e.item:GetStart()
    if not isLeaderKit(e, kind) and not isHeadItem(e.item) then
      if st >= S then
        if not programFirst or st < programFirst then programFirst = st end
      elseif not userBefore or st < userBefore then userBefore = st end
    end
  end
end
local ffoa = S + headLen
log(string.format("Standard: %s  (%s)", P.name or "?", P.source or ""))
if programFirst and programFirst < ffoa then
  local missing = ffoa - programFirst
  log(string.format("Il leader dura %s: va da %s a %s, il programma deve iniziare a %s (FFOA).",
    framesToTc(headLen, r), framesToTc(S, r), framesToTc(ffoa - 1, r), framesToTc(ffoa, r)))
  bad(string.format("Il programma inizia a %s, dentro il leader (mancano %s). Sposta il programma a %s o piu' avanti e premi di nuovo Genera. Non ho modificato nulla.",
    framesToTc(programFirst, r), framesToTc(missing, r), framesToTc(ffoa, r)))
  set(lk, "Guide", "Sposta il programma a " .. framesToTc(ffoa, r) .. " (mancano " .. framesToTc(missing, r) .. ")")
  report[#report + 1] = "\nCONTROLLI\n" .. table.concat(checks, "\n")
  warnings = {}
  show("LeaderKit — spazio insufficiente"); return
end

local panel = lk
if head:GetDuration() ~= headLen then
  local saved = {}
  for _, k in ipairs(PARAMS) do saved[k] = get(k, nil) end
  tl:DeleteClips({ head }, false)
  local newHead, exact = insertExact(HEAD_NAME, S, headLen)
  if not newHead then bad("Non riesco a ricreare il blocco LeaderKit Head."); show("LeaderKit"); return end
  head = newHead
  pcall(function() local nc = head:GetFusionCompByIndex(1); if nc then c = nc end end)
  panel = lkOf(head)
  if panel then for k, v in pairs(saved) do set(panel, k, v) end
  else bad("Parametri non ricopiati nel nuovo blocco (pannello non trovato).") end
  if exact then ok("Blocco leader portato alla durata dello standard: " .. framesToTc(headLen, r) .. ".")
  else bad(string.format("Il blocco dura %s invece di %s: questa versione di Resolve ignora In/Out. Allungalo a mano fino a %s.",
    framesToTc(head:GetDuration(), r), framesToTc(headLen, r), framesToTc(ffoa, r))) end
  local t2 = trackOf(head)
  if headTrack and t2 and t2 ~= headTrack then bad("Il blocco e' finito sulla traccia V" .. t2 .. " invece di V" .. headTrack .. ": spostalo.") end
else
  ok("Blocco leader gia' della durata giusta (" .. framesToTc(headLen, r) .. ").")
end
lk = panel or lk
ffoa = head:GetStart() + head:GetDuration()

-- ---------------------------------------------------------------- 2) start timecode
local ffoaTc = P.ffoa or "01:00:00:00"
if P.ffoa_hour_per_reel then ffoaTc = string.format("%02d%s", reel, string.sub(ffoaTc, 3)) end
local ffoaTarget = tcToFrames(ffoaTc, r)
local oldStartTc = tl:GetStartTimecode()
local newStart = ffoaTarget - (ffoa - tl:GetStartFrame())
if newStart < 0 then
  bad("Il blocco e' troppo lontano dall'inizio della timeline per portare il FFOA a " .. ffoaTc ..
    ": avvicinalo all'inizio e premi di nuovo Genera.")
elseif newStart ~= tl:GetStartFrame() then
  if tl:SetStartTimecode(framesToTc(newStart, r)) then
    ok("Start della timeline portato da " .. oldStartTc .. " a " .. framesToTc(newStart, r) ..
      " perche' lo standard vuole il FFOA a " .. ffoaTc .. ".")
  else bad("Non riesco a cambiare lo start timecode: impostalo a mano a " .. framesToTc(newStart, r) ..
    " (clic destro sulla timeline › Timelines › Starting Timecode).") end
else
  ok("Start della timeline gia' corretto (" .. oldStartTc .. ").")
end
ffoa = head:GetStart() + head:GetDuration()
if userBefore then
  bad("Ci sono clip prima del leader (da " .. framesToTc(userBefore, r) .. "): finiranno nel file prima della slate. " ..
    "Spostali dopo il FFOA o cancellali.")
end

-- Formato
local rateLabel = string.format("%g", r.fps)
local allowed = P.rates or {}
if #allowed > 0 then
  local found = false
  for _, a in ipairs(allowed) do if math.abs((tonumber(a) or 0) - r.fps) < 0.01 then found = true end end
  if found then ok("Frame rate " .. rateLabel .. " previsto dallo standard.")
  else bad("Frame rate " .. rateLabel .. " non previsto da " .. (P.name or "") .. " (attesi: " .. table.concat(allowed, ", ") ..
    "). Cambia il frame rate della timeline prima di montare.") end
end
if r.ntsc and P.ntsc_warning then bad(P.ntsc_warning) end
if r.df and (P.ffoa or ""):sub(1, 2) == "10" then bad("Timecode drop-frame in uno standard europeo: di norma si usa non-drop.") end
local res = P.resolutions or {}
if #res > 0 then
  local found = false
  for _, wh in ipairs(res) do if tostring(wh[1]) == tostring(W) and tostring(wh[2]) == tostring(H) then found = true end end
  if found then ok("Risoluzione " .. W .. "x" .. H .. " prevista dallo standard.")
  else bad("Risoluzione " .. W .. "x" .. H .. " non prevista da " .. (P.name or "") .. ".") end
end

-- ---------------------------------------------------------------- 3) programma e durata
local lastContent, firstContent = nil, nil
for _, kind in ipairs({ "video", "audio" }) do
  for _, e in ipairs(allItems(kind)) do
    local st = e.item:GetStart()
    if not isLeaderKit(e, kind) and not isHeadItem(e.item) and st >= ffoa then
      local last = st + e.item:GetDuration() - 1
      if not lastContent or last > lastContent then lastContent = last end
      if not firstContent or st < firstContent then firstContent = st end
    end
  end
end
if firstContent and firstContent ~= ffoa then
  bad("Il programma inizia a " .. framesToTc(firstContent, r) .. " ma il FFOA e' " .. framesToTc(ffoa, r) ..
    ": sposta il primo clip esattamente a " .. framesToTc(ffoa, r) .. ".")
elseif firstContent then
  ok("Il programma inizia esattamente al FFOA " .. framesToTc(ffoa, r) .. ".")
end

local slotFrames, slotLabel = nil, nil
if durSel.kind == "slot" then
  slotFrames, slotLabel = math.floor(durSel.seconds * n + 0.5), durSel.label
elseif durSel.kind == "custom" then
  local txt = tostring(get("ProgramTC", "") or "")
  if string.match(txt, "^%s*%d+[:;]%d+[:;]%d+[:;.]%d+%s*$") then
    slotFrames = tcToFrames(txt, makeRate(tostring(r.fps), "0"))
    slotLabel = "personalizzata " .. txt
  else
    bad("Durata personalizzata non valida ('" .. txt .. "'): scrivila come HH:MM:SS:FF, per esempio 00:52:00:00.")
  end
end

local lfoa = nil
if slotFrames and slotFrames > 0 then
  lfoa = ffoa + slotFrames - 1
  ok("Contenitore " .. slotLabel .. ": programma da " .. framesToTc(ffoa, r) .. " a " .. framesToTc(lfoa, r) ..
    " (" .. framesToTc(slotFrames, r) .. ").")
  if lastContent then
    local diff = (lastContent - ffoa + 1) - slotFrames
    if diff > 0 then
      bad(string.format("Il montato e' piu' lungo del contenitore di %d fotogrammi (%s): finisce a %s. Accorcialo, oppure scegli una durata libera.",
        diff, framesToTc(diff, r), framesToTc(lastContent, r)))
    elseif diff < 0 then
      bad(string.format("Mancano %d fotogrammi (%s) per riempire il contenitore: il montato finisce a %s.",
        -diff, framesToTc(-diff, r), framesToTc(lastContent, r)))
    else
      ok("Il montato riempie esattamente il contenitore.")
    end
  else
    ok("Contenitore vuoto: monta dentro il range " .. framesToTc(ffoa, r) .. " → " .. framesToTc(lfoa, r) .. ".")
  end
elseif lastContent then
  lfoa = lastContent
  ok("Durata libera: il programma finisce con l'ultimo clip a " .. framesToTc(lfoa, r) .. ".")
else
  bad("Nessun clip dopo il leader: monta il programma da " .. framesToTc(ffoa, r) ..
    " e premi di nuovo Genera, oppure scegli una durata fissa (slot o personalizzata) per creare subito contenitore e coda.")
end
local durTc = lfoa and framesToTc(lfoa - ffoa + 1, r) or "—"

-- ---------------------------------------------------------------- 4) audio
local home = os.getenv("HOME") or os.getenv("USERPROFILE") or "."
local sep = package.config:sub(1, 1)
local cacheDir = home .. sep .. ".leaderkit"
pcall(function() bmd.createdir(cacheDir) end)
do
  local probe = io.open(cacheDir .. sep .. "probe.txt", "w")
  if probe then probe:close(); os.remove(cacheDir .. sep .. "probe.txt") else cacheDir = home end
end

-- WAV mono 16 bit 48 kHz, tono 1 kHz: toneSec di tono seguiti da silenzio fino a totalSec.
local function writeWav(path, level, toneSec, totalSec)
  local f = io.open(path, "rb")
  if f then
    local size = f:seek("end"); f:close()
    if size and size > 1000 then return true end
  end
  local sr = 48000
  local total, tone = math.floor(totalSec * sr), math.floor(toneSec * sr)
  local amp = (10 ^ (level / 20)) * 32767
  local function le(v, bytes)
    local t = {}
    for i = 1, bytes do t[i] = string.char(v % 256); v = math.floor(v / 256) end
    return table.concat(t)
  end
  local cycle = {}
  for i = 0, 47 do   -- 1 kHz a 48 kHz = 48 campioni per periodo
    local v = math.floor(amp * math.sin(2 * math.pi * i / 48) + 0.5)
    if v < 0 then v = v + 65536 end
    cycle[#cycle + 1] = le(v, 2)
  end
  local period = table.concat(cycle)
  local silence = string.rep("\0\0", 48)
  local parts = {}
  for i = 0, math.floor(total / 48) - 1 do
    parts[#parts + 1] = (i * 48 < tone) and period or silence
  end
  local data = table.concat(parts)
  f = io.open(path, "wb")
  if not f then return false end
  f:write("RIFF", le(36 + #data, 4), "WAVEfmt ", le(16, 4), le(1, 2), le(1, 2), le(sr, 4),
    le(sr * 2, 4), le(2, 2), le(16, 2), "data", le(#data, 4), data)
  f:close()
  return true
end

local function mediaFolder()
  local root = pool:GetRootFolder()
  for _, sub in ipairs(listOf(root:GetSubFolderList())) do
    if sub:GetName() == "LeaderKit" then return sub end
  end
  return pool:AddSubFolder(root, "LeaderKit")
end

local clipCache = {}
local function toneClip(level, toneSec, totalSec)
  local name = string.format("LeaderKit_%s_1kHz_%ddBFS.wav", toneSec >= totalSec and ("tone" .. math.floor(totalSec) .. "s") or "pop", level)
  if clipCache[name] then return clipCache[name] end
  local path = cacheDir .. sep .. name
  if not writeWav(path, level, toneSec, totalSec) then return nil end
  local folder = mediaFolder()
  if folder then
    for _, clip in ipairs(listOf(folder:GetClipList())) do
      if clip:GetName() == name then clipCache[name] = clip; return clip end
    end
  end
  local prev = pool:GetCurrentFolder()
  if folder then pool:SetCurrentFolder(folder) end
  local items = pool:ImportMedia({ path })
  if prev then pool:SetCurrentFolder(prev) end
  clipCache[name] = listOf(items)[1]
  return clipCache[name]
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

-- Varianti di AppendToTimeline (endFrame = durata - 1 + extra): la prima che da' la durata esatta vince.
local VARIANTS = { { extra = 1, mediaType = 2 }, { extra = 0, mediaType = 2 }, { extra = 1 }, { extra = 0 } }
local goodVariant = nil
local audioOk, audioFail = 0, 0
local function placeOn(clip, frame, len, track, mediaType)
  local list = goodVariant and { goodVariant } or VARIANTS
  for _, v in ipairs(list) do
    local info = { mediaPoolItem = clip, recordFrame = frame, trackIndex = track, startFrame = 0,
      endFrame = len - 1 + v.extra, mediaType = v.mediaType and mediaType or nil }
    local placed = listOf(pool:AppendToTimeline({ info }))
    if placed[1] then
      local good = placed[1]:GetStart() == frame and placed[1]:GetDuration() == len
      if good then goodVariant = v; return placed[1] end
      if placed[1]:GetStart() == frame and placed[1]:GetDuration() > 0 and mediaType == 1 then return placed[1] end
      tl:DeleteClips(placed, false)
    end
  end
  return nil
end

local function placeAudio(clip, frame, len, label)
  if not clip then audioFail = audioFail + 1; bad(label .. ": file audio non creato (" .. cacheDir .. ")."); return false end
  local track = ensurePopTrack()
  local list = goodVariant and { goodVariant } or VARIANTS
  for _, v in ipairs(list) do
    local info = { mediaPoolItem = clip, recordFrame = frame, trackIndex = track, startFrame = 0,
      endFrame = len - 1 + v.extra, mediaType = v.mediaType }
    local placed = listOf(pool:AppendToTimeline({ info }))
    if placed[1] then
      local good = true
      for _, it in ipairs(placed) do
        if it:GetStart() ~= frame or it:GetDuration() ~= len then good = false end
      end
      if good then goodVariant = v; audioOk = audioOk + 1; return true end
      tl:DeleteClips(placed, false)
    end
  end
  audioFail = audioFail + 1
  bad(label .. ": audio non posizionato a " .. framesToTc(frame, r) .. " (AppendToTimeline). Il marker c'e' comunque.")
  return false
end

local function marker(frame, color, name, note, tag, duration)
  local okm = tl:AddMarker(frame - tl:GetStartFrame(), color, name, note, duration or 1, PREFIX .. ":" .. tag)
  if not okm then bad("Marker '" .. name .. "' non aggiunto a " .. framesToTc(frame, r) .. " (fotogramma gia' occupato?).") end
end

local leaderStart = head:GetStart()
local syncTc, popTc = "—", "—"
if barsSec > 0 then
  local lvl = P.bars_dbfs or -18
  placeAudio(toneClip(lvl, 30, 30), leaderStart, math.floor(barsSec * n + 0.5), "Tono di line-up")
  marker(leaderStart, "Purple", "BARS", string.format("Barre 100%% + tono 1 kHz %d dBFS", lvl), "bars")
end
local slateStart = leaderStart + math.floor(barsSec * n + 0.5)
if slateSec > 0 then
  marker(slateStart, "Purple", P.clock and "CLOCK" or "SLATE", (P.clock and "Clock/ident " or "Slate ") ..
    framesToTc(slateStart, r) .. " (silenzio)", "slate")
end
if countFrom > 0 and P.pop then
  local pop = ffoa - 2 * n
  popTc = framesToTc(pop, r)
  placeAudio(toneClip(popLevel, 0.25, 1), pop, 1, "2-pop")
  marker(pop, "Cyan", "2-POP", string.format("2-pop %s — 1 kHz %d dBFS", popTc, popLevel), "pop")
  if beepEach then
    for d = countFrom, 3, -1 do placeAudio(toneClip(popLevel, 0.25, 1), ffoa - d * n, 1, "Bip " .. d) end
  end
end
if P.sync_flash then
  local before = math.floor(P.sync_flash.before_s * n + 0.5)
  local sf = ffoa - before
  syncTc = framesToTc(sf, r)
  placeAudio(toneClip(P.sync_flash.dbfs or popLevel, 0.25, 1), sf, 1, "Sync")
  marker(sf, "Cyan", "SYNC", "Sync " .. syncTc .. ": bianco + 1 fotogramma di tono", "sync")
end
marker(ffoa, "Blue", "FFOA", "First frame of action " .. framesToTc(ffoa, r), "ffoa")

-- ---------------------------------------------------------------- 5) contenitore, coda, marker
if lfoa then
  if slotFrames then
    marker(ffoa + 1, "Green", "CONTENITORE", "Programma " .. slotLabel .. ": " .. framesToTc(ffoa, r) .. " → " ..
      framesToTc(lfoa, r), "slot", math.max(1, slotFrames - 2))
  end
  marker(lfoa, "Blue", "LFOA", "Last frame of action " .. framesToTc(lfoa, r), "lfoa")
  local contentPastEnd = lastContent and lastContent > lfoa
  if tailOn and not contentPastEnd then
    local playhead = tl:GetCurrentTimecode()
    local tail, exact = insertExact(TAIL_NAME, lfoa + 1, tailLen)
    if playhead then tl:SetCurrentTimecode(playhead) end
    if tail then
      if tail:GetStart() ~= lfoa + 1 then bad("La coda e' stata inserita a " .. framesToTc(tail:GetStart(), r) .. " invece che a " .. framesToTc(lfoa + 1, r) .. ".") end
      if not exact then bad("La coda dura " .. framesToTc(tail:GetDuration(), r) .. " invece di " .. framesToTc(tailLen, r) .. ": allungala a mano.") end
      local tlk = lkOf(tail)
      set(tlk, "TailPop", P.tail_pop and 1 or 0)
      set(tlk, "TailFlash", P.tail_flash and 1 or 0)
      set(tlk, "CardFrom", P.card_from or 0)
      set(tlk, "CardTo", P.card_to or 0)
      set(tlk, "CardText", P.card_text or "")
      set(tlk, "Info", "LFOA " .. framesToTc(lfoa, r) .. "  ·  DURATION " .. durTc)
      for _, k in ipairs(COLORS) do set(tlk, k, get(k, nil)) end
      ok("Coda " .. framesToTc(tail:GetStart(), r) .. " → " .. framesToTc(tail:GetStart() + tail:GetDuration() - 1, r) .. ".")
      if (P.tail_pop or P.tail_flash) and tail:GetDuration() >= 2 * n then
        local tp = lfoa + 2 * n
        placeAudio(toneClip(popLevel, 0.25, 1), tp, 1, "Tail pop")
        marker(tp, "Cyan", P.tail_flash and "TAIL CLAP" or "TAIL POP", "Tail " .. framesToTc(tp, r), "tailpop")
      end
    else
      bad("Non riesco a inserire il generatore '" .. TAIL_NAME .. "': e' installato?")
    end
  elseif tailOn and contentPastEnd then
    bad("Coda non inserita: il montato va oltre la fine del contenitore (" .. framesToTc(lfoa, r) .. ").")
  end
  if markersOn and markerKind ~= "none" and markerEvery and markerEvery > 0 then
    local step = math.floor(markerEvery * 60 * n + 0.5)
    local k, frame = 1, ffoa + step
    while frame < lfoa do
      if markerKind == "reel" then
        marker(frame, "Red", "Fine rullo " .. k, string.format("Cambio rullo %d → %d a %s", k, k + 1, framesToTc(frame, r)), "reel:" .. k)
      else
        marker(frame, "Yellow", "Break " .. k, "Break " .. k .. " a " .. framesToTc(frame, r), "break:" .. k)
      end
      k = k + 1
      frame = frame + step
    end
    ok(string.format("Marker %s ogni %g': %d.", markerKind == "reel" and "fine rullo" or "break", markerEvery, k - 1))
  end
end
if audioOk == 1 then ok("1 clip audio posizionato sulla traccia '" .. POP_TRACK .. "'.")
elseif audioOk > 1 then ok(audioOk .. " clip audio posizionati sulla traccia '" .. POP_TRACK .. "'.") end

-- ---------------------------------------------------------------- 5b) logo
local function importImage(path)
  local folder = mediaFolder()
  local name = string.match(path, "[^/\\]+$") or path
  if folder then
    for _, clip in ipairs(listOf(folder:GetClipList())) do
      if clip:GetName() == name then return clip end
    end
  end
  local prev = pool:GetCurrentFolder()
  if folder then pool:SetCurrentFolder(folder) end
  local items = pool:ImportMedia({ path })
  if prev then pool:SetCurrentFolder(prev) end
  return listOf(items)[1]
end

local function logoTrack()
  for t = 1, tl:GetTrackCount("video") do
    if tl:GetTrackName("video", t) == LOGO_TRACK then return t end
  end
  tl:AddTrack("video")
  local t = tl:GetTrackCount("video")
  tl:SetTrackName("video", t, LOGO_TRACK)
  return t
end

local logoPath = tostring(get("Logo", "") or "")
logoPath = string.gsub(string.gsub(logoPath, "^%s+", ""), "%s+$", "")
logoPath = string.gsub(logoPath, "^[\"']", ""); logoPath = string.gsub(logoPath, "[\"']$", "")
if logoPath ~= "" then
  local fh = io.open(logoPath, "rb")
  if not fh then
    bad("Logo non trovato: " .. logoPath .. " (scrivi il percorso completo del file, es. /Users/nome/logo.png).")
  else
    fh:close()
    local clip = importImage(logoPath)
    if not clip then
      bad("Resolve non ha importato il logo " .. logoPath .. ".")
    else
      local size = (get("LogoSize", 20) or 20) / 100
      local pos = math.floor(get("LogoPos", 0) + 0.5)
      local w, h = tonumber(W) or 1920, tonumber(H) or 1080
      local mx, my = w * (0.5 - size / 2 - 0.04), h * (0.5 - size / 2 - 0.06)
      local pan, tilt = ({ mx, -mx, mx, -mx, 0 })[pos + 1], ({ my, my, -my, -my, 0 })[pos + 1]
      local track = logoTrack()
      local spans = {}
      if slateSec > 0 then spans[#spans + 1] = { slateStart, math.floor(slateSec * n + 0.5), "slate" } end
      if get("LogoOnTail", 0) > 0.5 and lfoa and tailOn then spans[#spans + 1] = { lfoa + 1, tailLen, "coda" } end
      for _, sp in ipairs(spans) do
        local it = placeOn(clip, sp[1], sp[2], track, 1)
        if it then
          pcall(function()
            it:SetProperty("ZoomX", size); it:SetProperty("ZoomY", size)
            it:SetProperty("Pan", pan); it:SetProperty("Tilt", tilt)
          end)
          if it:GetDuration() ~= sp[2] then
            bad("Il logo sulla " .. sp[3] .. " dura " .. framesToTc(it:GetDuration(), r) ..
              ": allungalo a mano (le immagini fisse hanno la durata standard delle preferenze).")
          else
            ok("Logo sulla " .. sp[3] .. " (traccia '" .. LOGO_TRACK .. "').")
          end
        else
          bad("Logo non posizionato sulla " .. sp[3] .. ".")
        end
      end
    end
  end
end

-- ---------------------------------------------------------------- 6) slate, guida, note
do
  local parts = {}
  local function add(label, key)
    local okk, v = pcall(function() return project:GetSetting(key) end)
    if okk and v and tostring(v) ~= "" then parts[#parts + 1] = label .. " " .. tostring(v) end
  end
  add("COLOR", "colorScienceMode")
  add("TIMELINE", "colorSpaceTimeline")
  add("OUTPUT", "colorSpaceOutput")
  if #parts > 0 then set(lk, "ColorInfo", table.concat(parts, "  ·  ")) end
end
local tokens = { ffoa = framesToTc(ffoa, r), lfoa = lfoa and framesToTc(lfoa, r) or "—",
  ps = countFrom > 0 and framesToTc(ffoa - countFrom * n, r) or "—", sync = syncTc, pop = popTc }
local lines = {}
for _, l in ipairs(P.slate_lines or {}) do
  if string.find(l, "{", 1, true) then
    lines[#lines + 1] = (string.gsub(l, "{(%w+)}", function(k) return tokens[k] or "" end))
  end
end
local info = "FFOA " .. framesToTc(ffoa, r)
if popTc ~= "—" then info = info .. "  ·  2-POP " .. popTc end
if lfoa then info = info .. "  ·  LFOA " .. framesToTc(lfoa, r) end
if r.df then info = info .. "  ·  DROP-FRAME" end
if #lines > 0 then info = info .. "\n" .. table.concat(lines, "\n") end
set(lk, "Duration", durTc)
set(lk, "Info", info)

local guide = "Start timeline " .. tl:GetStartTimecode() .. "\nLeader " .. framesToTc(head:GetStart(), r) ..
  " → programma da " .. framesToTc(ffoa, r) .. " (FFOA)"
if popTc ~= "—" then guide = guide .. "\n2-pop " .. popTc end
if syncTc ~= "—" then guide = guide .. "\nSync " .. syncTc end
if lfoa then guide = guide .. "\nLFOA " .. framesToTc(lfoa, r) .. (tailOn and (" · coda fino a " .. framesToTc(lfoa + tailLen, r)) or "") end
if slotFrames then guide = guide .. "\nContenitore " .. slotLabel end
set(lk, "Guide", guide)

log(string.format("Timeline %s — %s fps%s, %sx%s", tl:GetName(), rateLabel, r.df and " DF" or "", W, H))
log(guide)
report[#report + 1] = "\nCONTROLLI\n" .. table.concat(checks, "\n")
if P.notes and #P.notes > 0 then report[#report + 1] = "\nNOTE DELLO STANDARD\n- " .. table.concat(P.notes, "\n- ") end
warnings = {}   -- gia' elencati nei controlli
show("LeaderKit — Genera")
