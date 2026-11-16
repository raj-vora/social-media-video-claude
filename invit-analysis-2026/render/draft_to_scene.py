"""Convert a CapCut draft folder into a scene (see SCENE.md).

Used to check the scene renderer against the old draft renderer, and to render drafts that
already exist without CapCut. It reads the same fields render_preview.py reads, so the two
should draw the same thing.

  python invit-analysis-2026/render/draft_to_scene.py <draft folder> [--asset-root DIR] [-o scene.json]

Media paths in a draft are absolute paths under ...\\invit-analysis-2026\\assets. --asset-root
replaces that prefix so the files can be found on another machine.
"""

import argparse
import json
import re
import sys
from pathlib import Path

DRAFT_ASSETS_PREFIX = re.compile(r"^(?:[A-Za-z]:)?[\\/].*?invit-analysis-2026[\\/]assets[\\/]", re.I)


def local_path(raw, asset_root):
    """The file a draft path names, on this machine."""
    if asset_root is None:
        return raw
    rel = DRAFT_ASSETS_PREFIX.sub("", raw).replace("\\", "/")
    return str(Path(asset_root) / rel)


def sec(us):
    return us / 1e6


def draft_to_scene(folder, asset_root=None):
    folder = Path(folder)
    c = json.loads((folder / "draft_content.json").read_text(encoding="utf-8"))
    if any(m.get("type") == "text_to_audio" for m in c["materials"]["audios"]) or \
            any(not m.get("path") for m in c["materials"]["videos"]):
        sys.exit(f"{folder.name}: has CapCut TTS or compound clips; the scene format can't express them")
    mats = {m["id"]: m for lst in c["materials"].values() if isinstance(lst, list)
            for m in lst if isinstance(m, dict) and "id" in m}
    opts = c.get("preview", {})
    fit_of = lambda clip: {"scale": [clip["scale"]["x"], clip["scale"]["y"]],
                           "position": [clip["transform"]["x"], clip["transform"]["y"]]}

    main = next(t for t in c["tracks"] if t["type"] == "video")
    segs = main["segments"]
    clips = []
    for i, s in enumerate(segs):
        m = mats[s["material_id"]]
        tr = s["target_timerange"]
        dip_in = bool(s.get("preview_dip"))
        dip_out = i + 1 < len(segs) and bool(segs[i + 1].get("preview_dip"))
        clips.append({
            "kind": "still" if m["type"] == "photo" else "video",
            "file": local_path(m["path"], asset_root),
            "width": m["width"], "height": m["height"],
            "start": sec(tr["start"]), "duration": sec(tr["duration"]),
            "source_start": sec(s["source_timerange"]["start"]),
            "fit": fit_of(s["clip"]),
            "dip_in": dip_in, "dip_out": dip_out,
        })

    overlays = []
    for t in c["tracks"]:
        if t is main or t["type"] not in ("video", "text"):
            continue
        for s in t["segments"]:
            m = mats[s["material_id"]]
            tr = s["target_timerange"]
            base = {"layer": s.get("render_index", 0), "start": sec(tr["start"]),
                    "duration": sec(tr["duration"]), "fit": fit_of(s["clip"])}
            if t["type"] == "text":
                content = json.loads(m["content"])
                st = content["styles"][0]
                shadows = [{"distance": sh.get("distance", 5), "alpha": sh.get("alpha", 0.6),
                            "feather": sh.get("feather", 0.1)} for sh in st.get("shadows", [])]
                overlays.append({**base, "kind": "text", "fade": True, "box": opts.get("text_box", False),
                                 "text": content["text"],
                                 "style": {"size": st.get("size", m.get("font_size", 15)),
                                           "color": st["fill"]["content"]["solid"]["color"],
                                           "bold": bool(st.get("bold")),
                                           "line_spacing": m.get("line_spacing", 0.02),
                                           "shadows": shadows}})
            else:
                if m["type"] != "photo":
                    sys.exit(f"{folder.name}: video overlays aren't supported")
                overlays.append({**base, "kind": "still", "fade": False,
                                 "file": local_path(m["path"], asset_root),
                                 "width": m["width"], "height": m["height"]})

    audio = []
    for t in c["tracks"]:
        if t["type"] != "audio":
            continue
        for s in t["segments"]:
            m = mats[s["material_id"]]
            audio.append({"file": local_path(m["path"], asset_root),
                          "source_start": sec(s["source_timerange"]["start"]),
                          "start": sec(s["target_timerange"]["start"]),
                          "duration": sec(s["target_timerange"]["duration"]),
                          "volume": s.get("volume", 1.0)})

    return {
        "name": folder.name,
        "fps": 30,
        "duration": sec(c["duration"]),
        "canvas": {"width": c["canvas_config"]["width"], "height": c["canvas_config"]["height"]},
        "clips": clips,
        "overlays": overlays,
        "audio": audio,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--asset-root", help="local folder that replaces the draft's assets path")
    ap.add_argument("-o", "--out", help="write here instead of stdout")
    a = ap.parse_args()
    scene = draft_to_scene(a.folder, a.asset_root)
    text = json.dumps(scene, indent=1)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
