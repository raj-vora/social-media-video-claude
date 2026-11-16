// Builds the English and Hindi CapCut drafts with the generated voiceover on an
// audio track. The voiceover runs past the scripts' 60s (sections that overrun push
// later ones back), so each storyboard beat is retimed to start where its VO
// section was placed in voiceover_manifest.json; the reel ends shortly after the
// last line.
//
// The outro closes on two full-screen end cards: the disclaimer from where the VO
// says "Not investment advice" (or its Hindi line), then the like/share/follow
// card from the "Follow" line to the end. The cue times come from end_cues.json
// (voiceover/mention_times.py).
//
// Drafts that were edited by hand in CapCut (text, stickers, extra tracks, CapCut
// TTS audio) are skipped unless --force, and any existing draft is copied to
// ../live_drafts_backup_<date>/ before it is overwritten. The builder's own text
// overlays and add_logos.js's logo track don't count as hand edits. New drafts are
// recorded in vo_build_results.json; register them with
//   node register_projects.js vo_build_results.json
//
// --variant <tag> builds a separate draft named <draft>_<lang>_<tag> instead, leaving the
// usual one (e.g. a hand-finished draft) untouched.
//
// Usage: node build_vo_drafts.js [--lang english|hindi] [--only 03_irb] [--variant v2] [--force] [--dry-run]
const fs = require('fs');
const path = require('path');
const { writeProject, buildProject, DRAFT_ROOT, OVERLAY_NAME } = require('./build_draft.js');
const { retime, withEndCards, TAIL_SEC, END_CARDS } = require('./draft_model.js');
const { reels } = require('./reels.js');

const MANIFEST = path.join(__dirname, '..', '..', 'voiceover', 'voiceover_manifest.json');
const END_CUES = JSON.parse(fs.readFileSync(path.join(__dirname, 'end_cues.json'), 'utf8'));
const BACKUP_ROOT = path.join(__dirname, '..', `live_drafts_backup_${new Date().toISOString().slice(0, 10).replace(/-/g, '')}`);
const SUFFIX = { english: 'EN', hindi: 'HI' };

const args = process.argv.slice(2);
const flag = (name) => args.includes(name);
const opt = (name) => (args.includes(name) ? args[args.indexOf(name) + 1] : null);

// Anything beyond our own single video track (+ our local-audio VO track) means
// the draft has been worked on in CapCut.
function handEdited(projDir) {
  const file = path.join(projDir, 'draft_content.json');
  if (!fs.existsSync(file)) return null;
  const content = JSON.parse(fs.readFileSync(file, 'utf8'));
  const texts = new Map(content.materials.texts.map((m) => [m.id, m]));
  const videos = new Map(content.materials.videos.map((m) => [m.id, m]));
  const ours = (t) => t.segments.length && t.segments.every((s) => (t.type === 'text'
    ? texts.get(s.material_id)?.name === OVERLAY_NAME
    : (videos.get(s.material_id)?.path || '').replace(/\\/g, '/').toLowerCase().includes('/images/logos/cards/')));
  const counts = {};
  for (const t of content.tracks.filter((t) => !ours(t))) counts[t.type] = (counts[t.type] || 0) + 1;
  const reasons = Object.entries(counts)
    .filter(([type, n]) => !(type === 'video' && n === 1) && !(type === 'audio' && n === 1))
    .map(([type, n]) => `${n} ${type} track(s)`);
  if (content.materials.audios.some((a) => a.type !== 'extract_music')) reasons.push('CapCut audio/TTS');
  return reasons.length ? reasons.join(', ') : null;
}

function main() {
  const manifest = JSON.parse(fs.readFileSync(MANIFEST, 'utf8'));
  const results = [];

  for (const [key, reel] of Object.entries(reels)) {
    if (opt('--only') && !key.includes(opt('--only'))) continue;
    for (const lang of Object.keys(SUFFIX)) {
      if (opt('--lang') && opt('--lang') !== lang) continue;
      const name = `${reel.draft}_${SUFFIX[lang]}${opt('--variant') ? `_${opt('--variant')}` : ''}`;
      const entry = manifest[`${lang}/${key}_${lang}`];
      // Entries from the original gTTS run store `voice` as gTTS params, not a preset id.
      if (!entry || typeof entry.voice !== 'string' || entry.voice.endsWith('_gtts')) {
        console.log(`WAIT ${name}: voiceover not generated with the chosen voice yet`);
        continue;
      }
      const projDir = path.join(DRAFT_ROOT, name);
      const edited = handEdited(projDir);
      if (edited && !flag('--force')) {
        console.log(`SKIP ${name}: edited in CapCut (${edited}); --force to overwrite (a backup is kept)`);
        continue;
      }

      // Manifest paths are relative to invit-analysis-2026/; the builder's are relative to assets/.
      const voDir = path.posix.dirname(entry.full_track).replace(/^assets\//, '');
      const voiceover = entry.segments.map((s) => ({
        file: `${voDir}/${s.file_name}`, startSec: s.placed_at, durationSec: s.duration,
      }));
      const beats = withEndCards(retime(reel.beats, entry.segments), entry.segments, END_CUES[`${lang}/${key}_${lang}`] || []);
      const totalSec = buildProject(beats, voiceover).totalDurationUs / 1e6;
      const timing = beats.map((b) => b.durationSec.toFixed(1)).join(' + ');

      if (flag('--dry-run')) {
        console.log(`DRY  ${name}: ${totalSec.toFixed(1)}s  (${timing})`);
        continue;
      }
      if (fs.existsSync(projDir)) {
        const backup = path.join(BACKUP_ROOT, name);
        if (!fs.existsSync(backup)) fs.cpSync(projDir, backup, { recursive: true });
      }
      const r = writeProject(name, beats, voiceover);
      results.push({ name, ...r, status: 'OK' });
      console.log(`OK   ${name}: ${totalSec.toFixed(1)}s  (${timing})`);
    }
  }

  if (!flag('--dry-run')) {
    fs.writeFileSync(path.join(__dirname, 'vo_build_results.json'), JSON.stringify(results, null, 2));
  }
}

if (require.main === module) main();

module.exports = { retime, withEndCards, TAIL_SEC };
