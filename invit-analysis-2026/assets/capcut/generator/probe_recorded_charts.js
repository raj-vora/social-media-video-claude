const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const FFPROBE = process.env.FFPROBE || 'ffprobe';
const ROOT = path.resolve(__dirname, '../../charts/ppt_videos');

function probeVideo(full) {
  const out = execFileSync(FFPROBE, ['-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-show_entries', 'format=duration', '-of', 'json', full]).toString();
  const j = JSON.parse(out);
  const s = (j.streams || [])[0] || {};
  return { width: s.width, height: s.height, durationUs: Math.round(parseFloat(j.format.duration) * 1000000) };
}
function probeImage(full) {
  const out = execFileSync(FFPROBE, ['-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'json', full]).toString();
  const j = JSON.parse(out);
  return { width: j.streams[0].width, height: j.streams[0].height };
}

const probePath = path.join(__dirname, 'asset_probe.json');
const probe = JSON.parse(fs.readFileSync(probePath, 'utf8'));

// Every recorded chart and its freeze-frame still (see charts/generator/export_chart_videos.ps1).
const videoFiles = {};
for (const f of fs.readdirSync(ROOT).filter((f) => f.endsWith('.mp4'))) {
  videoFiles[`charts/ppt_videos/${f}`] = path.join(ROOT, f);
}
const imageFiles = {};
for (const f of fs.readdirSync(path.join(ROOT, 'stills')).filter((f) => f.endsWith('.png'))) {
  imageFiles[`charts/ppt_videos/stills/${f}`] = path.join(ROOT, 'stills', f);
}

for (const [rel, full] of Object.entries(videoFiles)) {
  const info = probeVideo(full);
  probe.videos[rel] = info;
  console.log('VIDEO', rel, info);
}
for (const [rel, full] of Object.entries(imageFiles)) {
  const info = probeImage(full);
  probe.images[rel] = info;
  console.log('IMAGE', rel, info);
}

fs.writeFileSync(probePath, JSON.stringify(probe, null, 2));
