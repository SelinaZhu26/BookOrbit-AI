"""LLMClient (Ollama) - talks to a local Ollama server (spec note 2).

Nothing is sent outside the computer: Ollama runs at http://127.0.0.1:11434.
If Ollama is not installed or not running, ``available()`` is False and the
callers fall back to the offline behaviour written in each use case.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


class LLMUnavailable(Exception):
    pass


class LLMClient:
    def __init__(self, base_url: str, model: str, timeout_s: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        self._status: tuple[float, bool, str] = (0.0, False, "not checked")

    def _request(self, path: str, payload: dict | None, timeout: float):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(self.base_url + path, data=data,
                                     headers={"Content-Type": "application/json"},
                                     method="POST" if data else "GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def available(self, force: bool = False) -> bool:
        checked_at, ok, _ = self._status
        if not force and time.time() - checked_at < 15:
            return ok
        try:
            tags = self._request("/api/tags", None, timeout=2.0)
            names = [m.get("name", "") for m in tags.get("models", [])]
            base = self.model.split(":")[0]
            has_model = any(n == self.model or n.split(":")[0] == base for n in names)
            msg = f"Ollama online ({self.model})" if has_model else \
                f"Ollama online but model '{self.model}' is not pulled (run: ollama pull {self.model})"
            self._status = (time.time(), has_model, msg)
        except (urllib.error.URLError, OSError, ValueError, TimeoutError):
            self._status = (time.time(), False, "Ollama offline (start it with `ollama serve`)")
        return self._status[1]

    def status_text(self) -> str:
        self.available()
        return self._status[2]

    def chat(self, system: str, user: str, temperature: float = 0.2) -> str:
        if not self.available():
            raise LLMUnavailable("The assistant is offline - please try again later.")
        payload = {"model": self.model, "stream": False,
                   "options": {"temperature": temperature},
                   "messages": [{"role": "system", "content": system},
                                {"role": "user", "content": user}]}
        try:
            out = self._request("/api/chat", payload, timeout=self.timeout_s)
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
            self._status = (time.time(), False, "Ollama offline (no reply)")
            raise LLMUnavailable("The assistant is offline - please try again later.") from exc
        text = (out.get("message") or {}).get("content", "").strip()
        if not text:
            raise LLMUnavailable("The assistant did not answer - please try again later.")
        return text
