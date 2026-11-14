import tempfile
import time
import unittest
from pathlib import Path

from slg.engine import combat
from slg.web import savegame
from slg.web.server import App
from slg.web.session import PlanError, Session
from tests.test_web_session import wait_phase


def play(s, n):
    """Submit empty plans until the session has finished n steps."""
    for _ in range(n):
        wait_phase(s, "awaiting_input")
        t = s.status()["turn"]
        s.submit_plan({"orders": [], "next_cast": []})
        end = time.time() + 5
        while time.time() < end and (s.phase != "awaiting_input" or s.status()["turn"] == t):
            if s.phase == "game_over":
                return
            time.sleep(0.01)


class SaveGameTest(unittest.TestCase):
    def setUp(self):
        combat.set_rules("v2")
        self.dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.path = Path(self.dir.name) / "main.sav"

    def tearDown(self):
        self.dir.cleanup()
        combat.set_rules("v2")

    def test_resume_reproduces_the_same_game(self):
        # reference run: 6 turns straight through
        ref = Session(seed=7, turns=6, human_timeout=5)
        ref.start()
        play(ref, 6)
        wait_phase(ref, "game_over")
        # interrupted run: play 3, drop the session, resume from the save, play the rest
        a = Session(seed=7, turns=6, human_timeout=5, save_path=self.path)
        a.start()
        play(a, 3)
        wait_phase(a, "awaiting_input")
        a.abandon()
        self.assertTrue(self.path.is_file())
        self.assertEqual(savegame.describe(self.path)["turn"], 4)
        b = Session.resume(self.path, human_timeout=5)
        b.start()
        play(b, 3)
        wait_phase(b, "game_over")
        self.assertEqual(b.game.state, ref.game.state)
        self.assertFalse(self.path.exists())  # finished games are not resumable

    def test_abandoned_session_does_not_overwrite_newer_save(self):
        a = Session(seed=1, turns=5, human_timeout=5, save_path=self.path)
        a.start()
        wait_phase(a, "awaiting_input")
        before = self.path.read_bytes()
        a.abandon()
        time.sleep(0.2)
        self.assertEqual(self.path.read_bytes(), before)

    def test_ruleset_mismatch_is_refused(self):
        a = Session(seed=1, turns=5, human_timeout=5, save_path=self.path)
        a.start()
        wait_phase(a, "awaiting_input")
        a.abandon()
        combat.set_rules("softer_pool2_econ3")
        with self.assertRaises(ValueError):
            Session.resume(self.path)

    def test_app_resume_flow(self):
        app = App(save_dir=self.dir.name)
        self.assertIsNone(app.save_info("main"))
        with self.assertRaises(PlanError):
            app.resume("main")
        app.new({"seed": 2, "turns": 5}, "main")
        s = app.get("main")
        wait_phase(s, "awaiting_input")
        self.assertEqual(app.save_info("main")["turn"], 1)
        app.resume("main")  # replaces the live session with one restored from the file
        self.assertIsNot(app.get("main"), s)
        self.assertTrue(s.abandoned)

    def test_corrupt_save_is_reported(self):
        app = App(save_dir=self.dir.name)
        (Path(self.dir.name) / "main.sav").write_bytes(b"not a pickle")
        self.assertIsNone(app.save_info("main"))
        with self.assertRaises(PlanError):
            app.resume("main")


if __name__ == "__main__":
    unittest.main()
