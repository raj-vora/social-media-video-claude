const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const FFPROBE = process.env.FFPROBE || 'ffprobe';
const ASSETS_ROOT = path.resolve(__dirname, '../..');
const files = [
  'capcut/placeholders/placeholder_return_breakdown.png',
  'capcut/placeholders/placeholder_yearly_track_record.png',
];

const probePath = path.join(__dirname, 'asset_probe.json');
const probe = JSON.parse(fs.readFileSync(probePath, 'utf8'));
delete probe.images['capcut/placeholders/chart_placeholder.png'];

for (const rel of files) {
  const full = path.join(ASSETS_ROOT, rel);
  const out = execFileSync(FFPROBE, ['-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'json', full]).toString();
  const j = JSON.parse(out);
  probe.images[rel] = { width: j.streams[0].width, height: j.streams[0].height };
  console.log(rel, j.streams[0]);
}
fs.writeFileSync(probePath, JSON.stringify(probe, null, 2));
