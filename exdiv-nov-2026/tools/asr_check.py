"""Transcribe each voiced segment of the ex-dividend shorts with Whisper (faster-whisper medium,
cached under .cache/huggingface) and print it under the script text, to catch mispronounced
names or numbers before publishing.

Usage (repo root): .venv-tts/bin/python exdiv-nov-2026/tools/asr_check.py 01_sanofi_A [02_nov6_list_A ...]
"""

import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
os.environ.setdefault("HF_HOME", str(PROJECT.parent / ".cache" / "huggingface"))


def main():
    import numpy as np
    from faster_whisper import WhisperModel
    asr = WhisperModel("medium", device="cpu", compute_type="int8", cpu_threads=2)
    for vid in sys.argv[1:]:
        vo = PROJECT / "assets" / "voiceover" / vid
        timing = json.loads((vo / "timing.json").read_text(encoding="utf-8"))
        for name in timing:
            # decode with ffmpeg: this venv's PyAV is too new for faster-whisper's decode_audio
            raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(vo / f"{name}.wav"), "-f", "f32le", "-ac", "1",
                                  "-ar", "16000", "-"], capture_output=True, check=True).stdout
            segs, _ = asr.transcribe(np.frombuffer(raw, dtype=np.float32), language="hi", beam_size=5)
            heard = " ".join(s.text.strip() for s in segs)
            print(f"[{vid} {name}]\n  script: {' '.join(s['text'] for s in timing[name]['sentences'])}\n  heard:  {heard}", flush=True)


if __name__ == "__main__":
    main()
