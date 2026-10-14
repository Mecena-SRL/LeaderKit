-- LeaderKit overlay: immagini statiche (PNG RGBA) alla risoluzione esatta della timeline.
-- Taratura del countdown e quadranti delle slate sono disegnati pixel per pixel, salvati una
-- sola volta e caricati da Genera nei Loader del generatore (Fusion li tiene in cache per
-- tutto il clip). Frame lines, logo e dati del countdown sono nel generatore, sopra la taratura.
-- Funziona sia in LuaJIT (Fusion) sia in Lua 5.4 (test).

LK_OVERLAY = (function()
  local M = {}
  local floor, sqrt, max, min, abs = math.floor, math.sqrt, math.max, math.min, math.abs
  local atan2 = math.atan2 or math.atan
  local char, byte = string.char, string.byte
  local unpack = table.unpack or unpack

  -- ------------------------------------------------------------ CRC32 portabile
  local crc32
  do
    local bitlib = rawget(_G, "bit") or rawget(_G, "bit32")
    if not bitlib then pcall(function() bitlib = require("bit") end) end
    local src
    if bitlib then
      src = [[
        local bl, byte = ...
        local bxor, band, rshift = bl.bxor, bl.band, bl.rshift
        local T = {}
        for i = 0, 255 do
          local c = i
          for _ = 1, 8 do
            if band(c, 1) == 1 then c = bxor(0xEDB88320, rshift(c, 1)) else c = rshift(c, 1) end
          end
          T[i] = c
        end
        return function(crc, s)
          crc = bxor(crc, 0xFFFFFFFF)
          for i = 1, #s do crc = bxor(T[band(bxor(crc, byte(s, i)), 255)], rshift(crc, 8)) end
          crc = bxor(crc, 0xFFFFFFFF)
          if crc < 0 then crc = crc + 4294967296 end
          return crc
        end]]
    else
      src = [[
        local bl, byte = ...
        local T = {}
        for i = 0, 255 do
          local c = i
          for _ = 1, 8 do
            if c & 1 == 1 then c = 0xEDB88320 ~ (c >> 1) else c = c >> 1 end
          end
          T[i] = c
        end
        return function(crc, s)
          crc = crc ~ 0xFFFFFFFF
          for i = 1, #s do crc = T[(crc ~ byte(s, i)) & 255] ~ (crc >> 8) end
          return crc ~ 0xFFFFFFFF
        end]]
    end
    crc32 = assert(load(src, "crc32", "t", { math = math }))(bitlib, byte)
  end
  M.crc32 = crc32

  local function be32(v)
    return char(floor(v / 16777216) % 256, floor(v / 65536) % 256, floor(v / 256) % 256, v % 256)
  end

  -- ------------------------------------------------------------ PNG (zlib stored)
  local function pngWriter(path, W, H)
    local f = io.open(path, "wb")
    if not f then return nil end
    local function chunk(kind, data)
      f:write(be32(#data), kind, data, be32(crc32(0, kind .. data)))
    end
    f:write("\137PNG\r\n\26\n")
    chunk("IHDR", be32(W) .. be32(H) .. char(8, 6, 0, 0, 0))
    local w = { idat = {}, idatLen = 0, raw = {}, rawLen = 0, a = 1, b = 0 }
    w.idat[1] = char(0x78, 0x01); w.idatLen = 2
    local function flushIdat(force)
      if w.idatLen >= 1048576 or (force and w.idatLen > 0) then
        chunk("IDAT", table.concat(w.idat)); w.idat = {}; w.idatLen = 0
      end
    end
    local function block(data, final)
      local n = #data
      local nn = 65535 - n
      w.idat[#w.idat + 1] = char(final and 1 or 0, n % 256, floor(n / 256), nn % 256, floor(nn / 256))
      w.idat[#w.idat + 1] = data
      w.idatLen = w.idatLen + 5 + n
      flushIdat(false)
    end
    local function adler(s)
      local a, b = w.a, w.b
      local i, n = 1, #s
      while i <= n do
        local j = min(n, i + 3799)
        for k = i, j do a = a + byte(s, k); b = b + a end
        a = a % 65521; b = b % 65521
        i = j + 1
      end
      w.a, w.b = a, b
    end
    function w.row(s)
      adler(s)
      w.raw[#w.raw + 1] = s; w.rawLen = w.rawLen + #s
      if w.rawLen >= 65535 then
        local all = table.concat(w.raw)
        local i = 1
        while #all - i + 1 >= 65535 do block(all:sub(i, i + 65534), false); i = i + 65535 end
        w.raw = { all:sub(i) }; w.rawLen = #w.raw[1]
      end
    end
    function w.close()
      block(table.concat(w.raw), true)
      w.idat[#w.idat + 1] = be32(w.b * 65536 + w.a); w.idatLen = w.idatLen + 4
      flushIdat(true)
      chunk("IEND", "")
      f:close()
      return true
    end
    return w
  end

  -- ------------------------------------------------------------ raster a righe
  -- Ogni forma: { y0, y1, fn(y, row) }; la riga e' RGBA (0..255, alpha non premoltiplicato).
  local function blend(row, x, r, g, b, a)
    if a <= 0 then return end
    local i = x * 4 + 1
    local da = row[i + 3] / 255
    if a >= 1 or da <= 0 then
      row[i], row[i + 1], row[i + 2] = r, g, b
      row[i + 3] = (a >= 1) and 255 or floor(a * 255 + 0.5)
    else
      local k = da * (1 - a)
      local ao = a + k
      row[i] = floor((r * a + row[i] * k) / ao + 0.5)
      row[i + 1] = floor((g * a + row[i + 1] * k) / ao + 0.5)
      row[i + 2] = floor((b * a + row[i + 2] * k) / ao + 0.5)
      row[i + 3] = floor(ao * 255 + 0.5)
    end
  end

  local function c8(c) return { floor(c[1] * 255 + 0.5), floor(c[2] * 255 + 0.5), floor(c[3] * 255 + 0.5) } end

  local Canvas = {}
  Canvas.__index = Canvas
  local function canvas(W, H) return setmetatable({ W = W, H = H, shapes = {} }, Canvas) end

  function Canvas:add(y0, y1, fn)
    y0, y1 = max(0, floor(y0)), min(self.H - 1, floor(y1))
    if y1 >= y0 then self.shapes[#self.shapes + 1] = { y0, y1, fn } end
  end

  function Canvas:rect(x0, y0, x1, y1, c, a)
    x0, x1 = max(0, floor(x0 + 0.5)), min(self.W, floor(x1 + 0.5))
    y0, y1 = floor(y0 + 0.5), floor(y1 + 0.5)
    if x1 <= x0 or y1 <= y0 then return end
    local r, g, b = c[1], c[2], c[3]
    a = a or 1
    self:add(y0, y1 - 1, function(_, row) for x = x0, x1 - 1 do blend(row, x, r, g, b, a) end end)
  end

  function Canvas:frame(x0, y0, x1, y1, t, c)
    self:rect(x0, y0, x1, y0 + t, c); self:rect(x0, y1 - t, x1, y1, c)
    self:rect(x0, y0 + t, x0 + t, y1 - t, c); self:rect(x1 - t, y0 + t, x1, y1 - t, c)
  end

  -- rampa orizzontale continua da c0 a c1 (valori 0..255)
  function Canvas:ramp(x0, y0, x1, y1, c0, c1)
    x0, x1 = max(0, floor(x0 + 0.5)), min(self.W, floor(x1 + 0.5))
    local n = x1 - x0
    if n < 2 then return end
    local vals = {}
    for x = 0, n - 1 do
      local t = x / (n - 1)
      vals[x] = { floor(c0[1] + (c1[1] - c0[1]) * t + 0.5), floor(c0[2] + (c1[2] - c0[2]) * t + 0.5),
                  floor(c0[3] + (c1[3] - c0[3]) * t + 0.5) }
    end
    self:add(floor(y0 + 0.5), floor(y1 + 0.5) - 1, function(_, row)
      for x = 0, n - 1 do local v = vals[x]; blend(row, x0 + x, v[1], v[2], v[3], 1) end
    end)
  end

  -- griglia di righe alternate bianco/nero larghe p pixel (verticali o orizzontali), pixel-esatta
  function Canvas:grating(x0, y0, x1, y1, p, vertical, cw, cb)
    x0, x1 = max(0, floor(x0 + 0.5)), min(self.W, floor(x1 + 0.5))
    y0, y1 = floor(y0 + 0.5), floor(y1 + 0.5)
    if x1 <= x0 or y1 <= y0 then return end
    self:add(y0, y1 - 1, function(y, row)
      local hy = floor((y - y0) / p) % 2
      for x = x0, x1 - 1 do
        local on
        if vertical then on = floor((x - x0) / p) % 2 == 0 else on = hy == 0 end
        local c = on and cw or cb
        blend(row, x, c[1], c[2], c[3], 1)
      end
    end)
  end

  -- anello di spessore t
  function Canvas:ring(cx, cy, rad, t, c)
    local ro, ri = rad + t / 2, rad - t / 2
    local x0, x1 = max(0, floor(cx - ro - 1)), min(self.W - 1, floor(cx + ro + 1))
    self:add(cy - ro - 1, cy + ro + 1, function(y, row)
      local dy = y + 0.5 - cy
      for x = x0, x1 do
        local dx = x + 0.5 - cx
        local d = sqrt(dx * dx + dy * dy)
        local a = min(ro + 0.5 - d, d - ri + 0.5, 1)
        if a > 0 then blend(row, x, c[1], c[2], c[3], a) end
      end
    end)
  end

  -- sfera ombreggiata (gradiente continuo: rivela contouring e banding)
  function Canvas:sphere(cx, cy, rad)
    local lx, ly, lz = -0.45, -0.55, 0.70
    local ln = sqrt(lx * lx + ly * ly + lz * lz)
    lx, ly, lz = lx / ln, ly / ln, lz / ln
    local x0, x1 = max(0, floor(cx - rad - 1)), min(self.W - 1, floor(cx + rad + 1))
    self:add(cy - rad - 1, cy + rad + 1, function(y, row)
      local dy = (y + 0.5 - cy) / rad
      for x = x0, x1 do
        local dx = (x + 0.5 - cx) / rad
        local d2 = dx * dx + dy * dy
        local edge = (1 - sqrt(d2)) * rad + 0.5
        if edge > 0 then
          local nz = sqrt(max(0, 1 - d2))
          local l = max(0, dx * lx + dy * ly + nz * lz)
          local v = floor(255 * (0.04 + 0.96 * l ^ 1.4) + 0.5)
          blend(row, x, v, v, v, min(1, edge))
        end
      end
    end)
  end

  -- segmento spesso con estremi arrotondati (per il testo)
  function Canvas:segment(xa, ya, xb, yb, hw, c)
    local dx, dy = xb - xa, yb - ya
    local len2 = dx * dx + dy * dy
    local x0, x1 = max(0, floor(min(xa, xb) - hw - 1)), min(self.W - 1, floor(max(xa, xb) + hw + 1))
    self:add(min(ya, yb) - hw - 1, max(ya, yb) + hw + 1, function(y, row)
      local py = y + 0.5
      for x = x0, x1 do
        local px = x + 0.5
        local t = 0
        if len2 > 0 then t = max(0, min(1, ((px - xa) * dx + (py - ya) * dy) / len2)) end
        local ex, ey = px - (xa + t * dx), py - (ya + t * dy)
        local a = min(1, hw + 0.5 - sqrt(ex * ex + ey * ey))
        if a > 0 then blend(row, x, c[1], c[2], c[3], a) end
      end
    end)
  end

  -- ------------------------------------------------------------ font a tratti
  -- griglia 4 x 6 (y verso l'alto), polilinee
  local GLYPHS = {
    ["0"] = { { 1, 0, 3, 0, 4, 1, 4, 5, 3, 6, 1, 6, 0, 5, 0, 1, 1, 0 }, { 1, 1.5, 3, 4.5 } },
    ["1"] = { { 1, 5, 2, 6, 2, 0 }, { 1, 0, 3, 0 } },
    ["2"] = { { 0, 5, 1, 6, 3, 6, 4, 5, 4, 4, 0, 0, 4, 0 } },
    ["3"] = { { 0, 5, 1, 6, 3, 6, 4, 5, 4, 4, 3, 3, 4, 2, 4, 1, 3, 0, 1, 0, 0, 1 }, { 1.5, 3, 3, 3 } },
    ["4"] = { { 3, 0, 3, 6, 0, 2, 4, 2 } },
    ["5"] = { { 4, 6, 0, 6, 0, 3.5, 3, 3.5, 4, 2.5, 4, 1, 3, 0, 1, 0, 0, 1 } },
    ["6"] = { { 4, 5, 3, 6, 1, 6, 0, 5, 0, 1, 1, 0, 3, 0, 4, 1, 4, 2.5, 3, 3.5, 0, 3.5 } },
    ["7"] = { { 0, 6, 4, 6, 1.5, 0 } },
    ["8"] = { { 1, 3, 0, 4, 0, 5, 1, 6, 3, 6, 4, 5, 4, 4, 3, 3, 1, 3, 0, 2, 0, 1, 1, 0, 3, 0, 4, 1, 4, 2, 3, 3 } },
    ["9"] = { { 0, 1, 1, 0, 3, 0, 4, 1, 4, 5, 3, 6, 1, 6, 0, 5, 0, 3.5, 1, 2.5, 4, 2.5 } },
    A = { { 0, 0, 0, 4, 2, 6, 4, 4, 4, 0 }, { 0, 2.5, 4, 2.5 } },
    B = { { 0, 0, 0, 6, 3, 6, 4, 5, 4, 4, 3, 3, 0, 3 }, { 3, 3, 4, 2, 4, 1, 3, 0, 0, 0 } },
    C = { { 4, 5, 3, 6, 1, 6, 0, 5, 0, 1, 1, 0, 3, 0, 4, 1 } },
    D = { { 0, 0, 0, 6, 3, 6, 4, 5, 4, 1, 3, 0, 0, 0 } },
    E = { { 4, 6, 0, 6, 0, 0, 4, 0 }, { 0, 3, 3, 3 } },
    F = { { 4, 6, 0, 6, 0, 0 }, { 0, 3, 3, 3 } },
    G = { { 4, 5, 3, 6, 1, 6, 0, 5, 0, 1, 1, 0, 3, 0, 4, 1, 4, 3, 2, 3 } },
    H = { { 0, 0, 0, 6 }, { 4, 0, 4, 6 }, { 0, 3, 4, 3 } },
    I = { { 1, 6, 3, 6 }, { 2, 6, 2, 0 }, { 1, 0, 3, 0 } },
    J = { { 4, 6, 4, 1, 3, 0, 1, 0, 0, 1 } },
    K = { { 0, 0, 0, 6 }, { 4, 6, 0, 2 }, { 1.3, 3.3, 4, 0 } },
    L = { { 0, 6, 0, 0, 4, 0 } },
    M = { { 0, 0, 0, 6, 2, 3, 4, 6, 4, 0 } },
    N = { { 0, 0, 0, 6, 4, 0, 4, 6 } },
    O = { { 1, 0, 3, 0, 4, 1, 4, 5, 3, 6, 1, 6, 0, 5, 0, 1, 1, 0 } },
    P = { { 0, 0, 0, 6, 3, 6, 4, 5, 4, 4, 3, 3, 0, 3 } },
    Q = { { 1, 0, 3, 0, 4, 1, 4, 5, 3, 6, 1, 6, 0, 5, 0, 1, 1, 0 }, { 2.5, 1.5, 4, 0 } },
    R = { { 0, 0, 0, 6, 3, 6, 4, 5, 4, 4, 3, 3, 0, 3 }, { 2, 3, 4, 0 } },
    S = { { 4, 5, 3, 6, 1, 6, 0, 5, 0, 4, 1, 3, 3, 3, 4, 2, 4, 1, 3, 0, 1, 0, 0, 1 } },
    T = { { 0, 6, 4, 6 }, { 2, 6, 2, 0 } },
    U = { { 0, 6, 0, 1, 1, 0, 3, 0, 4, 1, 4, 6 } },
    V = { { 0, 6, 2, 0, 4, 6 } },
    W = { { 0, 6, 1, 0, 2, 4, 3, 0, 4, 6 } },
    X = { { 0, 0, 4, 6 }, { 0, 6, 4, 0 } },
    Y = { { 0, 6, 2, 3, 4, 6 }, { 2, 3, 2, 0 } },
    Z = { { 0, 6, 4, 6, 0, 0, 4, 0 } },
    [":"] = { { 2, 1, 2, 1 }, { 2, 4, 2, 4 } },
    ["."] = { { 2, 0, 2, 0 } },
    ["/"] = { { 0, 0, 4, 6 } },
    ["-"] = { { 1, 3, 3, 3 } },
    ["+"] = { { 1, 3, 3, 3 }, { 2, 2, 2, 4 } },
    ["%"] = { { 0, 0, 4, 6 }, { 0.6, 5.2, 0.6, 5.2 }, { 3.4, 0.8, 3.4, 0.8 } },
    ["x"] = { { 1, 0.5, 3, 3.5 }, { 1, 3.5, 3, 0.5 } },
    ["("] = { { 3, 6, 2, 5, 2, 1, 3, 0 } },
    [")"] = { { 1, 6, 2, 5, 2, 1, 1, 0 } },
    ["~"] = { { 0.4, 5.6, 1.3, 4.2, 2, 1.8 }, { 3.6, 5.6, 2, 1.8 }, { 2, 1.8, 1.4, 0.7, 2, 0, 2.6, 0.7, 2, 1.8 } },  -- gamma
  }
  M.GLYPHS = GLYPHS

  local function textWidth(s, gh) return max(0, #s * gh - gh / 3) end
  M.textWidth = textWidth

  -- testo: gh = altezza delle maiuscole in pixel; (x, y) = angolo in alto a sinistra
  function Canvas:text(s, x, y, gh, c, align)
    s = string.upper(s):gsub(" X ", " x ")
    local u = gh / 6
    local hw = max(0.6, u * 0.55)
    if align == "center" then x = x - textWidth(s, gh) / 2 elseif align == "right" then x = x - textWidth(s, gh) end
    for i = 1, #s do
      local ch = s:sub(i, i)
      local gl = GLYPHS[ch]
      if gl then
        for _, pl in ipairs(gl) do
          for k = 1, #pl - 2, 2 do
            self:segment(x + pl[k] * u, y + (6 - pl[k + 1]) * u, x + pl[k + 2] * u, y + (6 - pl[k + 3]) * u, hw, c)
          end
        end
      end
      x = x + gh
    end
  end

  function Canvas:write(path)
    local W, H = self.W, self.H
    local w = pngWriter(path, W, H)
    if not w then return false end
    local shapes = self.shapes      -- nell'ordine di disegno (livelli)
    local row = {}
    local n4 = W * 4
    local empty = nil
    for y = 0, H - 1 do
      local any = false
      for i = 1, #shapes do
        local s = shapes[i]
        if s[1] <= y and s[2] >= y then
          if not any then for k = 1, n4 do row[k] = 0 end; any = true end
          s[3](y, row)
        end
      end
      if any then
        local parts = { "\0" }
        for i = 1, n4, 4000 do parts[#parts + 1] = char(unpack(row, i, min(n4, i + 3999))) end
        w.row(table.concat(parts))
      else
        empty = empty or ("\0" .. string.rep("\0", n4))
        w.row(empty)
      end
    end
    return w.close()
  end

  -- area riempita pixel per pixel: fn(dx, dy, x, y) -> r, g, b (dx, dy relativi all'angolo in alto a sinistra)
  function Canvas:pattern(x0, y0, x1, y1, fn)
    x0, x1 = max(0, floor(x0 + 0.5)), min(self.W, floor(x1 + 0.5))
    y0, y1 = floor(y0 + 0.5), floor(y1 + 0.5)
    if x1 <= x0 or y1 <= y0 then return end
    self:add(y0, y1 - 1, function(y, row)
      for x = x0, x1 - 1 do
        local r, g, b = fn(x - x0, y - y0, x, y)
        blend(row, x, r, g, b, 1)
      end
    end)
  end

  -- L annidate di 1 px (quadrati concentrici attorno a un angolo) dentro il triangolo che ha
  -- l'angolo retto in quell'angolo: ogni L ha un tratto orizzontale e uno verticale di 1 px, alterni
  -- bianco / nero (media 50%). corner: "br" (in basso a destra) o "bl" (in basso a sinistra).
  function Canvas:nested(x0, y0, size, corner, cw, cb)
    x0, y0, size = floor(x0 + 0.5), floor(y0 + 0.5), floor(size + 0.5)
    local right = corner == "br"
    self:add(y0, y0 + size - 1, function(y, row)
      local dy = y0 + size - 1 - y                       -- distanza dal bordo basso
      for k = 0, size - 1 - dy do                        -- dentro il triangolo: dx + dy <= size - 1
        local x = right and (x0 + size - 1 - k) or (x0 + k)
        if x >= 0 and x < self.W then
          local c = (max(k, dy) % 2 == 0) and cw or cb
          blend(row, x, c[1], c[2], c[3], 1)
        end
      end
    end)
  end

  -- triangolo pieno con l'angolo retto in (xc, yc) e cateti lunghi L verso (sx, sy) = +-1
  function Canvas:corner(xc, yc, sx, sy, L, c)
    local y0, y1 = (sy > 0) and yc or (yc - L), (sy > 0) and (yc + L) or yc
    self:add(y0, y1 - 1, function(y, row)
      local d = (sy > 0) and (y + 0.5 - yc) or (yc - y - 0.5)
      local n = floor(L - d + 0.5)
      for k = 0, n - 1 do
        local x = (sx > 0) and (xc + k) or (xc - 1 - k)
        if x >= 0 and x < self.W then blend(row, x, c[1], c[2], c[3], 1) end
      end
    end)
  end

  -- corona circolare da r0 a r1 tra gli angoli a0 e a1 (gradi, in senso orario dalle ore 12); fn(frazione
  -- dell'angolo) -> colore. Bordi del raggio con antialiasing.
  function Canvas:annulus(cx, cy, r0, r1, a0, a1, fn)
    local x0, x1 = max(0, floor(cx - r1 - 1)), min(self.W - 1, floor(cx + r1 + 1))
    self:add(cy - r1 - 1, cy + r1 + 1, function(y, row)
      local dy = y + 0.5 - cy
      for x = x0, x1 do
        local dx = x + 0.5 - cx
        local d = sqrt(dx * dx + dy * dy)
        local a = min(r1 + 0.5 - d, d - r0 + 0.5, 1)
        if a > 0 then
          local ang = (math.deg(atan2(dx, -dy)) + 360) % 360
          if ang >= a0 and ang <= a1 then
            local c = fn((ang - a0) / (a1 - a0))
            if c then blend(row, x, c[1], c[2], c[3], a) end
          end
        end
      end
    end)
  end

  -- tessera rotonda: colora con 'bg' il riquadro fuori dal cerchio inscritto (con antialiasing)
  function Canvas:roundClip(x, y, s, bg)
    local cx, cy, r = x + s / 2, y + s / 2, s / 2
    self:add(y, y + s - 1, function(yy, row)
      local dy = yy + 0.5 - cy
      for xx = max(0, floor(x)), min(self.W - 1, floor(x + s - 1)) do
        local dx = xx + 0.5 - cx
        local a = min(1, sqrt(dx * dx + dy * dy) - r + 0.5)
        if a > 0 then
          local i = xx * 4 + 1
          if bg then blend(row, xx, bg[1], bg[2], bg[3], a)
          else row[i + 3] = floor(row[i + 3] * (1 - a) + 0.5) end
        end
      end
    end)
  end

  -- tessera con angoli arrotondati: fuori dal profilo trasparente, sul bordo un filo di 'lw' px in 'oc'
  function Canvas:roundRectClip(x, y, w, h, rad, oc, lw)
    local hx, hy, cx, cy = w / 2, h / 2, x + w / 2, y + h / 2
    self:add(y, y + h - 1, function(yy, row)
      local qy = abs(yy + 0.5 - cy) - (hy - rad)
      for xx = max(0, floor(x)), min(self.W - 1, floor(x + w - 1)) do
        local qx = abs(xx + 0.5 - cx) - (hx - rad)
        local d = sqrt(max(qx, 0) ^ 2 + max(qy, 0) ^ 2) + min(max(qx, qy), 0) - rad
        local i = xx * 4 + 1
        if oc and lw then
          local a = min(1, max(0, d + lw + 0.5)) - min(1, max(0, d + 0.5))
          if a > 0 then blend(row, xx, oc[1], oc[2], oc[3], a) end
        end
        local out = min(1, max(0, d + 0.5))
        if out > 0 then row[i + 3] = floor(row[i + 3] * (1 - out) + 0.5) end
      end
    end)
  end

  -- stella di Siemens con antialiasing analitico: verso il centro i settori si fondono in grigio
  function Canvas:siemens(cx, cy, rad, spokes, cw, cb)
    local x0, x1 = max(0, floor(cx - rad - 1)), min(self.W - 1, floor(cx + rad + 1))
    local k, sw = spokes / math.pi, math.pi / spokes
    self:add(cy - rad - 1, cy + rad + 1, function(y, row)
      local dy = y + 0.5 - cy
      for x = x0, x1 do
        local dx = x + 0.5 - cx
        local rr = sqrt(dx * dx + dy * dy)
        local a = min(1, rad + 0.5 - rr)
        if a > 0 then
          local t = (atan2(dy, dx) + math.pi) * k
          local i = floor(t)
          local f = t - i
          local d = min(f, 1 - f) * sw * rr
          local wf = 0.5 + ((i % 2 == 0) and 1 or -1) * min(0.5, d)
          blend(row, x, floor(cb[1] + (cw[1] - cb[1]) * wf + 0.5), floor(cb[2] + (cw[2] - cb[2]) * wf + 0.5),
            floor(cb[3] + (cw[3] - cb[3]) * wf + 0.5), a)
        end
      end
    end)
  end

  -- testo centrato nel riquadro largo 'w': si riduce finche' non ci sta
  local function fitText(cv, s, cx, y, gh, w, c)
    while textWidth(s, gh) > w and gh > 5 do gh = gh * 0.92 end
    cv:text(s, cx, y, gh, c, "center")
    return gh
  end

  -- ------------------------------------------------------------ geometria del countdown
  -- Diametro del cerchio in pixel: lo stesso calcolato dal generatore (min(0.62 H, 0.40 W)).
  -- stili del countdown: 0 Standard (leader SMPTE), 1 Pannelli, 2 Quadrante
  local RING_H, RING_W = { 0.62, 0.50, 0.48 }, { 0.40, 0.34, 0.31 }
  local function ringD(W, H, style)
    local k = (style or 0) + 1
    return min((RING_H[k] or 0.62) * H, (RING_W[k] or 0.40) * W)
  end
  M.ringD = ringD

  -- Moduli per zona (dall'esterno verso il cerchio) nelle posizioni del leader SMPTE RP 428-6: stelle
  -- di Siemens negli angoli esterni, due file di tre quadrati, due strisce vicino alla linea di centro.
  -- Al posto dei due volti (incarnati): ColorChecker e toni della pelle.
  -- larghezza delle prove strette (frazione del modulo) nello stile Standard, come nel leader SMPTE
  local WIDTH = { peak = 0.5, res = 0.5 }
  local ZONES = {
    left = { A = { "star", "sphere", "peak" }, S = { "rampWR", "rampGB" }, B = { "star", "checker", "info" } },
    right = { A = { "star", "blue", "res" }, S = { "grey", "colors" }, B = { "star", "skin", "gamma" } },
  }

  -- strumento (spunta della taratura) di ogni prova; dimensione scelta nel pannello: 1 normale, 2 piccola, 3 grande
  local ENABLED
  local function calOn(spec, kind)
    local c = spec.cal
    if not c then return true end
    local k = ENABLED[kind]
    if kind == "info" then return c.labels or c.diag end
    return k == nil or c[k] ~= false and c[k] ~= nil
  end
  local function calSize(spec, kind)
    local k = ENABLED[kind] or kind
    return (spec.sizes and spec.sizes[k]) or 1
  end
  local function starSize(spec, ss)
    local z = calSize(spec, "star")
    return floor(ss * ((z == 2) and 0.7 or ((z == 3) and 1.45 or 1)) + 0.5)
  end
  M.calSize = calSize

  -- Stile Pannelli: stelle di Siemens negli angoli dell'area utile (il fuoco si legge sui
  -- bordi) e due gruppi compatti accanto al cerchio, ognuno con due file di due moduli e due strisce,
  -- con la didascalia sotto ogni modulo (e il titolo del gruppo). I moduli hanno una
  -- grandezza fissa in proporzione all'altezza (mai sotto i 40 px: le righe di 1 px restano leggibili).
  local CLUSTERS = {
    left = { title = "NITIDEZZA E GAMMA", Q = { "info", "res", "gamma", "sphere" }, S = { "rampWR", "rampGB" } },
    right = { title = "LIVELLI E COLORE", Q = { "peak", "blue", "checker", "skin" }, S = { "grey", "colors" } },
  }
  local CAPTIONS = { star = "FUOCO", sphere = "CONTOURING", peak = "BIANCO / NERO", info = "PIXEL 1:1",
    res = "NITIDEZZA / RGB", gamma = "GAMMA", blue = "BLU 47B", checker = "COLORCHECKER", skin = "INCARNATI",
    rampWR = "RAMPE", rampGB = "RAMPE", ramps = "RAMPE", pluge = "PLUGE", zone = "ZONE PLATE", checker6 = "COLORCHECKER", skin5 = "INCARNATI (SCALA MONK)",
    ramps4 = "RAMPE B/N, R, G, B", grey = "GRIGI / NERI 0-10%", colors = "COLORI 100% / 75%" }
  M.CAPTIONS = CAPTIONS

  function M.clusters(W, H, spec, out, ix0, iy0, ix1, iy1, m)
    local style = out.style
    local D, u = out.D, min(W, H)
    local gc = max(3, floor(0.035 * u + 0.5))
    local titled = style == 1
    -- stelle negli angoli dell'area utile
    local ss = max(48, floor((style == 1 and 0.15 or 0.12) * min(H, 1.2 * W) + 0.5))
    ss = min(starSize(spec, ss), floor((ix1 - ix0) * 0.2), floor((iy1 - iy0) * 0.3))
    local function put(kind, x, y, ww, hh, extra)
      local it = { kind = kind, x = floor(x + 0.5), y = floor(y + 0.5), w = floor(ww + 0.5), h = floor(hh + 0.5) }
      for k, v in pairs(extra or {}) do it[k] = v end
      out.items[#out.items + 1] = it
      return it
    end
    if ss >= 24 then
      -- negli angoli dell'area utile (dentro le frame lines) o del quadro intero
      local a0, b0, a1, b1 = ix0, iy0, ix1, iy1
      if spec.starsPos == 1 then a0, b0, a1, b1 = 0, 0, W, H end
      put("star", a0 + m, b0 + m, ss, ss); put("star", a1 - m - ss, b0 + m, ss, ss)
      put("star", a0 + m, b1 - m - ss, ss, ss); put("star", a1 - m - ss, b1 - m - ss, ss, ss)
    end
    local cap = (style == 1) and 0.2 or 0.17            -- altezza della didascalia (frazione del modulo)
    local g = 0.1
    for _, name in ipairs({ "left", "right" }) do
      local C = CLUSTERS[name]
      local x0 = (name == "left") and (ix0 + m) or floor(W / 2 + D / 2 + gc)
      local x1 = (name == "left") and floor(W / 2 - D / 2 - gc) or (ix1 - m)
      local colw = x1 - x0
      -- altezza del gruppo in moduli: titolo + 2 file (modulo + didascalia) + 2 strisce (0.42 + didascalia)
      local rows = (titled and 0.28 or 0) + 2 * (1 + cap + g) + 2 * (0.42 + cap + g)
      local avail = (iy1 - iy0) - 2 * m - 2 * ss
      local s = min((style == 1 and 0.115 or 0.085) * H, colw / (2 + g), avail / rows)
      s = floor(max(min(40, colw / (2 + g)), s))
      if s >= 24 and colw > 0 then
        local gw = floor(2 * s + g * s)
        -- accanto al cerchio (gruppo stretto attorno al countdown), centrato in altezza
        local gx = (name == "left") and (x1 - gw) or x0
        local gh = floor(rows * s)
        local y = floor((iy0 + iy1) / 2 - gh / 2)
        -- scheda grigia dietro il gruppo
        local pad = floor(0.12 * s)
        put("card", gx - pad, y - pad, gw + 2 * pad, gh + pad)
        if titled then put("title", gx, y, gw, floor(0.18 * s), { text = C.title }); y = y + floor(0.28 * s) end
        for r = 0, 1 do
          for c = 0, 1 do
            local kind = C.Q[r * 2 + c + 1]
            put(kind, gx + c * (s + floor(g * s)), y, s, s, { caption = CAPTIONS[kind] })
          end
          y = y + floor(s * (1 + cap + g))
        end
        for i = 1, 2 do
          local kind = C.S[i]
          put(kind, gx, y, gw, floor(0.42 * s), { caption = (kind ~= "rampWR") and CAPTIONS[kind] or nil })
          y = y + floor(s * (0.42 + cap + g))
        end
        out.s = s
      end
    end
    return out
  end

  -- Quadrante: i test sono la ghiera dell'orologio. Tessere con angoli arrotondati lungo la ghiera (a destra nitidezza
  -- e gamma, a sinistra livelli e colore; niente in alto e in basso, dove stanno logo e dati), grigi e
  -- neri 0-10% come arco a sinistra, colori al 100% e al 75% come arco a destra, stelle negli angoli.
  -- Quadrante: due pannelli di prove nella loro forma vera (quadrati con bordo, strisce, tavole), file di
  -- larghezza uguale; ogni voce: { tipo, rapporto larghezza / altezza }
  local QUAD = {
    { dir = -1, title = "LIVELLI E NITIDEZZA", items = { { "peak", 1 }, { "pluge", 1 }, { "gamma", 1 }, { "grey", 3 },
      { "ramps4", 3 }, { "sphere", 1 }, { "info", 1 }, { "res", 1 } } },
    { dir = 1, title = "COLORE", items = { { "checker6", 1.5 }, { "blue", 1 }, { "skin5", 2.5 }, { "colors", 2 },
      { "zone", 1 } } },
  }
  -- file "giustificate": ogni fila si chiude quando la somma dei rapporti arriva al suo obiettivo (3; 4 se la
  -- prima prova e' piccola, 2 se e' grande, cioe' prove piu' grandi); le strisce piccole si assottigliano,
  -- quelle grandi si alzano. Le prove spente non occupano posto.
  local function quadRows(spec, side)
    local rows, cur = {}, nil
    for _, e in ipairs(side.items) do
      if calOn(spec, e[1]) then
        local z = calSize(spec, e[1])
        local a = e[2]
        if a > 1.2 then a = (z == 2) and a * 1.35 or ((z == 3) and a / 1.5 or a) end
        local target = (z == 2) and 4 or ((z == 3) and 2 or 3)
        if not cur or cur.sum + a > cur.target + 0.01 or (a <= 1.2 and cur.z ~= z) then
          cur = { items = {}, sum = 0, target = max(target, a), z = z }
          rows[#rows + 1] = cur
        end
        cur.items[#cur.items + 1] = { e[1], a }
        cur.sum = cur.sum + a
      end
    end
    return rows
  end
  local RADIAL = { { "info", 50 }, { "res", 80 }, { "gamma", 110 }, { "sphere", 140 },
    { "peak", 310 }, { "blue", 280 }, { "checker", 250 }, { "skin", 220 } }
  function M.radial(W, H, spec, out, ix0, iy0, ix1, iy1, m)
    local u = min(W, H)
    local R = out.D / 2
    local cx, cy = (ix0 + ix1) / 2, (iy0 + iy1) / 2
    local function put(kind, x, y, ww, hh, extra)
      local it = { kind = kind, x = floor(x + 0.5), y = floor(y + 0.5), w = floor(ww + 0.5), h = floor(hh + 0.5) }
      for k, v in pairs(extra or {}) do it[k] = v end
      out.items[#out.items + 1] = it
      return it
    end
    -- archi della ghiera
    out.arcs = { { kind = "grey", r0 = R * 1.13, r1 = R * 1.21, a0 = 206, a1 = 334 },
      { kind = "black", r0 = R * 1.225, r1 = R * 1.27, a0 = 206, a1 = 334 },
      { kind = "color", r0 = R * 1.13, r1 = R * 1.21, a0 = 26, a1 = 154 },
      { kind = "desat", r0 = R * 1.225, r1 = R * 1.27, a0 = 26, a1 = 154 } }
    local Rb = R * 1.27
    -- Griglia ordinata: due pannelli ai lati della ghiera, ognuno con il titolo e 3 file di 2 tessere
    -- uguali (a sinistra livelli e gamma, a destra colore e nitidezza), didascalia sotto ogni tessera;
    -- stelle di Siemens nei quattro angoli (il fuoco si valuta sui bordi del monitor). La tessera e' la piu'
    -- grande che sta nell'area utile senza toccare ghiera e stelle: le stelle stanno in una colonna a parte
    -- o in alto e in basso, secondo dove la tessera viene piu' grande.
    -- orient "side": pannelli a sinistra e a destra del cerchio; "stack": sopra e sotto (formati verticali).
    -- mode "rows": le stelle occupano la fascia in alto e in basso; "col": una colonna ai lati.
    -- Per ogni pannello: larghezza wp, ogni fila alta wp / (somma dei rapporti), didascalia sotto ogni prova.
    local g = max(4, floor(0.03 * u + 0.5))
    local function need(side, wp)                     -- altezza del pannello largo wp
      local gh = max(7, floor(0.026 * wp + 0.5))
      local cap = gh + max(3, floor(gh * 0.7))
      local th = floor(gh * 1.4 + 0.5)
      local tot = th + floor(gh * 0.9)
      for _, row in ipairs(quadRows(spec, side)) do
        tot = tot + (wp - (#row.items - 1) * g) / max(row.sum, row.target) + cap + g
      end
      return tot - g, gh, cap, th
    end
    local function panel(ss, orient, mode)
      local x0, y0, x1, y1 = ix0 + m, iy0 + m, ix1 - m, iy1 - m
      local w, h
      if orient == "side" then
        w, h = cx - Rb - g - x0, y1 - y0
        if mode == "col" then w = w - ss - g else h = h - 2 * (ss + g) end
      else
        w, h = x1 - x0, cy - Rb - g - y0
        if mode == "col" then w = w - 2 * (ss + g) else h = h - ss - g end
      end
      if w < 40 or h < 40 then return end
      local wp = w
      for _, side in ipairs(QUAD) do
        while wp > 40 and need(side, wp) > h do wp = wp * 0.97 end
      end
      wp = floor(wp)
      if wp < max(60, floor(0.12 * u)) then return end
      return { wp = wp, w = w, h = h, mode = mode, orient = orient }
    end
    local ss = starSize(spec, max(48, floor(0.16 * min(H, 1.2 * W) + 0.5)))
    if not calOn(spec, "star") then ss = 0 end
    local best
    -- con logo o dati sopra / sotto il cerchio i pannelli restano ai lati
    for _, orient in ipairs((spec.cdLogo or spec.cdInfo) and { "side" } or { "side", "stack" }) do
      for _, mode in ipairs({ "rows", "col" }) do
        local P = panel(ss, orient, mode)
        if P and (not best or P.wp > best.wp + 2) then best = P end
      end
    end
    if best then
      local P = best
      local x0, y0, x1, y1 = ix0 + m, iy0 + m, ix1 - m, iy1 - m
      if ss > 0 then
        local a0, b0, a1, b1 = x0, y0, x1, y1
        if spec.starsPos == 1 then a0, b0, a1, b1 = m, m, W - m, H - m end
        put("star", a0, b0, ss, ss); put("star", a1 - ss, b0, ss, ss)
        put("star", a0, b1 - ss, ss, ss); put("star", a1 - ss, b1 - ss, ss, ss)
      end
      for _, side in ipairs(QUAD) do
        local gH, gh, cap, th = need(side, P.wp)
        local gx, gy
        if P.orient == "side" then
          -- nella sua fascia, accostato alla ghiera, centrato in altezza
          local fx0 = (side.dir < 0) and (x0 + ((P.mode == "col") and (ss + g) or 0)) or (cx + Rb + g)
          gx = (side.dir < 0) and (fx0 + P.w - P.wp) or fx0
          gy = floor((y0 + y1) / 2 - gH / 2 + 0.5)
        else
          gx = floor(cx - P.wp / 2 + 0.5)
          gy = (side.dir < 0) and floor(cy - Rb - g - gH) or floor(cy + Rb + g)
        end
        put("title", gx, gy, P.wp, th, { text = side.title, center = true })
        local y = gy + th + floor(gh * 0.9)
        for _, row in ipairs(quadRows(spec, side)) do
          local n = #row.items
          local rh = floor((P.wp - (n - 1) * g) / max(row.sum, row.target))
          local rw = 0
          for _, e in ipairs(row.items) do rw = rw + floor(rh * e[2]) end
          rw = rw + (n - 1) * g
          local full = row.sum >= row.target - 0.01
          local x = full and gx or floor(gx + (P.wp - rw) / 2)       -- fila incompleta: centrata
          for k, e in ipairs(row.items) do
            local ww = (full and k == n) and (gx + P.wp - x) or floor(rh * e[2])
            put(e[1], x, y, ww, rh, { caption = CAPTIONS[e[1]], capBelow = true, capH = gh })
            x = x + ww + g
          end
          y = y + rh + cap + g
        end
      end
      out.s = P.wp
      out.s = P.s
      out.arcLabels = true
      return out
    end
    -- area troppo stretta per la griglia: stelle piccole negli angoli e tessere lungo la ghiera
    local ss = max(36, floor(0.075 * H + 0.5))
    ss = min(ss, floor((ix1 - ix0) * 0.12), floor((iy1 - iy0) * 0.25))
    if ss >= 24 then
      put("star", ix0 + m, iy0 + m, ss, ss, { round = true }); put("star", ix1 - m - ss, iy0 + m, ss, ss, { round = true })
      put("star", ix0 + m, iy1 - m - ss, ss, ss, { round = true })
      put("star", ix1 - m - ss, iy1 - m - ss, ss, ss, { round = true })
    end
    -- tessere: due colonne che seguono la curva della ghiera (x = bordo esterno del cerchio alla
    -- quota della fila); si rimpiccioliscono finche' stanno nell'area utile senza toccare le stelle
    -- didascalia a lato (verso l'esterno) se c'e' spazio, altrimenti sotto la tessera
    local function capLen(k) return (k == "gamma") and 9 or #CAPTIONS[k] end
    local function fits(t, side)
      local gh = max(7, floor(0.11 * t + 0.5))
      local p = side and t * 1.22 or t * 1.5
      if 4 * p > (iy1 - iy0) - 2 * m then return end
      local pos = {}
      for i, e in ipairs(RADIAL) do
        local dir = (i <= 4) and 1 or -1
        local k = (i <= 4) and i or (i - 4)
        local dy = (k - 2.5) * p
        -- la tessera (quadrata, angoli arrotondati) resta fuori dalla ghiera con un piccolo varco
        local gap, xc = max(4, 0.12 * t), 0.8 * Rb + t / 2
        local function clear(v)
          local nx, ny = max(0, v - t / 2), max(0, abs(dy) - t / 2)
          return sqrt(nx * nx + ny * ny) >= Rb + gap
        end
        local lo, hi = xc, xc + Rb + t
        if not clear(lo) then
          for _ = 1, 20 do local mid = (lo + hi) / 2; if clear(mid) then hi = mid else lo = mid end end
          xc = hi
        end
        local x = (dir > 0) and (cx + xc - t / 2) or (cx - xc - t / 2)
        local y = cy + dy - t / 2
        local bx0, bx1, by0, by1 = x, x + t, y, y + t
        if side then
          local cw = textWidth(string.rep("M", capLen(e[1])), gh) + 0.14 * t
          if dir > 0 then bx1 = bx1 + cw else bx0 = bx0 - cw end
        else
          by1 = by1 + 0.3 * t
        end
        if bx0 < ix0 + m or bx1 > ix1 - m then return end
        for _, st in ipairs(out.items) do
          if bx0 < st.x + st.w + 4 and st.x < bx1 + 4 and by0 < st.y + st.h + 4 and st.y < by1 + 4 then return end
        end
        pos[i] = { e[1], x, y, dir }
      end
      return pos, gh
    end
    local pos, gh, side
    for _, sd in ipairs({ true, false }) do
      local t = floor(0.16 * u + 0.5)
      pos, gh = fits(t, sd)
      while not pos and t > 24 do t = t - 2; pos, gh = fits(t, sd) end
      if pos and t >= floor(0.075 * u) or (pos and not sd) then side = sd; out.s = t; break end
      pos = nil
    end
    if pos then
      local t = out.s
      for _, q in ipairs(pos) do
        put(q[1], q[2], q[3], t, t, { tile = true, caption = CAPTIONS[q[1]], capSide = side and q[4] or nil, capH = gh })
      end
    end
    return out
  end

  -- Impaginazione adattiva: i moduli stanno ai lati del cerchio (colonna centrale libera per
  -- cerchio, logo e dati), dentro l'area comune delle frame lines attive (spec.inner) e con un
  -- varco a meta' altezza per la linea di centro e le scale dei bordi. Tre moduli per fila se la
  -- zona e' larga, uno sopra l'altro se e' stretta (4:3 molto stretto, verticali).
  function M.layout(W, H, spec)
    spec = spec or {}
    local u = min(W, H)
    local style = spec.style or 0
    local D = ringD(W, H, style)
    local m = max(3, floor(0.035 * u + 0.5))
    local gc = max(3, floor(0.03 * u + 0.5))
    local ix0, iy0, ix1, iy1 = 0, 0, W, H
    local inner = spec.inner
    if inner and (inner[1] > 0 or inner[2] > 0 or inner[3] < W or inner[4] < H) then
      local pad = floor(0.03 * H + 0.5)                  -- spazio per le etichette delle frame lines
      ix0, iy0 = max(0, inner[1] + pad), max(0, inner[2] + pad)
      ix1, iy1 = min(W, inner[3] - pad), min(H, inner[4] - pad)
    end
    local midgap = max(8, floor(0.075 * H + 0.5))
    local out = { D = D, items = {}, midgap = midgap, cols = 0, s = 0, style = style }
    if style == 1 then return M.clusters(W, H, spec, out, ix0, iy0, ix1, iy1, m) end
    if style == 2 then return M.radial(W, H, spec, out, ix0, iy0, ix1, iy1, m) end
    local function zone(name, x0, x1)
      local y0, y1 = iy0 + m, iy1 - m
      local w, h = x1 - x0, y1 - y0
      if w < 0.08 * u or h < 0.25 * u then return end
      local g, sr = 0.12, 0.5
      -- come nel leader SMPTE RP 428-6: prove grandi (fino al 19% dell'altezza), bianco/nero e righe RGB
      -- strette (mezzo modulo), 24/SEC e gamma a 2/3, cosi' stanno tre per fila accanto al cerchio
      local Z = ZONES[name]
      local function rowW(list) local t = 0 for _, k in ipairs(list) do t = t + (WIDTH[k] or 1) end return t end
      local wa = max(rowW(Z.A), rowW(Z.B))
      local s3 = min(w / (wa + 2 * g), (h - midgap) / (2 + 2 * sr + 2 * g), 0.19 * H)
      local s1 = min(w, (h - midgap) / (6 + 2 * sr + 6 * g), 0.15 * H)
      local cols = (s1 > 1.35 * s3) and 1 or 3
      local s = floor(cols == 3 and s3 or s1)
      if s < 24 then return end
      local gs = max(2, floor(g * s + 0.5))
      -- strisce alte fino a 3/4 del modulo se c'e' spazio
      local rows = (cols == 3) and 2 or 6
      local sh = floor(min(0.75 * s, (h - midgap - rows * s - (rows + 2) * gs) / 2) + 0.5)
      sh = max(sh, floor(sr * s + 0.5))
      local ym = floor((y0 + y1) / 2 + 0.5)
      local left = name == "left"
      local function put(kind, x, y, ww, hh)
        out.items[#out.items + 1] = { kind = kind, x = floor(x + 0.5), y = floor(y + 0.5), w = ww, h = hh, zone = name }
      end
      if cols == 3 then
        local cw = floor(wa * s + 2 * gs)
        local xs = x0 + floor((w - cw) / 2 + 0.5)
        for _, rw in ipairs({ { Z.A, y0 }, { Z.B, y1 - s } }) do
          local x = left and xs or (xs + cw)
          for _, kind in ipairs(rw[1]) do
            local ww = floor((WIDTH[kind] or 1) * s + 0.5)
            if left then put(kind, x, rw[2], ww, s); x = x + ww + gs
            else x = x - ww; put(kind, x, rw[2], ww, s); x = x - gs end
          end
        end
        put(Z.S[1], xs, ym - floor(midgap / 2) - sh, cw, sh)
        put(Z.S[2], xs, ym + midgap - floor(midgap / 2), cw, sh)
      else
        local xs = x0 + floor((w - s) / 2 + 0.5)
        for k = 1, 3 do
          put(Z.A[k], xs, y0 + (k - 1) * (s + gs), s, s)
          put(Z.B[k], xs, y1 - s - (k - 1) * (s + gs), s, s)
        end
        put(Z.S[1], xs, ym - floor(midgap / 2) - sh, s, sh)
        put(Z.S[2], xs, ym + midgap - floor(midgap / 2), s, sh)
      end
      out.cols, out.s = cols, s
    end
    zone("left", ix0 + m, floor(W / 2 - D / 2 - gc))
    zone("right", floor(W / 2 + D / 2 + gc), ix1 - m)
    return out
  end

  -- valori sRGB 8 bit del ColorChecker Classic (X-Rite, dopo il 2014), per righe
  local CHECKER = {
    { 115, 82, 68 }, { 194, 150, 130 }, { 98, 122, 157 }, { 87, 108, 67 }, { 133, 128, 177 }, { 103, 189, 170 },
    { 214, 126, 44 }, { 80, 91, 166 }, { 193, 90, 99 }, { 94, 60, 108 }, { 157, 188, 64 }, { 224, 163, 46 },
    { 56, 61, 150 }, { 70, 148, 73 }, { 175, 54, 60 }, { 231, 199, 31 }, { 187, 86, 149 }, { 8, 133, 161 },
    { 243, 243, 242 }, { 200, 200, 200 }, { 160, 160, 160 }, { 122, 122, 121 }, { 85, 85, 85 }, { 52, 52, 52 },
  }
  -- scala Monk dei toni della pelle (Google / E. Monk, CC BY 4.0), dal tono 1 (chiaro) al 10 (scuro)
  local SKIN = { "f6ede4", "f3e7db", "f7ead0", "eadaba", "d7bd96", "a07e56", "825c43", "604134", "3a312a", "292420" }
  -- toppa uniforme con la stessa luce media di righe alterne 0 / 100% con il gamma g: 0.5^(1/g)
  function M.gammaPatch(g) return floor(255 * 0.5 ^ (1 / g) + 0.5) end

  -- Riferimenti colorimetrici (ColorChecker, scala Monk): i valori pubblicati sono sRGB 8 bit (primari
  -- Rec.709, curva sRGB). Per un display Rec.709 / BT.1886 (gamma 2.4), DCI-P3 (2.6) o Rec.2020 vanno
  -- linearizzati, portati nei primari di uscita e ricodificati con il gamma di uscita: cosi' sul monitor di
  -- riferimento la toppa ha la stessa luce e la stessa cromaticita' della tavola vera (D65). Con uscita
  -- sRGB 2.2 i valori restano quelli pubblicati.
  local TO_PRIM = {   -- matrici lineari Rec.709 -> primari di uscita (D65; ITU-R BT.2087 per Rec.2020)
    p3 = { { 0.822462, 0.177538, 0 }, { 0.033194, 0.966806, 0 }, { 0.017083, 0.072397, 0.910520 } },
    ["2020"] = { { 0.627404, 0.329283, 0.043313 }, { 0.069097, 0.919540, 0.011362 }, { 0.016391, 0.088013, 0.895595 } },
  }
  function M.refColor(c, g, prim)
    g = g or 2.4
    if abs(g - 2.2) < 0.01 and not TO_PRIM[prim or ""] then return { c[1], c[2], c[3] } end
    local lin = {}
    for i = 1, 3 do
      local v = c[i] / 255
      lin[i] = (v <= 0.04045) and (v / 12.92) or (((v + 0.055) / 1.055) ^ 2.4)
    end
    local m = TO_PRIM[prim or ""]
    if m then
      lin = { m[1][1] * lin[1] + m[1][2] * lin[2] + m[1][3] * lin[3], m[2][1] * lin[1] + m[2][2] * lin[2] + m[2][3] * lin[3],
        m[3][1] * lin[1] + m[3][2] * lin[2] + m[3][3] * lin[3] }
    end
    local out = {}
    for i = 1, 3 do out[i] = floor(255 * max(0, min(1, lin[i])) ^ (1 / g) + 0.5) end
    return out
  end

  -- ------------------------------------------------------------ moduli
  local WHITE, BLACK = { 255, 255, 255 }, { 0, 0, 0 }
  local INK = { 16, 16, 16 }
  local RGBCMY = { { 255, 0, 0 }, { 0, 255, 0 }, { 0, 0, 255 }, { 255, 255, 0 }, { 0, 255, 255 }, { 255, 0, 255 } }
  -- stesso colore al 75% dell'ampiezza (191 su 255: 721 a 10 bit in livelli video, come le barre 75%)
  function M.c75(c) return { floor(c[1] * 0.75 + 0.5), floor(c[2] * 0.75 + 0.5), floor(c[3] * 0.75 + 0.5) } end

  -- testo allineato a sinistra ridotto fino a stare in w
  local function fitLeft(cv, s, x, y, gh, w, c)
    while textWidth(s, gh) > w and gh > 5 do gh = gh * 0.92 end
    cv:text(s, x, y, gh, c)
    return gh
  end

  local MODULES = {}
  local STRIPS_FILL
  -- stelle di Siemens (fuoco): il disco grigio al centro, dove i raggi si fondono, deve essere il piu'
  -- piccolo possibile, rotondo e uguale nei quattro angoli (planarita' del fuoco); frange rosse o blu
  -- sui raggi = convergenza RGB
  -- 36 cicli, come le stelle del leader SMPTE RP 428-6: alla mappatura 1:1 e a fuoco il disco grigio al
  -- centro ha un raggio di circa 36 / pi = 11.5 px (dove un ciclo e' lungo 2 px)
  function MODULES.star(cv, x, y, s, p, ctx)
    cv:rect(x + p, y + p, x + s - p, y + s - p, { 110, 110, 110 })
    cv:siemens(x + s / 2, y + s / 2, s / 2 - p - 1, 36, WHITE, BLACK)
  end
  -- sfera divisa (gradienti per il contouring): meta' alta nelle alte luci (dal 60% al bianco), meta'
  -- bassa nelle ombre (dal nero al 16%). Le sfumature devono essere continue, senza anelli ne' gradini;
  -- in basso l'ombra deve sparire nel nero senza un bordo.
  function MODULES.sphere(cv, x, y, s, p, ctx)
    cv:rect(x + p, y + p, x + s - p, y + s - p, { 110, 110, 110 })
    local cx, cy, R = x + s / 2, y + s / 2, s / 2 - p - 1
    local lx, ly, lz = -0.2, 0.45, 0.55
    local ln = sqrt(lx * lx + ly * ly + lz * lz)
    lx, ly, lz = lx / ln, ly / ln, lz / ln
    local x0, x1 = max(0, floor(cx - R - 1)), min(cv.W - 1, floor(cx + R + 1))
    cv:add(cy - R - 1, cy + R + 1, function(yy, row)
      local dy = (yy + 0.5 - cy) / R
      for xx = x0, x1 do
        local dx = (xx + 0.5 - cx) / R
        local d2 = dx * dx + dy * dy
        local edge = (1 - sqrt(d2)) * R + 0.5
        if edge > 0 then
          local nz = sqrt(max(0, 1 - d2))
          local v
          if dy < 0 then
            v = 0.60 + 0.40 * max(0, min(1, dx * lx - dy * ly + nz * lz)) ^ 0.9
          else
            v = 0.16 * (1 - nz) ^ 1.3
          end
          v = floor(255 * v + 0.5)
          blend(row, xx, v, v, v, min(1, edge))
        end
      end
    end)
  end
  -- riferimenti del bianco e del nero (valori di SMPTE RP 133): quadrato al 95% nel bianco al 100% e
  -- quadrato al 5% nel nero; si devono vedere tutti e due (niente bianchi tagliati ne' neri schiacciati)
  function MODULES.peak(cv, x, y, s, p, ctx, w, h)
    w, h = w or s, h or s
    local iw, ih = w - 2 * p, h - 2 * p
    local hh = floor(ih / 2)
    cv:rect(x + p, y + p, x + w - p, y + p + hh, WHITE)
    cv:rect(x + p, y + p + hh, x + w - p, y + h - p, BLACK)
    local q = floor(min(hh, iw) * 0.56)
    local cx = x + w / 2
    local cw, cb = y + p + hh / 2, y + p + hh + (ih - hh) / 2
    cv:rect(cx - q / 2, cw - q / 2, cx + q / 2, cw + q / 2, { 242, 242, 242 })
    cv:rect(cx - q / 2, cb - q / 2, cx + q / 2, cb + q / 2, { 13, 13, 13 })
  end
  -- fotogrammi al secondo e risoluzione della timeline (come "24 / SEC · 2K" del leader SMPTE, che
  -- esiste per ogni frame rate e in 2K e 4K) e triangolo di righe di 1 px annidate, orizzontali e
  -- verticali, alla risoluzione nativa: con la mappatura 1:1 dei pixel ogni riga e' netta e uniforme;
  -- moire', righe doppie o un grigio piatto = il monitor o il proiettore sta scalando l'immagine
  function MODULES.info(cv, x, y, s, p, ctx, w, h)
    w, h = w or s, h or s
    local iw, ih = w - 2 * p, h - 2 * p
    local band = floor(0.27 * ih)
    local x0, y0 = x + p, y + p
    cv:rect(x0, y0, x0 + iw, y0 + band, { 118, 118, 118 })
    cv:rect(x0, y0 + band, x0 + iw, y0 + ih, { 196, 196, 196 })
    if ctx.cal.labels then
      fitText(cv, ctx.fpsLabel or "", x0 + iw / 2, y0 + band * 0.22, floor(band * 0.56), iw * 0.88, INK)
      local g2 = fitLeft(cv, ctx.resLabel or "", x0 + 0.08 * iw, y0 + band + 0.09 * ih, floor(0.2 * ih), iw * 0.8, INK)
      fitLeft(cv, string.format("%dx%d", ctx.W, ctx.H), x0 + 0.06 * iw, y0 + band + 0.09 * ih + g2 * 1.4,
        floor(0.07 * ih), iw * 0.88, { 60, 60, 60 })
    end
    if ctx.cal.diag then
      local t = floor(min(iw, ih - band) * 0.8)
      cv:nested(x0 + iw - t, y0 + ih - t, t, "br", WHITE, BLACK)
    end
  end
  -- nitidezza e scalatura: righe di 1, 2, 3, 4 px verticali e orizzontali; sotto righe di 1 px rosse,
  -- verdi e blu (registrazione dei pannelli, sottocampionamento del colore): ognuna netta e pura
  function MODULES.res(cv, x, y, s, p, ctx, w, h)
    w, h = w or s, h or s
    local iw = w - 2 * p
    local nk = (iw >= 0.8 * (h - 2 * p)) and 4 or 2            -- modulo stretto: righe di 1 e 2 px
    local gh = max(6, floor(0.08 * h))
    local lh = floor(gh * 1.6)
    local gap = max(1, floor(0.03 * h))
    local cw = (iw - (nk - 1) * gap) / nk
    local rh = floor((h - 2 * p - lh - 3 * gap) / 3)
    local y1 = y + p + lh
    for k = 1, nk do
      local gx = x + p + (k - 1) * (cw + gap)
      fitText(cv, tostring(k), gx + cw / 2, y + p + (lh - gh) / 2, gh, cw, ctx.accent)
      cv:grating(gx, y1, gx + cw, y1 + rh, k, true, WHITE, BLACK)
      cv:grating(gx, y1 + rh + gap, gx + cw, y1 + 2 * rh + gap, k, false, WHITE, BLACK)
    end
    local y2 = y1 + 2 * (rh + gap)
    local half = x + p + floor(iw / 2)
    cv:pattern(x + p, y2, half - gap, y + h - p, function(dx)
      local c = RGBCMY[dx % 3 + 1]
      return c[1], c[2], c[3]
    end)
    cv:pattern(half + gap, y2, x + w - p, y + h - p, function(_, dy)
      local c = RGBCMY[dy % 3 + 1]
      return c[1], c[2], c[3]
    end)
  end
  -- verifica del blu (filtro Wratten 47B o canale blu del monitor): magenta, ciano, blu e bianco
  -- hanno tutti il blu al 100%: con il filtro i quadrati interni devono sparire
  function MODULES.blue(cv, x, y, s, p, ctx)
    local iw = s - 2 * p
    local hh = floor(iw / 2)
    local ym = y + p + hh
    cv:rect(x + p, y + p, x + s - p, ym, { 255, 0, 255 })
    cv:rect(x + p, ym, x + s - p, y + s - p, { 0, 0, 255 })
    local q = floor(iw * 0.46 / 2) * 2
    local cx = x + s / 2
    cv:rect(cx - q / 2, ym - q / 2, cx + q / 2, ym, { 0, 255, 255 })
    cv:rect(cx - q / 2, ym, cx + q / 2, ym + q / 2, WHITE)
  end
  -- ColorChecker 24: resa del colore, incarnati (le prime due toppe) e scala neutra, nel gamma e nei
  -- primari di uscita (M.refColor)
  function MODULES.checker(cv, x, y, s, p, ctx, w, h)
    if STRIPS_FILL then return STRIPS_FILL.checker6(cv, x, y, w or s, h or s, p, ctx) end
    local iw = s - 2 * p
    local pitch = iw / 6
    local ps = max(2, floor(pitch * 0.86))
    local gy = y + p + (iw - 4 * pitch) / 2
    for i, c in ipairs(CHECKER) do
      local col, row = (i - 1) % 6, floor((i - 1) / 6)
      local px, py = x + p + col * pitch + (pitch - ps) / 2, gy + row * pitch + (pitch - ps) / 2
      cv:rect(px, py, px + ps, py + ps, M.refColor(c, ctx.gamma, ctx.prim))
    end
  end
  -- toni della pelle (al posto dei volti del leader SMPTE): i 10 toni della scala Monk, dal piu'
  -- chiaro al piu' scuro; devono restare distinti e naturali, senza dominanti
  function MODULES.skin(cv, x, y, s, p, ctx, w, h)
    if STRIPS_FILL then return STRIPS_FILL.skin5(cv, x, y, w or s, h or s, p, ctx) end
    local iw = s - 2 * p
    local pitch = iw / 5
    local ps = max(2, floor(pitch * 0.88))
    local gy = y + p + (iw - 2 * pitch) / 2
    for i, hex in ipairs(SKIN) do
      local col, row = (i - 1) % 5, floor((i - 1) / 5)
      local c = { tonumber(hex:sub(1, 2), 16), tonumber(hex:sub(3, 4), 16), tonumber(hex:sub(5, 6), 16) }
      local px, py = x + p + col * pitch + (pitch - ps) / 2, gy + row * pitch + (pitch - ps) / 2
      cv:rect(px, py, px + ps, py + ps, M.refColor(c, ctx.gamma, ctx.prim))
    end
  end
  -- verifica del gamma (come "2,6 γ" del leader SMPTE, qui con il gamma dello spazio colore del
  -- progetto): righe orizzontali alterne di 1 px nero / bianco (luce media 50%) accanto a un grigio pari a
  -- 0.5^(1/γ). Al 100% e da lontano le righe devono sparire nel grigio; in alto i grigi dei gamma
  -- vicini: se le righe somigliano a quello a sinistra il gamma del display e' piu' basso, a destra piu' alto
  function MODULES.gamma(cv, x, y, s, p, ctx, w, h)
    w, h = w or s, h or s
    local iw, ih = w - 2 * p, h - 2 * p
    local x0, y0 = x + p, y + p
    local band = floor(0.24 * ih)
    local g = ctx.gamma or 2.4
    local vl, vh, vg = M.gammaPatch(g - 0.2), M.gammaPatch(g + 0.2), M.gammaPatch(g)
    cv:rect(x0, y0, x0 + floor(iw / 2), y0 + band, { vl, vl, vl })
    cv:rect(x0 + floor(iw / 2), y0, x0 + iw, y0 + band, { vh, vh, vh })
    local gh = max(6, floor(band * 0.4))
    fitText(cv, string.format("%.1f", g - 0.2), x0 + iw / 4, y0 + (band - gh) / 2, gh, iw * 0.36, INK)
    fitText(cv, string.format("%.1f", g + 0.2), x0 + 3 * iw / 4, y0 + (band - gh) / 2, gh, iw * 0.36, INK)
    cv:rect(x0, y0 + band, x0 + iw, y0 + ih, { vg, vg, vg })
    -- righe solo orizzontali: con righe verticali la luce media dipende dal tempo di salita del display
    -- (N. Koren, Cornell) e il confronto non vale piu'
    cv:grating(x0, y0 + band, x0 + floor(iw * 0.55), y0 + ih, 1, false, WHITE, BLACK)
    local lab = string.format("%.1f", g)
    local g2 = floor(0.17 * min(iw, ih))
    while textWidth(lab, g2) > iw * 0.4 and g2 > 6 do g2 = g2 * 0.92 end
    local lx = x0 + iw * 0.95 - textWidth(lab, g2) / 2
    cv:text(lab, lx, y0 + band + 0.07 * ih, g2, INK, "center")
    cv:text("~", lx, y0 + band + 0.07 * ih + g2 * 1.35, g2, INK, "center")
  end

  -- strisce (rampe continue, scale di grigi, colori a due livelli)
  local STRIPS = {}
  STRIPS_FILL = STRIPS          -- ColorChecker e incarnati riempiono sempre tutta la loro tessera
  -- rampe continue per canale: sfumature senza gradini ne' cambi di tinta (banding, canale che clippa)
  function STRIPS.rampWR(cv, x, y, w, h, p)
    local hh = floor((h - 2 * p) / 2)
    cv:ramp(x + p, y + p, x + w - p, y + p + hh, BLACK, WHITE)
    cv:ramp(x + p, y + p + hh, x + w - p, y + h - p, BLACK, { 255, 0, 0 })
  end
  function STRIPS.rampGB(cv, x, y, w, h, p)
    local hh = floor((h - 2 * p) / 2)
    cv:ramp(x + p, y + p, x + w - p, y + p + hh, BLACK, { 0, 255, 0 })
    cv:ramp(x + p, y + p + hh, x + w - p, y + h - p, BLACK, { 0, 0, 255 })
  end
  -- in alto 11 gradini 0-100% (neutri e ben distinti), in basso i neri 0-10% a passi dell'1%:
  -- il primo gradino visibile dice dove il nero del display "mangia" il dettaglio
  function STRIPS.grey(cv, x, y, w, h, p)
    local hh = floor((h - 2 * p) / 2)
    local iw = w - 2 * p
    for i = 0, 10 do
      local x0, x1 = x + p + iw * i / 11, x + p + iw * (i + 1) / 11
      local v = floor(i * 25.5 + 0.5)
      cv:rect(x0, y + p, x1, y + p + hh, { v, v, v })
      v = floor(i * 2.55 + 0.5)
      cv:rect(x0, y + p + hh, x1, y + h - p, { v, v, v })
    end
  end
  -- primari e secondari al 100% (in alto, bordo della gamma) e al 75% (in basso, come le barre EBU
  -- 100/0/75/0 e SMPTE): al vettorscopio ogni toppa cade nel suo bersaglio 100% o 75%
  function STRIPS.colors(cv, x, y, w, h, p)
    local hh = floor((h - 2 * p) / 2)
    local iw = w - 2 * p
    for i, c in ipairs(RGBCMY) do
      local x0, x1 = x + p + iw * (i - 1) / 6, x + p + iw * i / 6
      cv:rect(x0, y + p, x1, y + p + hh, c)
      cv:rect(x0, y + p + hh, x1, y + h - p, M.c75(c))
    end
  end
  -- rampe continue in una tessera (Quadrante): bianco, rosso, verde, blu, una fascia per canale
  function MODULES.ramps(cv, x, y, s, p, ctx)
    local iw = s - 2 * p
    local cols = { WHITE, { 255, 0, 0 }, { 0, 255, 0 }, { 0, 0, 255 } }
    for i, c in ipairs(cols) do
      cv:ramp(x + p, y + p + iw * (i - 1) / 4, x + s - p, y + p + iw * i / 4, BLACK, c)
    end
  end
  -- PLUGE (ITU-R BT.814, parte sopra il nero): fondo 0%, barre al +2% e al +4%. Con la luminosita'
  -- giusta il +2% si vede appena e il +4% si vede; se il +2% sparisce il nero e' schiacciato, se il fondo
  -- diventa grigio il nero e' alzato. Il -2% non entra in un'immagine 0-255.
  function MODULES.pluge(cv, x, y, s, p, ctx)
    -- disposizione di ITU-R BT.814: barre strette vicino al nero a sinistra, toppa bianca a destra per il
    -- contrasto (picco), tutto su nero
    local iw = s - 2 * p
    local x0, y0 = x + p, y + p
    cv:rect(x0, y0, x0 + iw, y0 + iw, BLACK)
    local bw = max(2, floor(iw * 0.11))
    local v2, v4 = floor(0.02 * 255 + 0.5), floor(0.04 * 255 + 0.5)
    local ya, yb = y0 + floor(iw * 0.12), y0 + floor(iw * 0.78)
    cv:rect(x0 + floor(iw * 0.12), ya, x0 + floor(iw * 0.12) + bw, yb, { v2, v2, v2 })
    cv:rect(x0 + floor(iw * 0.12) + 2 * bw, ya, x0 + floor(iw * 0.12) + 3 * bw, yb, { v4, v4, v4 })
    cv:rect(x0 + floor(iw * 0.68), ya, x0 + floor(iw * 0.88), y0 + floor(iw * 0.34), WHITE)
    local gh = max(6, floor(iw * 0.08))
    local lc = { 70, 70, 70 }
    fitText(cv, "+2", x0 + floor(iw * 0.12) + bw / 2, y0 + iw * 0.84, gh, bw * 2.2, lc)
    fitText(cv, "+4", x0 + floor(iw * 0.12) + 2.5 * bw, y0 + iw * 0.84, gh, bw * 2.2, lc)
    fitText(cv, "100", x0 + floor(iw * 0.78), y0 + iw * 0.4, gh, iw * 0.3, lc)
  end
  -- zone plate circolare: anelli sempre piu' fitti fino alla frequenza di Nyquist sul bordo (0.5 cicli per
  -- pixel). Alla mappatura 1:1 si vedono solo gli anelli concentrici; cerchi in piu' (moire') vicino ai
  -- bordi o in diagonale = l'immagine viene scalata o filtrata
  function MODULES.zone(cv, x, y, s, p, ctx)
    local iw = s - 2 * p
    local cx, cy, R = x + p + iw / 2, y + p + iw / 2, iw / 2
    local k = math.pi / (2 * R)
    cv:pattern(x + p, y + p, x + s - p, y + s - p, function(dx, dy)
      local rx, ry = dx + 0.5 - R, dy + 0.5 - R
      local v = floor(255 * (0.5 + 0.5 * math.cos(k * (rx * rx + ry * ry))) + 0.5)
      return v, v, v
    end)
  end
  -- versioni rettangolari (Quadrante): ColorChecker 6 x 4 e scala Monk 5 x 2 a tutta area, rampe in 4 fasce
  function STRIPS.checker6(cv, x, y, w, h, p, ctx)
    local iw, ih = w - 2 * p, h - 2 * p
    local px, py = iw / 6, ih / 4
    local gp = max(1, floor(min(px, py) * 0.1))
    for i, c in ipairs(CHECKER) do
      local col, row = (i - 1) % 6, floor((i - 1) / 6)
      local x0, y0 = x + p + col * px, y + p + row * py
      cv:rect(x0 + gp / 2, y0 + gp / 2, x0 + px - gp / 2, y0 + py - gp / 2, M.refColor(c, ctx.gamma, ctx.prim))
    end
  end
  function STRIPS.skin5(cv, x, y, w, h, p, ctx)
    local iw, ih = w - 2 * p, h - 2 * p
    local px, py = iw / 5, ih / 2
    local gp = max(1, floor(min(px, py) * 0.08))
    for i, hex in ipairs(SKIN) do
      local col, row = (i - 1) % 5, floor((i - 1) / 5)
      local c = { tonumber(hex:sub(1, 2), 16), tonumber(hex:sub(3, 4), 16), tonumber(hex:sub(5, 6), 16) }
      local x0, y0 = x + p + col * px, y + p + row * py
      cv:rect(x0 + gp / 2, y0 + gp / 2, x0 + px - gp / 2, y0 + py - gp / 2, M.refColor(c, ctx.gamma, ctx.prim))
    end
  end
  function STRIPS.ramps4(cv, x, y, w, h, p)
    local ih = h - 2 * p
    for i, c in ipairs({ WHITE, { 255, 0, 0 }, { 0, 255, 0 }, { 0, 0, 255 } }) do
      cv:ramp(x + p, y + p + ih * (i - 1) / 4, x + w - p, y + p + ih * i / 4, BLACK, c)
    end
  end
  ENABLED = { checker6 = "checker", skin5 = "skin", ramps4 = "ramps", pluge = "pluge", zone = "zone", ramps = "ramps", star = "stars", sphere = "contour", peak = "peak", gamma = "gamma", res = "res", blue = "blue",
    checker = "checker", skin = "skin", rampWR = "ramps", rampGB = "ramps", grey = "grey", colors = "color" }

  -- bordo del raster (1 px esatto) e triangoli negli angoli: se si vedono, il display mostra tutto il quadro
  local function edges(cv, W, H, c)
    local u = min(W, H)
    c = c or WHITE
    cv:frame(0, 0, W, H, 1, c)
    local L = max(6, floor(0.03 * u + 0.5))
    cv:corner(0, 0, 1, 1, L, c); cv:corner(W, 0, -1, 1, L, c)
    cv:corner(0, H, 1, -1, L, c); cv:corner(W, H, -1, -1, L, c)
  end

  -- area comune delle frame lines attive, a pixel interi e pari come nel generatore.
  -- list: { { ar = 2.39 }, { safe = 0.9 }, ... }
  function M.innerRect(W, H, list)
    local x0, y0, x1, y1 = 0, 0, W, H
    local A = W / H
    for _, gd in ipairs(list or {}) do
      local aw, ah = W, H
      if gd.safe then aw, ah = 2 * floor(W * gd.safe / 2 + 0.5), 2 * floor(H * gd.safe / 2 + 0.5)
      elseif gd.ar and gd.ar > A + 0.005 then ah = 2 * floor(W / gd.ar / 2 + 0.5)
      elseif gd.ar and gd.ar < A - 0.005 then aw = 2 * floor(H * gd.ar / 2 + 0.5) end
      x0, x1 = max(x0, (W - aw) / 2), min(x1, (W + aw) / 2)
      y0, y1 = max(y0, (H - ah) / 2), min(y1, (H + ah) / 2)
    end
    return { x0, y0, x1, y1 }
  end

  -- ------------------------------------------------------------ taratura sul countdown
  -- spec: { accent = {r,g,b} 0..1, cal = { stars, res, diag, center, grey, color, checker, skin, ramps,
  --         blue, gamma, contour, peak, edge, labels }, fpsLabel, resLabel, gamma (di riferimento),
  --         inner = { x0, y0, x1, y1 }, frames = { rettangoli dei formati accesi }, guide = {r,g,b},
  --         cdLogo, cdInfo }
  local function mix(a, b, t) return { floor(a[1] + (b[1] - a[1]) * t + 0.5), floor(a[2] + (b[2] - a[2]) * t + 0.5),
    floor(a[3] + (b[3] - a[3]) * t + 0.5) } end
  M.mix = mix

  -- Sfondo, disco e linee del countdown li disegna il generatore (tema del countdown, dal vivo); qui
  -- spec.bg (sfondo del tema) e spec.ink (colore delle linee) servono solo ai colori di bordi, schede e
  -- didascalie, cosi' restano leggibili anche su sfondo grigio o bianco.
  function M.compose(W, H, spec)
    local cv = canvas(W, H)
    local bg8 = c8(spec.bg or { 0, 0, 0 })
    local accent = c8(spec.ink or spec.accent or { 0.85, 0.85, 0.85 })
    local border = mix(accent, bg8, 0.15)
    local lw = max(1, floor(H / 1080 * 2 + 0.5))
    local cal = spec.cal or {}
    local style = spec.style or 0
    local L = M.layout(W, H, spec)
    if cal.edge then edges(cv, W, H, (bg8[1] + bg8[2] + bg8[3] > 384) and BLACK or WHITE) end
    local blw = (style == 2) and 1 or ((style == 1) and 0 or lw)
    if style == 2 then border = mix(accent, bg8, 0.55) end
    local ctx = { cal = cal, accent = accent, fpsLabel = spec.fpsLabel, resLabel = spec.resLabel, W = W, H = H,
      gamma = spec.gamma, prim = spec.prim }
    local capc = (style == 2) and mix(accent, bg8, 0.3) or accent
    for _, it in ipairs(L.items) do
      if it.kind == "card" then
        cv:rect(it.x, it.y, it.x + it.w, it.y + it.h, mix(bg8, accent, 0.16))
      elseif it.kind == "title" then
        local gh = max(6, it.h)
        while textWidth(it.text, gh) > it.w and gh > 6 do gh = gh * 0.92 end
        if it.center then cv:text(it.text, it.x + it.w / 2, it.y, gh, accent, "center")
        else cv:text(it.text, it.x, it.y, gh, accent) end
      else
        local on = (it.kind == "info") and (cal.labels or cal.diag) or cal[ENABLED[it.kind]]
        -- "Piccolo" negli stili Standard e Pannelli: la prova si stringe al 72% nel suo posto (in Quadrante
        -- e per le stelle di Pannelli la dimensione la decide gia' l'impaginazione)
        if on and style ~= 2 and calSize(spec, it.kind) == 2 and not (style == 1 and it.kind == "star") then
          local k = 0.72
          local nw, nh = floor(it.w * k + 0.5), floor(it.h * k + 0.5)
          local c = {}
          for kk, vv in pairs(it) do c[kk] = vv end
          c.x, c.y, c.w, c.h = it.x + floor((it.w - nw) / 2), it.y + floor((it.h - nh) / 2), nw, nh
          it = c
        end
        if on then
          local s = min(it.w, it.h)
          cv:rect(it.x, it.y, it.x + it.w, it.y + it.h, BLACK)
          if blw > 0 and not it.round and not it.tile then cv:frame(it.x, it.y, it.x + it.w, it.y + it.h, blw, border) end
          local p = (it.round and 0 or blw) + max(1, floor(0.05 * min(it.w, it.h) + 0.5))
          if it.round or it.tile then p = 0 end                          -- contenuto a piena tessera
          if MODULES[it.kind] then MODULES[it.kind](cv, it.x, it.y, s, p, ctx, it.w, it.h)
          else STRIPS[it.kind](cv, it.x, it.y, it.w, it.h, p, ctx) end
          if it.round then
            cv:roundClip(it.x, it.y, s, nil)
            cv:ring(it.x + s / 2, it.y + s / 2, s / 2 - 0.5, max(1, floor(s / 120)), border)
          elseif it.tile then
            cv:roundRectClip(it.x, it.y, s, s, 0.2 * s, border, max(1, floor(s / 120)))
          end
          if it.capBelow then
            local text = (it.kind == "gamma") and string.format("GAMMA %.1f", ctx.gamma or 2.4) or it.caption
            -- la griglia ha gia' fatto spazio alla didascalia; se e' piu' larga della tessera si riduce
            local gh = it.capH
            while textWidth(text, gh) > it.w * 1.08 and gh > 6 do gh = gh * 0.94 end
            cv:text(text, it.x + it.w / 2, it.y + it.h + max(2, floor(it.capH * 0.6)) + (it.capH - gh) / 2, gh, capc, "center")
          elseif it.capSide then
            local text = (it.kind == "gamma") and string.format("GAMMA %.1f", ctx.gamma or 2.4) or it.caption
            local gh, cy0 = it.capH, it.y + (it.h - it.capH) / 2
            if it.capSide > 0 then cv:text(text, it.x + it.w + 0.14 * it.w, cy0, gh, capc)
            else cv:text(text, it.x - 0.14 * it.w, cy0, gh, capc, "right") end
          elseif it.caption then
            local text = (it.kind == "gamma") and string.format("GAMMA %.1f", ctx.gamma or 2.4) or it.caption
            local gh = max(6, floor(min(it.h, it.w) * ((style == 2) and 0.085 or 0.1) + 0.5))
            if it.h < it.w then gh = max(6, floor(it.h * 0.2 + 0.5)) end
            while textWidth(text, gh) > it.w and gh > 5 do gh = gh * 0.92 end
            -- se non sta nel modulo nemmeno a 5 px non si scrive (niente didascalie accavallate)
            if textWidth(text, gh) <= it.w + 1 then
              if it.round then cv:text(text, it.x + it.w / 2, it.y + it.h + max(2, floor(gh * 0.6)), gh, capc, "center")
              else cv:text(text, it.x, it.y + it.h + max(2, floor(gh * 0.6)), gh, capc) end
            end
          end
        end
      end
    end
    -- Quadrante: archi della ghiera (grigi e neri a sinistra, colori a destra), poi 60 tacche
    for _, a in ipairs(L.arcs or {}) do
      local on = (a.kind == "grey" or a.kind == "black") and cal.grey or cal.color
      if on then
        local n = (a.kind == "grey" or a.kind == "black") and 11 or 6
        local gap = 0.12
        cv:annulus(W / 2, H / 2, a.r0, a.r1, a.a0, a.a1, function(f)
          local k = floor(f * n)
          if k >= n or f * n - k < gap / 2 or f * n - k > 1 - gap / 2 then return nil end
          if a.kind == "grey" then local v = floor(k * 25.5 + 0.5) return { v, v, v } end
          if a.kind == "black" then local v = floor(k * 2.55 + 0.5) return { max(v, 1) == 1 and 0 or v, v, v } end
          local c = RGBCMY[k + 1]
          if a.kind == "color" then return c end
          return M.c75(c)
        end)
        -- valori scritti dentro ogni gradino: 0-100 sui grigi, 0-10 sui neri, R G B Y C M sui colori
        if L.arcLabels then
          local th = a.r1 - a.r0
          local gh = floor(th * ((a.kind == "grey" or a.kind == "color") and 0.5 or 0.62))
          local seg = (a.r0 + a.r1) / 2 * math.rad(a.a1 - a.a0) / n
          if gh >= 6 and a.kind ~= "desat" then
            for k = 0, n - 1 do
              local ang = math.rad(a.a0 + (k + 0.5) * (a.a1 - a.a0) / n)
              local rr = (a.r0 + a.r1) / 2
              local tx, ty = W / 2 + math.sin(ang) * rr, H / 2 - math.cos(ang) * rr
              local txt, col
              if a.kind == "grey" then txt = tostring(k * 10); col = (k >= 5) and BLACK or WHITE
              elseif a.kind == "black" then txt = tostring(k); col = { 150, 150, 150 }
              else txt = ({ "R", "G", "B", "Y", "C", "M" })[k + 1]; col = (k == 2) and WHITE or BLACK end
              if textWidth(txt, gh) <= seg * 0.8 then cv:text(txt, tx, ty - gh / 2, gh, col, "center") end
            end
          end
        end
      end
    end
    if style == 2 then
      local R = L.D / 2
      local tc = mix(accent, bg8, 0.45)
      for k = 0, 59 do
        local a = 2 * math.pi * k / 60
        local long = k % 5 == 0
        local r0, r1 = R * 1.035, R * (long and 1.1 or 1.065)
        local sx, sy = math.sin(a), -math.cos(a)
        cv:segment(W / 2 + sx * r0, H / 2 + sy * r0, W / 2 + sx * r1, H / 2 + sy * r1, max(0.6, lw * (long and 0.6 or 0.35)), tc)
      end
    end
    -- mirino (come nel leader SMPTE RP 428-6): disco grigio, tre quadrati concentrici e asterisco al centro
    -- della croce; serve a verificare centro ottico e allineamento del proiettore
    if cal.center and style ~= 2 then
      local a = floor(0.045 * min(H, W / 1.78) + 0.5)
      local cx, cy = W / 2, H / 2
      local disc = mix(bg8, accent, 0.25)
      cv:add(cy - 1.45 * a - 1, cy + 1.45 * a + 1, function(y, row)
        local dy = y + 0.5 - cy
        for x = max(0, floor(cx - 1.45 * a - 1)), min(W - 1, floor(cx + 1.45 * a + 1)) do
          local dx = x + 0.5 - cx
          local al = min(1, 1.45 * a + 0.5 - sqrt(dx * dx + dy * dy))
          if al > 0 then blend(row, x, disc[1], disc[2], disc[3], al) end
        end
      end)
      cv:rect(cx - a, cy - a, cx + a, cy + a, mix(bg8, BLACK, 0.6))
      for _, k in ipairs({ 1, 0.78, 0.56 }) do
        local b2 = floor(a * k)
        cv:frame(floor(cx - b2), floor(cy - b2), floor(cx + b2), floor(cy + b2), lw, accent)
      end
      local r = a * 0.4
      for _, d in ipairs({ { 1, 0 }, { 0, 1 }, { 0.7071, 0.7071 }, { 0.7071, -0.7071 } }) do
        cv:segment(cx - d[1] * r, cy - d[2] * r, cx + d[1] * r, cy + d[2] * r, max(0.6, lw * 0.5), accent)
      end
    end
    -- angoli dei formati delle frame lines accese (come le frecce del leader SMPTE): il triangolo punta
    -- all'angolo del formato e resta visibile anche se il mascherino copre la linea
    local T = max(5, floor(0.022 * min(W, H) + 0.5))
    local frames = spec.frames or {}
    for _, r in ipairs(frames) do
      local gcol = c8(r.color or spec.guide or { 1, 1, 1 })
      local x0, y0, x1, y1 = floor(r[1] + 0.5), floor(r[2] + 0.5), floor(r[3] + 0.5), floor(r[4] + 0.5)
      if x0 > 0 or y0 > 0 or x1 < W or y1 < H then
        cv:corner(x0, y0, 1, 1, T, gcol); cv:corner(x1, y0, -1, 1, T, gcol)
        cv:corner(x0, y1, 1, -1, T, gcol); cv:corner(x1, y1, -1, -1, T, gcol)
      end
    end
    return cv, L
  end

  -- ------------------------------------------------------------ barre SMPTE RP 219
  -- Barre HD SMPTE RP 219 (ARIB STD-B28) alla risoluzione della timeline. Valori R'G'B' normalizzati
  -- (0 = nero 64, 1 = bianco 940 a 10 bit in livelli video): Resolve li porta ai livelli video in uscita.
  -- Geometria di RP 219: larghezza utile a = min(W, 16/9 H), barre c = 3a/28 (7c = 3a/4), lati d =
  -- (W - 7c) / 2 (a 1920: d = 240; a 2K DCI: 304); altezze 7/12, 1/12, 1/12, 3/12.
  --   fila 1: 40% grigio | 75% bianco, giallo, ciano, verde, magenta, rosso, blu | 40% grigio
  --   fila 2: 100% ciano | -I | 75% bianco (6c) | 100% blu
  --   fila 3: 100% giallo | +Q | rampa Y 0-100% (5c) | 100% bianco | 100% rosso
  --   fila 4: 15% grigio | 0% (3c/2) | 100% bianco (2c) | 0% (5c/6) | PLUGE -2, 0, +2, 0, +4% (c/3) | 0% (c) | 15% grigio
  -- -I e +Q valgono solo con i primari Rec.709 (RP 219): con Rec.2020 diventano 75% bianco e 0% nero.
  -- Il -2% (sotto il nero) non entra in un'immagine a 8 bit 0-255 ed esce come 0%: il PLUGE si legge
  -- su +2% appena visibile e +4% visibile.
  local function ycc10(Y, Cb, Cr)          -- Y'CbCr 10 bit (BT.709, livelli video) -> R'G'B' 0..1
    local y, cb, cr = (Y - 64) / 876, (Cb - 512) / 896, (Cr - 512) / 896
    return { y + 1.5748 * cr, y - 0.187324 * cb - 0.468124 * cr, y + 1.8556 * cb }
  end
  M.ycc10 = ycc10
  function M.barsGeometry(W, H)
    local a = min(W, H * 16 / 9)
    local c = 3 * a / 28
    local d = (W - 7 * c) / 2
    local rows = { 0, floor(H * 7 / 12 + 0.5), floor(H * 8 / 12 + 0.5), floor(H * 9 / 12 + 0.5), H }
    return c, d, rows
  end
  function M.composeBars(W, H, spec)
    spec = spec or {}
    local cv = canvas(W, H)
    local c, d, rows = M.barsGeometry(W, H)
    local iq = (spec.prim ~= "2020")
    local function v8(rgb) return { floor(255 * max(0, min(1, rgb[1])) + 0.5), floor(255 * max(0, min(1, rgb[2])) + 0.5),
      floor(255 * max(0, min(1, rgb[3])) + 0.5) } end
    local function g(v) return { v, v, v } end
    -- una fila: elenco di { larghezza in unita' c (o "d" per i lati), colore R'G'B' 0..1 | "ramp" }
    local function row(r, list)
      local x = 0
      local y0, y1 = rows[r], rows[r + 1]
      for _, e in ipairs(list) do
        local wpx = (e[1] == "d") and d or e[1] * c
        local xa, xb = floor(x + 0.5), floor(x + wpx + 0.5)
        if e[2] == "ramp" then cv:ramp(xa, y0, xb, y1, { 0, 0, 0 }, { 255, 255, 255 })
        else
          local col = v8(e[2])
          cv:add(y0, y1 - 1, function(_, rw)
            for xx = max(0, xa), min(W, xb) - 1 do
              local i = xx * 4 + 1
              rw[i], rw[i + 1], rw[i + 2], rw[i + 3] = col[1], col[2], col[3], 255
            end
          end)
        end
        x = x + wpx
      end
    end
    local q = 0.75
    row(1, { { "d", g(0.4) }, { 1, g(q) }, { 1, { q, q, 0 } }, { 1, { 0, q, q } }, { 1, { 0, q, 0 } },
      { 1, { q, 0, q } }, { 1, { q, 0, 0 } }, { 1, { 0, 0, q } }, { "d", g(0.4) } })
    row(2, { { "d", { 0, 1, 1 } }, { 1, iq and ycc10(244, 612, 395) or g(q) }, { 6, g(q) }, { "d", { 0, 0, 1 } } })
    row(3, { { "d", { 1, 1, 0 } }, { 1, iq and ycc10(141, 697, 606) or g(0) }, { 5, "ramp" }, { 1, g(1) },
      { "d", { 1, 0, 0 } } })
    row(4, { { "d", g(0.15) }, { 1.5, g(0) }, { 2, g(1) }, { 5 / 6, g(0) }, { 1 / 3, g(-0.02) }, { 1 / 3, g(0) },
      { 1 / 3, g(0.02) }, { 1 / 3, g(0) }, { 1 / 3, g(0.04) }, { 1, g(0) }, { "d", g(0.15) } })
    return cv
  end
  function M.renderBars(path, W, H, spec)
    local ok, res = pcall(function() return M.composeBars(W, H, spec):write(path) end)
    if not ok then return false, tostring(res) end
    return res, nil
  end

  -- ------------------------------------------------------------ quadranti della slate
  -- Geometria (in pixel) dei quadranti di Quadrante (b) e Orologio (c): la stessa del generatore.
  -- Il PNG e' un quadrato di lato S con il quadrante al centro; nel generatore Size = S / larghezza.
  function M.dialGeometry(kind, W, H)
    local r = (kind == "b") and min(0.36 * H, 0.22 * W) or min(0.31 * H, 0.20 * W)
    local S = 2 * math.ceil(r * 1.04 + 2)
    return r, S
  end

  function M.composeDial(kind, W, H, spec)
    local R, S = M.dialGeometry(kind, W, H)
    local cv = canvas(S, S)
    local accent = c8(spec.accent or { 0.85, 0.85, 0.85 })
    local dim = function(k) return { floor(accent[1] * k + 0.5), floor(accent[2] * k + 0.5), floor(accent[3] * k + 0.5) } end
    local lw = max(1, floor(H / 1080 * 2 + 0.5))
    local cx, cy = S / 2, S / 2
    if kind == "b" then
      local fps = max(1, floor((spec.fps or 24) + 0.5))
      local ro, ri = R, R * 0.8
      local lgh = max(7, floor(R * 0.07 + 0.5))
      -- corona: settori alternati, uno per fotogramma del secondo, numerati
      local light, darkc = dim(0.55), { 18, 18, 18 }
      cv:add(cy - ro - 1, cy + ro + 1, function(y, row)
        local dy = y + 0.5 - cy
        for x = max(0, floor(cx - ro - 1)), min(S - 1, floor(cx + ro + 1)) do
          local dx = x + 0.5 - cx
          local dd = sqrt(dx * dx + dy * dy)
          local a = min(ro + 0.5 - dd, dd - ri + 0.5, 1)
          if a > 0 then
            local ang = (atan2(dx, -dy) / (2 * math.pi)) % 1
            local seg = floor(ang * fps + 0.5) % fps
            local c = (seg % 2 == 0) and darkc or light
            blend(row, x, c[1], c[2], c[3], a)
          end
        end
      end)
      cv:ring(cx, cy, ro, lw * 2, accent)
      cv:ring(cx, cy, ri, lw, accent)
      for k = 0, fps - 1 do
        local ang = 2 * math.pi * k / fps
        local rr = (ro + ri) / 2
        local tx, ty = cx + math.sin(ang) * rr, cy - math.cos(ang) * rr
        cv:text(string.format("%02d", k), tx, ty - lgh / 2, lgh, (k % 2 == 0) and WHITE or BLACK, "center")
      end
      cv:rect(cx - lw, cy - ri, cx + lw, cy - ri * 0.72, accent)          -- indice fisso in alto
    else
      local lgh = max(7, floor(R * 0.075 + 0.5))
      for k = 0, 59 do
        local ang = 2 * math.pi * k / 60
        local long = k % 5 == 0
        local r0 = R * (long and 0.86 or 0.92)
        local sx, sy = math.sin(ang), -math.cos(ang)
        cv:segment(cx + sx * r0, cy + sy * r0, cx + sx * R * 0.985, cy + sy * R * 0.985, max(0.8, lw * (long and 0.9 or 0.5)), accent)
        if long then
          local rt = R * 0.74
          cv:text(tostring(k == 0 and 60 or k), cx + sx * rt, cy + sy * rt - lgh / 2, lgh, dim(0.9), "center")
        end
      end
    end
    return cv
  end

  function M.renderDial(path, kind, W, H, spec)
    local ok, res = pcall(function() return M.composeDial(kind, W, H, spec):write(path) end)
    if not ok then return false, tostring(res) end
    return res, nil
  end

  function M.render(path, W, H, spec)
    local ok, res = pcall(function() return (M.compose(W, H, spec)):write(path) end)
    if not ok then return false, tostring(res) end
    return res, nil
  end

  return M
end)()
