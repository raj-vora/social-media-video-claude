// Repairs drafts that CapCut won't open, or opens without rendering, because their
// draft_content.json `id` no longer matches the timeline CapCut recorded in
// Timelines/project.json. Drafts rebuilt before build_draft.js's saveContent() got
// a fresh id each time. The content is kept as is; only the id, CapCut's
// Timelines/<id>/ copy and timeline_layout.json are brought back in line.
//
// Close CapCut first. Each draft it changes is copied to
// ../live_drafts_backup_<date>_id_repair/ beforehand.
//
// Usage: node repair_draft_ids.js [--dry-run]
const fs = require('fs');
const path = require('path');
const { saveContent, DRAFT_ROOT } = require('./build_draft.js');

const BACKUP_ROOT = path.join(__dirname, '..', `live_drafts_backup_${new Date().toISOString().slice(0, 10).replace(/-/g, '')}_id_repair`);
const dryRun = process.argv.includes('--dry-run');

let fixed = 0;
for (const name of fs.readdirSync(DRAFT_ROOT).filter((n) => n.startsWith('InvIT_'))) {
  const projDir = path.join(DRAFT_ROOT, name);
  const project = path.join(projDir, 'Timelines', 'project.json');
  const file = path.join(projDir, 'draft_content.json');
  if (!fs.existsSync(project) || !fs.existsSync(file)) continue;
  const content = JSON.parse(fs.readFileSync(file, 'utf8'));
  const main = JSON.parse(fs.readFileSync(project, 'utf8')).main_timeline_id;
  if (content.id === main) { console.log(`OK   ${name}`); continue; }
  console.log(`${dryRun ? 'DRY ' : 'FIX '} ${name}: id ${content.id} -> ${main}`);
  if (dryRun) continue;
  const backup = path.join(BACKUP_ROOT, name);
  if (!fs.existsSync(backup)) fs.cpSync(projDir, backup, { recursive: true });
  saveContent(projDir, content);
  fixed++;
}
console.log(`\n${fixed} draft(s) repaired.`);
