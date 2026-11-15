// Builds CapCut draft projects (draft_content.json + draft_meta_info.json) on disk from
// the media under invit-analysis-2026/assets/ and the beat lists in reels.js.
//
// The pure parts - timing, segments and text overlays - are in draft_model.js, which has
// unit tests (tests/js). This file adds what touches the disk and the environment: the
// probe data, the text styles, CapCut's folder layout and the file writers.
//
// It does NOT touch CapCut's root_meta_info.json registry. register_projects.js does
// that as a separate, explicit step, because CapCut owns that file and reads it at startup.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const M = require('./draft_model');
// CapCut stores a device fingerprint in each draft. It is generated per machine (or taken
// from env), never written into the repo.
const PLATFORM = {
  os: 'windows', os_version: '10.0', app_id: 359289, app_version: '9.5.0', app_source: 'cc',
  device_id: process.env.CAPCUT_DEVICE_ID || crypto.randomBytes(16).toString('hex'),
  hard_disk_id: process.env.CAPCUT_DISK_ID || crypto.randomBytes(16).toString('hex'),
  mac_address: process.env.CAPCUT_MAC_ID || crypto.randomBytes(16).toString('hex'),
};

// Assets live beside this generator folder. CapCut's draft folder comes from the environment.
const ASSETS_ROOT = path.resolve(__dirname, '../..');
const DRAFT_ROOT = process.env.CAPCUT_DRAFTS_DIR || (() => { throw new Error('Set CAPCUT_DRAFTS_DIR to CapCut\'s Projects/com.lveditor.draft folder'); })();
const PROBE = JSON.parse(fs.readFileSync(path.join(__dirname, 'asset_probe.json'), 'utf8'));

const guid = M.guid;
const winPath = (relPath) => M.winPath(relPath, ASSETS_ROOT);
const isImage = M.isImage;


// ---- Material builders ----
function buildVideoMaterial(relPath) {
  const info = PROBE.videos[relPath];
  if (!info) throw new Error(`No probe data for video ${relPath}`);
  return {
    id: guid(),
    type: 'video',
    material_name: path.basename(relPath),
    path: winPath(relPath),
    duration: info.durationUs,
    width: info.width,
    height: info.height,
    has_audio: true,
    crop: { upper_left_x: 0, upper_left_y: 0, upper_right_x: 1, upper_right_y: 0, lower_left_x: 0, lower_left_y: 1, lower_right_x: 1, lower_right_y: 1 },
    crop_ratio: 'free',
    crop_scale: 1.0,
    check_flag: 63,
    category_id: '',
    category_name: 'local',
    source_platform: 0,
    local_material_id: '',
  };
}

function buildImageMaterial(relPath, displayDurationUs) {
  const info = PROBE.images[relPath];
  if (!info) throw new Error(`No probe data for image ${relPath}`);
  return {
    id: guid(),
    type: 'photo',
    material_name: path.basename(relPath),
    path: winPath(relPath),
    duration: Math.max(displayDurationUs * 4, 10800000000), // images are "infinite" source; segment's own timerange controls what's shown
    width: info.width,
    height: info.height,
    has_audio: false,
    crop: { upper_left_x: 0, upper_left_y: 0, upper_right_x: 1, upper_right_y: 0, lower_left_x: 0, lower_left_y: 1, lower_right_x: 1, lower_right_y: 1 },
    crop_ratio: 'free',
    crop_scale: 1.0,
    check_flag: 63,
    category_id: '',
    category_name: 'local',
    source_platform: 0,
    local_material_id: '',
  };
}

// Imported local audio (the voiceover clips). Field set follows the text_to_audio
// materials CapCut wrote into the hand-edited Indus draft, minus the TTS fields.
function buildAudioMaterial(relPath, durationUs) {
  return {
    id: guid(),
    type: 'extract_music',
    name: path.basename(relPath),
    path: winPath(relPath),
    duration: durationUs,
    category_name: 'local',
    category_id: '',
    check_flag: 1,
    source_platform: 0,
    local_material_id: '',
    music_id: '',
    resource_id: '',
    text_id: '',
    wave_points: [],
    app_id: 0,
    team_id: '',
    copyright_limit_type: 'none',
  };
}

const buildAudioSegment = M.buildAudioSegment;

// ---- Text overlays and timing ----
// Styles cloned from the two text layers the user made in the Indus EN draft (see
// text_styles.json): 'title' sits near the top for the whole beat; 'stat' is the big
// centred number, fading in a third of the way into the beat (at most 3s in).
const TEXT_STYLES = JSON.parse(fs.readFileSync(path.join(__dirname, 'text_styles.json'), 'utf8'));
const OVERLAY_NAME = M.OVERLAY_NAME; // marks text the builder made, vs. text added in CapCut
const buildSegment = M.buildSegment;
const beatParts = (beat, durationUs) => M.beatParts(beat, durationUs, PROBE.videos);
const beatOverlays = (beat, startUs, durationUs) => M.beatOverlays(TEXT_STYLES, beat, startUs, durationUs);
const textTracks = (overlays) => M.textTracks(TEXT_STYLES, overlays);

// ---- Project builder ----
// `beats` = [{ file: "videos/toll_roads_highways/xxx.mp4", durationSec: 6, hold?: "still.png",
//              text?: [["title", "#2 InvIT of 2026"], ["stat", "+22.7%"]] }, ...]
// `canvas` = the frame size, 9:16 unless a 16:9 video (the long form) says otherwise.
// `voiceover` = [{ file: "voiceover/english/.../01_0m00-0m06.mp3", startSec, durationSec }, ...]
function buildProject(beats, voiceover = [], canvas = { width: 1080, height: 1920 }) {
  const videos = [];
  const images = [];
  const audios = [];
  const speeds = [];
  const track = { id: guid(), type: 'video', attribute: 0, flag: 0, segments: [] };
  const materialIds = new Map(); // one material per file, shared by looped segments
  const overlays = [];

  let cursorUs = 0;
  for (const beat of beats) {
    const beatUs = Math.round(beat.durationSec * 1000000);
    overlays.push(...beatOverlays(beat, cursorUs, beatUs));
    for (const part of beatParts(beat, beatUs)) {
      if (!materialIds.has(part.file)) {
        const mat = isImage(part.file) ? buildImageMaterial(part.file, part.durationUs) : buildVideoMaterial(part.file);
        // Stills go in materials.videos too (type "photo"), as CapCut stores them; in
        // materials.images CapCut moves them to sticker tracks and closes the gap.
        videos.push(mat);
        materialIds.set(part.file, mat.id);
      }
      track.segments.push(buildSegment(materialIds.get(part.file), cursorUs, part.durationUs, 0));
      cursorUs += part.durationUs;
    }
  }

  const tracks = [track, ...textTracks(overlays)];
  overlays.forEach((o, i) => { o.segment.render_index = 14000 + i; });
  let audioEndUs = 0;
  if (voiceover.length) {
    const audioTrack = { id: guid(), type: 'audio', attribute: 0, flag: 0, name: '', is_default_name: true, segments: [] };
    for (const vo of voiceover) {
      const startUs = Math.round(vo.startSec * 1000000);
      const durationUs = Math.round(vo.durationSec * 1000000);
      const mat = buildAudioMaterial(vo.file, durationUs);
      const speed = { id: guid(), type: 'speed', mode: 0, speed: 1.0, curve_speed: null };
      audios.push(mat);
      speeds.push(speed);
      audioTrack.segments.push(buildAudioSegment(mat.id, speed.id, startUs, durationUs));
      audioEndUs = Math.max(audioEndUs, startUs + durationUs);
    }
    tracks.push(audioTrack);
  }

  const totalDurationUs = Math.max(cursorUs, audioEndUs);
  tracks.forEach((t, i) => t.segments.forEach((s) => { s.track_render_index = i; }));

  const content = {
    id: guid(),
    version: 360000,
    new_version: '187.0.0',
    name: '',
    duration: totalDurationUs,
    create_time: 0,
    update_time: 0,
    fps: 30.0,
    is_drop_frame_timecode: false,
    color_space: -1,
    config: {
      video_mute: false, record_audio_last_index: 1, extract_audio_last_index: 1, original_sound_last_index: 1,
      subtitle_recognition_id: '', subtitle_taskinfo: [], lyrics_recognition_id: '', lyrics_taskinfo: [],
      subtitle_sync: true, lyrics_sync: true, voice_change_sync: false, sticker_max_index: 1, adjust_max_index: 1,
      material_save_mode: 0, export_range: null, maintrack_adsorb: true, combination_max_index: 1,
      attachment_info: [], zoom_info_params: null, system_font_list: [], multi_language_mode: 'none',
      multi_language_main: 'none', multi_language_current: 'none', multi_language_list: [],
      subtitle_keywords_config: null, use_float_render: false, hdr_vivid: false,
    },
    canvas_config: { ratio: 'original', width: canvas.width, height: canvas.height, background: null },
    tracks,
    group_container: null,
    materials: {
      flowers: [], videos, tail_leaders: [], audios, images, texts: overlays.map((o) => o.material), effects: [], stickers: [],
      canvases: [], transitions: [], audio_effects: [], audio_fades: [], beats: [],
      material_animations: overlays.map((o) => o.animation),
      placeholders: [], placeholder_infos: [], speeds, common_mask: [], chromas: [], text_templates: [],
      realtime_denoises: [], audio_pannings: [], audio_pitch_shifts: [], video_trackings: [], hsl: [],
      drafts: [], color_curves: [], hsl_curves: [], primary_color_wheels: [], log_color_wheels: [],
      video_effects: [], ai_text_effects: [], audio_balances: [], handwrites: [], manual_deformations: [],
      manual_beautys: [], plugin_effects: [], sound_channel_mappings: [], green_screens: [], shapes: [],
      material_colors: [], digital_humans: [], digital_human_model_dressing: [], smart_crops: [],
      ai_translates: [], audio_track_indexes: [], loudnesses: [], vocal_beautifys: [], vocal_separations: [],
      smart_relights: [], time_marks: [], multi_language_refs: [], video_shadows: [], video_strokes: [], video_radius: [],
    },
    keyframes: { videos: [], audios: [], texts: [], stickers: [], filters: [], adjusts: [], handwrites: [], effects: [] },
    keyframe_graph_list: [],
    platform: PLATFORM,
    last_modified_platform: PLATFORM,
    mutable_config: null, cover: null, retouch_cover: null, extra_info: null, relationships: [],
    mixed_track_mode_on: false, render_index_track_mode_on: true, free_render_index_mode_on: false,
    static_cover_image_path: '', source: 'default', time_marks: null, path: '',
    lyrics_effects: [], uneven_animation_template_info: { composition: '', content: '', order: '', sub_template_info_list: [] },
    draft_type: 'video', smart_ads_info: { page_from: '', routine: '', draft_url: '' },
    function_assistant_info: {
      smart_rec_applied: false, fixed_rec_applied: false, auto_adjust: false, auto_adjust_segid_list: [],
      color_correction: false, color_correction_segid_list: [], enhance_quality: false, smooth_slow_motion: false,
      deflicker_segid_list: [], video_noise_segid_list: [], enhance_quality_segid_list: [], smart_segid_list: [],
      retouch: false, retouch_segid_list: [], enhande_voice: false, enhance_voice_segid_list: [],
      audio_noise_segid_list: [], auto_caption: false, auto_caption_segid_list: [], auto_caption_template_id: '',
      caption_opt: false, caption_opt_segid_list: [], eye_correction: false, eye_correction_segid_list: [],
      normalize_loudness: false, normalize_loudness_segid_list: [], normalize_loudness_audio_denoise_segid_list: [],
      auto_adjust_fixed: false, auto_adjust_fixed_value: 50.0, color_correction_fixed: false, color_correction_fixed_value: 50.0,
      normalize_loudness_fixed: false, enhande_voice_fixed: false, retouch_fixed: false, enhance_quality_fixed: false,
      smooth_slow_motion_fixed: false, fps: { num: 0, den: 1 },
    },
  };

  return { content, totalDurationUs };
}

// Once CapCut has opened a draft it tracks the timeline by id: Timelines/project.json
// names the main timeline, Timelines/<id>/ holds a copy of draft_content.json, and
// timeline_layout.json lists the open timelines. A draft_content.json whose `id` no
// longer matches won't open, or opens without rendering. So keep CapCut's id, write
// its copy too, and point the layout back at that one timeline.
function saveContent(projDir, content) {
  const project = path.join(projDir, 'Timelines', 'project.json');
  if (fs.existsSync(project)) {
    content.id = JSON.parse(fs.readFileSync(project, 'utf8')).main_timeline_id;
    const copyDir = path.join(projDir, 'Timelines', content.id);
    fs.mkdirSync(copyDir, { recursive: true });
    fs.writeFileSync(path.join(copyDir, 'draft_content.json'), JSON.stringify(content));
    fs.writeFileSync(path.join(projDir, 'timeline_layout.json'), JSON.stringify({
      dockItems: [{ dockIndex: 0, ratio: 1, timelineIds: [content.id], timelineNames: ['Timeline 01'] }],
      layoutOrientation: 1,
    }));
  }
  fs.writeFileSync(path.join(projDir, 'draft_content.json'), JSON.stringify(content));
}

function writeProject(draftName, beats, voiceover = []) {
  const { content, totalDurationUs } = buildProject(beats, voiceover);
  const projDir = path.join(DRAFT_ROOT, draftName);
  fs.mkdirSync(projDir, { recursive: true });
  saveContent(projDir, content);
  const metaFile = path.join(projDir, 'draft_meta_info.json');
  const oldMeta = fs.existsSync(metaFile) ? JSON.parse(fs.readFileSync(metaFile, 'utf8')) : {};

  const nowUs = Date.now() * 1000;
  const metaInfo = {
    cloud_package_completed_time: '', draft_cloud_capcut_purchase_info: '', draft_cloud_last_action_download: false,
    draft_cloud_materials: [], draft_cloud_purchase_info: '', draft_cloud_template_id: '', draft_cloud_tutorial_info: '',
    draft_cloud_videocut_purchase_info: '', draft_cover: '', draft_deeplink_url: '', draft_enterprise_info: { draft_enterprise_extra: '', draft_enterprise_id: '', draft_enterprise_name: '', enterprise_material: [] },
    draft_fold_path: projDir, draft_id: oldMeta.draft_id || guid(), draft_is_ai_packaging_used: false, draft_is_ai_shorts: false,
    draft_is_ai_translate: false, draft_is_article_video_draft: false, draft_is_from_deeplink: 'false',
    draft_is_invisible: false, draft_materials: [], draft_materials_copied_info: [], draft_name: draftName,
    draft_new_version: '', draft_removable_storage_device: '', draft_root_path: DRAFT_ROOT,
    draft_segment_extra_info: [], draft_timeline_materials_size_: 0, draft_type: '',
    tm_draft_cloud_completed: '', tm_draft_cloud_modified: 0, tm_draft_create: oldMeta.tm_draft_create || nowUs, tm_draft_modified: nowUs,
    tm_draft_removed: 0, tm_duration: totalDurationUs,
  };
  fs.writeFileSync(path.join(projDir, 'draft_meta_info.json'), JSON.stringify(metaInfo));

  return { projDir, totalDurationUs, draftId: metaInfo.draft_id };
}

module.exports = {
  writeProject, saveContent, buildProject, buildSegment, buildAudioMaterial, buildAudioSegment, guid,
  ASSETS_ROOT, DRAFT_ROOT, OVERLAY_NAME,
};
