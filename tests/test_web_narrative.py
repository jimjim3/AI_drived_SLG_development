"""Story text over HTTP, the favored-lord attack scenario in web sessions, and the calendar in the state."""
import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from slg.web.server import App, make_handler
from slg.web.session import Session


class WebNarrativeTest(unittest.TestCase):
    def setUp(self):
        self.app = App()
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.app))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()

    def call(self, path, body=None):
        req = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_narrative_works_before_any_game(self):
        code, d = self.call("/api/narrative?scenario=advantage&faction=faction_3")
        self.assertEqual(code, 200)
        self.assertEqual(d["scenario"]["id"], "advantage:faction_3")
        self.assertEqual(d["lord"]["name"], "孫權")
        self.assertEqual(d["opening"]["tone"], "優勢")
        self.assertEqual(len(d["opening"]["advice"]), 3)
        self.assertEqual(len(d["officers"]), 42)
        self.assertEqual(len(d["cities"]), 9)

    def test_narrative_default_scenario_keeps_its_id(self):
        code, d = self.call("/api/narrative?scenario=default&faction=faction_1")
        self.assertEqual((code, d["scenario"]["id"]), (200, "default"))

    def test_narrative_rejects_bad_input(self):
        self.assertEqual(self.call("/api/narrative?scenario=nope&faction=faction_1")[0], 400)
        self.assertEqual(self.call("/api/narrative?scenario=default&faction=faction_9")[0], 400)

    def test_state_carries_calendar_starting_in_spring(self):
        self.call("/api/new", {"turns": 2, "seed": 0})
        end = time.time() + 10
        while self.call("/api/status")[1]["phase"] != "awaiting_input" and time.time() < end:
            time.sleep(0.02)
        code, st = self.call("/api/state")
        self.assertEqual(code, 200)
        self.assertEqual(st["calendar"]["label"], "第1年春")


class FavoredSessionTest(unittest.TestCase):
    def test_attack_scenario_favors_the_chosen_lord(self):
        for fid in ("faction_1", "faction_2", "faction_3"):
            s = Session(scenario="advantage", player_faction=fid, turns=1)
            self.assertEqual(s.scenario, f"advantage:{fid}")
            st = s.game.state
            tot = {}
            for c in st.cities.values():
                tot[c.owner] = tot.get(c.owner, 0) + c.troops
            self.assertEqual(max(tot, key=tot.get), fid)

    def test_default_scenario_is_untouched(self):
        self.assertEqual(Session(scenario="default", player_faction="faction_1", turns=1).scenario, "default")


if __name__ == "__main__":
    unittest.main()
