"""Smallest possible public file server for Instagram's video_url: Python standard library only.

Serves read-only files from one directory, only as /<token>/<name>.mp4 (or .png/.jpg) (token = 16+ chars, so a link
can't be guessed and there is no directory listing), with HTTP Range support (Instagram fetches with
ranges), plus /health. Everything older than --keep-hours is deleted, so videos are only public while
a post is in flight. host_video.py writes files here and returns https://<VIDS_BASE_URL>/<token>/<name>.mp4.

  python serve_videos.py [--dir public_videos] [--port 8099] [--host 0.0.0.0] [--keep-hours 6]
Put an HTTPS reverse proxy or tunnel (e.g. videos.example.com) in front of this port.
"""
import argparse, os, re, shutil, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PATH_RE = re.compile(r"^/([A-Za-z0-9_-]{16,})/([A-Za-z0-9_.-]+\.(?:mp4|png|jpg))$")
TYPES = {".mp4": "video/mp4", ".png": "image/png", ".jpg": "image/jpeg"}


def make_handler(root):
    class H(BaseHTTPRequestHandler):
        server_version = "vids"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            print(self.log_date_time_string(), self.client_address[0], fmt % args, flush=True)

        def _send(self, code, body=b"", ctype="text/plain", extra=None, head=False):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if not head:
                self.wfile.write(body)

        def _serve(self, head):
            path = self.path.split("?", 1)[0]
            if path.rstrip("/") == "/health":
                return self._send(200, b"ok", head=head)
            m = PATH_RE.match(path)
            f = os.path.join(root, m.group(1), m.group(2)) if m else None
            if not f or not os.path.isfile(f):
                return self._send(404, b"not found", head=head)
            size = os.path.getsize(f)
            start, end, code = 0, size - 1, 200
            rng = self.headers.get("Range")
            if rng:
                r = re.match(r"bytes=(\d*)-(\d*)$", rng.strip())
                if not r or (not r.group(1) and not r.group(2)):
                    return self._send(416, b"bad range", extra={"Content-Range": f"bytes */{size}"}, head=head)
                if r.group(1):
                    start = int(r.group(1))
                    end = min(int(r.group(2)), size - 1) if r.group(2) else size - 1
                else:  # suffix range
                    start = max(0, size - int(r.group(2)))
                if start >= size or start > end:
                    return self._send(416, b"bad range", extra={"Content-Range": f"bytes */{size}"}, head=head)
                code = 206
            length = end - start + 1
            self.send_response(code)
            self.send_header("Content-Type", TYPES[os.path.splitext(f)[1]])
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-store")
            if code == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if head:
                return
            with open(f, "rb") as fh:
                fh.seek(start)
                left = length
                while left > 0:
                    chunk = fh.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)

        def handle(self):
            try:  # a client that hangs up after a range probe is normal, not an error
                super().handle()
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            self._serve(False)

        def do_HEAD(self):
            self._serve(True)

    return H


def cleaner(root, keep_hours):
    while True:
        cutoff = time.time() - keep_hours * 3600
        for d in os.listdir(root):
            p = os.path.join(root, d)
            if os.path.isdir(p) and os.path.getmtime(p) < cutoff:
                shutil.rmtree(p, ignore_errors=True)
        time.sleep(600)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "public_videos"))
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--keep-hours", type=float, default=6)
    a = ap.parse_args()
    root = os.path.abspath(a.dir)
    os.makedirs(root, exist_ok=True)
    threading.Thread(target=cleaner, args=(root, a.keep_hours), daemon=True).start()
    print(f"serving {root} on {a.host}:{a.port}", flush=True)
    ThreadingHTTPServer((a.host, a.port), make_handler(root)).serve_forever()
