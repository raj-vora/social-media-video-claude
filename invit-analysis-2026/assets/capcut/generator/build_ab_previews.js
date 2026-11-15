// Builds a draft for each A/B voiceover variant (voiceover/ab_voice.py's
// previews/_ab/<name>/plan.json), for render_preview.py to render. The drafts go to
// previews/_ab/drafts/<name>/, not CapCut's folder: they exist to be previewed.
//
// Same timeline as build_vo_drafts.js - beats retimed to the VO sections, outro
// ending on the end cards, logo cards on cue - with two optional extras:
//   - a hook variant's own title replaces the hook beat's overlay;
//   - "sfx": a whoosh on every cut (a tech slide into charts) and an impact under
//     the opening line, plus the plan's ducked music bed on its own audio track.
//
// Usage: node build_ab_previews.js [name-substring ...]   (default: every plan)
const fs = require('fs');
const path = require('path');
const { buildProject, buildAudioMaterial, buildAudioSegment, guid, ASSETS_ROOT } = require('./build_draft.js');
const { retime, withEndCards } = require('./build_vo_drafts.js');
const { placeLogos } = require('./add_logos.js');
const { reels, longform } = require('./reels.js');

const AB_ROOT = path.join(ASSETS_ROOT, '..', '..', 'previews', '_ab');
const SFX_DIR = path.join(AB_ROOT, 'sfx_dl');
const SFX = {
  impact: { file: 's2908.mp3', volume: 0.45, lead: 0 },      // Mixkit "Movie trailer epic impact"
  whoosh: { file: 's1492.mp3', volume: 0.5, lead: 0.3 },   // Mixkit "Cinematic whoosh fast transition"
  slide: { file: 's3120.mp3', volume: 0.8, lead: 0.2 },     // Mixkit "Technology transition slide"
};
const LOGO_LEAD_SEC = 0.15; // as add_logos.js

const rel = (abs) => path.relative(ASSETS_ROOT, abs);

function probeSec(file) {
  const out = require('child_process').execFileSync('ffprobe',
    ['-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nw=1:nk=1', file], { encoding: 'utf8' });
  return parseFloat(out);
}

// An audio track of [{ file (absolute), startSec, durationSec, volume }].
function audioTrack(content, clips) {
  const track = { id: guid(), type: 'audio', attribute: 0, flag: 0, name: '', is_default_name: true, segments: [] };
  for (const c of clips) {
    const durationUs = Math.round(c.durationSec * 1e6);
    const mat = buildAudioMaterial(rel(c.file), durationUs);
    const speed = { id: guid(), type: 'speed', mode: 0, speed: 1.0, curve_speed: null };
    content.materials.audios.push(mat);
    content.materials.speeds.push(speed);
    const seg = buildAudioSegment(mat.id, speed.id, Math.round(c.startSec * 1e6), durationUs);
    seg.volume = c.volume;
    track.segments.push(seg);
  }
  content.tracks.push(track);
  content.tracks.forEach((t, i) => t.segments.forEach((s) => { s.track_render_index = i; }));
}

function sfxClips(beats, totalSec) {
  const clip = (kind, at) => {
    const { file, volume, lead } = SFX[kind];
    const full = path.join(SFX_DIR, file);
    const startSec = Math.max(0, at - lead);
    return { file: full, startSec, durationSec: Math.min(probeSec(full), totalSec - startSec), volume };
  };
  const clips = [clip('impact', 0)];
  let at = 0;
  beats.forEach((b, i) => {
    if (i) clips.push(clip(b.file.startsWith('charts/') ? 'slide' : 'whoosh', at));
    at += b.durationSec;
  });
  return clips;
}

// Retimes beats to the sections; `groups` (beat indices per section, for a script
// with fewer sections than the reel has beats) splits a section across its beats
// in proportion to their scripted lengths.
function regroup(beats, groups, sections) {
  if (!groups) return retime(beats, sections);
  const merged = retime(groups.map((g) => beats[g[g.length - 1]]), sections);
  return groups.flatMap((g, i) => {
    const total = g.reduce((t, j) => t + beats[j].durationSec, 0);
    return g.map((j) => ({ ...beats[j], durationSec: merged[i].durationSec * beats[j].durationSec / total }));
  });
}

// Long form: each shot starts on its line of VO (`at` = sentence index in the
// chapter, from plan.sections[i].sentences), a beat early; a chapter's first shot
// starts with the chapter. Returns the beats and the chapter start times.
const CUE_LEAD_SEC = 0.2;
function cueShots(chapters, sections) {
  const spans = retime(chapters.map((c) => c[0]), sections); // each chapter as one beat
  const chapterStarts = [];
  const beats = chapters.flatMap((shots, i) => {
    const start = i ? sections[i].placed_at : 0;
    const end = start + spans[i].durationSec;
    if (i) chapterStarts.push(start);
    const sentences = sections[i].sentences || [];
    const starts = shots.map((shot, k) => {
      if (!k) return start;
      if (!sentences[shot.at]) throw new Error(`chapter ${i}: no sentence ${shot.at} (has ${sentences.length})`);
      return sections[i].placed_at + sentences[shot.at][0] - CUE_LEAD_SEC;
    });
    return shots.map((shot, k) => {
      const durationSec = (k + 1 < shots.length ? starts[k + 1] : end) - starts[k];
      if (durationSec < 0.5) throw new Error(`chapter ${i} shot ${k}: ${durationSec.toFixed(2)}s - cues out of order?`);
      return { ...shot, durationSec };
    });
  });
  return { beats, chapterStarts };
}

// Long-form finish:
// - logo cards sized for 16:9 and kept off graphics and charts, which carry their
//   own names (a card is cut where one starts, or dropped if little is left);
// - the big stat smaller and in the lower third, clear of the logo card above it;
// - a dip to black at each chapter, and a panel behind text (render_preview.py options).
const LOGO_SCALE = 0.38;
const isGraphic = (p) => /(^|[\\/])(graphics|ppt_videos)[\\/]/.test(p);
function finishLongform(content, chapterStarts) {
  const main = content.tracks.findIndex((t) => t.type === 'video');
  const mats = new Map(content.materials.videos.map((m) => [m.id, m]));
  const graphicStarts = content.tracks[main].segments
    .filter((seg) => isGraphic(mats.get(seg.material_id).path))
    .map((seg) => [seg.target_timerange.start, seg.target_timerange.start + seg.target_timerange.duration]);
  const logoTrack = content.tracks[main + 1];
  logoTrack.segments = logoTrack.segments.filter((seg) => {
    seg.clip.scale = { x: LOGO_SCALE, y: LOGO_SCALE };
    const t = seg.target_timerange;
    let end = t.start + t.duration;
    for (const [gs, ge] of graphicStarts) {
      if (gs <= t.start && t.start < ge) return false;  // lands on a graphic
      if (t.start < gs && gs < end) end = gs;
    }
    t.duration = end - t.start;
    return t.duration >= 1e6;
  });
  for (const track of content.tracks.filter((t) => t.type === 'text')) {
    for (const seg of track.segments.filter((x) => x.invit_style === 'stat')) {
      // Title shots are short now that shots follow the VO: bring the stat in early.
      const t = seg.target_timerange;
      const end = t.start + t.duration;
      const shotStart = content.tracks[main].segments.map((m) => m.target_timerange.start).filter((st) => st <= t.start).pop();
      t.start = Math.min(t.start, shotStart + 400000);
      t.duration = end - t.start;
      seg.clip.scale = { x: 0.6, y: 0.6 };
      seg.clip.transform.y = -0.64;
    }
  }
  for (const seg of content.tracks[main].segments) {
    if (chapterStarts.some((s) => Math.abs(seg.target_timerange.start - s * 1e6) < 40000)) seg.preview_dip = true;
  }
  content.preview = { text_box: true };
}

function build(plan) {
  // "shots": "longform" takes the footage from the long-form shot list instead of the reel.
  const isLong = plan.shots === 'longform';
  const reel = isLong ? longform : reels[plan.reel];
  const sections = plan.sections;
  let beats;
  let chapterStarts = [];
  if (isLong) {
    ({ beats, chapterStarts } = cueShots(longform.chapters, sections));
  } else {
    beats = reel.beats.map((b, i) => (i === 0 && plan.hook_title ? { ...b, text: [['title', plan.hook_title]] } : b));
    beats = regroup(beats, plan.beats, sections);
  }
  beats = withEndCards(beats, sections, plan.end_cues, reel.endCards);
  const voiceover = sections.map((s) => ({ file: rel(s.file), startSec: s.placed_at, durationSec: s.duration }));
  const { content } = buildProject(beats, voiceover, reel.canvas);
  const totalSec = content.duration / 1e6;

  const cues = plan.logo_cues.map((c) => ({ ...c, at: Math.max(0, c.at - LOGO_LEAD_SEC) })).filter((c) => c.at < totalSec - 1);
  const placed = placeLogos(content, cues);
  if (isLong) finishLongform(content, chapterStarts);
  if (plan.sfx) audioTrack(content, sfxClips(beats, totalSec));
  if (plan.bed) audioTrack(content, [{ file: plan.bed, startSec: 0, durationSec: Math.min(probeSec(plan.bed), totalSec), volume: 1 }]);

  const dir = path.join(AB_ROOT, 'drafts', plan.name);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'draft_content.json'), JSON.stringify(content));
  console.log(`OK   ${plan.name}: ${totalSec.toFixed(1)}s  logos ${placed.length}${plan.sfx ? '  +sfx' : ''}${plan.bed ? '  +music' : ''}`);
}

const filters = process.argv.slice(2);
for (const name of fs.readdirSync(AB_ROOT)) {
  const file = path.join(AB_ROOT, name, 'plan.json');
  if (!fs.existsSync(file) || (filters.length && !filters.some((f) => name.includes(f)))) continue;
  build(JSON.parse(fs.readFileSync(file, 'utf8')));
}
