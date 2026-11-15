"""Finds when each company name is spoken in the generated voiceover, so the
CapCut drafts can show that company's logo on cue (capcut/generator/add_logos.js),
and where each outro turns to its disclaimer and its call to action, so the
drafts cut to the end cards there (capcut/generator/build_vo_drafts.js).

Parler renders a section sentence by sentence (cached per sentence) and the raw
section wav is those sentences back to back, so sentence starts in the raw wav
are exact. Within a sentence the name is placed by its share of the spoken
characters. A raw time maps to the final mp3 by running tighten()'s own filter
(pause trimming + tempo) over the raw wav up to that point and measuring it.

Writes assets/capcut/generator/logo_cues.json:
  {"english/02_powergrid_invit_english": [{"logo", "phrase", "section", "file_name", "offset"}]}
and assets/capcut/generator/end_cues.json (the same with "card" in place of "logo"),
where offset is seconds into that section's final mp3.

Usage: .venv-tts/Scripts/python invit-analysis-2026/voiceover/mention_times.py
"""

import hashlib
import itertools
import json
import subprocess
import sys
from pathlib import Path

import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent))
from tts_engines import (PARLER_CACHE, PARLER_MOODS, PARLER_MOODS_LEGACY, PARLER_RECORDING, VOICES,  # noqa: E402
                         _parler_prepare, devanagari_only, split_sentences, spoken)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "assets" / "voiceover" / "voiceover_manifest.json"
OUT = ROOT / "assets" / "capcut" / "generator" / "logo_cues.json"
END_OUT = ROOT / "assets" / "capcut" / "generator" / "end_cues.json"
SILENCE = ("silenceremove=start_periods=1:start_threshold=-40dB:detection=peak"
           ":stop_periods=-1:stop_duration=0.25:stop_threshold=-40dB:stop_silence=0.15")  # as tighten()

# Phrase as written in the script (the Hindi scripts keep company names in Latin
# script) -> logo key in assets/images/logos/logos.json. First mention only.
MENTIONS = {
    "00_summary": [("IndiGrid", "indigrid"), ("Roadstar Infra", "roadstar"), ("IL&FS", "ilfs"),
                   ("IRB InvIT Fund", "irb_invit"), ("PowerGrid InvIT", "pginvit"),
                   ("power-grid giant", "powergrid"), ("पावर-ग्रिड", "powergrid"),
                   ("Indus Infra Trust", "indus"), ("Bharat Highways", "bharat_highways")],
    "01_indus_infra_trust": [("Indus Infra Trust", "indus"), ("Bharat Highways", "bharat_highways")],
    "02_powergrid_invit": [("PowerGrid Infrastructure Investment Trust", "pginvit"),
                           ("Power Grid Corporation", "powergrid")],
    "03_irb_invit_fund": [("IRB InvIT Fund", "irb_invit"), ("IRB Infrastructure", "irb")],
    "04_roadstar_infra": [("Roadstar Infra Investment Trust", "roadstar"), ("IL&FS", "ilfs")],
    "05_indigrid": [("IndiGrid", "indigrid")],
}

# Where a reel's outro (its last section) turns to the disclaimer and to the call to
# action. Per card, the first of these phrases found in the outro wins.
END_CARDS = {
    "english": [("disclaimer", ["Not investment advice", "always check the"]),
                ("cta", ["Follow", "That's the full top five"])],
    "hindi": [("disclaimer", ["यह इन्वेस्टमेंट एडवाइस नहीं है", "ये इन्वेस्टमेंट एडवाइस नहीं है", "इन्वेस्ट करने से पहले"]),
              ("cta", ["टॉप फाइव के बाकी नामों के लिए", "हर एक की डीप-डाइव के लिए", "यह रहा पूरा टॉप फाइव", "कमेंट में बताइए"])],
}


def said(text, lang):
    """The text as the model actually read it (numbers spelled out, Hindi names in Devanagari)."""
    text = spoken(text, lang)
    return devanagari_only(text) if lang == "hindi" else text


def sentence_durations(sentences, params, raw_dur):
    """Durations of the cached Parler takes that make up a raw section wav.

    A take's cache file depends on its mood, which rotates across whichever
    sentences one generate run rendered together - so rather than replaying that,
    try every mood and keep the takes whose lengths add up to the raw wav."""
    options = []
    for sentence in sentences:
        seed = (int(hashlib.sha1(sentence.encode("utf-8")).hexdigest()[:8], 16) + params.get("seed", 0)) % 2**31
        found = set()
        for wording in (*PARLER_MOODS.values(), *PARLER_MOODS_LEGACY.values()):
            desc = params.get("description", wording + PARLER_RECORDING).format(s=params["speaker"])
            path = PARLER_CACHE / (hashlib.sha1(f"{desc}|{seed}|{sentence}".encode("utf-8")).hexdigest()[:16] + ".wav")
            if path.exists():
                found.add(round(sf.info(str(path)).duration, 4))
        if not found:
            return None
        options.append(sorted(found))
    for combo in itertools.product(*options):
        if abs(sum(combo) - raw_dur) < 0.02:
            return list(combo)
    return None


def tightened_length(raw, upto, tempo):
    """Length of tighten()'s output for the first `upto` seconds of the raw wav."""
    out = subprocess.run(["ffmpeg", "-v", "error", "-t", f"{upto:.3f}", "-i", str(raw),
                          "-af", f"{SILENCE},atempo={tempo:.4f}", "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    return len(out) / 4 / 16000


def find_cues(key, entry, wanted, field):
    """`wanted` = [(section index, or None for any, phrase, id)] -> the first spoken
    mention of each id, timed in its section's final mp3, keyed by `field`."""
    lang = key.split("/")[0]
    params = VOICES[entry["voice"]][2]
    found, used = [], set()
    for i, seg in enumerate(entry["segments"]):
        hits = {}
        for sec, phrase, ident in wanted:
            if ident not in used and ident not in hits and sec in (None, i) and phrase in seg["text"]:
                hits[ident] = phrase
        if not hits:
            continue
        sents = _parler_prepare(spoken(seg["text"], lang), lang)
        originals = split_sentences(seg["text"])
        if len(originals) != len(sents):
            sys.exit(f"{key} section {i}: sentence split differs between script and spoken text")
        raw = ROOT / seg["raw"]
        raw_dur = sf.info(str(raw)).duration
        durs = sentence_durations(sents, params, raw_dur)
        if durs is None:
            sys.exit(f"{key} section {i}: no cached sentence takes add up to the raw wav ({raw_dur:.2f}s)")
        full = tightened_length(raw, raw_dur, entry["tempo"])
        print(f"{key} sec{i}: final mp3 {seg['duration']:.2f}s, re-tightened {full:.2f}s")
        for ident, phrase in hits.items():
            j = next(j for j, s in enumerate(originals) if phrase in s)
            pos = originals[j].find(phrase)
            frac = len(said(originals[j][:pos], lang)) / len(said(originals[j], lang))
            t_raw = sum(durs[:j]) + frac * durs[j]
            offset = tightened_length(raw, t_raw, entry["tempo"]) if t_raw > 0 else 0.0
            found.append({field: ident, "phrase": phrase, "section": i,
                          "file_name": seg["file_name"], "offset": round(offset, 2)})
            used.add(ident)
            print(f"    {ident:16} +{offset:5.2f}s  {phrase}")
    return sorted(found, key=lambda c: (c["section"], c["offset"]))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cues, end_cues = {}, {}
    for key, entry in manifest.items():
        lang, stem = key.split("/")
        engine = VOICES[entry["voice"]][0]
        if engine != "parler":
            print(f"skip {key}: {engine} voice has no per-sentence timing")
            continue
        mentions = MENTIONS.get(stem.rsplit("_", 1)[0], [])
        cues[key] = find_cues(key, entry, [(None, phrase, logo) for phrase, logo in mentions], "logo")
        last = len(entry["segments"]) - 1
        wanted = [(last, phrase, card) for card, phrases in END_CARDS[lang] for phrase in phrases]
        end_cues[key] = find_cues(key, entry, wanted, "card")
        missing = {card for card, _ in END_CARDS[lang]} - {c["card"] for c in end_cues[key]}
        if missing:
            sys.exit(f"{key}: no {', '.join(sorted(missing))} phrase found in the outro")

    OUT.write_text(json.dumps(cues, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    END_OUT.write_text(json.dumps(end_cues, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.name} and {END_OUT.name}")


if __name__ == "__main__":
    main()
