"""Progress of a Parler voiceover run, counted in rendered sentences.

Parler renders one sentence at a time and caches each as .cache/parler_sentences/
<key>.wav, so the exact set of sentences a generate_voiceovers.py run needs can be
worked out up front and checked against the cache. A reel counts as built once
the manifest shows it rendered with the chosen voice.

Usage (from repo root):
  .venv-tts/Scripts/python invit-analysis-2026/voiceover/progress.py [--voice-en en_parler_raghav] [--voice-hi hi_parler_aman]
  ... progress.py --watch 30     print a line whenever the count moves (for log tails)
"""

import argparse
import json
import sys
import time

from generate_voiceovers import DEFAULT_VOICES, MANIFEST, find_scripts, parse_sections
from tts_engines import VOICES, _parler_prepare, parler_plan, spoken

WIDTH = 30


def bar(done, total, width=WIDTH):
    fill = round(width * done / total) if total else width
    return "█" * fill + "░" * (width - fill)


def plan(voice_en, voice_hi):
    """[(reel key, voice, [cache paths])] for every reel, in generation order."""
    reels = []
    for lang, name, path in find_scripts():
        voice = {"english": voice_en, "hindi": voice_hi}[lang]
        engine, _lang, params, _label = VOICES[voice]
        if engine != "parler":
            sys.exit(f"{voice} is not a Parler voice; progress is counted in Parler sentences")
        paths = [cached for _s, _e, text in parse_sections(path)
                 for *_rest, cached in parler_plan(_parler_prepare(spoken(text, lang), lang), params)]
        reels.append((f"{lang}/{name}", voice, paths))
    return reels


def status(reels):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    rows = []
    for key, voice, paths in reels:
        done = sum(p.exists() for p in paths)
        built = manifest.get(key, {}).get("voice") == voice
        rows.append((key, done, len(paths), built))
    return rows


def report(rows):
    done = sum(r[1] for r in rows)
    total = sum(r[2] for r in rows)
    built = sum(r[3] for r in rows)
    for key, d, t, b in rows:
        state = "built" if b else ("rendered" if d == t else "")
        print(f"  {key:38s} {bar(d, t, 20)} {d:3d}/{t:<3d} {state}")
    print(f"\n  sentences {bar(done, total)} {done}/{total} ({100 * done / total:.0f}%)")
    print(f"  reels     {bar(built, len(rows))} {built}/{len(rows)} built")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--voice-en", default=DEFAULT_VOICES["english"])
    ap.add_argument("--voice-hi", default=DEFAULT_VOICES["hindi"])
    ap.add_argument("--watch", type=float, metavar="SECONDS",
                    help="poll and print one summary line per change until every reel is built")
    args = ap.parse_args()
    reels = plan(args.voice_en, args.voice_hi)

    if not args.watch:
        report(status(reels))
        return 0

    last = None
    while True:
        rows = status(reels)
        done, total = sum(r[1] for r in rows), sum(r[2] for r in rows)
        built = sum(r[3] for r in rows)
        current = next((r[0] for r in rows if r[1] < r[2] or not r[3]), "-")
        if (done, built) != last:
            print(f"{bar(done, total)} {done}/{total} sentences | {built}/{len(rows)} reels built"
                  f" | now: {current}", flush=True)
            last = (done, built)
        if built == len(rows):
            return 0
        time.sleep(args.watch)


if __name__ == "__main__":
    sys.exit(main())
