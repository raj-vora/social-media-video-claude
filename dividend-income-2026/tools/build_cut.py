"""Shorter (30-40 s) cut of each dividend short, reusing the existing voiceover takes,
timed sentences, overlays, footage, chart and banner.

A cut keeps chosen sentences of each section (CUTS below, indices into timing.json).
Audio is sliced from the timed section wavs, so the narrator is the same take as in the
full version. On-screen lines whose sentence was dropped are dropped with it; the
disclaimer is shortened to its first spoken sentence plus the full text on screen.
Output: videos/cut/<short>_H<i>_cut.mp4 for hooks H1..H5 (H2..H5 keep all their sentences
unless HOOK_CUTS says otherwise).

Usage (repo root): .venv-tts/bin/python dividend-income-2026/tools/build_cut.py [01_coal] [--hooks 1,2,3,4,5] [--force]
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent))
import build_short as B  # noqa: E402
from overlays import CTA, OVERLAYS  # noqa: E402
from timing import gap_after  # noqa: E402

S5_LINES = [("NOT INVESTMENT ADVICE", 0.1), ("DIVIDENDS ARE NOT GUARANTEED", 0.8), ("DIVIDENDS ARE TAXED", 1.4),
            ("PAST RETURNS ≠ FUTURE RETURNS", 2.0), (CTA, 2.6)]
S5_TAIL = 3.6

# sentence indices kept per section (S5 is always [0], then the lines above)
CUTS = {
    "01_coal_india": {"S1": [0, 2, 3], "S2": [0], "S3": [0, 2], "S4": [0, 2, 3]},
    "02_rec": {"S1": [0, 1, 2], "S2": [2], "S3": [2], "S4": [0, 1, 2, 3]},
    "03_pfc": {"S1": [0], "S2": [0, 2], "S3": [0, 3], "S4": [0, 1, 3]},
    "04_itc": {"S1": [0, 1, 3, 4], "S2": [0], "S3": [3], "S4": [0, 2, 4]},
    "05_cesc": {"S1": [0, 1, 3, 4], "S2": [0], "S3": [0, 3], "S4": [2, 3]},
    "06_infosys": {"S1": [0, 1], "S2": [0], "S3": [1], "S4": [1, 3]},
    "07_hcl_tech": {"S1": [0, 1, 3, 4], "S2": [0], "S3": [2], "S4": [0, 2]},
    "08_hudco": {"S1": [0, 1, 3, 4], "S2": [1], "S3": [1, 3], "S4": [0, 4]},
    "09_power_grid": {"S1": [0, 1], "S2": [0], "S3": [1], "S4": [0, 3]},
    "10_hero_motocorp": {"S1": [0, 1, 3, 4], "S2": [0], "S3": [1], "S4": [0, 2, 3]},
}


def cut_audio(full_wav, timing, kept, dest):
    """Slice the kept sentences out of a timed section wav; returns the new timing."""
    data, rate = sf.read(str(full_wav), dtype="float32")
    chunks, meta, t = [], [], 0.0
    for i in kept:
        s = timing["sentences"][i]
        piece = data[int(s["start"] * rate): int(s["end"] * rate)]
        gap = gap_after(s["text"])
        meta.append({"text": s["text"], "start": round(t, 3), "end": round(t + len(piece) / rate, 3), "old": i})
        chunks += [piece, np.zeros(int(gap * rate), dtype="float32")]
        t += len(piece) / rate + gap
    sf.write(str(dest), np.concatenate(chunks), rate)
    return {"duration": round(t, 3), "sentences": meta}


# optional trims for alternate hooks that would push a cut past 40 s: {short: {"H2": [indices]}}
HOOK_CUTS = {"06_infosys": {"H2": [0, 1, 3, 4]}}


def build(stem, hooks, force):
    short = stem.removesuffix("_short_hindi")
    n = int(short[:2])
    metrics = {r["symbol"]: r for r in json.loads((B.PROJECT / "data" / "stocks_metrics.json").read_text())}
    row = metrics[B.SYMBOLS[short]]
    top10 = {r["symbol"]: r for r in csv.DictReader(open(B.PROJECT / "data" / "top10.csv"))}
    yield_pct = f"{float(top10[B.SYMBOLS[short]]['screener_yield_pct']) + 1e-6:.1f}"
    series = {int(k): v for k, v in row["fy_divs"].items() if 2017 <= int(k) <= 2026}
    first = min(k for k, v in series.items() if v > 0)
    series = {k: v for k, v in series.items() if k >= first}
    vo = B.ASSETS / "voiceover" / "hindi" / stem / "timed"
    timing = json.loads((vo / "timing.json").read_text(encoding="utf-8"))
    work = B.WORK / f"{short}_cut"
    work.mkdir(parents=True, exist_ok=True)
    banner, footer = work / "banner.png", work / "footer.png"
    B.banner_png(n, row["name"], yield_pct, banner)
    B.footer_png(footer)
    clips = [B.norm_clip(c, 16) for c in B.POOLS[short]]
    cut = {**CUTS[short], "S5": [0]}
    for h in hooks:
        if h > 1:
            cut[f"H{h}"] = HOOK_CUTS.get(short, {}).get(f"H{h}") or list(range(len(timing[f"H{h}"]["sentences"])))

    def segment(key, src, k):
        wav = work / f"{key}.wav"
        t = cut_audio(vo / f"{src}.wav", timing[src], cut[key], wav)
        remap = {s["old"]: i for i, s in enumerate(t["sentences"])}
        items = []
        if key == "S5":
            items = [(text, at) for text, at in S5_LINES]
        else:
            for item in OVERLAYS[short][src]:
                sentence, text, keyword = (*item, None)[:3]
                if sentence in remap:
                    items.append((text, B.line_start(t, remap[sentence], keyword)))
        size = 88 if len(items) <= 3 else 64 if len(items) <= 5 else 52
        lines = []
        for j, (text, start) in enumerate(items):
            png = work / f"{key}_{j}.png"
            sz = size if len(text) < 26 else int(size * 0.82)
            h = B.text_png(text, png, sz, B.GREEN if text == CTA else B.ACCENT if j == 0 else B.WHITE)
            lines.append((png, h, start))
        dest = work / f"seg_{key}.mp4"
        clip = clips[-1] if key == "S3" else clips[0] if key == "S5" else clips[k % len(clips)]
        if key == "S5":  # hold the end card long enough to read the on-screen disclaimer
            data, rate = sf.read(str(wav), dtype="float32")
            sf.write(str(wav), np.concatenate([data, np.zeros(int((S5_TAIL - t["duration"]) * rate), dtype="float32")]), rate)
        if force or not dest.exists():
            B.render_segment(dest, clip, wav, lines, banner, footer, series if key == "S3" else None, shade=0.42 if key in ("S3", "S4", "S5") else 0)
        return dest

    body = [segment(key, key, k) for k, key in enumerate(["S2", "S3", "S4", "S5"], 1)]
    out_dir = B.OUT / "cut"
    out_dir.mkdir(parents=True, exist_ok=True)
    for h in hooks:
        key = "S1" if h == 1 else f"H{h}"
        hook = segment(key, key, h - 1)
        listing = work / f"concat_{h}.txt"
        listing.write_text("".join(f"file '{p}'\n" for p in [hook, *body]))
        final = out_dir / f"{short}_H{h}_cut.mp4"
        B.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", 0, "-i", listing, "-c", "copy", final])
        print(f"  {final.name}  {B.duration(final):.1f}s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("only", nargs="?", default="")
    ap.add_argument("--hooks", default="1,2,3,4,5")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    for path in sorted((B.PROJECT / "scripts" / "youtube").glob("*_short_hindi.md")):
        if args.only in path.stem:
            print(path.stem)
            build(path.stem, [int(h) for h in args.hooks.split(",")], args.force)


if __name__ == "__main__":
    main()
