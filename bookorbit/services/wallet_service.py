"""WalletService - UC-07 Manage Cash Balance and Ledger (spec item 6)."""
from __future__ import annotations

from .. import clock
from ..errors import PermissionDenied, ValidationError
from ..money import D, parse_amount, to_store
from .base import ServiceBase, Session


class WalletService(ServiceBase):
    def add_transaction(self, user: dict, kind: str, amount, note: str,
                        book_ID: str | None = None) -> dict:
        """Append a ledger line. ``amount`` is signed (deposits +, purchases/fines -)."""
        rec = {"txn_ID": self.store.next_id("transactions", "txn_ID", "T-", 6),
               "user_ID": user["user_ID"], "type": kind, "amount": to_store(amount),
               "balance_After": to_store(user["balance"]), "note": note,
               "book_ID": book_ID, "created_At": clock.now_iso()}
        self.store.append("transactions", rec)
        return rec

    def ledger(self, user_ID: str) -> list[dict]:
        return sorted(self.store.filter("transactions", user_ID=user_ID),
                      key=lambda t: t["txn_ID"], reverse=True)

    # ================================================================ UC-07
    def deposit(self, session: Session, amount_text: str) -> dict:
        if not session.is_customer:
            raise PermissionDenied("Only customers have a store balance.")
        try:
            amount = parse_amount(amount_text, self.config.max_deposit)
        except ValueError:
            raise ValidationError("Enter a valid amount", {"amount": "Enter a valid amount"})
        with self.store.lock:
            user = self.users.get(session.user_ID)
            snapshot = dict(user)
            user["balance"] = to_store(D(user["balance"]) + amount)
            try:
                self.users.save(user)
                txn = self.add_transaction(user, "DEPOSIT", amount, "Added funds")
            except Exception:
                self.users.save(snapshot)                # nothing changes
                raise
        note = None
        if user["status"] == "SUSPENDED" and D(user["balance"]) >= 0:
            note = "A Super-User can now reactivate your account"
        return {"user": user, "txn": txn, "note": note}
