"""사이트를 만들고 내 컴퓨터에서 열어 본다.

실행: python serve.py  →  http://localhost:4321
파일을 고친 뒤 브라우저를 새로 고치면 다시 만들어 보여 준다.
"""
from __future__ import annotations

import functools
import http.server
import os
import socketserver
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORT = 4321
WATCH = ("data", "content", "templates", "static", "lib", "build.py")


def stamp() -> float:
    latest = 0.0
    for name in WATCH:
        p = ROOT / name
        files = [p] if p.is_file() else [f for f in p.rglob("*") if f.is_file() and "__pycache__" not in f.parts]
        for f in files:
            latest = max(latest, f.stat().st_mtime)
    return latest


def rebuild():
    for name in [m for m in sys.modules if m == "build" or m == "lib" or m.startswith("lib.")]:
        del sys.modules[name]
    sys.path.insert(0, str(ROOT))
    os.environ["SITE_DRAFTS"] = "1"   # 공개 전 노트도 미리보기에서는 보여 준다
    import build
    build.main()


class Handler(http.server.SimpleHTTPRequestHandler):
    last = 0.0

    def do_GET(self):
        now = stamp()
        if now > Handler.last:
            try:
                rebuild()
                Handler.last = now
            except Exception as e:  # 오류 내용을 화면에 그대로 보여 준다
                self.send_response(500)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"빌드 오류\n\n{type(e).__name__}: {e}".encode("utf-8"))
                return
        super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_error(self, code, message=None, explain=None):
        page = ROOT / "dist" / "404.html"
        if code == 404 and page.exists():
            body = page.read_bytes()
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().send_error(code, message, explain)


def main():
    rebuild()
    Handler.last = stamp()
    handler = functools.partial(Handler, directory=str(ROOT / "dist"))
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), handler) as httpd:
        print(f"http://localhost:{PORT}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
