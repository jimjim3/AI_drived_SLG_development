"""Deployment safety: access token, safe bind, per-tab sessions, and the web AI backends."""
import json
import os
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

from slg.agents.backends import OpenAIChatCompleter
from slg.agents.llm_agent import SIEGE_VERDICT_NOTE, LLMFactionAgent
from slg.web import backends
from slg.web.server import App, check_bind, is_loopback, make_handler


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def serve(token=None, max_sessions=8):
    app = App(max_sessions=max_sessions)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app, token))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return app, srv, f"http://127.0.0.1:{srv.server_address[1]}"


def call(base, path, body=None, headers=None, follow=True):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **(headers or {})})
    opener = urllib.request.build_opener() if follow else urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw[:1] in (b"{", b"[") else raw), dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, (json.loads(raw) if raw[:1] in (b"{", b"[") else raw), dict(e.headers)


class BindTest(unittest.TestCase):
    def test_loopback_detection(self):
        for h in ("127.0.0.1", "localhost", "::1"):
            self.assertTrue(is_loopback(h), h)
        for h in ("0.0.0.0", "192.168.1.5", "example.com"):
            self.assertFalse(is_loopback(h), h)

    def test_public_bind_requires_token_or_insecure(self):
        check_bind("127.0.0.1", None)                 # fine
        check_bind("0.0.0.0", "secret")               # fine
        check_bind("0.0.0.0", None, insecure=True)    # explicit opt-out
        with self.assertRaises(SystemExit):
            check_bind("0.0.0.0", None)


class TokenTest(unittest.TestCase):
    def setUp(self):
        self.app, self.srv, self.base = serve(token="s3cret")
        self.addCleanup(lambda: (self.srv.shutdown(), self.srv.server_close()))

    def test_healthz_is_open_everything_else_is_not(self):
        self.assertEqual(call(self.base, "/healthz")[0], 200)
        self.assertEqual(call(self.base, "/api/status")[0], 401)
        self.assertEqual(call(self.base, "/api/narrative?scenario=default&faction=faction_1")[0], 401)
        self.assertEqual(call(self.base, "/")[0], 401)
        self.assertEqual(call(self.base, "/api/new", {})[0], 401)

    def test_wrong_token_is_rejected(self):
        self.assertEqual(call(self.base, "/api/status", headers={"Authorization": "Bearer nope"})[0], 401)
        self.assertEqual(call(self.base, "/?token=nope", follow=False)[0], 401)
        self.assertEqual(call(self.base, "/api/status", headers={"Cookie": "slg_token=nope"})[0], 401)

    def test_bearer_header_works(self):
        self.assertEqual(call(self.base, "/api/status", headers={"Authorization": "Bearer s3cret"})[0], 200)

    def test_query_token_sets_cookie_then_cookie_works(self):
        code, _, headers = call(self.base, "/?token=s3cret", follow=False)
        self.assertEqual(code, 302)
        cookie = headers["Set-Cookie"]
        self.assertIn("slg_token=s3cret", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertEqual(call(self.base, "/api/status", headers={"Cookie": "slg_token=s3cret"})[0], 200)
        self.assertEqual(call(self.base, "/", headers={"Cookie": "slg_token=s3cret"})[0], 200)

    def test_secure_flag_behind_https_proxy(self):
        _, _, headers = call(self.base, "/?token=s3cret", headers={"X-Forwarded-Proto": "https"}, follow=False)
        self.assertIn("Secure", headers["Set-Cookie"])

    def test_no_token_configured_means_open(self):
        app, srv, base = serve(token=None)
        self.addCleanup(lambda: (srv.shutdown(), srv.server_close()))
        self.assertEqual(call(base, "/api/status")[0], 200)


class SessionIsolationTest(unittest.TestCase):
    def setUp(self):
        self.app, self.srv, self.base = serve(max_sessions=2)
        self.addCleanup(lambda: (self.srv.shutdown(), self.srv.server_close()))

    def start(self, sid, **body):
        code, _, _ = call(self.base, "/api/new", {"turns": 1, "seed": 0, **body}, headers={"X-Session": sid})
        self.assertEqual(code, 200)

    def phase(self, sid):
        return call(self.base, "/api/status", headers={"X-Session": sid})[1]["phase"]

    def test_sessions_are_independent(self):
        self.assertEqual(self.phase("a"), "no_game")
        self.start("a")
        self.assertNotEqual(self.phase("a"), "no_game")
        self.assertEqual(self.phase("b"), "no_game")  # another tab sees nothing

    def test_invalid_session_id_is_rejected(self):
        self.assertEqual(call(self.base, "/api/status", headers={"X-Session": "bad id!"})[0], 400)
        self.assertEqual(call(self.base, "/api/new", {}, headers={"X-Session": "../x"})[0], 400)

    def test_least_recently_used_session_is_dropped(self):
        for sid in ("a", "b", "c"):
            self.start(sid)
        self.assertEqual(self.phase("a"), "no_game")      # evicted (limit is 2)
        self.assertNotEqual(self.phase("c"), "no_game")

    def test_legacy_main_session_still_works(self):
        call(self.base, "/api/new", {"turns": 1, "seed": 0})
        self.assertIsNotNone(self.app.session)


class BackendFactoryTest(unittest.TestCase):
    def completer(self, agent):
        self.assertIsInstance(agent, LLMFactionAgent)
        inner = agent._completer.inner
        self.assertIsInstance(inner, OpenAIChatCompleter)
        return inner

    def test_kinds_include_nim(self):
        self.assertIn("nim", backends.KINDS)
        with self.assertRaises(ValueError):
            backends.make_ai_agent("nope")

    def test_nim_agent_settings(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SLG_NIM_MODEL", None)
            agent = backends.make_ai_agent("nim")
        c = self.completer(agent)
        self.assertEqual(c.base_url, backends.NIM_URL)
        self.assertEqual(c.model, backends.NIM_DEFAULT_MODEL)
        self.assertEqual(c.api_key_env, "NVIDIA_API_KEY")        # name only: the key never leaves the environment
        self.assertEqual(c.extra_body, {"chat_template_kwargs": {"enable_thinking": False}})
        self.assertGreater(c.http_retries, 0)
        self.assertTrue(agent._with_verdict)
        self.assertTrue(agent._system_prompt.endswith(SIEGE_VERDICT_NOTE))

    def test_qwen_agent_uses_env_url_and_disables_thinking(self):
        env = {"SLG_QWEN_URL": "https://x.example/v1", "SLG_QWEN_MODEL": "qwen3.8:27b"}
        with mock.patch.dict(os.environ, env):
            os.environ.pop("SLG_QWEN_EXTRA_BODY", None)
            c = self.completer(backends.make_ai_agent("qwen"))
        self.assertEqual((c.base_url, c.model), ("https://x.example/v1", "qwen3.8:27b"))
        self.assertEqual(c.extra_body["reasoning_effort"], "none")
        self.assertFalse(c.extra_body["chat_template_kwargs"]["enable_thinking"])
        self.assertGreater(c.http_retries, 0)

    def test_qwen_extra_body_override_and_validation(self):
        with mock.patch.dict(os.environ, {"SLG_QWEN_EXTRA_BODY": '{"think": false}'}):
            self.assertEqual(self.completer(backends.make_ai_agent("qwen")).extra_body, {"think": False})
        with mock.patch.dict(os.environ, {"SLG_QWEN_EXTRA_BODY": "[1]"}):
            with self.assertRaises(ValueError):
                backends.make_ai_agent("qwen")

    def test_rule_and_demo_have_no_network(self):
        self.assertEqual(backends.make_ai_agent("rule").name, "rule_based")
        self.assertFalse(backends.make_ai_agent("demo")._with_verdict)

    def test_setup_form_offers_nim(self):
        from pathlib import Path
        html = (Path(backends.__file__).parent / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn('name="setupAI" value="nim"', html)


if __name__ == "__main__":
    unittest.main()
