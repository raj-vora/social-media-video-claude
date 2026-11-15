"""A/B voiceovers: renders reels with the current Parler moods, picks the best of
several takes per sentence, and paces the result by punctuation, for side-by-side
previews against the live voiceover (capcut/generator/build_ab_previews.js).

Each variant in the config (a JSON list) is either a whole reel in some voice:
  {"name": "InvIT_01_Indus_Infra_Trust_EN_thoma", "reel": "01_indus_infra_trust",
   "lang": "english", "voice": "en_parler_thoma", "music": "path.mp3"?}
or a reel's live voiceover with only the hook replaced, voiced in the reel's own voice:
  {"name": "...", "reel": "00_summary", "lang": "hindi", "hook": "...", "hook_title": "..."}
or another script for the reel's footage (e.g. a YouTube short), voiced whole in the reel's
own voice, its first section optionally replaced by "hook"; "beats" groups the reel's
beats per script section when the counts differ:
  {"name": "...", "reel": "02_powergrid_invit", "lang": "hindi", "script": "youtube/02_..._short_hindi.md",
   "hook": "...", "hook_title": "...", "beats": [[0], [1], [2, 3], [4], [5]]}
"shots": "longform" puts it on the long-form shot list (16:9) instead of the reel's footage.

Takes: take k of a sentence is cached in .cache/parler_sentences under the voice's
seed shifted by k * TAKE_SEED_STEP. A sentence's missing takes are rendered as one
batch, which costs little more than a single take.
Every take is transcribed with faster-whisper; takes that read noticeably worse than
the clearest one, or run unusually long or short, are dropped, and of the rest
the most animated wins (widest pitch movement, plus a little for pace). Scores go
to <name>/takes.json.

Cadence: each chosen take is trimmed and sped up by its mood (excited lines a
little faster, suspense lines slower), then sentences are joined with a gap set by
their end punctuation - a beat after "...", a breath after "?", almost none after
"!". Sections follow each other back to back instead of waiting for their script
timestamps.

Writes under <repo>/previews/_ab/<name>/: section mp3s, full.wav, plan.json (sections,
logo and end-card cues), and bed.wav when the variant has music.

Usage (from repo root; --phase render only renders takes, so it can run under a
retry loop on the crash-prone GPU):
  .venv-tts/Scripts/python invit-analysis-2026/voiceover/ab_voice.py previews/_ab/ab_config.json [--phase render|build|all] [--takes 3] [--only name-substring]
"""

import argparse
import difflib
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent))
from generate_voiceovers import DEFAULT_VOICES, SCRIPTS_DIR, parse_sections  # noqa: E402
from mention_times import END_CARDS, MENTIONS, said  # noqa: E402
from tts_engines import (CACHE, VOICES, _parler, _parler_prepare, parler_mood, parler_plan,  # noqa: E402
                         split_sentences, spoken)

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
OUT_ROOT = REPO / "previews" / "_ab"
MANIFEST = json.loads((ROOT / "assets/voiceover/voiceover_manifest.json").read_text(encoding="utf-8"))
GEN = ROOT / "assets/capcut/generator"
LOGO_CUES = json.loads((GEN / "logo_cues.json").read_text(encoding="utf-8"))
END_CUES = json.loads((GEN / "end_cues.json").read_text(encoding="utf-8"))

RATE = 44100
TAKE_SEED_STEP = 7919
SECTION_GAP = 0.3
TAIL_SEC = 0.8  # as build_vo_drafts.js
# Seconds of silence after a sentence, by how it ends.
GAPS = [("...", 0.45), ("…", 0.45), ("?", 0.30), ("!", 0.10), (".", 0.18), ("।", 0.18)]
DEFAULT_GAP = 0.15
# Tempo per mood, on top of the reel's base tempo.
MOOD_TEMPO = {"hype": 1.06, "thrilled": 1.06, "cta": 1.05, "proud": 1.03, "suspense": 0.92, "calm": 0.97}
# A take may read this much worse (character error rate) than the clearest take.
CER_SLACK = 0.10
PACE_WEIGHT = 3.0
TRIM = ("silenceremove=start_periods=1:start_threshold=-40dB:detection=peak"
        ":stop_periods=-1:stop_duration=0.3:stop_threshold=-40dB:stop_silence=0.2,"
        "areverse,silenceremove=start_periods=1:start_threshold=-40dB:detection=peak,areverse")


def script_path(reel, lang):
    if reel == "00_summary":
        return SCRIPTS_DIR / f"script_{lang}.md"
    return next((SCRIPTS_DIR / "individual").glob(f"{reel}_{lang}.md"))


def variant_voice(v):
    return v.get("voice") or (MANIFEST[f"{v['lang']}/{v['reel']}_{v['lang']}"]["voice"] if "hook" in v or "script" in v
                              else DEFAULT_VOICES[v["lang"]])


def new_sections(v):
    """[(index, text)] of the sections this variant voices itself."""
    if "script" in v:
        texts = [text for _, _, text in parse_sections(SCRIPTS_DIR / v["script"])]
        if "hook" in v:
            texts[0] = v["hook"]
        return list(enumerate(texts))
    if "hook" in v:
        return [(0, v["hook"])]
    return [(i, text) for i, (_, _, text) in enumerate(parse_sections(script_path(v["reel"], v["lang"])))]


def take_params(params, k, section):
    # Section 0 is the hook, read as a tease where the punctuation doesn't say otherwise.
    return {**params, "seed": params.get("seed", 0) + k * TAKE_SEED_STEP, "hook": section == 0}


def render_batch(sentence, desc, missing):
    """Renders several takes of one sentence in one generate() call - decoding is
    bound by per-step overhead, so a batch costs little more than one take.
    `missing` = [(seed, cache path)]; the batch is seeded with the first seed."""
    import torch
    model, tok, desc_tok, device = _parler()
    n = len(missing)
    d = desc_tok([desc] * n, return_tensors="pt").to(device)
    prompt = tok([sentence] * n, return_tensors="pt").to(device)
    torch.manual_seed(missing[0][0])
    gen = model.generate(input_ids=d.input_ids, attention_mask=d.attention_mask,
                         prompt_input_ids=prompt.input_ids, prompt_attention_mask=prompt.attention_mask,
                         return_dict_in_generate=True)
    for b, (_, path) in enumerate(missing):
        audio = gen.sequences[b, :gen.audios_length[b]].to(torch.float32).cpu().numpy().squeeze()
        sf.write(str(path), audio, model.config.sampling_rate)


def render(variants, takes, reverse=False):
    for v in variants:
        params = VOICES[variant_voice(v)][2]
        # Reversed, a second worker starts from the other end of a long script too.
        for i, text in (reversed if reverse else list)(new_sections(v)):
            sents = _parler_prepare(spoken(text, v["lang"]), v["lang"])
            plans = [parler_plan(sents, take_params(params, k, i)) for k in range(takes)]
            for j, sentence in enumerate(sents):
                missing = [(plans[k][j][2], plans[k][j][3]) for k in range(takes) if not plans[k][j][3].exists()]
                if missing:
                    print(f"{v['name']} s{i}.{j}: {len(missing)} take(s)", flush=True)
                    render_batch(sentence, plans[0][j][1], missing)


# --- scoring -------------------------------------------------------------------

def normalise(text):
    return re.sub(r"[\W_]+", "", text.lower())


class Scorer:
    def __init__(self):
        from faster_whisper import WhisperModel
        self.asr = WhisperModel("small", device="cpu", compute_type="int8",
                                download_root=str(CACHE / "whisper"))

    def score(self, audio, rate, expected, lang):
        import librosa
        y = librosa.resample(audio, orig_sr=rate, target_sr=16000)
        yt, _ = librosa.effects.trim(y, top_db=35)
        segs, _ = self.asr.transcribe(yt, language="en" if lang == "english" else "hi", beam_size=1,
                                      condition_on_previous_text=False, vad_filter=False)
        heard = " ".join(s.text for s in segs)
        want = normalise(said(expected, lang))
        cer = 1 - difflib.SequenceMatcher(None, want, normalise(heard)).ratio()
        f0, voiced, _ = librosa.pyin(yt, fmin=65, fmax=450, sr=16000, frame_length=1024)
        f0 = f0[voiced & ~np.isnan(f0)]
        spread = float(np.std(12 * np.log2(f0 / np.median(f0)))) if len(f0) > 10 else 0.0
        dur = len(yt) / 16000
        return {"heard": heard.strip(), "cer": round(cer, 3), "pitch_st": round(spread, 2),
                "dur": round(dur, 2), "chars_per_s": round(len(want) / max(dur, 0.1), 2)}


SCORE_CACHE = CACHE / "ab_scores"


def cached_score(scorer, path, expected, lang):
    """scorer.score() of one cached take, itself cached: variants that share sections
    (a short's hooks) would otherwise transcribe the same takes again."""
    key = hashlib.sha1(f"{path.name}|{expected}|{lang}".encode("utf-8")).hexdigest()[:16]
    dest = SCORE_CACHE / f"{key}.json"
    if dest.exists():
        return json.loads(dest.read_text(encoding="utf-8"))
    audio, rate = sf.read(str(path), dtype="float32")
    result = scorer.score(audio, rate, expected, lang)
    SCORE_CACHE.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def pick(scored):
    """Index of the take to use, from per-take score dicts."""
    best_cer = min(s["cer"] for s in scored)
    med_rate = float(np.median([s["chars_per_s"] for s in scored]))
    ok = [i for i, s in enumerate(scored)
          if s["cer"] <= best_cer + CER_SLACK and 0.65 <= s["chars_per_s"] / med_rate <= 1.5]
    if not ok:
        ok = [min(range(len(scored)), key=lambda i: scored[i]["cer"])]
    for s in scored:
        s["score"] = round(s["pitch_st"] + PACE_WEIGHT * (s["chars_per_s"] / med_rate - 1), 3)
    return max(ok, key=lambda i: scored[i]["score"])


# --- assembly ------------------------------------------------------------------

def gap_after(sentence):
    s = sentence.rstrip().rstrip('"')
    return next((g for end, g in GAPS if s.endswith(end)), DEFAULT_GAP)


def process(audio, rate, tempo, dest):
    """Trim edge silence and long pauses, apply tempo; returns mono float32 at RATE."""
    raw = dest.with_suffix(".in.wav")
    sf.write(str(raw), audio, rate)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", f"{TRIM},atempo={tempo:.4f}",
                    "-ar", str(RATE), "-ac", "1", str(dest)], check=True)
    raw.unlink()
    data, _ = sf.read(str(dest), dtype="float32")
    return data


def encode(wav, mp3):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-b:a", "160k", str(mp3)], check=True)


def voice_section(v, i, text, takes, scorer, out, log):
    """Builds section i's audio; returns (wav path, [(original sentence, start, dur)])."""
    lang = v["lang"]
    params = VOICES[variant_voice(v)][2]
    base_tempo = MANIFEST[f"{lang}/{v['reel']}_{lang}"]["tempo"]
    sents = _parler_prepare(spoken(text, lang), lang)
    originals = split_sentences(text)
    if len(originals) != len(sents):
        sys.exit(f"{v['name']} section {i}: sentence split differs between script and spoken text")
    counts, pieces, timing, t = {}, [], [], 0.0
    for j, (sent, orig) in enumerate(zip(sents, originals)):
        mood = params.get("mood") or parler_mood(sent, counts, hook=i == 0)
        options = []
        for k in range(takes):
            path = parler_plan(sents, take_params(params, k, i))[j][3]
            if path.exists():
                options.append((k, path))
        if not options:
            sys.exit(f"{v['name']} section {i} sentence {j}: no takes rendered - run --phase render")
        scored = []
        for k, path in options:
            scored.append({"take": k, **cached_score(scorer, path, orig, lang)})
        best = pick(scored)
        audio, rate = sf.read(str(options[best][1]), dtype="float32")
        data = process(audio, rate, base_tempo * MOOD_TEMPO.get(mood, 1.0), out / f"s{i:02d}_{j:02d}.wav")
        log.append({"section": i, "sentence": orig, "mood": mood, "chosen": scored[best]["take"], "takes": scored})
        print(f"  {v['name']} s{i}.{j} {mood:9} take {scored[best]['take']} of {len(scored)}  "
              + "  ".join(f"[{s['take']}] cer {s['cer']:.2f} pitch {s['pitch_st']:.1f}" for s in scored), flush=True)
        timing.append((orig, t, len(data) / RATE))
        pieces.append(data)
        t += len(data) / RATE
        if j < len(sents) - 1:
            gap = np.zeros(int(gap_after(orig) * RATE), dtype="float32")
            pieces.append(gap)
            t += len(gap) / RATE
    wav = out / f"section_{i:02d}.wav"
    sf.write(str(wav), np.concatenate(pieces), RATE)
    return wav, timing


def cue_offset(timing, phrase, lang):
    for orig, start, dur in timing:
        if phrase in orig:
            pos = orig.find(phrase)
            return start + dur * len(said(orig[:pos], lang)) / max(1, len(said(orig, lang)))
    return None


def build(v, takes, scorer):
    lang, reel = v["lang"], v["reel"]
    key = f"{lang}/{reel}_{lang}"
    live = MANIFEST[key]
    out = OUT_ROOT / v["name"]
    out.mkdir(parents=True, exist_ok=True)
    print(f"{v['name']}", flush=True)
    log, voiced = [], {}
    for i, text in new_sections(v):
        voiced[i] = voice_section(v, i, text, takes, scorer, out, log)

    sections, cursor = [], 0.0
    for i, seg in enumerate(live["segments"] if "script" not in v else [None] * len(voiced)):
        if i in voiced:
            wav, timing = voiced[i]
            mp3 = out / f"{i + 1:02d}.mp3"
            encode(wav, mp3)
            dur = sf.info(str(wav)).duration
        else:  # the live voiceover's own clip
            mp3, timing = ROOT / Path(live["full_track"]).parent / seg["file_name"], None
            dur = seg["duration"]
        start = cursor + (SECTION_GAP if i else 0.0)
        sections.append({"file": str(mp3), "placed_at": round(start, 3), "duration": round(dur, 3), "timing": timing})
        cursor = start + dur

    # Logo cues (absolute seconds) and end-card cues (seconds into the outro clip).
    logos, used = [], set()
    for i, s in enumerate(sections):
        if s["timing"]:
            for phrase, logo in MENTIONS.get(reel, []):
                off = cue_offset(s["timing"], phrase, lang) if logo not in used else None
                if off is not None:
                    logos.append({"logo": logo, "at": round(s["placed_at"] + off, 3)})
                    used.add(logo)
        else:
            for c in LOGO_CUES.get(key, []):
                if c["section"] == i and c["logo"] not in used:
                    logos.append({"logo": c["logo"], "at": round(s["placed_at"] + c["offset"], 3)})
                    used.add(c["logo"])
    last = sections[-1]
    if last["timing"]:
        ends = []
        for card, phrases in END_CARDS[lang]:
            off = next((o for o in (cue_offset(last["timing"], p, lang) for p in phrases) if o is not None), None)
            if off is None and "script" in v:  # a short without the card's line: show it after the VO
                off = last["duration"]
            if off is None:
                sys.exit(f"{v['name']}: no {card} phrase in the outro")
            ends.append({"card": card, "offset": round(off, 3)})
    else:
        ends = [{"card": c["card"], "offset": c["offset"]} for c in END_CUES[key]]

    # Whole voiceover on one track, for listening and for ducking the music under it.
    total = cursor + TAIL_SEC
    full = np.zeros(int(total * RATE) + 1, dtype="float32")
    for s in sections:
        data, rate = sf.read(s["file"], dtype="float32", always_2d=True)
        data = data.mean(axis=1)
        if rate != RATE:
            import librosa
            data = librosa.resample(data, orig_sr=rate, target_sr=RATE)
        a = int(s["placed_at"] * RATE)
        full[a:a + len(data)] += data[:len(full) - a]
    sf.write(str(out / "full.wav"), full, RATE)
    bed = make_bed(v["music"], out / "full.wav", total, out / "bed.wav") if v.get("music") else None

    plan = {"name": v["name"], "reel": reel, "lang": lang, "voice": variant_voice(v),
            "hook_title": v.get("hook_title"), "beats": v.get("beats"), "shots": v.get("shots"), "sfx": v.get("sfx"), "bed": bed and str(bed),
            "sections": [{**{k: s[k] for k in ("file", "placed_at", "duration")},
                          # [start, duration] of each sentence in the clip, for cueing shots to lines
                          **({"sentences": [[round(st, 3), round(d, 3)] for _, st, d in s["timing"]]} if s["timing"] else {})}
                         for s in sections],
            "logo_cues": sorted(logos, key=lambda c: c["at"]), "end_cues": ends}
    (out / "plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "takes.json").write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  -> {total:.1f}s  (live voiceover: {live['full_duration']:.1f}s)", flush=True)


def loudness(path):
    out = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", out)[-1])


def make_bed(music, vo, total, dest):
    """The music looped to the reel's length, levelled 7 LU under the voice and
    ducked a few dB more while the voice is speaking."""
    target = loudness(vo) - 7
    # The track starts on the beat at 0 (Mixkit tracks open with a second or two of silence).
    graph = (f"[0:a]silenceremove=start_periods=1:start_threshold=-50dB,atrim=0:{total:.3f},asetpts=N/SR/TB,loudnorm=I={target:.1f}:TP=-3:LRA=11,"
             f"aresample={RATE},aformat=channel_layouts=stereo[m];"
             f"[1:a]aresample={RATE},aformat=channel_layouts=stereo,apad=whole_dur={total:.3f}[k];"
             f"[m][k]sidechaincompress=threshold=0.03:ratio=2:attack=30:release=450:knee=4,"
             f"afade=t=in:d=0.4,afade=t=out:st={max(0.0, total - 1.5):.3f}:d=1.5[out]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-stream_loop", "-1", "-i", str(music), "-i", str(vo),
                    "-filter_complex", graph, "-map", "[out]", "-t", f"{total:.3f}", str(dest)], check=True)
    return dest


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("config")
    ap.add_argument("--phase", choices=["render", "build", "all"], default="all")
    ap.add_argument("--takes", type=int, default=3)
    ap.add_argument("--only", help="substring filter on variant name")
    ap.add_argument("--reverse", action="store_true",
                    help="work through the variants last to first (a second render worker, e.g. on CPU)")
    args = ap.parse_args()
    variants = [v for v in json.loads(Path(args.config).read_text(encoding="utf-8"))
                if not args.only or args.only in v["name"]]
    if args.reverse:
        variants.reverse()
    if args.phase in ("render", "all"):
        render(variants, args.takes, args.reverse)
    if args.phase in ("build", "all"):
        scorer = Scorer()
        for v in variants:
            build(v, args.takes, scorer)


if __name__ == "__main__":
    main()
