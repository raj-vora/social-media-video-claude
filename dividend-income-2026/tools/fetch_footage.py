"""Download Pixabay stock footage for the dividend videos into assets/videos/<category>/
and record source pages in assets/manifest.json (Pixabay Content License).

Takes the first search hit per query whose largest rendition is at least 1280 px wide
and no bigger than 40 MB. Skips files already downloaded.

Usage (repo root): .venv-tts/bin/python dividend-income-2026/tools/fetch_footage.py
Reads PIXABAY_API_KEY from .env.
"""

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ASSETS = REPO / "dividend-income-2026" / "assets"
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"}
MANIFEST = ASSETS / "manifest.json"

# category -> search queries (one clip per query)
QUERIES = {
    "coal_mining": ["coal mine", "coal mining excavator", "coal train wagons"],
    "power_lines": ["electricity pylon", "high voltage power lines", "power plant chimney"],
    "city_night": ["kolkata", "india city night traffic", "city lights night aerial"],
    "retail_food": ["supermarket shelves", "wheat field harvest", "grocery shopping"],
    "it_office": ["software developer coding", "data center servers", "office team laptop"],
    "housing": ["apartment buildings india", "construction crane building", "housing society"],
    "motorbikes": ["motorcycle road india", "motorbike traffic", "scooter city"],
    "money": ["coins falling", "indian rupee notes", "money growth plant coins"],
    "finance": ["stock market chart", "calculator finance", "bank building"],
}


def load_env():
    for line in (REPO / ".env").read_text().splitlines():
        k, _, v = line.partition("=")
        if k and not k.startswith("#"):
            os.environ.setdefault(k, v.strip())


def search(q):
    url = "https://pixabay.com/api/videos/?" + urllib.parse.urlencode(
        {"key": os.environ["PIXABAY_API_KEY"], "q": q, "per_page": 20, "safesearch": "true"})
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30) as r:
        return json.load(r)["hits"]


def pick(hits):
    for h in hits:
        for size in ("large", "medium"):
            v = h["videos"].get(size, {})
            if v.get("width", 0) >= 1280 and 0 < v.get("size", 0) <= 40_000_000 and v.get("url"):
                return h, v
    return None, None


def main():
    load_env()
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else []
    have = {m["file"] for m in manifest}
    for cat, queries in QUERIES.items():
        (ASSETS / "videos" / cat).mkdir(parents=True, exist_ok=True)
        for i, q in enumerate(queries, 1):
            rel = f"videos/{cat}/{cat}_{i:02d}.mp4"
            if rel in have and (ASSETS / rel).exists():
                continue
            hit, v = pick(search(q))
            if not hit:
                print("none  ", q)
                continue
            with urllib.request.urlopen(urllib.request.Request(v["url"], headers=HEADERS), timeout=120) as r:
                (ASSETS / rel).write_bytes(r.read())
            manifest.append({"category": cat, "type": "video", "file": rel, "query": q, "source": v["url"],
                             "page": hit["pageURL"], "width": v["width"], "height": v["height"],
                             "duration": hit["duration"], "licence": "Pixabay Content License"})
            print("ok    ", rel, f'{v["width"]}x{v["height"]}', hit["duration"], "s", q)
    MANIFEST.write_text(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main()
