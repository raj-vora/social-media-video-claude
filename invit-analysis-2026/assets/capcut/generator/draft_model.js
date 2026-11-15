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

module.exports = {
  guid, winPath, isImage, beatParts, identityClip, buildSegment, buildAudioSegment,
  textOverlay, beatOverlays, textTracks,
  FRAME_US, OVERLAY_NAME, STAT_DELAY_US, TWO_LINE_TITLE_SCALE,
};
