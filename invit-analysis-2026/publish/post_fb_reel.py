"""Post a reel to the Facebook Page linked to the Instagram account. Standard library only.

Uses the long-lived user token in .secrets/meta.json ("token") to look up the Page and its Page token
(me/accounts; the Page token does not expire), then the Page Reels API:
  1. POST /{page}/video_reels?upload_phase=start           -> video_id
  2. POST rupload.facebook.com/video-upload/v23.0/{video_id} with the file bytes
  3. POST /{page}/video_reels?upload_phase=finish&video_state=PUBLISHED&description=...
then polls until the reel is published and prints its link on the last line.

  python post_fb_reel.py VIDEO --caption TEXT [--page-id ID] [--dry-run]
"""
import argparse, json, os, sys, time, urllib.error, urllib.parse, urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GRAPH = "https://graph.facebook.com/v23.0"


def call(method, url, params=None, data=None, headers=None):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {url.split('?')[0]} -> {e.code}: {e.read().decode(errors='replace')[:400]}")


def set_thumbnail(video_id, cover, tok):
    """Custom cover for a Page video/reel: POST /{video}/thumbnails (multipart source, is_preferred)."""
    boundary = "----fbthumb" + os.urandom(8).hex()
    img = open(cover, "rb").read()
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"is_preferred\"\r\n\r\ntrue\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"source\"; filename=\"cover.jpg\"\r\n"
            f"Content-Type: image/jpeg\r\n\r\n").encode() + img + f"\r\n--{boundary}--\r\n".encode()
    r = call("POST", f"{GRAPH}/{video_id}/thumbnails", {"access_token": tok}, data=body,
             headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    print("[facebook] cover set:", r)


def page_token(user_token, page_id=None):
    pages = call("GET", f"{GRAPH}/me/accounts", {"fields": "id,name,access_token,instagram_business_account",
                                                   "access_token": user_token}).get("data", [])
    if page_id:
        pages = [p for p in pages if p["id"] == page_id]
    if not pages:
        sys.exit("no Facebook Page visible to this token (needs pages_show_list + business_management)")
    return pages[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--caption")
    ap.add_argument("--cover", help="jpg to use as the reel's cover (set after publishing)")
    ap.add_argument("--thumbnail-only", metavar="VIDEO_ID", help="only change the cover of this existing Page video")
    ap.add_argument("--page-id")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    meta = json.load(open(os.path.join(ROOT, ".secrets", "meta.json"), encoding="utf-8"))
    page = page_token(meta["token"], a.page_id or meta.get("fb_page_id"))
    tok, pid = page["access_token"], page["id"]
    if a.thumbnail_only:
        set_thumbnail(a.thumbnail_only, a.cover, tok)
        return
    size = os.path.getsize(a.video)
    if a.dry_run:
        print(f"[facebook] dry run: page '{page['name']}' ({pid}) reachable, would upload {os.path.basename(a.video)} ({size} bytes)"
              + (f" with cover {os.path.basename(a.cover)}" if a.cover else ""))
        return
    vid = call("POST", f"{GRAPH}/{pid}/video_reels", {"upload_phase": "start", "access_token": tok})["video_id"]
    with open(a.video, "rb") as f:
        up = call("POST", f"https://rupload.facebook.com/video-upload/v23.0/{vid}", data=f.read(),
                  headers={"Authorization": f"OAuth {tok}", "offset": "0", "file_size": str(size)})
    if not up.get("success"):
        sys.exit(f"upload failed: {up}")
    fin = call("POST", f"{GRAPH}/{pid}/video_reels", {"upload_phase": "finish", "video_id": vid, "video_state": "PUBLISHED",
                                                      "description": a.caption, "access_token": tok})
    if not fin.get("success"):
        sys.exit(f"finish failed: {fin}")
    wait = 15
    for _ in range(60):  # processing usually takes 1-3 minutes
        time.sleep(wait)
        try:  # a status check that is rate-limited (429) or fails must not fail a reel that is already uploaded
            with urllib.request.urlopen(f"{GRAPH}/{vid}?" + urllib.parse.urlencode(
                    {"fields": "status,permalink_url", "access_token": tok}), timeout=60) as r:
                st = json.load(r)
            wait = 15
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            print(f"[facebook] status check failed ({getattr(e, 'code', e)}), retrying", flush=True)
            wait = min(wait * 2, 120)
            continue
        s = st.get("status", {})
        if s.get("video_status") == "error" or s.get("processing_phase", {}).get("status") == "error":
            sys.exit(f"processing failed: {s}")
        if s.get("publishing_phase", {}).get("status") == "complete" or s.get("video_status") == "ready":
            if a.cover:
                try:
                    set_thumbnail(vid, a.cover, tok)
                except SystemExit as e:  # the reel is already live: a cover failure must not fail the post
                    print("[facebook] cover not set:", e)
            link = st.get("permalink_url", f"/reel/{vid}")
            print("[facebook] published reel:", link if link.startswith("http") else "https://www.facebook.com" + link)
            return
    print(f"[facebook] submitted, still processing after 10 min: https://www.facebook.com/reel/{vid}")


if __name__ == "__main__":
    main()
