"""Stdlib HTTP server for the web UI. Usage: python3 -m slg.web.server [port=8080]"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .payload import narrative_payload
from .session import PlanError, Session

STATIC = Path(__file__).parent / "static"
MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".json": "application/json"}


class App:
    def __init__(self):
        self.session: Session | None = None
        self.lock = threading.Lock()

    def new(self, body: dict) -> dict:
        s = Session(scenario=body.get("scenario", "default"), seed=int(body.get("seed", 0)),
                    player_faction=body.get("player_faction", "faction_2"), turns=int(body.get("turns", 20)),
                    ai=body.get("ai") if isinstance(body.get("ai"), dict) else None)
        with self.lock:
            self.session = s
        s.start()
        return {"session_id": "main"}


def make_handler(app: App):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, code, obj):
            b = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > 100_000:
                raise PlanError("body too large")
            try:
                return json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                raise PlanError("invalid JSON")

        def do_GET(self):
            p = self.path.split("?")[0]
            s = app.session
            if p == "/api/narrative":
                q = parse_qs(urlsplit(self.path).query)
                try:
                    return self._json(200, narrative_payload((q.get("scenario") or ["default"])[0],
                                                             (q.get("faction") or ["faction_2"])[0]))
                except ValueError as e:
                    return self._json(400, {"error": str(e)})
            if p == "/api/status":
                return self._json(200, s.status() if s else {"phase": "no_game"})
            if p == "/api/state":
                st = s.state() if s else None
                return self._json(200 if st else 409, st or {"error": "not awaiting input"})
            if p.startswith("/api/"):
                return self._json(404, {"error": "not found"})
            rel = "index.html" if p in ("/", "") else p.lstrip("/")
            f = (STATIC / rel).resolve()
            if STATIC.resolve() not in f.parents and f != STATIC.resolve() or not f.is_file():
                return self._json(404, {"error": "not found"})
            b = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", MIME.get(f.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_POST(self):
            p = self.path.split("?")[0]
            try:
                body = self._body()
                if p == "/api/new":
                    return self._json(200, app.new(body))
                s = app.session
                if s is None:
                    return self._json(409, {"error": "no game"})
                if p == "/api/plan":
                    s.submit_plan(body)
                    return self._json(200, {"ok": True})
                if p == "/api/estimate":
                    return self._json(200, {"ratio": s.estimate(str(body["city"]), str(body["target"]), int(body["troops"]))})
            except (PlanError, ValueError, KeyError) as e:
                return self._json(400, {"error": str(e)})
            return self._json(404, {"error": "not found"})

    return H


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    ThreadingHTTPServer(("127.0.0.1", port), make_handler(App())).serve_forever()


if __name__ == "__main__":
    main()
