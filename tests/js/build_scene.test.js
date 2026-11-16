// Tests for the pure scene builder. Run with: node --test tests/js/build_scene.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const B = require(path.join(__dirname, '..', '..', 'invit-analysis-2026', 'render', 'build_scene.js'));

const SEC = 1;
const STYLES = {
  title: {
    content: { text: '', styles: [{ range: [0, 0], size: 20, bold: true, fill: { content: { solid: { color: [1, 1, 1, 1] } } }, shadows: [{ distance: 4, alpha: 0.5 }] }] },
    material: { type: 'text', name: '', line_spacing: 0.05 },
    animation: { type: 'in' },
    segment: { clip: { transform: { x: 0, y: 0.8 }, scale: { x: 1, y: 1 } } },
  },
  stat: {
    content: { text: '', styles: [{ range: [0, 0], fill: { content: { solid: { color: [1, 0.8, 0, 1] } } } }] },
    material: { type: 'text', name: '', font_size: 30 },
    animation: { type: 'in' },
    segment: { clip: { transform: { x: 0, y: 0 }, scale: { x: 1, y: 1 } } },
  },
};
const PROBE = {
  videos: { 'videos/a.mp4': { durationUs: 5 * 1e6, width: 1920, height: 1080 } },
  images: { 'images/still.png': { width: 1080, height: 1920 }, 'images/logos/cards/x.png': { width: 900, height: 300 } },
};
const CTX = { assetRoot: '/assets', probe: PROBE, styles: STYLES };

test('placeLogos lands each card before its cue and drops ones that are too short', () => {
  const registry = { indus: { card: 'cards/indus.png' }, bh: { card: 'cards/bh.png' } };
  const placed = B.placeLogos([
    { logo: 'indus', at: 5.0 },   // 4.85 after the lead; the next card is 0.5 s later, so this one is too short
    { logo: 'indus', at: 5.5 },   // 5.35: stays up for the full 3 s
    { logo: 'bh', at: 20 },       // 19.85
    { logo: 'indus', at: 200 },   // after the end: dropped
  ], registry, 60);
  assert.deepEqual(placed.map((p) => p.file), ['images/logos/cards/indus.png', 'images/logos/cards/bh.png']);
  assert.equal(placed[0].at, 5.35);
  assert.equal(placed[0].durationSec, 3);
});

test('placeLogos shortens a card that the next one replaces', () => {
  const registry = { a: { card: 'a.png' }, b: { card: 'b.png' } };
  const placed = B.placeLogos([{ logo: 'a', at: 10 }, { logo: 'b', at: 12 }], registry, 60);
  // a: 9.85 -> next at 11.85 - 0.1, so 1.9 s
  assert.equal(placed[0].durationSec, 1.9);
});

test('a scene has a contiguous main track with absolute paths', () => {
  const scene = B.sceneFromTimeline({
    name: 'T',
    beats: [{ file: 'videos/a.mp4', durationSec: 7 }, { file: 'images/still.png', durationSec: 2 }],
  }, CTX);
  // The 7 s beat from a 5 s clip is two parts (a full clip, then the rest); the 2 s still is one.
  assert.equal(scene.clips.length, 3);
  let t = 0;
  for (const c of scene.clips) {
    assert.ok(Math.abs(c.start - t) < 1e-9, `clip starts where the previous one ends (${c.start} vs ${t})`);
    t += c.duration;
  }
  assert.ok(Math.abs(t - 9) < 1e-9);
  assert.equal(scene.clips[0].file, path.join('/assets', 'videos/a.mp4'));
  assert.equal(scene.clips[2].kind, 'still');
  assert.equal(scene.clips[0].width, 1920);
});

test('a still held after a clip plays once and then holds', () => {
  const scene = B.sceneFromTimeline({
    name: 'T',
    beats: [{ file: 'videos/a.mp4', durationSec: 9, hold: 'images/still.png' }],
  }, CTX);
  const last = scene.clips[scene.clips.length - 1];
  assert.equal(last.kind, 'still');
  assert.equal(last.file, path.join('/assets', 'images/still.png'));
});

test('text sits above logo cards, with layers counted up from 14000', () => {
  const scene = B.sceneFromTimeline({
    name: 'T',
    beats: [{ file: 'videos/a.mp4', durationSec: 6, text: [['title', 'Hi'], ['stat', '+1%']] }],
    logos: [{ file: 'images/logos/cards/x.png', at: 1, durationSec: 2 }],
  }, CTX);
  const logo = scene.overlays.find((o) => o.kind === 'still');
  const texts = scene.overlays.filter((o) => o.kind === 'text');
  assert.equal(logo.layer, 1);
  assert.deepEqual(texts.map((t) => t.layer), [14000, 14001]);
  assert.equal(texts[0].text, 'Hi');
  assert.equal(texts[0].style.size, 20);
  assert.equal(texts[0].style.bold, true);
  assert.equal(texts[0].style.line_spacing, 0.05);
  assert.deepEqual(texts[0].style.color, [1, 1, 1, 1]);
  assert.deepEqual(texts[0].style.shadows, [{ distance: 4, alpha: 0.5, feather: 0.1 }]);
  assert.equal(texts[1].style.size, 30, 'falls back to the material font size');
  assert.equal(logo.width, 900, 'logo size is read from the card, not the probe');
});

test('the scene is as long as the longer of the footage and the voiceover', () => {
  const scene = B.sceneFromTimeline({
    name: 'T',
    beats: [{ file: 'videos/a.mp4', durationSec: 3 }],
    voiceover: [{ file: 'voiceover/x.mp3', startSec: 0, durationSec: 4.5 }],
  }, CTX);
  assert.equal(scene.duration, 4.5);
  assert.equal(scene.audio[0].start, 0);
  assert.equal(scene.audio[0].duration, 4.5);
  assert.equal(scene.audio[0].file, path.join('/assets', 'voiceover/x.mp3'));
});

test('a beat with no probe data is an error, not a silent gap', () => {
  assert.throws(() => B.sceneFromTimeline({ name: 'T', beats: [{ file: 'videos/missing.mp4', durationSec: 2 }] }, CTX),
    /No probe data/);
});
