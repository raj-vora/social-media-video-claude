"""Sentence-level timing for the dividend shorts' voiceover, so on-screen text can appear
when the narrator says it.

Parler rendered each sentence as its own cached take. This rebuilds every section (and
alternate hook) from those takes: each sentence gets the same silence trim and tempo as
generate_voiceovers.tighten (x1.1), and sentences are joined with a gap set by their end
punctuation. That gives exact start/end times per sentence, written to
assets/voiceover/hindi/<short>/timed/timing.json next to the section wavs (S1..S5 for
the script sections, H2..H5 for the alternate hooks).

Usage (repo root): .venv-tts/bin/python dividend-income-2026/tools/timing.py [01_coal] [--tempo 1.1]
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "invit-analysis-2026" / "voiceover"))
from generate_voiceovers import DEFAULT_VOICES, VOICES, parse_sections  # noqa: E402
from tts_engines import _parler_prepare, parler_plan, parler_sentences, spoken  # noqa: E402

PROJECT = REPO / "dividend-income-2026"
RATE = 44100
GAPS = [("...", 0.45), ("…", 0.45), ("?", 0.30), ("!", 0.10), (".", 0.18), ("।", 0.18)]
DEFAULT_GAP = 0.15
SILENCE = ("silenceremove=start_periods=1:start_threshold=-40dB:detection=peak"
           ":stop_periods=-1:stop_duration=0.25:stop_threshold=-40dB:stop_silence=0.15")
# The Parler takes of the closing "link below" sentence vary by mood: one reads YouTube as "jaut"/"u".
# This one (verified with the medium ASR model) says यूट्यूब, so every video uses it.
FIXED_TAKES = {"पूरा वीडियो यूट्यूब पर — लिंक नीचे।": PROJECT / "assets" / "voiceover" / "hindi" / "cta" / "link_youtube.wav"}
HOOK_RE = re.compile(r'^\*\*H(\d) — .*?:\*\* "(.*?)"\s*$', re.M)


def gap_after(sentence):
    s = sentence.rstrip()
    return next((g for end, g in GAPS if s.endswith(end)), DEFAULT_GAP)


def sentences_of(text):
    return _parler_prepare(spoken(" ".join(text.split()), "hindi"), "hindi")


def process(wav, tempo, work):
    out = work / (wav.stem + ".wav")
    if not out.exists():
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-af", f"{SILENCE},atempo={tempo:.4f}",
                        "-ar", str(RATE), "-ac", "1", str(out)], check=True)
    data, rate = sf.read(str(out), dtype="float32")
    assert rate == RATE
    return data


def build_text(text, params, tempo, work, dest):
    """Write dest (wav) and return {"duration", "sentences": [{text, start, end}]}."""
    sents = sentences_of(text)
    plan = [(s, d, sd, FIXED_TAKES.get(s, w)) for s, d, sd, w in parler_plan(sents, params)]
    if not all(p[3].exists() for p in plan):
        parler_sentences(sents, params)  # renders only the takes that are missing (edited lines)
    chunks, t, meta = [], 0.0, []
    for sentence, (_, _, _, wav) in zip(sents, plan):
        data = process(wav, tempo, work)
        gap = gap_after(sentence)
        meta.append({"text": sentence, "start": round(t, 3), "end": round(t + len(data) / RATE, 3)})
        chunks += [data, np.zeros(int(gap * RATE), dtype="float32")]
        t += len(data) / RATE + gap
    sf.write(str(dest), np.concatenate(chunks), RATE)
    return {"duration": round(t, 3), "sentences": meta}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("only", nargs="?", default="")
    ap.add_argument("--tempo", type=float, default=1.1)
    args = ap.parse_args()
    params = VOICES[DEFAULT_VOICES["hindi"]][2]
    for path in sorted((PROJECT / "scripts" / "youtube").glob("*_short_hindi.md")):
        if args.only not in path.stem:
            continue
        out = PROJECT / "assets" / "voiceover" / "hindi" / path.stem / "timed"
        work = out / "takes"
        work.mkdir(parents=True, exist_ok=True)
        timing = {}
        for n, (_, _, text) in enumerate(parse_sections(path), 1):
            timing[f"S{n}"] = build_text(text, params, args.tempo, work, out / f"S{n}.wav")
        for n, text in HOOK_RE.findall(path.read_text(encoding="utf-8")):
            if n != "1":
                timing[f"H{n}"] = build_text(text, params, args.tempo, work, out / f"H{n}.wav")
        (out / "timing.json").write_text(json.dumps(timing, ensure_ascii=False, indent=1), encoding="utf-8")
        print(path.stem, {k: v["duration"] for k, v in timing.items()})


if __name__ == "__main__":
    main()
