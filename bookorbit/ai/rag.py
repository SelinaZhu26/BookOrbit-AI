"""RAGRetriever - retrieval over local store files (spec item 9).

rag_chunks.txt holds the chunks; each chunk has a scope:
  PUBLIC     - store/team information from data/policies.txt
  BOOK_TEXT  - passages of a book's public-domain text (book_ID set)
Catalog facts (titles, prices, ratings) are read live from books.txt so they
are never stale. Ranking is BM25 (no external service needed), so "is this
question about our local files?" can be answered even when the LLM is off.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from ..persistence.filestore import FileStore
from .texts import tokenize


@dataclass
class Hit:
    chunk: dict
    score: float
    coverage: float          # share of the question's content words found in the chunk


class _BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.4, b: float = 0.75):
        self.docs = docs
        self.k1, self.b = k1, b
        self.N = len(docs)
        self.avgdl = (sum(len(d) for d in docs) / self.N) if self.N else 0
        self.tf = [Counter(d) for d in docs]
        df = Counter()
        for d in self.tf:
            df.update(d.keys())
        self.idf = {t: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for t, n in df.items()}
        self.postings = defaultdict(list)
        for i, d in enumerate(self.tf):
            for t in d:
                self.postings[t].append(i)

    def scores(self, query: list[str], allowed: set[int] | None = None) -> dict[int, float]:
        out: dict[int, float] = defaultdict(float)
        for t in set(query):
            idf = self.idf.get(t)
            if idf is None:
                continue
            for i in self.postings[t]:
                if allowed is not None and i not in allowed:
                    continue
                f = self.tf[i][t]
                dl = len(self.docs[i])
                out[i] += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return out


class RAGRetriever:
    CHUNK_WORDS = 160
    OVERLAP = 40

    def __init__(self, store: FileStore):
        self.store = store
        self._sig = None
        self._chunks: list[dict] = []
        self._bm25: _BM25 | None = None

    # ------------------------------------------------------------ indexing
    @staticmethod
    def policy_chunks(policy_text: str) -> list[dict]:
        chunks, title, buf = [], "Store information", []
        for line in policy_text.splitlines():
            if line.startswith("## "):
                if "".join(buf).strip():
                    chunks.append({"title": title, "text": " ".join(" ".join(buf).split())})
                title, buf = line[3:].strip(), []
            elif not line.startswith("# "):
                buf.append(line)
        if "".join(buf).strip():
            chunks.append({"title": title, "text": " ".join(" ".join(buf).split())})
        return chunks

    def _book_chunks(self, book: dict, text: str) -> list[dict]:
        words = text.split()
        step = self.CHUNK_WORDS - self.OVERLAP
        out = []
        for i in range(0, max(1, len(words) - self.OVERLAP), step):
            piece = " ".join(words[i:i + self.CHUNK_WORDS])
            if len(piece.split()) < 20:
                continue
            out.append({"title": book["title"], "text": piece})
        return out

    def rebuild(self, policy_text: str, books_with_text: list[tuple[dict, str]]) -> int:
        records, n = [], 0
        for c in self.policy_chunks(policy_text):
            n += 1
            records.append({"chunk_ID": f"C-{n:06d}", "scope": "PUBLIC", "book_ID": None, **c})
        for book, text in books_with_text:
            for c in self._book_chunks(book, text):
                n += 1
                records.append({"chunk_ID": f"C-{n:06d}", "scope": "BOOK_TEXT",
                                "book_ID": book["book_ID"], **c})
        self.store.write_all("rag_chunks", records)
        self._sig = None
        return len(records)

    def index_book(self, book: dict, text: str) -> int:
        with self.store.lock:
            existing = self.store.read_all("rag_chunks")
            existing = [c for c in existing if c.get("book_ID") != book["book_ID"]]
            n = max([int(c["chunk_ID"][2:]) for c in existing] or [0])
            new = []
            for c in self._book_chunks(book, text):
                n += 1
                new.append({"chunk_ID": f"C-{n:06d}", "scope": "BOOK_TEXT", "book_ID": book["book_ID"], **c})
            self.store.write_all("rag_chunks", existing + new)
        self._sig = None
        return len(new)

    def replace_policies(self, policy_text: str) -> None:
        with self.store.lock:
            rest = [c for c in self.store.read_all("rag_chunks") if c.get("scope") != "PUBLIC"]
            n = max([int(c["chunk_ID"][2:]) for c in rest] or [0])
            pub = []
            for c in self.policy_chunks(policy_text):
                n += 1
                pub.append({"chunk_ID": f"C-{n:06d}", "scope": "PUBLIC", "book_ID": None, **c})
            self.store.write_all("rag_chunks", pub + rest)
        self._sig = None

    # ------------------------------------------------------------- search
    def _ensure_index(self) -> None:
        p = self.store.path("rag_chunks")
        sig = (p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else None
        if sig != self._sig:
            self._chunks = self.store.read_all("rag_chunks")
            self._bm25 = _BM25([tokenize(c["title"] + " " + c["text"]) for c in self._chunks])
            self._sig = sig

    def search(self, query: str, scopes: set[str], book_ID: str | None = None,
               k: int = 3) -> list[Hit]:
        self._ensure_index()
        q = tokenize(query)
        if not q or not self._chunks:
            return []
        allowed = {i for i, c in enumerate(self._chunks)
                   if c["scope"] in scopes and (book_ID is None or c.get("book_ID") == book_ID)}
        scores = self._bm25.scores(q, allowed)
        qset = set(q)
        hits = []
        for i, s in sorted(scores.items(), key=lambda kv: -kv[1])[: k * 4]:
            words = set(self._bm25.docs[i])
            cov = len(qset & words) / len(qset)
            hits.append(Hit(self._chunks[i], s, cov))
        hits.sort(key=lambda h: (-(h.coverage >= 0.5), -h.score))
        return hits[:k]

    @staticmethod
    def is_relevant(hits: list[Hit], min_coverage: float = 0.5, min_score: float = 2.0) -> bool:
        return bool(hits) and hits[0].coverage >= min_coverage and hits[0].score >= min_score

    @staticmethod
    def best_sentences(query: str, text: str, n: int = 3) -> str:
        """Extractive answer used when the LLM is offline."""
        q = set(tokenize(query))
        sents = re.split(r"(?<=[.!?])\s+", text)
        ranked = sorted(range(len(sents)), key=lambda i: -len(q & set(tokenize(sents[i]))))
        keep = sorted(ranked[:n])
        return " ".join(sents[i] for i in keep).strip()
