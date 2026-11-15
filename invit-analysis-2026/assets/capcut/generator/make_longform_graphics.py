"""Animated explainer graphics for the long-form video (16:9), in place of text laid
over stock footage: counters, the InvIT money-flow diagram, OUT stamps, price paths,
the IPO-to-date money stacks, the leaderboard, the yield trap, the checklist.

Each graphic animates in over a couple of seconds and then holds, so it is written as
  videos/graphics/<name>.mp4         the animation
  images/graphics/<name>_hold.png    its last frame, held for the rest of the shot
and the shot list (reels.js `longform`) cues it to the line of VO it illustrates.
Figures are the script's (scripts/youtube/00_longform_top5_hindi.md), which come from
data/invits_2026_returns.csv. Text is Latin only, with "Rs", like every overlay.

Usage: .venv-tts/Scripts/python invit-analysis-2026/assets/capcut/generator/make_longform_graphics.py [name-substring ...]
"""

import math
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).resolve().parents[2]
VIDEO_OUT = ASSETS / "videos" / "graphics"
HOLD_OUT = ASSETS / "images" / "graphics"
LOGOS = ASSETS / "images" / "logos" / "cards"
W, H, FPS = 1920, 1080, 30
FONTS = Path("C:/Windows/Fonts")

# The charts' palette (generate_charts.ps1).
BG = (13, 17, 23)
PANEL = (28, 34, 43)
WHITE = (255, 255, 255)
GREY = (160, 170, 180)
DIM = (95, 104, 114)
GREEN = (46, 160, 108)
RED = (205, 70, 70)
RED_TXT = (255, 125, 115)
AMBER = (232, 168, 48)
BLUE = (70, 130, 180)


def font(size, weight="b"):
    name = {"b": "segoeuib.ttf", "r": "segoeui.ttf", "k": "ariblk.ttf", "s": "seguisb.ttf"}[weight]
    return ImageFont.truetype(str(FONTS / name), round(size))


def ease(t, start, dur=0.6):
    """0 -> 1 over [start, start + dur], cubic ease-out."""
    x = min(1.0, max(0.0, (t - start) / dur)) if dur > 0 else float(t >= start)
    return 1 - (1 - x) ** 3


def back(t, start, dur=0.45):
    """0 -> 1 with a little overshoot, for things that land (stamps, pops)."""
    x = min(1.0, max(0.0, (t - start) / dur))
    c = 1.9
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def rgba(color, a):
    return (*color[:3], max(0, min(255, round(255 * a))))


class Frame:
    def __init__(self):
        self.im = Image.new("RGBA", (W, H), (*BG, 255))
        self.d = ImageDraw.Draw(self.im, "RGBA")

    def text(self, xy, s, size, color=WHITE, weight="b", a=1.0, anchor="mm", dy=0):
        if a <= 0:
            return
        self.d.text((xy[0], xy[1] + dy * (1 - a)), s, font=font(size, weight), fill=rgba(color, a), anchor=anchor)

    def box(self, x0, y0, x1, y1, color, a=1.0, r=18, outline=None, width=4):
        if a <= 0 or x1 <= x0 or y1 <= y0:
            return
        self.d.rounded_rectangle((x0, y0, x1, y1), r, fill=rgba(color, a),
                                 outline=rgba(outline, a) if outline else None, width=width)

    def line(self, pts, color, width=6, a=1.0):
        if a > 0 and len(pts) > 1:
            self.d.line(pts, fill=rgba(color, a), width=width, joint="curve")

    def arrow(self, x0, y, x1, p, color=GREY, width=8):
        """Horizontal arrow growing from x0 toward x1 as p goes 0 -> 1."""
        if p <= 0:
            return
        xe = x0 + (x1 - x0) * p
        self.line([(x0, y), (xe, y)], color, width)
        self.d.polygon([(xe + 4, y), (xe - 22, y - 16), (xe - 22, y + 16)], fill=rgba(color, 1))

    def stamp(self, center, s, size, color, p, angle=-12, weight="k"):
        """Text in a bordered box that drops onto the frame (p: 0 -> 1, with overshoot)."""
        if p <= 0:
            return
        f = font(size, weight)
        l, t, r, b = f.getbbox(s)
        pad = size * 0.28
        w, h = int(r - l + 2 * pad), int(b - t + 2 * pad)
        tile = Image.new("RGBA", (w + 20, h + 20), (0, 0, 0, 0))
        td = ImageDraw.Draw(tile)
        td.rounded_rectangle((10, 10, 10 + w, 10 + h), 12, outline=rgba(color, 1), width=max(6, size // 12))
        td.text((10 + w / 2, 10 + h / 2), s, font=f, fill=rgba(color, 1), anchor="mm")
        scale = 2.2 - 1.2 * p  # starts big, lands at 1 (p overshoots slightly)
        tile = tile.rotate(angle, expand=True, resample=Image.BICUBIC)
        tile = tile.resize((max(1, int(tile.width * scale)), max(1, int(tile.height * scale))), Image.BICUBIC)
        alpha = tile.getchannel("A").point(lambda v: int(v * min(1.0, p * 1.4)))
        tile.putalpha(alpha)
        self.im.alpha_composite(tile, (int(center[0] - tile.width / 2), int(center[1] - tile.height / 2)))

    def paste(self, img, center, a=1.0, sx=1.0):
        if a <= 0 or sx <= 0.01:
            return
        im = img.resize((max(1, int(img.width * sx)), img.height), Image.LANCZOS) if sx != 1.0 else img.copy()
        if a < 1:
            im.putalpha(im.getchannel("A").point(lambda v: int(v * a)))
        self.im.alpha_composite(im, (int(center[0] - im.width / 2), int(center[1] - im.height / 2)))


def rs(v):
    return f"Rs {v:,.0f}" if abs(v - round(v)) < 0.05 else f"Rs {v:,.2f}".rstrip("0").rstrip(".")


# ---- Reusable layouts -------------------------------------------------------------

def header(f, t, title, sub=None):
    f.text((W / 2, 120), title, 64, a=ease(t, 0, 0.5), dy=-20)
    if sub:
        f.text((W / 2, 196), sub, 34, GREY, "r", a=ease(t, 0.25, 0.5))


def ipo_stack(name, since, price, cash, total_label):
    """Rs 100 at the IPO next to what it is now: unit price + cash paid out."""
    def draw(f, t):
        header(f, t, f"{name}: Rs 100 at the IPO = aaj?", since)
        base, unit = 900, 3.2  # px per rupee
        # Invested column.
        p = ease(t, 0.5, 0.8)
        f.box(560, base - 100 * unit * p, 800, base, DIM, r=10)
        f.text((680, base + 40), "IPO", 34, GREY, "s")
        f.text((680, base - 100 * unit - 40), "Rs 100", 44, a=ease(t, 1.1, 0.4))
        # Today column: price, then cash on top.
        pp = ease(t, 1.4, 0.9)
        f.box(1120, base - price * unit * pp, 1360, base, BLUE, r=10)
        f.text((1240, base - price * unit / 2), f"Price\n{rs(price)}", 34, WHITE, "s", a=ease(t, 2.1, 0.4))
        cp = ease(t, 2.4, 0.9)
        top = base - price * unit
        f.box(1120, top - cash * unit * cp, 1360, top, GREEN, r=10)
        f.text((1240, top - cash * unit / 2), f"Cash\n+{rs(cash)}", 34, WHITE, "s", a=ease(t, 3.1, 0.4))
        f.text((1240, base + 40), "AAJ", 34, GREY, "s")
        f.text((1240, top - cash * unit - 50), total_label, 56, AMBER, a=ease(t, 3.4, 0.5), dy=20)
        f.line([(500, base), (1420, base)], DIM, 4)
    return 4.2, draw


def zero_sum(title, sub, price, cash, net_label, net_color, tag=None):
    """A year's price move against its cash payout, and what they net to."""
    def draw(f, t):
        header(f, t, title, sub)
        base, unit = 560, 14.0
        f.line([(520, base), (1400, base)], DIM, 4, a=ease(t, 0.3))
        pp = ease(t, 0.6, 0.9)  # price (down when negative)
        h = abs(price) * unit * pp
        if price < 0:
            f.box(620, base, 860, base + h, RED, r=8)
            f.text((740, base + abs(price) * unit + 44), f"Price {price:+.1f}%", 40, RED_TXT, a=ease(t, 1.3, 0.4))
        else:
            f.box(620, base - h, 860, base, BLUE, r=8)
            f.text((740, base - price * unit - 44), f"Price {price:+.1f}%", 40, a=ease(t, 1.3, 0.4))
        cp = ease(t, 1.6, 0.9)
        f.box(1060, base - cash * unit * cp, 1300, base, GREEN, r=8)
        f.text((1180, base - cash * unit - 44), f"Cash +{cash:.1f}%", 40, (120, 220, 160), a=ease(t, 2.3, 0.4))
        f.stamp((W / 2, 930), net_label, 84, net_color, back(t, 2.8), angle=0, weight="k")
        if tag:
            f.text((W / 2, 1035), tag, 28, GREY, "r", a=ease(t, 3.3, 0.5))
    return 3.8, draw


def checklist(done):
    items = ["Interest rates", "Concession end date", "Debt", "Tax: Form 64B"]

    def draw(f, t):
        f.text((W / 2, 150), "BEFORE YOU BUY AN InvIT", 64, a=1 if done else ease(t, 0, 0.5))
        for i, item in enumerate(items):
            y = 330 + i * 165
            appear = 1 if i < done or done == 0 else 1  # every row is visible; ticks mark progress
            f.box(430, y - 62, 1490, y + 62, PANEL, a=appear, r=20)
            f.text((540, y), str(i + 1), 54, AMBER, "k")
            f.text((620, y), item, 50, WHITE if i < done else GREY, "s", anchor="lm")
            if i < done:
                p = 1.0 if i < done - 1 else ease(t, 0.2, 0.5)
                cx, cy = 1400, y
                pts = [(cx - 34, cy), (cx - 10, cy + 26), (cx + 38, cy - 30)]
                seg = p * 2
                drawn = [pts[0], pts[1] if seg >= 1 else (pts[0][0] + (pts[1][0] - pts[0][0]) * seg, pts[0][1] + (pts[1][1] - pts[0][1]) * seg)]
                if seg > 1:
                    s2 = seg - 1
                    drawn.append((pts[1][0] + (pts[2][0] - pts[1][0]) * s2, pts[1][1] + (pts[2][1] - pts[1][1]) * s2))
                f.line(drawn, GREEN, 14)
    return (1.0 if done else 0.8), draw


def out_cards(n):
    cards = [("Cube Highways Trust", "~21% in 2026, but min ticket Rs 25 lakh+"),
             ("Anzen InvIT", "same reason: min ticket out of reach"),
             ("Raajmarg Infra", "listed Mar 2026, not there in Jan")]

    def draw(f, t):
        f.text((W / 2, 130), "Not in the retail Top 5", 60, a=1 if n > 1 else ease(t, 0, 0.5))
        for i, (name, why) in enumerate(cards):
            x = 340 + i * 620
            f.box(x - 270, 300, x + 270, 820, PANEL, r=24, a=1 if n > 1 else ease(t, 0.1 * i, 0.4))
            f.text((x, 420), name, 44, a=1 if n > 1 else ease(t, 0.1 * i, 0.4))
            for k, part in enumerate(why.split(", ")):
                f.text((x, 720 + k * 46), part, 30, GREY, "r", a=1 if n > 1 else ease(t, 0.2 + 0.1 * i, 0.4))
            if i < n:
                f.stamp((x, 570), "OUT", 120, RED, 1.0 if i < n - 1 else back(t, 0.3))
    return 1.2, draw


# ---- The graphics, in VO order ------------------------------------------------------

def c0_invest(f, t):
    f.text((W / 2, 330), "JUNE 2017", 56, GREY, "s", a=ease(t, 0, 0.5))
    f.stamp((W / 2, 540), "Rs 100", 170, AMBER, back(t, 0.4), angle=0)
    f.text((W / 2, 760), "in one InvIT", 46, GREY, "r", a=ease(t, 0.9, 0.5))


def c0_today(f, t):
    f.text((W / 2, 300), "AAJ: unit price", 56, GREY, "s", a=ease(t, 0, 0.4))
    v = 100 + 73.49 * ease(t, 0.3, 1.6)
    f.text((W / 2, 540), f"Rs {v:.0f}", 190, WHITE, "k")
    f.text((W / 2, 760), "June 2017: Rs 100", 40, DIM, "r", a=ease(t, 1.9, 0.4))


def c0_cash(f, t):
    base, unit = 900, 1.95
    f.text((W / 2, 120), "Rs 100 in June 2017 = aaj?", 60, a=ease(t, 0, 0.4))
    f.box(560, base - 100 * unit * ease(t, 0.2, 0.6), 780, base, DIM, r=10)
    f.text((670, base + 40), "Invested", 32, GREY, "s")
    f.text((670, base - 100 * unit - 36), "Rs 100", 40, a=ease(t, 0.6, 0.4))
    f.box(1140, base - 173.49 * unit * ease(t, 0.6, 0.8), 1360, base, BLUE, r=10)
    f.text((1250, base - 173.49 * unit / 2), "Price\nRs 173", 36, WHITE, "s", a=ease(t, 1.2, 0.4))
    top = base - 173.49 * unit
    f.box(1140, top - 121.32 * unit * ease(t, 1.4, 0.9), 1360, top, GREEN, r=10)
    f.text((1250, top - 121.32 * unit / 2), "Cash\n+Rs 121", 36, WHITE, "s", a=ease(t, 2.1, 0.4))
    f.text((1250, base + 40), "AAJ", 32, GREY, "s")
    f.text((1550, top - 121.32 * unit / 2), "more than\nyou put in!", 40, AMBER, "s", a=ease(t, 2.5, 0.5))
    f.line([(500, base), (1420, base)], DIM, 4)


def c0_rank5(f, t):
    f.text((W / 2, 280), "Its 2026 rank in our Top 5?", 56, GREY, "s", a=ease(t, 0, 0.4))
    f.stamp((W / 2, 580), "#5 ?!", 220, RED, back(t, 0.5), angle=-8)
    f.text((W / 2, 880), "dead last", 48, RED_TXT, "s", a=ease(t, 1.2, 0.5))


def c1_flow(f, t):
    f.text((W / 2, 140), "How an InvIT works", 60, a=ease(t, 0, 0.4))
    boxes = [("ASSETS", "toll roads, power lines"), ("TRUST", "the InvIT"),
             ("UNITS", "listed on the exchange"), ("YOU", "buy via demat")]
    xs = [300, 760, 1220, 1680]
    for i, (head, sub) in enumerate(boxes):
        a = ease(t, 0.3 + i * 0.7, 0.4)
        f.box(xs[i] - 190, 380, xs[i] + 190, 600, PANEL, a=a, r=22, outline=AMBER if i == 3 else None)
        f.text((xs[i], 455), head, 52, a=a)
        f.text((xs[i], 535), sub, 28, GREY, "r", a=a)
        if i:
            f.arrow(xs[i - 1] + 195, 490, xs[i] - 200, ease(t, 0.1 + i * 0.7, 0.4))
    # Cash flows back from the assets to you.
    p = ease(t, 3.3, 1.2)
    if p > 0:
        x_end = 300 + (1680 - 300) * p
        f.line([(300, 610), (300, 760), (x_end, 760)], GREEN, 10)
        if p >= 1:
            f.line([(1680, 760), (1680, 615)], GREEN, 10)
            f.d.polygon([(1680, 605), (1662, 635), (1698, 635)], fill=rgba(GREEN, 1))
    f.text((990, 820), "cash comes back to unit-holders", 40, (120, 220, 160), "s", a=ease(t, 4.3, 0.5))


def c1_90(f, t):
    f.text((W / 2, 230), "SEBI RULE", 56, GREY, "s", a=ease(t, 0, 0.4))
    f.stamp((W / 2, 500), "90%", 240, GREEN, back(t, 0.4), angle=-6)
    f.text((W / 2, 760), "of distributable cash, at least,", 46, WHITE, "s", a=ease(t, 1.0, 0.5))
    f.text((W / 2, 830), "must be paid out to unit-holders", 46, WHITE, "s", a=ease(t, 1.2, 0.5))


def c1_two(f, t):
    f.text((W / 2, 200), "InvIT kamai: two ways", 60, a=ease(t, 0, 0.4))
    a1, a2 = ease(t, 0.4, 0.5), ease(t, 1.4, 0.5)
    f.box(340, 380, 860, 700, BLUE, a=a1, r=26)
    f.text((600, 490), "1. PRICE", 60, a=a1)
    f.text((600, 590), "the unit's price rises", 34, WHITE, "r", a=a1)
    f.text((W / 2, 540), "+", 110, a=ease(t, 1.0, 0.3))
    f.box(1060, 380, 1580, 700, AMBER, a=a2, r=26)
    f.text((1320, 490), "2. DISTRIBUTIONS", 54, BG, a=a2)
    f.text((1320, 590), "cash, mostly every quarter", 34, BG, "s", a=a2)


def c1_mix(f, t):
    f.text((W / 2, 220), "A distribution is not all dividend", 58, a=ease(t, 0, 0.4))
    parts = [("Interest", BLUE), ("Dividend", GREEN), ("Your capital back", AMBER)]
    x = 300
    for i, (name, col) in enumerate(parts):
        a = ease(t, 0.5 + i * 0.5, 0.4)
        f.box(x, 460, x + 420, 620, col, a=a, r=14)
        f.text((x + 210, 540), name, 40, WHITE if col != AMBER else BG, a=a)
        x += 440
    f.text((W / 2, 760), "each part is taxed differently", 46, AMBER, "s", a=ease(t, 2.1, 0.5))
    f.text((W / 2, 830), "(the mix varies by InvIT and quarter)", 32, GREY, "r", a=ease(t, 2.4, 0.5))


def c2_formula(f, t):
    f.text((W / 2, 260), "TOTAL RETURN", 80, AMBER, "k", a=ease(t, 0, 0.5))
    f.text((W / 2, 400), "=", 80, a=ease(t, 0.4, 0.3))
    f.box(330, 470, 900, 650, BLUE, a=ease(t, 0.7, 0.4), r=22)
    f.text((615, 560), "Price change", 54, a=ease(t, 0.7, 0.4))
    f.text((W / 2, 560), "+", 80, a=ease(t, 1.0, 0.3))
    f.box(1020, 470, 1590, 650, GREEN, a=ease(t, 1.2, 0.4), r=22)
    f.text((1305, 560), "Cash received", 54, a=ease(t, 1.2, 0.4))
    f.text((W / 2, 760), "end-Dec 2025 to Sep 2026  |  Yahoo Finance daily closes + every payout", 34, GREY, "r",
           a=ease(t, 1.7, 0.5))


def c2_rule(f, t):
    f.text((W / 2, 250), "ONE STRICT RULE", 56, AMBER, "k", a=ease(t, 0, 0.4))
    f.box(330, 400, 1590, 640, PANEL, a=ease(t, 0.3, 0.4), r=26)
    f.text((W / 2, 480), "Could an ordinary retail investor", 52, a=ease(t, 0.4, 0.4))
    f.text((W / 2, 560), "actually buy it in January 2026?", 52, a=ease(t, 0.6, 0.4))
    f.stamp((W / 2, 790), "ONLY THEN IT COUNTS", 60, GREEN, back(t, 1.1), angle=0)


def c2_top5(f, t):
    f.text((W / 2, 260), "Aam nivesak ka", 56, GREY, "s", a=ease(t, 0, 0.4))
    f.stamp((W / 2, 480), "TOP 5", 200, AMBER, back(t, 0.3), angle=0)
    for i in range(5):
        a = ease(t, 0.9 + i * 0.15, 0.3)
        f.box(560 + i * 170, 700, 690 + i * 170, 830, PANEL, a=a, r=18)
        f.text((625 + i * 170, 765), f"#{5 - i}", 50, a=a)


def c3_payout(f, t):
    header(f, t, "IndiGrid: distribution per unit", "rose every year since 2019")
    base, unit = 900, 30.0
    for x, yr, v, col, st in [(700, "2019", 11.88, DIM, 0.4), (1220, "2025", 15.85, GREEN, 1.0)]:
        p = ease(t, st, 0.8)
        f.box(x - 130, base - v * unit * p, x + 130, base, col, r=10)
        f.text((x, base - v * unit - 44), rs(v), 50, a=ease(t, st + 0.6, 0.4))
        f.text((x, base + 40), yr, 36, GREY, "s")
    f.arrow(860, 520, 1060, ease(t, 1.6, 0.5), AMBER, 10)
    f.text((960, 470), "+33%", 54, AMBER, "k", a=ease(t, 1.9, 0.4))
    f.line([(480, base), (1440, base)], DIM, 4)


def c4_ilfs(f, t):
    f.text((W / 2, 240), "2018", 80, GREY, "k", a=ease(t, 0, 0.4))
    f.stamp((W / 2, 450), "IL&FS COLLAPSES", 110, RED, back(t, 0.4), angle=-4)
    f.text((W / 2, 650), "big infra lender, crushed under its debt", 46, WHITE, "s", a=ease(t, 1.0, 0.5))
    f.text((W / 2, 730), "its creditors wait years for their money", 40, GREY, "r", a=ease(t, 1.5, 0.5))


def c4_units(f, t):
    f.text((W / 2, 200), "2025 resolution: IL&FS toll roads → Roadstar InvIT", 50, a=ease(t, 0, 0.4))
    f.text((W / 2, 340), "Creditors got, instead of cash:", 46, GREY, "s", a=ease(t, 0.4, 0.4))
    p = ease(t, 0.8, 0.7)
    x = -400 + (W / 2 + 400) * p
    f.box(x - 300, 450, x + 300, 750, PANEL, r=26, outline=AMBER)
    f.text((x, 540), "UNITS", 70, AMBER, "k")
    f.text((x, 650), "face value Rs 100", 48)


def c4_price(f, t):
    header(f, t, "Roadstar: unit price", "creditors' face value Rs 100")
    pts = [("Face value", 100), ("Jul 2025", 80), ("Dec 2025", 60), ("Sep 2026", 62)]
    x0, x1, y_of = 420, 1500, (lambda v: 900 - (v - 40) * 9.0)
    xs = [x0 + (x1 - x0) * i / 3 for i in range(4)]
    f.line([(x0 - 60, y_of(100)), (x1 + 60, y_of(100))], DIM, 3, a=ease(t, 0.3))
    p = ease(t, 0.5, 2.6) * 3
    path = [(xs[0], y_of(100))]
    for i in range(1, 4):
        seg = min(1.0, max(0.0, p - (i - 1)))
        if seg <= 0:
            break
        path.append((xs[i - 1] + (xs[i] - xs[i - 1]) * seg, y_of(pts[i - 1][1]) + (y_of(pts[i][1]) - y_of(pts[i - 1][1])) * seg))
    f.line(path, RED, 10)
    for i, (label, v) in enumerate(pts):
        a = 1.0 if i == 0 else ease(t, 0.5 + i * 0.87, 0.3)
        f.d.ellipse((xs[i] - 14, y_of(v) - 14, xs[i] + 14, y_of(v) + 14), fill=rgba(WHITE, a))
        f.text((xs[i], y_of(v) - 56), f"~Rs {v}" if i in (1, 2) else f"Rs {v}", 46, a=a)
        f.text((xs[i], 960), label, 34, GREY, "s", a=a)


def c4_risk(f, t):
    f.text((W / 2, 220), "A creditor's Rs 100 today", 58, a=ease(t, 0, 0.4))
    f.text((W / 2, 400), "Rs 62 price  +  Rs 5.30 cash", 64, a=ease(t, 0.4, 0.5))
    f.text((W / 2, 530), "= ~Rs 67", 110, RED_TXT, "k", a=ease(t, 0.9, 0.5))
    f.stamp((W / 2, 790), "HIGHEST RISK", 100, RED, back(t, 1.5), angle=-5)


def c5_ipo(f, t):
    f.text((W / 2, 260), "MAY 2017", 64, GREY, "k", a=ease(t, 0, 0.4))
    f.text((W / 2, 400), "India's first listed InvIT", 66, a=ease(t, 0.4, 0.5))
    f.stamp((W / 2, 640), "IPO Rs 102", 130, AMBER, back(t, 0.9), angle=0)


def c5_today(f, t):
    f.text((W / 2, 260), "IPO Rs 102  →  aaj?", 60, GREY, "s", a=ease(t, 0, 0.4))
    v = 102 - 37 * ease(t, 0.3, 1.3)
    f.text((W / 2, 540), f"~Rs {v:.0f}", 200, RED_TXT, "k")
    f.text((W / 2, 780), "so how is it in the Top 3?", 46, WHITE, "s", a=ease(t, 1.8, 0.5))


def c5_cash42(f, t):
    header(f, t, "IRB since Jan 2023", "price roughly flat: ~Rs 66 then, ~Rs 65 now")
    f.text((W / 2, 400), "cash per unit: Rs 8 + Rs 8 + Rs 7.50 + Rs 4.73", 46, a=ease(t, 0.5, 0.5))
    f.text((W / 2, 480), "= Rs 28.2 on a ~Rs 66 unit", 46, GREY, "s", a=ease(t, 1.0, 0.5))
    f.stamp((W / 2, 700), "~Rs 42 cash per Rs 100", 96, GREEN, back(t, 1.5), angle=0)


def c5_note(f, t):
    f.box(330, 380, 1590, 700, PANEL, a=ease(t, 0, 0.4), r=26, outline=AMBER)
    f.text((W / 2, 470), "DATA NOTE", 48, AMBER, "k", a=ease(t, 0.1, 0.4))
    f.text((W / 2, 560), "IRB's price data before May 2022 isn't reliable,", 42, a=ease(t, 0.3, 0.4))
    f.text((W / 2, 625), "so no IPO-to-date total for IRB", 42, GREY, "s", a=ease(t, 0.5, 0.4))


def c6_line(f, t):
    header(f, t, "PowerGrid InvIT: unit price", "listed May 2021 at Rs 100")
    pts = [("May 2021", 100), ("End 2022", 127), ("End 2023", 96), ("End 2024", 85), ("End 2025", 90), ("Sep 2026", 101)]
    x0, x1, y_of = 300, 1620, (lambda v: 930 - (v - 70) * 9.5)
    xs = [x0 + (x1 - x0) * i / 5 for i in range(6)]
    p = ease(t, 0.4, 4.5) * 5
    path = [(xs[0], y_of(100))]
    for i in range(1, 6):
        seg = min(1.0, max(0.0, p - (i - 1)))
        if seg <= 0:
            break
        path.append((xs[i - 1] + (xs[i] - xs[i - 1]) * seg, y_of(pts[i - 1][1]) + (y_of(pts[i][1]) - y_of(pts[i - 1][1])) * seg))
    f.line(path, AMBER, 10)
    for i, (label, v) in enumerate(pts):
        a = 1.0 if i == 0 else ease(t, 0.4 + i * 0.9, 0.3)
        col = RED_TXT if i in (2, 3) else WHITE
        f.d.ellipse((xs[i] - 13, y_of(v) - 13, xs[i] + 13, y_of(v) + 13), fill=rgba(WHITE, a))
        below = i in (2, 3)  # the dips: label under the point, clear of the line
        f.text((xs[i], y_of(v) + (54 if below else -54)), f"~Rs {v}" if i else f"Rs {v}", 44, col, a=a)
        f.text((xs[i], 990), label, 32, GREY, "s", a=a)


def c6_clock(f, t):
    f.text((W / 2, 200), "Every quarter, like clockwork", 60, a=ease(t, 0, 0.4))
    for i in range(4):
        x = 480 + i * 320
        p = back(t, 0.4 + i * 0.45)
        if p > 0:
            r = 120 * min(p, 1.08)
            f.d.ellipse((x - r, 540 - r, x + r, 540 + r), fill=rgba(AMBER, 1))
            f.text((x, 540), "Rs 3", 64, BG, "k")
        f.text((x, 720), f"Q{i + 1}", 40, GREY, "s", a=ease(t, 0.4 + i * 0.45, 0.3))
    f.text((W / 2, 860), "Rs 3 per unit, every three months", 44, WHITE, "s", a=ease(t, 2.4, 0.5))


def c7_rename(f, t):
    old = Image.open(LOGOS / "bharat_highways.png").convert("RGBA")
    new = Image.open(LOGOS / "indus.png").convert("RGBA")
    scale = 520 / max(old.height, new.height)
    old = old.resize((int(old.width * scale), int(old.height * scale)), Image.LANCZOS)
    new = new.resize((int(new.width * scale), int(new.height * scale)), Image.LANCZOS)
    flip = ease(t, 1.2, 0.8)  # 0..0.5 squash the old card, 0.5..1 open the new one
    if flip < 0.5:
        f.paste(old, (W / 2, 520), a=ease(t, 0, 0.4), sx=1 - 2 * flip)
        f.text((W / 2, 900), "till Nov 2024: Bharat Highways InvIT", 44, GREY, "s", a=ease(t, 0.2, 0.4))
    else:
        f.paste(new, (W / 2, 520), sx=2 * flip - 1)
        f.text((W / 2, 900), "now: Indus Infra Trust", 48, WHITE, "s", a=ease(t, 2.0, 0.4))


def c8_rank(f, t):
    f.text((W / 2, 110), "2026 RANK (Jan-Sep total return)", 56, a=ease(t, 0, 0.4))
    rows = [("1", "Indus Infra Trust", 24.3), ("2", "PGInvIT", 22.7), ("3", "IRB InvIT", 11.4),
            ("4", "Roadstar", 10.9), ("5", "IndiGrid", 10.0)]
    for i, (rank, name, pct) in enumerate(rows):
        a = ease(t, 1.4 + i * 1.2, 0.4)
        y = 250 + i * 160
        f.box(360, y - 60, 1560, y + 60, PANEL, a=a, r=18)
        f.text((440, y), f"#{rank}", 52, AMBER, "k", a=a)
        f.text((530, y), name, 48, a=a, anchor="lm")
        bw = pct * 22 * ease(t, 1.5 + i * 1.2, 0.6)
        f.box(1000, y - 26, 1000 + bw, y + 26, GREEN, a=a, r=8)
        f.text((1020 + pct * 22, y), f"+{pct:.1f}%", 42, a=a, anchor="lm")


def c8_flip(f, t, rows_on=True):
    """Rs 100 on listing day, per InvIT; rows_on=False is the question alone."""
    f.text((W / 2, 100), "Rs 100 on listing day = aaj?", 58, AMBER, a=ease(t, 0, 0.4))
    rows = [("IndiGrid", 173.49, 121.32, "~Rs 295"), ("Indus", 133.97, 31.25, "~Rs 165"),
            ("PGInvIT", 101.0, 61.5, "~Rs 162"), ("Roadstar*", 62.0, 5.3, "~Rs 67"), ("IRB", None, None, "data n/a")]
    unit, x0 = 3.0, 560
    for i, (name, price, cash, label) in enumerate(rows if rows_on else []):
        st = 0.3 + i * 2.3
        a = ease(t, st, 0.4)
        y = 230 + i * 150
        f.text((x0 - 40, y), name, 46, a=a, anchor="rm")
        if price is None:
            f.text((x0, y), label, 42, GREY, "s", a=a, anchor="lm")
            continue
        p = ease(t, st + 0.2, 0.9)
        f.box(x0, y - 40, x0 + price * unit * p, y + 40, BLUE, a=a, r=8)
        if p >= 1:
            f.box(x0 + price * unit, y - 40, x0 + (price + cash * ease(t, st + 1.1, 0.7)) * unit, y + 40, GREEN, r=8)
        f.text((x0 + (price + cash) * unit + 30, y), label, 46, RED_TXT if price + cash < 100 else WHITE,
               "k", a=ease(t, st + 1.6, 0.4), anchor="lm")
    xr = x0 + 100 * unit
    f.line([(xr, 160), (xr, 900)], WHITE, 3, a=0.6 * ease(t, 0.3))
    f.text((xr, 940), "Rs 100", 30, GREY, "s", a=ease(t, 0.3))
    f.box(1260, 960, 1300, 990, BLUE, a=ease(t, 0.3), r=4)
    f.text((1315, 975), "price", 28, GREY, "r", a=ease(t, 0.3), anchor="lm")
    f.box(1440, 960, 1480, 990, GREEN, a=ease(t, 0.3), r=4)
    f.text((1495, 975), "cash paid out", 28, GREY, "r", a=ease(t, 0.3), anchor="lm")
    f.text((300, 1030), "* Roadstar: creditors' units at Rs 100 face value", 26, DIM, "r", a=ease(t, 9.5, 0.4), anchor="lm")


def c8_lesson(f, t):
    f.stamp((W / 2, 380), "1 YEAR'S RANK ≠ THE FULL STORY", 76, AMBER, back(t, 0.2), angle=0)
    f.text((W / 2, 640), "IndiGrid and PGInvIT made most of their money", 46, a=ease(t, 1.0, 0.5))
    f.text((W / 2, 715), "from distributions, not from price", 46, (120, 220, 160), "s", a=ease(t, 1.3, 0.5))


GRAPHICS = {
    "c0_invest": (2.0, c0_invest),
    "c0_today": (2.4, c0_today),
    "c0_cash": (3.2, c0_cash),
    "c0_rank5": (1.9, c0_rank5),
    "c1_flow": (5.0, c1_flow),
    "c1_90": (1.9, c1_90),
    "c1_two": (2.1, c1_two),
    "c1_mix": (3.0, c1_mix),
    "c2_formula": (2.4, c2_formula),
    "c2_rule": (1.8, c2_rule),
    "c2_out1": out_cards(1),
    "c2_out2": out_cards(2),
    "c2_out3": out_cards(3),
    "c2_top5": (1.8, c2_top5),
    "c3_payout": (2.5, c3_payout),
    "c4_ilfs": (2.1, c4_ilfs),
    "c4_units": (1.8, c4_units),
    "c4_price": (3.6, c4_price),
    "c4_risk": (2.1, c4_risk),
    "c5_ipo": (1.6, c5_ipo),
    "c5_today": (2.4, c5_today),
    "c5_cash42": (2.1, c5_cash42),
    "c5_note": (1.1, c5_note),
    "c6_line": (5.2, c6_line),
    "c6_zero": zero_sum("PowerGrid InvIT in 2024", "a bad year for the price", -12.39, 12.41, "TOTAL ~0%", AMBER),
    "c6_clock": (2.9, c6_clock),
    "c6_ipo": ipo_stack("PGInvIT", "listed May 2021", 101.0, 61.5, "~Rs 162"),
    "c7_rename": (2.4, c7_rename),
    "c7_ipo": ipo_stack("Indus Infra Trust", "listed Mar 2024", 133.97, 31.25, "~Rs 165"),
    "c8_rank": (7.2, c8_rank),
    "c8_flip_q": (0.8, lambda f, t: c8_flip(f, t, rows_on=False)),
    "c8_flip": (10.0, c8_flip),
    "c8_lesson": (1.8, c8_lesson),
    "c9_trap": zero_sum("Energy Infrastructure Trust, 2026", "gas pipelines InvIT", -17.0, 12.44, "TOTAL -4.6%", RED,
                        "institutional-only: not in the retail Top 5"),
    **{f"c9_check{k}": checklist(k) for k in range(5)},
}


def render(name, dur, draw):
    VIDEO_OUT.mkdir(parents=True, exist_ok=True)
    HOLD_OUT.mkdir(parents=True, exist_ok=True)
    out = VIDEO_OUT / f"{name}.mp4"
    n = max(1, round(dur * FPS))
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                             "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                             "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    last = None
    for i in range(n):
        f = Frame()
        draw(f, i / FPS)
        last = f.im.convert("RGB")
        proc.stdin.write(last.tobytes())
    proc.stdin.close()
    if proc.wait():
        sys.exit(f"ffmpeg failed on {name}")
    last.save(HOLD_OUT / f"{name}_hold.png")
    print(f"wrote {name} ({dur:.1f}s)")


if __name__ == "__main__":
    wanted = sys.argv[1:]
    for name, (dur, draw) in GRAPHICS.items():
        if not wanted or any(w in name for w in wanted):
            render(name, dur, draw)
