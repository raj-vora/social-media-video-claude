#!/usr/bin/env bash
# Post one reel from previews_shorts/ to Instagram, for cron.
#
#   scheduled_post.sh REEL_KEY [--dry-run]      e.g. scheduled_post.sh 02_powergrid
#
# The video and caption come from previews_shorts/captions.json (REEL_KEY.video,
# REEL_KEY.instagram.caption). Writes previews_shorts/logs/REEL_KEY.log, and on a real run
#   REEL_KEY.status   one line: "OK <permalink>" or "ERROR <reason>" (watch this)
#   REEL_KEY.posted   marker; a reel with a marker is never posted again
# then removes its own crontab line (tagged "# post:REEL_KEY") so the entry fires once.
set -uo pipefail
export LC_ALL=C.UTF-8 PYTHONIOENCODING=utf-8 PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SHORTS="$ROOT/previews_shorts"
LOGS="$SHORTS/logs"
KEY="${1:?usage: scheduled_post.sh REEL_KEY [--dry-run]}"
DRY="${2:-}"
mkdir -p "$LOGS"
LOG="$LOGS/$KEY.log"
STATUS="$LOGS/$KEY.status"
MARKER="$LOGS/$KEY.posted"

log() { echo "[$(TZ=Asia/Kolkata date '+%F %T IST')] $*" | tee -a "$LOG"; }
unschedule() { crontab -l 2>/dev/null | grep -vF "# post:$KEY" | crontab -; }
fail() { log "ERROR $*"; [ -z "$DRY" ] && { echo "ERROR $*" > "$STATUS"; unschedule; }; exit 1; }

if [ -e "$MARKER" ]; then
  log "already posted ($(cat "$MARKER")), skipping"
  unschedule
  exit 0
fi

# video path in captions.json is relative to the old previews/ folder; the file lives here
read_field() {
  python3 -c 'import json,sys; d=json.load(open(sys.argv[1],encoding="utf-8"))[sys.argv[2]]
for k in sys.argv[3:]: d=d[k]
print(d)' "$SHORTS/captions.json" "$KEY" "$@"
}
VIDEO="$(read_field video 2>>"$LOG")" || fail "no entry '$KEY' in captions.json"
VIDEO="$SHORTS/$(basename "$VIDEO")"
CAPTION="$(read_field instagram caption 2>>"$LOG")" || fail "no instagram caption for '$KEY'"
[ -f "$VIDEO" ] || fail "video not found: $VIDEO"

# Reel cover (previews_shorts/covers/KEY.jpg, made by exdiv-nov-2026/tools/make_covers.py if missing) so each reel
# has its own thumbnail in the profile grids. A missing cover never blocks a post.
COVER="$SHORTS/covers/$KEY.jpg"
if [ ! -f "$COVER" ]; then
  "$ROOT/.venv-tts/bin/python" "$ROOT/exdiv-nov-2026/tools/make_covers.py" "$KEY" >> "$LOG" 2>&1 || log "cover: could not make one, posting without"
fi
COVER_ARGS=(); YT_COVER_ARGS=()
[ -f "$COVER" ] && COVER_ARGS=(--cover "$COVER") && YT_COVER_ARGS=(--yt-thumbnail "$COVER")

# Facebook Page reel first, independent of Instagram: its own status/marker, and a failure never stops the
# Instagram post. Caption: REEL_KEY.facebook.caption (clickable YouTube link) if set, else the Instagram one.
FB_STATUS="$LOGS/$KEY.fb_status"
FB_MARKER="$LOGS/$KEY.fb_posted"
if [ -e "$FB_MARKER" ]; then
  log "facebook: already posted ($(cat "$FB_MARKER")), skipping"
else
  FB_CAPTION="$(read_field facebook caption 2>/dev/null)" || FB_CAPTION="$CAPTION"
  FB_OUT="$(python3 "$ROOT/invit-analysis-2026/publish/post_fb_reel.py" "$VIDEO" --caption "$FB_CAPTION" "${COVER_ARGS[@]}" $DRY 2>&1)"
  FB_RC=$?
  echo "$FB_OUT" >> "$LOG"
  if [ $FB_RC -ne 0 ]; then
    log "facebook: ERROR $(echo "$FB_OUT" | tail -n 1)"
    [ -z "$DRY" ] && echo "ERROR $(echo "$FB_OUT" | tail -n 1)" > "$FB_STATUS"
  elif [ -z "$DRY" ]; then
    FB_LINK="$(echo "$FB_OUT" | grep -o 'https://[^ ]*' | tail -n 1)"
    echo "$(TZ=Asia/Kolkata date '+%F %T IST') ${FB_LINK:-published}" > "$FB_MARKER"
    echo "OK ${FB_LINK:-published}" > "$FB_STATUS"
    log "facebook: OK ${FB_LINK:-published}"
  else
    log "facebook: $(echo "$FB_OUT" | tail -n 1)"
  fi
fi

# YouTube Short, also independent: REEL_KEY.youtube.title/.description, language from the key (_hi_/_en_/_mr_/_gu_,
# default Hindi), tags from the description's hashtags. Public at posting time.
YT_STATUS="$LOGS/$KEY.yt_status"
YT_MARKER="$LOGS/$KEY.yt_posted"
if [ -e "$YT_MARKER" ]; then
  log "youtube: already posted ($(cat "$YT_MARKER")), skipping"
elif YT_TITLE="$(read_field youtube title 2>/dev/null)" && YT_DESC="$(read_field youtube description 2>/dev/null)"; then
  YT_LANG="$(echo "$KEY" | grep -oE '_(hi|en|mr|gu)_[A-E]$' | cut -d_ -f2)"
  YT_OUT="$(python3 "$ROOT/invit-analysis-2026/publish/post_reel.py" "$VIDEO" --only youtube --yt-privacy public \
            --yt-lang "${YT_LANG:-hi}" --title "$YT_TITLE" --caption "$YT_DESC" "${YT_COVER_ARGS[@]}" $DRY 2>&1)"
  YT_RC=$?
  echo "$YT_OUT" >> "$LOG"
  if [ $YT_RC -ne 0 ]; then
    log "youtube: ERROR $(echo "$YT_OUT" | tail -n 1)"
    [ -z "$DRY" ] && echo "ERROR $(echo "$YT_OUT" | tail -n 1)" > "$YT_STATUS"
  elif [ -z "$DRY" ]; then
    YT_LINK="$(echo "$YT_OUT" | grep -o 'https://[^ ]*' | tail -n 1)"
    echo "$(TZ=Asia/Kolkata date '+%F %T IST') ${YT_LINK:-published}" > "$YT_MARKER"
    echo "OK ${YT_LINK:-published}" > "$YT_STATUS"
    log "youtube: OK ${YT_LINK:-published}"
  else
    log "youtube: $(echo "$YT_OUT" | tail -n 1)"
  fi
else
  log "youtube: no youtube title/description in captions.json, skipped"
fi

# Instagram-Login tokens need a public video_url (no direct upload): host the file first (not on dry runs)
URL_ARG=()
if [ -z "$DRY" ]; then
  VIDEO_URL="$(python3 "$ROOT/invit-analysis-2026/publish/host_video.py" "$VIDEO" 2>>"$LOG" | tail -n 1)"
  [ -n "$VIDEO_URL" ] || fail "could not host $(basename "$VIDEO") for Instagram (see log)"
  log "hosted at $VIDEO_URL"
  URL_ARG=(--video-url "$VIDEO_URL")
  if [ -f "$COVER" ]; then
    COVER_URL="$(python3 "$ROOT/invit-analysis-2026/publish/host_video.py" "$COVER" 2>>"$LOG" | tail -n 1)"
    if [ -n "$COVER_URL" ]; then URL_ARG+=(--cover-url "$COVER_URL"); log "cover at $COVER_URL"; else log "cover: hosting failed, posting without"; fi
  fi
fi

log "posting $KEY: $(basename "$VIDEO") ${DRY:+(dry run)}"
OUT="$(python3 "$ROOT/invit-analysis-2026/publish/post_reel.py" "$VIDEO" \
        --only instagram --caption "$CAPTION" "${URL_ARG[@]}" $DRY 2>&1)"
RC=$?
echo "$OUT" >> "$LOG"
[ $RC -eq 0 ] || fail "post_reel.py exited $RC: $(echo "$OUT" | tail -n 1)"

if [ -n "$DRY" ]; then
  log "dry run ok"
  exit 0
fi
LINK="$(echo "$OUT" | grep -o 'https://[^ ]*' | tail -n 1)"
echo "$(TZ=Asia/Kolkata date '+%F %T IST') ${LINK:-published}" > "$MARKER"
echo "OK ${LINK:-published}" > "$STATUS"
log "OK ${LINK:-published}"
unschedule
