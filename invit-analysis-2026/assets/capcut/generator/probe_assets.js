// Probes every video/image asset with ffprobe to get real duration (microseconds,
// CapCut's unit) and pixel dimensions, needed for accurate CapCut material objects.
const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const ASSETS_ROOT = path.resolve(__dirname, '../..');
const FFPROBE = process.env.FFPROBE || 'ffprobe';

function probeVideo(filePath) {
  const out = execFileSync(FFPROBE, [
    '-v', 'error', '-select_streams', 'v:0',
    '-show_entries', 'stream=width,height', '-show_entries', 'format=duration',
    '-of', 'json', filePath
  ]).toString();
  const j = JSON.parse(out);
  const stream = (j.streams || [])[0] || {};
  const durationSec = parseFloat(j.format && j.format.duration || '0');
  return { width: stream.width || 1920, height: stream.height || 1080, durationUs: Math.round(durationSec * 1000000) };
}

function probeImage(filePath) {
  const out = execFileSync(FFPROBE, [
    '-v', 'error', '-select_streams', 'v:0',
    '-show_entries', 'stream=width,height',
    '-of', 'json', filePath
  ]).toString();
  const j = JSON.parse(out);
  const stream = (j.streams || [])[0] || {};
  return { width: stream.width || 1920, height: stream.height || 1080 };
}

// graphics: the long form's animated explainers (make_longform_graphics.py); their
// last-frame holds live in images/graphics.
// end_cards: the full-screen disclaimer / call-to-action stills (make_end_cards.py).
const categories = ['toll_roads_highways', 'power_transmission', 'electrical_substation', 'stock_market_charts', 'construction_growth', 'gas_pipelines', 'indian_roads', 'graphics', 'end_cards'];
const result = { videos: {}, images: {} };

for (const cat of categories) {
  const vDir = path.join(ASSETS_ROOT, 'videos', cat);
  if (fs.existsSync(vDir)) {
    for (const f of fs.readdirSync(vDir)) {
      const full = path.join(vDir, f);
      try {
        result.videos[`videos/${cat}/${f}`] = probeVideo(full);
      } catch (e) {
        console.error(`FAILED probing ${full}: ${e.message}`);
      }
    }
  }
  const iDir = path.join(ASSETS_ROOT, 'images', cat);
  if (fs.existsSync(iDir)) {
    for (const f of fs.readdirSync(iDir)) {
      const full = path.join(iDir, f);
      try {
        result.images[`images/${cat}/${f}`] = probeImage(full);
      } catch (e) {
        console.error(`FAILED probing ${full}: ${e.message}`);
      }
    }
  }
}

fs.writeFileSync(path.join(__dirname, 'asset_probe.json'), JSON.stringify(result, null, 2));
console.log(`Probed ${Object.keys(result.videos).length} videos and ${Object.keys(result.images).length} images.`);
