"""Build the 16:9 ex-dividend long form (scripts/00_longform_exdiv_hindi.md) with the dividend
series' voice and look (make_longform.py): Parler voiceover per section, footage, chapter cards,
synced text, and a right-hand panel (payout table, dividend chart or the yield bars).

Usage (repo root):
  .venv-tts/bin/python exdiv-nov-2026/tools/make_exdiv_longform.py audio [0 1 2 ...]
  .venv-tts/bin/python exdiv-nov-2026/tools/make_exdiv_longform.py video [--only 3] [--force]
Output: exdiv-nov-2026/videos/00_longform_exdiv_hindi.mp4 (gitignored); prints YouTube chapters.
"""

import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
REPO = PROJECT.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "dividend-income-2026" / "tools"))
import build_short as B  # noqa: E402
import make_longform as ML  # noqa: E402
from longform_sections import SECTIONS  # noqa: E402
from make_exdiv import CHART_TITLE, cash_series  # noqa: E402

from PIL import Image, ImageDraw  # noqa: E402

SCRIPT = PROJECT / "scripts" / "00_longform_exdiv_hindi.md"
VO = PROJECT / "assets" / "voiceover" / "longform"
WORK = REPO / ".cache" / "exdiv_build" / "longform"
OUT = PROJECT / "videos"
W, H, FPS, GAP = ML.W, ML.H, ML.FPS, ML.GAP
PW, PH = 1000, 640


def sections():
    s = SCRIPT.read_text(encoding="utf-8")
    return [(t, title, " ".join(vo.split()))
            for t, title, vo in re.findall(r"^### \[(.*?)\] (.*?)\n\*\*VO:\*\* \"(.*?)\"\n", s, re.M | re.S)]


def table_rows():
    with open(PROJECT / "data" / "exdiv_table.csv", newline="") as f:
        return list(csv.DictReader(f))


def audio(ks):
    from timing import build_text  # puts the voiceover package on sys.path
    from generate_voiceovers import DEFAULT_VOICES, VOICES
    params = VOICES[DEFAULT_VOICES["hindi"]][2]
    secs = sections()
    (VO / "takes").mkdir(parents=True, exist_ok=True)
    for k in ks:
        meta = build_text(secs[k][2], params, 1.1, VO / "takes", VO / f"L{k}.wav")
        (VO / f"L{k}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"L{k} {secs[k][1]}: {meta['duration']:.1f}s, {len(meta['sentences'])} sentences", flush=True)


# ------------------------------------------------------------------ panels
def table_frames(record, stdin, seconds):
    """The six payouts of one record date: name, ₹ a share, % of the share price; rows slide in."""
    rows = [r for r in table_rows() if r["record_date"] == record]
    for f in range(int(seconds * FPS)):
        t = f / FPS
        img = Image.new("RGBA", (PW, PH), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((0, 0, PW, PH), 36, fill=(8, 12, 22, 205))
        day = int(record[-2:])
        d.text((40, 24), f"Record date {day} Nov 2026", font=B.font(34), fill=B.WHITE)
        d.text((560, 92), "₹ / SHARE", font=B.font(26, False), fill=B.DIM, anchor="ma")
        d.text((840, 92), "% OF PRICE", font=B.font(26, False), fill=B.DIM, anchor="ma")
        for i, r in enumerate(rows):
            a = min(1.0, max(0.0, (t - 0.3 * i) / 0.4))
            if a <= 0:
                continue
            y = 140 + i * 80
            col = lambda c: (*c, int(255 * a))
            d.text((40, y + 26), r["name"].replace(" Energy & Mobility", "").replace(" Network", ""), font=B.font(34),
                   fill=col(B.WHITE), anchor="lm")
            amt = float(r["amount"])
            d.text((560, y + 26), f"{amt:g}" if amt == int(amt) else f"{amt:.2f}", font=B.font(36), fill=col(B.ACCENT), anchor="mm")
            d.text((840, y + 26), f"{float(r['payout_yield_pct']):.2f}%", font=B.font(36), fill=col(B.GREEN), anchor="mm")
        stdin.write(img.tobytes())


def yields_frames(stdin, seconds):
    """Payout yield (this dividend) and 12-month yield for all twelve, as paired bars."""
    rows = sorted(table_rows(), key=lambda r: -float(r["ttm_yield_pct"]))
    top = max(float(r["ttm_yield_pct"]) for r in rows) * 1.12
    for f in range(int(seconds * FPS)):
        grow = 1 - (1 - min(1.0, f / (FPS * 2.0))) ** 3
        img = Image.new("RGBA", (PW, PH), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((0, 0, PW, PH), 36, fill=(8, 12, 22, 205))
        d.text((40, 20), "Yield, % of share price", font=B.font(32), fill=B.WHITE)
        d.rounded_rectangle((560, 30, 584, 50), 5, fill=B.ACCENT)
        d.text((592, 40), "this dividend", font=B.font(22, False), fill=B.DIM, anchor="lm")
        d.rounded_rectangle((760, 30, 784, 50), 5, fill=(90, 160, 255))
        d.text((792, 40), "12 months", font=B.font(22, False), fill=B.DIM, anchor="lm")
        for i, r in enumerate(rows):
            y = 76 + i * 46
            name = r["name"].replace(" Energy & Mobility", "").replace(" Network", "").replace(" Beverages", " Bev.").replace(" Fasteners", "")
            d.text((40, y + 19), name, font=B.font(24, False), fill=B.DIM, anchor="lm")
            ttm, pay = float(r["ttm_yield_pct"]), float(r["payout_yield_pct"])
            full = (PW - 380) * grow
            d.rounded_rectangle((270, y + 4, 270 + max(4, full * ttm / top), y + 34), 7, fill=(90, 160, 255))
            d.rounded_rectangle((270, y + 4, 270 + max(4, full * pay / top), y + 34), 7, fill=B.ACCENT)
            if grow > 0.9:
                d.text((270 + full * ttm / top + 12, y + 19), f"{ttm:.2f}", font=B.font(24), fill=B.WHITE, anchor="lm")
        stdin.write(img.tobytes())


def panel_fn(panel):
    if not panel:
        return None
    if panel[0] == "table":
        return lambda stdin, secs: table_frames(panel[1], stdin, secs)
    if panel[0] == "yields":
        return yields_frames
    series = cash_series(panel[1])
    first = min(y for y, v in series.items() if v > 0)
    series = {y: v for y, v in series.items() if y >= first}
    return lambda stdin, secs: B.chart_frames(series, stdin, secs, CHART_TITLE)


# ------------------------------------------------------------------ video
def render_section(k, force):
    sec = SECTIONS[k]
    dest = WORK / f"sec_{k:02d}.mp4"
    meta = json.loads((VO / f"L{k}.json").read_text(encoding="utf-8"))
    dur = meta["duration"] + GAP
    if dest.exists() and not force:
        return dest, dur
    work = WORK / f"s{k:02d}"
    work.mkdir(parents=True, exist_ok=True)
    clips = [ML.norm_wide(c) for c in sec["clips"]]
    listing, total, i = work / "bg.txt", 0.0, 0
    with open(listing, "w") as f:
        while total < dur + 1:
            c = clips[i % len(clips)]
            f.write(f"file '{c}'\n")
            total += min(16.0, B.duration(c))
            i += 1
    inputs = ["-f", "concat", "-safe", "0", "-i", listing, "-i", VO / f"L{k}.wav"]
    chain = [f"[0:v]trim=duration={dur:.3f},setpts=PTS-STARTPTS,fps={FPS},drawbox=x=0:y=0:w=1920:h=1080:color=black@0.25:t=fill[bg]"]
    last, idx = "bg", 2

    def add(png, x, y, fade_in=None, fade_out=None):
        nonlocal last, idx
        inputs.extend(["-loop", "1", "-i", png])
        f = "format=rgba"
        if fade_in is not None:
            f += f",fade=in:st={fade_in:.2f}:d=0.3:alpha=1"
        if fade_out is not None:
            f += f",fade=out:st={fade_out:.2f}:d=0.3:alpha=1"
        chain.append(f"[{idx}:v]{f}[o{idx}]")
        chain.append(f"[{last}][o{idx}]overlay={x}:{y}[v{idx}]")
        last, idx = f"v{idx}", idx + 1

    if sec["card"]:
        ML.card_png(sec["card"][0], sec["card"][1], work / "card.png")
        add(work / "card.png", 0, 0, fade_in=0.15, fade_out=2.0)
    starts = [B.line_start(meta, g[0], g[2]) for g in sec["groups"]]
    if sec["card"]:  # text waits for the chapter card to clear
        starts = [max(s, 2.35) for s in starts]
    for n, (g, start) in enumerate(zip(sec["groups"], starts)):
        end = starts[n + 1] if n + 1 < len(starts) else None
        png = work / f"g{n}.png"
        ML.group_png(g[1], png)
        add(png, 60, 250, fade_in=start, fade_out=(end - 0.25) if end else None)
    add(WORK / "footer.png", 0, 1000)
    panel = panel_fn(sec["panel"])
    if panel:
        inputs.extend(["-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{PW}x{PH}", "-r", str(FPS), "-i", "-"])
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
            ML.delayed(panel, ML.CHART_AT if sec["card"] else 0.6)(proc.stdin, dur)
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
    ML.footer_wide(WORK / "footer.png")
    secs = sections()
    assert len(secs) == len(SECTIONS), f"script has {len(secs)} sections, longform_sections.py {len(SECTIONS)}"
    parts, starts, t = [], [], 0.0
    for k in range(len(SECTIONS)):
        if only is not None and k != only:
            continue
        path, _ = render_section(k, force)
        parts.append(path)
        starts.append((t, secs[k][1]))
        t += B.duration(path)
        print(f"  section {k} {secs[k][1]}  {B.duration(path):.1f}s", flush=True)
    if only is not None:
        return
    OUT.mkdir(parents=True, exist_ok=True)
    listing = WORK / "concat.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in parts))
    joined, final = WORK / "joined.mp4", OUT / "00_longform_exdiv_hindi.mp4"
    B.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", 0, "-i", listing, "-c", "copy", joined])
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
