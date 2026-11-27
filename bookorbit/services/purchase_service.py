"""PurchaseService - UC-08 Purchase Books, UC-09 Receive VIP Discount
(spec items 6 and 8).

The checkout screen (Figure 25) may hold several books; each book is a
separate purchase record and ledger line, and the balance check, fine and
VIP promotion rules are applied to the order exactly as UC-08 describes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .. import clock
from ..errors import AccountSuspended, NotFoundError, PermissionDenied, ValidationError
from ..money import D, to_store
from .base import ServiceBase, Session
from .status_manager import StatusManager
from .wallet_service import WalletService


@dataclass
class Quote:
    lines: list[dict]
    subtotal: object
    discount: object
    total: object
    vip: bool
    balance: object
    balance_after: object


@dataclass
class CheckoutResult:
    ok: bool
    message: str
    receipt: list[dict] = field(default_factory=list)
    total: object = None
    promoted: bool = False
    fined: bool = False
    suspended: bool = False
    balance: object = None


class PurchaseService(ServiceBase):
    def __init__(self, store, config, wallet: WalletService, status: StatusManager):
        super().__init__(store, config)
        self.wallet = wallet
        self.status = status

    def owns(self, user_ID: str, book_ID: str) -> bool:
        return self.store.find("purchases", user_ID=user_ID, book_ID=book_ID) is not None

    def orders(self, user_ID: str) -> list[dict]:
        books = {b["book_ID"]: b for b in self.store.read_all("books")}
        out = []
        for p in sorted(self.store.filter("purchases", user_ID=user_ID),
                        key=lambda p: p["purchase_ID"], reverse=True):
            out.append({**p, "book": books.get(p["book_ID"])})
        return out

    # ================================================================ UC-09
    def final_price(self, user_ID: str, list_price) -> dict:
        user = self.users.get(user_ID)                  # read the role again
        price = D(list_price)
        if user["role"] == "VC":
            discount = D(price * D(self.config.vip_discount))
        else:
            discount = D(0)                              # demoted users pay full price
        return {"list": price, "discount": discount, "paid": price - discount,
                "label": "VIP -10%" if discount > 0 else ""}

    # ================================================================ UC-08
    def quote(self, session: Session, book_IDs: list[str]) -> Quote:
        if not session.is_customer:
            raise PermissionDenied("Sign in as a customer to buy books.")
        user = self.users.get(session.user_ID)
        lines, sub, disc = [], D(0), D(0)
        for bid in dict.fromkeys(book_IDs):              # keep order, drop duplicates
            book = self.store.find("books", book_ID=bid)
            if not book:
                continue
            p = self.final_price(user["user_ID"], book["price"])
            lines.append({"book": book, **p, "owned": self.owns(user["user_ID"], bid)})
            sub += p["list"]
            disc += p["discount"]
        total = sub - disc
        bal = D(user["balance"])
        return Quote(lines, sub, disc, total, user["role"] == "VC", bal, bal - total)

    def checkout(self, session: Session, book_IDs: list[str]) -> CheckoutResult:
        if not session.is_customer:
            raise PermissionDenied("Sign in as a customer to buy books.")
        if not book_IDs:
            raise ValidationError("Your cart is empty")
        with self.store.lock:
            user = self.users.get(session.user_ID)
            if user["status"] == "SUSPENDED":
                raise AccountSuspended("Your account is suspended - purchases are disabled.")
            for bid in book_IDs:
                if not self.store.find("books", book_ID=bid):
                    raise NotFoundError("Book unavailable")
                if self.owns(user["user_ID"], bid):
                    title = self.store.find("books", book_ID=bid)["title"]
                    raise ValidationError(f"You already own this book ({title})")
            q = self.quote(session, book_IDs)
            balance = D(user["balance"])

            if balance < q.total:                        # insufficient funds -> $1 fine
                fine = D(self.config.fine_amount)
                user["balance"] = to_store(balance - fine)
                self.users.save(user)
                self.wallet.add_transaction(user, "FINE", -fine,
                                            f"Insufficient funds for {self._money(q.total)} order")
                suspended = False
                if D(user["balance"]) < 0:
                    self.status.suspend(user, "Negative balance after a $1.00 fine")
                    suspended = True
                msg = "Insufficient funds: $1.00 fine charged."
                if suspended:
                    msg += " Your balance is below $0, so your account is suspended."
                return CheckoutResult(False, msg, fined=True, suspended=suspended,
                                      balance=D(user["balance"]), total=q.total)

            receipt = []
            for line in q.lines:
                book = line["book"]
                balance -= line["paid"]
                user["balance"] = to_store(balance)
                note = f"Bought “{book['title']}”" + (f" ({line['label']})" if line["label"] else "")
                txn = self.wallet.add_transaction(user, "PURCHASE", -line["paid"], note, book["book_ID"])
                rec = {"purchase_ID": self.store.next_id("purchases", "purchase_ID", "P-", 5),
                       "user_ID": user["user_ID"], "book_ID": book["book_ID"],
                       "list_Price": to_store(line["list"]), "discount": to_store(line["discount"]),
                       "paid": to_store(line["paid"]), "txn_ID": txn["txn_ID"],
                       "created_At": clock.now_iso()}
                self.store.append("purchases", rec)
                user["purchase_Count"] += 1
                user["total_Spent"] = to_store(D(user["total_Spent"]) + line["paid"])
                user["promo_Purchases"] += 1
                user["promo_Spent"] = to_store(D(user["promo_Spent"]) + line["paid"])
                self.store.update("books", "book_ID", book["book_ID"],
                                  lambda b: b.__setitem__("purchase_Count", b["purchase_Count"] + 1))
                receipt.append({**rec, "title": book["title"], "label": line["label"]})
            self.users.save(user)

            promoted = False
            if user["role"] == "RC" and (user["promo_Purchases"] > self.config.vip_min_purchases
                                         or D(user["promo_Spent"]) > D(self.config.vip_min_spent)):
                self.status.promote_to_vip(user, f"{user['promo_Purchases']} purchases / "
                                                 f"{self._money(user['promo_Spent'])} spent")
                promoted = True
            msg = "Purchase complete."
            if promoted:
                msg += " Congratulations - you are now a VIP Customer!"
            return CheckoutResult(True, msg, receipt=receipt, total=q.total, promoted=promoted,
                                  balance=D(user["balance"]))

    @staticmethod
    def _money(v) -> str:
        return f"${D(v):,.2f}"
