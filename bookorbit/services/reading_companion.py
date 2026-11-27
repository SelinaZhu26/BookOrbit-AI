"""ReadingCompanion - UC-14 Use Smart Reading Companion (the team's creative
feature, spec item 10).

The reader opens a public-domain book chapter by chapter. Next to the text,
the companion can Summarize, Explain a selected passage, Define a word,
Quiz the reader (3 questions, answers hidden until answered) or answer a
free question. Every AI answer is grounded in passages of THIS book only
(retrieved with the RAG index). With the LLM offline, Summarize, Quiz and
Ask still work with extractive/offline methods; Explain and Define need the LLM.
"""
from __future__ import annotations

import json
import re
import uuid
from functools import lru_cache

from .. import clock
from ..ai.llm_client import LLMClient, LLMUnavailable
from ..ai.rag import RAGRetriever
from ..ai.texts import cloze_quiz, extractive_summary, paragraphs, split_chapters
from ..errors import NotFoundError, PermissionDenied, ValidationError
from .base import ServiceBase, Session
from .catalog_service import CatalogService
from .purchase_service import PurchaseService

NOT_AVAILABLE = "The Reading Companion isn't available for this book."
BUY_TO_CONTINUE = "Buy the book to keep reading."
OFFLINE = "AI features are offline - the text stays readable. (Start Ollama to use this button.)"


class ReadingCompanion(ServiceBase):
    def __init__(self, store, config, catalog: CatalogService, purchases: PurchaseService,
                 rag: RAGRetriever, llm: LLMClient):
        super().__init__(store, config)
        self.catalog = catalog
        self.purchases = purchases
        self.rag = rag
        self.llm = llm
        self._chapters = lru_cache(maxsize=32)(self._load_chapters)
        self.quizzes: dict[str, dict] = {}

    def _load_chapters(self, book_ID: str, mtime: float) -> list[dict]:
        book = self.catalog.get(book_ID)
        text = self.catalog.book_text(book)
        return split_chapters(text) if text else []

    def chapters(self, book: dict) -> list[dict]:
        if not book.get("text_Path"):
            return []
        p = self.config.data_dir / book["text_Path"]
        if not p.exists():
            return []
        return self._chapters(book["book_ID"], p.stat().st_mtime)

    def _check(self, session: Session, book_ID: str) -> tuple[dict, list[dict], bool]:
        if not session.is_customer:
            raise PermissionDenied("Sign in as a customer to use the Reading Companion.")
        book = self.catalog.get(book_ID)
        chapters = self.chapters(book)
        if not chapters:
            raise NotFoundError(NOT_AVAILABLE)
        owned = self.purchases.owns(session.user_ID, book_ID)
        return book, chapters, owned

    def progress(self, user_ID: str, book_ID: str) -> dict | None:
        return self.store.find("reading_progress", user_ID=user_ID, book_ID=book_ID)

    def latest(self, user_ID: str) -> dict | None:
        recs = sorted(self.store.filter("reading_progress", user_ID=user_ID),
                      key=lambda r: r["updated_At"], reverse=True)
        for r in recs:
            b = self.store.find("books", book_ID=r["book_ID"])
            if b:
                chapters = self.chapters(b)
                idx = min(r["chapter"], len(chapters)) - 1 if chapters else 0
                return {**r, "book": b, "chapter_title": chapters[idx]["title"] if chapters else ""}
        return None

    def _save(self, session: Session, book_ID: str, chapter: int, action: str) -> None:
        self.store.upsert("reading_progress", {"user_ID": session.user_ID, "book_ID": book_ID},
                          {"chapter": chapter, "last_Action": action, "updated_At": clock.now_iso()})

    # ------------------------------------------------------------ reading
    def open(self, session: Session, book_ID: str, chapter: int | None = None) -> dict:
        book, chapters, owned = self._check(session, book_ID)
        if chapter is None:
            prog = self.progress(session.user_ID, book_ID)
            chapter = prog["chapter"] if prog else 1
        chapter = min(max(1, int(chapter)), len(chapters))
        locked = chapter > 1 and not owned
        view = {"book": book, "owned": owned, "chapter": chapter, "count": len(chapters),
                "titles": [c["title"] for c in chapters], "locked": locked,
                "paragraphs": [] if locked else paragraphs(chapters[chapter - 1]["text"]),
                "message": BUY_TO_CONTINUE if locked else ""}
        if not locked:
            self._save(session, book_ID, chapter, "READ")
        return view

    # ------------------------------------------------------------ actions
    def act(self, session: Session, book_ID: str, chapter: int, action: str,
            selection: str = "", question: str = "") -> dict:
        book, chapters, owned = self._check(session, book_ID)
        chapter = min(max(1, int(chapter)), len(chapters))
        if chapter > 1 and not owned:
            return {"ok": False, "message": BUY_TO_CONTINUE, "buy": True}
        selection = (selection or "").strip()[:2000]
        question = (question or "").strip()[:300]
        text = chapters[chapter - 1]["text"]
        if action in ("explain", "define") and not selection:
            return {"ok": False, "message": "Select a passage first" if action == "explain"
                    else "Select a word first"}
        if action == "ask" and not question:
            return {"ok": False, "message": "Type a question first"}
        if action not in ("summarize", "explain", "define", "quiz", "ask"):
            raise ValidationError("Unknown action")

        llm_ok = self.llm.available()
        if not llm_ok and action in ("explain", "define"):
            return {"ok": False, "message": OFFLINE, "offline": True}

        result = getattr(self, f"_{action}")(book, chapter, text, selection, question, llm_ok)
        self._save(session, book_ID, chapter, action.upper())
        return {"ok": True, **result}

    def _passages(self, book: dict, query: str, k: int = 3) -> list[str]:
        return [h.chunk["text"] for h in self.rag.search(query, {"BOOK_TEXT"}, book_ID=book["book_ID"], k=k)]

    def _summarize(self, book, chapter, text, selection, question, llm_ok):
        source = selection or text
        if llm_ok:
            try:
                out = self.llm.chat(f"You help a reader of “{book['title']}” by {book['author']}. "
                                    "Summarize the given text in 4-6 plain sentences. Use only the text.",
                                    source[:9000])
                return {"title": "Summary", "text": out, "source": "LLM + this book's text"}
            except LLMUnavailable:
                pass
        return {"title": "Summary", "text": extractive_summary(source, 5),
                "source": "Key sentences from this chapter (offline summary)"}

    def _explain(self, book, chapter, text, selection, question, llm_ok):
        ctx = self._passages(book, selection, 2)
        out = self.llm.chat(f"You explain passages of “{book['title']}” by {book['author']} to a modern "
                            "reader in plain English (max 5 sentences). Use the nearby passages for context.",
                            "Nearby passages:\n" + "\n---\n".join(ctx) + f"\n\nExplain this passage:\n{selection}")
        return {"title": "Explanation", "text": out, "source": "LLM + passages from this book (RAG)"}

    def _define(self, book, chapter, text, selection, question, llm_ok):
        word = selection.split()[0].strip(".,;:!?\"'()") if selection else ""
        usage = next((s for s in re.split(r"(?<=[.!?])\s+", text) if re.search(rf"\b{re.escape(word)}\b", s, re.I)), "")
        out = self.llm.chat("Define the word as it is used in the sentence, in 1-2 sentences. "
                            "Mention if the meaning is old-fashioned.",
                            f"Word: {word}\nSentence from “{book['title']}”: {usage[:600]}")
        return {"title": f"Definition: {word}", "text": out, "source": "LLM + this book's sentence"}

    def _ask(self, book, chapter, text, selection, question, llm_ok):
        ctx = self._passages(book, question, 3)
        if llm_ok:
            try:
                out = self.llm.chat(f"Answer questions about “{book['title']}” using ONLY these "
                                    "passages from the book. If they don't contain the answer, say so.",
                                    "Passages:\n" + "\n---\n".join(ctx) + f"\n\nQuestion: {question}")
                return {"title": "Answer", "text": out, "source": "LLM + passages from this book (RAG)"}
            except LLMUnavailable:
                pass
        if not ctx:
            return {"title": "Answer", "text": "I couldn't find that in this book.", "source": "RAG"}
        return {"title": "Most relevant passage", "text": "“" + self.rag.best_sentences(question, ctx[0], 4) + "”",
                "source": "Passage found with RAG (LLM offline)"}

    def _quiz(self, book, chapter, text, selection, question, llm_ok):
        items = None
        source = "Fill-in-the-blank questions from this chapter (offline)"
        if llm_ok:
            try:
                raw = self.llm.chat("Write exactly 3 multiple-choice questions about the chapter. Reply with "
                                    "JSON only: [{\"question\":..., \"options\":[4 strings], \"answer_index\":0-3}]",
                                    text[:9000], )
                m = re.search(r"\[.*\]", raw, re.S)
                data = json.loads(m.group(0)) if m else []
                items = [{"question": str(d["question"]), "options": [str(o) for o in d["options"]][:4],
                          "answer_index": int(d["answer_index"])} for d in data
                         if len(d.get("options", [])) >= 4 and 0 <= int(d.get("answer_index", -1)) < 4][:3]
                source = "LLM + this chapter"
                if len(items) < 3:
                    items = None
            except (LLMUnavailable, ValueError, KeyError, TypeError):
                items = None
        if items is None:
            items = cloze_quiz(text, 3, seed=hash((book["book_ID"], chapter)) & 0xFFFF)
        if not items:
            return {"title": "Quiz", "text": "This chapter is too short for a quiz.", "source": source}
        quiz_ID = uuid.uuid4().hex[:12]
        self.quizzes[quiz_ID] = {"items": items, "book_ID": book["book_ID"]}
        # answers stay on the server until the reader answers
        public = [{"question": q["question"], "options": q["options"]} for q in items]
        return {"title": "Quiz me", "quiz_ID": quiz_ID, "quiz": public, "source": source}

    def check_answer(self, quiz_ID: str, index: int, choice: int) -> dict:
        quiz = self.quizzes.get(quiz_ID)
        if not quiz or not 0 <= index < len(quiz["items"]):
            raise NotFoundError("This quiz has expired - press Quiz me again.")
        item = quiz["items"][index]
        correct = int(choice) == item["answer_index"]
        return {"correct": correct, "answer_index": item["answer_index"],
                "answer": item["options"][item["answer_index"]]}
