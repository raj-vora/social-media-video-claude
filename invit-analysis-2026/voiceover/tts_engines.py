"""TTS engine wrappers shared by voice_samples.py and generate_voiceovers.py.

Every engine exposes synth(text, lang, params, dest) and writes an audio file
(mp3 for the online engines, wav for the local ones) to `dest` minus suffix;
the written path is returned.

Engines:
  gtts    Google Translate TTS (online, one female voice per language)
  edge    Microsoft Edge neural voices (online, free, no key)
  piper   Piper ONNX voices (local, CPU)
  kokoro  Kokoro-82M (local, GPU if available)
  parler  AI4Bharat Indic Parler-TTS (local, GPU; gated model, needs `hf auth login`)

All model downloads go under <repo>/.cache so nothing large lands on C:.
"""

import asyncio
import os
import re
import wave
from functools import lru_cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / ".cache"


def _load_dotenv():
    """Put the repo's .env keys (HF_TOKEN for the gated Indic Parler model) into os.environ."""
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and key and not key.startswith("#"):
                os.environ.setdefault(key, value.strip().strip("\"'"))


_load_dotenv()
os.environ.setdefault("HF_HOME", str(CACHE / "huggingface"))
os.environ.setdefault("TORCH_HOME", str(CACHE / "torch"))
# The local GPU throws intermittent CUDA "illegal memory access" errors (even on
# a plain matmul), so the torch engines default to CPU. TTS_DEVICE=cuda opts in.
DEVICE = os.environ.get("TTS_DEVICE", "cpu")
# `hf auth login` run without HF_HOME set stores the token on C:; use it from there.
_DEFAULT_TOKEN = Path.home() / ".cache" / "huggingface" / "token"
if not (Path(os.environ["HF_HOME"]) / "token").exists() and _DEFAULT_TOKEN.exists():
    os.environ.setdefault("HF_TOKEN_PATH", str(_DEFAULT_TOKEN))

# Local engines can't read Latin-script names inside Hindi text, so spell the
# ones used in the Hindi scripts out in Devanagari (longest match first).
HINDI_TRANSLIT = {
    "PGInvIT": "पी जी इनविट",
    "P G Invit": "पी जी इनविट",  # forms left by SAY_AS, which runs first
    "Invits": "इनविट्स",
    "Invit": "इनविट",
    "InvITs": "इनविट्स",
    "InvIT": "इनविट",
    "IndiGrid": "इंडिग्रिड",
    "IL&FS": "आई एल एंड एफ एस",
    "IRB": "आई आर बी",
    "IPO": "आई पी ओ",
    "PowerGrid": "पावरग्रिड",
    "Roadstar": "रोडस्टार",
    "Infrastructure": "इन्फ्रास्ट्रक्चर",
    "Investment": "इन्वेस्टमेंट",
    "Corporation": "कॉर्पोरेशन",
    "Highways": "हाईवेज़",
    "Bharat": "भारत",
    "Indus": "इंडस",
    "Infra": "इन्फ्रा",
    "Trusts": "ट्रस्ट्स",
    "Trust": "ट्रस्ट",
    "Fund": "फंड",
    "Power": "पावर",
    "Grid": "ग्रिड",
    "India": "इंडिया",
    # dividend passive-income series
    "Hero MotoCorp": "हीरो मोटोकॉर्प",
    "MotoCorp": "मोटोकॉर्प",
    "Hero": "हीरो",
    "Coal": "कोल",
    "Rural Electrification": "रूरल इलेक्ट्रिफिकेशन",
    "Power Finance": "पावर फाइनेंस",
    "Housing and Urban Development": "हाउसिंग एंड अर्बन डेवलपमेंट",
    "Petronet": "पेट्रोनेट",
    "RP-Sanjiv Goenka": "आर पी संजीव गोयनका",
    "Infosys": "इन्फोसिस",
    "HCL Tech": "एच सी एल टेक",
    "HUDCO": "हडको",
    "Vedanta": "वेदांता",
    "CESC": "सेस्क",
    "REC": "आर ई सी",
    "PFC": "पी एफ सी",
    "ITC": "आई टी सी",
    "TCS": "टी सी एस",
    "PTC": "पी टी सी",
    "ROCE": "आर ओ सी ई",
    "ROE": "आर ओ ई",
    "NBFC": "एन बी एफ सी",
    "TDS": "टी डी एस",
    "EV": "ई वी",
    "AI": "ए आई",
    "FMCG": "एफ एम सी जी",
    "YouTube": "यूट्यूब",  # Parler read the Latin word as "you"
}
_TRANSLIT_RE = re.compile(
    "|".join(re.escape(k) for k in sorted(HINDI_TRANSLIT, key=len, reverse=True))
)


def devanagari_only(text):
    return _TRANSLIT_RE.sub(lambda m: HINDI_TRANSLIT[m.group(0)], text)


# Pronunciation fixes applied to every engine's input: neural voices spell
# "InvIT" out as "Inv I.T." / "inventory IT" (it's said "in-vit"), and Parler
# garbles the run-together "IndiGrid".
SAY_AS = {"PGInvIT": "P G Invit", "InvITs": "Invits", "InvIT": "Invit"}
SAY_AS_EN = {"IndiGrid": "Indi Grid"}  # Hindi gets इंडिग्रिड from HINDI_TRANSLIT
_SAY_AS_RE = re.compile("|".join(sorted(SAY_AS, key=len, reverse=True)))
_SAY_AS_EN_RE = re.compile("|".join(sorted(SAY_AS_EN, key=len, reverse=True)))


# Numbers are spelled out before synthesis: Parler garbles digit strings
# ("100 rupees", "169-rupee", "2017"), and words read consistently on every engine.
HINDI_0_99 = (
    "शून्य एक दो तीन चार पाँच छह सात आठ नौ "
    "दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस "
    "बीस इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस "
    "तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस छत्तीस सैंतीस अड़तीस उनतालीस "
    "चालीस इकतालीस बयालीस तैंतालीस चवालीस पैंतालीस छियालीस सैंतालीस अड़तालीस उनचास "
    "पचास इक्यावन बावन तिरेपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ "
    "साठ इकसठ बासठ तिरेसठ चौंसठ पैंसठ छियासठ सड़सठ अड़सठ उनहत्तर "
    "सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उन्यासी "
    "अस्सी इक्यासी बयासी तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी "
    "नब्बे इक्यानवे बानवे तिरानवे चौरानवे पचानवे छियानवे सत्तानवे अट्ठानवे निन्यानवे"
).split()
HINDI_SCALES = [(10_000_000, "करोड़"), (100_000, "लाख"), (1000, "हज़ार"), (100, "सौ")]


def hindi_number(n):
    if n < 100:
        return HINDI_0_99[n]
    for size, word in HINDI_SCALES:
        if n >= size:
            head, rest = divmod(n, size)
            return f"{hindi_number(head)} {word}" + (f" {hindi_number(rest)}" if rest else "")


def english_number(n, is_year):
    from num2words import num2words
    if is_year:
        return num2words(n, lang="en", to="year")
    return num2words(n, lang="en_IN")


_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def numbers_to_words(text, lang):
    def word(m):
        raw = m.group(0).replace(",", "")
        whole, _, frac = raw.partition(".")
        n = int(whole)
        if lang == "hindi":
            out = hindi_number(n)
            return out + (" दशमलव " + " ".join(HINDI_0_99[int(d)] for d in frac) if frac else "")
        is_year = not frac and len(whole) == 4 and 1900 <= n <= 2099
        out = english_number(n, is_year)
        return out + (" point " + " ".join(english_number(int(d), False) for d in frac) if frac else "")
    return _NUMBER_RE.sub(word, text)


def spoken(text, lang):
    text = _SAY_AS_RE.sub(lambda m: SAY_AS[m.group(0)], text)
    if lang == "english":
        text = _SAY_AS_EN_RE.sub(lambda m: SAY_AS_EN[m.group(0)], text)
    text = text.replace("%", " परसेंट" if lang == "hindi" else " percent")
    return numbers_to_words(text, lang)


def split_sentences(text):
    """Split on sentence ends so the local models get short, stable inputs."""
    parts = re.split(r"(?<=[.!?।])\s+", text)
    return [p for p in (s.strip() for s in parts) if p]


# --- online engines -----------------------------------------------------------

def synth_gtts(text, lang, params, dest):
    from gtts import gTTS
    out = dest.with_suffix(".mp3")
    gTTS(text=text, lang={"english": "en", "hindi": "hi"}[lang],
         tld=params.get("tld", "co.in")).save(str(out))
    return out


def synth_edge(text, lang, params, dest):
    import edge_tts
    out = dest.with_suffix(".mp3")
    comm = edge_tts.Communicate(text, params["voice"],
                                rate=params.get("rate", "+0%"),
                                pitch=params.get("pitch", "+0Hz"))
    asyncio.run(comm.save(str(out)))
    return out


# --- local engines ------------------------------------------------------------

def _write_wav(path, audio, rate):
    import numpy as np
    import soundfile as sf
    sf.write(str(path), np.concatenate(audio) if isinstance(audio, list) else audio, rate)


@lru_cache(maxsize=None)
def _piper_voice(model):
    from huggingface_hub import hf_hub_download
    from piper import PiperVoice
    lang_code, name, quality = model.split("-")
    base = f"{lang_code.split('_')[0]}/{lang_code}/{name}/{quality}/{model}.onnx"
    onnx = hf_hub_download("rhasspy/piper-voices", base)
    hf_hub_download("rhasspy/piper-voices", base + ".json")
    return PiperVoice.load(onnx)


def synth_piper(text, lang, params, dest):
    """params: model, plus optional length_scale (pace), noise_scale (intonation
    variation, default 0.667) and noise_w_scale (timing variation, default 0.8)."""
    from piper import SynthesisConfig
    out = dest.with_suffix(".wav")
    if lang == "hindi":
        text = devanagari_only(text)
    config = SynthesisConfig(**{k: v for k, v in params.items() if k != "model"})
    with wave.open(str(out), "wb") as wf:
        _piper_voice(params["model"]).synthesize_wav(text, wf, syn_config=config)
    return out


@lru_cache(maxsize=None)
def _kokoro_pipeline(lang_code):
    from kokoro import KPipeline
    return KPipeline(lang_code=lang_code, repo_id="hexgrad/Kokoro-82M", device=DEVICE)


def synth_kokoro(text, lang, params, dest):
    out = dest.with_suffix(".wav")
    lang_code = params.get("lang_code", "h" if lang == "hindi" else "a")
    if lang_code == "h":
        text = devanagari_only(text)
    pipe = _kokoro_pipeline(lang_code)
    audio = [a.numpy() for _, _, a in pipe(text, voice=params["voice"], speed=params.get("speed", 1.0))]
    _write_wav(out, audio, 24000)
    return out


@lru_cache(maxsize=None)
def _parler():
    import torch
    from parler_tts import ParlerTTSForConditionalGeneration
    from transformers import AutoTokenizer
    device = DEVICE
    # bf16 on GPU: fp16 overflows to NaN logits on longer batches, which trips a
    # device-side assert in torch.multinomial. (Zen 3 CPUs have no fast bf16.)
    dtype = torch.bfloat16 if device.startswith("cuda") else torch.float32
    # Stream weights straight to the target device: a full fp32 copy in RAM
    # first (~3.7 GB) can exhaust the Windows commit limit.
    model = ParlerTTSForConditionalGeneration.from_pretrained(
        "ai4bharat/indic-parler-tts", torch_dtype=dtype, low_cpu_mem_usage=True,
        device_map=device, attn_implementation=os.environ.get("PARLER_ATTN", "eager"))
    tok = AutoTokenizer.from_pretrained("ai4bharat/indic-parler-tts")
    desc_tok = AutoTokenizer.from_pretrained(model.config.text_encoder._name_or_path)
    return model, tok, desc_tok, device


# Parler takes its delivery from a text description, so each sentence gets a
# mood picked from its punctuation and content - the reel doesn't sound like one
# long monotone take. {s} is the speaker name, which keeps the voice identity.
# Worded in the caption vocabulary Parler was trained on (expressivity, pitch, pace):
# the model card lists no emotion control for English or Hindi, so words like
# "thrilled" or "triumphant" did little. Energy comes from "very expressive and
# animated", a higher pitch and a faster pace.
PARLER_MOODS = {
    "hype": "{s} delivers very expressive and animated speech with a slightly high pitch at a fast pace.",
    "thrilled": "{s} delivers very expressive and animated speech with a high pitch at a slightly fast pace.",
    "curious": "{s} delivers expressive and animated speech with a moderate pitch at a slightly fast pace.",
    "suspense": "{s} delivers expressive and animated speech with a slightly low pitch at a slightly slow pace.",
    "confident": "{s} delivers expressive and animated speech with a slightly high pitch at a moderate speed.",
    "warm": "{s} delivers slightly expressive and animated speech with a moderate pitch at a moderate speed.",
    "story": "{s} delivers expressive and animated speech with a moderate pitch at a slightly fast pace.",
    "calm": "{s} delivers slightly expressive and animated speech with a moderate pitch at a moderate speed.",
    "cta": "{s} delivers very expressive and animated speech with a slightly high pitch at a slightly fast pace.",
    "proud": "{s} delivers expressive and animated speech with a slightly high pitch at a slightly fast pace.",
}
# The first wording, which the voiceovers generated before Oct 2026 were rendered
# with; mention_times.py still looks their cached takes up by it.
PARLER_MOODS_LEGACY = {
    "hype": "{s} speaks in a very excited, thrilled and energetic tone, highly expressive, at a fast pace.",
    "thrilled": "{s} speaks in an amazed, delighted and highly expressive tone, full of energy, at a slightly fast pace.",
    "curious": "{s} speaks in a curious, teasing and expressive tone, building anticipation, at a moderate pace.",
    "suspense": "{s} speaks in a dramatic, suspenseful and expressive tone, at a slightly slow pace.",
    "confident": "{s} speaks in a confident, upbeat and enthusiastic tone, stressing every number clearly, at a moderate pace.",
    "warm": "{s} speaks in a warm, friendly and conversational tone, slightly expressive, at a moderate pace.",
    "story": "{s} speaks in an engaging, animated storytelling tone, quite expressive, at a moderate pace.",
    "calm": "{s} speaks in a calm, sincere and clear tone, at a moderate pace.",
    "cta": "{s} speaks in a cheerful, upbeat and friendly tone, full of energy, at a slightly fast pace.",
    "proud": "{s} speaks in a proud, triumphant and expressive tone, with a lot of energy, at a moderate pace.",
}
EXCITED_ROTATION = ["hype", "thrilled", "proud"]
CALM_ROTATION = ["warm", "story"]
PARLER_RECORDING = " The recording is very close-sounding with very clear audio and no background noise."
_NUMBERISH = re.compile(r"\d|percent|rupee|परसेंट|रुपये|सौ|हज़ार", re.I)


def parler_mood(sentence, counts, hook=False):
    """Mood for one sentence; `counts` tracks rotations across a reel's sentences.
    In a hook, plain statements are read as a tease (curious) rather than calmly."""
    s = sentence.strip().strip('"')
    low = s.lower()
    if "investment advice" in low or "इन्वेस्टमेंट एडवाइस" in s or "check the" in low or "चेक करें" in s:
        return "calm"
    if low.startswith("follow") or "follow," in low or "फॉलो" in s:
        return "cta"
    if s.endswith("?"):
        return "curious"
    if s.endswith("..."):
        return "suspense"
    if s.endswith("!"):
        counts["excited"] = counts.get("excited", -1) + 1
        return EXCITED_ROTATION[counts["excited"] % len(EXCITED_ROTATION)]
    if hook:
        return "curious"
    if _NUMBERISH.search(s):
        return "confident"
    counts["calm"] = counts.get("calm", -1) + 1
    return CALM_ROTATION[counts["calm"] % len(CALM_ROTATION)]


# One sentence per generate(): larger batches crash this GPU far more often, and
# sequential decoding is nearly as fast. Every sentence is cached on disk as soon
# as it's rendered, so a crashed run (see voice_samples.py --isolate) resumes
# where it stopped instead of starting over.
PARLER_CACHE = CACHE / "parler_sentences"


def parler_plan(sentences, params):
    """[(sentence, description, seed, cache path)] for one parler_sentences() call."""
    import hashlib
    plan, counts = [], {}
    for sentence in sentences:
        mood = params.get("mood") or parler_mood(sentence, counts, params.get("hook", False))
        desc = params.get("description", PARLER_MOODS[mood] + PARLER_RECORDING).format(s=params["speaker"])
        # A different seed per sentence (stable across runs) varies the prosody;
        # params["seed"] shifts them all to re-roll a take.
        seed = (int(hashlib.sha1(sentence.encode("utf-8")).hexdigest()[:8], 16) + params.get("seed", 0)) % 2**31
        key = hashlib.sha1(f"{desc}|{seed}|{sentence}".encode("utf-8")).hexdigest()[:16]
        plan.append((sentence, desc, seed, PARLER_CACHE / f"{key}.wav"))
    return plan


def parler_sentences(sentences, params):
    """Render sentences with one Parler voice; returns (float32 arrays, sample rate)."""
    import soundfile as sf
    PARLER_CACHE.mkdir(parents=True, exist_ok=True)
    audio, rate = [], 44100
    for sentence, desc, seed, cached in parler_plan(sentences, params):
        if not cached.exists():
            import torch
            model, tok, desc_tok, device = _parler()
            d = desc_tok(desc, return_tensors="pt").to(device)
            prompt = tok(sentence, return_tensors="pt").to(device)
            torch.manual_seed(seed)
            gen = model.generate(input_ids=d.input_ids, attention_mask=d.attention_mask,
                                 prompt_input_ids=prompt.input_ids,
                                 prompt_attention_mask=prompt.attention_mask)
            sf.write(str(cached), gen.to(torch.float32).cpu().numpy().squeeze(),
                     model.config.sampling_rate)
        data, rate = sf.read(str(cached), dtype="float32")
        audio.append(data)
    return audio, rate


def _parler_prepare(text, lang):
    return split_sentences(devanagari_only(text) if lang == "hindi" else text)


def synth_parler(text, lang, params, dest):
    out = dest.with_suffix(".wav")
    audio, rate = parler_sentences(_parler_prepare(text, lang), params)
    _write_wav(out, audio, rate)
    return out


def synth_many(engine, texts, lang, params, dests):
    """synth() over several texts (Parler renders and caches them sentence by
    sentence). Returns the written paths."""
    if engine != "parler":
        return [synth(engine, t, lang, params, d) for t, d in zip(texts, dests)]
    per_text = [_parler_prepare(spoken(t, lang), lang) for t in texts]
    flat = [s for sents in per_text for s in sents]
    audio, rate = parler_sentences(flat, params)
    outs, k = [], 0
    for sents, dest in zip(per_text, dests):
        out = Path(dest).with_suffix(".wav")
        _write_wav(out, audio[k:k + len(sents)], rate)
        k += len(sents)
        outs.append(out)
    return outs


ENGINES = {
    "gtts": synth_gtts,
    "edge": synth_edge,
    "piper": synth_piper,
    "kokoro": synth_kokoro,
    "parler": synth_parler,
}


def synth(engine, text, lang, params, dest):
    return ENGINES[engine](spoken(text, lang), lang, params, Path(dest))


# --- voice presets ------------------------------------------------------------
# id -> (engine, language, params, description). Ids are what --voice-en /
# --voice-hi take in generate_voiceovers.py.

PARLER_EN_MALE = ["Thoma", "Dinesh", "Jatin", "Aakash", "Kabir", "Tarun", "Raghav", "Ravi", "Vikas"]
PARLER_EN_FEMALE = ["Mary"]  # with Thoma, the model card's recommended English voices
PARLER_HI_MALE = ["Rohit", "Aman"]

VOICES = {
    "en_gtts": ("gtts", "english", {}, "gTTS en (co.in) - current, female"),
    "hi_gtts": ("gtts", "hindi", {}, "gTTS hi (co.in) - current, female"),

    "en_edge_prabhat": ("edge", "english", {"voice": "en-IN-PrabhatNeural"},
                        "Edge Prabhat - Indian English male"),
    "en_edge_prabhat_deep": ("edge", "english", {"voice": "en-IN-PrabhatNeural", "pitch": "-6Hz"},
                             "Edge Prabhat, pitched down"),
    "en_edge_madhur": ("edge", "english", {"voice": "hi-IN-MadhurNeural"},
                       "Edge Madhur (Hindi voice) reading English - stronger desi accent"),
    "hi_edge_madhur": ("edge", "hindi", {"voice": "hi-IN-MadhurNeural"},
                       "Edge Madhur - Hindi male"),
    "hi_edge_madhur_deep": ("edge", "hindi", {"voice": "hi-IN-MadhurNeural", "pitch": "-6Hz"},
                            "Edge Madhur, pitched down"),

    "hi_piper_pratham": ("piper", "hindi", {"model": "hi_IN-pratham-medium"}, "Piper Pratham - Hindi male"),
    "hi_piper_pratham_lively": ("piper", "hindi", {"model": "hi_IN-pratham-medium", "noise_scale": 0.85,
                                                   "noise_w_scale": 1.0},
                                "Piper Pratham, livelier intonation"),
    "hi_piper_pratham_vivid": ("piper", "hindi", {"model": "hi_IN-pratham-medium", "noise_scale": 1.0,
                                                  "noise_w_scale": 1.2},
                               "Piper Pratham, most varied intonation"),
    "hi_piper_rohan": ("piper", "hindi", {"model": "hi_IN-rohan-medium"}, "Piper Rohan - Hindi male"),

    "hi_kokoro_omega": ("kokoro", "hindi", {"voice": "hm_omega"}, "Kokoro Omega - Hindi male"),
    "hi_kokoro_psi": ("kokoro", "hindi", {"voice": "hm_psi"}, "Kokoro Psi - Hindi male"),
    "en_kokoro_omega": ("kokoro", "english", {"voice": "hm_omega", "lang_code": "h"},
                        "Kokoro Omega (Hindi voice) reading English - experimental"),
    **{f"en_parler_{s.lower()}": ("parler", "english", {"speaker": s}, f"Indic Parler {s} - Indian English")
       for s in PARLER_EN_MALE + PARLER_EN_FEMALE},
    **{f"hi_parler_{s.lower()}": ("parler", "hindi", {"speaker": s}, f"Indic Parler {s} - Hindi")
       for s in PARLER_HI_MALE},
}
