"""Build the 16:9 long-form video (scripts/youtube/00_longform_top10_passive_income_hindi.md).

  audio   voice every section with the same Parler voice as the shorts (sentence takes are cached),
          write assets/voiceover/hindi/longform/L<k>.wav and L<k>.json (sentence times)
  video   render each section (footage, banner, chapter card, synced text, animated chart), join them,
          and apply one loudness pass; prints YouTube chapter times

Usage (repo root):
  .venv-tts/bin/python dividend-income-2026/tools/make_longform.py audio 0 1 2     # CPU Parler: ~3 sections per process
  .venv-tts/bin/python dividend-income-2026/tools/make_longform.py video [--only 3] [--force]
Output: videos/longform/00_longform_top10_hindi.mp4
"""

import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
import build_short as B  # noqa: E402
from longform_data import SECTIONS  # noqa: E402

PROJECT, ASSETS = B.PROJECT, B.ASSETS
SCRIPT = PROJECT / "scripts" / "youtube" / "00_longform_top10_passive_income_hindi.md"
VO = ASSETS / "voiceover" / "hindi" / "longform"
WORK = B.WORK / "longform"
OUT = B.OUT / "longform"
W, H, FPS, GAP = 1920, 1080, 30, 0.3
CHART_AT = 2.4  # seconds into a chapter before the chart appears (the chapter card is up first)


def sections():
    s = SCRIPT.read_text(encoding="utf-8")
    return [(t, title, " ".join(vo.split())) for t, title, vo in re.findall(r"^### \[(.*?)\] (.*?)\n\*\*VO:\*\* \"(.*?)\"\n", s, re.M | re.S)]


# ------------------------------------------------------------------ audio
def audio(ks):
    from timing import build_text  # first: puts the voiceover package on sys.path
    from generate_voiceovers import DEFAULT_VOICES, VOICES
    params = VOICES[DEFAULT_VOICES["hindi"]][2]
    secs = sections()
    VO.mkdir(parents=True, exist_ok=True)
    (VO / "takes").mkdir(exist_ok=True)
    for k in ks:
        meta = build_text(secs[k][2], params, 1.1, VO / "takes", VO / f"L{k}.wav")
        (VO / f"L{k}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"L{k} {secs[k][1]}: {meta['duration']:.1f}s, {len(meta['sentences'])} sentences", flush=True)


# ------------------------------------------------------------------ overlays
def group_png(lines, dest, width=740):  # plate ends at x=860, left of the chart panel (x=880)
    first, rest = B.font(54), B.font(46)
    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    rows = []
    for i, ln in enumerate(lines):
        f = first if i == 0 else rest
        for part in B.wrap(probe, ln, f, width):
            rows.append((part, f, B.ACCENT if i == 0 else B.WHITE, 66 if i == 0 else 58))
    h = sum(r[3] for r in rows) + 44
    img = Image.new("RGBA", (width + 60, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, width + 60, h), 28, fill=(0, 0, 0, 150))
    y = 22
    for text, f, color, step in rows:
        d.text((30, y), text, font=f, fill=color)
        y += step
    img.save(dest)


def banner_wide(rank, name, yld, dest):
    img = Image.new("RGBA", (900, 120), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, 900, 120), 36, fill=(0, 0, 0, 175))
    d.text((40, 60), f"#{rank}", font=B.font(70), fill=B.ACCENT, anchor="lm")
    x0 = 40 + d.textlength(f"#{rank}", font=B.font(70)) + 28
    chip = f"{yld}% YIELD"
    d.text((870, 60), chip, font=B.font(38), fill=B.GREEN, anchor="rm")
    size, room = 52, 870 - d.textlength(chip, font=B.font(38)) - x0 - 24
    while d.textlength(name.upper(), font=B.font(size)) > room:
        size -= 2
    d.text((x0, 60), name.upper(), font=B.font(size), fill=B.WHITE, anchor="lm")
    img.save(dest)


def card_png(rank, name, dest):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((360, 330, W - 360, 750), 60, fill=(0, 0, 0, 185))
    d.text((W / 2, 480), rank, font=B.font(190), fill=B.ACCENT, anchor="mm", stroke_width=4, stroke_fill=(0, 0, 0, 255))
    d.text((W / 2, 660), name, font=B.font(96), fill=B.WHITE, anchor="mm", stroke_width=3, stroke_fill=(0, 0, 0, 255))
    img.save(dest)


def footer_wide(dest):
    img = Image.new("RGBA", (W, 70), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((420, 6, W - 420, 64), 26, fill=(0, 0, 0, 150))
    d.text((W / 2, 35), "Not investment advice | Pre-tax | Past is not future", font=B.font(28, False), fill=(240, 240, 240, 255), anchor="mm")
    img.save(dest)


def delayed(frames_fn, delay, w=1000, h=640):
    """Transparent frames for `delay` seconds, then the animation."""
    def run(stdin, seconds):
        blank = bytes(w * h * 4)
        for _ in range(int(delay * FPS)):
            stdin.write(blank)
        frames_fn(stdin, max(0.1, seconds - delay))
    return run


def yield_frames(rows, stdin, seconds):
    """Horizontal bars of the ten yields, growing in."""
    cw, ch = 1000, 640
    top = max(v for _, v in rows) * 1.12
    for f in range(int(seconds * FPS)):
        grow = 1 - (1 - min(1.0, f / (FPS * 2.0))) ** 3
        img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((0, 0, cw, ch), 36, fill=(8, 12, 22, 205))
        d.text((40, 22), "Dividend yield today, top 10 (%)", font=B.font(34), fill=B.WHITE)
        for i, (name, v) in enumerate(rows):
            y = 90 + i * 53
            d.text((40, y + 20), name, font=B.font(27, False), fill=B.DIM, anchor="lm")
            wbar = (cw - 330) * v / top * grow
            d.rounded_rectangle((250, y + 4, 250 + max(6, wbar), y + 38), 8, fill=B.ACCENT if i == 0 else (90, 160, 255))
            if grow > 0.9:
                d.text((250 + wbar + 12, y + 21), f"{v + 1e-6:.1f}", font=B.font(27), fill=B.WHITE, anchor="lm")
        stdin.write(img.tobytes())


# ------------------------------------------------------------------ video
def norm_wide(name):
    dest = WORK / "clips" / f"{name.replace('/', '_')}.mp4"
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        B.run(["ffmpeg", "-v", "error", "-y", "-i", ASSETS / "videos" / f"{name}.mp4", "-t", 16, "-an",
               "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},eq=brightness=-0.14:saturation=1.1",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", 22, "-pix_fmt", "yuv420p", dest])
    return dest


def render_section(k, force):
    sec = SECTIONS[k]
    dest = WORK / f"sec_{k:02d}.mp4"
    meta = json.loads((VO / f"L{k}.json").read_text(encoding="utf-8"))
    dur = meta["duration"] + GAP
    if dest.exists() and not force:
        return dest, dur
    work = WORK / f"s{k:02d}"
    work.mkdir(parents=True, exist_ok=True)
    clips = [norm_wide(c) for c in sec["clips"]]
    listing, total, i = work / "bg.txt", 0.0, 0
    with open(listing, "w") as f:
        while total < dur + 1:
            c = clips[i % len(clips)]
            f.write(f"file '{c}'\n")
            total += min(16.0, B.duration(c))
            i += 1
    inputs = ["-f", "concat", "-safe", "0", "-i", listing, "-i", VO / f"L{k}.wav"]
    chain = [f"[0:v]trim=duration={dur:.3f},setpts=PTS-STARTPTS,fps={FPS},drawbox=x=0:y=0:w=1920:h=1080:color=black@0.22:t=fill[bg]"]
    last, idx = "bg", 2

    def add(png, x, y, fade_in=None, fade_out=None, loop=True):
        nonlocal last, idx
        inputs.extend(["-loop", "1", "-i", png] if loop else ["-i", png])
        f = "format=rgba"
        if fade_in is not None:
            f += f",fade=in:st={fade_in:.2f}:d=0.3:alpha=1"
        if fade_out is not None:
            f += f",fade=out:st={fade_out:.2f}:d=0.3:alpha=1"
        chain.append(f"[{idx}:v]{f}[o{idx}]")
        chain.append(f"[{last}][o{idx}]overlay={x}:{y}[v{idx}]")
        last, idx = f"v{idx}", idx + 1

    rows_top = None
    if sec["symbol"] and sec["symbol"] != "BASKET":
        top10 = {r["symbol"]: r for r in csv.DictReader(open(PROJECT / "data" / "top10.csv"))}
        metrics = {r["symbol"]: r for r in json.loads((PROJECT / "data" / "stocks_metrics.json").read_text())}
        row = metrics[sec["symbol"]]
        rank = int(sec["card"][0][1:])
        banner_wide(rank, sec["card"][1], f"{float(top10[sec['symbol']]['screener_yield_pct']) + 1e-6:.1f}", work / "banner.png")
        add(work / "banner.png", 40, 30)
        card_png(sec["card"][0], sec["card"][1], work / "card.png")
        add(work / "card.png", 0, 0, fade_in=0.15, fade_out=2.0)
        series = {int(a): v for a, v in row["fy_divs"].items() if 2017 <= int(a) <= 2026}
        first = min(a for a, v in series.items() if v > 0)
        series = {a: v for a, v in series.items() if a >= first}
        panel = lambda stdin, secs: B.chart_frames(series, stdin, secs)
    elif sec["symbol"] == "BASKET":
        top10 = list(csv.DictReader(open(PROJECT / "data" / "top10.csv")))
        names = {"COALINDIA": "Coal India", "RECLTD": "REC", "PFC": "PFC", "ITC": "ITC", "CESC": "CESC", "INFY": "Infosys",
                 "HCLTECH": "HCL Tech", "HUDCO": "HUDCO", "POWERGRID": "Power Grid", "HEROMOTOCO": "Hero MotoCorp"}
        rows_top = [(names[r["symbol"]], float(r["screener_yield_pct"])) for r in top10 if r["symbol"] in names]
        panel = lambda stdin, secs: yield_frames(rows_top, stdin, secs)
    else:
        panel = None

    # synced text groups: each stays until the next one appears
    starts = [B.line_start(meta, g[0], g[2]) for g in sec["groups"]]
    for n, (g, start) in enumerate(zip(sec["groups"], starts)):
        end = starts[n + 1] if n + 1 < len(starts) else None
        png = work / f"g{n}.png"
        group_png(g[1], png)
        add(png, 60, 250, fade_in=start, fade_out=(end - 0.25) if end else None)
    add(WORK / "footer.png", 0, 1000)
    if panel:
        inputs.extend(["-f", "rawvideo", "-pix_fmt", "rgba", "-s", "1000x640", "-r", str(FPS), "-i", "-"])
        chain.append(f"[{idx}:v]format=rgba[chart]")
        chain.append(f"[{last}][chart]overlay=880:260[vc]")
        last = "vc"
    cmd = ["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(chain), "-map", f"[{last}]", "-map", "1:a",
           "-af", f"apad=pad_dur={GAP}", "-t", f"{dur:.3f}", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", str(dest)]
    cmd = [str(c) for c in cmd]
    if panel:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        try:
            delayed(panel, CHART_AT if sec["symbol"] != "BASKET" else 2.0)(proc.stdin, dur)
        except BrokenPipeError:
            pass
        proc.stdin.close()
        if proc.wait():
            raise SystemExit(f"ffmpeg failed for section {k}")
    else:
        subprocess.run(cmd, check=True)
    return dest, dur


def video(only, force):
    WORK.mkdir(parents=True, exist_ok=True)
    footer_wide(WORK / "footer.png")
    secs = sections()
    parts, starts, t = [], [], 0.0
    for k in range(len(SECTIONS)):
        if only is not None and k != only:
            continue
        path, dur = render_section(k, force)
        parts.append(path)
        starts.append((t, secs[k][1]))
        t += B.duration(path)
        print(f"  section {k} {secs[k][1]}  {B.duration(path):.1f}s", flush=True)
    if only is not None:
        return
    OUT.mkdir(parents=True, exist_ok=True)
    listing = WORK / "concat.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in parts))
    joined = WORK / "joined.mp4"
    B.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", 0, "-i", listing, "-c", "copy", joined])
    final = OUT / "00_longform_top10_hindi.mp4"
    B.run(["ffmpeg", "-v", "error", "-y", "-i", joined, "-c:v", "copy", "-af", "loudnorm=I=-16:TP=-1.5:LRA=9",
           "-c:a", "aac", "-b:a", "160k", "-ar", 44100, final])
    print(f"\n{final}  {B.duration(final) / 60:.1f} min\nChapters:")
    for s, title in starts:
        print(f"{int(s // 60)}:{int(s % 60):02d} {title}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["audio", "video"])
    ap.add_argument("sections", nargs="*", type=int)
    ap.add_argument("--only", type=int)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if args.mode == "audio":
        audio(args.sections or range(len(SECTIONS)))
    else:
        video(args.only, args.force)


if __name__ == "__main__":
    main()
