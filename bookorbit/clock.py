"""Time helpers. Tests can freeze time with ``set_now``."""
from __future__ import annotations

from datetime import datetime, timedelta

_frozen: datetime | None = None


def now() -> datetime:
    return _frozen or datetime.now().replace(microsecond=0)


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def set_now(value: datetime | None) -> None:
    global _frozen
    _frozen = value


def advance(**kwargs) -> None:
    global _frozen
    _frozen = now() + timedelta(**kwargs)
