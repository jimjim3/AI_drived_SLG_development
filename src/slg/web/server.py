"""Stdlib HTTP server for the web UI.

Usage: python3 -m slg.web.server [port=8080] [--host 127.0.0.1] [--insecure]

Deployment notes (see deploy/README.md):
- Binds to loopback by default. Binding anywhere else requires SLG_ACCESS_TOKEN (or --insecure).
- With SLG_ACCESS_TOKEN set, every request except /healthz needs the token: open the site once with
  ?token=<value> (it is stored in a cookie), or send `Authorization: Bearer <value>`.
- Each browser tab sends its own X-Session id, so several people/tabs can play at once (at most
  MAX_SESSIONS live games; the least recently used one is dropped). Without the header the legacy
  single "main" session is used.
"""

from __future__ import annotations

import argparse
import hmac
import ipaddress
import json
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .payload import narrative_payload
from .session import PlanError, Session

MAX_SESSIONS = 8
SID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
STATIC = Path(__file__).parent / "static"
MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".json": "application/json"}


class App:
    def __init__(self, max_sessions: int = MAX_SESSIONS):
        self.max_sessions = max_sessions
        self.sessions: dict[str, Session] = {}  # insertion order doubles as recency order
        self.lock = threading.Lock()

    @property
    def session(self) -> Session | None:
        """The legacy single session ("main")."""
        return self.sessions.get("main")

    def get(self, sid: str = "main") -> Session | None:
        with self.lock:
            s = self.sessions.pop(sid, None)
            if s is not None:
                self.sessions[sid] = s  # mark as most recently used
            return s

    def new(self, body: dict, sid: str = "main") -> dict:
        s = Session(scenario=body.get("scenario", "default"), seed=int(body.get("seed", 0)),
                    player_faction=body.get("player_faction", "faction_2"), turns=int(body.get("turns", 20)),
                    ai=body.get("ai") if isinstance(body.get("ai"), dict) else None)
        with self.lock:
            self.sessions.pop(sid, None)
            self.sessions[sid] = s
            while len(self.sessions) > self.max_sessions:
                self.sessions.pop(next(iter(self.sessions)))
        s.start()
        return {"session_id": sid}


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def check_bind(host: str, token: str | None, insecure: bool = False) -> None:
    """Refuse to expose the server beyond loopback without an access token."""
    if not is_loopback(host) and not token and not insecure:
        raise SystemExit(
            f"refusing to listen on {host!r} without protection: set SLG_ACCESS_TOKEN (recommended) "
            "or pass --insecure. Anyone who can reach the port could start games and spend your AI quota."
        )


def make_handler(app: App, token: str | None = None):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        # --- access control ---------------------------------------------------
        def _cookie_token(self) -> str:
            for part in (self.headers.get("Cookie") or "").split(";"):
                k, _, v = part.strip().partition("=")
                if k == "slg_token":
                    return v
            return ""

        def _token_ok(self, candidate: str) -> bool:
            return bool(token) and hmac.compare_digest(candidate.encode(), token.encode())

        def _authorized(self) -> bool:
            if not token:
                return True
            bearer = (self.headers.get("Authorization") or "")
            if bearer.startswith("Bearer ") and self._token_ok(bearer[7:]):
                return True
            return self._token_ok(self._cookie_token())

        def _deny(self, path: str):
            msg = "unauthorized: open this site once with ?token=<access token>"
            if path.startswith("/api/"):
                return self._json(401, {"error": msg})
            b = f"<!doctype html><meta charset=utf-8><title>需要存取密碼</title><p>{msg}</p>".encode()
            self.send_response(401)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def _try_login(self, parts) -> bool:
            """?token=... on a page request: set the cookie and redirect to the clean URL."""
            q = parse_qs(parts.query).get("token")
            if not (token and q and self._token_ok(q[0])):
                return False
            secure = "; Secure" if (self.headers.get("X-Forwarded-Proto") or "").lower() == "https" else ""
            self.send_response(302)
            self.send_header("Set-Cookie", f"slg_token={q[0]}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000{secure}")
            self.send_header("Location", parts.path or "/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return True

        def _sid(self) -> str:
            sid = self.headers.get("X-Session") or "main"
            if not SID_RE.match(sid):
                raise PlanError("invalid X-Session header")
            return sid

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
            parts = urlsplit(self.path)
            p = parts.path
            if p == "/healthz":
                return self._json(200, {"ok": True})
            if not self._authorized():
                if self._try_login(parts):
                    return
                return self._deny(p)
            try:
                s = app.get(self._sid())
            except PlanError as e:
                return self._json(400, {"error": str(e)})
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
            if not self._authorized():
                return self._deny(p)
            try:
                body = self._body()
                sid = self._sid()
                if p == "/api/new":
                    return self._json(200, app.new(body, sid))
                s = app.get(sid)
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


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="SLG web UI server")
    ap.add_argument("port", nargs="?", type=int, default=int(os.environ.get("SLG_PORT", "8080")))
    ap.add_argument("--host", default=os.environ.get("SLG_HOST", "127.0.0.1"))
    ap.add_argument("--insecure", action="store_true", help="allow a non-loopback bind without SLG_ACCESS_TOKEN")
    ap.add_argument("--rules", default=os.environ.get("SLG_RULES") or None,
                    help="combat ruleset (default v2; e.g. softer_pool2 lets AI opponents attack)")
    args = ap.parse_args(argv)
    if args.rules:
        from slg.engine import combat
        combat.set_rules(args.rules)
    token = os.environ.get("SLG_ACCESS_TOKEN") or None
    check_bind(args.host, token, args.insecure)
    srv = ThreadingHTTPServer((args.host, args.port), make_handler(App(), token))
    print(f"SLG web on http://{args.host}:{args.port}/  (access token {'required' if token else 'NOT required'})",
          file=sys.stderr, flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
