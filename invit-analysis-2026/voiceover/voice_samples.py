"""Render one reel's full VO in every male voice preset, for picking a voice.

Writes assets/voiceover/samples/<script>/<english|hindi>/<voice id>.mp3 at the
voice's natural speed (no tempo change), sections joined with a short pause,
plus an index.html with players for side-by-side listening.

Usage (from repo root):
  .venv-tts/Scripts/python invit-analysis-2026/voiceover/voice_samples.py [--script 05_indigrid] [--engines edge,piper,kokoro,parler]
"""

import argparse
import html
import subprocess
import sys
import tempfile
from pathlib import Path

from generate_voiceovers import OUT_DIR, SCRIPTS_DIR, parse_sections, probe_duration
from tts_engines import VOICES, synth_many

GAP = 0.35


def join_sections(parts, dest):
    inputs, filters = [], []
    for i, p in enumerate(parts):
        inputs += ["-i", str(p)]
        filters.append(f"[{i}:a]aresample=24000,aformat=channel_layouts=mono,apad=pad_dur={GAP}[a{i}]")
    filters.append("".join(f"[a{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1[out]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filters),
                    "-map", "[out]", "-b:a", "128k", str(dest)], check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", default="05_indigrid")
    ap.add_argument("--engines", default="edge,piper,kokoro,parler")
    ap.add_argument("--voices", help="comma-separated preset ids (overrides --engines)")
    ap.add_argument("--sections", type=int, help="only the first N sections (Parler on CPU is ~11x slower than real time)")
    ap.add_argument("--isolate", action="store_true",
                    help="render each voice in its own process, retrying crashes (flaky GPU)")
    ap.add_argument("--retries", type=int, default=25)
    args = ap.parse_args()

    engines = set(args.engines.split(","))
    wanted = args.voices.split(",") if args.voices else [
        v for v, (eng, *_rest) in VOICES.items() if eng in engines]
    out_root = OUT_DIR / "samples" / args.script
    results = []

    if args.isolate:
        for vid in wanted:
            cmd = [sys.executable, __file__, "--script", args.script, "--voices", vid]
            if args.sections:
                cmd += ["--sections", str(args.sections)]
            for attempt in range(1, args.retries + 1):
                if subprocess.run(cmd).returncode == 0:
                    break
                print(f"  {vid}: attempt {attempt} crashed, retrying", flush=True)
        wanted = []

    for vid in wanted:
        engine, lang, params, label = VOICES[vid]
        script = SCRIPTS_DIR / "individual" / f"{args.script}_{lang}.md"
        sections = parse_sections(script)[:args.sections]
        dest = out_root / lang / f"{vid}.mp3"
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"{vid}: {label}", flush=True)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                parts = synth_many(engine, [text for _s, _e, text in sections], lang, params,
                                   [Path(tmp) / f"{n:02d}" for n in range(1, len(sections) + 1)])
                join_sections(parts, dest)
        except Exception as exc:
            print(f"  FAILED: {type(exc).__name__}: {exc}", flush=True)
            if len(wanted) == 1:
                return 1  # lets an --isolate parent retry
            continue
        dur = probe_duration(dest)
        print(f"  {dur:.1f}s", flush=True)
        results.append((lang, vid, label, dest, dur))

    rows = []
    for lang in ("english", "hindi"):
        for dest in sorted((out_root / lang).glob("*.mp3")):
            vid, dur = dest.stem, probe_duration(dest)
            label = VOICES[vid][3] if vid in VOICES else ""
            rows.append(f"<tr><td>{lang}</td><td><code>{vid}</code></td><td>{html.escape(label)}</td>"
                        f"<td>{dur:.1f}s</td><td><audio controls preload=none "
                        f"src=\"{dest.relative_to(out_root).as_posix()}\"></audio></td></tr>")
    (out_root / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><title>Voice samples</title>"
        "<style>body{font:14px system-ui;margin:24px}td{padding:6px 10px;border-bottom:1px solid #ddd}</style>"
        f"<h1>Voice samples - {args.script}</h1><p>Natural speed; target is 60s.</p>"
        "<table>" + "".join(rows) + "</table>", encoding="utf-8")
    print(f"\n{len(results)}/{len(wanted)} voices -> {out_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
