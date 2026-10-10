"""LLM completer backends.

Provides backend implementations adhering to the Completer signature
(system: str, user: str) -> str:
- ScriptedCompleter: for deterministic unit testing.
- CommandCompleter: runs a subprocess CLI (stdin or temp prompt file).
- OpenAIChatCompleter: calls an OpenAI-compatible REST API via urllib.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request
from typing import Sequence


class ScriptedCompleter:
    """Pre-programmed response completer for tests."""

    def __init__(self, responses: Sequence[str | Exception]) -> None:
        self._responses = list(responses)
        self._index = 0
        self.calls: list[tuple[str, str]] = []

    def __call__(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if self._index >= len(self._responses):
            raise IndexError("No more scripted responses available")
        resp = self._responses[self._index]
        self._index += 1
        if isinstance(resp, Exception):
            raise resp
        if isinstance(resp, type) and issubclass(resp, Exception):
            raise resp()
        return str(resp)


class CommandCompleter:
    """Executes a command-line program to generate a completion."""

    def __init__(self, argv: Sequence[str], timeout: float = 180.0) -> None:
        self.argv = list(argv)
        self.timeout = timeout

    def __call__(self, system: str, user: str) -> str:
        prompt_text = system + "\n\n" + user
        fd, temp_path = tempfile.mkstemp(prefix="slg_prompt_", suffix=".txt", text=True)
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(prompt_text)

            has_file_placeholder = any("{prompt_file}" in arg for arg in self.argv)
            if has_file_placeholder:
                cmd = [arg.replace("{prompt_file}", temp_path) for arg in self.argv]
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
            else:
                proc = subprocess.run(
                    self.argv,
                    input=prompt_text,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )

            if proc.returncode != 0:
                stderr_tail = (proc.stderr or "")[-300:]
                raise RuntimeError(
                    f"Command failed with exit code {proc.returncode}: {stderr_tail}"
                )
            return proc.stdout.strip()
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


class OpenAIChatCompleter:
    """Invokes an OpenAI-compatible /chat/completions endpoint using standard library urllib."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key_env: str | None = None,
        timeout: float = 120.0,
        temperature: float = 0.2,
        max_tokens: int = 900,
    ) -> None:
        self.base_url = base_url
        self.model = model
        self.api_key_env = api_key_env
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens

    def __call__(self, system: str, user: str) -> str:
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}

        api_key = os.environ.get(self.api_key_env) if self.api_key_env else None
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        def _clean(msg: str) -> str:
            if api_key and api_key in msg:
                return msg.replace(api_key, "[REDACTED]")
            return msg

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(_clean(f"HTTP error {exc.code}: {exc.reason}")) from None
        except urllib.error.URLError as exc:
            raise RuntimeError(_clean(f"Network error: {exc.reason}")) from None
        except Exception as exc:
            raise RuntimeError(_clean(f"Request failed: {type(exc).__name__}: {exc}")) from None

        try:
            res_json = json.loads(body)
            content = res_json["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise ValueError("Response message content is not a string")
            return content
        except Exception as exc:
            raise RuntimeError(_clean(f"Invalid response JSON structure: {exc}")) from None
