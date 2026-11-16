"""Render a scene file to an MP4 with ffmpeg.

A scene is a plain JSON description of one vertical reel: a main track of clips played
back to back, overlays (stills and text) on top, and voiceover audio. It knows nothing
about CapCut. SCENE.md documents the format; build_scene.js writes it from a reel's beats.

  python invit-analysis-2026/render/render_scene.py scene.json [more.json ...] [--out-dir DIR]

Writes <out-dir>/<scene name>.mp4 (default: previews/ at the repo root).

Needs ffmpeg/ffprobe on PATH, Pillow, and a TrueType font for text. The font path comes
from the CAPCUT_FONT environment variable (any .ttf works; the reels were drawn with
CapCut's en.ttf). The font is the only machine-specific input.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

PX_PER_SIZE = 6.1   # text size units -> pixels at 1080 wide, measured on a CapCut export
FADE = 0.5          # seconds: text and overlay fade-in
DIP = 0.25          # seconds: fade to and from black at a chapter change
BOX_ALPHA = 0.62    # opacity of the black panel behind text when a text item asks for one
OUT_DIR = Path(__file__).resolve().parents[2] / "previews"


def run(args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def fit_box(mw, mh, fit, W, H):
    """Size and top-left of a media item on the canvas: fit inside it, then the item's scale,
    centred on its position (x, y in -1..1, y up)."""
    f = min(W / mw, H / mh)
    w = round(mw * f * fit["scale"][0] / 2) * 2
    h = round(mh * f * fit["scale"][1] / 2) * 2
    cx = W / 2 + fit["position"][0] * W / 2
    cy = H / 2 - fit["position"][1] * H / 2
    return w, h, round(cx - w / 2), round(cy - h / 2)


def text_png(item, path, W, H, box=False):
    """Draw one text item on a transparent full-canvas PNG."""
    style = item["style"]
    size = style["size"] * PX_PER_SIZE * item["fit"]["scale"][0]
    font = ImageFont.truetype(os.environ["CAPCUT_FONT"], max(8, round(size)))
    lines = item["text"].split("\n")
    asc, desc = font.getmetrics()
    line_h = (asc + desc) * (1 + style.get("line_spacing", 0.02))
    block_h = line_h * len(lines)
    cx = W / 2 + item["fit"]["position"][0] * W / 2
    cy = H / 2 - item["fit"]["position"][1] * H / 2
    rgb = tuple(round(c * 255) for c in style["color"])
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


def render_scene(scene, out_dir, fps=None):
    """Render one scene dict to <out_dir>/<name>.mp4 and return the path."""
    W, H = scene["canvas"]["width"], scene["canvas"]["height"]
    FPS = fps or scene.get("fps", 30)
    name = scene["name"]
    total = float(scene["duration"])
    tmp = Path(tempfile.mkdtemp(prefix=f"render_{name}_"))

    # 1. Main track: each clip normalised onto the canvas, then concatenated.
    clips = scene["clips"]
    parts = []
    for i, c in enumerate(clips):
        # Exact frame count from the timeline position, so clips never drift from the voiceover.
        frames = round((c["start"] + c["duration"]) * FPS) - round(c["start"] * FPS)
        if frames <= 0:  # a sliver left over when a clip loops; an empty part would end the concat
            continue
        w, h, x, y = fit_box(c["width"], c["height"], c["fit"], W, H)
        dur = c["duration"]
        if c["kind"] == "still":
            src = ["-loop", "1", "-t", f"{dur + 1:.3f}", "-i", c["file"]]
        else:
            src = ["-ss", f"{c['source_start']:.3f}", "-t", f"{dur:.3f}", "-i", c["file"]]
        dips = []
        if c.get("dip_in"):
            dips.append(f"fade=t=in:st=0:d={DIP}")
        if c.get("dip_out"):
            dips.append(f"fade=t=out:st={max(0.0, frames / FPS - DIP):.3f}:d={DIP}")
        dip = "," + ",".join(dips) if dips else ""
        out = tmp / f"main_{i:03d}.mp4"
        run([*src, "-f", "lavfi", "-i", f"color=black:s={W}x{H}:r={FPS}",
             # setparams: screen recordings tag colour as "reserved", which the scaler refuses.
             "-filter_complex", f"[0:v]setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709,"
                                f"fps={FPS},scale={w}:{h},setsar=1,tpad=stop_mode=clone:stop_duration=2[m];"
                                f"[1:v][m]overlay={x}:{y}:eof_action=repeat,format=yuv420p{dip}",
             "-frames:v", str(frames), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", str(out)])
        parts.append(out)
    (tmp / "main.txt").write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    run(["-f", "concat", "-safe", "0", "-i", str(tmp / "main.txt"), "-c", "copy", str(tmp / "main.mp4")])

    # 2. Overlays: each a full-canvas RGBA still, layered by its layer number.
    overlays = []
    for j, o in enumerate(scene.get("overlays", [])):
        png = tmp / f"ov_{j:03d}.png"
        if o["kind"] == "text":
            text_png(o, png, W, H, box=o.get("box", False))
        else:
            w, h, x, y = fit_box(o["width"], o["height"], o["fit"], W, H)
            canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            canvas.alpha_composite(Image.open(o["file"]).convert("RGBA").resize((w, h), Image.LANCZOS), (x, y))
            canvas.save(png)
        overlays.append((o.get("layer", 0), j, png, o["start"], o["duration"], o.get("fade", False)))
    overlays.sort(key=lambda o: (o[0], o[1]))

    # 3. Audio: each item is trimmed, scaled, delayed to its start, then mixed.
    audio = scene.get("audio", [])

    args = ["-i", str(tmp / "main.mp4")]
    graph, last = [], "0:v"
    for i, (_, _, png, start, dur, fade) in enumerate(overlays, 1):
        args += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(png)]
        f = f",fade=t=in:st=0:d={min(FADE, dur):.2f}:alpha=1" if fade else ""
        graph.append(f"[{i}:v]format=rgba{f},setpts=PTS-STARTPTS+{start:.3f}/TB[o{i}]")
        graph.append(f"[{last}][o{i}]overlay=0:0:eof_action=pass:repeatlast=0[v{i}]")
        last = f"v{i}"
    base = len(overlays) + 1
    for j, a in enumerate(audio):
        args += ["-ss", f"{a['source_start']:.3f}", "-t", f"{a['duration']:.3f}", "-i", a["file"]]
        ms = round(a["start"] * 1000)
        graph.append(f"[{base + j}:a]aresample=48000,volume={a.get('volume', 1.0)},adelay={ms}|{ms}[a{j}]")
    graph.append("".join(f"[a{j}]" for j in range(len(audio)))
                 + f"amix=inputs={len(audio)}:normalize=0:dropout_transition=0[aout]")
    (tmp / "graph.txt").write_text(";\n".join(graph), encoding="utf-8")

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{name}.mp4"
    run([*args, "-filter_complex_script", str(tmp / "graph.txt"), "-map", f"[{last}]", "-map", "[aout]",
         "-t", f"{total:.3f}", "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "23",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenes", nargs="+", help="scene JSON files")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    a = ap.parse_args()
    for path in a.scenes:
        scene = json.loads(Path(path).read_text(encoding="utf-8"))
        out = render_scene(scene, Path(a.out_dir))
        print(f"wrote {out}  ({float(scene['duration']):.1f}s)")


if __name__ == "__main__":
    sys.exit(main())
