"""CatalogService - UC-04 Browse and Search Books, UC-05 View Book Details and
Reviews, UC-15 Add New Books (book form, cover and text indexing)."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import cv2
import numpy as np

from .. import clock
from ..ai.covers import CoverIndex
from ..ai.rag import RAGRetriever
from ..ai.texts import strip_title_line
from ..errors import BiometricError, NotFoundError, ValidationError
from ..money import D, to_store
from .base import ServiceBase, Session, log_admin, require_role

SEARCH_FIELDS = ("title", "author", "keyword", "year")
SORTS = {
    "title": (lambda b: b["title"].lower(), False),
    "author": (lambda b: b["author"].lower(), False),
    "year": (lambda b: b["pub_Year"], False),
    "price": (lambda b: b["price"], False),
    "rating": (lambda b: b["weighted_Avg"], True),
    "popular": (lambda b: b["browse_Count"] + 3 * b["purchase_Count"], True),
}


@dataclass
class SearchResult:
    books: list[dict]
    total: int
    page: int
    pages: int
    errors: dict = field(default_factory=dict)
    message: str = ""
    similarities: dict = field(default_factory=dict)


class CatalogService(ServiceBase):
    def __init__(self, store, config, covers: CoverIndex, rag: RAGRetriever):
        super().__init__(store, config)
        self.covers = covers
        self.rag = rag

    # ---------------------------------------------------------------- reads
    def all_books(self) -> list[dict]:
        return self.store.read_all("books")

    def get(self, book_ID: str) -> dict:
        b = self.store.find("books", book_ID=book_ID)
        if not b:
            raise NotFoundError("Book unavailable")
        return b

    def categories(self) -> list[str]:
        return sorted({b["category"] for b in self.all_books()})

    def authors(self) -> list[str]:
        return sorted({b["author"] for b in self.all_books()})

    # ================================================================ UC-04
    def search(self, category: str = "", query: str = "", field: str = "title",
               year_from: str = "", year_to: str = "", sort: str = "title",
               page: int = 1) -> SearchResult:
        books = self.all_books()
        errors: dict[str, str] = {}
        if category:
            books = [b for b in books if b["category"].lower() == category.lower()]
        q = (query or "").strip()
        yf, yt = (year_from or "").strip(), (year_to or "").strip()
        if field == "year" and q and not (yf or yt):
            m = re.fullmatch(r"\s*(\d{1,4})\s*(?:[-–]\s*(\d{1,4}))?\s*", q.replace(" to ", "-"))
            if m:
                yf, yt = m.group(1), m.group(2) or m.group(1)
            else:
                errors["year"] = "Enter a year or a range like 1990-2000"
        if (yf or yt) and not errors:
            try:
                lo = int(yf) if yf else -10000
                hi = int(yt) if yt else 10000
                if lo > hi:
                    raise ValueError
                books = [b for b in books if lo <= int(b["pub_Year"]) <= hi]
            except ValueError:
                errors["year"] = "The year range is not valid"
        if errors:
            return SearchResult([], 0, 1, 1, errors=errors, message="The year range is not valid")
        if q and field != "year":
            ql = q.lower()

            def hay(b):
                if field == "author":
                    return b["author"].lower()
                if field == "keyword":
                    return " ".join([b["title"], b["author"], b["category"], b["description"],
                                     " ".join(b.get("keywords", []))]).lower()
                return b["title"].lower()
            terms = ql.split()
            books = [b for b in books if all(t in hay(b) for t in terms)]
        key, rev = SORTS.get(sort, SORTS["title"])
        books.sort(key=key, reverse=rev)
        if q and field in ("title", "author") and sort == "title":
            books.sort(key=lambda b: 0 if b[field].lower() == q.lower() else 1)   # exact matches first
        total = len(books)
        size = self.config.page_size
        pages = max(1, math.ceil(total / size))
        page = min(max(1, int(page or 1)), pages)
        return SearchResult(books[(page - 1) * size: page * size], total, page, pages,
                            message="" if total else "No books found")

    def cover_search(self, data: bytes) -> SearchResult:
        if not self.covers.available:
            raise BiometricError("Cover search is unavailable - use text search", "COVER_OFF")
        arr = np.frombuffer(data or b"", np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR) if arr.size else None
        if img is None:
            raise BiometricError("Please choose a JPG or PNG image", "BAD_IMAGE")
        hits = self.covers.search(img, self.config.cover_top_k, self.config.cover_min_similarity)
        books = []
        sims = {}
        for book_ID, sim in hits:
            b = self.store.find("books", book_ID=book_ID)
            if b:
                books.append(b)
                sims[book_ID] = sim
        return SearchResult(books, len(books), 1, 1, similarities=sims,
                            message="" if books else "No books found")

    # ================================================================ UC-05
    def view(self, book_ID: str, session: Session) -> dict:
        """Load the book, add one view and record it for RC/VC."""
        with self.store.lock:
            book = self.get(book_ID)
            book = self.store.update("books", "book_ID", book_ID,
                                     lambda b: b.__setitem__("browse_Count", b["browse_Count"] + 1))
            if session.is_customer:
                self.store.append("browse_history", {
                    "event_ID": self.store.next_id("browse_history", "event_ID", "E-", 6),
                    "user_ID": session.user_ID, "book_ID": book_ID, "action": "VIEW",
                    "created_At": clock.now_iso()})
        return book

    def display_price(self, book: dict, role: str) -> dict:
        price = D(book["price"])
        if role == "VC":
            disc = D(price * D(self.config.vip_discount))
            return {"list": price, "discount": disc, "final": price - disc, "vip": True}
        return {"list": price, "discount": D(0), "final": price, "vip": False}

    def book_text(self, book: dict) -> str | None:
        if not book.get("text_Path"):
            return None
        p = self.config.data_dir / book["text_Path"]
        if not p.exists():
            return None
        return strip_title_line(p.read_text(encoding="utf-8"))

    # ================================================================ UC-15
    def add_book(self, session: Session, form: dict, cover: bytes | None,
                 text: bytes | None) -> dict:
        require_role(session, "SU")
        errors: dict[str, str] = {}
        title = (form.get("title") or "").strip()
        author = (form.get("author") or "").strip()
        category = (form.get("category") or "").strip()
        description = (form.get("description") or "").strip()
        keywords = [k.strip().lower() for k in (form.get("keywords") or "").split(",") if k.strip()]
        for f, v in (("title", title), ("author", author), ("category", category),
                     ("description", description)):
            if not v:
                errors[f] = "Required"
        try:
            year = int(str(form.get("year", "")).strip())
            if year < -3000 or year > clock.now().year:
                raise ValueError
        except ValueError:
            errors["year"] = "Enter a valid year"
        try:
            price = D(str(form.get("price", "")).strip().replace("$", ""))
            if price <= 0:
                raise ValueError
        except Exception:
            errors["price"] = "Price must be above $0"
        img = None
        if not cover:
            errors["cover"] = "Upload a cover image"
        else:
            img = cv2.imdecode(np.frombuffer(cover, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                errors["cover"] = "The cover must be a JPG or PNG image"
        text_str = None
        if text:
            try:
                text_str = text.decode("utf-8")
            except UnicodeDecodeError:
                errors["text"] = "The text file must be UTF-8 text"
        if errors:
            raise ValidationError("Please fix the highlighted fields", errors)
        if any(b["title"].lower() == title.lower() and b["author"].lower() == author.lower()
               for b in self.all_books()):
            raise ValidationError("This book is already in the catalog",
                                  {"title": "This book is already in the catalog"})

        with self.store.lock:
            book_ID = self.store.next_id("books", "book_ID", "B-")
            self.config.covers_dir.mkdir(parents=True, exist_ok=True)
            cover_rel = f"covers/{book_ID}.png"
            cv2.imwrite(str(self.config.data_dir / cover_rel), img)
            text_rel = None
            if text_str:
                self.config.texts_dir.mkdir(parents=True, exist_ok=True)
                text_rel = f"texts/{book_ID}.txt"
                (self.config.data_dir / text_rel).write_text(text_str, encoding="utf-8")
            book = {"book_ID": book_ID, "title": title, "author": author, "category": category,
                    "keywords": keywords, "description": description, "pub_Year": year,
                    "price": to_store(price), "cover_Path": cover_rel, "text_Path": text_rel,
                    "browse_Count": 0, "purchase_Count": 0, "rating_Count": 0,
                    "weighted_Avg": 0.0, "list_Status": "NONE", "indexed": False,
                    "added_At": clock.now_iso()}
            self.store.append("books", book)
        book["indexed"] = self.index_book(book)
        log_admin(self.store, session.user_ID, "ADD_BOOK", book_ID, f"{title} by {author}")
        return book

    def index_book(self, book: dict) -> bool:
        """Index the cover for image search and the text for RAG / Reading Companion."""
        try:
            ok = self.covers.add(book["book_ID"], self.config.data_dir / book["cover_Path"])
            text = self.book_text(book)
            if text:
                self.rag.index_book(book, text)
            self.store.update("books", "book_ID", book["book_ID"], {"indexed": bool(ok)})
            return bool(ok)
        except Exception:
            return False          # indexed at the next start-up (see AppContext.startup)

    def index_pending(self) -> int:
        n = 0
        for b in self.all_books():
            if not b.get("indexed"):
                n += int(self.index_book(b))
        return n
