#!/usr/bin/env python3
"""Anteprima approssimata dei generatori LeaderKit (senza Fusion).

Valuta le espressioni con lua5.4 (tests/lua_dump.lua) e disegna i nodi usati
da LeaderKit (Background, maschere, Merge, Transform, Text+) con Pillow.
Serve a controllare impaginazione e proporzioni: i font e alcuni dettagli
differiscono da Fusion.

    python3 tools/preview_fx.py "dist/LeaderKit.setting" --fps 24 --size 1920x1080 \\
        --frames 432 --t 300 -o preview.png [Chiave=valore ...]
"""

import argparse
import json
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def num(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def pt(v, d=(0.5, 0.5)):
    if isinstance(v, list) and len(v) >= 2:
        return float(v[0]), float(v[1])
    return d


class Renderer(object):
    def __init__(self, data, w, h):
        self.tools = data["tools"]
        self.w, self.h = w, h
        self.cache = {}
        yy, xx = np.mgrid[0:h, 0:w]
        self.xn = (xx + 0.5) / w                 # 0..1 da sinistra
        self.yn = 1.0 - (yy + 0.5) / h           # 0..1 dal basso (come Fusion)

    def inp(self, tool, key, default=None):
        return self.tools[tool]["inputs"].get(key, default)

    def link(self, tool, key):
        v = self.inp(tool, key)
        return v["link"] if isinstance(v, dict) and "link" in v else None

    # --- maschere (alpha 0..1)
    def mask(self, name):
        if ("m", name) in self.cache:
            return self.cache[("m", name)]
        t = self.tools[name]
        kind = t["kind"]
        cx, cy = pt(self.inp(name, "Center"))
        mw, mh = num(self.inp(name, "Width"), 0.5), num(self.inp(name, "Height"), 0.5)
        ang = math.radians(num(self.inp(name, "Angle"), 0))
        # coordinate in unita' di larghezza, centrate
        dx = (self.xn - cx)
        dy = (self.yn - cy) * self.h / self.w
        rx = dx * math.cos(-ang) - dy * math.sin(-ang)
        ry = dx * math.sin(-ang) + dy * math.cos(-ang)
        solid = num(self.inp(name, "Solid"), 1) > 0.5
        bw = num(self.inp(name, "BorderWidth"), 0)
        if kind == "EllipseMask":
            d = np.sqrt((rx / (mw / 2 + 1e-9)) ** 2 + (ry / (mh / 2 + 1e-9)) ** 2)
            inside = d <= 1
            if not solid:
                inner = np.sqrt((rx / max(mw / 2 - bw, 1e-9)) ** 2 + (ry / max(mh / 2 - bw, 1e-9)) ** 2) <= 1
                inside = inside & ~inner
        else:
            # come in Resolve (verificato su timeline 2:1): l'altezza dei RectangleMask e'
            # relativa all'altezza dell'immagine, la larghezza alla larghezza
            mh = mh * self.h / self.w
            inside = (np.abs(rx) <= mw / 2) & (np.abs(ry) <= mh / 2)
            if not solid:
                inner = (np.abs(rx) <= mw / 2 - bw) & (np.abs(ry) <= mh / 2 - bw)
                inside = inside & ~inner
        a = inside.astype(np.float32)
        soft = num(self.inp(name, "SoftEdge"), 0)
        if soft > 0:
            img = Image.fromarray((a * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(soft * self.w / 2))
            a = np.asarray(img).astype(np.float32) / 255
        prev = self.link(name, "EffectMask")
        if prev:
            a = np.maximum(a, self.mask(prev))
        self.cache[("m", name)] = a
        return a

    # --- immagini RGBA premoltiplicate
    def image(self, name):
        if ("i", name) in self.cache:
            return self.cache[("i", name)]
        t = self.tools[name]
        kind = t["kind"]
        out = np.zeros((self.h, self.w, 4), np.float32)
        if kind == "Background":
            c = [num(self.inp(name, "TopLeft" + ch), 0) for ch in ("Red", "Green", "Blue", "Alpha")]
            typ = self.inp(name, "Type")
            if typ == "Horizontal":
                c2 = [num(self.inp(name, "TopRight" + ch), 0) for ch in ("Red", "Green", "Blue", "Alpha")]
                f = self.xn[..., None]
                col = np.array(c) * (1 - f) + np.array(c2) * f
            else:
                col = np.broadcast_to(np.array(c, np.float32), (self.h, self.w, 4)).copy()
            m = self.link(name, "EffectMask")
            a = col[..., 3] * (self.mask(m) if m else 1.0)
            out[..., :3] = col[..., :3] * a[..., None]
            out[..., 3] = a
        elif kind == "TextPlus":
            out = self.text(name)
        elif kind == "Merge":
            bg = self.link(name, "Background")
            fg = self.link(name, "Foreground")
            b = self.image(bg) if bg else out
            f = self.image(fg) if fg else out
            k = num(self.inp(name, "Blend"), 1.0)
            out = b * (1 - f[..., 3:4] * k) + f * k
        elif kind == "Dissolve":
            k = num(self.inp(name, "Mix"), 0.0)
            bg = self.link(name, "Background")
            fg = self.link(name, "Foreground")
            if k <= 0:
                out = self.image(bg) if bg else out
            elif k >= 1:
                out = self.image(fg) if fg else out
            else:
                out = self.image(bg) * (1 - k) + self.image(fg) * k
        elif kind == "Transform":
            src = self.image(self.link(name, "Input"))
            cx, cy = pt(self.inp(name, "Center"))
            px, py = pt(self.inp(name, "Pivot"))
            ang = num(self.inp(name, "Angle"), 0)
            img = Image.fromarray((np.clip(src, 0, 1) * 255).astype(np.uint8), "RGBA")
            ppx, ppy = px * self.w, (1 - py) * self.h
            img = img.rotate(ang, resample=Image.BICUBIC, center=(ppx, ppy))
            ox, oy = (cx - 0.5) * self.w, -(cy - 0.5) * self.h
            canvas = Image.new("RGBA", img.size, (0, 0, 0, 0))
            canvas.paste(img, (int(round(ox)), int(round(oy))))
            out = np.asarray(canvas).astype(np.float32) / 255
        self.cache[("i", name)] = out
        return out

    def text(self, name):
        s = str(self.inp(name, "StyledText", "") or "")
        out = np.zeros((self.h, self.w, 4), np.float32)
        if not s.strip():
            return out
        size = num(self.inp(name, "Size"), 0.08)
        bold = (self.inp(name, "Style") or "Bold") != "Regular"
        font = ImageFont.truetype(FONTS[0] if bold else FONTS[1], max(6, int(size * self.w * 0.55)))
        cx, cy = pt(self.inp(name, "Center"))
        spacing = num(self.inp(name, "LineSpacing"), 1.0)
        img = Image.new("L", (self.w, self.h), 0)
        d = ImageDraw.Draw(img)
        lines = s.split("\n")
        lh = font.size * 1.2 * spacing
        total = lh * len(lines)
        y0 = (1 - cy) * self.h - total / 2
        for i, line in enumerate(lines):
            tw = d.textlength(line, font=font)
            d.text((cx * self.w - tw / 2, y0 + i * lh), line, fill=255, font=font)
        a = np.asarray(img).astype(np.float32) / 255
        col = [num(self.inp(name, ch), 1) for ch in ("Red1", "Green1", "Blue1")]
        out[..., 0], out[..., 1], out[..., 2] = a * col[0], a * col[1], a * col[2]
        out[..., 3] = a
        return out


def dump(setting, fps, w, h, frames, t, extra):
    cmd = ["lua5.4", os.path.join(ROOT, "tests", "lua_dump.lua"), setting, str(fps), str(w), str(h),
           str(frames), str(t)] + list(extra)
    return json.loads(subprocess.check_output(cmd).decode())


def render(setting, fps=24, w=1920, h=1080, frames=432, t=0, extra=(), scale=1.0):
    data = dump(setting, fps, w, h, frames, t, extra)
    rw, rh = int(w * scale), int(h * scale)
    r = Renderer(data, rw, rh)
    img = r.image(data["output"])
    # sotto: grigio-blu dove l'uscita e' trasparente (per vedere burn-in e mascherino)
    under = np.array([0.27, 0.35, 0.47], dtype=np.float32)
    rgb = np.clip(img[..., :3] + (1 - img[..., 3:4]) * under, 0, 1)
    return Image.fromarray((rgb * 255).astype(np.uint8), "RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("setting")
    ap.add_argument("--fps", type=float, default=24)
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--frames", type=int, default=432)
    ap.add_argument("--t", type=int, default=0)
    ap.add_argument("--scale", type=float, default=0.5)
    ap.add_argument("-o", "--out", default="preview.png")
    a, extra = ap.parse_known_args()
    a.extra = extra
    w, h = (int(x) for x in a.size.split("x"))
    render(a.setting, a.fps, w, h, a.frames, a.t, a.extra, a.scale).save(a.out)
    print(a.out)


if __name__ == "__main__":
    sys.exit(main())
