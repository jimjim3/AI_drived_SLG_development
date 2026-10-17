"""OpenAIChatCompleter: retry on 429/5xx with backoff, Retry-After, pacing; default stays no-retry."""
import http.server
import json
import threading
import unittest

from slg.agents.backends import MAX_BACKOFF_SECONDS, OpenAIChatCompleter

OK_BODY = b'{"choices":[{"message":{"content":"fine"}}]}'


def make_server(script):
    """script: list of (status, headers) consumed one per request; once empty, answers 200."""
    calls = []

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            calls.append(1)
            status, headers = script.pop(0) if script else (200, {})
            body = OK_BODY if status == 200 else b'{"error":"x"}'
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, calls


class RetryTest(unittest.TestCase):
    def completer(self, srv, **kw):
        self.slept = []
        return OpenAIChatCompleter(f"http://127.0.0.1:{srv.server_address[1]}", "m", sleep=self.slept.append, **kw)

    def test_default_does_not_retry(self):
        srv, calls = make_server([(429, {})])
        self.addCleanup(lambda: (srv.shutdown(), srv.server_close()))
        with self.assertRaises(RuntimeError) as cm:
            self.completer(srv)("s", "u")
        self.assertIn("429", str(cm.exception))
        self.assertEqual((len(calls), self.slept), (1, []))

    def test_retries_with_exponential_backoff_then_succeeds(self):
        srv, calls = make_server([(429, {}), (503, {}), (200, {})])
        self.addCleanup(lambda: (srv.shutdown(), srv.server_close()))
        self.assertEqual(self.completer(srv, http_retries=3)("s", "u"), "fine")
        self.assertEqual(len(calls), 3)
        self.assertEqual(self.slept, [2.0, 4.0])

    def test_retry_after_header_wins_and_is_capped(self):
        srv, _ = make_server([(429, {"Retry-After": "7"}), (429, {"Retry-After": "9999"}), (200, {})])
        self.addCleanup(lambda: (srv.shutdown(), srv.server_close()))
        self.completer(srv, http_retries=2)("s", "u")
        self.assertEqual(self.slept, [7.0, MAX_BACKOFF_SECONDS])

    def test_gives_up_after_retries_and_reports_last_status(self):
        srv, calls = make_server([(503, {})] * 5)
        self.addCleanup(lambda: (srv.shutdown(), srv.server_close()))
        with self.assertRaises(RuntimeError) as cm:
            self.completer(srv, http_retries=2)("s", "u")
        self.assertIn("503", str(cm.exception))
        self.assertEqual(len(calls), 3)

    def test_non_retryable_status_fails_immediately(self):
        srv, calls = make_server([(400, {})])
        self.addCleanup(lambda: (srv.shutdown(), srv.server_close()))
        with self.assertRaises(RuntimeError):
            self.completer(srv, http_retries=5)("s", "u")
        self.assertEqual((len(calls), self.slept), (1, []))

    def test_min_interval_paces_request_starts(self):
        srv, _ = make_server([])
        self.addCleanup(lambda: (srv.shutdown(), srv.server_close()))
        now = [100.0]
        c = OpenAIChatCompleter(f"http://127.0.0.1:{srv.server_address[1]}", "m", min_interval=5.0,
                                sleep=lambda s: (self.slept.append(s), now.__setitem__(0, now[0] + s)),
                                clock=lambda: now[0])
        self.slept = []
        c("s", "u")                      # first call starts immediately
        self.assertEqual(self.slept, [])
        now[0] += 2.0                    # only 2s later: must wait the remaining 3s
        c("s", "u")
        self.assertEqual(self.slept, [3.0])

    def test_cli_flags_reach_the_completer(self):
        import argparse
        from slg.sim.run_llm import build_completer
        ns = argparse.Namespace(openai_base_url="http://x", model="m", api_key_env=None, extra_body=None,
                                extra_body_json=None, demo=False, command=None, max_consecutive_errors=3,
                                http_retries=4, min_interval=1.5)
        inner = build_completer(ns)
        base = getattr(inner, "_completer", None) or getattr(inner, "completer", None) or getattr(inner, "inner", None)
        found = base if isinstance(base, OpenAIChatCompleter) else next(
            (v for v in vars(inner).values() if isinstance(v, OpenAIChatCompleter)), None)
        self.assertIsNotNone(found)
        self.assertEqual((found.http_retries, found.min_interval), (4, 1.5))


if __name__ == "__main__":
    unittest.main()


class TimeoutRetryTest(unittest.TestCase):
    def _run(self, retries, failures):
        from unittest import mock
        slept, state = [], {"n": 0}

        class Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return OK_BODY

        def fake_urlopen(req, timeout=None):
            state["n"] += 1
            if state["n"] <= failures:
                raise TimeoutError("The read operation timed out")
            return Resp()

        c = OpenAIChatCompleter("http://x", "m", http_retries=retries, sleep=slept.append)
        with mock.patch("urllib.request.urlopen", fake_urlopen):
            try:
                return c("s", "u"), state["n"], slept
            except RuntimeError as e:
                return str(e), state["n"], slept

    def test_timeouts_are_retried_when_enabled(self):
        out, n, slept = self._run(retries=3, failures=2)
        self.assertEqual((out, n, slept), ("fine", 3, [2.0, 4.0]))

    def test_timeouts_fail_fast_by_default(self):
        out, n, slept = self._run(retries=0, failures=1)
        self.assertIn("TimeoutError", out)
        self.assertEqual((n, slept), (1, []))

    def test_gives_up_after_the_retry_budget(self):
        out, n, _ = self._run(retries=1, failures=9)
        self.assertIn("TimeoutError", out)
        self.assertEqual(n, 2)

    def test_http_timeout_flag_reaches_the_completer(self):
        import argparse
        from slg.sim.run_llm import build_completer
        ns = argparse.Namespace(openai_base_url="http://x", model="m", api_key_env=None, extra_body=None,
                                extra_body_json=None, demo=False, command=None, max_consecutive_errors=3,
                                http_retries=1, min_interval=0.0, http_timeout=300.0)
        inner = build_completer(ns)
        found = next(v for v in vars(inner).values() if isinstance(v, OpenAIChatCompleter))
        self.assertEqual(found.timeout, 300.0)
