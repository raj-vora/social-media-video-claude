"""Generate voiceovers (English + Hindi, Indian accent) for every reel script.

Reads the `**VO:** "..."` blocks under each `### [m:ss–m:ss]` section of the
scripts in /scripts and writes, per script:

  assets/voiceover/<lang>/<script>/NN_<start>-<end>.mp3   one file per section
  assets/voiceover/<lang>/<script>/<script>_full.mp3      sections laid out at
                                                          their script timestamps

The voice per language is a preset id from tts_engines.VOICES (--voice-en,
--voice-hi; see voice_samples.py to audition them). The defaults are the Indic
Parler voices picked from the samples: Raghav (English) and Aman (Hindi).
progress.py shows how many sentences of a Parler run are rendered.

TTS voices read slower (~1.8 words/s) than the ~2.5 the scripts are written for, so
each raw clip is post-processed with ffmpeg: pauses longer than 0.25s are cut
down to 0.15s and the whole reel gets one uniform pitch-preserving --tempo, so
pacing stays consistent across sections. A section that still overruns its slot
pushes the following sections later in the full track.

Raw clips are cached per voice in raw/<voice id>/ and are only re-synthesised
when the VO text changes (or with --force); re-running with a different --tempo
is offline and fast.

Usage (from repo root):
  .venv-tts/Scripts/python invit-analysis-2026/voiceover/generate_voiceovers.py       [--voice-en en_parler_raghav] [--voice-hi hi_parler_aman] [--tempo 1.1] [--only 01_indus] [--force] [--project dividend-income-2026]
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from script_format import parse_sections  # re-exported: progress.py, ab_voice.py and others import it from here
from tts_engines import VOICES, synth

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
OUT_DIR = ROOT / "assets" / "voiceover"
MANIFEST = OUT_DIR / "voiceover_manifest.json"

DEFAULT_TEMPO = 1.1
DEFAULT_VOICES = {"english": "en_parler_raghav", "hindi": "hi_parler_aman"}
MIN_GAP = 0.25  # seconds between sections when one overruns into the next

def find_scripts():
    """Yield (language, script name, path) for every script with VO blocks."""
    youtube = SCRIPTS_DIR / "youtube"
    if not (SCRIPTS_DIR / "individual").exists():  # a project with only YouTube scripts
        for path in sorted(youtube.glob("*.md")):
            yield path.stem.rsplit("_", 1)[1], path.stem, path
        return
    for path in sorted(SCRIPTS_DIR.glob("script_*.md")):
        lang = path.stem.split("_", 1)[1]
        yield lang, f"00_summary_{lang}", path
    for path in sorted((SCRIPTS_DIR / "individual").glob("*.md")):
        lang = path.stem.rsplit("_", 1)[1]
        yield lang, path.stem, path


def probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def synthesize(voice_id, text, dest, retries=3):
    engine, lang, params, _label = VOICES[voice_id]
    for attempt in range(1, retries + 1):
        try:
            return synth(engine, text, lang, params, dest)
        except Exception as exc:  # online engines raise on HTTP 429 / network blips
            if attempt == retries:
                raise
            print(f"    retry {attempt} after error: {exc}")
            time.sleep(5 * attempt)


def tighten(raw, dest, tempo):
    """Trim edge silence, shorten long pauses, and apply a pitch-preserving tempo."""
    silence = ("silenceremove=start_periods=1:start_threshold=-40dB:detection=peak"
               ":stop_periods=-1:stop_duration=0.25:stop_threshold=-40dB:stop_silence=0.15")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(raw),
         "-filter:a", f"{silence},atempo={tempo:.4f}", "-b:a", "128k", str(dest)],
        check=True,
    )


def build_full_track(segments, dest):
    """Mix segments onto one track, each starting at its script timestamp."""
    inputs, filters, cursor = [], [], 0.0
    for i, seg in enumerate(segments):
        start = max(seg["start"], cursor + (MIN_GAP if i else 0))
        seg["placed_at"] = round(start, 2)
        cursor = start + seg["duration"]
        inputs += ["-i", str(seg["file"])]
        filters.append(f"[{i}:a]adelay={int(start * 1000)}:all=1[a{i}]")
    mix_in = "".join(f"[a{i}]" for i in range(len(segments)))
    filters.append(f"{mix_in}amix=inputs={len(segments)}:normalize=0:duration=longest[out]")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filters),
         "-map", "[out]", "-b:a", "128k", str(dest)],
        check=True,
    )
    return cursor


def main():
    global ROOT, SCRIPTS_DIR, OUT_DIR, MANIFEST
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--force", action="store_true", help="re-synthesise every segment")
    ap.add_argument("--tempo", type=float, default=DEFAULT_TEMPO,
                    help=f"uniform speed-up applied to every section (default {DEFAULT_TEMPO})")
    ap.add_argument("--only", help="substring filter on script name, e.g. 01_indus")
    ap.add_argument("--project", default=ROOT.name,
                    help="project folder at the repo root whose scripts/ to voice (default invit-analysis-2026)")
    ap.add_argument("--voice-en", default=DEFAULT_VOICES["english"], help="English voice preset id")
    ap.add_argument("--voice-hi", default=DEFAULT_VOICES["hindi"], help="Hindi voice preset id")
    args = ap.parse_args()
    ROOT = ROOT.parent / args.project
    SCRIPTS_DIR, OUT_DIR = ROOT / "scripts", ROOT / "assets" / "voiceover"
    MANIFEST = OUT_DIR / "voiceover_manifest.json"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    report = []

    for lang, name, path in find_scripts():
        if args.only and args.only not in name:
            continue
        voice = {"english": args.voice_en, "hindi": args.voice_hi}[lang]
        if VOICES[voice][1] != lang:
            sys.exit(f"voice {voice} is a {VOICES[voice][1]} voice, not {lang}")
        out = OUT_DIR / lang / name
        raw_dir = out / "raw" / voice
        raw_dir.mkdir(parents=True, exist_ok=True)
        print(f"{lang}/{name}")

        prev_entry = manifest.get(f"{lang}/{name}", {})
        cached = ({s["file_name"]: s for s in prev_entry.get("segments", [])}
                  if prev_entry.get("voice") == voice else {})
        segments = []
        for n, (start, end, text) in enumerate(parse_sections(path), 1):
            file_name = f"{n:02d}_{start // 60}m{start % 60:02d}-{end // 60}m{end % 60:02d}.mp3"
            final = out / file_name
            prev = cached.get(file_name, {})
            raw = ROOT / prev["raw"] if "raw" in prev else None
            if args.force or prev.get("text") != text or not (raw and raw.exists()):
                print(f"  tts {file_name}")
                raw = synthesize(voice, text, raw_dir / Path(file_name).stem)
                if VOICES[voice][0] in ("gtts", "edge"):
                    time.sleep(1)  # be polite to the online services
            tighten(raw, final, args.tempo)
            dur = probe_duration(final)
            segments.append({
                "file_name": file_name, "file": final, "start": start, "end": end,
                "slot": end - start, "duration": round(dur, 2),
                "raw": raw.relative_to(ROOT).as_posix(), "text": text,
            })

        full = out / f"{name}_full.mp3"
        total = build_full_track(segments, full)
        manifest[f"{lang}/{name}"] = {
            "source": path.relative_to(ROOT).as_posix(),
            "voice": voice,
            "voice_label": VOICES[voice][3],
            "tempo": args.tempo,
            "full_track": full.relative_to(ROOT).as_posix(),
            "full_duration": round(probe_duration(full), 2),
            "segments": [{k: v for k, v in s.items() if k != "file"} for s in segments],
        }
        # Saved per reel so a crashed run keeps the reels it finished.
        MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        over = [s for s in segments if s["duration"] > s["slot"]]
        report.append((f"{lang}/{name}", total, segments[-1]["end"], len(over)))

    print("\nscript                                   VO end   target  sections over slot")
    for key, total, target, over in report:
        print(f"{key:40s} {total:6.1f}s  {target:5d}s  {over}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
