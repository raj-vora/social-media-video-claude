// Writes a scene (see SCENE.md) for each reel from its beats, its voiceover timing and its
// cue files. render_scene.py renders the scene to an MP4. No CapCut is involved.
//
// The timeline follows the rules the CapCut builders used, so the same reel renders the
// same way: beats are retimed to the voiceover sections, the outro is split into footage
// and two end cards, text comes from text_styles.json, and each company logo card appears
// as its name is said (logo_cues.json, anchored to the manifest's section times).
//
//   node invit-analysis-2026/render/build_scene.js [--lang english|hindi] [--only 02_powergrid] [--out DIR]
//
// Writes <out>/<draft name>.json (default: previews/scenes/ at the repo root).
const fs = require('fs');
const path = require('path');
const M = require('../assets/capcut/generator/draft_model.js');

const ASSETS = path.resolve(__dirname, '..', 'assets');
const GEN = path.join(ASSETS, 'capcut', 'generator');
const CANVAS = { width: 1080, height: 1920 };
const FPS = 30;
const SUFFIX = { english: 'EN', hindi: 'HI' };

// Logo timing (see add_logos.js): a card lands just before its name, stays up for up to
// SHOW_SEC, and gives way to the next card after GAP_SEC.
const LEAD_SEC = 0.15;
const SHOW_SEC = 3.0;
const GAP_SEC = 0.1;
const MIN_SEC = 1.0;

const readJson = (file) => JSON.parse(fs.readFileSync(file, 'utf8'));
const us = (sec) => Math.round(sec * 1e6);

// Pixel size from a PNG header (the logo cards aren't in asset_probe.json).
function pngSize(file) {
  const b = fs.readFileSync(file);
  return { width: b.readUInt32BE(16), height: b.readUInt32BE(20) };
}

function identityFit() {
  return { scale: [1, 1], position: [0, 0] };
}

// A text overlay from the draft model, in the scene's shape. Mirrors draft_to_scene.py.
function textItem(o, layer) {
  const content = JSON.parse(o.material.content);
  const st = content.styles[0];
  const clip = o.segment.clip;
  return {
    kind: 'text',
    text: content.text,
    layer,
    start: o.segment.target_timerange.start / 1e6,
    duration: o.segment.target_timerange.duration / 1e6,
    fade: true,
    box: false,
    fit: { scale: [clip.scale.x, clip.scale.y], position: [clip.transform.x, clip.transform.y] },
    style: {
      size: st.size !== undefined ? st.size : (o.material.font_size ?? 15),
      color: st.fill.content.solid.color,
      bold: Boolean(st.bold),
      line_spacing: o.material.line_spacing ?? 0.02,
      shadows: (st.shadows || []).map((sh) => ({
        distance: sh.distance ?? 5, alpha: sh.alpha ?? 0.6, feather: sh.feather ?? 0.1,
      })),
    },
  };
}

// The pure core: beats (already retimed, end cards included), voiceover clips and logo
// cards in, scene out. `assetRoot` turns the relative asset paths into absolute ones.
//   beats:     [{ file, durationSec, hold?, text? }]
//   voiceover: [{ file, startSec, durationSec }]            file relative to assets/
//   logos:     [{ file, at, durationSec }]                  logo cards, seconds on the timeline
//   probe:     { videos: { rel: {durationUs,width,height} }, images: { rel: {width,height} } }
//   styles:    parsed text_styles.json
function sceneFromTimeline({ name, beats, voiceover = [], logos = [] }, { assetRoot, probe, styles }) {
  const abs = (rel) => path.join(assetRoot, rel);
  const clips = [];
  const overlays = [];
  let cursorUs = 0;
  for (const beat of beats) {
    const beatUs = us(beat.durationSec);
    for (const o of M.beatOverlays(styles, beat, cursorUs, beatUs)) overlays.push(o);
    for (const part of M.beatParts(beat, beatUs, probe.videos)) {
      const still = M.isImage(part.file);
      const info = still ? probe.images[part.file] : probe.videos[part.file];
      if (!info) throw new Error(`No probe data for ${part.file}`);
      clips.push({
        kind: still ? 'still' : 'video',
        file: abs(part.file),
        width: info.width,
        height: info.height,
        start: cursorUs / 1e6,
        duration: part.durationUs / 1e6,
        source_start: 0,
        fit: identityFit(),
        dip_in: false,
        dip_out: false,
      });
      cursorUs += part.durationUs;
    }
  }

  // Text draws above the logo cards, in the order the beats add it (as the draft builder does).
  const textItems = overlays.map((o, i) => textItem(o, 14000 + i));

  // Logo cards sit just above the main track.
  const logoItems = [];
  for (const logo of logos) {
    const info = probe.images[logo.file] || pngSize(abs(logo.file));
    logoItems.push({
      kind: 'still',
      file: abs(logo.file),
      width: info.width, height: info.height,
      layer: 1,
      start: us(logo.at) / 1e6,
      duration: us(logo.durationSec) / 1e6,
      fade: false,
      fit: identityFit(),
    });
  }

  let audioEndUs = 0;
  const audio = voiceover.map((v) => {
    const startUs = us(v.startSec);
    const durUs = us(v.durationSec);
    audioEndUs = Math.max(audioEndUs, startUs + durUs);
    return { file: abs(v.file), source_start: 0, start: startUs / 1e6, duration: durUs / 1e6, volume: 1.0 };
  });

  return {
    name,
    fps: FPS,
    duration: Math.max(cursorUs, audioEndUs) / 1e6,
    canvas: { ...CANVAS },
    clips,
    overlays: [...logoItems, ...textItems],
    audio,
  };
}

// Places logo cards the way add_logos.js does: each card lands LEAD_SEC before its cue,
// runs until the next card needs the slot (or SHOW_SEC), and is dropped if it's too short.
function placeLogos(cues, registry, endSec) {
  const timed = cues
    .map((c) => ({ ...c, at: Math.max(0, c.at - LEAD_SEC) }))
    .filter((c) => c.at < endSec - MIN_SEC)
    .sort((a, b) => a.at - b.at);
  const out = [];
  timed.forEach((cue, i) => {
    const next = timed[i + 1] ? timed[i + 1].at - GAP_SEC : Infinity;
    const durationSec = Math.min(SHOW_SEC, next - cue.at, endSec - cue.at);
    if (durationSec < MIN_SEC) return;
    out.push({ file: path.join('images', 'logos', registry[cue.logo].card), at: Math.round(cue.at * 1e6) / 1e6,
               durationSec: Math.round(durationSec * 1e6) / 1e6 });
  });
  return out;
}

// One reel from the project's own files: its beats, its manifest entry and its cues.
function buildReelScene(key, lang, ctx) {
  const reel = ctx.reels[key];
  const name = `${reel.draft}_${SUFFIX[lang]}`;
  const entry = ctx.manifest[`${lang}/${key}_${lang}`];
  if (!entry) throw new Error(`no voiceover manifest entry for ${lang}/${key}_${lang}`);
  const segments = entry.segments;
  const cueKey = `${lang}/${key}_${lang}`;

  // Same as build_vo_drafts.js: beats retimed to the VO, outro split into end cards.
  const beats = M.withEndCards(M.retime(reel.beats, segments), segments, ctx.endCues[cueKey] || []);
  const voDir = path.posix.dirname(entry.full_track).replace(/^assets\//, '');
  const voiceover = segments.map((s) => ({ file: `${voDir}/${s.file_name}`, startSec: s.placed_at, durationSec: s.duration }));

  // Logo cues are anchored to the section's start in the voiceover, as add_logos.js does.
  const cues = (ctx.logoCues[cueKey] || []).map((c) => ({
    logo: c.logo, at: segments[c.section].placed_at + c.offset,
  }));
  const totalSec = Math.max(
    beats.reduce((sum, b) => sum + us(b.durationSec), 0) / 1e6,
    Math.max(0, ...voiceover.map((v) => v.startSec + v.durationSec)),
  );
  const logos = placeLogos(cues, ctx.registry, totalSec);

  return sceneFromTimeline({ name, beats, voiceover, logos }, {
    assetRoot: ctx.assetRoot, probe: ctx.probe, styles: ctx.styles,
  });
}

// reels.js holds each reel's beats (the content). It is loaded here, not at import, so the
// pure functions can be used and tested without it.
function loadContext(assetRoot = ASSETS) {
  return {
    assetRoot,
    reels: require(path.join(GEN, 'reels.js')).reels,
    probe: readJson(path.join(GEN, 'asset_probe.json')),
    styles: readJson(path.join(GEN, 'text_styles.json')),
    endCues: readJson(path.join(GEN, 'end_cues.json')),
    logoCues: readJson(path.join(GEN, 'logo_cues.json')),
    registry: readJson(path.join(ASSETS, 'images', 'logos', 'logos.json')),
    manifest: readJson(path.join(ASSETS, 'voiceover', 'voiceover_manifest.json')),
  };
}

function main() {
  const args = process.argv.slice(2);
  const opt = (name) => (args.includes(name) ? args[args.indexOf(name) + 1] : null);
  const outDir = opt('--out') || path.join(__dirname, '..', '..', 'previews', 'scenes');
  const ctx = loadContext();
  fs.mkdirSync(outDir, { recursive: true });
  for (const key of Object.keys(ctx.reels)) {
    if (opt('--only') && !key.includes(opt('--only'))) continue;
    for (const lang of Object.keys(SUFFIX)) {
      if (opt('--lang') && opt('--lang') !== lang) continue;
      const entry = ctx.manifest[`${lang}/${key}_${lang}`];
      if (!entry || typeof entry.voice !== 'string' || entry.voice.endsWith('_gtts')) {
        console.log(`WAIT ${key} ${lang}: voiceover not generated with the chosen voice yet`);
        continue;
      }
      const scene = buildReelScene(key, lang, ctx);
      const out = path.join(outDir, `${scene.name}.json`);
      fs.writeFileSync(out, JSON.stringify(scene, null, 1));
      console.log(`OK   ${scene.name}: ${scene.duration.toFixed(1)}s -> ${out}`);
    }
  }
}

if (require.main === module) main();

module.exports = { sceneFromTimeline, placeLogos, buildReelScene, loadContext, textItem };
