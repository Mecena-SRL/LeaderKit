-- LeaderKit engine: eseguito dai bottoni del generatore "LeaderKit Head".
-- LK_MODE = "generate" | "remove" | "burnin" | "images" (impostato dal bottone).
-- "images" rifa' solo le immagini (taratura, frame lines, slate fissa, titolo, loghi) senza toccare
-- blocco, coda, audio, marker, timecode e burn-in.
-- Tutto viene ricalcolato sul frame rate e sul drop-frame reali della timeline.

local MODE = LK_MODE or "generate"
local FULL = MODE ~= "images"
local PREFIX = "leaderkit"
local POP_TRACK = "LeaderKit Pop"
local TAIL_NAME = "LeaderKit Tail"
local LOGO_TRACK = "LeaderKit Logo"
local GFX_TRACK = "LeaderKit Grafica"
local SLATE_TRACK = "LeaderKit Slate"
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

-- In caso di errore imprevisto: riepilogo con quanto fatto fino a quel punto e l'errore
LK_FAIL = function(err)
  report[#report + 1] = "\nERRORE INTERNO (Genera si e' fermato qui, il resto non e' stato fatto):\n" .. tostring(err)
  show("LeaderKit — errore")
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
-- Lettura di un input: GetInput, poi (per selettore file e casi particolari) il valore all'istante corrente.
local function readInput(t, name)
  if not t then return nil end
  local okk, v = pcall(function() return t:GetInput(name) end)
  if okk and v ~= nil then
    if type(v) == "table" then v = v[1] or v.Value or v.Filename end
    if v ~= nil then return v end
  end
  okk, v = pcall(function() return t[name][fu.TIME_UNDEFINED] end)
  if okk and v ~= nil and type(v) ~= "table" then return v end
  okk, v = pcall(function() return t[name][(c or comp).CurrentTime] end)
  if okk and v ~= nil and type(v) ~= "table" then return v end
  return nil
end
-- Fotografia dei parametri al momento in cui si preme il bottone: Genera legge sempre questi valori,
-- anche dopo aver ricreato il blocco (dove la copia di alcuni campi potrebbe non riuscire).
local SNAP = {}
for _, k in ipairs(LK_PARAMS or {}) do SNAP[k] = readInput(lk, k) end
local function get(name, default)
  local v = SNAP[name]
  if v == nil then v = readInput(lk, name) end
  if v ~= nil then return v end
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
  if name == TAIL_NAME or name == HEAD_NAME or name == BURN_NAME then return true end
  if string.sub(name, 1, 10) == "LeaderKit_" then return true end
  if kind == "audio" and tl:GetTrackName("audio", entry.track) == POP_TRACK then return true end
  if kind == "video" then
    local tn = tl:GetTrackName("video", entry.track)
    if tn == LOGO_TRACK or tn == LOGO_TRACK .. " 2" or tn == LOGO_TRACK .. " Titolo" or tn == GFX_TRACK
      or tn == BURN_TRACK or tn == SLATE_TRACK then return true end
  end
  return false
end

local function imageTrack(tn)
  return tn == LOGO_TRACK or tn == LOGO_TRACK .. " 2" or tn == LOGO_TRACK .. " Titolo" or tn == GFX_TRACK
    or tn == SLATE_TRACK
end
-- solo le immagini (per "Aggiorna solo le immagini")
local function cleanupImages()
  local doomed = {}
  for _, e in ipairs(allItems("video")) do
    if imageTrack(tl:GetTrackName("video", e.track)) then doomed[#doomed + 1] = e.item end
  end
  if #doomed > 0 then tl:DeleteClips(doomed, false) end
  return 0, #doomed
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
    local tn = tl:GetTrackName("video", e.track)
    if e.item:GetName() == TAIL_NAME or imageTrack(tn) or tn == BURN_TRACK then
      doomed[#doomed + 1] = e.item
    end
  end
  if #doomed > 0 then tl:DeleteClips(doomed, false) end
  return nm, #doomed
end

-- ---------------------------------------------------------------- burn-in (copie di lavoro)
local BURN = {}
function BURN.isBurn(item)
  local okk, has = pcall(function()
    local t = findTool(item:GetFusionCompByIndex(1), "LK")
    return t ~= nil and t:GetInput("BPhase") ~= nil
  end)
  if okk and has then return true end
  return (item:GetName() or "") == BURN_NAME
end
function BURN.lk(item)
  local okk, t = pcall(function() return findTool(item:GetFusionCompByIndex(1), "LK") end)
  return okk and t or nil
end
local function clean(v)
  v = tostring(v or "")
  v = string.gsub(v, "[|~\r\n]", " ")
  return (string.gsub(string.gsub(v, "^%s+", ""), "%s+$", ""))
end
function BURN.meta(mpi, keys)
  if not mpi then return "" end
  for _, k in ipairs(keys) do
    for _, fn in ipairs({ "GetMetadata", "GetClipProperty" }) do
      local okk, v = pcall(function() return mpi[fn](mpi, k) end)
      if okk and type(v) ~= "table" and v ~= nil and clean(v) ~= "" then return clean(v) end
    end
  end
  return ""
end
function BURN.mpi(it)
  local okk, m = pcall(function() return it:GetMediaPoolItem() end)
  return okk and m or nil
end
function BURN.srcStart(it)
  local okk, v = pcall(function() return it:GetSourceStartFrame() end)
  if okk and type(v) == "number" then return v end
  okk, v = pcall(function() return it:GetLeftOffset() end)
  if okk and type(v) == "number" then return v end
  return 0
end
local function joinb(t, sepr)
  local out = {}
  for _, v in ipairs(t) do if v and v ~= "" then out[#out + 1] = v end end
  return table.concat(out, sepr or "   ")
end

-- Riempie un clip Burn-in con i dati dei clip sotto di lui (uno per segmento).
function BURN.fill(item, lkb, opts)
  opts = opts or {}
  local function on(k) local okk, v = pcall(function() return lkb:GetInput(k) end); return okk and (v or 0) > 0.5 end
  local function txt(k) local okk, v = pcall(function() return lkb:GetInput(k) end); return okk and clean(v) or "" end
  local rs = item:GetStart()
  local re_ = rs + item:GetDuration()
  local function users(kind)
    local out = {}
    for _, e in ipairs(allItems(kind)) do
      local st = e.item:GetStart()
      local en = st + e.item:GetDuration()
      local nm = e.item:GetName() or ""
      if en > rs and st < re_ and not isLeaderKit(e, kind) and string.find(nm, "LeaderKit", 1, true) == nil then
        out[#out + 1] = { item = e.item, track = e.track, st = st, en = en }
      end
    end
    return out
  end
  local vids, auds = users("video"), users("audio")
  local cuts = { [rs] = true, [re_] = true }
  for _, v in ipairs(vids) do
    if v.st > rs and v.st < re_ then cuts[v.st] = true end
    if v.en > rs and v.en < re_ then cuts[v.en] = true end
  end
  local points = {}
  for f in pairs(cuts) do points[#points + 1] = f end
  table.sort(points)
  local title = txt("BTitleText"); if title == "" then title = clean(opts.title) end
  local version = txt("BVersionText"); if version == "" then version = clean(opts.version) end
  local fmt = string.format("%g fps  %sx%s", r.fps, tostring(W), tostring(H))
  local color = ""
  pcall(function() color = clean(project:GetSetting("colorSpaceOutput")) end)
  local frameMode = 1
  pcall(function() frameMode = math.floor((lkb:GetInput("BFrameMode") or 1) + 0.5) end)
  local lines, clips = {}, 0
  for i = 1, #points - 1 do
    local a, b = points[i], points[i + 1]
    local v = nil
    for _, x in ipairs(vids) do
      if x.st <= a and x.en > a and (not v or x.track > v.track) then v = x end
    end
    local srcv, step, sn, sd, fr0 = -1, 1, r.nominal, r.drop, a - rs
    local tl1, tl2, tr1, tr2, bl1, bl2 = "", "", "", "", "", ""
    local mpi = v and BURN.mpi(v.item)
    if v then
      clips = clips + 1
      local cfps = tonumber(string.match(BURN.meta(mpi, { "FPS" }), "[%d%.]+") or "") or r.fps
      local stc = BURN.meta(mpi, { "Start TC" })
      local cr = makeRate(tostring(cfps), string.find(stc, ";", 1, true) and "1" or "0")
      sn, sd, step = cr.nominal, cr.drop, cfps / r.fps
      local base = string.match(stc, "%d+[:;]%d+[:;]%d+[:;.]%d+") and tcToFrames(stc, cr) or 0
      srcv = base + BURN.srcStart(v.item) + (a - v.st) * step
      if frameMode == 0 then fr0 = 1001 + (a - v.st) elseif frameMode == 1 then fr0 = a - v.st end
      if on("BClip") then tr1 = clean(v.item:GetName()) end
      local sc = BURN.meta(mpi, { "Scene" })
      local shot = BURN.meta(mpi, { "Shot" })
      local tk = BURN.meta(mpi, { "Take" })
      local good = BURN.meta(mpi, { "Good Take", "Circled" })
      local scene = joinb({ sc ~= "" and ("SC " .. sc .. (shot ~= "" and ("/" .. shot) or "")) or "",
        tk ~= "" and ("TK " .. tk) or "", (good == "1" or string.lower(good) == "true" or string.lower(good) == "yes") and "CIRCLED" or "" }, " ")
      local cam = BURN.meta(mpi, { "Camera #", "Camera", "Angle" })
      local reel = joinb({ BURN.meta(mpi, { "Reel Name", "Reel Number", "Reel" }), BURN.meta(mpi, { "Roll Card #", "Roll/Card" }) }, " / ")
      tr2 = joinb({ on("BScene") and scene or "", on("BCam") and cam ~= "" and ("CAM " .. cam) or "", on("BReel") and reel or "" })
      if on("BDate") then
        local d = BURN.meta(mpi, { "Shoot Day", "Date Recorded", "Date Created" })
        tl2 = d ~= "" and d or os.date("%d/%m/%Y")
      end
    elseif on("BDate") then
      tl2 = os.date("%d/%m/%Y")
    end
    tl1 = joinb({ on("BTitle") and string.upper(title) or "", on("BVersion") and version or "" })
    tl2 = joinb({ tl2, on("BFormat") and fmt or "", on("BColor") and color or "" })
    if on("BSrc") then bl1 = "SRC {SRC}" end
    local aud = -1
    if on("BAtc") then
      local au = nil
      for _, x in ipairs(auds) do
        if x.st <= a and x.en > a and (not au or x.track < au.track) then au = x end
      end
      if au then
        local ampi = BURN.mpi(au.item)
        local atc = BURN.meta(ampi, { "Start TC" })
        if string.match(atc, "%d+[:;]%d+[:;]%d+[:;.]%d+") then
          aud = tcToFrames(atc, r) + BURN.srcStart(au.item) + (a - au.st)
        end
        local roll = BURN.meta(ampi, { "Sound Roll #", "Reel Name" })
        if roll == "" then roll = BURN.meta(mpi, { "Sound Roll #" }) end
        bl2 = "SND {ATC}" .. (roll ~= "" and ("   " .. roll) or "")
      else
        bl2 = "SND --"
      end
    end
    local br1, br2 = on("BRec") and "REC {REC}" or "", on("BFrame") and "FR {FRM}" or ""
    if tl1 == "" then tl1, tl2 = tl2, "" end
    if tr1 == "" then tr1, tr2 = tr2, "" end
    if bl2 == "" then bl2, bl1 = bl1, "" end
    if br2 == "" then br2, br1 = br1, "" end
    lines[#lines + 1] = string.format("%d|%d|%s|%s|%d|%d|%d|%d|%s~%s|%s~%s|%s~%s|%s~%s~{REC}",
      a, b, string.format("%.4f", srcv), string.format("%.6f", step), sn, sd, aud, fr0,
      tl1, tl2, tr1, tr2, bl1, bl2, br1, br2)
  end
  set(lkb, "Seg", table.concat(lines, "\n"))
  set(lkb, "RecStart", rs)
  set(lkb, "TlFps", r.nominal)
  set(lkb, "TlDrop", r.drop)
  set(lkb, "TlW", tonumber(W) or 0)          -- risoluzione vera della timeline per mascherino e testi
  set(lkb, "TlH", tonumber(H) or 0)
  set(lkb, "FW", tonumber(W) or 0); set(lkb, "FH", tonumber(H) or 0); set(lkb, "FR", r.fps or 0)
  local msg = string.format("Burn-in %s → %s: %d segmenti, %d clip letti dai metadati.",
    framesToTc(rs, r), framesToTc(re_ - 1, r), #points - 1, clips)
  set(lkb, "BInfo", msg)
  return msg, clips
end

if MODE == "burnin" then
  local target = nil
  local cur = tl:GetCurrentVideoItem()
  if cur and BURN.isBurn(cur) then target = cur end
  local all = {}
  for _, e in ipairs(allItems("video")) do if BURN.isBurn(e.item) then all[#all + 1] = e.item end end
  if not target then target = all[1] end
  if not target then log("Non trovo il clip LeaderKit Burn-in sulla timeline."); show("LeaderKit Burn-in"); return end
  local title = ""
  for _, e in ipairs(allItems("video")) do
    local t = BURN.lk(e.item)
    if t and not BURN.isBurn(e.item) then
      local okk, v = pcall(function() return t:GetInput("Title") end)
      if okk and v and v ~= "" then title = v; break end
    end
  end
  local msg = BURN.fill(target, BURN.lk(target) or lk, { title = title })
  log(msg)
  log("I dati si aggiornano solo con questo bottone: premilo di nuovo dopo aver cambiato montaggio, campi o metadati.")
  show("LeaderKit Burn-in")
  return
end

if MODE == "remove" then
  local nm, ni = cleanup()
  log(string.format("Rimossi %d marker e %d clip LeaderKit (audio, coda, taratura, logo). Il clip Head resta.", nm, ni))
  show("LeaderKit — Rimuovi")
  return
end

-- ---------------------------------------------------------------- generate
local checks = {}
local function ok(s) checks[#checks + 1] = "✓ " .. s end
local function bad(s) checks[#checks + 1] = "⚠ " .. s; warnings[#warnings + 1] = s end
LK_FAIL = function(err)
  report[#report + 1] = "\nCONTROLLI\n" .. table.concat(checks, "\n")
  report[#report + 1] = "\nERRORE INTERNO (Genera si e' fermato qui, il resto non e' stato fatto):\n" .. tostring(err)
  show("LeaderKit — errore")
end
-- Una parte che si rompe non ferma le altre: l'errore finisce nel riepilogo.
local function stage(label, fn)
  local okS, err = xpcall(fn, function(e2)
    return tostring(e2) .. ((debug and debug.traceback) and ("\n" .. debug.traceback("", 2)) or "")
  end)
  if not okS then
    bad(label .. ": non riuscito, il resto e' stato fatto lo stesso. Dettagli: " .. string.sub(tostring(err), 1, 700))
  end
  return okS
end

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

local nm, ni
if FULL then nm, ni = cleanup() else nm, ni = cleanupImages() end
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
if not FULL and head:GetDuration() ~= headLen then
  bad("Il blocco LeaderKit Head non ha la durata dello standard (" .. framesToTc(headLen, r) ..
    "): premi prima 'Genera sulla timeline' (scheda Progetto).")
  report[#report + 1] = "\nCONTROLLI\n" .. table.concat(checks, "\n")
  warnings = {}
  show("LeaderKit — Aggiorna immagini"); return
end
if head:GetDuration() ~= headLen then
  local saved = {}
  for _, k in ipairs(PARAMS) do saved[k] = get(k, nil) end
  tl:DeleteClips({ head }, false)
  local newHead, exact = insertExact(HEAD_NAME, S, headLen)
  if not newHead then bad("Non riesco a ricreare il blocco LeaderKit Head."); show("LeaderKit"); return end
  head = newHead
  pcall(function() local nc = head:GetFusionCompByIndex(1); if nc then c = nc end end)
  panel = lkOf(head)
  if panel then
    local lost = {}
    for k, v in pairs(saved) do
      set(panel, k, v)
      local back = readInput(panel, k)
      if back == nil or tostring(back) ~= tostring(v) then lost[#lost + 1] = k end
    end
    table.sort(lost)
    if #lost > 0 then
      bad("Nel blocco ricreato Resolve non ha accettato: " .. table.concat(lost, ", ") ..
        ". Genera usa comunque i valori che avevi impostato; se nell'Inspector li vedi diversi, reimpostali.")
    end
  else bad("Parametri non ricopiati nel nuovo blocco (pannello non trovato): Genera usa comunque i valori impostati.") end
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
-- input nascosti: si scrivono sia sul pannello del bottone sia sul nodo LK dentro il blocco
local lkInner = lkOf(head)
local function setHead(name, value)
  set(lk, name, value)
  if lkInner and lkInner ~= lk then set(lkInner, name, value) end
end
-- formato della timeline per le espressioni (cosi' non lo chiedono alla composizione a ogni fotogramma)
setHead("FW", tonumber(W) or 0); setHead("FH", tonumber(H) or 0); setHead("FR", r.fps or 0)
setHead("SlateBaked", 0)

-- ---------------------------------------------------------------- 2) start timecode
local ffoaTc = P.ffoa or "01:00:00:00"
if P.ffoa_hour_per_reel then ffoaTc = string.format("%02d%s", reel, string.sub(ffoaTc, 3)) end
local ffoaTarget = tcToFrames(ffoaTc, r)
local oldStartTc = tl:GetStartTimecode()
local newStart = ffoaTarget - (ffoa - tl:GetStartFrame())
if newStart < 0 then
  bad("Il blocco e' troppo lontano dall'inizio della timeline per portare il FFOA a " .. ffoaTc ..
    ": avvicinalo all'inizio e premi di nuovo Genera.")
elseif newStart ~= tl:GetStartFrame() and not FULL then
  bad("Lo start della timeline non porta il FFOA a " .. ffoaTc .. ": premi 'Genera sulla timeline'.")
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
  if not FULL then return true end
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
  if not FULL then return end
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
  if tailOn and not contentPastEnd and FULL then
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
      set(tlk, "FW", tonumber(W) or 0); set(tlk, "FH", tonumber(H) or 0); set(tlk, "FR", r.fps or 0)
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
if not FULL then
  -- in "Aggiorna solo le immagini" i controlli di durate e coda non servono
  for i = #checks, 1, -1 do checks[i] = nil end
  ok("Aggiornate solo le immagini: blocco, coda, audio, marker e burn-in non sono stati toccati.")
end
-- Tutti i clip del Media Pool (ricorsivo)
local poolWalk = nil
local function poolClips()
  if poolWalk then return poolWalk end
  local out = {}
  local function walk(folder, depth)
    if not folder or depth > 12 then return end
    local okc, clips = pcall(function() return folder:GetClipList() end)
    for _, cl in ipairs(okc and listOf(clips) or {}) do out[#out + 1] = { clip = cl, folder = folder } end
    local oks, subs = pcall(function() return folder:GetSubFolderList() end)
    for _, sub in ipairs(oks and listOf(subs) or {}) do walk(sub, depth + 1) end
  end
  walk(pool:GetRootFolder(), 0)
  poolWalk = out
  return out
end
local function clipProp(clip, key)
  local okp, v = pcall(function() return clip:GetClipProperty(key) end)
  if okp and type(v) ~= "table" and v ~= nil then return tostring(v) end
  return ""
end
local function normPath(p) return (string.gsub(string.lower(tostring(p or "")), "\\", "/")) end

-- percorso -> clip del Media Pool, costruito una volta sola (le proprieta' dei clip sono lente da leggere)
local poolByPath = nil
local function findInPool(path)
  if not poolByPath then
    poolByPath = {}
    for _, e in ipairs(poolClips()) do
      local fp = clipProp(e.clip, "File Path")
      if fp ~= "" then poolByPath[normPath(fp)] = e.clip end
    end
  end
  return poolByPath[normPath(path)]
end
local function importImage(path)
  local name = string.match(path, "[^/\\]+$") or path
  local folder = mediaFolder()
  -- 1) nel bin LeaderKit (immagini generate le altre volte)
  if folder then
    for _, clip in ipairs(listOf(folder:GetClipList())) do
      if normPath(clipProp(clip, "File Path")) == normPath(path) then return clip end
    end
  end
  -- 2) importazione
  local prev = pool:GetCurrentFolder()
  if folder then pool:SetCurrentFolder(folder) end
  local okI, items = pcall(function() return pool:ImportMedia({ path }) end)
  if prev then pool:SetCurrentFolder(prev) end
  local clip = okI and listOf(items)[1] or nil
  if clip then
    if poolByPath then poolByPath[normPath(path)] = clip end
    return clip
  end
  -- 3) gia' altrove nel Media Pool (Resolve non reimporta un file gia' presente)
  clip = findInPool(path)
  if clip then return clip end
  if folder then
    for _, cl in ipairs(listOf(folder:GetClipList())) do
      if cl:GetName() == name then return cl end
    end
  end
  return nil
end

-- Immagine scelta dall'utente: file dal selettore, oppure clip del Media Pool
-- (con lo stesso nome, o il primo clip del bin indicato). Ritorna clip, percorso, descrizione.
local function userImage(key, bin, label)
  local v = get(key, "")
  if type(v) == "table" then v = v[1] or v.Value or "" end
  v = tostring(v or "")
  v = string.gsub(string.gsub(v, "^%s+", ""), "%s+$", "")
  v = string.gsub(string.gsub(v, "^[\"']", ""), "[\"']$", "")
  v = string.gsub(v, "^file://", "")
  if v ~= "" then
    local fh = io.open(v, "rb")
    if fh then
      fh:close()
      local clip = importImage(v)
      if clip then return clip, v end
      bad(label .. ": Resolve non ha importato " .. v .. " (formato non supportato?).")
      return nil
    end
  end
  local base = v ~= "" and (string.match(v, "[^/\\]+$") or v) or nil
  for _, e in ipairs(poolClips()) do
    local fname = e.folder and select(2, pcall(function() return e.folder:GetName() end)) or ""
    if (base and e.clip:GetName() == base) or (not base and fname == bin) then
      return e.clip, clipProp(e.clip, "File Path")
    end
  end
  if v ~= "" then
    bad(label .. ": file non trovato (" .. v .. "). Sceglilo di nuovo nella scheda Aspetto, oppure metti l'immagine nel bin '" ..
      bin .. "' del Media Pool.")
  end
  return nil
end

local function videoTrack(name)
  for t = 1, tl:GetTrackCount("video") do
    if tl:GetTrackName("video", t) == name then return t end
  end
  tl:AddTrack("video")
  local t = tl:GetTrackCount("video")
  tl:SetTrackName("video", t, name)
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
local frameLines = {}
for _, fl in ipairs(LK_FRAMELINES or {}) do
  if get(fl[1], fl[4] or 0) > 0.5 then frameLines[#frameLines + 1] = { ar = fl[3], label = fl[2] } end
end
local guidesOn = get("Guides", 1) > 0.5
if not guidesOn then frameLines = {} end
local safeA, safeT = guidesOn and get("SafeAction", 0) > 0.5, guidesOn and get("SafeTitle", 0) > 0.5

local function overlay(kind, spec)
  local key = kind .. "|" .. w .. "x" .. h .. "|" .. table.concat(accent, ",")
  for _, fl in ipairs(spec.framelines) do key = key .. "|" .. fl.label end
  for k, v in pairs(spec.cal or {}) do key = key .. "|" .. k .. "=" .. tostring(v) end
  key = key .. "|" .. tostring(spec.safeAction) .. tostring(spec.safeTitle) .. (spec.fpsLabel or "") .. (spec.resLabel or "")
  local path = cacheDir .. sep .. string.format("LeaderKit_%s_%dx%d_%s.png", kind, w, h, hash(key))
  local fh = io.open(path, "rb")
  if fh then fh:close(); return path end
  local okr, err = LK_OVERLAY.render(path, w, h, spec)
  if not okr then bad("Immagine " .. kind .. " non creata: " .. tostring(err)); return nil end
  return path
end

-- fascia libera sotto il cerchio del countdown (per i dati del progetto e il piccolo logo)
local cdFree = nil
stage("Taratura e frame lines sul countdown", function()
if countFrom > 0 and (get("CalOn", 1) > 0.5 or #frameLines > 0 or safeA or safeT) then
  local calOn = get("CalOn", 1) > 0.5
  local cal = nil
  if calOn then
    cal = {}
    for _, k in ipairs(LK_CALIBRATION or {}) do cal[string.lower(string.sub(k, 4))] = get(k, 1) > 0.5 end
  end
  local cdSpec = { accent = accent, cal = cal, framelines = frameLines,
    safeAction = safeA, safeTitle = safeT, fpsLabel = string.format("%g/SEC", r.fps), resLabel = resClass() }
  pcall(function() LK_OVERLAY.compose(w, h, cdSpec); cdFree = LK_OVERLAY.lastFreeArea end)
  local path = overlay(calOn and "Taratura" or "FrameLines", cdSpec)
  local clip = path and importImage(path)
  if path and not clip then bad("Resolve non ha importato " .. path .. ".") end
  if clip then
    local from = ffoa - countFrom * n
    local len = (countFrom - 2) * n + 1
    local pieces = placeStill(clip, from, len, videoTrack(GFX_TRACK))
    describe(pieces, (calOn and "Taratura" or "Frame lines") .. " " .. w .. "x" .. h .. " sul countdown", GFX_TRACK)
  end
elseif countFrom <= 0 and (#frameLines > 0 or safeA or safeT) then
  ok("Frame lines: questo standard non ha countdown; attiva 'Anche sulla slate' (scheda Tecnico) per vederle.")
end
end)
local cdY, cdCap = 0.075, 0.014
do
  local R = cdFree or { 0.018 * h, 0.018 * h, w - 0.018 * h, h - 0.018 * h }
  local bm = (h - R[4]) / h                             -- bordo inferiore dell'area libera (dal basso)
  local rb = 0.5 - (0.18 + 0.012) * w / h               -- fondo del cerchio del countdown (dal basso)
  if rb - bm < 0.03 then rb = bm + 0.03 end
  cdY = (bm + rb) / 2
  cdCap = math.max(0.006, math.min(0.016, (rb - bm) / 4.2))
  setHead("CdY", cdY); setHead("CdCap", cdCap)
end
stage("Frame lines sulla slate", function()
if slateSec > 0 and get("GuidesSlate", 0) > 0.5 and (#frameLines > 0 or safeA or safeT) then
  local path = overlay("FrameLines", { accent = accent, framelines = frameLines, safeAction = safeA, safeTitle = safeT })
  local clip = path and importImage(path)
  if clip then
    local slateAt = head:GetStart() + math.floor(barsSec * n + 0.5)
    describe(placeStill(clip, slateAt, math.floor(slateSec * n + 0.5), videoTrack(GFX_TRACK)), "Frame lines sulla slate", GFX_TRACK)
  end
end
end)

-- dimensioni di un PNG (per impaginare titolo e loghi); nil per altri formati
local function pngSize(path)
  local fh = io.open(path, "rb")
  if not fh then return nil end
  local hd = fh:read(24); fh:close()
  if not hd or #hd < 24 or hd:sub(1, 8) ~= "\137PNG\r\n\26\n" then return nil end
  local function be(i) local a, b2, c2, d = hd:byte(i, i + 3); return ((a * 256 + b2) * 256 + c2) * 256 + d end
  return be(17), be(21)
end
-- zoom/pan/tilt di Resolve per mettere un'immagine in un riquadro (pixel), con l'immagine adattata al quadro
local function imageSize(clip, path)
  local rw, rh = string.match(clipProp(clip, "Resolution"), "(%d+)%s*[xX]%s*(%d+)")
  if rw then return tonumber(rw), tonumber(rh) end
  if path and path ~= "" then return pngSize(path) end
  return nil
end
local function fitBox(clip, path, bw, bh, cxp, cyp, anchorLeft)
  local iw, ih = imageSize(clip, path)
  if not iw or iw <= 0 or ih <= 0 then iw, ih = w, h end
  local f = math.min(w / iw, h / ih)
  local z = math.min(bw / (iw * f), bh / (ih * f))
  local dw, dh = iw * f * z, ih * f * z
  if anchorLeft == "left" then cxp = cxp + dw / 2 elseif anchorLeft == "right" then cxp = cxp - dw / 2 end
  return z, cxp - w / 2, cyp - h / 2, dw, dh
end
local function placeImage(clip, span, track, label, z, pan, tilt)
  local pieces = placeStill(clip, span[1], span[2], track)
  for _, it in ipairs(pieces) do
    pcall(function()
      it:SetProperty("ZoomX", z); it:SetProperty("ZoomY", z)
      it:SetProperty("Pan", pan); it:SetProperty("Tilt", tilt)
    end)
  end
  describe(pieces, label, tl:GetTrackName("video", track) or "")
end

local slateStyle = math.floor(get("SlateStyle", 0) + 0.5)
local slateSpan = { head:GetStart() + math.floor(barsSec * n + 0.5), math.floor(slateSec * n + 0.5) }
stage("Quadrante della slate", function()
if slateSec > 0 and (slateStyle == 1 or slateStyle == 2) and LK_DIALS then
  local d = LK_DIALS[slateStyle == 1 and "b" or "c"]
  local key = slateStyle == 1 and "dialB" or "dialC"
  local spec = { accent = accent, framelines = {} }
  spec[key] = { cx = d[1], cy = d[2], r = d[3], fps = r.fps }
  local path = overlay(slateStyle == 1 and ("Quadrante" .. math.floor(r.fps + 0.5)) or "Orologio", spec)
  local clip = path and importImage(path)
  if clip then
    describe(placeStill(clip, slateSpan[1], slateSpan[2], videoTrack(GFX_TRACK)),
      (slateStyle == 1 and "Quadrante" or "Orologio") .. " della slate " .. w .. "x" .. h, GFX_TRACK)
  end
end
end)

stage("Titolo in PNG", function()
if slateSec > 0 then
  local clip, path = userImage("TitleImage", "LeaderKit Titolo", "Titolo in PNG")
  if clip then
    local box = (LK_TITLE_BOXES or {})[slateStyle + 1] or { 0.5, 0.8, 0.6, 0.12, "center" }
    local k = (get("TitleImageSize", 100) or 100) / 100
    local z, pan, tilt = fitBox(clip, path, box[3] * w * k, box[4] * h * k, box[1] * w, box[2] * h, box[5])
    placeImage(clip, slateSpan, videoTrack(LOGO_TRACK .. " Titolo"), "Titolo in PNG sulla slate", z, pan, tilt)
  end
end
end)

local LOGOS = { { "Logo", "LogoPos", "LogoSize", LOGO_TRACK, "Logo" },
  { "Logo2", "LogoPos2", "LogoSize2", LOGO_TRACK .. " 2", "Secondo logo" } }
local logosPlaced = 0
for _, L in ipairs(LOGOS) do
 stage(L[5], function()
  local clip, path = userImage(L[1], L[4], L[5])
  if clip then
    local size = (get(L[3], 12) or 12) / 100
    local pos = math.floor(get(L[2], L[1] == "Logo" and 0 or 1) + 0.5)
    -- riquadro del logo: largo size * W, alto al massimo meta'; angolo esatto a 3.5% / 4% dai bordi
    local z, _, _, dw, dh = fitBox(clip, path, size * w, size * w * 0.5, 0, 0, "center")
    local mx, my = w / 2 - 0.035 * w - dw / 2, h / 2 - 0.04 * h - dh / 2
    local pan, tilt = ({ mx, -mx, mx, -mx, 0 })[pos + 1], ({ my, my, -my, -my, 0 })[pos + 1]
    local track = videoTrack(L[4])
    local spans = {}
    if slateSec > 0 then spans[#spans + 1] = { slateSpan[1], slateSpan[2], "slate" } end
    if get("LogoOnTail", 0) > 0.5 and lfoa and tailOn then spans[#spans + 1] = { lfoa + 1, tailLen, "coda" } end
    if #spans == 0 then bad(L[5] .. ": lo standard non ha slate; attiva 'Anche sulla coda' per vederlo.") end
    for _, sp in ipairs(spans) do
      placeImage(clip, sp, track, L[5] .. " sulla " .. sp[3], z, pan, tilt)
      logosPlaced = logosPlaced + 1
    end
    -- piccolo logo della produzione nel countdown, a sinistra dei dati del progetto
    if L[1] == "Logo" and countFrom > 0 and get("CdLogo", 1) > 0.5 then
      local cz, _, _, cdw = fitBox(clip, path, 0.07 * w, math.min(cdCap * 4.2 * h * 0.9, 0.07 * h), 0, 0, "center")
      local cx = 0.5 * w - 0.16 * w - cdw / 2
      placeImage(clip, { ffoa - countFrom * n, (countFrom - 2) * n + 1 }, track, "Logo nel countdown",
        cz, cx - w / 2, cdY * h - h / 2)
      logosPlaced = logosPlaced + 1
    end
  end
 end)
end
if logosPlaced == 0 then
  ok("Logo: nessuno (scegli il file in Aspetto › Logo, oppure metti l'immagine nel bin 'LeaderKit Logo' del Media Pool).")
end

-- ---------------------------------------------------------------- 5c) burn-in delle copie di lavoro
if FULL then stage("Burn-in", function()
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
end) end

-- ---------------------------------------------------------------- 5d) cache Fusion
-- La grafica dei generatori (slate con molti testi, countdown) si calcola una volta e poi
-- si riproduce dalla cache: come "Render Cache Fusion Output > On" nel menu del clip.
do
  local cacheOn = 1
  pcall(function() if resolve.CACHE_ENABLED ~= nil then cacheOn = resolve.CACHE_ENABLED end end)
  local done, failed = 0, 0
  for _, e in ipairs(allItems("video")) do
    local nm = e.item:GetName() or ""
    if e.item == head or nm == TAIL_NAME or isHeadItem(e.item) then
      local okc, res = pcall(function() return e.item:SetFusionOutputCache(cacheOn) end)
      if okc and res ~= false then done = done + 1 else failed = failed + 1 end
    end
  end
  if done > 0 then
    ok("Cache Fusion attivata su " .. done .. " clip LeaderKit: la riproduzione e' fluida dopo il primo passaggio " ..
      "(serve Playback › Render Cache su Smart o User).")
  elseif failed > 0 then
    bad("Non riesco ad attivare la cache Fusion: fai clic destro sui clip LeaderKit › Render Cache Fusion Output › On.")
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
setHead("FfoaTc", framesToTc(ffoa, r))

-- ---------------------------------------------------------------- 7) slate come immagine fissa
-- La slate e' testo fermo: Resolve la esporta una volta alla risoluzione della timeline (con titolo,
-- loghi e quadranti gia' sopra) e l'immagine va sulla traccia "LeaderKit Slate". Nel blocco la slate
-- non si calcola piu' (SlateBaked). Se c'e' un orologio che scatta ogni secondo, un'immagine per secondo.
stage("Slate come immagine fissa", function()
  if slateSec <= 0 then return end
  if get("SlateBake", 1) < 0.5 then
    ok("Slate in tempo reale (Aspetto › Slate come immagine fissa e' spenta).")
    return
  end
  if slateStyle == 1 then
    ok("Slate stile Quadrante: resta in tempo reale (la tacca si muove a ogni fotogramma).")
    return
  end
  local span0, spanLen = slateSpan[1], slateSpan[2]
  local perSecond = (P.clock and true or false) or slateStyle == 2
  -- pezzi: interi, oppure un pezzo per ogni secondo del conto alla rovescia (cambia quando (FFOA - f) % n == 0)
  local pieces = {}
  local startP = span0
  if perSecond then
    for f = span0 + 1, span0 + spanLen - 1 do
      if (ffoa - f) % n == 0 then pieces[#pieces + 1] = { startP, f - startP }; startP = f end
    end
  end
  pieces[#pieces + 1] = { startP, span0 + spanLen - startP }
  local playhead = tl:GetCurrentTimecode()
  local page = nil
  pcall(function() page = resolve:GetCurrentPage() end)
  local stamp = tostring(os.time())
  local files, why = {}, nil
  local function exportAt(frame, path)
    tl:SetCurrentTimecode(framesToTc(frame, r))
    local okx, res = pcall(function() return project:ExportCurrentFrameAsStill(path) end)
    if not okx then return false, "ExportCurrentFrameAsStill non disponibile (" .. tostring(res) .. ")" end
    local fh = io.open(path, "rb")
    if not fh then return false, "l'esportazione non ha creato il file" end
    fh:close()
    return true
  end
  local switched = false
  for i, pc in ipairs(pieces) do
    local letters = string.rep("a", math.floor((i - 1) / 26)) .. string.char(97 + (i - 1) % 26)
    local path = cacheDir .. sep .. "LeaderKit_Slate_" .. stamp .. "_" .. letters .. ".png"
    local frame = pc[1] + math.floor((pc[2] - 1) / 2)
    local okE, err = exportAt(frame, path)
    if not okE and i == 1 and not switched and page and page ~= "color" then
      -- alcune versioni esportano solo dalla pagina Color
      if pcall(function() resolve:OpenPage("color") end) then
        switched = true
        okE, err = exportAt(frame, path)
      end
    end
    if not okE then why = err; break end
    local pw, ph = pngSize(path)
    if pw and (pw ~= w or ph ~= h) then
      why = string.format("l'immagine esportata e' %dx%d invece di %dx%d", pw, ph, w, h); break
    end
    files[#files + 1] = { path, pc }
  end
  if switched and page then pcall(function() resolve:OpenPage(page) end) end
  if playhead then pcall(function() tl:SetCurrentTimecode(playhead) end) end
  if why or #files == 0 then
    bad("Slate in tempo reale: non sono riuscito a esportarla come immagine (" .. tostring(why) .. ").")
    return
  end
  local track = videoTrack(SLATE_TRACK)
  local placed = 0
  for _, fp in ipairs(files) do
    local clip = importImage(fp[1])
    if not clip then bad("Slate: Resolve non ha importato " .. fp[1] .. "."); return end
    local its, full = placeStill(clip, fp[2][1], fp[2][2], track)
    if not full then
      for _, it in ipairs(its) do pcall(function() tl:DeleteClips({ it }, false) end) end
      bad("Slate: immagine non posizionata sulla traccia '" .. SLATE_TRACK .. "': resta in tempo reale.")
      return
    end
    placed = placed + 1
  end
  -- titolo, loghi e quadranti sono gia' dentro l'immagine: si tolgono dalla durata della slate
  local extra = {}
  for _, e in ipairs(allItems("video")) do
    local tn = tl:GetTrackName("video", e.track)
    local st = e.item:GetStart()
    if tn ~= SLATE_TRACK and imageTrack(tn) and st >= span0 and st < span0 + spanLen then extra[#extra + 1] = e.item end
  end
  if #extra > 0 then pcall(function() tl:DeleteClips(extra, false) end) end
  setHead("SlateBaked", 1)
  ok(string.format("Slate esportata come immagine fissa %dx%d (%d %s) sulla traccia '%s': si riproduce senza calcoli. " ..
    "Se cambi testi, stile o loghi premi 'Aggiorna solo le immagini'.", w, h, placed,
    placed == 1 and "immagine" or "immagini, una per secondo", SLATE_TRACK))
end)

log(string.format("Timeline %s — %s fps%s, %sx%s", tl:GetName(), rateLabel, r.df and " DF" or "", W, H))
log(guide)
do
  local fls = {}
  for _, fl in ipairs(frameLines or {}) do fls[#fls + 1] = fl.label end
  local function q(k) local v = get(k, ""); v = tostring(v or ""); return v == "" and "(vuoto)" or v end
  log("\nPARAMETRI USATI")
  log("Frame lines: " .. (#fls > 0 and table.concat(fls, "  ") or "nessuna") ..
    (guidesOn and "" or " (frame lines spente)") .. "   ·   Taratura: " .. (get("CalOn", 1) > 0.5 and "si" or "no"))
  log("Logo: " .. q("Logo") .. "   ·   Secondo logo: " .. q("Logo2") .. "   ·   Titolo PNG: " .. q("TitleImage"))
  log("Stile slate: " .. tostring(math.floor(get("SlateStyle", 0) + 0.5) + 1) .. "   ·   Dati progetto nel countdown: " ..
    (get("CdInfo", 1) > 0.5 and "si" or "no"))
end
if P.unverified then
  checks[#checks + 1] = "⚠ Standard senza specifica pubblica: i valori sono un riferimento, verificali con il capitolato del committente."
end
report[#report + 1] = "\nCONTROLLI\n" .. table.concat(checks, "\n")
if P.notes and #P.notes > 0 then report[#report + 1] = "\nNOTE DELLO STANDARD\n- " .. table.concat(P.notes, "\n- ") end
warnings = {}   -- gia' elencati nei controlli
show(FULL and "LeaderKit — Genera" or "LeaderKit — Aggiorna immagini")
