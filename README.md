# social-media-video-claude

Tools that turn research into short vertical videos: a data pipeline, text-to-speech
voiceovers, animated PowerPoint charts, and editable CapCut drafts timed to the
voiceover, with logos, on-screen text, end cards and an ffmpeg preview renderer.

This repository holds the tooling only. The scripts, footage, data tables and rendered
videos for each series are not included; bring your own content. The tools are for
education. Nothing here is investment advice.

## Projects

| Folder | What it builds |
|---|---|
| `invit-analysis-2026/` | Vertical explainers on InvITs: returns data, charts, voiceovers, CapCut drafts, and the publishing helpers for Instagram and YouTube |
| `dividend-income-2026/` | Short and long-form videos on dividend stocks: data scripts, footage fetching, overlays, thumbnails |
| `exdiv-nov-2026/` | Ex-dividend shorts and a long-form video: ex-date data, ASR check, thumbnails |
| `gold-2026/` | Gold and Sovereign Gold Bond price analysis and fetching |

## How the pipeline fits together

1. **Data.** Fetch prices and dividend events (Yahoo Finance) and compute returns. The
   methodology for each series is in its `data/README_methodology.md`.
2. **Scripts.** Each reel is a list of timed sections in the format shown in
   [`examples/sample_script.md`](examples/sample_script.md). The voiceover parser reads
   that format.
3. **Charts.** PowerPoint charts are generated with VBA through COM (Windows). Their
   videos are exported with PowerPoint's own exporter.
4. **Voiceover.** Indic Parler-TTS renders each sentence. Sections are concatenated,
   trimmed and tempo-adjusted.
5. **Drafts.** The CapCut builders write draft projects straight into CapCut's data
   folder, retimed to the voiceover, with overlays and end cards.
6. **Preview.** `render_preview.py` renders a draft to MP4 with ffmpeg, so a reel can be
   reviewed without opening CapCut.

## Setup

- **Windows** for the CapCut, PowerPoint and VBA steps. The voiceover and preview steps
  also run on Linux, but the default paths are Windows-only.
- **Python 3.12** for `voiceover/` and the image and preview scripts. `requirements.txt`
  lists the packages.
- **Node.js.** The generator scripts use only the standard library; there is no
  `package.json`.
- **ffmpeg and ffprobe** on `PATH`.
- **Environment variables** (set them in your shell or system settings; Node does not read `.env`):

  | Variable | Used by | Example |
  |---|---|---|
  | `CAPCUT_DRAFTS_DIR` | CapCut builders, `render_preview.py` | `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft` |
  | `CAPCUT_FONT` | `render_preview.py` | path to CapCut's `en.ttf` |
  | `FFPROBE` | probe scripts (optional) | path to `ffprobe` if it is not on `PATH` |
  | `PIXABAY_API_KEY` | `fetch_footage.py` (optional) | your Pixabay key |
  | `VIDS_BASE_URL` | `publish/host_video.py` (optional) | HTTPS base of your own video host |

- **Credentials** for publishing (Meta and YouTube OAuth) go in a `.secrets/` folder that
  is git-ignored. `publish/post_reel.py` describes the files it reads.

## Placeholder example

[`examples/sample_script.md`](examples/sample_script.md) shows one section in the format
the voiceover parser expects. The builders also read a reel-definition file
(`reels.js`) and per-series script modules. Those hold the content of each series, so
they are not included. Write your own to use the pipeline.

## License

MIT. See [`LICENSE`](LICENSE).
