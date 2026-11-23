"""Drawing helpers for thumbnails and covers: a darkened footage frame, a fitted headline,
and text on a pill. The helpers take the text and layout from the caller, so this module has
no copy of its own. Used by make_covers.py and the thumbnail scripts.
"""

import sys
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

sys.path.insert(0, str(Path(__file__).parent))
import build_short as B  # noqa: E402

ACCENT, WHITE, GREEN, RED = B.ACCENT, B.WHITE, B.GREEN, (255, 120, 110)


def frame(clip, w, h, t=2):
    tmp = B.WORK / "thumb_bg.png"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    B.run(["ffmpeg", "-v", "error", "-y", "-ss", t, "-i", B.ASSETS / "videos" / f"{clip}.mp4", "-frames:v", 1, tmp])
    im = Image.open(tmp).convert("RGB")
    s = max(w / im.width, h / im.height)
    im = im.resize((int(im.width * s) + 1, int(im.height * s) + 1))
    x, y = (im.width - w) // 2, (im.height - h) // 2
    im = im.crop((x, y, x + w, y + h)).filter(ImageFilter.GaussianBlur(2.5))
    im = ImageEnhance.Brightness(im).enhance(0.42)
    return ImageEnhance.Color(im).enhance(1.15)


def fit(d, text, size, width, bold=True):
    while d.textlength(text, font=B.font(size, bold)) > width and size > 20:
        size -= 4
    return size


def line(d, xy, text, size, color, anchor="mm", stroke=10):
    d.text(xy, text, font=B.font(size), fill=color, anchor=anchor, stroke_width=stroke, stroke_fill=(0, 0, 0))


def pill(d, cx, cy, text, size, fg, bg=(0, 0, 0, 200), pad=34):
    f = B.font(size)
    w = d.textlength(text, font=f)
    d.rounded_rectangle((cx - w / 2 - pad, cy - size * 0.85, cx + w / 2 + pad, cy + size * 0.85), size, fill=bg)
    d.text((cx, cy), text, font=f, fill=fg, anchor="mm")
