"""Preview the web UI from this checkout against the running API, without touching it.

Serves index.html and /static/* from THIS folder, and forwards every other request
(login, /me, /answer, /documents, PDFs) to the API at http://localhost:8000.
Use it to try a UI branch while the frozen API keeps running from main.

    python scripts/ui_preview.py            # then open http://localhost:8001
"""
import http.server
import mimetypes
import sys
import urllib.error
import urllib.request
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"
API = "http://localhost:8000"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8001
HOP = {"connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade",
       "proxy-authorization", "proxy-authenticate", "host", "content-length"}


class Handler(http.server.BaseHTTPRequestHandler):
    def _static(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            target = STATIC / "index.html"
        elif path.startswith("/static/"):
            target = (STATIC / path[len("/static/"):]).resolve()
            if STATIC.resolve() not in target.parents:
                return False
        else:
            return False
        if not target.is_file():
            return False
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
        return True

    def _proxy(self):
        length = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
        req = urllib.request.Request(API + self.path, data=data, headers=headers, method=self.command)
        try:
            resp = urllib.request.urlopen(req, timeout=180)
        except urllib.error.HTTPError as err:
            resp = err
        except urllib.error.URLError:
            self.send_error(502, "API not reachable on localhost:8000. Is docker compose up?")
            return
        body = resp.read()
        self.send_response(resp.status if hasattr(resp, "status") else resp.code)
        for k, v in resp.headers.items():
            if k.lower() not in HOP:
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._static():
            self._proxy()

    def do_POST(self):
        self._proxy()

    def log_message(self, fmt, *args):
        sys.stderr.write("preview: " + fmt % args + "\n")


if __name__ == "__main__":
    print(f"UI from {STATIC}\nAPI at {API}\nOpen http://localhost:{PORT}  (Ctrl+C to stop)")
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
