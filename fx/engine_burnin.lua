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
-- metadati in cache per media pool item: lo stesso clip compare in molti segmenti
local metaCache = setmetatable({}, { __mode = "k" })
function BURN.meta(mpi, keys)
  if not mpi then return "" end
  local mc = metaCache[mpi]
  if not mc then mc = {}; metaCache[mpi] = mc end
  for _, k in ipairs(keys) do
    local v = mc[k]
    if v == nil then
      v = ""
      for _, fn in ipairs({ "GetMetadata", "GetClipProperty" }) do
        local okk, x = pcall(function() return mpi[fn](mpi, k) end)
        if okk and type(x) ~= "table" and x ~= nil and clean(x) ~= "" then v = clean(x); break end
      end
      mc[k] = v
    end
    if v ~= "" then return v end
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
-- formato audio: layout della traccia della timeline (mono, stereo, LCR, quad, 5.1, 7.1, "film", adaptive)
-- oppure, se l'API non lo da', il numero di canali del clip; piu' il codec se e' Dolby / DTS
local AUDIO_LAYOUT = { mono = "MONO", stereo = "STEREO", lrc = "LCR", lcr = "LCR", lrcs = "LCRS", lcrs = "LCRS",
  quad = "QUAD", ["5.0"] = "5.0", ["5.0film"] = "5.0 FILM", ["5.1"] = "5.1", ["5.1film"] = "5.1 FILM",
  ["7.0"] = "7.0", ["7.0film"] = "7.0 FILM", ["7.1"] = "7.1", ["7.1film"] = "7.1 FILM" }
local AUDIO_BY_CH = { [1] = "MONO", [2] = "STEREO", [3] = "LCR", [4] = "QUAD", [5] = "5.0", [6] = "5.1", [7] = "7.0",
  [8] = "7.1" }
function BURN.audioFormat(tlh, x)
  local mpi = BURN.mpi(x.item)
  local n = tonumber(string.match(BURN.meta(mpi, { "Audio Ch", "Channels" }), "%d+") or "")
  local sub = ""
  local okk, v = pcall(function() return tlh:GetTrackSubType("audio", x.track) end)
  if okk and type(v) == "string" then sub = string.lower(v) end
  local lab = AUDIO_LAYOUT[sub]
  if not lab and string.sub(sub, 1, 8) == "adaptive" then lab = "ADAPTIVE" .. (n and (" " .. n .. "CH") or "") end
  if not lab and n then lab = AUDIO_BY_CH[n] or (n .. "CH") end
  local codec = string.lower(BURN.meta(mpi, { "Audio Codec", "Format" }))
  local tag = ""
  if string.find(codec, "atmos", 1, true) or string.find(codec, "iab", 1, true) then tag = "ATMOS"
  elseif string.find(codec, "e-ac", 1, true) or string.find(codec, "eac", 1, true) or string.find(codec, "ec-3", 1, true)
    or string.find(codec, "dd+", 1, true) then tag = "DD+"
  elseif string.find(codec, "ac-3", 1, true) or string.find(codec, "ac3", 1, true) or string.find(codec, "dolby", 1, true) then tag = "DD"
  elseif string.find(codec, "dts", 1, true) then tag = "DTS" end
  return joinb({ lab or "", tag }, " ")
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
  -- canali letti: V1-V8 / A1-A8 spuntati nel pannello (di default tutti; sopra l'8 vale "tutti spuntati")
  local function chOn(k)
    local okk, v = pcall(function() return lkb:GetInput(k) end)
    if not okk or v == nil then return true end
    return v > 0.5
  end
  local function chan(prefix, t)
    if t <= 8 then return chOn(prefix .. t) end
    for i = 1, 8 do if not chOn(prefix .. i) then return false end end
    return true
  end
  local listCh = on("BChList")
  local vids, auds = {}, {}
  for _, x in ipairs(users("video")) do if chan("BV", x.track) then vids[#vids + 1] = x end end
  for _, x in ipairs(users("audio")) do if chan("BA", x.track) then auds[#auds + 1] = x end end
  local cuts = { [rs] = true, [re_] = true }
  local function cutAt(x)
    if x.st > rs and x.st < re_ then cuts[x.st] = true end
    if x.en > rs and x.en < re_ then cuts[x.en] = true end
  end
  for _, v in ipairs(vids) do cutAt(v) end
  if listCh or on("BAtc") then for _, x in ipairs(auds) do cutAt(x) end end
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
  -- lunghezze massime (in caratteri) di ogni blocco su tutto il programma: il generatore ne ricava
  -- la grandezza del testo e l'impaginazione senza rileggere i dati a ogni fotogramma
  local lens = { {0, 0, 0, 0, 0}, {0, 0, 0, 0, 0}, {0, 0, 0, 0, 0}, {0, 0, 0, 0, 0}, {0, 0, 0, 0, 0} }
  local chLen, chRows = 0, 0              -- elenco dei canali: riga piu' lunga e numero massimo di righe
  local function ulen(x)
    x = string.gsub(string.gsub(string.gsub(x, "{[RSA][ERT][CC]}", "00:00:00:00"), "{FRM}", "0000000"),
      "{X[^}]*}", "00:00:00:00")
    local _, nch = string.gsub(x, "[^\128-\191]", "")
    return nch
  end
  local function measure(k, p1, p2)
    local L = lens[k]
    local a, b = ulen(p1), ulen(p2)
    L[1] = math.max(L[1], a, b)
    L[2] = math.max(L[2], a + b + ((a > 0 and b > 0) and 5 or 0))
    local nst = 0
    for q in string.gmatch(p1 .. "  ·  " .. p2 .. "  ·  ", "(.-)  ·  ") do
      if q ~= "" then nst = nst + 1; L[3] = math.max(L[3], ulen(q)) end
    end
    L[4] = math.max(L[4], (a > 0 and 1 or 0) + (b > 0 and 1 or 0))
    L[5] = math.max(L[5], nst)
  end
  local wantName, wantSrc, chFmt = chOn("BChName"), chOn("BChSrc"), chOn("BChFmt")
  -- una riga dell'elenco: "V2  A001C003  SRC {X...}" (il TC corre da solo, come {SRC})
  local function chanLine(label, x, a, isVideo)
    local cmpi = BURN.mpi(x.item)
    local parts = { label }
    if wantName then
      local nm = BURN.meta(cmpi, { "File Name", "Clip Name" })
      if nm == "" then nm = clean(x.item:GetName()) end
      parts[#parts + 1] = (string.gsub(nm, "%.[%w]+$", ""))
    end
    if wantSrc then
      local sv, step, sn, sd = -1, 1, r.nominal, r.drop
      local stc = BURN.meta(cmpi, { "Start TC" })
      if isVideo then
        local cfps = tonumber(string.match(BURN.meta(cmpi, { "FPS" }), "[%d%.]+") or "") or r.fps
        local cr = makeRate(tostring(cfps), string.find(stc, ";", 1, true) and "1" or "0")
        sn, sd, step = cr.nominal, cr.drop, cfps / r.fps
        if string.match(stc, "%d+[:;]%d+[:;]%d+[:;.]%d+") then
          sv = tcToFrames(stc, cr) + BURN.srcStart(x.item) + (a - x.st) * step
        end
      elseif string.match(stc, "%d+[:;]%d+[:;]%d+[:;.]%d+") then
        sv = tcToFrames(stc, r) + BURN.srcStart(x.item) + (a - x.st)
      end
      parts[#parts + 1] = string.format("SRC {X%.4f,%.6f,%d,%d}", sv, step, sn, sd)
    end
    if not isVideo and chFmt then
      local af = BURN.audioFormat(tl, x)
      if af ~= "" then table.insert(parts, 2 + (wantName and 1 or 0), af) end
    end
    return table.concat(parts, "  ")
  end
  local function chanList(a)
    local out = {}
    local function pick(set, desc, label, isVideo)
      local at = {}
      for _, x in ipairs(set) do if x.st <= a and x.en > a then at[#at + 1] = x end end
      table.sort(at, function(p, q) if desc then return p.track > q.track end return p.track < q.track end)
      for _, x in ipairs(at) do out[#out + 1] = chanLine(label .. x.track, x, a, isVideo) end
    end
    pick(vids, true, "V", true)
    pick(auds, false, "A", false)
    return out
  end

  for i = 1, #points - 1 do
    local a, b = points[i], points[i + 1]
    local v = nil
    for _, x in ipairs(vids) do
      if x.st <= a and x.en > a and (not v or x.track > v.track) then v = x end
    end
    local srcv, step, sn, sd, fr0 = -1, 1, r.nominal, r.drop, a - rs
    -- impaginazione (convenzioni dailies / review: dati fuori dall'immagine attiva, etichette
    -- esplicite SRC TC / REC TC, source a sinistra e record a destra come in Avid):
    --   alto sx  nome file del clip / reel · camera     alto centro  titolo · versione / data
    --   alto dx  scena / take / formato · colore        basso sx     SRC TC / AUD TC + sound roll
    --   basso dx REC TC / contatore fotogrammi          (TC grande in basso al centro)
    local tl1, tl2, tr1, tr2, bl1, bl2, tc1, tc2 = "", "", "", "", "", "", "", ""
    local date = ""
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
      if on("BClip") then
        -- nome del file di camera, senza estensione (si ritrova nel media pool e nei report)
        local fname = BURN.meta(mpi, { "File Name", "Clip Name" })
        if fname == "" then fname = clean(v.item:GetName()) end
        tl1 = (string.gsub(fname, "%.[%w]+$", ""))
      end
      local sc = BURN.meta(mpi, { "Scene" })
      local shot = BURN.meta(mpi, { "Shot" })
      local tk = BURN.meta(mpi, { "Take" })
      local good = BURN.meta(mpi, { "Good Take", "Circled" })
      local scene = joinb({ sc ~= "" and ("SC " .. sc .. (shot ~= "" and ("/" .. shot) or "")) or "",
        tk ~= "" and ("TK " .. tk) or "", (good == "1" or string.lower(good) == "true" or string.lower(good) == "yes") and "CIRCLED" or "" }, " ")
      local cam = BURN.meta(mpi, { "Camera #", "Camera", "Angle" })
      local reel = joinb({ BURN.meta(mpi, { "Reel Name", "Reel Number", "Reel" }), BURN.meta(mpi, { "Roll Card #", "Roll/Card" }) }, " / ")
      tl2 = joinb({ on("BReel") and reel or "", on("BCam") and cam ~= "" and ("CAM " .. cam) or "" }, "  ·  ")
      tr1 = on("BScene") and scene or ""
      if on("BDate") then date = BURN.meta(mpi, { "Shoot Day", "Date Recorded", "Date Created" }) end
    end
    if on("BDate") and date == "" then date = os.date("%d/%m/%Y") end
    tc1 = joinb({ on("BTitle") and string.upper(title) or "", on("BVersion") and version or "" }, "  ·  ")
    tc2 = date
    tr2 = joinb({ on("BFormat") and fmt or "", on("BColor") and color or "" }, "  ·  ")
    if on("BSrc") then bl1 = "SRC TC {SRC}" end
    local aud = -1
    local wantAtc, wantFmt = on("BAtc"), on("BAfmt")
    if wantAtc or wantFmt then
      local au = nil
      for _, x in ipairs(auds) do
        if x.st <= a and x.en > a and (not au or x.track < au.track) then au = x end
      end
      if au then
        local ampi = BURN.mpi(au.item)
        local p = {}
        if wantAtc then
          local atc = BURN.meta(ampi, { "Start TC" })
          if string.match(atc, "%d+[:;]%d+[:;]%d+[:;.]%d+") then
            aud = tcToFrames(atc, r) + BURN.srcStart(au.item) + (a - au.st)
          end
          local roll = BURN.meta(ampi, { "Sound Roll #", "Reel Name" })
          if roll == "" then roll = BURN.meta(mpi, { "Sound Roll #" }) end
          p[#p + 1] = "AUD TC {ATC}" .. (roll ~= "" and ("   " .. roll) or "")
        end
        if wantFmt then
          local af = BURN.audioFormat(tl, au)
          if af ~= "" then p[#p + 1] = (wantAtc and "" or "AUD ") .. af end
        end
        bl2 = joinb(p, "   ")
      else
        bl2 = wantAtc and "AUD TC --" or "AUD --"
      end
    end
    local br1, br2 = on("BRec") and "REC TC {REC}" or "", on("BFrame") and "FR {FRM}" or ""
    if tl1 == "" then tl1, tl2 = tl2, "" end
    if tc1 == "" then tc1, tc2 = tc2, "" end
    if tr1 == "" then tr1, tr2 = tr2, "" end
    if bl1 == "" then bl1, bl2 = bl2, "" end
    if br1 == "" then br1, br2 = br2, "" end
    measure(1, tl1, tl2); measure(2, tr1, tr2); measure(3, bl1, bl2); measure(4, br1, br2); measure(5, tc1, tc2)
    local chl = ""
    if listCh and (wantName or wantSrc or chFmt) then
      local cl = chanList(a)
      for _, q in ipairs(cl) do chLen = math.max(chLen, ulen(q)) end
      chRows = math.max(chRows, #cl)
      chl = table.concat(cl, "~")
    end
    lines[#lines + 1] = string.format("%d|%d|%s|%s|%d|%d|%d|%d|%s~%s|%s~%s|%s~%s|%s~%s~{REC}|%s~%s|%s",
      a, b, string.format("%.4f", srcv), string.format("%.6f", step), sn, sd, aud, fr0,
      tl1, tl2, tr1, tr2, bl1, bl2, br1, br2, tc1, tc2, chl)
  end
  -- indice a record fissi (inizio relativo al clip, posizione della riga in Seg): il generatore
  -- trova il segmento del fotogramma con una ricerca binaria, senza rileggere tutto Seg
  local idx, pos = {}, 1
  for i, l in ipairs(lines) do
    idx[i] = string.format("%010d%08d", math.max(0, points[i] - rs), pos)
    pos = pos + #l + 1
  end
  set(lkb, "Seg", table.concat(lines, "\n"))
  set(lkb, "SegIdx", table.concat(idx))
  local ls = {}
  for k = 1, 5 do ls[k] = table.concat(lens[k], ",") end
  set(lkb, "BLens", table.concat(ls, "|"))
  set(lkb, "BChLens", chLen .. "," .. chRows)
  set(lkb, "RecStart", rs)
  set(lkb, "TlFps", r.nominal)
  set(lkb, "TlDrop", r.drop)
  set(lkb, "TlW", tonumber(W) or 0)          -- risoluzione vera della timeline per mascherino e testi
  set(lkb, "TlH", tonumber(H) or 0)
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
