const { writeProject } = require('./build_draft.js');

const { reels } = require('./reels.js');

// Fixed 60s English timelines, no voiceover (build_vo_drafts.js retimes to the VO).
const projects = Object.fromEntries(Object.values(reels).map(r => [`${r.draft}_EN`, r.beats]));

const results = [];
for (const [name, beats] of Object.entries(projects)) {
  const totalSec = beats.reduce((s, b) => s + b.durationSec, 0);
  if (totalSec !== 60) {
    console.log(`SKIPPED ${name}: beats sum to ${totalSec}s, not 60s - fix before running`);
    continue;
  }
  try {
    const r = writeProject(name, beats);
    results.push({ name, ...r, status: 'OK' });
    console.log(`OK   ${name}  (${totalSec}s, ${beats.length} segments)`);
  } catch (e) {
    results.push({ name, status: 'FAIL', error: e.message });
    console.log(`FAIL ${name}: ${e.message}`);
  }
}

require('fs').writeFileSync(require('path').join(__dirname, 'build_results.json'), JSON.stringify(results, null, 2));
