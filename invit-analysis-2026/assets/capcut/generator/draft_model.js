// Pure helpers for building CapCut draft JSON: timing, segments and text overlays.
//
// Nothing here touches the file system or the environment. Data that build_draft.js
// reads from disk (the probed clip lengths and the text styles) is passed in as
// arguments, which keeps these functions testable with `node --test`.

const crypto = require('crypto');
const path = require('path');

// CapCut ids are upper-case UUIDs.
function guid() {
  return crypto.randomUUID().toUpperCase();
}

// Windows-style absolute path for a file under `root`, as CapCut stores it.
function winPath(relPath, root) {
  return path.join(root, relPath).replace(/\//g, '\\');
}

function isImage(relPath) {
  return /\.(png|jpe?g)$/i.test(relPath);
}

// A clip is trimmed one frame short of its probed length, so the last frame never
// runs past the end of the source.
const FRAME_US = 33334;

// A clip shorter than its beat loops, or - when the beat names a `hold` still - plays
// once and then holds on that still. Returns [{ file, durationUs }].
// `probeVideos` maps a video path to { durationUs } as recorded by probe_assets.js.
function beatParts(beat, durationUs, probeVideos) {
  if (isImage(beat.file)) return [{ file: beat.file, durationUs }];
  const info = probeVideos[beat.file];
  if (!info) throw new Error(`No probe data for video ${beat.file}`);
  const clipUs = info.durationUs - FRAME_US;
  const parts = [];
  for (let left = durationUs; left > 0;) {
    if (parts.length && beat.hold) {
      parts.push({ file: beat.hold, durationUs: left });
      break;
    }
    const d = Math.min(left, clipUs);
    parts.push({ file: beat.file, durationUs: d });
    left -= d;
  }
  return parts;
}

function identityClip() {
  return {
    alpha: 1.0,
    flip: { horizontal: false, vertical: false },
    rotation: 0.0,
    scale: { x: 1.0, y: 1.0 },
    transform: { x: 0.0, y: 0.0 },
  };
}

// A video or still segment on the main track.
function buildSegment(materialId, timelineStartUs, durationUs, sourceStartUs = 0) {
  return {
    id: guid(),
    material_id: materialId,
    target_timerange: { start: timelineStartUs, duration: durationUs },
    source_timerange: { start: sourceStartUs, duration: durationUs },
    speed: 1.0,
    volume: 1.0,
    visible: true,
    clip: identityClip(),
    enable_adjust: true,
    enable_color_correct_adjust: false,
    enable_color_curves: true,
    enable_color_wheels: true,
    enable_lut: true,
    enable_smart_color_adjust: false,
    render_index: 0,
    reverse: false,
    template_id: '',
    track_attribute: 0,
    track_render_index: 0,
    uniform_scale: { on: true, value: 1.0 },
    hdr_settings: null,
    extra_material_refs: [],
    common_keyframes: [],
  };
}

// A voiceover clip on an audio track. `speedId` links the speed object CapCut needs.
function buildAudioSegment(materialId, speedId, timelineStartUs, durationUs) {
  return {
    id: guid(),
    material_id: materialId,
    target_timerange: { start: timelineStartUs, duration: durationUs },
    source_timerange: { start: 0, duration: durationUs },
    render_timerange: { start: 0, duration: 0 },
    speed: 1.0,
    volume: 1.0,
    last_nonzero_volume: 1.0,
    visible: true,
    clip: null,
    uniform_scale: null,
    reverse: false,
    is_loop: false,
    is_tone_modify: false,
    intensifies_audio: false,
    cartoon: false,
    render_index: 0,
    track_render_index: 0,
    track_attribute: 0,
    template_id: '',
    extra_material_refs: [speedId],
    keyframe_refs: [],
    common_keyframes: [],
    source: 'segmentsourcenormal',
  };
}

// ---- Text overlays ----
// Name given to text the builder makes, to tell it apart from text added in CapCut.
const OVERLAY_NAME = 'invit-overlay';
// The big stat number fades in a third of the way into its beat, and at most this late.
const STAT_DELAY_US = 3000000;
// A two-line title is scaled down to fit the frame, as the user did by hand on the
// Roadstar HI name title.
const TWO_LINE_TITLE_SCALE = 0.7365;

const clone = (value) => JSON.parse(JSON.stringify(value));

// `styles` is the parsed text_styles.json: { title: {...}, stat: {...}, _note: ... }.
// `y` overrides the vertical position (-1 bottom .. 1 top); `scale` shrinks text that
// would otherwise run off the 1080-wide frame.
function textOverlay(styles, style, text, startUs, durationUs, y, scale) {
  const s = styles[style];
  const content = clone(s.content);
  content.text = text;
  content.styles.forEach((st) => { st.range = [0, text.length]; });
  const material = { ...clone(s.material), id: guid(), name: OVERLAY_NAME, content: JSON.stringify(content) };
  const animation = { ...clone(s.animation), id: guid() };
  const segment = {
    ...clone(s.segment), id: guid(), material_id: material.id,
    target_timerange: { start: startUs, duration: durationUs }, extra_material_refs: [animation.id],
  };
  if (y !== undefined) segment.clip.transform.y = y;
  if (style === 'title' && text.includes('\n')) segment.clip.scale = { x: TWO_LINE_TITLE_SCALE, y: TWO_LINE_TITLE_SCALE };
  if (scale !== undefined) segment.clip.scale = { x: scale, y: scale };
  return { material, animation, segment };
}

// beat.text = [[style, text, y?, scale?], ...] -> overlays timed inside that beat.
function beatOverlays(styles, beat, startUs, durationUs) {
  return (beat.text || []).map(([style, text, y, scale]) => {
    const delay = style === 'title' ? 0 : Math.min(STAT_DELAY_US, Math.round(durationUs / 3));
    const overlay = textOverlay(styles, style, text, startUs + delay, durationUs - delay, y, scale);
    overlay.segment.invit_style = style; // lets the preview builder retime stats around logo cards
    return { ...overlay, style };
  });
}

// One text track per style, so the overlays of a beat never overlap on a track.
function textTracks(styles, overlays) {
  const tracks = [];
  for (const style of Object.keys(styles).filter((k) => !k.startsWith('_'))) {
    const segs = overlays.filter((o) => o.style === style).map((o) => o.segment);
    if (segs.length) tracks.push({ id: guid(), type: 'text', flag: 0, attribute: 0, name: '', is_default_name: true, segments: segs });
  }
  return tracks;
}

// ---- Reel timeline ----
// How a reel's beats line up with its voiceover and end cards. Pure: it takes the beats
// and the manifest's VO sections and returns new beats.
const TAIL_SEC = 0.8; // picture held after the last VO line ends
const CARD_LEAD_SEC = 0.15; // a card lands just before its line is said
const MIN_FOOTAGE_SEC = 0.5; // shorter than this, the outro starts on the disclaimer
const END_CARDS = { disclaimer: 'images/end_cards/disclaimer_card.png', cta: 'images/end_cards/cta_card.png' };

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


module.exports = {
  guid, winPath, isImage, beatParts, identityClip, buildSegment, buildAudioSegment,
  textOverlay, beatOverlays, textTracks,
  retime, withEndCards, TAIL_SEC, CARD_LEAD_SEC, MIN_FOOTAGE_SEC, END_CARDS,
  FRAME_US, OVERLAY_NAME, STAT_DELAY_US, TWO_LINE_TITLE_SCALE,
};
