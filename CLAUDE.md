# CLAUDE.md

Guidance for AI coding agents working in this repository.

## What this repo is

Tooling for short vertical videos (9:16, 1080×1920) and some 16:9 long-form videos.
It holds generators, voiceover code, publishing helpers and data scripts. It does not
hold the scripts, footage, data tables or renders for any series. Those are the
author's own, kept outside this repo, so several scripts will not run until content
files of the same names are provided (see the README).

Pipeline stages, each feeding the next: data → scripts → charts → voiceover → CapCut
drafts → logos and end cards → ffmpeg preview.

## Environment

- Windows is the primary target: CapCut, PowerPoint (VBA via COM) and the Windows
  default paths. Linux works for the voiceover, image and preview scripts if the paths
  are set.
- Set these environment variables instead of editing paths in code:
  `CAPCUT_DRAFTS_DIR`, `CAPCUT_FONT`, optionally `FFPROBE`, `PIXABAY_API_KEY`,
  `VIDS_BASE_URL`.
- Python 3.12 for voiceover and images. Node has no dependencies. Model caches go to
  `.cache/`, which is git-ignored.
- Close CapCut before writing draft projects. It overwrites `draft_content.json` from
  memory.

## Conventions

- Run commands from the repo root.
- Media, data tables, scripts and renders are not committed. Keep them out of commits.
- Credentials live in `.env` or `.secrets/`. Both are git-ignored. Never print them, and
  never put a key in code, a comment, or a commit message.
- A CapCut draft's `id` must not change once CapCut has opened it. The builders keep it;
  don't regenerate ids on an existing draft.
- Builders back up a draft before changing it, and skip drafts that a person has edited
  by hand unless forced.

## Script format (parsed by code)

`generate_voiceovers.py` relies on this shape, shown in `examples/sample_script.md`:

- Section headers: `### [m:ss–m:ss] TITLE` (en dash or hyphen).
- One `**VO:** "..."` line per section.
- Then `**On-screen text:**` and `**Visual:**`.

Section *i* of a script lines up with beat *i* of its reel in the reel-definition file,
and the builder throws if the counts differ.

Company names in Hindi scripts stay in Latin script. `tts_engines.py` handles how they
are spoken, and `mention_times.py` matches logo cues on those Latin names.

## Gotchas

- CapCut's `en.ttf` has no glyph for `·`, `•`, `₹` or `→`. Use `|`, `Rs` or words.
- Stills in a CapCut draft must be `type: "photo"` entries in `materials.videos`.
  Entries in `materials.images` move onto sticker tracks and desync the timeline.
- Parler renders one sentence at a time and caches each take. A crash loses only the
  sentence in progress. Run GPU workers in a retry loop, and CPU workers too.
