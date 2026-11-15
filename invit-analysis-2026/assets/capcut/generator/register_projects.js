// Registers our generated draft projects in CapCut's project registry
// (root_meta_info.json) so they show up in CapCut's "Drafts" list. Only ever ADDS
// entries to all_draft_store - never touches or removes the existing entry (the
// user's own "0922" project).
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const DRAFT_ROOT = process.env.CAPCUT_DRAFTS_DIR || (() => { throw new Error('Set CAPCUT_DRAFTS_DIR to CapCut\'s Projects/com.lveditor.draft folder'); })();
const REGISTRY_PATH = path.join(DRAFT_ROOT, 'root_meta_info.json');

// Optional argument: another results file, e.g. vo_build_results.json.
const resultsFile = path.resolve(__dirname, process.argv[2] || 'build_results.json');
const results = JSON.parse(fs.readFileSync(resultsFile, 'utf8'));

const registry = JSON.parse(fs.readFileSync(REGISTRY_PATH, 'utf8'));
const existingNames = new Set(registry.all_draft_store.map(e => e.draft_name));

let added = 0;
for (const r of results) {
  if (r.status !== 'OK') continue;
  if (existingNames.has(r.name)) {
    console.log(`SKIP ${r.name}: already registered`);
    continue;
  }
  const nowUs = Date.now() * 1000;
  const draftId = crypto.randomUUID().toUpperCase();
  const coverPath = path.join(r.projDir, 'draft_cover.jpg'); // may not exist - that's fine, CapCut regenerates on open

  registry.all_draft_store.push({
    cloud_draft_cover: false, cloud_draft_sync: false, draft_cloud_last_action_download: false,
    draft_cloud_purchase_info: '', draft_cloud_template_id: '', draft_cloud_tutorial_info: '',
    draft_cloud_videocut_purchase_info: '',
    draft_cover: coverPath,
    draft_fold_path: r.projDir,
    draft_id: draftId,
    draft_is_ai_shorts: false, draft_is_cloud_temp_draft: false, draft_is_infinite_canvas_draft: false,
    draft_is_invisible: false, draft_is_pippit_draft: false, draft_is_web_article_video: false,
    draft_json_file: path.join(r.projDir, 'draft_content.json'),
    draft_name: r.name,
    draft_new_version: '',
    draft_root_path: DRAFT_ROOT,
    draft_timeline_materials_size: 0,
    draft_type: '', draft_web_article_video_enter_from: '',
    pippit_avatar_url: '', pippit_extra_info: '', pippit_id: '', pippit_user_name: '',
    streaming_edit_draft_ready: true,
    tm_draft_cloud_completed: '', tm_draft_cloud_entry_id: -1, tm_draft_cloud_modified: 0,
    tm_draft_cloud_parent_entry_id: -1, tm_draft_cloud_space_id: -1, tm_draft_cloud_user_id: -1,
    tm_draft_create: nowUs, tm_draft_modified: nowUs, tm_draft_removed: 0,
    tm_duration: r.totalDurationUs,
  });
  added++;
  console.log(`ADDED ${r.name}`);
}

registry.draft_ids = (registry.draft_ids || 0) + added;

fs.writeFileSync(REGISTRY_PATH, JSON.stringify(registry));
console.log(`\nDone. Added ${added} new project(s) to the registry. Total entries: ${registry.all_draft_store.length}`);
