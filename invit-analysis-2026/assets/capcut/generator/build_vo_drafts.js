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
const { reels } = require('./reels.js');

const MANIFEST = path.join(__dirname, '..', '..', 'voiceover', 'voiceover_manifest.json');
const END_CUES = JSON.parse(fs.readFileSync(path.join(__dirname, 'end_cues.json'), 'utf8'));
const BACKUP_ROOT = path.join(__dirname, '..', `live_drafts_backup_${new Date().toISOString().slice(0, 10).replace(/-/g, '')}`);
const TAIL_SEC = 0.8; // picture held after the last VO line ends
const CARD_LEAD_SEC = 0.15; // a card lands just before its line is said
const MIN_FOOTAGE_SEC = 0.5; // shorter than this, the outro starts on the disclaimer
const END_CARDS = { disclaimer: 'images/end_cards/disclaimer_card.png', cta: 'images/end_cards/cta_card.png' };
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

// Beat i starts where VO section i was placed; the last beat runs to the end of the VO.
function retime(beats, segments) {
  if (beats.length !== segments.length) {
    throw new Error(`${beats.length} beats but ${segments.length} VO sections`);
  }
  const last = segments[segments.length - 1];
  const ends = segments.slice(1).map((s) => s.placed_at).concat(last.placed_at + last.duration + TAIL_SEC);
  return beats.map((beat, i) => ({ ...beat, durationSec: ends[i] - (i ? segments[i].placed_at : 0) }));
}

// Splits the outro beat into footage -> disclaimer card -> call-to-action card at
// the cue times (seconds into the outro's VO clip).
function withEndCards(beats, segments, cues, cards = END_CARDS) {
  const outro = beats[beats.length - 1];
  const start = segments[segments.length - 1].placed_at;
  const end = start + outro.durationSec;
  const at = (card) => {
    const cue = cues.find((c) => c.card === card);
    if (!cue) throw new Error(`no ${card} cue in end_cues.json - run voiceover/mention_times.py`);
    return Math.min(end, Math.max(start, start + cue.offset - CARD_LEAD_SEC));
  };
  let disclaimer = at('disclaimer');
  const cta = at('cta');
  if (disclaimer - start < MIN_FOOTAGE_SEC) disclaimer = start;
  const parts = [
    { ...outro, durationSec: disclaimer - start },
    { file: cards.disclaimer, durationSec: cta - disclaimer },
    { file: cards.cta, durationSec: end - cta },
  ].filter((b) => b.durationSec > 0);
  return beats.slice(0, -1).concat(parts);
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
