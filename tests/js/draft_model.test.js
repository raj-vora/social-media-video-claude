// Tests for the pure CapCut draft helpers. Run with: node --test tests/js/
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const M = require(path.join(__dirname, '..', '..', 'invit-analysis-2026', 'assets', 'capcut', 'generator', 'draft_model.js'));

// A minimal text style in the shape text_styles.json uses.
const STYLES = {
  title: {
    content: { text: '', styles: [{ range: [0, 0], font: 'x' }] },
    material: { type: 'text', name: '' },
    animation: { type: 'in' },
    segment: { clip: { transform: { x: 0, y: 0 }, scale: { x: 1, y: 1 } } },
  },
  stat: {
    content: { text: '', styles: [{ range: [0, 0], font: 'x' }] },
    material: { type: 'text', name: '' },
    animation: { type: 'in' },
    segment: { clip: { transform: { x: 0, y: 0 }, scale: { x: 1, y: 1 } } },
  },
  _note: 'ignored',
};

const SEC = 1000000;

test('guid returns an upper-case UUID and is unique', () => {
  const a = M.guid();
  const b = M.guid();
  assert.match(a, /^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$/);
  assert.notEqual(a, b);
});

test('winPath joins under the root and uses backslashes', () => {
  assert.equal(M.winPath('videos/a/b.mp4', 'C:\\assets'), 'C:\\assets\\videos\\a\\b.mp4');
});

test('isImage recognises png and jpeg in any case, and rejects video', () => {
  assert.equal(M.isImage('images/x.PNG'), true);
  assert.equal(M.isImage('images/x.jpeg'), true);
  assert.equal(M.isImage('images/x.jpg'), true);
  assert.equal(M.isImage('videos/x.mp4'), false);
});

test('beatParts loops a short clip to fill the beat', () => {
  const probe = { 'videos/short.mp4': { durationUs: 5 * SEC } };
  const parts = M.beatParts({ file: 'videos/short.mp4' }, 12 * SEC, probe);
  const total = parts.reduce((sum, p) => sum + p.durationUs, 0);
  assert.equal(total, 12 * SEC);
  assert.ok(parts.length >= 3, 'a 12 s beat from a 5 s clip needs at least three parts');
  assert.ok(parts.every((p) => p.file === 'videos/short.mp4'));
  assert.ok(parts.every((p) => p.durationUs <= 5 * SEC - M.FRAME_US));
});

test('beatParts holds on the still once the clip has played', () => {
  const probe = { 'videos/short.mp4': { durationUs: 5 * SEC } };
  const parts = M.beatParts({ file: 'videos/short.mp4', hold: 'images/still.png' }, 12 * SEC, probe);
  assert.equal(parts[parts.length - 1].file, 'images/still.png');
  assert.equal(parts.reduce((sum, p) => sum + p.durationUs, 0), 12 * SEC);
});

test('beatParts passes a still through as one part', () => {
  const parts = M.beatParts({ file: 'images/still.jpg' }, 3 * SEC, {});
  assert.deepEqual(parts, [{ file: 'images/still.jpg', durationUs: 3 * SEC }]);
});

test('beatParts refuses a video it has no probe data for', () => {
  assert.throws(() => M.beatParts({ file: 'videos/missing.mp4' }, SEC, {}), /No probe data/);
});

test('buildSegment sets both timeranges and the identity transform', () => {
  const seg = M.buildSegment('MAT', 2 * SEC, 4 * SEC, SEC);
  assert.equal(seg.material_id, 'MAT');
  assert.deepEqual(seg.target_timerange, { start: 2 * SEC, duration: 4 * SEC });
  assert.deepEqual(seg.source_timerange, { start: SEC, duration: 4 * SEC });
  assert.deepEqual(seg.clip.scale, { x: 1, y: 1 });
  assert.deepEqual(seg.clip.transform, { x: 0, y: 0 });
});

test('buildAudioSegment links its speed object', () => {
  const seg = M.buildAudioSegment('MAT', 'SPEED', SEC, 2 * SEC);
  assert.deepEqual(seg.extra_material_refs, ['SPEED']);
  assert.deepEqual(seg.target_timerange, { start: SEC, duration: 2 * SEC });
});

test('textOverlay fills the style template with the text and links its animation', () => {
  const before = JSON.stringify(STYLES);
  const o = M.textOverlay(STYLES, 'title', 'Hello', SEC, 2 * SEC);
  const content = JSON.parse(o.material.content);
  assert.equal(content.text, 'Hello');
  assert.deepEqual(content.styles[0].range, [0, 5]);
  assert.equal(o.material.name, M.OVERLAY_NAME);
  assert.deepEqual(o.segment.extra_material_refs, [o.animation.id]);
  assert.equal(o.segment.material_id, o.material.id);
  assert.equal(JSON.stringify(STYLES), before, 'the style template must not be mutated');
});

test('a two-line title is scaled down to fit the frame', () => {
  const o = M.textOverlay(STYLES, 'title', 'Two\nlines', 0, SEC);
  assert.equal(o.segment.clip.scale.x, M.TWO_LINE_TITLE_SCALE);
});

test('textOverlay applies explicit y and scale overrides', () => {
  const o = M.textOverlay(STYLES, 'stat', '+22.7%', 0, SEC, 0.3, 0.5);
  assert.equal(o.segment.clip.transform.y, 0.3);
  assert.deepEqual(o.segment.clip.scale, { x: 0.5, y: 0.5 });
});

test('stat text waits a third of its beat, at most three seconds', () => {
  const short = M.beatOverlays(STYLES, { text: [['stat', '1%']] }, 0, 6 * SEC);
  assert.equal(short[0].segment.target_timerange.start, 2 * SEC);
  assert.equal(short[0].segment.target_timerange.duration, 4 * SEC);

  const long = M.beatOverlays(STYLES, { text: [['stat', '1%']] }, 0, 30 * SEC);
  assert.equal(long[0].segment.target_timerange.start, M.STAT_DELAY_US);
});

test('title text appears at the start of its beat', () => {
  const [o] = M.beatOverlays(STYLES, { text: [['title', 'Hi']] }, 5 * SEC, 6 * SEC);
  assert.equal(o.segment.target_timerange.start, 5 * SEC);
  assert.equal(o.segment.invit_style, 'title');
  assert.equal(o.style, 'title');
});

test('textTracks makes one track per style and skips _ keys', () => {
  const overlays = [
    ...M.beatOverlays(STYLES, { text: [['title', 'A'], ['stat', 'B']] }, 0, 6 * SEC),
    ...M.beatOverlays(STYLES, { text: [['stat', 'C']] }, 6 * SEC, 6 * SEC),
  ];
  const tracks = M.textTracks(STYLES, overlays);
  assert.equal(tracks.length, 2);
  assert.deepEqual(tracks.map((t) => t.segments.length).sort(), [1, 2]);
  assert.ok(tracks.every((t) => t.type === 'text'));
});

test('textTracks returns nothing when there is no text', () => {
  assert.deepEqual(M.textTracks(STYLES, []), []);
});
