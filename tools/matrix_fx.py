#!/usr/bin/env python3
"""Provini di LeaderKit su tutti i formati (da 480p a 4K, 4:3 -> 2.39, verticali).

Per ogni formato e schermata (slate nei quattro stili, countdown con la taratura, burn-in)
disegna un'anteprima approssimata (tools/preview_fx.py) con tutti i campi compilati e le
compone in fogli di provini:

    python3 tools/build_fx.py
    python3 tools/matrix_fx.py -o /tmp/provini [--only slate0,countdown,burnin] [--formats 480]

La taratura e i quadranti sono i PNG che crea Genera (fx/overlay.lua eseguito con lua5.4).
"""

import argparse
import json
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import preview_fx  # noqa: E402

# (etichetta, larghezza, altezza): 480p ricavato dal cheat sheet (larghezza 854 = 16:9 a 480 righe)
FORMATS = [
    ("480 4:3", 640, 480), ("480 16:9", 854, 480), ("480 1.85", 888, 480), ("480 2.39", 1148, 480),
    ("NTSC 720x480", 720, 480), ("PAL 720x576", 720, 576),
    ("720p", 1280, 720), ("720 2.39", 1280, 536),
    ("HD 4:3", 1440, 1080), ("HD 16:9", 1920, 1080), ("HD 1.85", 1998, 1080), ("DCI 2K", 2048, 1080),
    ("HD 2:1", 1920, 960), ("HD 2.39", 1920, 804), ("2K Scope", 2048, 858),
    ("UHD", 3840, 2160), ("4K DCI", 4096, 2160), ("4K Flat", 3996, 2160), ("4K Scope", 4096, 1716),
    ("UHD 2:1", 3840, 1920),
    ("9:16", 1080, 1920), ("4:5", 1080, 1350), ("1:1", 1080, 1080),
]

FULL = dict(Title="La lunga notte del cinema italiano", Production="Mecena Srl", Producer="Ivan Mazzone",
            Client="RAI Cinema", Agency="Agenzia Esempio", Code="IT-MEC-2026-0042", Episode="Rullo 3",
            Language="ITA / 5.1", Director="Anna Maria Rossellini", Editor="Giovanni Bianchi",
            AsstEditor="Chiara Verdi", Colorist="Marco Neri", Sound="Studio Suono Roma", VFXBy="Effetti Srl",
            Version="v12 · locked cut", Phase=2, StColor=2, StSound=1, StVFX=1, StMusic=2, StTitles=1,
            Note="Consegna definitiva per il festival", AudioFormat="5.1 + stereo, 24 bit 48 kHz",
            ColorInfo="Rec.709 Gamma 2.4", Duration="01:52:14:08",
            Info="FFOA 01:00:08:00  ·  2-POP 01:00:06:00  ·  LFOA 02:52:22:07")

OVERLAY_LUA = r"""
dofile(arg[1])
local W, H = tonumber(arg[3]), tonumber(arg[4])
local spec = load("return " .. arg[5])()
local ok, err
if spec.guides then spec.inner = LK_OVERLAY.innerRect(W, H, spec.guides) end
if spec.dial then ok, err = LK_OVERLAY.renderDial(arg[2], spec.dial, W, H, spec)
else ok, err = LK_OVERLAY.render(arg[2], W, H, spec) end
if not ok then io.stderr:write(tostring(err)); os.exit(1) end
"""
CAL = dict((k, True) for k in ("stars", "res", "diag", "center", "grey", "color", "checker", "ramps", "blue", "gamma",
                               "contour", "peak", "edge", "labels"))


def lua_table(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, (list, tuple)):
        return "{ " + ", ".join(lua_table(x) for x in v) + " }"
    return "{ " + ", ".join("[%s] = %s" % (json.dumps(k), lua_table(x)) for k, x in v.items()) + " }"


def overlay_png(out_dir, kind, w, h, spec):
    path = os.path.join(out_dir, "_%s_%dx%d.png" % (kind, w, h))
    if not os.path.exists(path):
        script = os.path.join(out_dir, "_overlay.lua")
        with open(script, "w") as fh:
            fh.write(OVERLAY_LUA)
        subprocess.check_call(["lua5.4", script, os.path.join(ROOT, "fx", "overlay.lua"), path, str(w), str(h),
                               lua_table(spec)])
    return path


GUIDES = [dict(ar=2.39), dict(safe=0.93)]       # frame lines accese nei provini del countdown
LOGO = os.path.join(ROOT, "dist", "_logo_prova.png")


def make_logo():
    if not os.path.exists(LOGO):
        im = Image.new("RGBA", (900, 300), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((10, 10, 890, 290), 40, outline=(240, 180, 60, 255), width=14)
        d.text((80, 70), "MECENA", fill=(255, 255, 255, 255), font=ImageFont.truetype(preview_fx.FONTS[0], 150))
        im.save(LOGO)


def params(d):
    return ["%s=%s" % (k, v) for k, v in d.items()]


def png_size(path):
    with Image.open(path) as im:
        return im.size


def head_frame(out_dir, w, h, t, extra, scale):
    setting = os.path.join(ROOT, "dist", "LeaderKit.setting")
    extra = dict(extra)
    style = extra.get("SlateStyle")
    if t >= 300:          # countdown: taratura di Genera nel Loader CalLd
        spec = dict(cal=CAL, fpsLabel="24/SEC", resLabel="HD", cdLogo=bool(extra.get("CdLogo")),
                    cdInfo=bool(extra.get("CdInfo")), guides=GUIDES)
        path = overlay_png(out_dir, "cal%d%d" % (spec["cdLogo"], spec["cdInfo"]), w, h, spec)
        extra.update(CalImage=path, CalW=w, CalH=h)
    elif style in (1, 2):
        kind = "b" if style == 1 else "c"
        path = overlay_png(out_dir, "dial" + kind, w, h, dict(dial=kind, fps=24))
        pw, ph = png_size(path)
        extra.update(**{"Dial%sImage" % kind.upper(): path, "Dial%sW" % kind.upper(): pw, "Dial%sH" % kind.upper(): ph})
    return preview_fx.render(setting, 24, w, h, 432, t, params(extra), scale)


def blens(seg):
    """Come BURN.fill (fx/engine_burnin.lua): lunghezze massime di ogni blocco."""
    import re
    parts = seg.split("|")[8:]
    out = []
    for k, blk in enumerate(parts[:5]):
        p = (blk.split("~") + ["", ""])[:2]
        ul = [len(re.sub(r"\{(SRC|REC|ATC)\}", "00:00:00:00", re.sub(r"\{FRM\}", "0000000", x))) for x in p]
        pieces = [q for q in (p[0] + "  ·  " + p[1]).split("  ·  ") if q]
        st = [len(re.sub(r"\{(SRC|REC|ATC)\}", "00:00:00:00", re.sub(r"\{FRM\}", "0000000", q))) for q in pieces]
        out.append("%d,%d,%d,%d,%d" % (max(ul), ul[0] + ul[1] + (5 if ul[0] and ul[1] else 0), max(st or [0]),
                                        sum(1 for x in ul if x), len(pieces)))
    return "|".join(out)


def burn_frame(w, h, extra, scale):
    setting = os.path.join(ROOT, "dist", "LeaderKit Burn-in.setting")
    seg = ("86400|86880|1000|1|24|0|90000|0|A001C003_260926_R2AB~A001  ·  CAM A|SC 12A  SH 3  TK 4 ★~|"
           "SRC TC {SRC}~AUD TC {ATC}  ·  SR 012|REC TC {REC}~FR {FRM}~{REC}|LA LUNGA NOTTE  ·  v12~26/09/2026")
    base = dict(Seg=seg, SegIdx="000000000000000001", RecStart=86400, TlW=w, TlH=h, BLens=blens(seg))
    base.update(extra)
    return preview_fx.render(setting, 24, w, h, 480, 10, params(base), scale)


SCREENS = {
    "slate0": lambda o, w, h, s: head_frame(o, w, h, 40, dict(FULL, SlateStyle=0), s),
    "slate1": lambda o, w, h, s: head_frame(o, w, h, 40, dict(FULL, SlateStyle=1), s),
    "slate2": lambda o, w, h, s: head_frame(o, w, h, 40, dict(FULL, SlateStyle=2), s),
    "slate3": lambda o, w, h, s: head_frame(o, w, h, 40, dict(FULL, SlateStyle=3), s),
    "countdown": lambda o, w, h, s: head_frame(o, w, h, 300, dict(FULL, CdInfo=1, CdLogo=1, Logo=LOGO, LogoW=900,
                                                                   LogoH=300, FL239=1, SafeAction=1), s),
    "burnin": lambda o, w, h, s: burn_frame(w, h, {}, s),
    "burnin43": lambda o, w, h, s: burn_frame(w, h, dict(BMatte=1), s),
    "burnin239": lambda o, w, h, s: burn_frame(w, h, dict(BMatte=11), s),
    "burnin185": lambda o, w, h, s: burn_frame(w, h, dict(BMatte=6), s),
    "burnin_in": lambda o, w, h, s: burn_frame(w, h, dict(BPos=1), s),
}


def sheet(images, labels, cols, cell_w):
    rows = (len(images) + cols - 1) // cols
    cells = []
    for im in images:
        k = cell_w / float(im.width)
        cells.append(im.resize((cell_w, max(1, int(im.height * k))), Image.LANCZOS))
    row_h = [max(c.height for c in cells[r * cols:(r + 1) * cols]) + 22 for r in range(rows)]
    out = Image.new("RGB", (cols * (cell_w + 8) + 8, sum(row_h) + 8), (40, 40, 40))
    d = ImageDraw.Draw(out)
    font = ImageFont.truetype(preview_fx.FONTS[0], 14)
    y = 8
    for r in range(rows):
        for c in range(cols):
            i = r * cols + c
            if i >= len(cells):
                break
            x = 8 + c * (cell_w + 8)
            d.text((x, y), labels[i], fill=(255, 220, 120), font=font)
            out.paste(cells[i], (x, y + 18))
        y += row_h[r]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="provini")
    ap.add_argument("--only", default=",".join(SCREENS))
    ap.add_argument("--formats", default="", help="filtro sulle etichette dei formati (es. 480,HD)")
    ap.add_argument("--cell", type=int, default=640)
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--maxw", type=int, default=1280, help="larghezza massima di calcolo dell'anteprima")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    import build_fx
    build_fx.build()                     # generatori aggiornati in dist/
    make_logo()
    fmts = [f for f in FORMATS if not a.formats or any(x in f[0] for x in a.formats.split(","))]
    for scr in a.only.split(","):
        imgs, labels = [], []
        for lab, w, h in fmts:
            scale = min(1.0, a.maxw / float(max(w, h)))
            imgs.append(SCREENS[scr](a.out, w, h, scale))
            labels.append("%s  %dx%d  %.2f:1" % (lab, w, h, w / float(h)))
        path = os.path.join(a.out, "%s.png" % scr)
        sheet(imgs, labels, a.cols, a.cell).save(path)
        print(path)


if __name__ == "__main__":
    main()
