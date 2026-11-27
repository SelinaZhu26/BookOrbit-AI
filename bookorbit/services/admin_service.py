"""AdminService - UC-17 Reopen Suspended Accounts, user management and the
figures behind the Super-User finance report (used by UC-13)."""
from __future__ import annotations

from collections import Counter

from ..errors import NotFoundError, PermissionDenied, ValidationError
from ..money import D, parse_amount, to_store
from .base import ROLE_NAMES, ServiceBase, Session, log_admin, require_role
from .status_manager import StatusManager
from .wallet_service import WalletService


class AdminService(ServiceBase):
    def __init__(self, store, config, status: StatusManager, wallet: WalletService):
        super().__init__(store, config)
        self.status = status
        self.wallet = wallet

    def users_list(self, session: Session) -> list[dict]:
        require_role(session, "SU")
        bios = {b["user_ID"] for b in self.store.read_all("biometrics")}
        out = []
        for u in sorted(self.store.read_all("users"), key=lambda u: u["user_ID"]):
            out.append({**u, "has_face": u["user_ID"] in bios, "role_name": ROLE_NAMES[u["role"]]})
        return out

    def suspended(self, session: Session) -> list[dict]:
        return [u for u in self.users_list(session) if u["status"] == "SUSPENDED"]

    # ================================================================ UC-17
    def reopen(self, session: Session, user_ID: str, deposit_text: str = "") -> dict:
        """Reopen a suspended account. The SU may record the customer's deposit
        in the same step (spec item 6: "reopen the account with positive money
        deposited")."""
        require_role(session, "SU")
        with self.store.lock:
            customer = self.users.get(user_ID)           # read again
            if customer["status"] != "SUSPENDED":
                raise NotFoundError("This account was already reopened - the list was reloaded")
            if deposit_text and str(deposit_text).strip():
                try:
                    amount = parse_amount(deposit_text, self.config.max_deposit)
                except ValueError:
                    raise ValidationError("Enter a valid amount", {"amount": "Enter a valid amount"})
                customer["balance"] = to_store(D(customer["balance"]) + amount)
                self.users.save(customer)
                self.wallet.add_transaction(customer, "DEPOSIT", amount, "Deposit recorded by Super-User")
            if D(customer["balance"]) < 0:
                need = -D(customer["balance"])
                raise ValidationError(f"The customer must deposit at least ${need:,.2f} first",
                                      {"amount": f"At least ${need:,.2f}"})
            self.status.reopen(customer, by=session.user_ID)
            log_admin(self.store, session.user_ID, "REOPEN_ACCOUNT", user_ID,
                      f"balance ${D(customer['balance']):,.2f}")
            return customer

    # ===================================================== finance facts
    def finance_facts(self, session: Session) -> dict:
        if session.role != "SU":
            raise PermissionDenied("That information isn't available for your account type")
        users = self.store.read_all("users")
        txns = self.store.read_all("transactions")
        purchases = self.store.read_all("purchases")
        books = {b["book_ID"]: b for b in self.store.read_all("books")}
        customers = [u for u in users if u["role"] in ("RC", "VC")]
        sales = sum((D(p["paid"]) for p in purchases), D(0))
        discounts = sum((D(p["discount"]) for p in purchases), D(0))
        deposits = sum((D(t["amount"]) for t in txns if t["type"] == "DEPOSIT"), D(0))
        fines = sum((-D(t["amount"]) for t in txns if t["type"] == "FINE"), D(0))
        balances = sum((D(u["balance"]) for u in customers), D(0))
        per_book = Counter()
        for p in purchases:
            per_book[p["book_ID"]] += 1
        top = [(books[b]["title"], n) for b, n in per_book.most_common(3) if b in books]
        spenders = sorted(customers, key=lambda u: -D(u["total_Spent"]))[:3]
        return {
            "total_sales": sales, "books_sold": len(purchases), "vip_discounts": discounts,
            "deposits": deposits, "fines": fines, "fine_count": sum(1 for t in txns if t["type"] == "FINE"),
            "customer_balances": balances,
            "customers": len(customers), "vip_customers": sum(1 for u in customers if u["role"] == "VC"),
            "suspended": [u["username"] for u in customers if u["status"] == "SUSPENDED"],
            "warnings": {u["username"]: u["warnings"] for u in customers if u["warnings"]},
            "no_order": [b["title"] for b in books.values() if b["list_Status"] == "NO_ORDER"],
            "to_order": [b["title"] for b in books.values() if b["list_Status"] == "TO_ORDER"],
            "top_books": top,
            "top_spenders": [(u["username"], D(u["total_Spent"])) for u in spenders if D(u["total_Spent"]) > 0],
        }

    def recent_actions(self, session: Session, n: int = 10) -> list[dict]:
        require_role(session, "SU")
        return sorted(self.store.read_all("admin_actions"), key=lambda a: a["action_ID"], reverse=True)[:n]

    def log(self, session: Session, action: str, target: str, details: str = "") -> None:
        log_admin(self.store, session.user_ID, action, target, details)
