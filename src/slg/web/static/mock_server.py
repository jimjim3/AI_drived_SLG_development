#!/usr/bin/env python3
"""Mock server for Three Kingdoms SLG web frontend development & verification.

Uses only Python standard library.
Serves static assets and provides mock /api endpoints matching docs/UI_SPEC.md.
"""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import time
from urllib.parse import urlparse

STATIC_DIR = Path(__file__).resolve().parent
REPO_ROOT = STATIC_DIR.parents[3]
FIXTURE_PATH = REPO_ROOT / "docs" / "ui_fixtures" / "state_turn0_faction_2.json"


class MockGameState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self.lock:
            self.turn = 0
            self.phase = "awaiting_input"
            self.resolving_until = 0.0
            self.events: list[str] = []
            self.feedback: list[str] = []
            self.winner: str | None = None
            self.last_plan: dict | None = None

    def submit_plan(self, plan: dict) -> None:
        with self.lock:
            self.last_plan = plan
            self.phase = "resolving"
            self.resolving_until = time.time() + 2.0

    def get_status(self) -> dict:
        with self.lock:
            if self.phase == "resolving" and time.time() >= self.resolving_until:
                self.phase = "awaiting_input"
                self.turn += 1
                orders_count = len(self.last_plan.get("orders", [])) if self.last_plan else 0
                self.events = [
                    f"T{self.turn} 關羽 develop_agri@洛陽: 農業提升，民殷國富",
                    f"T{self.turn} 諸葛亮 視察軍政，安撫黎民",
                    f"T{self.turn} 曹操 勢力在許昌集結步騎千人",
                ]
                self.feedback = [
                    f"軍務報告：本回合下達之 {orders_count} 道命令已驗證完畢",
                    "審查反饋：部分調動已按排程生效",
                ]
            return {
                "phase": self.phase,
                "turn": self.turn,
                "events": list(self.events),
                "feedback": list(self.feedback),
                "winner": self.winner,
            }

    def get_state(self) -> dict:
        with self.lock:
            current_turn = self.turn
            events = list(self.events)
            feedback = list(self.feedback)

        if FIXTURE_PATH.is_file():
            with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {
                "turn": current_turn,
                "faction_id": "faction_2",
                "faction_name": "劉備",
                "cities": [],
                "frontier": [],
                "cast": [],
                "roster": {},
                "map": {"nodes": [], "edges": []},
            }

        data["turn"] = current_turn
        data["events"] = events
        data["feedback"] = feedback
        return data


GAME_STATE = MockGameState()


class SLGRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def _send_json(self, data: dict, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            self._send_json(GAME_STATE.get_state())
            return
        if parsed.path == "/api/status":
            self._send_json(GAME_STATE.get_status())
            return

        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            payload = json.loads(post_data.decode("utf-8")) if post_data else {}
        except Exception:
            payload = {}

        if parsed.path == "/api/new":
            GAME_STATE.reset()
            self._send_json({"session_id": "mock", "turn": 0, "status": "ok"})
            return

        if parsed.path == "/api/plan":
            GAME_STATE.submit_plan(payload)
            self._send_json({"status": "ok", "phase": "resolving"})
            return

        if parsed.path == "/api/estimate":
            self._send_json({"ratio": 0.5})
            return

        self._send_json({"error": "Not Found"}, status=HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args) -> None:
        # Standard quiet logging
        sys.stderr.write(f"[{self.log_date_time_string()}] {format % args}\n")


def run(port: int = 8765) -> None:
    server_address = ("0.0.0.0", port)
    httpd = ThreadingHTTPServer(server_address, SLGRequestHandler)
    print(f"Mock SLG Server serving {STATIC_DIR} at http://localhost:{port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    port_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    run(port_arg)
