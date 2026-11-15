"""Renders the two full-screen end cards every reel closes on (1080x1920, white):

  images/end_cards/disclaimer_card.png  shown while the VO says "Not investment advice"
  images/end_cards/cta_card.png         shown from the "Follow" line to the end

The disclaimer is our own artwork with the same message and look as the reference
image the user picked (big black capitals on white). That reference was someone
else's watermarked design, so it isn't used. The CTA card centres the user's
images/cta.png (Like / Share / Comment) with a "Follow" line under it.

--wide renders 1920x1080 versions for the long-form video instead (*_wide.png), with
the disclaimer on three lines and "Subscribe" in place of "Follow".

Usage: .venv-tts/Scripts/python invit-analysis-2026/assets/capcut/generator/make_end_cards.py [--wide]
"""

import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

IMAGES = Path(__file__).resolve().parents[2] / "images"
OUT = IMAGES / "end_cards"
WIDE = "--wide" in sys.argv[1:]
SIZE = (1920, 1080) if WIDE else (1080, 1920)
FONTS = Path("C:/Windows/Fonts")
INK = (17, 17, 17)
MARGIN = 160 if WIDE else 90


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def centered(draw, y, text, fnt, fill=INK, spacing=0):
    """Draws `text` (one line) centred at height y; returns the y below it."""
    left, top, right, bottom = draw.textbbox((0, 0), text, font=fnt)
    draw.text(((SIZE[0] - (right - left)) / 2 - left, y - top), text, font=fnt, fill=fill)
    return y + (bottom - top) + spacing


def fit_lines(draw, lines, name, width):
    """Largest size of font `name` at which every line fits `width`."""
    size = 200
    while any(draw.textlength(line, font=font(name, size)) > width for line in lines):
        size -= 2
    return font(name, size)


def disclaimer():
    im = Image.new("RGB", SIZE, "white")
    d = ImageDraw.Draw(im)
    lines = (["I'M NOT YOUR", "FINANCIAL ADVISOR.", "THIS IS NOT FINANCIAL ADVICE"] if WIDE else
             ["I'M NOT YOUR", "FINANCIAL", "ADVISOR.", "THIS IS NOT", "FINANCIAL", "ADVICE"])
    big = fit_lines(d, lines, "ariblk.ttf", SIZE[0] - 2 * MARGIN)
    line_h = d.textbbox((0, 0), "FINANCIAL", font=big)[3] - d.textbbox((0, 0), "FINANCIAL", font=big)[1]
    gap = int(line_h * 0.22)
    head = font("georgiai.ttf", 64)
    foot = font("segoeuib.ttf", 58)
    block = 90 + 70 + len(lines) * (line_h + gap) + 70 + 60
    if WIDE:  # measured, since the three long lines leave a much shorter block
        h = lambda t, f: d.textbbox((0, 0), t, font=f)[3] - d.textbbox((0, 0), t, font=f)[1]
        block = h("Disclaimer", head) + 70 + len(lines) * (line_h + gap) + 70 + h("Do Your Own Due Diligence", foot)
    y = (SIZE[1] - block) // 2
    y = centered(d, y, "Disclaimer", head, spacing=70)
    for line in lines:
        y = centered(d, y, line, big, spacing=gap)
    centered(d, y + 70, "Do Your Own Due Diligence", foot)
    return im


def cta():
    im = Image.new("RGB", SIZE, "white")
    src = Image.open(IMAGES / "cta.png").convert("RGBA")
    flat = Image.alpha_composite(Image.new("RGBA", src.size, "white"), src).convert("RGB")
    ink = ImageChops.difference(flat, Image.new("RGB", src.size, "white")).convert("L").point(lambda v: 255 if v > 24 else 0)
    src = flat.crop(ink.getbbox())
    w = SIZE[0] - 2 * MARGIN
    if WIDE:  # leave room under the image for the two text lines
        w = min(w, round(src.width * (SIZE[1] - 520) / src.height))
    src = src.resize((w, round(src.height * w / src.width)), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    follow = font("ariblk.ttf", 92)
    sub = font("segoeuib.ttf", 52)
    block = src.height + 110 + 100 + 30 + 60
    y = (SIZE[1] - block) // 2
    im.paste(src, ((SIZE[0] - src.width) // 2, y))
    y = centered(d, y + src.height + 110, "+ SUBSCRIBE" if WIDE else "+ FOLLOW", follow, fill=(230, 30, 35), spacing=30)
    centered(d, y, "for more InvIT deep-dives", sub, fill=(60, 60, 60))
    return im


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, render in (("disclaimer_card", disclaimer), ("cta_card", cta)):
        path = OUT / f"{name}{'_wide' if WIDE else ''}.png"
        render().save(path)
        print("wrote", path.relative_to(IMAGES.parent))


if __name__ == "__main__":
    main()
