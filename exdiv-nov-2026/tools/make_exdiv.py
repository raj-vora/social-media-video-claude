"""Build the ex-dividend shorts (exdiv_scripts.py) with the dividend series' voice, renderer and
look: Parler voiceover per segment, footage, a banner with the payout, synced on-screen text and,
on chart segments, the dividend cash per share by calendar year.

Usage (repo root):
  .venv-tts/bin/python exdiv-nov-2026/tools/make_exdiv.py voice [01_sanofi:A ...]   # Parler takes only (slow, CPU)
  .venv-tts/bin/python exdiv-nov-2026/tools/make_exdiv.py video [01_sanofi:A ...] [--force]
  .venv-tts/bin/python exdiv-nov-2026/tools/make_exdiv.py md                        # script markdown only
With no ids, every version in exdiv_scripts.ORDER; "week2" / "trusts" mean ORDER_WEEK2 / ORDER_TRUSTS. Output: exdiv-nov-2026/videos/<short>_<letter>.mp4
(gitignored); audio and timing in exdiv-nov-2026/assets/voiceover/<short>_<letter>/;
scripts as exdiv-nov-2026/scripts/<short>_<letter>.md
"""

import argparse
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
REPO = PROJECT.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "dividend-income-2026" / "tools"))
import build_short as B  # noqa: E402
from exdiv_scripts import CTA, FOLLOW, ORDER, ORDER_SIX, ORDER_TRUSTS, ORDER_WEEK2, SHORTS  # noqa: E402
from make_short import END_LINES, END_SENTENCE, END_TAIL, item_sentences, line_time  # noqa: E402
from timing import build_text  # noqa: E402
from generate_voiceovers import DEFAULT_VOICES, VOICES  # noqa: E402

from PIL import Image, ImageDraw  # noqa: E402

VO = PROJECT / "assets" / "voiceover"
OUT = PROJECT / "videos"
WORK = REPO / ".cache" / "exdiv_build"
CHART_TITLE = "Dividend cash per share (₹), by calendar year"
GREEN_LINES = (CTA, FOLLOW)
TALL_SHADE = 800  # grey panel from y=330 to 1130: the six-stock closing lines ran below the old 970


def cash_series(symbol):
    for path in sorted((PROJECT / "data").glob("cash_by_year*.csv")):
        with open(path, newline="") as f:
            row = next((r for r in csv.DictReader(f) if r["symbol"] == symbol), None)
        if row:
            series = {int(y): float(v) for y, v in row.items() if y != "symbol"}
            # drop leading empty years: Yahoo has no PFC dividend in 2019 (an ex-date gap, not a skipped year)
            first = min(y for y, v in series.items() if v > 0)
            return {y: v for y, v in series.items() if y >= first}
    raise SystemExit(f"{symbol} not in data/cash_by_year*.csv")


def shared(short, seg):
    """True when every version of the short uses this very segment (week 2: one body, five hooks)."""
    return len(SHORTS[short]) > 1 and all(seg in v["segs"] for v in SHORTS[short].values())


def banner_png(big, name, chip, dest):
    img = Image.new("RGBA", (B.W, 230), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((40, 30, B.W - 40, 190), 40, fill=(0, 0, 0, 170))
    d.text((80, 110), big, font=B.font(68), fill=B.ACCENT, anchor="lm")
    d.text((B.W - 80, 110), chip, font=B.font(36), fill=B.GREEN, anchor="rm")
    x0 = 80 + d.textlength(big, font=B.font(68)) + 28
    room = B.W - 80 - d.textlength(chip, font=B.font(36)) - x0 - 25
    size = 50
    while d.textlength(name, font=B.font(size)) > room:
        size -= 2
    d.text((x0, 110), name, font=B.font(size), fill=B.WHITE, anchor="lm")
    img.save(dest)


def all_segs(script):
    """The script's segments plus the closing disclaimer, in the script's language (Hindi by default)."""
    return [*script["segs"], ("end", [script.get("end", END_SENTENCE)], [], None, script.get("end_clip", "savings/savings_01"))]


def chart_series(chart):
    """chart is a symbol, or (symbol, last_year) to stop before an unfinished year."""
    symbol, last = chart if isinstance(chart, tuple) else (chart, None)
    series = cash_series(symbol)
    return {y: v for y, v in series.items() if last is None or y <= last}


def voice(short, letter):
    script = SHORTS[short][letter]
    # Indic Parler picks the language from the script; the speaker sets the voice (Yash: Gujarati,
    # Sanjay: Marathi, both from the model card's recommended list)
    params = {"speaker": script["speaker"]} if "speaker" in script else VOICES[DEFAULT_VOICES["hindi"]][2]
    vo = VO / f"{short}_{letter}"
    (vo / "takes").mkdir(parents=True, exist_ok=True)
    timings = {}
    for name, sentences, *_ in all_segs(SHORTS[short][letter]):
        # processed takes are cached by name, not tempo: a tempo change needs a fresh takes/ folder
        takes = vo / ("takes" if script.get("tempo", 1.1) == 1.1 else f"takes_{script['tempo']}")
        takes.mkdir(parents=True, exist_ok=True)
        timings[name] = build_text(" ".join(sentences), params, script.get("tempo", 1.1), takes, vo / f"{name}.wav")
        print(f"  {short}_{letter} {name}: {timings[name]['duration']:.1f}s", flush=True)
    (vo / "timing.json").write_text(json.dumps(timings, ensure_ascii=False, indent=1), encoding="utf-8")
    return timings


def video(short, letter, force):
    import numpy as np
    import soundfile as sf
    script = SHORTS[short][letter]
    timings = voice(short, letter)  # instant once the takes exist
    vo, work = VO / f"{short}_{letter}", WORK / f"{short}_{letter}"
    work.mkdir(parents=True, exist_ok=True)
    banner, footer = work / "banner.png", work / "footer.png"
    banner_png(*script["banner"], banner)
    B.footer_png(footer)
    segs = []
    for seg in all_segs(script):
        name, sentences, lines, chart, clip = seg
        t, wav = timings[name], vo / f"{name}.wav"
        # a body shared by all versions is rendered once, in WORK/<short>_body/
        # the closing card is shared too, unless this version has its own end lines
        same_end = name == "end" and "end_lines" not in script
        sdir = (WORK / f"{short}_body") if (shared(short, seg) or same_end) and len(SHORTS[short]) > 2 else work
        sdir.mkdir(parents=True, exist_ok=True)
        groups = item_sentences(sentences)
        lead = 0.0
        if name == "hook":  # 0.12 s of silence before the first word
            lead = 0.12
            data, rate = sf.read(str(wav), dtype="float32")
            wav = work / "hook.wav"
            sf.write(str(wav), np.concatenate([np.zeros(int(lead * rate), dtype="float32"), data]), rate)
        if name == "end":
            data, rate = sf.read(str(wav), dtype="float32")
            wav = work / "end.wav"
            sf.write(str(wav), np.concatenate([data, np.zeros(max(0, int((END_TAIL - t["duration"]) * rate)), dtype="float32")]), rate)
            items = list(script.get("end_lines", END_LINES))
        else:
            items = [(l[1], line_time(t, groups, l[0], l[2] if len(l) > 2 else None) + lead) for l in lines]
        size = 88 if len(items) <= 3 else 64 if len(items) <= 5 else 52
        room = 600 if chart else 1250  # text sits between y=380 and the chart (y=990), or the footer
        while True:
            pngs = []
            for j, (text, start) in enumerate(items):
                png = sdir / f"{name}_{j}.png"
                sz = size if len(text) < 26 else int(size * 0.82)
                h = B.text_png(text, png, sz, B.GREEN if text in GREEN_LINES else B.ACCENT if j == 0 else B.WHITE)
                pngs.append((png, h, start))
            if sum(h + 10 for _, h, _ in pngs) <= room or size <= 36:
                break
            size -= 4
        dest = sdir / f"seg_{name}.mp4"
        if force or not dest.exists():
            B.render_segment(dest, B.norm_clip(clip, 16), wav, pngs, banner, footer,
                             chart_series(chart) if chart else None,
                             shade=0.34 if name == "hook" else 0.45, chart_title=script.get("chart_title", CHART_TITLE),
                             shade_h=TALL_SHADE if short.startswith(("15_", "16_", "17_", "18_", "19_", "20_")) else 640)
        segs.append(dest)
    OUT.mkdir(parents=True, exist_ok=True)
    listing = work / "concat.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in segs))
    joined, final = work / "joined.mp4", OUT / f"{short}_{letter}.mp4"
    B.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", 0, "-i", listing, "-c", "copy", joined])
    # one loudness pass over the whole video, as the dividend shorts
    B.run(["ffmpeg", "-v", "error", "-y", "-i", joined, "-c:v", "copy", "-af", "loudnorm=I=-16:TP=-1.5:LRA=7",
           "-c:a", "aac", "-b:a", "128k", "-ar", 44100, final])
    print(f"{final.name}  {B.duration(final):.1f}s", flush=True)


def write_md(short, letter):
    script = SHORTS[short][letter]
    L = [f"# Short {short} {letter}: {script['title']} (9:16, Hindi)", "",
         "Numbers: `data/exdiv_table.csv`, `data/cash_by_year.csv`; sources in `data/README.md`. "
         "Each on-screen line appears when it is spoken.", "", "---", ""]
    for name, sentences, lines, chart, clip in all_segs(script):
        L += [f"### {name.upper()}" + (f" (chart: {chart})" if chart else "") + f" [{clip}]",
              f"**VO:** \"{' '.join(sentences)}\"", ""]
        shown = [l[1] for l in lines] if name != "end" else [t for t, _ in script.get("end_lines", END_LINES)]
        L += ["**On-screen:** " + " | ".join(shown), ""]
    path = PROJECT / "scripts" / f"{short}_{letter}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["voice", "video", "md"])
    ap.add_argument("ids", nargs="*", help="short:letter, e.g. 01_sanofi:A")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    batches = {"week2": ORDER_WEEK2, "trusts": ORDER_TRUSTS, "six": ORDER_SIX}
    ids = ([tuple(i.split(":")) for i in args.ids if i not in batches]
           + [x for b in args.ids if b in batches for x in batches[b]]) or ORDER
    for short, letter in ids:
        write_md(short, letter)
        if args.mode == "voice":
            voice(short, letter)
        elif args.mode == "video":
            video(short, letter, args.force)


if __name__ == "__main__":
    main()
