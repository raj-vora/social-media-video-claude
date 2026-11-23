"""Build the vertical (1080x1920) dividend shorts with ffmpeg: stock footage, on-screen
text from each script section, an animated dividend-per-share chart on the proof
section, and the Parler voiceover.

For each short it renders one clip per body section (sections 2-5) and one per hook
(H1 = section 1 of the voiceover, H2..H5 from hooks/), then joins hook + body, so five
A/B versions cost one body render. Output: videos/<short>_H<i>.mp4 (gitignored previews).

Usage (repo root):
  .venv-tts/bin/python dividend-income-2026/tools/build_short.py [01_coal] [--hooks 1,2,3,4,5] [--force]
Needs the voiceover (generate_voiceovers.py --project dividend-income-2026), the hook
renders (tools/render_hooks.py) and the footage (tools/fetch_footage.py).
"""

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from overlays import CTA, OVERLAYS  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
PROJECT = REPO / "dividend-income-2026"
ASSETS = PROJECT / "assets"
OUT = PROJECT / "videos"
WORK = REPO / ".cache" / "dividend_build"
W, H, FPS = 1080, 1920, 30
GAP = 0.25  # silence after each section, as generate_voiceovers.MIN_GAP
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
ACCENT, WHITE, DIM, GREEN = (255, 214, 64), (255, 255, 255), (205, 210, 220), (120, 230, 150)
LEAD = 0.25  # seconds a line appears before the narrator's word

# footage pool per short (the euro-coin and dollar-note clips were dropped as not Indian); hook i uses pool[i % len], who/risk use the first two,
# the proof section the last (money / finance b-roll behind the chart).
POOLS = {
    "01_coal_india": ["coal_mining/coal_mining_01", "coal_mining/coal_mining_02", "power_lines/power_lines_03", "savings/savings_01"],
    "02_rec": ["power_lines/power_lines_01", "power_lines/power_lines_02", "savings/savings_01", "money/money_03"],
    "03_pfc": ["power_lines/power_lines_02", "power_lines/power_lines_01", "savings/savings_01", "money/money_03"],
    "04_itc": ["retail_food/retail_food_02", "savings/savings_01", "retail_food/retail_food_02", "money/money_03"],
    "05_cesc": ["city_night/city_night_01", "city_night/city_night_02", "power_lines/power_lines_01", "savings/savings_01"],
    "06_infosys": ["it_office/it_office_07", "it_office/it_office_04", "it_office/it_office_08", "money/money_03"],
    "07_hcl_tech": ["it_office/it_office_08", "it_office/it_office_09", "it_office/it_office_04", "savings/savings_01"],
    "08_hudco": ["housing/housing_02", "city_night/city_night_03", "money/money_03", "money/money_03"],
    "09_power_grid": ["power_lines/power_lines_01", "power_lines/power_lines_02", "power_lines/power_lines_04", "savings/savings_01"],
    "10_hero_motocorp": ["motorbikes/motorbikes_04", "motorbikes/motorbikes_01", "city_night/city_night_02", "savings/savings_01"],
}
SYMBOLS = {"01_coal_india": "COALINDIA", "02_rec": "RECLTD", "03_pfc": "PFC", "04_itc": "ITC", "05_cesc": "CESC",
           "06_infosys": "INFY", "07_hcl_tech": "HCLTECH", "08_hudco": "HUDCO", "09_power_grid": "POWERGRID",
           "10_hero_motocorp": "HEROMOTOCO"}


def run(cmd, **kw):
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
                         capture_output=True, text=True, check=True)
    return float(out.stdout)


def font(size, bold=True):
    return ImageFont.truetype(BOLD if bold else REG, size)


def wrap(draw, text, fnt, width):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=fnt) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + [line]


def text_png(text, dest, size, color, width=940):
    """One on-screen line (wrapped) as a transparent PNG with a dark outline."""
    fnt = font(size)
    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    lines = wrap(probe, text.replace(" -> ", " → "), fnt, width)
    h = int(len(lines) * size * 1.22) + 24
    img = Image.new("RGBA", (W, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        d.text((W / 2, 12 + i * size * 1.22), ln, font=fnt, fill=color, anchor="ma", stroke_width=6, stroke_fill=(0, 0, 0, 255))
    img.save(dest)
    return h


def banner_png(rank, name, yld, dest):
    img = Image.new("RGBA", (W, 230), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((40, 30, W - 40, 190), 40, fill=(0, 0, 0, 170))
    d.text((80, 110), f"#{rank}", font=font(72), fill=ACCENT, anchor="lm")
    chip = f"{yld}% YIELD"
    d.text((W - 80, 110), chip, font=font(40), fill=GREEN, anchor="rm")
    x0 = 80 + d.textlength(f"#{rank}", font=font(72)) + 30
    room = W - 80 - d.textlength(chip, font=font(40)) - x0 - 25
    size = 56
    while d.textlength(name.upper(), font=font(size)) > room:  # long names (Hero MotoCorp) shrink to fit
        size -= 2
    d.text((x0, 110), name.upper(), font=font(size), fill=WHITE, anchor="lm")
    img.save(dest)


def footer_png(dest):
    img = Image.new("RGBA", (W, 100), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((90, 14, W - 90, 86), 30, fill=(0, 0, 0, 150))
    d.text((W / 2, 50), "Not investment advice | Pre-tax | Past is not future", font=font(30, False), fill=(240, 240, 240, 255), anchor="mm")
    img.save(dest)


def chart_frames(series, dest_stdin, seconds, title="Dividend per share (₹), by fiscal year"):
    """Animated dividend-per-share bars, written as raw RGBA frames to ffmpeg's stdin."""
    cw, ch = 1000, 640
    years = list(series)
    top = max(series.values()) * 1.15
    n = int(seconds * FPS)
    for f in range(n):
        t = min(1.0, f / (FPS * 2.2))
        grow = 1 - (1 - t) ** 3
        img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((0, 0, cw, ch), 36, fill=(8, 12, 22, 200))
        d.text((40, 24), title, font=font(34), fill=WHITE)
        base, plot_h = ch - 80, ch - 200
        bw = (cw - 80) / len(years)
        for i, y in enumerate(years):
            v = series[y]
            hgt = plot_h * v / top * grow
            x0 = 40 + i * bw + bw * 0.14
            last = i == len(years) - 1
            cx = x0 + bw * 0.36
            if v > 0:
                d.rounded_rectangle((x0, base - hgt, x0 + bw * 0.72, base), 8, fill=ACCENT if last else (90, 160, 255))
            d.text((cx, base + 8), f"'{str(y)[2:]}", font=font(30, False), fill=DIM, anchor="ma")
            if grow > 0.9:
                label = "none" if v == 0 else f"{v:.0f}" if v >= 100 else f"{v:.1f}"
                d.text((cx, base - hgt - 6), label, font=font(27), fill=WHITE if v else DIM, anchor="ms")
        dest_stdin.write(img.tobytes())


def norm_clip(name, seconds):
    """Footage cropped to 1080x1920, 30 fps, no audio, cached."""
    dest = WORK / "clips" / f"{name.replace('/', '_')}.mp4"
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        run(["ffmpeg", "-v", "error", "-y", "-i", ASSETS / "videos" / f"{name}.mp4", "-t", 16, "-an",
             "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},eq=brightness=-0.12:saturation=1.1",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", 22, "-pix_fmt", "yuv420p", dest])
    return dest


def render_segment(dest, clip, audio, texts, banner, footer, series, shade=0.0, chart_title=None, shade_h=640):
    """One section: footage + banner + staggered text lines (+ chart) over the voiceover."""
    dur = duration(audio) + GAP
    inputs = ["-stream_loop", "-1", "-i", clip, "-i", audio, "-i", banner, "-i", footer]
    chain = [f"[0:v]trim=duration={dur:.3f},setpts=PTS-STARTPTS[bg]", (f"[bg]drawbox=x=0:y=330:w=1080:h={shade_h}:color=black@{shade}:t=fill:enable='gte(t,{texts[0][2] - 0.1:.2f})'[bg2];[bg2]" if shade and texts else "[bg]") + "[2:v]overlay=0:90[v1]", "[v1][3:v]overlay=0:1640[v2]"]
    last, idx, y = "v2", 4, 380
    for k, (png, h, start) in enumerate(texts):
        inputs += ["-loop", "1", "-i", png]
        chain.append(f"[{idx}:v]format=rgba,fade=in:st={start:.2f}:d=0.35:alpha=1[t{k}]")
        chain.append(f"[{last}][t{k}]overlay=0:{y}:enable='gte(t,{start:.2f})'[o{k}]")
        last, idx, y = f"o{k}", idx + 1, y + h + 10
    proc = None
    if series:
        inputs += ["-f", "rawvideo", "-pix_fmt", "rgba", "-s", "1000x640", "-r", FPS, "-i", "-"]
        chain.append(f"[{idx}:v]fade=in:st=0.4:d=0.4:alpha=1[ch]")
        chain.append(f"[{last}][ch]overlay=40:990:enable='gte(t,0.4)'[oc]")
        last = "oc"
    cmd = ["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(chain), "-map", f"[{last}]", "-map", "1:a",
           "-af", f"apad=pad_dur={GAP}", "-t", f"{dur:.3f}", "-r", FPS, "-c:v", "libx264", "-preset", "veryfast", "-crf", 23,
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-ar", 44100, "-ac", 2, dest]
    cmd = [str(c) for c in cmd]
    if series:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        try:
            chart_frames(series, proc.stdin, dur, *([chart_title] if chart_title else []))
        except BrokenPipeError:
            pass
        proc.stdin.close()
        if proc.wait():
            raise SystemExit(f"ffmpeg failed for {dest}")
    else:
        subprocess.run(cmd, check=True)


def line_start(timing, sentence, keyword):
    """When a line appears: the sentence start, or the keyword's estimated moment inside it."""
    s = timing["sentences"][sentence]
    if not keyword:
        return max(0.1, s["start"] - 0.05)
    pos = s["text"].find(keyword)
    if pos < 0:
        raise SystemExit(f"keyword {keyword!r} not in sentence {sentence}: {s['text']}")
    return max(0.1, s["start"] + pos / len(s["text"]) * (s["end"] - s["start"]) - LEAD)


def build(stem, hooks, force):
    short = stem.removesuffix("_short_hindi")
    n = int(short[:2])
    metrics = {r["symbol"]: r for r in json.loads((PROJECT / "data" / "stocks_metrics.json").read_text())}
    row = metrics[SYMBOLS[short]]
    top10 = {r["symbol"]: r for r in csv.DictReader(open(PROJECT / "data" / "top10.csv"))}
    yield_pct = f"{float(top10[SYMBOLS[short]]['screener_yield_pct']) + 1e-6:.1f}"  # 4.25 shows as 4.3
    series = {int(k): v for k, v in row["fy_divs"].items() if 2017 <= int(k) <= 2026}
    first = min(k for k, v in series.items() if v > 0)  # drop pre-listing years, keep real gaps
    series = {k: v for k, v in series.items() if k >= first}
    vo_dir = ASSETS / "voiceover" / "hindi" / stem / "timed"
    timing = json.loads((vo_dir / "timing.json").read_text(encoding="utf-8"))
    pool = POOLS[short]
    work = WORK / short
    work.mkdir(parents=True, exist_ok=True)
    banner, footer = work / "banner.png", work / "footer.png"
    banner_png(n, row["name"], yield_pct, banner)
    footer_png(footer)

    def lines(key):
        """(png, height, start) per on-screen line of segment `key`, synced to the voiceover."""
        items = OVERLAYS[short][key]
        size = 88 if len(items) <= 3 else 64 if len(items) <= 5 else 52
        out = []
        for k, item in enumerate(items):
            sentence, text, keyword = (*item, None)[:3]
            png = work / f"{key}_{k}.png"
            sz = size if len(text) < 26 else int(size * 0.82)
            h = text_png(text, png, sz, GREEN if text == CTA else ACCENT if k == 0 else WHITE)
            out.append((png, h, line_start(timing[key], sentence, keyword)))
        return out

    clips = [norm_clip(c, 16) for c in pool]
    body = []
    for i in (2, 3, 4, 5):  # script sections 2..5
        dest = work / f"body_{i}.mp4"
        if force or not dest.exists():
            clip = clips[-1] if i == 3 else clips[0] if i == 5 else clips[(i - 2) % len(clips)]
            render_segment(dest, clip, vo_dir / f"S{i}.wav", lines(f"S{i}"), banner, footer, series if i == 3 else None, shade=0.42 if i in (3, 4) else 0)
        body.append(dest)
    OUT.mkdir(exist_ok=True)
    for h in hooks:
        key = "S1" if h == 1 else f"H{h}"
        hook_mp4 = work / f"hook_{h}.mp4"
        if force or not hook_mp4.exists():
            render_segment(hook_mp4, clips[(h - 1) % len(clips)], vo_dir / f"{key}.wav", lines(key), banner, footer, None)
        listing = work / f"concat_{h}.txt"
        listing.write_text("".join(f"file '{p}'\n" for p in [hook_mp4, *body]))
        final = OUT / f"{short}_H{h}.mp4"
        run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", 0, "-i", listing, "-c", "copy", final])
        print(f"  {final.name}  {duration(final):.1f}s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("only", nargs="?", default="")
    ap.add_argument("--hooks", default="1,2,3,4,5")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    for path in sorted((PROJECT / "scripts" / "youtube").glob("*_short_hindi.md")):
        if args.only in path.stem:
            print(path.stem)
            build(path.stem, [int(h) for h in args.hooks.split(",")], args.force)


if __name__ == "__main__":
    sys.exit(main())
