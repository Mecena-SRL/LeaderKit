-- LeaderKit image: logo e titolo in PNG dentro i generatori (nodi Loader).
-- sync() legge il percorso dal pannello (nodo LK, cercato per nome), carica il file nel
-- Loader e salva le dimensioni in pixel negli input nascosti usati dalle espressioni
-- (grandezza e posizione). pick() apre il selettore di Fusion, scrive il campo, chiama
-- sync() e mostra sempre l'esito.
-- Funziona sia in LuaJIT (Fusion) sia in Lua 5.4 (test).

LK_IMAGE = (function()
  local M = {}

  function M.clean(p)
    p = tostring(p or "")
    p = string.gsub(p, "^%s+", ""); p = string.gsub(p, "%s+$", "")
    p = string.gsub(p, "^[\"']", ""); p = string.gsub(p, "[\"']$", "")
    p = string.gsub(p, "^file://", "")
    return p
  end

  local function be(s, i, n)
    local v = 0
    for k = i, i + n - 1 do v = v * 256 + string.byte(s, k) end
    return v
  end

  -- dimensioni di PNG e JPEG leggendo solo l'intestazione; nil per altri formati
  function M.size(path)
    local f = io.open(path, "rb")
    if not f then return nil end
    local head = f:read(32) or ""
    if #head >= 24 and head:sub(1, 8) == "\137PNG\r\n\26\n" then
      f:close()
      return be(head, 17, 4), be(head, 21, 4)
    end
    if #head >= 4 and head:byte(1) == 255 and head:byte(2) == 216 then
      f:seek("set", 2)
      for _ = 1, 10000 do
        local m = f:read(4)
        if not m or #m < 4 or m:byte(1) ~= 255 then break end
        local kind, len = m:byte(2), be(m, 3, 2)
        if kind >= 192 and kind <= 207 and kind ~= 196 and kind ~= 200 and kind ~= 204 then
          local d = f:read(5)
          f:close()
          if not d or #d < 5 then return nil end
          return be(d, 4, 2), be(d, 2, 2)
        end
        if len < 2 then break end
        f:seek("cur", len - 2)
      end
    end
    f:close()
    return nil
  end

  local function set(t, k, v) pcall(function() t:SetInput(k, v) end) end

  -- Il pannello e' il nodo "LK" della composizione: nel contesto di un bottone o di un cambio
  -- di campo "tool" puo' essere un altro nodo (per esempio il gruppo), quindi si cerca per nome.
  function M.panel(c, tool)
    local lk = nil
    pcall(function() lk = c:FindTool("LK") end)
    return lk or tool
  end

  local function readText(lk, key)
    local v = ""
    pcall(function() v = lk:GetInput(key) end)
    return M.clean(v)
  end

  -- scrive il percorso nel campo e controlla che ci sia davvero
  function M.write(lk, key, p)
    set(lk, key, p)
    if readText(lk, key) ~= p then pcall(function() lk[key] = p end) end
    if readText(lk, key) ~= p then pcall(function() lk[key][fu.TIME_UNDEFINED] = p end) end
    return readText(lk, key) == p
  end

  -- stato: "empty" (campo vuoto), "missing" (file assente), "unknown" (formato non leggibile), "ok".
  -- 'path' (facoltativo) evita di rileggere il campo appena scritto.
  function M.sync(c, tool, key, ldName, wKey, hKey, path)
    local lk = M.panel(c, tool)
    path = path and M.clean(path) or readText(lk, key)
    if path == "" then set(lk, wKey, 0); set(lk, hKey, 0); return "empty", path end
    local f = io.open(path, "rb")
    if not f then set(lk, wKey, 0); set(lk, hKey, 0); return "missing", path end
    f:close()
    local w, h = M.size(path)
    local ld = nil
    pcall(function() ld = c:FindTool(ldName) end)
    if ld then
      pcall(function() c:Lock() end)
      local done = pcall(function() ld.Clip[fu.TIME_UNDEFINED] = path end)
      if not done then done = pcall(function() ld.Clip = path end) end
      if not done then pcall(function() ld:SetInput("Clip", path) end) end
      -- immagine fissa: tenuta per tutta la durata del clip
      pcall(function() ld:SetInput("Loop", 1) end)
      pcall(function() ld:SetInput("HoldFirstFrame", 1000000) end)
      pcall(function() ld:SetInput("HoldLastFrame", 1000000) end)
      pcall(function() c:Unlock() end)
      if not w then
        pcall(function()
          local a = ld:GetAttrs() or {}
          local cw, ch = a.TOOLIT_Clip_Width, a.TOOLIT_Clip_Height
          if type(cw) == "table" then cw = cw[1] end
          if type(ch) == "table" then ch = ch[1] end
          if tonumber(cw) and tonumber(ch) then w, h = tonumber(cw), tonumber(ch) end
        end)
      end
    end
    if not w or not h or w <= 0 or h <= 0 then set(lk, wKey, 0); set(lk, hKey, 0); return "unknown", path end
    set(lk, wKey, w); set(lk, hKey, h)
    return "ok", path, w, h
  end

  function M.message(label, st, path, w, h)
    if st == "ok" then return string.format("%s caricato: %s (%dx%d px).", label, path, w, h) end
    if st == "missing" then return label .. " non trovato: " .. path .. " (sceglilo di nuovo con \"Scegli...\")." end
    if st == "unknown" then return label .. ": formato non leggibile (" .. path .. "). Usa un PNG (con trasparenza) o un JPG." end
    return label .. ": nessun file."
  end

  -- "Scegli...": selettore di Fusion, poi campo, Loader e dimensioni; l'esito si vede sempre
  function M.pick(c, tool, key, ldName, wKey, hKey, label)
    local lk = M.panel(c, tool)
    local cur = readText(lk, key)
    local okd, res = pcall(function()
      return c:AskUser("LeaderKit - " .. label, { { "File", "FileBrowse", Save = false, Default = cur } })
    end)
    if not okd or type(res) ~= "table" then return nil end
    local p = M.clean(res.File or res[1] or "")
    if p == "" then return nil end
    pcall(function() local m = c:MapPath(p); if type(m) == "string" and m ~= "" then p = M.clean(m) end end)
    local written = M.write(lk, key, p)
    local st, path, w, h = M.sync(c, lk, key, ldName, wKey, hKey, p)
    local msg = M.message(label, st, path, w, h)
    if not written then
      msg = msg .. "\n\nIl campo non si e' aggiornato: incolla il percorso a mano nel campo \"" .. label .. " (file)\"."
    end
    pcall(function()
      c:AskUser("LeaderKit - " .. label, { { "Esito", "Text", Default = msg, Lines = 5, Wrap = true } })
    end)
    return st, written
  end

  return M
end)()
