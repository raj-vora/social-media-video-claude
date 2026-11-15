// Adds a logo overlay track to the live CapCut drafts: each company's logo card
// (assets/images/logos/cards/, from make_logo_cards.py) appears as the voiceover
// says its name. Cue times come from logo_cues.json (voiceover/mention_times.py),
// anchored to wherever that VO clip actually sits in the draft, so drafts that
// were retimed or hand-edited in CapCut still line up. Drafts without the VO
// clips fall back to the script's own section timings.
//
// Patches draft_content.json in place - every other track is left as it is.
// Re-running replaces the logo track it added before. Drafts that already have
// logos placed by hand in CapCut are skipped unless --force. Each draft is copied
// to ../live_drafts_backup_<date>/ before its first change that day.
// Run again after build_vo_drafts.js, which rebuilds drafts without logos.
//
// Usage: node add_logos.js [--only 03_irb] [--lang english|hindi] [--variant v2] [--force] [--dry-run]
const fs = require('fs');
const path = require('path');
const { buildSegment, guid, saveContent, DRAFT_ROOT } = require('./build_draft.js');
const { reels } = require('./reels.js');

const ASSETS = path.join(__dirname, '..', '..');
const LOGOS = path.join(ASSETS, 'images', 'logos');
const CUES = JSON.parse(fs.readFileSync(path.join(__dirname, 'logo_cues.json'), 'utf8'));
const REGISTRY = JSON.parse(fs.readFileSync(path.join(LOGOS, 'logos.json'), 'utf8'));
const MANIFEST = JSON.parse(fs.readFileSync(path.join(ASSETS, 'voiceover', 'voiceover_manifest.json'), 'utf8'));
const BACKUP_ROOT = path.join(__dirname, '..', `live_drafts_backup_${new Date().toISOString().slice(0, 10).replace(/-/g, '')}`);
const SUFFIX = { english: 'EN', hindi: 'HI' };

const LEAD_SEC = 0.15;  // card lands just before the name is said
const SHOW_SEC = 3.0;   // how long a card stays up ...
const GAP_SEC = 0.1;    // ... unless the next card needs the slot
const MIN_SEC = 1.0;

const args = process.argv.slice(2);
const flag = (name) => args.includes(name);
const opt = (name) => (args.includes(name) ? args[args.indexOf(name) + 1] : null);

const norm = (p) => (p || '').replace(/\\/g, '/').toLowerCase();
const isCard = (p) => norm(p).includes('/images/logos/cards/');
const isLogo = (p) => norm(p).includes('/images/logos/');

function pngSize(file) {
  const b = fs.readFileSync(file);
  return { width: b.readUInt32BE(16), height: b.readUInt32BE(20) };
}

// Same shape CapCut itself writes for an imported still (type "photo" inside
// materials.videos); stills put in materials.images get pulled off the track.
function photoMaterial(file) {
  const { width, height } = pngSize(file);
  return {
    id: guid(), type: 'photo', material_name: path.basename(file), path: file.replace(/\\/g, '/'),
    duration: 10800000000, width, height, has_audio: false,
    crop: { upper_left_x: 0, upper_left_y: 0, upper_right_x: 1, upper_right_y: 0, lower_left_x: 0, lower_left_y: 1, lower_right_x: 1, lower_right_y: 1 },
    crop_ratio: 'free', crop_scale: 1.0, check_flag: 63, category_id: '', category_name: 'local',
    source_platform: 0, local_material_id: '',
  };
}

// Where (in seconds on the draft timeline) VO section `cue.section` starts, and
// how manifest-time maps into it.
function sectionClock(content, lang, key, cue) {
  const voDir = `${key}_${lang}`;
  const audios = new Map(content.materials.audios.map((a) => [a.id, a]));
  for (const track of content.tracks.filter((t) => t.type === 'audio')) {
    for (const seg of track.segments) {
      const p = norm(audios.get(seg.material_id)?.path);
      if (p.endsWith(`/${voDir}/${cue.file_name}`.toLowerCase())) {
        const speed = seg.speed || 1;
        return (offset) => (seg.target_timerange.start + (offset * 1e6 - seg.source_timerange.start) / speed) / 1e6;
      }
    }
  }
  // No VO clip in the draft: use the script's timestamp for the section, with the
  // spoken offset squeezed into the section's slot.
  const s = MANIFEST[`${lang}/${key}_${lang}`].segments[cue.section];
  return (offset) => s.start + offset * Math.min(1, s.slot / s.duration);
}

function addLogos(content, lang, key) {
  const cues = CUES[`${lang}/${key}_${lang}`] || [];
  const endSec = content.duration / 1e6;
  const timed = cues.map((cue) => ({ ...cue, at: Math.max(0, sectionClock(content, lang, key, cue)(cue.offset) - LEAD_SEC) }))
    .filter((c) => c.at < endSec - MIN_SEC)
    .sort((a, b) => a.at - b.at);
  return placeLogos(content, timed);
}

// Replaces the logo-card track with one showing each cue's card from `at` seconds
// ([{ logo, at }], sorted by time). Returns the placements, for logging.
function placeLogos(content, timed) {
  const endSec = content.duration / 1e6;
  // Drop the logo track from an earlier run, and its materials.
  const ourIds = new Set(content.materials.videos.filter((m) => isCard(m.path)).map((m) => m.id));
  const dropped = new Set();
  content.tracks = content.tracks.filter((t) => {
    const ours = t.segments.length && t.segments.every((s) => ourIds.has(s.material_id));
    if (ours) t.segments.forEach((s) => s.extra_material_refs.forEach((r) => dropped.add(r)));
    return !ours;
  });
  content.materials.videos = content.materials.videos.filter((m) => !ourIds.has(m.id));
  content.materials.speeds = (content.materials.speeds || []).filter((m) => !dropped.has(m.id));

  const track = { id: guid(), type: 'video', attribute: 0, flag: 2, name: '', is_default_name: true, segments: [] };
  const materialIds = new Map();
  const overlayIndex = 1 + Math.max(0, ...content.tracks
    .filter((t) => t.type === 'video' || t.type === 'sticker')
    .flatMap((t) => t.segments.map((s) => s.render_index || 0)));
  const placed = [];
  timed.forEach((cue, i) => {
    const next = timed[i + 1] ? timed[i + 1].at - GAP_SEC : Infinity;
    const durSec = Math.min(SHOW_SEC, next - cue.at, endSec - cue.at);
    if (durSec < MIN_SEC) return;
    const file = path.join(LOGOS, REGISTRY[cue.logo].card);
    if (!materialIds.has(file)) {
      const mat = photoMaterial(file);
      content.materials.videos.push(mat);
      materialIds.set(file, mat.id);
    }
    const speed = { id: guid(), type: 'speed', mode: 0, speed: 1.0, curve_speed: null };
    content.materials.speeds.push(speed);
    const seg = buildSegment(materialIds.get(file), Math.round(cue.at * 1e6), Math.round(durSec * 1e6));
    seg.render_index = overlayIndex;
    seg.extra_material_refs = [speed.id];
    track.segments.push(seg);
    placed.push(`${cue.logo}@${cue.at.toFixed(2)}s/${durSec.toFixed(1)}s`);
  });

  // Overlay sits right above the main video track, as CapCut places one.
  const main = content.tracks.findIndex((t) => t.type === 'video');
  content.tracks.splice(main + 1, 0, track);
  content.tracks.forEach((t, i) => t.segments.forEach((s) => { s.track_render_index = i; }));
  return placed;
}

function main() {
  let changed = 0;
  for (const [key, reel] of Object.entries(reels)) {
    if (opt('--only') && !key.includes(opt('--only'))) continue;
    for (const [lang, suffix] of Object.entries(SUFFIX)) {
      if (opt('--lang') && opt('--lang') !== lang) continue;
      const name = `${reel.draft}_${suffix}${opt('--variant') ? `_${opt('--variant')}` : ''}`;
      const projDir = path.join(DRAFT_ROOT, name);
      const file = path.join(projDir, 'draft_content.json');
      if (!fs.existsSync(file)) { console.log(`MISS ${name}: no draft`); continue; }
      if (fs.existsSync(path.join(projDir, '.locked')) && !flag('--force')) {
        // CapCut leaves .locked behind; only trust it while CapCut is running.
        const running = require('child_process').execSync('tasklist', { encoding: 'utf8' }).toLowerCase().includes('capcut');
        if (running) { console.log(`SKIP ${name}: open in CapCut - close CapCut first`); continue; }
      }
      const content = JSON.parse(fs.readFileSync(file, 'utf8'));
      const handPlaced = content.materials.videos.filter((m) => isLogo(m.path) && !isCard(m.path));
      if (handPlaced.length && !flag('--force')) {
        console.log(`SKIP ${name}: logos already placed by hand (${handPlaced.map((m) => m.material_name).join(', ')}); --force to add cards too`);
        continue;
      }
      const placed = addLogos(content, lang, key);
      if (flag('--dry-run')) { console.log(`DRY  ${name}: ${placed.join('  ')}`); continue; }
      const backup = path.join(BACKUP_ROOT, name);
      if (!fs.existsSync(backup)) fs.cpSync(projDir, backup, { recursive: true });
      saveContent(projDir, content);
      changed++;
      console.log(`OK   ${name}: ${placed.join('  ')}`);
    }
  }
  console.log(`\n${changed} draft(s) updated.`);
}

if (require.main === module) main();

module.exports = { addLogos, placeLogos };
