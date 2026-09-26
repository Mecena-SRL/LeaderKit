-- ---------------------------------------------------------------- generate
-- (eseguito dopo engine_common.lua e engine_burnin.lua)
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
  return string.find(nm, "LeaderKit", 1, true) ~= nil and nm ~= TAIL_NAME and nm ~= BURN_NAME
    and not BURN.isBurn(item)
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
local presetIdx = math.floor(get("Preset", 0) + 0.5)
local P = presets[presetIdx + 1] or presets[1] or {}
local cat = P.category or "custom"
local custom = cat == "custom" and (get("Custom", 0) or 0) > 0.5
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
local markersOn = get("MarkersOn", 1) > 0.5 and (cat == "cinema" or cat == "custom")
local pm = P.markers or {}
local markerKind = (pm.kind == "reel") and "reel" or "none"
local markerEvery = get("MarkerEvery", 0)
if not markerEvery or markerEvery <= 0 then markerEvery = pm.every_min or 0 end
local breakChoice = math.floor(get("Breaks", 0) + 0.5)          -- 0 nessuno, 1 AVMSD, 2.. = 1..N break
local durMode = math.floor(get("DurSel", 0) + 0.5)               -- 0 libera, 1 slot, 2 personalizzata

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
  else bad("Risoluzione " .. W .. "x" .. H .. " non prevista da " .. (P.name or "") .. ". " .. (P.resolution_hint or "")) end
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
if durMode == 1 then
  local list = (LK_SLOTS or {})[cat]
  local input = (LK_SLOT_INPUTS or {})[cat]
  if not list or not input then
    bad("Lo standard '" .. (P.name or "") .. "' non ha slot standard: scegli durata Libera o Personalizzata.")
  else
    local sl = list[math.floor(get(input, 0) + 0.5) + 1] or list[1]
    slotFrames, slotLabel = math.floor(sl[2] * n + 0.5), sl[1]
  end
elseif durMode == 2 then
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
    trackNamesChanged()
  end
  return popTrack
end

-- Varianti di AppendToTimeline (endFrame = durata - 1 + extra): la prima che da' la durata esatta vince.
local VARIANTS = { { extra = 1, mediaType = 2 }, { extra = 0, mediaType = 2 }, { extra = 1 }, { extra = 0 } }
local goodVariant = nil
local audioOk, audioFail = 0, 0
local function placeOn(clip, frame, len, track, mediaType, src)
  src = src or 0
  local still = mediaType == 1
  local list = (goodVariant and not still) and { goodVariant } or VARIANTS
  local shorter = nil
  for _, v in ipairs(list) do
    local info = { mediaPoolItem = clip, recordFrame = frame, trackIndex = track, startFrame = src,
      endFrame = src + len - 1 + v.extra, mediaType = v.mediaType and mediaType or nil }
    local placed = listOf(pool:AppendToTimeline({ info }))
    if placed[1] then
      local st, d = placed[1]:GetStart(), placed[1]:GetDuration()
      if st == frame and d == len then
        if not still then goodVariant = v end
        if shorter then pcall(function() tl:DeleteClips({ shorter }, false) end) end
        return placed[1]
      end
      if still and st == frame and d > 0 and d < len and not shorter then
        shorter = placed[1]      -- immagine fissa piu' corta: la si tiene se non c'e' di meglio
      else
        tl:DeleteClips(placed, false)
      end
    end
  end
  return shorter
end

-- Immagine fissa su [frame, frame+len): se Resolve la accorcia alla durata
-- standard delle immagini, la si ripete fino a coprire tutto l'intervallo.
local function placeStill(clip, frame, len, track)
  local pieces, pos, remaining = {}, frame, len
  for _ = 1, 200 do
    if remaining <= 0 then break end
    local it = placeOn(clip, pos, remaining, track, 1)
    if not it and remaining > n then it = placeOn(clip, pos, n, track, 1) end
    if not it then break end
    local d = it:GetDuration()
    pieces[#pieces + 1] = it
    pos, remaining = pos + d, remaining - d
  end
  return pieces, remaining <= 0
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
    -- Se la coda cade oltre la fine attuale della timeline (contenitore ancora vuoto),
    -- un fotogramma di silenzio temporaneo estende la timeline fino alla fine della coda.
    -- Secondo tentativo: ancora sempre presente.
    local tail, exact = nil, false
    for attempt = 1, 2 do
      local anchor = nil
      local okEnd, tlEnd = pcall(function() return tl:GetEndFrame() end)
      if attempt == 2 or not okEnd or not tlEnd or tlEnd < lfoa + 1 + tailLen then
        local clip = toneClip(popLevel, 0.25, 1)
        if clip then anchor = placeOn(clip, lfoa + tailLen, 1, ensurePopTrack(), 2, math.floor(n / 2)) end
      end
      if tail then pcall(function() tl:DeleteClips({ tail }, false) end) end
      tail, exact = insertExact(TAIL_NAME, lfoa + 1, tailLen)
      if anchor then pcall(function() tl:DeleteClips({ anchor }, false) end) end
      if tail and tail:GetStart() == lfoa + 1 then break end
    end
    if playhead then tl:SetCurrentTimecode(playhead) end
    marker(lfoa + 1, "Purple", "CODA", "Inizio coda " .. framesToTc(lfoa + 1, r), "tail")
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
      local onTail = get("LogoOnTail", 0) > 0.5
      for _, k in ipairs({ "Logo", "Logo2" }) do set(tlk, k, onTail and get(k, "") or "") end
      for _, k in ipairs({ "LogoPos", "LogoSize", "LogoPos2", "LogoSize2" }) do set(tlk, k, get(k, nil)) end
      local tcomp = nil
      pcall(function() tcomp = tail:GetFusionCompByIndex(1) end)
      if tlk and tcomp then
        LK_IMAGE.sync(tcomp, tlk, "Logo", "Logo1Ld", "LogoW", "LogoH")
        LK_IMAGE.sync(tcomp, tlk, "Logo2", "Logo2Ld", "Logo2W", "Logo2H")
      end
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
  if (cat == "tv" or cat == "streaming") and breakChoice > 0 then
    local progFrames = lfoa - ffoa + 1
    local minutes = progFrames / (60 * n)
    local maxAvmsd = math.floor(minutes / 30)
    local nb = (breakChoice == 1) and maxAvmsd or (breakChoice - 1)
    if nb < 1 then
      bad(string.format("Programma di %.0f': con la regola AVMSD (1 interruzione ogni 30' programmati) non sono previsti break.", minutes))
    else
      for k = 1, nb do
        local frame = ffoa + math.floor(progFrames * k / (nb + 1) + 0.5)
        marker(frame, "Yellow", "Break " .. k, string.format("Break pubblicitario %d di %d a %s (fine parte %d)",
          k, nb, framesToTc(frame, r), k), "break:" .. k)
      end
      ok(string.format("%d break pubblicitari (parti uguali da %s).", nb, framesToTc(math.floor(progFrames / (nb + 1)), r)))
      if nb > maxAvmsd then
        bad(string.format("%d break su %.0f': per film, film TV e notiziari la direttiva AVMSD consente al massimo %d interruzioni (1 ogni 30' programmati). Per serie e documentari la regola non si applica.",
          nb, minutes, maxAvmsd))
      end
    end
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

-- ---------------------------------------------------------------- 5b) taratura, frame lines, logo
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

local function videoTrack(name)
  for t = 1, tl:GetTrackCount("video") do
    if tl:GetTrackName("video", t) == name then return t end
  end
  tl:AddTrack("video")
  local t = tl:GetTrackCount("video")
  tl:SetTrackName("video", t, name)
  trackNamesChanged()
  return t
end

local function describe(pieces, label, track)
  if #pieces == 0 then bad(label .. ": immagine non posizionata sulla traccia '" .. track .. "'."); return end
  if #pieces > 1 then
    ok(label .. " (traccia '" .. track .. "', " .. #pieces .. " pezzi: Resolve limita la durata delle immagini fisse).")
  else
    ok(label .. " (traccia '" .. track .. "').")
  end
end

local w, h = tonumber(W) or 1920, tonumber(H) or 1080
local function hash(str)
  local hv = 5381
  for i = 1, #str do hv = (hv * 33 + string.byte(str, i)) % 2147483647 end
  return string.format("%08x", hv)
end
local function resClass()
  if w >= 7680 then return "8K" elseif w >= 3996 then return "4K DCI" elseif w >= 3840 then return "UHD"
  elseif w >= 1998 then return "2K DCI" elseif w >= 1920 then return "HD" end
  return "SD"
end
local accent = { get("AccentRed", 0.85), get("AccentGreen", 0.85), get("AccentBlue", 0.85) }

local function overlay(kind, spec)
  local key = kind .. "|" .. w .. "x" .. h .. "|" .. table.concat(accent, ",")
  local ck = {}
  for k, v in pairs(spec.cal or {}) do ck[#ck + 1] = k .. "=" .. tostring(v) end
  table.sort(ck)
  key = key .. "|" .. table.concat(ck, "|") .. (spec.fpsLabel or "") .. (spec.resLabel or "")
  for _, d in ipairs({ spec.dialB, spec.dialC }) do
    if d then key = key .. string.format("|%g,%g,%g,%g", d.cx, d.cy, d.r, d.fps) end
  end
  local path = cacheDir .. sep .. string.format("LeaderKit_%s_%dx%d_%s.png", kind, w, h, hash(key))
  local fh = io.open(path, "rb")
  if fh then fh:close(); return path end
  local okr, err = LK_OVERLAY.render(path, w, h, spec)
  if not okr then bad("Immagine " .. kind .. " non creata: " .. tostring(err)); return nil end
  return path
end

-- taratura sul countdown (frame lines, safe area e pallino finale sono nel generatore, sotto i testi)
if countFrom > 0 and get("CalOn", 1) > 0.5 then
  local cal = {}
  for _, k in ipairs(LK_CALIBRATION or {}) do cal[string.lower(string.sub(k, 4))] = get(k, 1) > 0.5 end
  local path = overlay("Taratura", { accent = accent, cal = cal, fpsLabel = string.format("%g/SEC", r.fps), resLabel = resClass() })
  local clip = path and importImage(path)
  if path and not clip then bad("Resolve non ha importato " .. path .. ".") end
  if clip then
    local from = ffoa - countFrom * n
    local len = (countFrom - 2) * n + 1
    local pieces = placeStill(clip, from, len, videoTrack(GFX_TRACK))
    describe(pieces, "Taratura " .. w .. "x" .. h .. " sul countdown", GFX_TRACK)
  end
end

local slateStyle = math.floor(get("SlateStyle", 0) + 0.5)
local slateSpan = { head:GetStart() + math.floor(barsSec * n + 0.5), math.floor(slateSec * n + 0.5) }
if slateSec > 0 and (slateStyle == 1 or slateStyle == 2) and LK_DIALS then
  local d = LK_DIALS[slateStyle == 1 and "b" or "c"]
  local key = slateStyle == 1 and "dialB" or "dialC"
  local spec = { accent = accent }
  spec[key] = { cx = d[1], cy = d[2], r = d[3], fps = r.fps }
  local path = overlay(slateStyle == 1 and ("Quadrante" .. math.floor(r.fps + 0.5)) or "Orologio", spec)
  local clip = path and importImage(path)
  if clip then
    describe(placeStill(clip, slateSpan[1], slateSpan[2], videoTrack(GFX_TRACK)),
      (slateStyle == 1 and "Quadrante" or "Orologio") .. " della slate " .. w .. "x" .. h, GFX_TRACK)
  end
end

-- logo, secondo logo e titolo in PNG: dentro il generatore (nodi Loader), visibili subito.
-- Genera li ricarica nel blocco (anche se e' stato ricreato) e nella coda.
local IMAGES = { { "Logo", "Logo1Ld", "LogoW", "LogoH", "Logo" }, { "Logo2", "Logo2Ld", "Logo2W", "Logo2H", "Secondo logo" },
  { "TitleImage", "TitleLd", "TitleW", "TitleH", "Titolo in PNG" } }
for _, im in ipairs(IMAGES) do
  local st, path, iw, ih = LK_IMAGE.sync(c, lk, im[1], im[2], im[3], im[4])
  if st == "ok" then
    local where = slateSec > 0 and "sulla slate" or "(lo standard non ha slate)"
    if im[1] ~= "TitleImage" and get("LogoOnTail", 0) > 0.5 then where = where .. " e sulla coda" end
    ok(string.format("%s %s: %s, %dx%d px.", im[5], where, string.match(path, "[^/\\]+$") or path, iw, ih))
    if slateSec <= 0 and (im[1] == "TitleImage" or get("LogoOnTail", 0) <= 0.5) then
      bad(im[5] .. ": lo standard non ha slate" .. (im[1] == "TitleImage" and "." or "; attiva 'Loghi anche sulla coda' (scheda Aspetto) per vederlo."))
    end
  elseif st ~= "empty" then
    bad(LK_IMAGE.message(im[5], st, path))
  end
end

-- elementi fuori standard: si avvisa, ma restano come li hai scelti
if get("EndDot", 0) > 0.5 then
  if cat == "work" or cat == "custom" then
    ok("Pallino sull'ultimo fotogramma del leader (" .. framesToTc(ffoa - 1, r) .. "): il programma parte al fotogramma dopo.")
  else
    bad("Pallino sull'ultimo fotogramma del leader (" .. framesToTc(ffoa - 1, r) .. "): " .. (P.name or "lo standard") ..
      " prevede nero fino al FFOA. Va bene per uso interno; toglilo (scheda Guide) per la consegna.")
  end
end

-- ---------------------------------------------------------------- 5c) burn-in delle copie di lavoro
do
  local existing = {}
  for _, e in ipairs(allItems("video")) do
    if BURN.isBurn(e.item) then existing[#existing + 1] = e.item end
  end
  local title, version = get("Title", ""), get("Version", "")
  if P.burnin ~= nil and lfoa then
    local item = existing[1]
    if not item then
      -- Si blocca ogni altra traccia: Resolve puo' inserire il generatore solo sulla traccia del burn-in,
      -- cosi' il montato non viene mai toccato.
      local track = videoTrack(BURN_TRACK)
      local locked = {}
      local canLock = pcall(function()
        for _, kind in ipairs({ "video", "audio" }) do
          for t = 1, tl:GetTrackCount(kind) do
            if not (kind == "video" and t == track) then
              locked[#locked + 1] = { kind, t, tl:GetIsTrackLocked(kind, t) }
              tl:SetTrackLock(kind, t, true)
            end
          end
        end
        tl:SetTrackLock("video", track, false)
      end)
      if canLock then
        local playhead = tl:GetCurrentTimecode()
        item = insertExact(BURN_NAME, ffoa, lfoa - ffoa + 1)
        if playhead then tl:SetCurrentTimecode(playhead) end
      end
      for _, l in ipairs(locked) do pcall(function() tl:SetTrackLock(l[1], l[2], l[3] and true or false) end) end
      if item then
        local okt, ti = pcall(function() return item:GetTrackTypeAndIndex() end)
        local where = (okt and type(ti) == "table") and ti[2] or trackOf(item)
        if where ~= track then
          pcall(function() tl:DeleteClips({ item }, false) end)
          item = nil
        end
      end
      if not item then
        bad("Burn-in non inserito automaticamente: trascina 'LeaderKit Burn-in' (Effetti › Generators) su una traccia sopra il montato, " ..
          "da " .. framesToTc(ffoa, r) .. " a " .. framesToTc(lfoa, r) .. ", e premi 'Aggiorna dai metadati'.")
      end
    end
    if item then
      local lkb = BURN.lk(item)
      if lkb then
        local ph = LK_BURN_PHASES and LK_BURN_PHASES[P.burnin + 1]
        if ph and not existing[1] then
          set(lkb, "BPhase", P.burnin)
          local onf = {}
          for _, k in ipairs(ph.fields) do onf[k] = true end
          for _, k in ipairs(LK_BURN_FIELDS or {}) do set(lkb, k, onf[k] and 1 or 0) end
          set(lkb, "BFrameMode", ph.frame)
        end
        local msg = BURN.fill(item, lkb, { title = title, version = version })
        ok(msg .. " Traccia '" .. BURN_TRACK .. "' (o quella dove l'hai messo).")
        if item:GetStart() ~= ffoa or item:GetStart() + item:GetDuration() - 1 ~= lfoa then
          bad("Il burn-in va da " .. framesToTc(item:GetStart(), r) .. " a " ..
            framesToTc(item:GetStart() + item:GetDuration() - 1, r) .. ": allungalo al programma (" ..
            framesToTc(ffoa, r) .. " → " .. framesToTc(lfoa, r) .. ") e premi 'Aggiorna dai metadati'.")
        end
      end
    end
  else
    for _, item in ipairs(existing) do
      local lkb = BURN.lk(item)
      if lkb then ok(BURN.fill(item, lkb, { title = title, version = version })) end
    end
    if P.burnin ~= nil and not lfoa then
      bad("Burn-in: serve la fine del programma (monta i clip o scegli una durata) per sapere quanto deve durare.")
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
  -- sulla slate va lo spazio colore di uscita (quello del file consegnato)
  add("", "colorSpaceOutput")
  if #parts == 0 then add("", "colorScienceMode") end
  if #parts > 0 then set(lk, "ColorInfo", (string.gsub(parts[1], "^%s+", ""))) end
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
if get("DateAuto", 1) > 0.5 then set(lk, "Date", os.date("%d/%m/%Y")) end
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
if P.unverified then
  checks[#checks + 1] = "⚠ Standard senza specifica pubblica: i valori sono un riferimento, verificali con il capitolato del committente."
end
report[#report + 1] = "\nCONTROLLI\n" .. table.concat(checks, "\n")
if P.notes and #P.notes > 0 then report[#report + 1] = "\nNOTE DELLO STANDARD\n- " .. table.concat(P.notes, "\n- ") end
warnings = {}   -- gia' elencati nei controlli
show("LeaderKit — Genera")
