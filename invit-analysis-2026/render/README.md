# Rendering without CapCut

This folder turns a reel into an MP4 with ffmpeg. It replaces the CapCut draft step:
the old pipeline wrote a CapCut project and rendered it with `render_preview.py`. The new
one writes a scene (see [SCENE.md](SCENE.md)) and renders it directly.

| File | What it does |
|---|---|
| `build_scene.js` | Reads a reel's beats, voiceover timing, cues and footage, and writes its scene JSON. No CapCut. |
| `render_scene.py` | Renders a scene JSON to MP4 with ffmpeg. |
| `draft_to_scene.py` | Converts an existing CapCut draft folder into a scene. Used to check the renderer and to render old drafts. |
| `SCENE.md` | The scene format. |

## Usage

Scene files are written under `previews/scenes/` and rendered to `previews/`:

```bash
node invit-analysis-2026/render/build_scene.js --only 02_powergrid
.venv-tts/Scripts/python invit-analysis-2026/render/render_scene.py previews/scenes/InvIT_02_PowerGrid_InvIT_EN.json
```

Rendering needs ffmpeg/ffprobe on `PATH`, Pillow, and a TrueType font for the text. Set
`CAPCUT_FONT` to the font file; the reels were drawn with CapCut's `en.ttf`, and any `.ttf`
works for testing.

## How it was checked

- **Renderer against the old renderer.** A synthetic draft with text, stills, a hold, a
  voiceover, and the chapter-dip and text-panel options was rendered by `render_preview.py`
  and by `render_scene.py` (after `draft_to_scene.py`). The decoded video frames and the audio
  were identical.
- **Whole reel against the old chain.** InvIT 02 (PowerGrid, English) was built through
  `build_vo_drafts.js` and `add_logos.js` and rendered by the old renderer, then built through
  `build_scene.js` and rendered by `render_scene.py`. Both give the same 2,187 video frames and
  the same audio, with end cards and logo cards included. The voiceover was a stand-in tone of
  the manifest's durations, because the real recordings are not on the build machine; both
  sides used the same audio.
- **Timeline rules.** `tests/js/build_scene.test.js` covers the pure parts: clip timing, logo
  placement, text layers and the voiceover length.

The old renderer (`assets/capcut/generator/render_preview.py`) is kept only for these checks. The comparison scripts are not in the repo.
