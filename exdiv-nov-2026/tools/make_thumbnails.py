"""Three long-form thumbnail variants (1280x720) for YouTube's Test & compare, in the dividend
series' style (dividend-income-2026/tools/make_thumbnails_ab.py). Every number is in the video.
Output: exdiv-nov-2026/thumbnails/T<n>_<name>_1280x720.png

Usage (repo root): .venv-tts/bin/python exdiv-nov-2026/tools/make_thumbnails.py
"""

import sys
from pathlib import Path

from PIL import ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "dividend-income-2026" / "tools"))
import make_thumbnails as T  # noqa: E402
from make_thumbnails_ab import line, pill  # noqa: E402

ACCENT, WHITE, GREEN, RED = T.ACCENT, T.WHITE, T.GREEN, T.RED
OUT = HERE.parent / "thumbnails"


def t1():  # free money?
    im = T.frame("pharma_lab/pharma_lab_02", 1280, 720).convert("RGBA"); d = ImageDraw.Draw(im)
    line(d, (60, 150), "₹75 FREE?", 210, ACCENT, anchor="lm", stroke=12)
    line(d, (60, 330), "SANOFI DIVIDEND", 110, WHITE, anchor="lm", stroke=10)
    pill(d, 470, 490, "BUT THE PRICE FALLS ₹75 TOO", 60, (255, 255, 255), bg=(190, 30, 30, 235))
    pill(d, 400, 630, "+ 11 MORE STOCKS, 5-6 NOV", 52, (20, 20, 20), bg=GREEN + (255,))
    return im.convert("RGB")


def t2():  # the deadline
    im = T.frame("trading/trading_02", 1280, 720).convert("RGBA"); d = ImageDraw.Draw(im)
    line(d, (640, 130), "BUY BEFORE", 160, WHITE, stroke=12)
    line(d, (640, 320), "6 NOV?", 190, ACCENT, stroke=12)
    pill(d, 640, 500, "12 DIVIDEND STOCKS | RECORD DATE", 56, (20, 20, 20), bg=GREEN + (255,))
    line(d, (640, 640), "WATCH THIS FIRST", 80, RED, stroke=8)
    return im.convert("RGB")


def t3():  # the tiny yield
    im = T.frame("money/money_03", 1280, 720).convert("RGBA"); d = ImageDraw.Draw(im)
    line(d, (640, 150), "0.04%", 230, RED, stroke=12)
    line(d, (640, 330), "DIVIDEND YIELD?!", 130, WHITE, stroke=12)
    pill(d, 640, 500, "₹10 OR ₹1: WHICH PAYS MORE?", 58, (20, 20, 20), bg=GREEN + (255,))
    pill(d, 640, 630, "THE REAL MATHS OF 12 STOCKS", 50, (255, 255, 255), bg=(0, 0, 0, 210))
    return im.convert("RGB")


VARIANTS = {"T1_75_free": t1, "T2_buy_before_6nov": t2, "T3_tiny_yield": t3}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in VARIANTS.items():
        fn().save(OUT / f"{name}_1280x720.png")
    print(sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()
