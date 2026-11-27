#!/usr/bin/env python3
"""Draw the launcher icon (a wallet on the square-board green) at every density."""
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
SIZES = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
GREEN, LIGHT, GOLD = (11, 61, 46), (243, 250, 246), (226, 182, 92)


def draw(px: int) -> Image.Image:
    s = 4  # draw big, then shrink for smooth edges
    n = px * s
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, n - 1, n - 1], radius=int(n * 0.22), fill=GREEN)
    # banknote peeking out of the wallet
    d.rounded_rectangle([n * .24, n * .22, n * .80, n * .50], radius=int(n * .04), fill=GOLD)
    # wallet body
    d.rounded_rectangle([n * .16, n * .34, n * .84, n * .80], radius=int(n * .08), fill=LIGHT)
    # clasp
    d.rounded_rectangle([n * .58, n * .49, n * .88, n * .65], radius=int(n * .06), fill=GREEN)
    r = n * .035
    cx, cy = n * .66, n * .57
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=LIGHT)
    return img.resize((px, px), Image.LANCZOS)


for name, px in SIZES.items():
    out = HERE / "res" / f"mipmap-{name}" / "ic_launcher.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    draw(px).save(out)
print("icons ok")
