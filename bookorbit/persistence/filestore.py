"""Local text-file storage (spec note 3: "no need for a database").

Each entity lives in its own ``data/<name>.txt`` file, one JSON object per
line (JSON Lines). Writes are atomic (write a temp file, then rename) and
guarded by one re-entrant lock, so a crash or two clicks at once can never
leave a half-written file.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Callable, Iterable

from ..errors import StorageError

# Every file the system uses (Section 4.1 "Global Data" of the design report).
FILES = (
    "users", "books", "transactions", "purchases", "reviews", "warnings",
    "taboo_words", "biometrics", "login_attempts", "browse_history",
    "chat_log", "reading_progress", "status_changes", "admin_actions",
    "rag_chunks",
)


class FileStore:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        # Test hook: when set, the next write raises (used to test "If saving fails").
        self.fail_next_write: bool = False

    # -- paths ----------------------------------------------------------------
    def path(self, name: str) -> Path:
        if name not in FILES:
            raise StorageError(f"Unknown data file '{name}'")
        return self.data_dir / f"{name}.txt"

    def ensure_files(self) -> None:
        for name in FILES:
            p = self.path(name)
            if not p.exists():
                p.write_text("", encoding="utf-8")

    # -- reads ----------------------------------------------------------------
    def read_all(self, name: str) -> list[dict]:
        p = self.path(name)
        with self.lock:
            if not p.exists():
                return []
            out = []
            with p.open(encoding="utf-8") as fh:
                for line_no, line in enumerate(fh, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        raise StorageError(f"{p.name} line {line_no} is corrupt: {exc}") from exc
            return out

    def find(self, name: str, **match) -> dict | None:
        for rec in self.read_all(name):
            if all(rec.get(k) == v for k, v in match.items()):
                return rec
        return None

    def filter(self, name: str, pred: Callable[[dict], bool] | None = None, **match) -> list[dict]:
        out = []
        for rec in self.read_all(name):
            if all(rec.get(k) == v for k, v in match.items()) and (pred is None or pred(rec)):
                out.append(rec)
        return out

    # -- writes ---------------------------------------------------------------
    def _check_fail(self) -> None:
        if self.fail_next_write:
            self.fail_next_write = False
            raise StorageError("Simulated disk failure")

    def append(self, name: str, record: dict) -> dict:
        with self.lock:
            self._check_fail()
            p = self.path(name)
            with p.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            return record

    def write_all(self, name: str, records: Iterable[dict]) -> None:
        with self.lock:
            self._check_fail()
            p = self.path(name)
            fd, tmp = tempfile.mkstemp(dir=self.data_dir, prefix=f".{name}.", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    for rec in records:
                        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, p)
            except BaseException:
                if os.path.exists(tmp):
                    os.unlink(tmp)
                raise

    def update(self, name: str, key: str, value, changes: dict | Callable[[dict], None]) -> dict:
        """Change the record whose ``key`` equals ``value``; returns the new record."""
        with self.lock:
            records = self.read_all(name)
            for rec in records:
                if rec.get(key) == value:
                    if callable(changes):
                        changes(rec)
                    else:
                        rec.update(changes)
                    self.write_all(name, records)
                    return rec
            raise StorageError(f"No record with {key}={value!r} in {name}.txt")

    def delete(self, name: str, pred: Callable[[dict], bool]) -> int:
        with self.lock:
            records = self.read_all(name)
            keep = [r for r in records if not pred(r)]
            if len(keep) != len(records):
                self.write_all(name, keep)
            return len(records) - len(keep)

    def upsert(self, name: str, keys: dict, record: dict) -> dict:
        with self.lock:
            records = self.read_all(name)
            for i, rec in enumerate(records):
                if all(rec.get(k) == v for k, v in keys.items()):
                    rec.update(record)
                    self.write_all(name, records)
                    return rec
            new = {**keys, **record}
            self.append(name, new)
            return new

    def next_id(self, name: str, key: str, prefix: str, width: int = 4) -> str:
        with self.lock:
            best = 0
            for rec in self.read_all(name):
                v = str(rec.get(key, ""))
                if v.startswith(prefix):
                    try:
                        best = max(best, int(v[len(prefix):]))
                    except ValueError:
                        pass
            return f"{prefix}{best + 1:0{width}d}"
