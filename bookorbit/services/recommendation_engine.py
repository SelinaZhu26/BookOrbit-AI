"""RecommendationEngine - UC-03 View Popular Books, UC-06 Receive Personalized
Recommendations (spec item 2)."""
from __future__ import annotations

from collections import Counter

from .base import ServiceBase, Session


class RecommendationEngine(ServiceBase):
    PURCHASE_WEIGHT = 3
    VIEW_WEIGHT = 1

    @staticmethod
    def popularity(book: dict) -> int:
        return book["browse_Count"] + 3 * book["purchase_Count"]

    # ================================================================ UC-03
    def popular(self, n: int = 3, exclude: set[str] | None = None) -> list[dict]:
        books = [b for b in self.store.read_all("books") if not exclude or b["book_ID"] not in exclude]
        books.sort(key=lambda b: (-self.popularity(b), -b["weighted_Avg"], b["title"].lower()))
        return books[:n]

    def owned(self, user_ID: str) -> set[str]:
        return {p["book_ID"] for p in self.store.filter("purchases", user_ID=user_ID)}

    # ================================================================ UC-06
    def profile(self, user_ID: str) -> Counter:
        books = {b["book_ID"]: b for b in self.store.read_all("books")}
        prof: Counter = Counter()

        def add(book, w):
            prof["cat:" + book["category"].lower()] += w
            prof["author:" + book["author"].lower()] += w
            for k in book.get("keywords", []):
                prof["kw:" + k.lower()] += w

        for p in self.store.filter("purchases", user_ID=user_ID):
            if p["book_ID"] in books:
                add(books[p["book_ID"]], self.PURCHASE_WEIGHT)
        for e in self.store.filter("browse_history", user_ID=user_ID):
            if e["book_ID"] in books:
                add(books[e["book_ID"]], self.VIEW_WEIGHT)
        return prof

    def _reason(self, book: dict, prof: Counter) -> str:
        parts = []
        if prof["author:" + book["author"].lower()]:
            parts.append(f"more by {book['author']}")
        if prof["cat:" + book["category"].lower()]:
            parts.append(f"you like {book['category']}")
        kws = [k for k in book.get("keywords", []) if prof["kw:" + k.lower()]]
        if kws:
            parts.append("themes: " + ", ".join(kws[:2]))
        return "; ".join(parts) or "popular right now"

    def personalized(self, session: Session, n: int = 3) -> dict:
        """Returns {"title", "books", "reasons", "personal"} for the home page."""
        if not session.is_customer:
            return {"title": "Top picks this week", "subtitle": "Most browsed and purchased books",
                    "books": self.popular(n), "reasons": {}, "personal": False}
        owned = self.owned(session.user_ID)
        has_history = bool(owned) or bool(self.store.filter("browse_history", user_ID=session.user_ID))
        if not has_history:
            return {"title": "Popular right now", "subtitle": "Browse or buy a book to get personal picks",
                    "books": self.popular(n, exclude=owned), "reasons": {}, "personal": False}
        prof = self.profile(session.user_ID)
        candidates = [b for b in self.store.read_all("books") if b["book_ID"] not in owned]
        if not candidates:
            return {"title": "Popular right now", "subtitle": "You own every book in the store!",
                    "books": self.popular(n), "reasons": {}, "personal": False}
        scored = []
        for b in candidates:
            score = prof["cat:" + b["category"].lower()] + prof["author:" + b["author"].lower()] \
                + sum(prof["kw:" + k.lower()] for k in b.get("keywords", []))
            if score > 0:
                scored.append((score, self.popularity(b), b))
        scored.sort(key=lambda t: (-t[0], -t[1], t[2]["title"]))
        picks = [b for _, _, b in scored[:n]]
        if len(picks) < n:                       # fill with popular books not listed yet
            seen = owned | {b["book_ID"] for b in picks}
            picks += self.popular(n - len(picks), exclude=seen)
        reasons = {b["book_ID"]: self._reason(b, prof) for b in picks}
        return {"title": "Recommended for you", "subtitle": "Based on the books you bought and viewed.",
                "books": picks, "reasons": reasons, "personal": True}
