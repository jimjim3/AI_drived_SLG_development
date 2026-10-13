import json
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

from slg.web.server import App, make_handler
from slg.web.session import PlanError, Session, parse_plan


def wait_phase(s, phase, t=10):
    end = time.time() + t
    while time.time() < end:
        if s.status()["phase"] == phase:
            return
        time.sleep(0.01)
    raise AssertionError(f"phase {s.status()} != {phase}")


class SessionTest(unittest.TestCase):
    def test_parse_rejects_bad_shapes(self):
        for bad in ({"orders": [{"officer": 1, "action": "rest"}]}, {"orders": [{"action": "rest"}]},
                    {"next_cast": ["a"] * 7}, {"next_cast": "x"}, []):
            with self.assertRaises(PlanError):
                parse_plan(bad)

    def test_empty_plans_complete_game(self):
        s = Session(seed=3, turns=4, human_timeout=5)
        s.start()
        for t in range(4):
            wait_phase(s, "awaiting_input")
            while s.status()["turn"] != t + 1:
                time.sleep(0.01)
            s.submit_plan({"orders": [], "next_cast": []})
            time.sleep(0.05)
        wait_phase(s, "game_over")
        self.assertIsNone(s.status()["error"])
        self.assertEqual(s.timeouts, 0)
        self.assertEqual(s.game.state.turn, 4)

    def test_state_has_no_fog_leak(self):
        s = Session(seed=0, turns=1, human_timeout=2)
        s.start()
        wait_phase(s, "awaiting_input")
        st = s.state()
        fog = [n["id"] for n in st["map"]["nodes"] if n["visibility"] == "fog"]
        self.assertTrue(fog)
        blob = json.dumps(st, ensure_ascii=False)
        full = s.game.state
        for cid in fog:
            self.assertNotIn(f'"{cid}"', json.dumps([c for c in st["cities"]] + st["frontier"]))
            self.assertNotIn(f"{full.cities[cid].troops}兵", blob)
        self.assertTrue(all("legal_structured" in c for c in st["cast"]))
        s.submit_plan({})
        wait_phase(s, "game_over")

    def test_timeout_counts_and_continues(self):
        s = Session(seed=0, turns=2, human_timeout=0.2)
        s.start()
        wait_phase(s, "game_over")
        self.assertEqual(s.timeouts, 2)

    def test_illegal_order_gets_feedback(self):
        s = Session(seed=0, turns=2, human_timeout=5)
        s.start()
        wait_phase(s, "awaiting_input")
        s.submit_plan({"orders": [{"officer": "guan_yu", "action": "siege", "params": {"to": "kuaiji", "troops": 900}}]})
        while s.status()["turn"] != 2 or s.status()["phase"] != "awaiting_input":
            time.sleep(0.01)
        # turn 2 view is built from the same turn counter; feedback must mention the rejection
        fb = s.status()["feedback"]
        self.assertTrue(fb, "rejected order should come back as feedback")
        s.submit_plan({})
        wait_phase(s, "game_over")


class HttpTest(unittest.TestCase):
    def test_roundtrip(self):
        app = App()
        srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"

        def call(path, body=None):
            req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read())
        try:
            self.assertEqual(call("/api/status")[1]["phase"], "no_game")
            self.assertEqual(call("/api/plan", {})[0], 409)
            call("/api/new", {"turns": 1, "seed": 0})
            end = time.time() + 10
            while call("/api/status")[1]["phase"] != "awaiting_input" and time.time() < end:
                time.sleep(0.02)
            self.assertEqual(call("/api/state")[0], 200)
            self.assertEqual(call("/api/plan", {"next_cast": ["x"] * 9})[0], 400)
            self.assertEqual(call("/api/plan", {"orders": []})[0], 200)
            self.assertEqual(call("/../../etc/passwd")[0], 404)
        finally:
            srv.shutdown()


if __name__ == "__main__":
    unittest.main()
