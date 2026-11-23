"""Put a local mp4 on a temporary public host and print its direct URL (last line of stdout).

Instagram's API for Instagram-Login tokens only accepts a `video_url` it can download, not a file
upload. This remuxes the mp4 with the moov atom first (faststart, which Instagram prefers), then
  1. if VIDS_BASE_URL is set (e.g. https://videos.example.com) and its /health answers, copies the file into
     public_videos/<random token>/ for serve_videos.py to serve (removed after a few hours), else
  2. uploads it to uguu.se (direct https link, kept a few hours),
and checks that the link serves video/mp4 with the right size.

  python host_video.py VIDEO
"""
import os, re, secrets, shutil, subprocess, sys, tempfile

UA = "Mozilla/5.0 (X11; Linux x86_64)"
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=900)


def base_url():
    """VIDS_BASE_URL from the environment or the repo's .env (own server, see serve_videos.py)."""
    if os.environ.get("VIDS_BASE_URL"):
        return os.environ["VIDS_BASE_URL"].rstrip("/")
    env = os.path.join(ROOT, ".env")
    if os.path.exists(env):
        for line in open(env, encoding="utf-8"):
            k, _, v = line.strip().partition("=")
            if k == "VIDS_BASE_URL" and v:
                return v.strip().strip("\"'").rstrip("/")
    return ""


def check(url, size, ctype="video/mp4"):
    h = run(["curl", "-sI", "-m", "30", "-A", "facebookexternalhit/1.1", url]).stdout.lower()
    lines = h.splitlines()
    return bool(lines) and "200" in lines[0] and ctype in h and f"content-length: {size}" in h


def own_server(fast, name, size):
    """Copy into the served folder under a random token and return the public URL (or None)."""
    base = base_url()
    if not base:
        return None
    if run(["curl", "-s", "-m", "15", base + "/health"]).stdout.strip() != "ok":
        print(f"{base} is not answering /health; falling back to uguu.se", file=sys.stderr)
        return None
    token = secrets.token_urlsafe(16)
    folder = os.path.join(os.environ.get("VIDS_DIR", os.path.join(ROOT, "public_videos")), token)
    os.makedirs(folder)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
    shutil.copy(fast, os.path.join(folder, safe))
    url = f"{base}/{token}/{safe}"
    if check(url, size, "image/" if safe.endswith((".jpg", ".png")) else "video/mp4"):
        return url
    shutil.rmtree(folder, ignore_errors=True)
    print(f"{url} did not check out; falling back to uguu.se", file=sys.stderr)
    return None


def main(video):
    if video.lower().endswith((".jpg", ".png")):  # covers: served as they are, own server only
        url = own_server(video, os.path.basename(video), os.path.getsize(video))
        sys.exit(f"could not host {video}") if not url else print(url)
        return
    with tempfile.TemporaryDirectory() as tmp:
        fast = os.path.join(tmp, "fast.mp4")
        r = run(["ffmpeg", "-v", "error", "-y", "-i", video, "-c", "copy", "-movflags", "+faststart", fast])
        if r.returncode:
            sys.exit(f"faststart remux failed: {r.stderr.strip()}")
        size = os.path.getsize(fast)
        url = own_server(fast, os.path.basename(video), size)
        if url:
            print(url)
            return
        r = run(["curl", "-sS", "-m", "600", "-A", UA, "-F", f"files[]=@{fast}", "https://uguu.se/upload?output=text"])
        url = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
        if not url.startswith("https://") or r.returncode:
            sys.exit(f"upload to uguu.se failed: {r.stdout.strip()[:200]} {r.stderr.strip()[:200]}")
    if not check(url, size):
        sys.exit(f"hosted file did not check out: {url}")
    print(url)


if __name__ == "__main__":
    main(sys.argv[1])
