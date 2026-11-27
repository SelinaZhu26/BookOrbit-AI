"""Review moderation (spec item 7).

  TabooService      UC-16 Manage Taboo Word List
  ModerationEngine  counts and masks taboo words
  RatingService     weighted average and No-Order / To-Order lists (UC-10, UC-18)
  WarningService    UC-11 Receive Review Warnings (demotion / suspension)
  ReviewService     UC-10 Submit Book Reviews
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .. import clock
from ..errors import AccountSuspended, NotFoundError, ValidationError
from .base import ServiceBase, Session, log_admin, require_role
from .status_manager import StatusManager


# =============================================================== UC-16
class TabooService(ServiceBase):
    def words(self) -> list[str]:
        return sorted(r["word"] for r in self.store.read_all("taboo_words"))

    def records(self) -> list[dict]:
        return sorted(self.store.read_all("taboo_words"), key=lambda r: r["word"])

    @staticmethod
    def _clean(word: str) -> str:
        w = (word or "").strip().lower()
        if not w or re.search(r"\s", w) or not re.fullmatch(r"[a-z][a-z'\-]*", w):
            raise ValidationError("Enter one word", {"word": "Enter one word"})
        return w

    def add(self, session: Session, word: str) -> str:
        require_role(session, "SU")
        w = self._clean(word)
        with self.store.lock:
            if w in self.words():
                raise ValidationError("That word is already in the list", {"word": "That word is already in the list"})
            self.store.append("taboo_words", {"word": w, "added_By": session.user_ID, "added_At": clock.now_iso()})
        log_admin(self.store, session.user_ID, "TABOO_ADD", w)
        return w

    def edit(self, session: Session, old: str, new: str) -> str:
        require_role(session, "SU")
        w = self._clean(new)
        old = (old or "").strip().lower()
        with self.store.lock:
            words = self.words()
            if old not in words:
                raise NotFoundError("That word was already removed - the list was reloaded")
            if w != old and w in words:
                raise ValidationError("That word is already in the list", {"word": "That word is already in the list"})
            self.store.update("taboo_words", "word", old, {"word": w, "added_By": session.user_ID,
                                                           "added_At": clock.now_iso()})
        log_admin(self.store, session.user_ID, "TABOO_EDIT", w, f"was '{old}'")
        return w

    def delete(self, session: Session, word: str) -> None:
        require_role(session, "SU")
        w = (word or "").strip().lower()
        removed = self.store.delete("taboo_words", lambda r: r["word"] == w)
        if not removed:
            raise NotFoundError("That word was already removed - the list was reloaded")
        log_admin(self.store, session.user_ID, "TABOO_DELETE", w)


# ======================================================= moderation
@dataclass
class Moderation:
    taboo_count: int
    found: list[str]
    display_text: str
    blocked: bool


class ModerationEngine:
    WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")

    def __init__(self, block_over: int = 3):
        self.block_over = block_over

    def check(self, text: str, taboo: list[str]) -> Moderation:
        taboo_set = {t.lower() for t in taboo}
        found = []

        def mask(m: re.Match) -> str:
            word = m.group(0)
            key = word.lower().strip("'-")
            if key in taboo_set:
                found.append(key)
                return "*" * len(word)
            return word
        display = self.WORD.sub(mask, text)
        return Moderation(len(found), found, display, len(found) > self.block_over)


# ============================================================ ratings
class RatingService(ServiceBase):
    def recalculate(self, book_ID: str) -> dict:
        reviews = self.store.filter("reviews", book_ID=book_ID, status="PUBLISHED")
        count = len(reviews)
        wsum = sum(r["weight"] for r in reviews)
        avg = round(sum(r["rating"] * r["weight"] for r in reviews) / wsum, 2) if wsum else 0.0
        status = "NONE"
        if count > self.config.list_min_ratings and avg < self.config.no_order_below:
            status = "NO_ORDER"
        elif count > self.config.list_min_ratings and avg > self.config.to_order_above:
            status = "TO_ORDER"
        return self.store.update("books", "book_ID", book_ID,
                                 {"rating_Count": count, "weighted_Avg": avg, "list_Status": status})

    def recalculate_all(self, session: Session) -> int:
        require_role(session, "SU")
        books = self.store.read_all("books")
        for b in books:
            self.recalculate(b["book_ID"])
        log_admin(self.store, session.user_ID, "RECALCULATE_ALL", "books", f"{len(books)} books")
        return len(books)

    # ============================================================ UC-18
    def order_lists(self, session: Session) -> dict:
        require_role(session, "SU")
        books = self.store.read_all("books")
        no_order = sorted([b for b in books if b["list_Status"] == "NO_ORDER"], key=lambda b: b["weighted_Avg"])
        to_order = sorted([b for b in books if b["list_Status"] == "TO_ORDER"], key=lambda b: -b["weighted_Avg"])
        return {"no_order": no_order, "to_order": to_order,
                "message": "" if (no_order or to_order) else "No books meet the thresholds yet"}

    def breakdown(self, book_ID: str) -> dict[int, int]:
        out = {s: 0 for s in range(5, 0, -1)}
        for r in self.store.filter("reviews", book_ID=book_ID, status="PUBLISHED"):
            out[int(r["rating"])] += 1
        return out


# ============================================================ UC-11
class WarningService(ServiceBase):
    def __init__(self, store, config, status: StatusManager):
        super().__init__(store, config)
        self.status = status

    def issue(self, user_ID: str, review_ID: str) -> dict:
        user = self.users.get(user_ID)
        self.store.append("warnings", {
            "warning_ID": self.store.next_id("warnings", "warning_ID", "W-"),
            "user_ID": user_ID, "review_ID": review_ID, "reason": "Blocked comment (more than 3 taboo words)",
            "created_At": clock.now_iso()})
        user["warnings"] += 1
        self.users.save(user)
        n = user["warnings"]
        if user["role"] == "VC":
            self.status.demote_to_rc(user, "Blocked comment")
            return {"outcome": "DEMOTED", "warnings": n,
                    "message": f"Your comment was blocked. It contains more than 3 prohibited words. "
                               f"This is your warning {n} of 3. You are no longer a VIP Customer, "
                               f"so prices are shown without the 10% discount."}
        if user["role"] == "RC" and n > self.config.rc_max_warnings:
            self.status.suspend(user, f"{n} warnings for blocked comments")
            return {"outcome": "SUSPENDED", "warnings": n,
                    "message": f"Your comment was blocked. It contains more than 3 prohibited words. "
                               f"This is your warning {n} of 3, so your account is suspended. "
                               f"You can still open My Balance."}
        return {"outcome": "WARNED", "warnings": n,
                "message": f"Your comment was blocked. It contains more than 3 prohibited words. "
                           f"Warning {n} of 3."}

    def for_user(self, user_ID: str) -> list[dict]:
        return sorted(self.store.filter("warnings", user_ID=user_ID), key=lambda w: w["warning_ID"], reverse=True)


# ============================================================ UC-10
class ReviewService(ServiceBase):
    def __init__(self, store, config, taboo: TabooService, moderation: ModerationEngine,
                 ratings: RatingService, warnings: WarningService):
        super().__init__(store, config)
        self.taboo = taboo
        self.moderation = moderation
        self.ratings = ratings
        self.warnings = warnings

    def published(self, book_ID: str) -> list[dict]:
        return sorted(self.store.filter("reviews", book_ID=book_ID, status="PUBLISHED"),
                      key=lambda r: r["created_At"] + r["review_ID"], reverse=True)

    def own_review(self, session: Session, book_ID: str) -> dict | None:
        if session.user_ID:
            return self.store.find("reviews", book_ID=book_ID, user_ID=session.user_ID, status="PUBLISHED")
        if session.visitor_key:
            return self.store.find("reviews", book_ID=book_ID, visitor_Key=session.visitor_key, status="PUBLISHED")
        return None

    def for_user(self, user_ID: str) -> list[dict]:
        books = {b["book_ID"]: b for b in self.store.read_all("books")}
        out = []
        for r in sorted(self.store.filter("reviews", user_ID=user_ID), key=lambda r: r["review_ID"], reverse=True):
            out.append({**r, "book": books.get(r["book_ID"])})
        return out

    def submit(self, session: Session, book_ID: str, rating, comment: str) -> dict:
        """Returns {"status": PUBLISHED|BLOCKED, "review", "masked", "warning", "book"}."""
        book = self.store.find("books", book_ID=book_ID)
        if not book:
            raise NotFoundError("Book unavailable")
        if session.user_ID:
            user = self.users.get(session.user_ID)
            if user["status"] == "SUSPENDED":
                raise AccountSuspended("Your account is suspended - writing reviews is disabled.")
        else:
            user = None
        try:
            stars = int(rating)
        except (TypeError, ValueError):
            stars = 0
        comment = (comment or "").strip()
        if not 1 <= stars <= 5 or not comment or len(comment) > self.config.max_comment_len:
            raise ValidationError("Choose 1-5 stars and write 1-1000 characters",
                                  {"rating": "Choose 1-5 stars"} if not 1 <= stars <= 5 else
                                  {"comment": "Write 1-1000 characters"})

        mod = self.moderation.check(comment, self.taboo.words())
        verified = bool(user) and self.store.find("purchases", user_ID=user["user_ID"], book_ID=book_ID) is not None
        weight = self.config.buyer_weight if verified else 1.0
        now = clock.now_iso()
        base = {"book_ID": book_ID,
                "user_ID": user["user_ID"] if user else None,
                "visitor_Key": None if user else session.visitor_key,
                "author_Name": user["full_Name"] if user else "Visitor",
                "role_At_Time": session.role, "rating": stars, "original_Text": comment,
                "taboo_Count": mod.taboo_count, "weight": weight, "verified_Buyer": verified,
                "updated_At": now}

        with self.store.lock:
            if mod.blocked:
                rec = {"review_ID": self.store.next_id("reviews", "review_ID", "R-", 5),
                       **base, "display_Text": "", "status": "BLOCKED", "created_At": now}
                self.store.append("reviews", rec)               # never shown
                warning = None
                if user and user["role"] in ("RC", "VC"):
                    warning = self.warnings.issue(user["user_ID"], rec["review_ID"])
                return {"status": "BLOCKED", "review": rec, "masked": mod.taboo_count,
                        "warning": warning, "book": book,
                        "message": warning["message"] if warning else
                        "Your comment was blocked. It contains more than 3 prohibited words."}

            existing = self.own_review(session, book_ID)
            if existing:                                         # "Edit review" (Figure 24)
                rec = self.store.update("reviews", "review_ID", existing["review_ID"],
                                        {**base, "display_Text": mod.display_text})
            else:
                rec = {"review_ID": self.store.next_id("reviews", "review_ID", "R-", 5),
                       **base, "display_Text": mod.display_text, "status": "PUBLISHED", "created_At": now}
                self.store.append("reviews", rec)
            before = book["list_Status"]
            book = self.ratings.recalculate(book_ID)
        msg = "Review published"
        if mod.taboo_count:
            msg += f" - {mod.taboo_count} word{'s were' if mod.taboo_count > 1 else ' was'} masked"
        msg += "."
        if book["list_Status"] != before and book["list_Status"] != "NONE":
            lst = "To-Order" if book["list_Status"] == "TO_ORDER" else "No-Order"
            msg += (f" {book['title']} now has {book['rating_Count']} ratings (weighted average "
                    f"{book['weighted_Avg']:.2f}) and was added to the {lst} List.")
        return {"status": "PUBLISHED", "review": rec, "masked": mod.taboo_count, "warning": None,
                "book": book, "message": msg}
