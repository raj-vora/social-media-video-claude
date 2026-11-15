"""Renders a CapCut draft to an MP4 preview with ffmpeg, straight from its
draft_content.json, for reviewing a reel without opening CapCut. It is not a CapCut
export: clips, cut points, stills, logo cards, end cards and the voiceover follow
the draft exactly, but text is drawn here (with CapCut's own en.ttf), and every
text and overlay animation is shown as a 0.5s fade.

Handles what the generated drafts use: video/photo segments on video tracks
(fit to the 1080x1920 canvas, then the segment's scale and position), text
segments, and local audio. Drafts with compound clips or CapCut TTS (the
hand-finished Indus EN) are refused.

Writes previews/<draft>_preview.mp4 at the repo root (gitignored).

Usage: .venv-tts/Scripts/python invit-analysis-2026/assets/capcut/generator/render_preview.py InvIT_02_PowerGrid_InvIT_EN [...]

A draft folder path works too (e.g. previews/_ab/drafts/<name>, from build_ab_previews.js).
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# CapCut's draft folder and its en.ttf font come from the environment (see README).
DRAFT_ROOT = Path(os.environ["CAPCUT_DRAFTS_DIR"])
OUT_DIR = Path(__file__).resolve().parents[4] / "previews"
FONT = os.environ["CAPCUT_FONT"]
W, H, FPS = 1080, 1920, 30   # W, H: set per draft from its canvas (the long form is 16:9)
PX_PER_SIZE = 6.1   # CapCut text size -> pixels at 1080 wide, measured on the user's own export
FADE = 0.5
DIP = 0.25          # fade to and from black at a segment marked preview_dip (a chapter change)
BOX_ALPHA = 0.62    # the black panel behind text, when the draft asks for one (preview.text_box)


def sec(us):
    return us / 1e6


def run(args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def fit_box(mw, mh, clip):
    """Size and top-left of a media item on the canvas: fit inside it, then the
    segment's scale, centred on its transform (x, y in -1..1, y up)."""
    f = min(W / mw, H / mh)
    w = round(mw * f * clip["scale"]["x"] / 2) * 2
    h = round(mh * f * clip["scale"]["y"] / 2) * 2
    cx = W / 2 + clip["transform"]["x"] * W / 2
    cy = H / 2 - clip["transform"]["y"] * H / 2
    return w, h, round(cx - w / 2), round(cy - h / 2)


def text_png(material, clip, path, box=False):
    """The text drawn on a transparent full-canvas PNG, where CapCut places it."""
    content = json.loads(material["content"])
    style = content["styles"][0]
    size = style.get("size", material.get("font_size", 15)) * PX_PER_SIZE * clip["scale"]["x"]
    font = ImageFont.truetype(FONT, max(8, round(size)))
    lines = content["text"].split("\n")
    asc, desc = font.getmetrics()
    line_h = (asc + desc) * (1 + material.get("line_spacing", 0.02))
    block_h = line_h * len(lines)
    cx = W / 2 + clip["transform"]["x"] * W / 2
    cy = H / 2 - clip["transform"]["y"] * H / 2
    rgb = tuple(round(c * 255) for c in style["fill"]["content"]["solid"]["color"])
    bold = round(size * 0.025) if style.get("bold") else 0

    def draw(img, fill, dx=0, dy=0):
        d = ImageDraw.Draw(img)
        for i, line in enumerate(lines):
            w = d.textlength(line, font=font)
            y = cy - block_h / 2 + i * line_h
            d.text((cx - w / 2 + dx, y + dy), line, font=font, fill=fill, stroke_width=bold, stroke_fill=fill)

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if box:  # a rounded black panel behind the block, so text reads on any footage
        probe = ImageDraw.Draw(img)
        bw = max(probe.textlength(line, font=font) for line in lines)
        px, py = size * 0.45, size * 0.18
        ImageDraw.Draw(img).rounded_rectangle(
            (cx - bw / 2 - px, cy - block_h / 2 - py, cx + bw / 2 + px, cy + block_h / 2 + py * 1.6),
            radius=size * 0.3, fill=(0, 0, 0, round(255 * BOX_ALPHA)))
    for sh in style.get("shadows", []):
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dist = sh.get("distance", 5) * 0.8
        draw(layer, (0, 0, 0, round(255 * sh.get("alpha", 0.6))), dist, dist)
        img = Image.alpha_composite(img, layer.filter(ImageFilter.GaussianBlur(max(1, size * sh.get("feather", 0.1) * 0.15))))
    draw(img, rgb + (255,))
    img.save(path)


def render(arg):
    folder = Path(arg) if Path(arg).is_dir() else DRAFT_ROOT / arg
    name = folder.name
    draft = folder / "draft_content.json"
    c = json.loads(draft.read_text(encoding="utf-8"))
    global W, H
    W, H = c["canvas_config"]["width"], c["canvas_config"]["height"]
    opts = c.get("preview", {})  # renderer-only options (build_ab_previews.js)
    mats = {m["id"]: (kind, m) for kind, lst in c["materials"].items() if isinstance(lst, list)
            for m in lst if isinstance(m, dict) and "id" in m}
    if any(m.get("type") == "text_to_audio" for m in c["materials"]["audios"]) or \
            any(not m.get("path") for m in c["materials"]["videos"]):
        sys.exit(f"{name}: has CapCut TTS or compound clips - export it from CapCut instead")
    total = sec(c["duration"])
    tmp = Path(tempfile.mkdtemp(prefix=f"preview_{name}_"))

    # 1. Main track: each segment normalised onto the canvas, then concatenated.
    main = next(t for t in c["tracks"] if t["type"] == "video")
    parts = []
    for i, s in enumerate(main["segments"]):
        _, m = mats[s["material_id"]]
        tr = s["target_timerange"]
        dur = sec(tr["duration"])
        # Exact frame count from the timeline position, so segments never drift from the VO.
        frames = round(sec(tr["start"] + tr["duration"]) * FPS) - round(sec(tr["start"]) * FPS)
        if frames <= 0:  # a sliver left over when a clip loops; an empty part would end the concat
            continue
        w, h, x, y = fit_box(m["width"], m["height"], s["clip"])
        src = ["-loop", "1", "-t", f"{dur + 1:.3f}", "-i", m["path"]] if m["type"] == "photo" else \
              ["-ss", f"{sec(s['source_timerange']['start']):.3f}", "-t", f"{dur:.3f}", "-i", m["path"]]
        out = tmp / f"main_{i:03d}.mp4"
        segs = main["segments"]
        dips = []
        if s.get("preview_dip"):
            dips.append(f"fade=t=in:st=0:d={DIP}")
        if i + 1 < len(segs) and segs[i + 1].get("preview_dip"):
            dips.append(f"fade=t=out:st={max(0.0, frames / FPS - DIP):.3f}:d={DIP}")
        dip = "," + ",".join(dips) if dips else ""
        run([*src, "-f", "lavfi", "-i", f"color=black:s={W}x{H}:r={FPS}",
             # setparams: screen recordings tag colour as "reserved", which the scaler refuses.
             "-filter_complex", f"[0:v]setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709,"
                                f"fps={FPS},scale={w}:{h},setsar=1,tpad=stop_mode=clone:stop_duration=2[m];"
                                f"[1:v][m]overlay={x}:{y}:eof_action=repeat,format=yuv420p{dip}",
             "-frames:v", str(frames), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", str(out)])
        parts.append(out)
    (tmp / "main.txt").write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    run(["-f", "concat", "-safe", "0", "-i", str(tmp / "main.txt"), "-c", "copy", str(tmp / "main.mp4")])

    # 2. Overlays (other video tracks + text), each a full-canvas RGBA still, layered by render_index.
    overlays = []
    for t in c["tracks"]:
        if t is main or t["type"] not in ("video", "text"):
            continue
        for s in t["segments"]:
            kind, m = mats[s["material_id"]]
            png = tmp / f"ov_{len(overlays):03d}.png"
            if t["type"] == "text":
                text_png(m, s["clip"], png, box=opts.get("text_box", False))
                fade = True
            else:
                if m["type"] != "photo":
                    sys.exit(f"{name}: video overlays aren't supported")
                w, h, x, y = fit_box(m["width"], m["height"], s["clip"])
                canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                canvas.alpha_composite(Image.open(m["path"]).convert("RGBA").resize((w, h), Image.LANCZOS), (x, y))
                canvas.save(png)
                fade = False
            tr = s["target_timerange"]
            overlays.append((s.get("render_index", 0), png, sec(tr["start"]), sec(tr["duration"]), fade))
    overlays.sort(key=lambda o: o[0])

    # 3. Audio segments.
    audio = []
    for t in c["tracks"]:
        if t["type"] != "audio":
            continue
        for s in t["segments"]:
            _, m = mats[s["material_id"]]
            audio.append((m["path"], sec(s["source_timerange"]["start"]), sec(s["target_timerange"]["start"]),
                          sec(s["target_timerange"]["duration"]), s.get("volume", 1.0)))

    args = ["-i", str(tmp / "main.mp4")]
    graph, last = [], "0:v"
    for i, (_, png, start, dur, fade) in enumerate(overlays, 1):
        args += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(png)]
        f = f",fade=t=in:st=0:d={min(FADE, dur):.2f}:alpha=1" if fade else ""
        graph.append(f"[{i}:v]format=rgba{f},setpts=PTS-STARTPTS+{start:.3f}/TB[o{i}]")
        graph.append(f"[{last}][o{i}]overlay=0:0:eof_action=pass:repeatlast=0[v{i}]")
        last = f"v{i}"
    base = len(overlays) + 1
    for j, (path, src, start, dur, vol) in enumerate(audio):
        args += ["-ss", f"{src:.3f}", "-t", f"{dur:.3f}", "-i", path]
        ms = round(start * 1000)
        graph.append(f"[{base + j}:a]aresample=48000,volume={vol},adelay={ms}|{ms}[a{j}]")
    graph.append("".join(f"[a{j}]" for j in range(len(audio))) + f"amix=inputs={len(audio)}:normalize=0:dropout_transition=0[aout]")
    (tmp / "graph.txt").write_text(";\n".join(graph), encoding="utf-8")

    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / f"{name}_preview.mp4"
    run([*args, "-filter_complex_script", str(tmp / "graph.txt"), "-map", f"[{last}]", "-map", "[aout]",
         "-t", f"{total:.3f}", "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "23",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)])
    print(f"wrote {out}  ({total:.1f}s)")


if __name__ == "__main__":
    for name in sys.argv[1:]:
        render(name)
