# Scene format

A scene is a JSON file that describes one reel. `render_scene.py` turns it into an MP4.
Nothing in it is specific to CapCut. All times are in seconds, and all paths are absolute.

```json
{
  "name": "InvIT_02_PowerGrid_InvIT_EN",
  "fps": 30,
  "duration": 61.3,
  "canvas": { "width": 1080, "height": 1920 },
  "clips": [ ... ],
  "overlays": [ ... ],
  "audio": [ ... ]
}
```

## `clips`: the main track

Clips play back to back, in order. Each one covers `[start, start + duration)` on the timeline.

| Field | Meaning |
|---|---|
| `kind` | `"video"` or `"still"` |
| `file` | Absolute path to the media file |
| `width`, `height` | Pixel size of the media |
| `start`, `duration` | Position and length on the timeline |
| `source_start` | Where to start reading a video (ignored for stills) |
| `fit` | `{ "scale": [sx, sy], "position": [x, y] }`, see below |
| `dip_in`, `dip_out` | Fade in from, or out to, black at this clip's edges (chapter changes) |

## `overlays`: stills and text on top

Each overlay is drawn over the main track at its own time. Overlays with a higher `layer`
draw on top of lower ones.

| Field | Meaning |
|---|---|
| `kind` | `"still"` (an image) or `"text"` |
| `layer` | Stacking order (default 0) |
| `start`, `duration` | When it shows |
| `fade` | `true` to fade in over half a second |
| `fit` | Same as for clips. Used for stills and text |
| `file`, `width`, `height` | Stills only |
| `text`, `style`, `box` | Text only (see below) |

Text overlays take a `style`:

| Field | Meaning |
|---|---|
| `size` | Size in CapCut's text units (the renderer multiplies by 6.1 at 1080 px wide) |
| `color` | `[r, g, b]` with values from 0 to 1 |
| `bold` | Boolean |
| `line_spacing` | Extra spacing between lines, as a fraction (default 0.02) |
| `shadows` | List of `{ "distance", "alpha", "feather" }` |

`box: true` draws a black rounded panel behind the text.

## `fit`

`scale` is relative to the media's size after it is fitted inside the canvas. `position` is
the centre, with x from -1 (left) to 1 (right) and y from -1 (bottom) to 1 (top). Both are
the same values CapCut stores in a clip's `transform`.

## `audio`

Each item is one voiceover clip:

| Field | Meaning |
|---|---|
| `file` | Absolute path to the audio file |
| `source_start`, `duration` | The part of the file to use |
| `start` | When it starts on the timeline |
| `volume` | Optional gain (default 1.0) |

The clips are mixed together with `amix`. Nothing is normalised, so the voiceover levels
are set when the clips are generated.
