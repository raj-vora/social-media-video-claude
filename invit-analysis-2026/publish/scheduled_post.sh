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

# Instagram-Login tokens need a public video_url (no direct upload): host the file first (not on dry runs)
URL_ARG=()
if [ -z "$DRY" ]; then
  VIDEO_URL="$(python3 "$ROOT/invit-analysis-2026/publish/host_video.py" "$VIDEO" 2>>"$LOG" | tail -n 1)"
  [ -n "$VIDEO_URL" ] || fail "could not host $(basename "$VIDEO") for Instagram (see log)"
  log "hosted at $VIDEO_URL"
  URL_ARG=(--video-url "$VIDEO_URL")
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
