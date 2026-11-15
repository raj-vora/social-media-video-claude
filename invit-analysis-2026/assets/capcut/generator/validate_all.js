const fs = require('fs');
const path = require('path');
const DRAFT_ROOT = process.env.CAPCUT_DRAFTS_DIR || (() => { throw new Error('Set CAPCUT_DRAFTS_DIR to CapCut\'s Projects/com.lveditor.draft folder'); })();
const results = JSON.parse(fs.readFileSync(path.join(__dirname, 'build_results.json'), 'utf8'));

let allGood = true;
for (const r of results) {
  if (r.status !== 'OK') { console.log(`SKIP ${r.name} (build failed)`); continue; }
  const contentPath = path.join(r.projDir, 'draft_content.json');
  const content = JSON.parse(fs.readFileSync(contentPath, 'utf8'));
  const segs = content.tracks[0].segments;
  let cursor = 0;
  let ok = true;
  for (const seg of segs) {
    if (seg.target_timerange.start !== cursor) { ok = false; console.log(`  GAP/OVERLAP in ${r.name} at segment (expected start ${cursor}, got ${seg.target_timerange.start})`); }
    cursor += seg.target_timerange.duration;
  }
  if (cursor !== content.duration) { ok = false; console.log(`  DURATION MISMATCH in ${r.name}: segments sum ${cursor}, declared duration ${content.duration}`); }
  const allMaterials = [...content.materials.videos, ...content.materials.images];
  for (const m of allMaterials) {
    if (!fs.existsSync(m.path)) { ok = false; console.log(`  MISSING FILE in ${r.name}: ${m.path}`); }
  }
  if (allMaterials.length !== segs.length) { ok = false; console.log(`  MATERIAL/SEGMENT COUNT MISMATCH in ${r.name}: ${allMaterials.length} materials vs ${segs.length} segments`); }
  console.log(`${ok ? 'PASS' : 'FAIL'} ${r.name}  duration=${content.duration/1000000}s  segments=${segs.length}  materials=${allMaterials.length}`);
  if (!ok) allGood = false;
}
console.log(allGood ? '\nAll projects validated successfully.' : '\nSOME PROJECTS HAVE ISSUES - see above.');
