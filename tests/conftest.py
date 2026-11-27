import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bookorbit import clock  # noqa: E402
from tests.helpers import make_ctx  # noqa: E402


@pytest.fixture
def ctx(tmp_path):
    c = make_ctx(tmp_path)
    yield c
    clock.set_now(None)


@pytest.fixture
def ctx_llm(tmp_path):
    c = make_ctx(tmp_path, llm_online=True)
    yield c
    clock.set_now(None)
