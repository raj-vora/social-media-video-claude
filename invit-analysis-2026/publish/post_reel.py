"""Post a reel to Instagram (as a trial reel) and YouTube Shorts. Standard library only.

Credentials are read from .secrets/ at run time:
  meta.json                 access token + Instagram business account id
  youtube_client_secret.json  OAuth "installed app" client from Google Cloud
  youtube_token.json        written on first YouTube run (browser consent)

  python invit-analysis-2026/publish/post_reel.py VIDEO [--only instagram|youtube]
         [--caption TEXT] [--title TEXT] [--yt-privacy public|unlisted|private] [--dry-run]
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import argparse, json, os, re, secrets, sys, time, urllib.parse, urllib.request, webbrowser

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SECRETS = os.path.join(ROOT, ".secrets")
GRAPH = "https://graph.facebook.com/v23.0"

DEFAULT_TITLE = "Indus Infra Trust InvIT 2026 | Returns explained in Hindi #Shorts"
DEFAULT_CAPTION = (
    "Indus Infra Trust: India's top InvITs of 2026, explained in Hindi.\n"
    "Returns = price change + distributions (data: Yahoo Finance).\n\n"
    "Educational only, not investment advice. Do your own research.\n\n"
    "#InvIT #IndusInfraTrust #Investing #StockMarketIndia #Shorts"
)


def first(d, *names):
    for n in names:
        if d.get(n):
            return d[n]
    sys.exit(f"meta.json is missing one of: {', '.join(names)}")


def http(method, url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            body = r.read()
            return r.headers, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {url.split('?')[0]} -> {e.code}: {e.read().decode(errors='replace')}")


def form(d):
    return urllib.parse.urlencode(d).encode()


# ---------- Instagram: resumable upload of a local file, trial reel ----------
def post_instagram(video, caption, trial, dry, video_url=None, cover_url=None):
    meta = json.load(open(os.path.join(SECRETS, "meta.json"), encoding="utf-8"))
    token = first(meta, "access_token", "page_access_token", "ig_access_token", "token")
    ig = first(meta, "ig_user_id", "instagram_business_account_id", "instagram_account_id", "ig_id")
    # Instagram Login tokens (IGAA...) only work on graph.instagram.com
    global GRAPH
    if token.startswith("IG"):
        GRAPH = "https://graph.instagram.com/v23.0"
    if dry:
        print("[instagram] dry run: credentials found, would upload", video)
        return
    params = {"media_type": "REELS", "upload_type": "resumable", "caption": caption,
              "share_to_feed": "true", "access_token": token}
    if trial:  # needs a minimum follower count
        params["share_to_feed"] = "false"
        params["trial_params"] = json.dumps({"graduation_strategy": "MANUAL"})
    if cover_url:  # custom cover for the profile grid (Instagram fetches the image)
        params["cover_url"] = cover_url
    if video_url:  # Instagram fetches the file itself
        del params["upload_type"]
        params["video_url"] = video_url
    _, c = http("POST", f"{GRAPH}/{ig}/media", form(params))
    if not video_url:
        size = os.path.getsize(video)
        with open(video, "rb") as f:
            http("POST", c["uri"], f.read(), {
                "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)})
    for _ in range(60):
        _, s = http("GET", f"{GRAPH}/{c['id']}?fields=status_code,status&access_token={token}")
        print("[instagram] processing:", s.get("status_code"))
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") == "ERROR":
            sys.exit(f"[instagram] processing failed: {s}")
        time.sleep(10)
    else:
        sys.exit("[instagram] timed out waiting for processing")
    _, p = http("POST", f"{GRAPH}/{ig}/media_publish", form({"creation_id": c["id"], "access_token": token}))
    _, m = http("GET", f"{GRAPH}/{p['id']}?fields=permalink&access_token={token}")
    print("[instagram] published", "trial reel:" if trial else "reel:", m.get("permalink", p["id"]))


# ---------- YouTube: installed-app OAuth + resumable upload ----------
def yt_token():
    path = os.path.join(SECRETS, "youtube_token.json")
    cs = json.load(open(os.path.join(SECRETS, "youtube_client_secret.json"), encoding="utf-8"))
    cs = cs.get("installed") or cs.get("web")
    tok = json.load(open(path)) if os.path.exists(path) else {}
    if tok.get("refresh_token"):
        _, r = http("POST", cs["token_uri"], form({
            "client_id": cs["client_id"], "client_secret": cs["client_secret"],
            "refresh_token": tok["refresh_token"], "grant_type": "refresh_token"}))
        return r["access_token"]
    # first run: consent in the browser, code comes back to a loopback server
    got = {}
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            got.update(urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query))
            self.send_response(200); self.end_headers()
            self.wfile.write(b"Authorized. You can close this tab.")
        def log_message(self, *a): pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    redirect = f"http://127.0.0.1:{srv.server_port}"
    state = secrets.token_urlsafe(16)
    url = cs["auth_uri"] + "?" + urllib.parse.urlencode({
        "client_id": cs["client_id"], "redirect_uri": redirect, "response_type": "code",
        "scope": "https://www.googleapis.com/auth/youtube.upload",
        "access_type": "offline", "prompt": "consent", "state": state})
    print("[youtube] opening browser for consent:\n", url)
    webbrowser.open(url)
    while "code" not in got and "error" not in got:
        srv.handle_request()
    if got.get("state", [""])[0] != state or "code" not in got:
        sys.exit(f"[youtube] authorization failed: {got.get('error')}")
    _, r = http("POST", cs["token_uri"], form({
        "client_id": cs["client_id"], "client_secret": cs["client_secret"], "code": got["code"][0],
        "redirect_uri": redirect, "grant_type": "authorization_code"}))
    json.dump({"refresh_token": r["refresh_token"]}, open(path, "w"))
    return r["access_token"]


def yt_set_thumbnail(video_id, image, token=None):
    """thumbnails.set (50 quota units). Shorts mostly show a video frame in the feed; this shows on the channel/search."""
    _, r = http("POST", f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={video_id}",
                open(image, "rb").read(), {"Authorization": f"Bearer {token or yt_token()}", "Content-Type": "image/jpeg"})
    print("[youtube] thumbnail set:", (r.get("items") or [{}])[0].get("default", {}).get("url", r))


def post_youtube(video, title, caption, privacy, dry, lang="hi", tags=None, publish_at=None, thumbnail=None):
    if dry:
        json.load(open(os.path.join(SECRETS, "youtube_client_secret.json"), encoding="utf-8"))
        print("[youtube] dry run: client secret found, would upload", video, "as", privacy)
        return
    token = yt_token()
    meta = {"snippet": {"title": title[:100], "description": caption, "categoryId": "27",
                        "defaultLanguage": lang, "defaultAudioLanguage": lang,
                        "tags": tags or ["Investing", "Shorts"]},
            "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}}
    if publish_at:  # YouTube publishes it itself at this time (RFC 3339); it must be private until then
        meta["status"].update(privacyStatus="private", publishAt=publish_at)
    size = os.path.getsize(video)
    h, _ = http("POST",
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        json.dumps(meta).encode(), {
            "Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)})
    with open(video, "rb") as f:
        _, v = http("PUT", h["Location"], f.read(), {
            "Authorization": f"Bearer {token}", "Content-Type": "video/mp4"})
    when = f", publishes {publish_at}" if publish_at else ""
    print(f"[youtube] uploaded ({meta['status']['privacyStatus']}{when}): https://youtube.com/shorts/{v['id']}")
    if thumbnail:
        yt_set_thumbnail(v["id"], thumbnail, token)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--only", choices=["instagram", "youtube"])
    ap.add_argument("--title", default=DEFAULT_TITLE)
    ap.add_argument("--caption", default=DEFAULT_CAPTION)
    ap.add_argument("--yt-privacy", default="unlisted", choices=["public", "unlisted", "private"])
    ap.add_argument("--yt-lang", default="hi", help="YouTube language code (hi, en, mr, gu)")
    ap.add_argument("--yt-publish-at", help="RFC 3339 time for YouTube to publish it (uploads private until then)")
    ap.add_argument("--yt-tags", help="comma-separated YouTube tags (default: the caption's hashtags)")
    ap.add_argument("--trial", action="store_true", help="Instagram trial reel (non-followers only)")
    ap.add_argument("--cover-url", help="public https URL of a jpg cover, for Instagram")
    ap.add_argument("--yt-thumbnail", help="jpg to set as the YouTube thumbnail after uploading")
    ap.add_argument("--video-url", help="public https URL of the same mp4, for Instagram to fetch")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.only != "youtube":
        post_instagram(a.video, a.caption, a.trial, a.dry_run, a.video_url, a.cover_url)
    if a.only != "instagram":
        tags = [t.strip() for t in a.yt_tags.split(",")] if a.yt_tags else \
            list(dict.fromkeys(re.findall(r"#(\w+)", a.caption) + ["Shorts"]))
        post_youtube(a.video, a.title, a.caption, a.yt_privacy, a.dry_run, a.yt_lang, tags[:15], a.yt_publish_at, a.yt_thumbnail)
