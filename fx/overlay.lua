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
  -- stili del countdown: 0 Standard (leader SMPTE), 1 Ordinato (moduli raggruppati), 2 Moderno
  local RING_H, RING_W = { 0.62, 0.50, 0.56 }, { 0.40, 0.34, 0.36 }
  local function ringD(W, H, style)
    local k = (style or 0) + 1
    return min((RING_H[k] or 0.62) * H, (RING_W[k] or 0.40) * W)
  end
  M.ringD = ringD

  -- Moduli per zona (dall'esterno verso il cerchio) nelle posizioni del leader SMPTE RP 428-6: stelle
  -- di Siemens negli angoli esterni, due file di tre quadrati, due strisce vicino alla linea di centro.
  -- Al posto dei due volti (incarnati): ColorChecker e toni della pelle.
  local ZONES = {
    left = { A = { "star", "sphere", "peak" }, S = { "rampWR", "rampGB" }, B = { "star", "checker", "info" } },
    right = { A = { "star", "blue", "res" }, S = { "grey", "colors" }, B = { "star", "skin", "gamma" } },
  }

  -- Stili Ordinato e Moderno: stelle di Siemens negli angoli dell'area utile (il fuoco si legge sui
  -- bordi) e due gruppi compatti accanto al cerchio, ognuno con due file di due moduli e due strisce,
  -- con la didascalia sotto ogni modulo (e, nell'Ordinato, il titolo del gruppo). I moduli hanno una
  -- grandezza fissa in proporzione all'altezza (mai sotto i 40 px: le righe di 1 px restano leggibili).
  local CLUSTERS = {
    left = { title = "NITIDEZZA E GAMMA", Q = { "info", "res", "gamma", "sphere" }, S = { "rampWR", "rampGB" } },
    right = { title = "LIVELLI E COLORE", Q = { "peak", "blue", "checker", "skin" }, S = { "grey", "colors" } },
  }
  local CAPTIONS = { star = "FUOCO", sphere = "CONTOURING", peak = "BIANCO / NERO", info = "PIXEL 1:1",
    res = "NITIDEZZA / RGB", gamma = "GAMMA", blue = "BLU 47B", checker = "COLORCHECKER", skin = "INCARNATI",
    rampWR = "RAMPE", rampGB = "RAMPE", grey = "GRIGI / NERI 0-10%", colors = "SATURI / DESATURATI" }
  M.CAPTIONS = CAPTIONS

  function M.clusters(W, H, spec, out, ix0, iy0, ix1, iy1, m)
    local style = out.style
    local D, u = out.D, min(W, H)
    local gc = max(3, floor(0.035 * u + 0.5))
    local titled = style == 1
    -- stelle negli angoli dell'area utile
    local ss = max(40, floor((style == 1 and 0.10 or 0.075) * H + 0.5))
    ss = min(ss, floor((ix1 - ix0) * 0.12), floor((iy1 - iy0) * 0.25))
    local function put(kind, x, y, ww, hh, extra)
      local it = { kind = kind, x = floor(x + 0.5), y = floor(y + 0.5), w = floor(ww + 0.5), h = floor(hh + 0.5) }
      for k, v in pairs(extra or {}) do it[k] = v end
      out.items[#out.items + 1] = it
      return it
    end
    if ss >= 24 then
      put("star", ix0 + m, iy0 + m, ss, ss); put("star", ix1 - m - ss, iy0 + m, ss, ss)
      put("star", ix0 + m, iy1 - m - ss, ss, ss); put("star", ix1 - m - ss, iy1 - m - ss, ss, ss)
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
    if style ~= 0 then return M.clusters(W, H, spec, out, ix0, iy0, ix1, iy1, m) end
    local function zone(name, x0, x1)
      local y0, y1 = iy0 + m, iy1 - m
      local w, h = x1 - x0, y1 - y0
      if w < 0.08 * u or h < 0.25 * u then return end
      local g, sr = 0.12, 0.5
      -- moduli contenuti (al massimo il 15% dell'altezza): si raggruppano invece di riempire la zona
      local s3 = min(w / (3 + 2 * g), (h - midgap) / (2 + 2 * sr + 2 * g), 0.15 * H)
      local s1 = min(w, (h - midgap) / (6 + 2 * sr + 6 * g), 0.15 * H)
      local cols = (s1 > 1.35 * s3) and 1 or 3
      local s = floor(cols == 3 and s3 or s1)
      if s < 24 then return end
      local gs = max(2, floor(g * s + 0.5))
      -- strisce piu' alte se c'e' spazio (fino a 0.8 del modulo)
      local rows = (cols == 3) and 2 or 6
      local sh = floor(min(0.62 * s, (h - midgap - rows * s - (rows + 2) * gs) / 2) + 0.5)
      sh = max(sh, floor(sr * s + 0.5))
      local Z = ZONES[name]
      local ym = floor((y0 + y1) / 2 + 0.5)
      local left = name == "left"
      local function put(kind, x, y, ww, hh)
        out.items[#out.items + 1] = { kind = kind, x = floor(x + 0.5), y = floor(y + 0.5), w = ww, h = hh, zone = name }
      end
      if cols == 3 then
        local cw = 3 * s + 2 * gs
        local xs = x0 + floor((w - cw) / 2 + 0.5)
        for k = 1, 3 do
          local x = left and (xs + (k - 1) * (s + gs)) or (xs + cw - s - (k - 1) * (s + gs))
          put(Z.A[k], x, y0, s, s)
          put(Z.B[k], x, y1 - s, s, s)
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

  -- ------------------------------------------------------------ moduli
  local WHITE, BLACK = { 255, 255, 255 }, { 0, 0, 0 }
  local INK = { 16, 16, 16 }
  local RGBCMY = { { 255, 0, 0 }, { 0, 255, 0 }, { 0, 0, 255 }, { 255, 255, 0 }, { 0, 255, 255 }, { 255, 0, 255 } }

  -- testo allineato a sinistra ridotto fino a stare in w
  local function fitLeft(cv, s, x, y, gh, w, c)
    while textWidth(s, gh) > w and gh > 5 do gh = gh * 0.92 end
    cv:text(s, x, y, gh, c)
    return gh
  end

  local MODULES = {}
  -- stelle di Siemens (fuoco): il disco grigio al centro, dove i raggi si fondono, deve essere il piu'
  -- piccolo possibile, rotondo e uguale nei quattro angoli (planarita' del fuoco); frange rosse o blu
  -- sui raggi = convergenza RGB
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
  function MODULES.peak(cv, x, y, s, p, ctx)
    local iw = s - 2 * p
    local hh = floor(iw / 2)
    cv:rect(x + p, y + p, x + s - p, y + p + hh, WHITE)
    cv:rect(x + p, y + p + hh, x + s - p, y + s - p, BLACK)
    local q = floor(hh * 0.56)
    local cx = x + s / 2
    local cw, cb = y + p + hh / 2, y + p + hh + (iw - hh) / 2
    cv:rect(cx - q / 2, cw - q / 2, cx + q / 2, cw + q / 2, { 242, 242, 242 })
    cv:rect(cx - q / 2, cb - q / 2, cx + q / 2, cb + q / 2, { 13, 13, 13 })
  end
  -- fotogrammi al secondo e risoluzione della timeline (come "24 / SEC · 2K" del leader SMPTE, che
  -- esiste per ogni frame rate e in 2K e 4K) e triangolo di righe di 1 px annidate, orizzontali e
  -- verticali, alla risoluzione nativa: con la mappatura 1:1 dei pixel ogni riga e' netta e uniforme;
  -- moire', righe doppie o un grigio piatto = il monitor o il proiettore sta scalando l'immagine
  function MODULES.info(cv, x, y, s, p, ctx)
    local iw = s - 2 * p
    local band = floor(0.27 * iw)
    local x0, y0 = x + p, y + p
    cv:rect(x0, y0, x0 + iw, y0 + band, { 118, 118, 118 })
    cv:rect(x0, y0 + band, x0 + iw, y0 + iw, { 196, 196, 196 })
    if ctx.cal.labels then
      fitText(cv, ctx.fpsLabel or "", x0 + iw / 2, y0 + band * 0.22, floor(band * 0.56), iw * 0.88, INK)
      local g2 = fitLeft(cv, ctx.resLabel or "", x0 + 0.08 * iw, y0 + band + 0.09 * iw, floor(0.2 * iw), iw * 0.6, INK)
      fitLeft(cv, string.format("%dx%d", ctx.W, ctx.H), x0 + 0.08 * iw, y0 + band + 0.09 * iw + g2 * 1.4,
        floor(0.07 * iw), iw * 0.5, { 60, 60, 60 })
    end
    if ctx.cal.diag then
      local t = floor((iw - band) * 0.8)
      cv:nested(x0 + iw - t, y0 + iw - t, t, "br", WHITE, BLACK)
    end
  end
  -- nitidezza e scalatura: righe di 1, 2, 3, 4 px verticali e orizzontali; sotto righe di 1 px rosse,
  -- verdi e blu (registrazione dei pannelli, sottocampionamento del colore): ognuna netta e pura
  function MODULES.res(cv, x, y, s, p, ctx)
    local iw = s - 2 * p
    local gh = max(6, floor(0.08 * s))
    local lh = floor(gh * 1.6)
    local gap = max(1, floor(0.03 * s))
    local cw = (iw - 3 * gap) / 4
    local rh = floor((s - 2 * p - lh - 3 * gap) / 3)
    local y1 = y + p + lh
    for k = 1, 4 do
      local gx = x + p + (k - 1) * (cw + gap)
      fitText(cv, tostring(k), gx + cw / 2, y + p + (lh - gh) / 2, gh, cw, ctx.accent)
      cv:grating(gx, y1, gx + cw, y1 + rh, k, true, WHITE, BLACK)
      cv:grating(gx, y1 + rh + gap, gx + cw, y1 + 2 * rh + gap, k, false, WHITE, BLACK)
    end
    local y2 = y1 + 2 * (rh + gap)
    local half = x + p + floor(iw / 2)
    cv:pattern(x + p, y2, half - gap, y + s - p, function(dx)
      local c = RGBCMY[dx % 3 + 1]
      return c[1], c[2], c[3]
    end)
    cv:pattern(half + gap, y2, x + s - p, y + s - p, function(_, dy)
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
  -- ColorChecker 24: resa del colore, incarnati (le prime due toppe) e scala neutra
  function MODULES.checker(cv, x, y, s, p, ctx)
    local iw = s - 2 * p
    local pitch = iw / 6
    local ps = max(2, floor(pitch * 0.86))
    local gy = y + p + (iw - 4 * pitch) / 2
    for i, c in ipairs(CHECKER) do
      local col, row = (i - 1) % 6, floor((i - 1) / 6)
      local px, py = x + p + col * pitch + (pitch - ps) / 2, gy + row * pitch + (pitch - ps) / 2
      cv:rect(px, py, px + ps, py + ps, c)
    end
  end
  -- toni della pelle (al posto dei volti del leader SMPTE): i 10 toni della scala Monk, dal piu'
  -- chiaro al piu' scuro; devono restare distinti e naturali, senza dominanti
  function MODULES.skin(cv, x, y, s, p, ctx)
    local iw = s - 2 * p
    local pitch = iw / 5
    local ps = max(2, floor(pitch * 0.88))
    local gy = y + p + (iw - 2 * pitch) / 2
    for i, hex in ipairs(SKIN) do
      local col, row = (i - 1) % 5, floor((i - 1) / 5)
      local c = { tonumber(hex:sub(1, 2), 16), tonumber(hex:sub(3, 4), 16), tonumber(hex:sub(5, 6), 16) }
      local px, py = x + p + col * pitch + (pitch - ps) / 2, gy + row * pitch + (pitch - ps) / 2
      cv:rect(px, py, px + ps, py + ps, c)
    end
  end
  -- verifica del gamma (come "2,6 γ" del leader SMPTE, qui con il gamma dello spazio colore del
  -- progetto): triangolo di righe alterne di 1 px nero / bianco (luce media 50%) su un grigio pari a
  -- 0.5^(1/γ). Al 100% e da lontano le righe devono sparire nel grigio; in alto i grigi dei gamma
  -- vicini: se le righe somigliano a quello a sinistra il gamma del display e' piu' basso, a destra piu' alto
  function MODULES.gamma(cv, x, y, s, p, ctx)
    local iw = s - 2 * p
    local x0, y0 = x + p, y + p
    local band = floor(0.24 * iw)
    local g = ctx.gamma or 2.4
    local vl, vh, vg = M.gammaPatch(g - 0.2), M.gammaPatch(g + 0.2), M.gammaPatch(g)
    cv:rect(x0, y0, x0 + floor(iw / 2), y0 + band, { vl, vl, vl })
    cv:rect(x0 + floor(iw / 2), y0, x0 + iw, y0 + band, { vh, vh, vh })
    local gh = max(6, floor(band * 0.4))
    fitText(cv, string.format("%.1f", g - 0.2), x0 + iw / 4, y0 + (band - gh) / 2, gh, iw * 0.36, INK)
    fitText(cv, string.format("%.1f", g + 0.2), x0 + 3 * iw / 4, y0 + (band - gh) / 2, gh, iw * 0.36, INK)
    cv:rect(x0, y0 + band, x0 + iw, y0 + iw, { vg, vg, vg })
    local t = iw - band
    cv:nested(x0, y0 + iw - t, t, "bl", WHITE, BLACK)
    local lab = string.format("%.1f", g)
    local g2 = floor(0.17 * iw)
    while textWidth(lab, g2) > iw * 0.4 and g2 > 6 do g2 = g2 * 0.92 end
    local lx = x0 + iw * 0.95 - textWidth(lab, g2) / 2
    cv:text(lab, lx, y0 + band + 0.07 * iw, g2, INK, "center")
    cv:text("~", lx, y0 + band + 0.07 * iw + g2 * 1.35, g2, INK, "center")
  end

  -- strisce (rampe continue, scale di grigi, colori a due livelli)
  local STRIPS = {}
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
  -- colori saturi (in alto) e desaturati (in basso, 70% di saturazione): i saturi mostrano il bordo
  -- della gamma, i desaturati tinta e matrice del colore dentro la gamma
  function STRIPS.colors(cv, x, y, w, h, p)
    local hh = floor((h - 2 * p) / 2)
    local iw = w - 2 * p
    for i, c in ipairs(RGBCMY) do
      local x0, x1 = x + p + iw * (i - 1) / 6, x + p + iw * i / 6
      cv:rect(x0, y + p, x1, y + p + hh, c)
      cv:rect(x0, y + p + hh, x1, y + h - p, { floor(c[1] + (255 - c[1]) * 0.3 + 0.5),
        floor(c[2] + (255 - c[2]) * 0.3 + 0.5), floor(c[3] + (255 - c[3]) * 0.3 + 0.5) })
    end
  end
  local ENABLED = { star = "stars", sphere = "contour", peak = "peak", gamma = "gamma", res = "res", blue = "blue",
    checker = "checker", skin = "skin", rampWR = "ramps", rampGB = "ramps", grey = "grey", colors = "color" }

  -- bordo del raster (1 px esatto), angoli e scale dei bordi (overscan / mascherini: tacche ogni 1%,
  -- numeri ogni 2%) a meta' dei lati; in alto e in basso solo se logo e dati non occupano il centro
  local function edges(cv, W, H, spec, accent, lw, LAY)
    local u = min(W, H)
    cv:frame(0, 0, W, H, 1, WHITE)
    local L = max(6, floor(0.03 * u + 0.5))
    cv:corner(0, 0, 1, 1, L, WHITE); cv:corner(W, 0, -1, 1, L, WHITE)
    cv:corner(0, H, 1, -1, L, WHITE); cv:corner(W, H, -1, -1, L, WHITE)
    local gh = max(6, floor(min(0.014 * H, 0.0105 * W) + 0.5))       -- numeri distanti 2% della larghezza
    local tl, ts = max(6, floor(0.03 * H + 0.5)), max(3, floor(0.016 * H + 0.5))
    -- scale a meta' dei lati solo se non toccano i moduli
    local clear = true
    for _, it in ipairs((LAY and LAY.items) or {}) do
      if it.x < W * 0.105 + 4 and it.x + it.w > 0 and it.y < H / 2 + tl and it.y + it.h > H / 2 - tl then clear = false end
    end
    for k = 1, clear and 10 or 0 do
      local t = (k % 2 == 0) and tl or ts
      for _, side in ipairs({ 1, -1 }) do
        local xk = (side > 0) and floor(W * k / 100 + 0.5) or (W - floor(W * k / 100 + 0.5))
        cv:rect(xk - lw / 2, H / 2 - t / 2, xk + lw / 2, H / 2 + t / 2, accent)
        -- numeri ogni 2%; se non ci stanno solo 2, 6, 10 (come nel leader SMPTE)
        local lab = (k % 2 == 0) and (W * 0.02 >= textWidth("10%", gh) * 1.15 or k % 4 == 2)
        if lab then cv:text(k == 10 and "10%" or tostring(k), xk, H / 2 + tl / 2 + 2, gh, accent, "center") end
      end
    end
    local vt, vs = max(6, floor(0.03 * W * min(1, H / W * 1.78) + 0.5)), 0
    vs = max(3, floor(vt * 0.53 + 0.5))
    for k = 1, 10 do
      local t = (k % 2 == 0) and vt or vs
      for _, side in ipairs({ 1, -1 }) do
        if (side > 0 and not spec.cdLogo) or (side < 0 and not spec.cdInfo) then
          local yk = (side > 0) and floor(H * k / 100 + 0.5) or (H - floor(H * k / 100 + 0.5))
          cv:rect(W / 2 - t / 2, yk - lw / 2, W / 2 + t / 2, yk + lw / 2, accent)
          if k % 2 == 0 then cv:text(k == 10 and "10%" or tostring(k), W / 2 + vt / 2 + 3, yk - gh / 2, gh, accent) end
        end
      end
    end
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
  function M.compose(W, H, spec)
    local cv = canvas(W, H)
    local accent = c8(spec.accent or { 0.85, 0.85, 0.85 })
    local border = { floor(accent[1] * 0.85 + 0.5), floor(accent[2] * 0.85 + 0.5), floor(accent[3] * 0.85 + 0.5) }
    local lw = max(1, floor(H / 1080 * 2 + 0.5))
    local cal = spec.cal or {}
    local style = spec.style or 0
    local L = M.layout(W, H, spec)
    if cal.edge then edges(cv, W, H, spec, accent, lw, L) end
    local blw = (style == 2) and 1 or lw
    if style == 2 then border = { floor(accent[1] * 0.45 + 0.5), floor(accent[2] * 0.45 + 0.5), floor(accent[3] * 0.45 + 0.5) } end
    local ctx = { cal = cal, accent = accent, fpsLabel = spec.fpsLabel, resLabel = spec.resLabel, W = W, H = H,
      gamma = spec.gamma }
    local capc = (style == 2) and { floor(accent[1] * 0.6), floor(accent[2] * 0.6), floor(accent[3] * 0.6) } or accent
    for _, it in ipairs(L.items) do
      if it.kind == "title" then
        local gh = max(6, it.h)
        while textWidth(it.text, gh) > it.w and gh > 6 do gh = gh * 0.92 end
        cv:text(it.text, it.x, it.y, gh, accent)
      else
        local on = (it.kind == "info") and (cal.labels or cal.diag) or cal[ENABLED[it.kind]]
        if on then
          local s = it.w
          cv:rect(it.x, it.y, it.x + it.w, it.y + it.h, BLACK)
          cv:frame(it.x, it.y, it.x + it.w, it.y + it.h, blw, border)
          local p = blw + max(1, floor(0.05 * min(it.w, it.h) + 0.5))
          if MODULES[it.kind] then MODULES[it.kind](cv, it.x, it.y, s, p, ctx)
          else STRIPS[it.kind](cv, it.x, it.y, it.w, it.h, p) end
          if it.caption then
            local text = (it.kind == "gamma") and string.format("GAMMA %.1f", ctx.gamma or 2.4) or it.caption
            local gh = max(6, floor(min(it.h, it.w) * ((style == 2) and 0.085 or 0.1) + 0.5))
            if it.h < it.w then gh = max(6, floor(it.h * 0.2 + 0.5)) end
            while textWidth(text, gh) > it.w and gh > 5 do gh = gh * 0.92 end
            -- se non sta nel modulo nemmeno a 5 px non si scrive (niente didascalie accavallate)
            if textWidth(text, gh) <= it.w + 1 then cv:text(text, it.x, it.y + it.h + max(2, floor(gh * 0.6)), gh, capc) end
          end
        end
      end
    end
    -- Moderno: 60 tacche attorno al cerchio del countdown (5 lunghe ogni 5 secondi di quadrante)
    if style == 2 then
      local R = L.D / 2
      local tc = { floor(accent[1] * 0.55), floor(accent[2] * 0.55), floor(accent[3] * 0.55) }
      for k = 0, 59 do
        local a = 2 * math.pi * k / 60
        local long = k % 5 == 0
        local r0, r1 = R * 1.035, R * (long and 1.1 or 1.065)
        local sx, sy = math.sin(a), -math.cos(a)
        cv:segment(W / 2 + sx * r0, H / 2 + sy * r0, W / 2 + sx * r1, H / 2 + sy * r1, max(0.6, lw * (long and 0.6 or 0.35)), tc)
      end
    end
    if cal.center and style ~= 2 then
      local a = floor(0.012 * min(W, 1.78 * H))
      cv:frame(floor(W / 2 - a), floor(H / 2 - a), floor(W / 2 + a), floor(H / 2 + a), lw, accent)
      local b = floor(a / 2.5)
      cv:frame(floor(W / 2 - b), floor(H / 2 - b), floor(W / 2 + b), floor(H / 2 + b), lw, accent)
      for _, d in ipairs({ { 1, 1 }, { 1, -1 } }) do                      -- asterisco (le croci sono del generatore)
        cv:segment(W / 2 - d[1] * b * 0.7, H / 2 - d[2] * b * 0.7, W / 2 + d[1] * b * 0.7, H / 2 + d[2] * b * 0.7,
          max(0.6, lw * 0.5), accent)
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
