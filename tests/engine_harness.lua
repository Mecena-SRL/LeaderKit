-- Resolve simulato per fx/engine.lua. Argomenti key=value:
-- fps, df, preset, head (secondi), program (secondi), variant (1-4: quale variante
-- di AppendToTimeline produce 1 fotogramma), runs, usermarker, remove.
local enginePath = arg[1]
local opt = { fps = "24", df = "0", preset = "0", head = "5", progstart = "30", program = "60",
  variant = "1", runs = "1", usermarker = "0", remove = "0", marks = "abs_incl", beep = "0",
  dursel = "0", programtc = "00:00:30:00", removecode = "", logo = "", res = "1920x1080", stilldur = "0" }
for i = 2, #arg do local k, v = arg[i]:match("([^=]+)=(.*)"); opt[k] = v end
local fps = tonumber(opt.fps)
local nominal = math.floor(fps + 0.5)
local df = opt.df == "1"

-- Come Resolve: le liste restituite contengono anche un contatore numerico.
local function counted(t) local c = {}; for i, v in ipairs(t) do c[i] = v end; c.n = #t; return c end
-- timecode di verifica (indipendente dal motore)
local drop = df and (nominal == 30 and 2 or 4) or 0
local function tc(frames)
  local n = nominal
  if drop > 0 then
    local per10 = n * 600 - drop * 9
    local perMin = n * 60 - drop
    local d = frames // per10
    local m = frames % per10
    if m > drop then frames = frames + drop * 9 * d + drop * ((m - drop) // perMin)
    else frames = frames + drop * 9 * d end
  end
  local sep = drop > 0 and ";" or ":"
  return string.format("%02d:%02d:%02d%s%02d", frames // (n * 3600), (frames // (n * 60)) % 60,
    (frames // n) % 60, sep, frames % n)
end
local function tcf(s)
  local h, m, sec, f = s:match("(%d+)[:;](%d+)[:;](%d+)[:;](%d+)")
  h, m, sec, f = tonumber(h), tonumber(m), tonumber(sec), tonumber(f)
  local frames = ((h * 60 + m) * 60 + sec) * nominal + f
  if drop > 0 then local tm = h * 60 + m; frames = frames - drop * (tm - tm // 10) end
  return frames
end

-- oggetti
local Item = {}; Item.__index = Item
local tlStart = tcf("01:00:00:00")
function Item:GetStart() return tlStart + self.off end
function Item:GetDuration() return self.dur end
function Item:GetName() return self.name end
function Item:GetFusionCompByIndex() return self.comp end
function Item:SetProperty(k, v) self.props = self.props or {}; self.props[k] = v; return true end
function Item:GetMediaPoolItem() return self.mpi end
function Item:GetSourceStartFrame() return self.srcin or 0 end
function Item:GetTrackTypeAndIndex() return self.where end

local tracks = { video = { { name = "Video 1", items = {} } }, audio = { { name = "Audio 1", items = {} } } }
local markers = {}
local playhead = "01:00:00:00"
local function newTool() local t = { inputs = {} }
  function t:GetInput(k) return self.inputs[k] end
  function t:SetInput(k, v) self.inputs[k] = v end
  return t end
-- Loader simulati: il motore imposta Clip (come in Fusion, per assegnazione) e gli input di tenuta
local function newLoader(name)
  local ld = { name = name, inputs = {} }
  function ld:SetInput(k, v) self.inputs[k] = v end
  function ld:GetAttrs() return {} end
  return ld
end
local function newComp(tool) local c = { tool = tool, loaders = {} }
  function c:FindTool(n)
    if n == "LK" then return self.tool end
    if n:match("Ld$") then self.loaders[n] = self.loaders[n] or newLoader(n); return self.loaders[n] end
  end
  function c:GetToolList() return {} end
  function c:Lock() end
  function c:Unlock() end
  function c:AskUser(title, t) print("DIALOG " .. title .. "\n" .. tostring(t[1].Default)) end
  return c end

local headTool = newTool()
headTool.inputs = { Preset = tonumber(opt.preset), Reel = 1, Custom = 0, BarsSec = 0, CountFrom = 8, SlateSec = 8,
  GapSec = 2, TailSec = 8, MarkersOn = 1, MarkerKind = 0, MarkerEvery = 0, TailOn = 1,
  DurSel = tonumber(opt.dursel), ProgramTC = opt.programtc, Breaks = tonumber(opt.Breaks or "0"),
  SlotCinema = tonumber(opt.SlotCinema or "3"), SlotTV = tonumber(opt.SlotTV or "0"),
  SlotSpot = tonumber(opt.SlotSpot or "3"), SlotStream = tonumber(opt.SlotStream or "3"), DateAuto = 1,
  Title = "Il film", TextRed = 0.5, BeepEach = tonumber(opt.beep), PopLevel = 0,
  Logo = opt.logo, LogoPos = 0, LogoSize = 20, LogoOnTail = tonumber(opt.logotail or "1"), Logo2 = opt.logo2 or "",
  LogoPos2 = 1, LogoSize2 = 12, EndDot = tonumber(opt.enddot or "0"),
  SlateStyle = tonumber(opt.style or "0"), TitleImage = opt.titleimg or "", TitleImageSize = 100 }
local head = setmetatable({ off = 0, dur = tonumber(opt.head) * nominal, name = "LeaderKit Head",
  comp = newComp(headTool) }, Item)
table.insert(tracks.video[1].items, head)
local progDur = math.floor(tonumber(opt.program) * nominal)
local progOff = math.floor(tonumber(opt.progstart) * nominal)
if progDur > 0 then
  local md = { Scene = "12", Take = "3", ["Camera #"] = "A", ["Reel Name"] = "A001", ["Good Take"] = "1",
    ["Start TC"] = opt.srctc or "14:22:10:00", FPS = opt.srcfps or opt.fps }
  local mpi = { GetMetadata = function(_, k) return md[k] end, GetClipProperty = function(_, k) return md[k] end }
  local amd = { ["Start TC"] = opt.audtc or "14:22:10:00", ["Sound Roll #"] = "S012" }
  local ampi = { GetMetadata = function(_, k) return amd[k] end, GetClipProperty = function(_, k) return amd[k] end }
  table.insert(tracks.video[1].items, setmetatable({ off = progOff, dur = progDur, name = "A001C003.mov", mpi = mpi,
    srcin = 48 }, Item))
  table.insert(tracks.audio[1].items, setmetatable({ off = progOff, dur = progDur, name = "A001C003.mov", mpi = ampi,
    srcin = 48 }, Item))
end
if opt.usermarker == "1" then markers[5] = { name = "nota utente", customData = "" } end

local tl = {}
function tl:GetName() return "Timeline 1" end
function tl:GetSetting(k)
  if k == "timelineFrameRate" then return opt.fps end
  if k == "timelineDropFrameTimecode" then return opt.df end
  if k == "timelineResolutionWidth" then return opt.res:match("^(%d+)") end
  if k == "timelineResolutionHeight" then return opt.res:match("x(%d+)$") end
end
function tl:GetStartFrame() return tlStart end
function tl:GetStartTimecode() return tc(tlStart) end
function tl:SetStartTimecode(s) tlStart = tcf(s); print("RESULT starttc=" .. s); return true end
function tl:GetTrackCount(k) return #tracks[k] end
function tl:SetTrackLock(k, i, v) if opt.nolock == "1" then error("no lock api") end; tracks[k][i].locked = v; return true end
function tl:GetIsTrackLocked(k, i) return tracks[k][i].locked or false end
function tl:GetTrackName(k, i) return tracks[k][i].name end
function tl:SetTrackName(k, i, n) tracks[k][i].name = n; return true end
function tl:AddTrack(k) table.insert(tracks[k], { name = k .. " " .. (#tracks[k] + 1), items = {} }); return true end
function tl:GetItemListInTrack(k, i) return counted(tracks[k][i].items) end
function tl:DeleteClips(list)
  local dead = {}; for _, it in ipairs(list) do dead[it] = true end
  for _, k in ipairs({ "video", "audio" }) do for _, t in ipairs(tracks[k]) do
    local keep = {}; for _, it in ipairs(t.items) do if not dead[it] then keep[#keep + 1] = it end end
    t.items = keep end end
  return true
end
function tl:GetMarkers() local c = {}; for k, v in pairs(markers) do c[k] = v end; return c end
function tl:AddMarker(f, color, name, note, d, cd)
  if markers[f] then return false end
  markers[f] = { name = name, color = color, customData = cd, duration = d }; return true
end
function tl:DeleteMarkerAtFrame(f) local had = markers[f] ~= nil; markers[f] = nil; return had end
function tl:GetCurrentVideoItem() return head end
function head_of() return head end
function tl:GetCurrentTimecode() return playhead end
function tl:SetCurrentTimecode(s) playhead = s; return true end
local marks = nil
function tl:SetMarkInOut(i, o)
  if opt.marks == "none" then return false end
  marks = { i, o }; return true
end
function tl:ClearMarkInOut() marks = nil; return true end
function tl:InsertFusionGeneratorIntoTimeline(name)
  local t = newTool()
  t.inputs = { Preset = 0, Info = "", CountFrom = 8, SlateSec = 8, GapSec = 2, TailSec = 8, MarkersOn = 1,
    MarkerKind = 0, MarkerEvery = 20, TailOn = 1, Reel = 1 }
  local off, dur = tcf(playhead) - tlStart, 5 * nominal
  if marks then
    -- convenzione simulata: in/out assoluti con out incluso (abs_incl) o relativi (rel_incl)
    local base = (opt.marks == "rel_incl") and 0 or tlStart
    off = marks[1] - base + ((opt.marks == "rel_incl") and 0 or 0)
    dur = marks[2] - marks[1] + 1
    if opt.marks == "rel_incl" and marks[1] > 1000000 then off, dur = -1, 5 * nominal end
    if opt.marks == "abs_incl" and marks[1] < tlStart then off, dur = -1, 5 * nominal end
    if off < 0 then off = tcf(playhead) - tlStart end
  end
  if name == "LeaderKit Burn-in" then t.inputs = { BPhase = 2, BFrameMode = 1 } end
  local ti = 1
  while tracks.video[ti] and tracks.video[ti].locked do ti = ti + 1 end
  if not tracks.video[ti] then return nil end
  local it = setmetatable({ off = off, dur = dur, name = name, comp = newComp(t), where = { "video", ti } }, Item)
  table.insert(tracks.video[ti].items, it)
  if name == "LeaderKit Head" then head = it; comp = it.comp end
  return it
end

local wavClip = { GetName = function() return "LeaderKit_pop_1kHz_-20dBFS.wav" end }
local folder = { clips = {} }
function folder:GetName() return "LeaderKit" end
function folder:GetClipList() return counted(self.clips) end
local rootFolder = { GetSubFolderList = function() return counted({ folder }) end }
local pool = {}
function pool:GetRootFolder() return rootFolder end
function pool:AddSubFolder() return folder end
function pool:GetCurrentFolder() return folder end
function pool:SetCurrentFolder() return true end
function pool:ImportMedia(paths)
  local name = paths[1]:match("[^/\\]+$")
  local clip = { GetName = function() return name end, path = paths[1] }
  table.insert(folder.clips, clip)
  return counted({ clip })
end
-- variant 1: endFrame esclusivo; variant 2: endFrame incluso (piu' mediaType richiesto se opt.needtype)
function pool:AppendToTimeline(infos)
  local info = infos[1]
  local incl = tonumber(opt.variant) ~= 1
  local dur = info.endFrame - info.startFrame + (incl and 1 or 0)
  local kind = info.mediaType == 1 and "video" or "audio"
  if not info.mediaType and not info.mediaPoolItem:GetName():match("%.wav$") then kind = "video" end
  -- immagini fisse limitate alla durata standard (opzione stilldur, in fotogrammi)
  if kind == "video" and tonumber(opt.stilldur) > 0 then dur = math.min(dur, tonumber(opt.stilldur)) end
  local it = setmetatable({ off = info.recordFrame - tlStart, dur = dur, name = info.mediaPoolItem:GetName(),
    path = info.mediaPoolItem.path }, Item)
  table.insert(tracks[kind][info.trackIndex].items, it)
  return counted({ it })
end

local project = { GetCurrentTimeline = function() return tl end, GetMediaPool = function() return pool end,
  GetSetting = function(_, k)
    return ({ colorScienceMode = "davinciYRGBColorManagedv2", colorSpaceTimeline = "DaVinci WG/Intermediate",
      colorSpaceOutput = "Rec.709 Gamma 2.4" })[k]
  end }
local resolveObj = { GetProjectManager = function() return { GetCurrentProject = function() return project end } end }

-- globali attesi dal motore
fusion = { GetResolve = function() return resolveObj end, GetCurrentComp = function() return head.comp end }
comp = head.comp
tool = headTool
local HOME = os.tmpname(); os.remove(HOME); os.execute("mkdir -p " .. HOME)
bmd = { createdir = function(p) os.execute("mkdir -p '" .. p .. "'") end }
os.getenv = function(k) if k == "HOME" then return HOME end end

local source = io.open(enginePath):read("a")
local runs = tonumber(opt.runs)
for i = 1, runs do
  comp = head.comp; tool = head.comp.tool
  assert(load(source, "engine", "t", _ENV))()
end
if opt.burncode then
  for _, t in ipairs(tracks.video) do for _, it in ipairs(t.items) do
    if it.name == "LeaderKit Burn-in" then
      it.comp.tool.inputs.Seg = ""; it.comp.tool.inputs.BFrameMode = 0
      comp = it.comp; tool = it.comp.tool
    end
  end end
  assert(load(io.open(opt.burncode):read("a"), "engine", "t", _ENV))()
end
if opt.remove == "1" then
  comp = head.comp; tool = head.comp.tool
  assert(load(io.open(opt.removecode):read("a"), "engine", "t", _ENV))()
  local n = 0; for _ in pairs(markers) do n = n + 1 end
  print("RESULT after_remove_markers=" .. n)
end

for f, m in pairs(markers) do print("RESULT marker=" .. m.name .. "|" .. tc(tlStart + f) .. "|" .. tostring(m.duration or 1)) end
for _, t in ipairs(tracks.audio) do
  if t.name == "LeaderKit Pop" then
    table.sort(t.items, function(a, b) return a.off < b.off end)
    for _, it in ipairs(t.items) do print("RESULT pop=" .. tc(it:GetStart()) .. "|" .. it:GetDuration()) end
  end
end
for _, t in ipairs(tracks.video) do
  if t.name == "LeaderKit Grafica" then
    table.sort(t.items, function(a, b) return a.off < b.off end)
    for _, it in ipairs(t.items) do print("RESULT gfx=" .. tc(it:GetStart()) .. "|" .. it:GetDuration() .. "|" .. tostring(it.path)) end
  end
  if t.name == "LeaderKit Burn-in" then
    for _, it in ipairs(t.items) do
      local ti = it.comp.tool.inputs
      print("RESULT burn=" .. tc(it:GetStart()) .. "|" .. it:GetDuration() .. "|" .. tostring(ti.BFrameMode) .. "|" ..
        tostring(ti.BRec) .. tostring(ti.BSrc) .. tostring(ti.BAtc) .. "|" .. tostring(ti.RecStart) .. "|" .. tostring(ti.TlFps))
      print("RESULT burnseg=" .. (tostring(ti.Seg):gsub("\n", " // ")))
      print("RESULT burnidx=" .. tostring(ti.SegIdx))
      print("RESULT burnseglen=" .. tostring(#tostring(ti.Seg)))
    end
  end
  if t.name == "LeaderKit Logo" then
    for _, it in ipairs(t.items) do
      print("RESULT logo=" .. tc(it:GetStart()) .. "|" .. it:GetDuration() .. "|" .. tostring((it.props or {}).ZoomX))
    end
  end
end
for _, t in ipairs(tracks.video) do
  if t.name:sub(1, 9) == "LeaderKit" then
    for _, it in ipairs(t.items) do
      local pr = it.props or {}
      print(string.format("RESULT track=%s|%s|%d|%s|%s|%s|%s", t.name, tc(it:GetStart()), it:GetDuration(),
        tostring(pr.ZoomX), tostring(pr.Pan), tostring(pr.Tilt), tostring(it.path)))
    end
  end
end
for _, t in ipairs(tracks.video) do
  for _, it in ipairs(t.items) do
    if it.comp and it.comp.loaders then
      local names = {}
      for n in pairs(it.comp.loaders) do names[#names + 1] = n end
      table.sort(names)
      for _, n in ipairs(names) do
        local ld, ti = it.comp.loaders[n], it.comp.tool.inputs
        local pre = ({ Logo1Ld = "Logo", Logo2Ld = "Logo2", TitleLd = "Title" })[n]
        print(string.format("RESULT loader=%s|%s|%s|%s|%s|%s", it.name, n, tostring(ld.Clip), tostring(ti[pre .. "W"]),
          tostring(ti[pre .. "H"]), tostring(ld.inputs.HoldLastFrame)))
      end
    end
  end
end
for _, it in ipairs(tracks.video[1].items) do
  if it.name == "LeaderKit Tail" then
    local ti = it.comp.tool.inputs
    print("RESULT tail=start=" .. tc(it:GetStart()) .. " dur=" .. it:GetDuration() .. " pop=" .. tostring(ti.TailPop) ..
      " flash=" .. tostring(ti.TailFlash) .. " card=" .. tostring(ti.CardText) .. " info=" .. tostring(ti.Info))
  end
end
for _, it in ipairs(tracks.video[1].items) do
  if it.name == "LeaderKit Head" then
    print("RESULT head=" .. tc(it:GetStart()) .. "|" .. it:GetDuration() .. "|" .. tostring(it.comp.tool.inputs.Title))
    print("RESULT duration=" .. tostring(it.comp.tool.inputs.Duration))
    print("RESULT colorinfo=" .. tostring(it.comp.tool.inputs.ColorInfo))
    print("RESULT date=" .. tostring(it.comp.tool.inputs.Date))
    print("RESULT info=" .. tostring(it.comp.tool.inputs.Info):gsub("\n", " / "))
    print("RESULT guide=" .. tostring(it.comp.tool.inputs.Guide):gsub("\n", " / "))
  end
end
