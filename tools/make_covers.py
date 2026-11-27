"""Generate the demo cover images in the style of the design report
(solid colour, serif title, accent line, simple motif, author in capitals).

    python tools/make_covers.py      ->  seed_covers/<key>.png
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from bookorbit.seed_catalog import BOOKS  # noqa: E402

W, H = 400, 600
ACCENT = "#E8B04A"
LIGHT = {"#E9E2D0", "#E8B04A", "#8A9A7B"}

SERIF_CANDIDATES = ["DejaVuSerif-Bold.ttf", "Georgia Bold.ttf", "georgiab.ttf", "Times New Roman Bold.ttf"]
SANS_CANDIDATES = ["DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf"]


def font(cands, size):
    for c in cands:
        for base in ("", "/usr/share/fonts/truetype/dejavu/", "/Library/Fonts/", "C:/Windows/Fonts/"):
            try:
                return ImageFont.truetype(base + c, size)
            except OSError:
                continue
    return ImageFont.load_default()


def shade(hex_color, f):
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return tuple(max(0, min(255, int(c * f))) for c in (r, g, b))


def motif(d: ImageDraw.ImageDraw, kind: str, fg, bg, rng: random.Random):
    cx = W // 2
    if kind == "envelope":
        d.rectangle([90, 290, 310, 430], outline=fg, width=6)
        d.line([90, 290, 200, 370, 310, 290], fill=fg, width=6)
        d.ellipse([180, 352, 220, 392], fill=fg)
    elif kind == "waves":
        d.ellipse([255, 270, 295, 310], fill=fg)
        for k in range(3):
            pts = [(x, 380 + k * 22 + 12 * math.sin(x / 28)) for x in range(30, 371, 6)]
            d.line(pts, fill=fg, width=5)
    elif kind == "tree":
        d.ellipse([140, 270, 260, 390], fill=fg)
        d.rectangle([193, 380, 207, 450], fill=fg)
        d.line([60, 450, 340, 450], fill=fg, width=4)
        for x, y in ((175, 310), (225, 330), (195, 355)):
            d.ellipse([x - 6, y - 6, x + 6, y + 6], fill=bg)
    elif kind == "sun":
        d.ellipse([150, 300, 250, 400], fill=fg)
        for a in range(0, 360, 30):
            r1, r2 = 65, 95
            d.line([cx + r1 * math.cos(math.radians(a)), 350 + r1 * math.sin(math.radians(a)),
                    cx + r2 * math.cos(math.radians(a)), 350 + r2 * math.sin(math.radians(a))], fill=fg, width=5)
    elif kind == "moon":
        d.ellipse([230, 260, 300, 330], fill=fg)
        d.ellipse([250, 250, 320, 320], fill=bg)
        x = 40
        while x < 360:
            h = rng.randint(40, 110)
            w = rng.randint(30, 50)
            d.rectangle([x, 460 - h, x + w, 460], outline=fg, width=3)
            for wy in range(470 - h, 455, 18):
                if rng.random() < 0.5:
                    d.rectangle([x + 8, wy, x + 14, wy + 6], fill=fg)
            x += w + 6
        for _ in range(14):
            sx, sy = rng.randint(40, 360), rng.randint(250, 340)
            d.ellipse([sx - 2, sy - 2, sx + 2, sy + 2], fill=fg)
    elif kind == "keyhole":
        d.ellipse([160, 280, 240, 360], fill=fg)
        d.polygon([(175, 340), (225, 340), (245, 450), (155, 450)], fill=fg)
    elif kind == "cross":
        d.ellipse([110, 290, 210, 390], outline=fg, width=7)
        d.rectangle([255, 270, 271, 440], fill=fg)
        d.rectangle([225, 310, 301, 326], fill=fg)
    elif kind == "magnifier":
        d.ellipse([130, 280, 240, 390], outline=fg, width=10)
        d.line([228, 378, 300, 450], fill=fg, width=16)
    elif kind == "heart":
        d.ellipse([140, 300, 205, 365], fill=fg)
        d.ellipse([195, 300, 260, 365], fill=fg)
        d.polygon([(143, 345), (257, 345), (200, 420)], fill=fg)
    elif kind == "whale":
        d.ellipse([90, 330, 290, 410], fill=fg)
        d.polygon([(280, 370), (340, 320), (330, 380), (345, 420)], fill=fg)
        d.ellipse([130, 355, 142, 367], fill=bg)
        d.line([180, 330, 170, 290], fill=fg, width=4)
        d.line([180, 330, 195, 292], fill=fg, width=4)
        for k in range(2):
            d.line([(x, 440 + k * 20 + 8 * math.sin(x / 20)) for x in range(30, 371, 6)], fill=fg, width=4)
    elif kind == "dagger":
        d.polygon([(200, 260), (214, 380), (186, 380)], fill=fg)
        d.rectangle([160, 380, 240, 392], fill=fg)
        d.rectangle([194, 392, 206, 440], fill=fg)
        d.ellipse([190, 436, 210, 456], fill=fg)
    elif kind == "crown":
        d.polygon([(110, 420), (110, 320), (155, 370), (200, 300), (245, 370), (290, 320), (290, 420)], fill=fg)
        for x in (110, 200, 290):
            d.ellipse([x - 10, 290 if x == 200 else 310, x + 10, 310 if x == 200 else 330], fill=fg)
    elif kind == "grass":
        for i in range(40):
            x = 40 + i * 8
            h = rng.randint(60, 150)
            d.line([x, 450, x + rng.randint(-25, 25), 450 - h], fill=fg, width=3)
    elif kind == "bolt":
        d.polygon([(220, 260), (150, 370), (195, 370), (170, 460), (250, 340), (205, 340)], fill=fg)
    elif kind == "clock":
        d.ellipse([125, 280, 275, 430], outline=fg, width=8)
        d.line([200, 355, 200, 300], fill=fg, width=7)
        d.line([200, 355, 245, 375], fill=fg, width=7)
        for a in range(0, 360, 30):
            d.ellipse([200 + 62 * math.cos(math.radians(a)) - 3, 355 + 62 * math.sin(math.radians(a)) - 3,
                       200 + 62 * math.cos(math.radians(a)) + 3, 355 + 62 * math.sin(math.radians(a)) + 3], fill=fg)
    elif kind == "planet":
        d.ellipse([150, 300, 250, 400], fill=fg)
        d.ellipse([95, 335, 305, 365], outline=fg, width=5)
        for _ in range(16):
            sx, sy = rng.randint(30, 370), rng.randint(250, 460)
            d.ellipse([sx - 2, sy - 2, sx + 2, sy + 2], fill=fg)
    elif kind == "ship":
        d.polygon([(110, 400), (290, 400), (260, 440), (140, 440)], fill=fg)
        d.line([200, 280, 200, 400], fill=fg, width=5)
        d.polygon([(205, 285), (205, 390), (275, 390)], fill=fg)
        d.polygon([(195, 300), (195, 390), (140, 390)], fill=fg)
        d.line([(x, 455 + 6 * math.sin(x / 15)) for x in range(40, 361, 5)], fill=fg, width=4)
    elif kind == "candle":
        d.rectangle([175, 340, 225, 450], fill=fg)
        d.ellipse([186, 280, 214, 330], fill=fg)
        d.line([200, 330, 200, 342], fill=bg, width=3)
    elif kind == "leaf":
        d.ellipse([130, 280, 270, 440], fill=fg)
        d.line([140, 450, 260, 270], fill=bg, width=5)
        for t in (0.3, 0.5, 0.7):
            x, y = 140 + 120 * t, 450 - 180 * t
            d.line([x, y, x - 40, y - 20], fill=bg, width=3)
            d.line([x, y, x + 25, y + 30], fill=bg, width=3)
    elif kind == "atom":
        d.ellipse([188, 343, 212, 367], fill=fg)
        for ang in (0, 60, 120):
            pts = []
            for t in range(0, 361, 6):
                x, y = 95 * math.cos(math.radians(t)), 32 * math.sin(math.radians(t))
                a = math.radians(ang)
                pts.append((200 + x * math.cos(a) - y * math.sin(a), 355 + x * math.sin(a) + y * math.cos(a)))
            d.line(pts, fill=fg, width=4)
    elif kind == "mountain":
        d.polygon([(40, 450), (150, 290), (230, 400), (280, 330), (360, 450)], fill=fg)
        d.ellipse([270, 250, 310, 290], fill=fg)


def make_cover(path: Path, title: str, author: str, color: str, kind: str, seed: int) -> None:
    rng = random.Random(seed)
    img = Image.new("RGB", (W, H), color)
    d = ImageDraw.Draw(img)
    light = color in LIGHT
    text_col = "#1E2A44" if light else "#F4EFE3"
    fg = "#1E2A44" if color == "#E8B04A" else (ACCENT if not light else "#B5452F")
    d.rectangle([0, 0, 12, H], fill=shade(color, 0.72))                 # spine shadow
    size = 46 if len(title) < 14 else (40 if len(title) < 26 else 34)
    f_title = font(SERIF_CANDIDATES, size)
    lines, cur = [], ""
    for word in title.split():
        trial = (cur + " " + word).strip()
        if d.textlength(trial, font=f_title) <= W - 72 or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    lines.append(cur)
    y = 40
    for line in lines[:4]:
        d.text((36, y), line, font=f_title, fill=text_col)
        y += int(size * 1.18)
    d.line([36, y + 12, 76, y + 12], fill=fg, width=4)
    motif(d, kind, fg, color, rng)
    f_auth = font(SANS_CANDIDATES, 15)
    d.text((36, H - 52), "  ".join(author.upper().split()), font=f_auth, fill=text_col)
    img.save(path, optimize=True)


def main() -> None:
    out = ROOT / "seed_covers"
    out.mkdir(exist_ok=True)
    for i, (key, title, author, _cat, _y, _p, _k, _d, _t, color, kind) in enumerate(BOOKS):
        make_cover(out / f"{key}.png", title, author, color, kind, seed=i)
    print(f"Wrote {len(BOOKS)} covers to {out}")


if __name__ == "__main__":
    main()
