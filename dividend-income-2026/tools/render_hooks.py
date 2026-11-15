"""Voice the alternate hooks (H2..H5) of a dividend short in the short's own voice.

H1 is already the first section of the short's voiceover. Each alternate is rendered
the same way (hi_parler_aman, tempo 1.1, silence trimmed) and written to
assets/voiceover/hindi/<short>/hooks/H<i>.mp3, with hooks.json recording text and duration.

Usage (repo root): .venv-tts/bin/python dividend-income-2026/tools/render_hooks.py 01_coal [--tempo 1.1]
Run one short per process: the CPU Parler run grows to ~7 GB over a few dozen sentences.
"""

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "invit-analysis-2026" / "voiceover"))
from generate_voiceovers import DEFAULT_VOICES, probe_duration, synthesize, tighten  # noqa: E402

PROJECT = REPO / "dividend-income-2026"
HOOK_RE = re.compile(r'^\*\*H(\d) — (.*?):\*\* "(.*?)"\s*$', re.M)


def hooks_of(path):
    return [(int(n), label, " ".join(vo.split())) for n, label, vo in HOOK_RE.findall(path.read_text(encoding="utf-8"))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("only")
    ap.add_argument("--tempo", type=float, default=1.1)
    args = ap.parse_args()
    voice = DEFAULT_VOICES["hindi"]
    for path in sorted((PROJECT / "scripts" / "youtube").glob("*_short_hindi.md")):
        if args.only not in path.stem:
            continue
        out = PROJECT / "assets" / "voiceover" / "hindi" / path.stem / "hooks"
        (out / "raw").mkdir(parents=True, exist_ok=True)
        meta = {}
        for n, label, text in hooks_of(path):
            if n == 1:
                continue
            raw = synthesize(voice, text, out / "raw" / f"H{n}")
            tighten(raw, out / f"H{n}.mp3", args.tempo)
            meta[f"H{n}"] = {"label": label, "text": text, "duration": round(probe_duration(out / f"H{n}.mp3"), 2)}
            print(path.stem, f"H{n}", meta[f"H{n}"]["duration"], "s", flush=True)
        (out / "hooks.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
