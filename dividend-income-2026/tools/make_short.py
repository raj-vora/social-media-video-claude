"""Build one of the 30-40 s dividend shorts written for the short format (short_scripts.py):
voices every sentence with the same Parler voice and settings as the longer shorts, then renders
the 1080x1920 video with the same banner, footage, chart and synced on-screen text.

Usage (repo root): .venv-tts/bin/python dividend-income-2026/tools/make_short.py 01_coal_india A [--force] [--md]
Output: videos/s30/<short>_<letter>.mp4; audio and timing in
assets/voiceover/hindi/s30/<short>_<letter>/; the script as scripts/youtube/s30/<short>_<letter>.md
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
from short_scripts import CTA, SCRIPTS  # noqa: E402
from timing import build_text, sentences_of  # noqa: E402
from generate_voiceovers import DEFAULT_VOICES, VOICES  # noqa: E402

END_SENTENCE = "ये इन्वेस्टमेंट एडवाइस नहीं है।"
END_LINES = [("NOT INVESTMENT ADVICE", 0.1), ("DIVIDENDS ARE NOT GUARANTEED", 0.6), ("DIVIDENDS ARE TAXED", 1.1),
             ("PAST RETURNS ≠ FUTURE RETURNS", 1.6), (CTA, 2.1)]
END_TAIL = 4.6  # the link line stays up for 2.5 s


def item_sentences(sentences):
    """Authoring items may hold several sentences: map item index -> indices of voiced sentences."""
    out, k = [], 0
    for item in sentences:
        n = len(sentences_of(item))
        out.append(list(range(k, k + n)))
        k += n
    return out


def line_time(timing, groups, item, keyword):
    """Start of an on-screen line: the item's first sentence, or the sentence holding the keyword."""
    idxs = groups[item]
    target = idxs[0]
    if keyword:
        for i in idxs:
            if keyword in timing["sentences"][i]["text"]:
                target = i
                break
        else:
            raise SystemExit(f"keyword {keyword!r} not found in item {item}")
    return B.line_start(timing, target, keyword)


def write_md(short, letter, script, path):
    n = int(short[:2])
    L = [f"# शॉर्ट {n:02d}{letter} — {short[3:].replace('_', ' ').title()} — {script['title']} (30–40 सेकंड, 9:16)", "",
         "नंबर्स: `data/top10.csv`, `stocks_metrics.json`; तरीका: `data/README_methodology.md`। हर लाइन ऑन-स्क्रीन तभी आती है जब बोली जाती है।", "", "---", ""]
    for name, sentences, lines, chart in script["segs"]:
        L += [f"### {name.upper()}" + (" (चार्ट)" if chart else ""), f"**VO:** \"{' '.join(sentences)}\"", "",
              "**ऑन-स्क्रीन टेक्स्ट:** " + " | ".join(l[1] for l in lines), ""]
    L += ["### END", f"**VO:** \"{END_SENTENCE}\"", "", "**ऑन-स्क्रीन टेक्स्ट:** " + " | ".join(t for t, _ in END_LINES), ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L), encoding="utf-8")


def build(short, letter, force, md_only):
    script = SCRIPTS[short][letter]
    write_md(short, letter, script, B.PROJECT / "scripts" / "youtube" / "s30" / f"{short}_{letter}.md")
    if md_only:
        return
    n = int(short[:2])
    metrics = {r["symbol"]: r for r in json.loads((B.PROJECT / "data" / "stocks_metrics.json").read_text())}
    row = metrics[B.SYMBOLS[short]]
    top10 = {r["symbol"]: r for r in csv.DictReader(open(B.PROJECT / "data" / "top10.csv"))}
    yield_pct = f"{float(top10[B.SYMBOLS[short]]['screener_yield_pct']) + 1e-6:.1f}"
    series = {int(k): v for k, v in row["fy_divs"].items() if 2017 <= int(k) <= 2026}
    first = min(k for k, v in series.items() if v > 0)
    series = {k: v for k, v in series.items() if k >= first}
    params = VOICES[DEFAULT_VOICES["hindi"]][2]
    vo = B.ASSETS / "voiceover" / "hindi" / "s30" / f"{short}_{letter}"
    work = B.WORK / "s30" / f"{short}_{letter}"
    (vo / "takes").mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    banner, footer = work / "banner.png", work / "footer.png"
    B.banner_png(n, row["name"], yield_pct, banner)
    B.footer_png(footer)
    pool = [B.norm_clip(c, 16) for c in B.POOLS[short]]
    r = "ABC".index(letter[0])
    segs, timings = [], {}
    all_segs = [*script["segs"], ("end", [END_SENTENCE], [], False)]
    clip_for = {"hook": pool[r % 3], "m1": pool[(r + 1) % 3], "m2": pool[3], "risk": pool[(r + 2) % 3], "end": pool[0]}
    for name, sentences, lines, chart in all_segs:
        wav = vo / f"{name}.wav"
        t = build_text(" ".join(sentences), params, 1.1, vo / "takes", wav)
        timings[name] = t
        groups = item_sentences(sentences)
        items = []
        lead = 0.0
        if name == "hook":  # 0.12 s of silence before the first word
            lead = 0.12
            data, rate = sf.read(str(wav), dtype="float32")
            sf.write(str(wav), np.concatenate([np.zeros(int(lead * rate), dtype="float32"), data]), rate)
        if name == "end":
            data, rate = sf.read(str(wav), dtype="float32")
            sf.write(str(wav), np.concatenate([data, np.zeros(max(0, int((END_TAIL - t["duration"]) * rate)), dtype="float32")]), rate)
            items = list(END_LINES)
        else:
            items = [(l[1], line_time(t, groups, l[0], l[2] if len(l) > 2 else None) + lead) for l in lines]
        size = 88 if len(items) <= 3 else 64 if len(items) <= 5 else 52
        room = 600 if chart else 1250  # text sits between y=380 and the chart (y=990), or the footer
        while True:  # shrink until the stacked lines fit above the chart
            pngs = []
            for j, (text, start) in enumerate(items):
                png = work / f"{name}_{j}.png"
                sz = size if len(text) < 26 else int(size * 0.82)
                h = B.text_png(text, png, sz, B.GREEN if text == CTA else B.ACCENT if j == 0 else B.WHITE)
                pngs.append((png, h, start))
            if sum(h + 10 for _, h, _ in pngs) <= room or size <= 36:
                break
            size -= 4
        dest = work / f"seg_{name}.mp4"
        if force or not dest.exists():
            B.render_segment(dest, clip_for[name], wav, pngs, banner, footer, series if chart else None,
                             shade=0.34 if name == "hook" else 0.45)
        segs.append(dest)
    (vo / "timing.json").write_text(json.dumps(timings, ensure_ascii=False, indent=1), encoding="utf-8")
    out = B.OUT / "s30"
    out.mkdir(parents=True, exist_ok=True)
    listing = work / "concat.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in segs))
    final = out / f"{short}_{letter}.mp4"
    joined = work / "joined.mp4"
    B.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", 0, "-i", listing, "-c", "copy", joined])
    # one loudness pass over the whole video: -16 LUFS, true peak under -1.5 dB (the raw takes touched 0 dBFS)
    B.run(["ffmpeg", "-v", "error", "-y", "-i", joined, "-c:v", "copy", "-af", "loudnorm=I=-16:TP=-1.5:LRA=7",
           "-c:a", "aac", "-b:a", "128k", "-ar", 44100, final])
    print(f"{final.name}  {B.duration(final):.1f}s", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("short")
    ap.add_argument("letter")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--md", action="store_true", help="only write the script markdown")
    args = ap.parse_args()
    build(args.short, args.letter, args.force, args.md)


if __name__ == "__main__":
    main()
