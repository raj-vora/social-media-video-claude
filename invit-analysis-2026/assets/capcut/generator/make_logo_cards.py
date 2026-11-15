"""Renders every logo in assets/images/logos/logos.json onto a uniform card:
a white rounded panel with a soft shadow, on a transparent 16:9 canvas. Each
card is the same size, so add_logos.js can place them all with one transform and
they read the same over any footage. Logos are trimmed to their own content
first, so differently-padded source files end up the same visual size.

Usage: .venv-tts/Scripts/python invit-analysis-2026/assets/capcut/generator/make_logo_cards.py
"""

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

LOGOS = Path(__file__).resolve().parents[2] / "images" / "logos"
CANVAS = (2160, 1216)          # shown at 1080 wide on the 1080x1920 reel canvas
CARD = (1680, 840)
RADIUS = 56
BOX = (1400, 600)              # the logo is fitted inside this
SHADOW = (0, 0, 0, 110)


def trimmed(path, crop=None):
    """The logo cropped to its visible content (non-transparent, non-white).
    `crop` (a registry option) first cuts away source artwork that isn't logo."""
    im = Image.open(path).convert("RGBA")
    if crop:
        im = im.crop(tuple(crop))
    white = Image.new("RGBA", im.size, (255, 255, 255, 255))
    flat = Image.alpha_composite(white, im).convert("RGB")
    ink = ImageChops.difference(flat, Image.new("RGB", im.size, (255, 255, 255))).convert("L")
    ink = ink.point(lambda v: 255 if v > 24 else 0)
    return im.crop(ink.getbbox())


def card(logo):
    canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    x0, y0 = (CANVAS[0] - CARD[0]) // 2, (CANVAS[1] - CARD[1]) // 2
    panel = (x0, y0, x0 + CARD[0], y0 + CARD[1])

    shadow = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([panel[0], panel[1] + 18, panel[2], panel[3] + 18],
                                             RADIUS, fill=SHADOW)
    canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(28)))
    ImageDraw.Draw(canvas).rounded_rectangle(panel, RADIUS, fill=(255, 255, 255, 255))

    scale = min(BOX[0] / logo.width, BOX[1] / logo.height)
    logo = logo.resize((round(logo.width * scale), round(logo.height * scale)), Image.LANCZOS)
    canvas.alpha_composite(logo, ((CANVAS[0] - logo.width) // 2, (CANVAS[1] - logo.height) // 2))
    return canvas


def main():
    registry = json.loads((LOGOS / "logos.json").read_text(encoding="utf-8"))
    for key, entry in registry.items():
        out = LOGOS / entry["card"]
        out.parent.mkdir(exist_ok=True)
        logo = trimmed(LOGOS / entry["raster"], entry.get("crop"))
        card(logo).save(out)
        print(f"{key:16} {logo.width}x{logo.height} -> {out.relative_to(LOGOS)}")


if __name__ == "__main__":
    main()
