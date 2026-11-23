"""Reel covers (1080x1920) so every reel looks different in the Instagram / Facebook profile grid instead of
showing the same auto-picked frame. Each cover uses the reel's own hook footage and hook headline, with an
accent colour per language. All text sits inside the centre 3:4 band (y 240-1680), which is what the
Instagram grid shows.

Output: previews_shorts/covers/<KEY>.jpg  (KEY as in previews_shorts/captions.json)

  .venv-tts/bin/python exdiv-nov-2026/tools/make_covers.py KEY [KEY ...]
"""
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path[:0] = [str(HERE), str(REPO / "dividend-income-2026" / "tools")]
import build_short as B  # noqa: E402
import thumb_draw as T  # noqa: E402
from cover_copy import DIV  # noqa: E402
from exdiv_scripts import SHORTS  # noqa: E402

OUT = REPO / "previews_shorts" / "covers"
W, H = 1080, 1920
LANG = {"hi": ("HINDI", (255, 214, 64)), "mr": ("MARATHI", (120, 230, 150)),
        "gu": ("GUJARATI", (110, 210, 255)), "en": ("ENGLISH", (255, 140, 190))}
RANK_COLOURS = [(255, 214, 64), (120, 230, 150), (110, 210, 255), (255, 140, 190), (255, 170, 80),
                (190, 160, 255), (90, 230, 220), (255, 120, 110), (200, 230, 90), (255, 255, 255)]
# Cover copy for the dividend-series reels lives in cover_copy.py (private).


def fit(d, text, size, room):
    while d.textlength(text, font=B.font(size)) > room and size > 40:
        size -= 4
    return size


def cover(key):
    m = re.match(r"exdiv_(.+)_(hi|mr|gu|en)_([A-E])$", key)
    if m:
        short, lang, v = m.groups()
        s = SHORTS[f"{short}_{lang}"][v]
        big, name, chip = s["banner"]
        hook = next(x for x in s["segs"] if x[0] == "hook")
        head, sub = (hook[2][0][1], hook[2][1][1] if len(hook[2]) > 1 else "")
        clip, badge = hook[4], LANG[lang][0]
        accent = LANG[lang][1]
    else:
        name, head, sub, clip, chip = DIV[key]
        big, badge = "", "HINDI"
        accent = RANK_COLOURS[int(chip.split()[0][1:]) - 1]  # one colour per rank so the Page grid varies
    im = T.frame(clip, W, H).convert("RGBA")
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for y in range(H):  # darker in the middle band, where the text is
        a = (150 if 240 <= y <= 1680 else 90) if m else (110 if 240 <= y <= 1680 else 60)
        sd.line([(0, y), (W, y)], fill=(0, 0, 0, a))
    im = Image.alpha_composite(im, shade)
    d = ImageDraw.Draw(im)
    T.pill(d, W // 2, 330, name, fit(d, name, 76, W - 220), (255, 255, 255), bg=(0, 0, 0, 215))
    if big:
        d.text((W // 2, 610), big, font=B.font(fit(d, big, 260, W - 120)), fill=accent, anchor="mm",
               stroke_width=14, stroke_fill=(0, 0, 0))
    y = 900 if big else 760
    for text, size, col in ((head, 96 if big else 120, (255, 255, 255) if big else accent), (sub, 70 if big else 80, (255, 255, 255))):
        if not text:
            continue
        f = B.font(fit(d, text, size, W - 120))
        for ln in B.wrap(d, text, f, W - 120):
            d.text((W // 2, y), ln, font=f, fill=col, anchor="mm", stroke_width=9, stroke_fill=(0, 0, 0))
            y += int(f.size * 1.2)
        y += 40
    T.pill(d, W // 2, 1520, chip, 60, (20, 20, 20), bg=accent + (255,))
    if not m:  # dividend series: the headline in the accent colour, a bigger rank badge
        pass
    T.pill(d, W // 2, 1630, badge, 44, (255, 255, 255), bg=(0, 0, 0, 200))
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / f"{key}.jpg"
    im.convert("RGB").save(dest, quality=90)
    return dest


if __name__ == "__main__":
    for k in sys.argv[1:]:
        print(cover(k))
