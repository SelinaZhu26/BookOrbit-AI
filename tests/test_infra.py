"""Infrastructure: text-file store, Ollama client (against a fake Ollama
server), chapter splitting, money parsing."""
import json
import threading
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from bookorbit.ai.llm_client import LLMClient, LLMUnavailable
from bookorbit.ai.texts import split_chapters
from bookorbit.errors import StorageError
from bookorbit.money import parse_amount
from bookorbit.persistence.filestore import FileStore


def test_filestore_roundtrip_update_and_atomicity(tmp_path):
    fs = FileStore(tmp_path)
    fs.ensure_files()
    fs.append("users", {"user_ID": "U-0001", "n": 1})
    fs.append("users", {"user_ID": "U-0002", "n": 2})
    fs.update("users", "user_ID", "U-0002", {"n": 5})
    assert [u["n"] for u in fs.read_all("users")] == [1, 5]
    assert fs.next_id("users", "user_ID", "U-") == "U-0003"
    fs.fail_next_write = True
    with pytest.raises(StorageError):
        fs.update("users", "user_ID", "U-0001", {"n": 9})
    assert [u["n"] for u in fs.read_all("users")] == [1, 5]      # unchanged
    assert not list(tmp_path.glob("*.tmp"))


def test_filestore_reports_corrupt_line(tmp_path):
    fs = FileStore(tmp_path)
    fs.path("books").write_text('{"ok": 1}\n{broken\n')
    with pytest.raises(StorageError, match="line 2"):
        fs.read_all("books")


def test_filestore_rejects_unknown_files(tmp_path):
    with pytest.raises(StorageError):
        FileStore(tmp_path).read_all("../etc/passwd")


@pytest.mark.parametrize("text,ok", [("10", "10.00"), ("$1,234.50", "1234.50"), ("0.01", "0.01")])
def test_parse_amount(text, ok):
    assert parse_amount(text) == Decimal(ok)


class _FakeOllama(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._json({"models": [{"name": "llama3.2:1b"}]})

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append(req)
        self._json({"message": {"role": "assistant", "content": "Paris is the capital of France."}})


@pytest.fixture
def fake_ollama():
    srv = HTTPServer(("127.0.0.1", 0), _FakeOllama)
    srv.requests = []
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv
    srv.shutdown()


def test_llm_client_talks_to_ollama_api(fake_ollama):
    c = LLMClient(f"http://127.0.0.1:{fake_ollama.server_port}", "llama3.2:1b")
    assert c.available(force=True) and "online" in c.status_text()
    assert c.chat("sys", "capital of France?") == "Paris is the capital of France."
    req = fake_ollama.requests[-1]
    assert req["model"] == "llama3.2:1b" and req["stream"] is False
    assert req["messages"][0] == {"role": "system", "content": "sys"}


def test_llm_client_missing_model_counts_as_unavailable(fake_ollama):
    c = LLMClient(f"http://127.0.0.1:{fake_ollama.server_port}", "mistral")
    assert not c.available(force=True) and "ollama pull mistral" in c.status_text()


def test_llm_client_offline():
    c = LLMClient("http://127.0.0.1:9", "llama3.2:1b")
    assert not c.available(force=True)
    with pytest.raises(LLMUnavailable):
        c.chat("s", "u")


def test_chatbot_end_to_end_with_real_client_and_fake_ollama(tmp_path, fake_ollama):
    from bookorbit.services.base import Session
    from tests.helpers import make_ctx
    llm = LLMClient(f"http://127.0.0.1:{fake_ollama.server_port}", "llama3.2:1b")
    ctx = make_ctx(tmp_path, llm=llm)
    a = ctx.chatbot.ask(Session(user_ID=ctx.users.by_username("alice")["user_ID"], role="RC"),
                        "What is the capital of France?")
    assert a.source == "LLM" and "Paris" in a.text and "Ollama" in a.label


def test_split_chapters_headings_and_fallback():
    text = "\n\n".join(f"CHAPTER {r}\n\n" + ("word " * 100) for r in ("I", "II", "III"))
    ch = split_chapters(text)
    assert [c["title"] for c in ch] == ["Chapter I", "Chapter II", "Chapter III"]
    plain = "\n\n".join("para " * 500 for _ in range(20))
    parts = split_chapters(plain, words_per_part=2000)
    assert parts[0]["title"] == "Part 1" and len(parts) == 5
