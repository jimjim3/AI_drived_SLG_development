import http.server
import json
import os
import sys
import tempfile
import threading
import unittest

from slg.agents.backends import (
    CommandCompleter,
    OpenAIChatCompleter,
    ScriptedCompleter,
)


class MockOpenAIHandler(http.server.BaseHTTPRequestHandler):
    requests_received = []
    response_code = 200
    response_body = b'{"choices":[{"message":{"content":"response from mock server"}}]}'

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length)
        parsed_body = json.loads(raw_body.decode("utf-8")) if raw_body else {}

        self.__class__.requests_received.append({
            "path": self.path,
            "headers": dict(self.headers),
            "body": parsed_body,
        })

        self.send_response(self.__class__.response_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(self.__class__.response_body)

    def log_message(self, format, *args):
        pass


class BackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), MockOpenAIHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        MockOpenAIHandler.requests_received = []
        MockOpenAIHandler.response_code = 200
        MockOpenAIHandler.response_body = b'{"choices":[{"message":{"content":"response from mock server"}}]}'

    def test_scripted_completer_sequential_and_call_log(self):
        completer = ScriptedCompleter(["first response", "second response"])
        res1 = completer("sys", "u1")
        res2 = completer("sys", "u2")
        self.assertEqual(res1, "first response")
        self.assertEqual(res2, "second response")
        self.assertEqual(completer.calls, [("sys", "u1"), ("sys", "u2")])

    def test_scripted_completer_exception_propagation(self):
        completer = ScriptedCompleter([RuntimeError("upstream crash")])
        with self.assertRaises(RuntimeError) as cm:
            completer("sys", "u")
        self.assertIn("upstream crash", str(cm.exception))

    def test_scripted_completer_exhaustion_raises_index_error(self):
        completer = ScriptedCompleter(["only one"])
        completer("sys", "u1")
        with self.assertRaises(IndexError):
            completer("sys", "u2")

    def test_command_completer_stdin_mode(self):
        cmd = [
            sys.executable,
            "-c",
            "import sys; print(sys.stdin.read().upper())",
        ]
        completer = CommandCompleter(cmd)
        output = completer("hello", "world")
        self.assertEqual(output, "HELLO\n\nWORLD")

    def test_command_completer_file_mode(self):
        cmd = [
            sys.executable,
            "-c",
            "import sys; print(open(sys.argv[1]).read().lower())",
            "{prompt_file}",
        ]
        completer = CommandCompleter(cmd)
        output = completer("HELLO", "WORLD")
        self.assertEqual(output, "hello\n\nworld")

    def test_command_completer_nonzero_exit_raises_runtime_error(self):
        cmd = [
            sys.executable,
            "-c",
            "import sys; sys.stderr.write('fatal command error'); sys.exit(42)",
        ]
        completer = CommandCompleter(cmd)
        with self.assertRaises(RuntimeError) as cm:
            completer("sys", "user")
        self.assertIn("42", str(cm.exception))
        self.assertIn("fatal command error", str(cm.exception))

    def test_command_completer_temp_file_deleted_on_success_and_failure(self):
        created_paths = []
        orig_mkstemp = tempfile.mkstemp

        def tracking_mkstemp(*args, **kwargs):
            fd, path = orig_mkstemp(*args, **kwargs)
            created_paths.append(path)
            return fd, path

        # Test success cleanup
        tempfile.mkstemp = tracking_mkstemp
        try:
            success_cmd = [sys.executable, "-c", "print('ok')"]
            completer_succ = CommandCompleter(success_cmd)
            completer_succ("sys", "user")

            # Test failure cleanup
            fail_cmd = [sys.executable, "-c", "import sys; sys.exit(1)"]
            completer_fail = CommandCompleter(fail_cmd)
            with self.assertRaises(RuntimeError):
                completer_fail("sys", "user")
        finally:
            tempfile.mkstemp = orig_mkstemp

        self.assertEqual(len(created_paths), 2)
        for p in created_paths:
            self.assertFalse(os.path.exists(p), f"Temp file {p} was not cleaned up!")

    def test_openai_chat_completer_success_and_headers_and_body(self):
        env_key = "TEST_OPENAI_API_KEY_ENV"
        secret_token = "sk-mock-key-xyz-789"
        os.environ[env_key] = secret_token
        try:
            completer = OpenAIChatCompleter(
                base_url=f"http://127.0.0.1:{self.port}",
                model="test-gpt-model",
                api_key_env=env_key,
                temperature=0.3,
                max_tokens=600,
            )
            result = completer("system instructions", "user request")
            self.assertEqual(result, "response from mock server")

            self.assertEqual(len(MockOpenAIHandler.requests_received), 1)
            req = MockOpenAIHandler.requests_received[0]
            self.assertEqual(req["path"], "/chat/completions")
            self.assertEqual(req["headers"].get("Authorization"), f"Bearer {secret_token}")
            self.assertEqual(req["body"]["model"], "test-gpt-model")
            self.assertEqual(req["body"]["temperature"], 0.3)
            self.assertEqual(req["body"]["max_tokens"], 600)
            self.assertEqual(
                req["body"]["messages"],
                [
                    {"role": "system", "content": "system instructions"},
                    {"role": "user", "content": "user request"},
                ],
            )
        finally:
            os.environ.pop(env_key, None)

    def test_openai_chat_completer_http_500_raises_runtime_error(self):
        MockOpenAIHandler.response_code = 500
        MockOpenAIHandler.response_body = b'{"error": "Internal server crash"}'

        completer = OpenAIChatCompleter(
            base_url=f"http://127.0.0.1:{self.port}",
            model="test-gpt-model",
        )
        with self.assertRaises(RuntimeError) as cm:
            completer("sys", "user")
        self.assertIn("500", str(cm.exception))

    def test_openai_chat_completer_error_message_never_leaks_api_key(self):
        MockOpenAIHandler.response_code = 500
        MockOpenAIHandler.response_body = b'{"error": "Internal failure"}'

        env_key = "LEAK_CHECK_KEY"
        secret_key = "CRITICAL_SECRET_TOKEN_NEVER_LEAK"
        os.environ[env_key] = secret_key
        try:
            completer = OpenAIChatCompleter(
                base_url=f"http://127.0.0.1:{self.port}",
                model="test-gpt-model",
                api_key_env=env_key,
            )
            with self.assertRaises(RuntimeError) as cm:
                completer("sys", "user")
            self.assertNotIn(
                secret_key,
                str(cm.exception),
                "API key leaked in exception message!",
            )
        finally:
            os.environ.pop(env_key, None)


if __name__ == "__main__":
    unittest.main()
