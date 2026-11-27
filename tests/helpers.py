"""Test helpers: a seeded store in a temp folder, a deterministic face engine
and a scripted LLM, so every use case can be tested without a camera or Ollama."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from bookorbit import clock
from bookorbit.ai.biometric import BiometricEngine
from bookorbit.ai.llm_client import LLMUnavailable
from bookorbit.app_context import AppContext
from bookorbit.config import Config
from bookorbit.errors import BiometricError
from bookorbit.services.base import Session


def face(person: int, size: int = 64) -> np.ndarray:
    """A fake 'photo'. Pixel (0,0) encodes who is in it:
    0 = no face, 255 = two faces, anything else = that person."""
    img = np.full((size, size, 3), 128, np.uint8)
    img[0, 0] = (person, person, person)
    return img


NO_FACE = face(0)
TWO_FACES = face(255)


class FakeBiometric(BiometricEngine):
    """Same API as BiometricEngine; identity comes from pixel (0,0)."""

    def __init__(self, threshold: float = 0.40):
        self.threshold = threshold
        self.load_error = None

    @property
    def available(self) -> bool:
        return True

    def status_text(self) -> str:
        return "fake engine ready"

    def _code(self, image) -> int:
        return int(image[0, 0, 0])

    def detect(self, image):
        c = self._code(image)
        return [] if c == 0 else ([1, 2] if c == 255 else [1])

    def _vec(self, c: int) -> np.ndarray:
        v = np.zeros(256, np.float32)
        v[c] = 1.0
        v[(c * 7) % 256] += 0.3            # some shared structure, still < threshold across people
        return v / np.linalg.norm(v)

    def single_face_embedding(self, image):
        c = self._code(image)
        if c == 0:
            raise BiometricError("No face found - look at the camera and try again.", "NO_FACE")
        if c == 255:
            raise BiometricError("More than one face found - make sure only your face is visible.", "MULTI_FACE")
        return self._vec(c)

    def verify(self, template, image) -> float:
        c = self._code(image)
        if c == 0:
            raise BiometricError("No face detected - please capture again.", "NO_FACE")
        return self.similarity(template, self._vec(c if c != 255 else 1))


class FakeLLM:
    """Scripted stand-in for LLMClient."""

    def __init__(self, online: bool = True, reply: str = "LLM ANSWER"):
        self.online = online
        self.reply = reply
        self.model = "fake-model"
        self.calls: list[tuple[str, str]] = []

    def available(self, force: bool = False) -> bool:
        return self.online

    def status_text(self) -> str:
        return "Ollama online (fake-model)" if self.online else "Ollama offline"

    def chat(self, system: str, user: str, temperature: float = 0.2) -> str:
        self.calls.append((system, user))
        if not self.online:
            raise LLMUnavailable("The assistant is offline - please try again later.")
        return self.reply(system, user) if callable(self.reply) else self.reply


class NoCamera:
    def available(self):
        return False

    def snapshot(self, wait_s=2.0):
        return None

    def mjpeg(self):
        return iter(())


# person codes used by the seeded demo accounts
FACES = {"admin": 11, "yixin": 12, "alice": 13, "selina": 14, "evan": 15, "zakiah": 16, "ibrahim": 17}


_TEMPLATE: dict = {}


def _seeded_template() -> "Path":
    """Seed once per test run, then copy the folder for every test (fast)."""
    import tempfile
    from pathlib import Path

    import seed as seed_module
    if "dir" not in _TEMPLATE:
        d = Path(tempfile.mkdtemp(prefix="bookorbit-seed-")) / "data"
        cfg = Config()
        cfg.data_dir = d
        ctx = AppContext(cfg, biometric=FakeBiometric(), llm=FakeLLM(online=False), camera=NoCamera())
        seed_module.seed(cfg, quiet=True, ctx=ctx)
        for uname, code in FACES.items():
            u = ctx.users.by_username(uname)
            ctx.auth.enroll(u["user_ID"], [face(code)])
        clock.set_now(None)
        _TEMPLATE["dir"] = d
    return _TEMPLATE["dir"]


def make_ctx(tmp_path, llm_online: bool = False, seed_data: bool = True, llm=None) -> AppContext:
    import shutil
    cfg = Config()
    cfg.data_dir = tmp_path / "data"
    if seed_data:
        shutil.copytree(_seeded_template(), cfg.data_dir)
    ctx = AppContext(cfg, biometric=FakeBiometric(), llm=llm or FakeLLM(online=llm_online), camera=NoCamera())
    clock.set_now(None)
    return ctx


def session_for(ctx: AppContext, username: str) -> Session:
    u = ctx.users.by_username(username)
    return Session(user_ID=u["user_ID"], role=u["role"], wallet_only=u["status"] == "SUSPENDED")


def book_id(ctx: AppContext, title: str) -> str:
    for b in ctx.store.read_all("books"):
        if b["title"] == title:
            return b["book_ID"]
    raise KeyError(title)
