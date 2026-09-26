-- LeaderKit overlay: immagini statiche (PNG RGBA) alla risoluzione esatta della timeline.
-- Taratura e quadranti delle slate sono disegnati pixel per pixel e salvati una sola
-- volta; su timeline stanno sopra il leader come still. Frame lines e safe area sono
-- invece nel generatore (sotto i testi).
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

  -- stella di Siemens (fuoco): settori bianchi/neri con antialiasing 3x3
  function Canvas:star(cx, cy, rad, spokes, cw, cb)
    local r2 = rad * rad
    local x0, x1 = max(0, floor(cx - rad)), min(self.W - 1, floor(cx + rad))
    local sub = { -1 / 3, 0, 1 / 3 }
    local k = spokes / math.pi
    self:add(cy - rad, cy + rad, function(y, row)
      for x = x0, x1 do
        local inside, white = 0, 0
        for _, sy in ipairs(sub) do
          local dy = y + 0.5 + sy - cy
          for _, sx in ipairs(sub) do
            local dx = x + 0.5 + sx - cx
            if dx * dx + dy * dy <= r2 then
              inside = inside + 1
              if floor((atan2(dy, dx) + math.pi) * k) % 2 == 0 then white = white + 1 end
            end
          end
        end
        if inside > 0 then
          local wf = white / inside
          blend(row, x, floor(cb[1] + (cw[1] - cb[1]) * wf + 0.5), floor(cb[2] + (cw[2] - cb[2]) * wf + 0.5),
            floor(cb[3] + (cw[3] - cb[3]) * wf + 0.5), inside / 9)
        end
      end
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

  -- ------------------------------------------------------------ composizione
  -- spec: { accent = {r,g,b} 0..1, cal = { stars, center, grey, color, ramps, blue, contour, peak, labels },
  --         fpsLabel, resLabel, dialB / dialC = { cx, cy, r, fps } }
  function M.compose(W, H, spec)
    local cv = canvas(W, H)
    local accent = c8(spec.accent or { 0.85, 0.85, 0.85 })
    local dim = function(k) return { floor(accent[1] * k + 0.5), floor(accent[2] * k + 0.5), floor(accent[3] * k + 0.5) } end
    local lw = max(1, floor(H / 1080 * 2 + 0.5))
    local cal = spec.cal
    local WHITE, BLACK = { 255, 255, 255 }, { 0, 0, 0 }

    -- quadranti della slate (stili Quadrante e Orologio)
    if spec.dialB then
      local d = spec.dialB
      local cx, cy, R = d.cx * W, d.cy * H, d.r * H
      local fps = max(1, floor(d.fps + 0.5))
      local ro, ri = R, R * 0.8
      local lgh = max(8, floor(R * 0.07 + 0.5))
      -- corona: settori alternati, uno per fotogramma del secondo, numerati
      local x0, x1 = max(0, floor(cx - ro - 1)), min(W - 1, floor(cx + ro + 1))
      local light, darkc = dim(0.55), { 18, 18, 18 }
      cv:add(cy - ro - 1, cy + ro + 1, function(y, row)
        local dy = y + 0.5 - cy
        for x = x0, x1 do
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
        local c = (k % 2 == 0) and WHITE or BLACK
        cv:text(string.format("%02d", k), tx, ty - lgh / 2, lgh, c, "center")
      end
      -- indice fisso in alto
      cv:rect(cx - lw, cy - ri, cx + lw, cy - ri * 0.72, accent)
    end
    if spec.dialC then
      local d = spec.dialC
      local cx, cy, R = d.cx * W, d.cy * H, d.r * H
      local lgh = max(8, floor(R * 0.075 + 0.5))
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

    if cal then
      -- pannelli ai lati del cerchio del countdown (diametro 0.36 W)
      local py0, py1 = floor(0.22 * H), floor(0.78 * H)
      local boxes = { { floor(0.025 * W), floor(0.30 * W) }, { W - floor(0.30 * W), W - floor(0.025 * W) } }
      local VW, VH = 100, 112
      local P = {}
      for i, bx in ipairs(boxes) do
        cv:rect(bx[1], py0, bx[2], py1, { 15, 15, 15 })
        cv:frame(bx[1], py0, bx[2], py1, lw, dim(0.8))
        local pw, ph = bx[2] - bx[1], py1 - py0
        local s = min(pw / VW, ph / VH) * 0.92
        local ox, oy = bx[1] + (pw - VW * s) / 2, py0 + (ph - VH * s) / 2
        P[i] = function(x, y) return ox + x * s, oy + y * s end
        P[i .. "s"] = s
      end
      local L, R, s = P[1], P[2], P["1s"]
      local function box(F, x0, y0, x1, y1, c)
        local a, b = F(x0, y0); local cc, d = F(x1, y1); cv:rect(a, b, cc, d, c)
      end
      -- sinistra: sfera, bianco di picco, nero (PLUGE), rampe, etichette
      if cal.contour then local x, y = L(20, 20); cv:sphere(x, y, 15 * s) end
      if cal.peak then
        box(L, 40, 5, 60, 35, WHITE)
        box(L, 65, 5, 95, 35, BLACK)
        box(L, 69, 9, 75, 31, { 5, 5, 5 }); box(L, 78, 9, 84, 31, { 10, 10, 10 }); box(L, 87, 9, 93, 31, { 20, 20, 20 })
      end
      if cal.ramps then
        for i, c in ipairs({ { 255, 255, 255 }, { 255, 0, 0 }, { 0, 255, 0 }, { 0, 0, 255 } }) do
          local y0 = 42 + (i - 1) * 14
          local ax, ay = L(5, y0); local bx, by = L(95, y0 + 10)
          cv:ramp(ax, ay, bx, by, { 0, 0, 0 }, c)
        end
      end
      if cal.labels then
        for i, lab in ipairs({ spec.fpsLabel or "", spec.resLabel or "" }) do
          local x0 = (i == 1) and 5 or 53
          local ax, ay = L(x0, 99); local bx, by = L(x0 + 42, 111)
          cv:frame(floor(ax), floor(ay), floor(bx), floor(by), lw, accent)
          local gh = 5 * s
          while textWidth(lab, gh) > (bx - ax) * 0.86 and gh > 6 do gh = gh * 0.9 end
          cv:text(lab, (ax + bx) / 2, (ay + by) / 2 - gh / 2, gh, WHITE, "center")
        end
      end
      -- destra: verifica del blu, bianchi vicini al clip, scala di grigi, colori, formato
      if cal.blue then
        box(R, 5, 5, 20, 20, { 255, 0, 255 }); box(R, 20, 5, 35, 20, { 0, 255, 255 })
        box(R, 5, 20, 20, 35, WHITE); box(R, 20, 20, 35, 35, { 0, 0, 255 })
      end
      if cal.peak then
        box(R, 40, 5, 95, 35, WHITE)
        box(R, 44, 9, 54, 31, { 235, 235, 235 }); box(R, 60, 9, 70, 31, { 245, 245, 245 })
        box(R, 76, 9, 86, 31, { 250, 250, 250 })
      end
      if cal.grey then
        for i = 0, 10 do
          local v = floor(i * 25.5 + 0.5)
          box(R, 5 + i * 90 / 11, 42, 5 + (i + 1) * 90 / 11, 56, { v, v, v })
        end
      end
      if cal.color then
        local cols = { { 255, 0, 0 }, { 0, 255, 0 }, { 0, 0, 255 }, { 255, 255, 0 }, { 0, 255, 255 }, { 255, 0, 255 } }
        for i, c in ipairs(cols) do box(R, 5 + (i - 1) * 15, 62, 5 + i * 15 - 1, 80, c) end
      end
      if cal.labels then
        local gh = 4.2 * s
        local x, y = R(50, 88)
        cv:text(string.format("%d x %d", W, H), x, y, gh, accent, "center")
        x, y = R(50, 100)
        cv:text(string.format("%.2f:1", W / H), x, y, gh, accent, "center")
      end
      -- griglie di risoluzione sopra e sotto i pannelli: righe di 1, 2, 3, 4 pixel,
      -- verticali (fila in alto) e orizzontali (fila in basso). Al 100% devono essere nette:
      -- se le righe da 1 px si impastano l'immagine e' stata scalata o e' morbida.
      if cal.stars then
        local sq = floor(0.042 * H + 0.5)
        local gap = floor(0.008 * H + 0.5)
        local lgh = max(8, floor(0.016 * H + 0.5))
        local wTot = 4 * sq + 3 * gap
        local hTot = lgh + gap + 2 * sq + gap
        for _, p in ipairs({ { 0.25, 0.115 }, { 0.75, 0.115 }, { 0.25, 0.885 }, { 0.75, 0.885 } }) do
          local x0 = floor(p[1] * W - wTot / 2 + 0.5)
          local y0 = floor(p[2] * H - hTot / 2 + 0.5)
          cv:rect(x0 - gap, y0 - gap, x0 + wTot + gap, y0 + hTot + gap, BLACK)
          cv:frame(x0 - gap, y0 - gap, x0 + wTot + gap, y0 + hTot + gap, lw, dim(0.6))
          for k = 1, 4 do
            local gx = x0 + (k - 1) * (sq + gap)
            cv:text(tostring(k), gx + sq / 2, y0, lgh, accent, "center")
            local gy = y0 + lgh + gap
            cv:grating(gx, gy, gx + sq, gy + sq, k, true, WHITE, BLACK)
            cv:grating(gx, gy + sq + gap, gx + sq, gy + 2 * sq + gap, k, false, WHITE, BLACK)
          end
        end
      end
      if cal.center then
        local a = floor(0.012 * W)
        cv:frame(floor(W / 2 - a), floor(H / 2 - a), floor(W / 2 + a), floor(H / 2 + a), lw, accent)
        local b = floor(a / 2.5)
        cv:frame(floor(W / 2 - b), floor(H / 2 - b), floor(W / 2 + b), floor(H / 2 + b), lw, accent)
      end
    end

    return cv
  end

  function M.render(path, W, H, spec)
    local ok, res = pcall(function() return M.compose(W, H, spec):write(path) end)
    if not ok then return false, tostring(res) end
    return res, nil
  end

  return M
end)()
