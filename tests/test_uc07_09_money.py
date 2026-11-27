"""UC-07 Manage Cash Balance and Ledger, UC-08 Purchase Books, UC-09 Receive VIP Discount."""
from decimal import Decimal

import pytest

from bookorbit.errors import AccountSuspended, StorageError, ValidationError
from tests.helpers import book_id, session_for


def bal(ctx, username):
    return Decimal(str(ctx.users.by_username(username)["balance"]))


# ---------------------------------------------------------------- UC-07
def test_deposit_updates_balance_and_ledger(ctx):
    s = session_for(ctx, "alice")
    out = ctx.wallet.deposit(s, "25.50")
    assert bal(ctx, "alice") == Decimal("55.52")
    top = ctx.wallet.ledger(s.user_ID)[0]
    assert top["type"] == "DEPOSIT" and top["amount"] == 25.5 and top["balance_After"] == 55.52
    assert out["note"] is None


@pytest.mark.parametrize("amount", ["0", "-5", "abc", "1.234", "10000.01", "", "nan", "inf"])
def test_invalid_deposits_change_nothing(ctx, amount):
    s = session_for(ctx, "alice")
    n = len(ctx.wallet.ledger(s.user_ID))
    with pytest.raises(ValidationError, match="Enter a valid amount"):
        ctx.wallet.deposit(s, amount)
    assert bal(ctx, "alice") == Decimal("30.02") and len(ctx.wallet.ledger(s.user_ID)) == n


def test_deposit_max_is_allowed(ctx):
    ctx.wallet.deposit(session_for(ctx, "alice"), "10000")
    assert bal(ctx, "alice") == Decimal("10030.02")


def test_suspended_customer_can_deposit_and_is_told_su_can_reactivate(ctx):
    s = session_for(ctx, "zakiah")                         # balance -0.99
    out = ctx.wallet.deposit(s, "5")
    assert out["note"] == "A Super-User can now reactivate your account"
    assert ctx.users.by_username("zakiah")["status"] == "SUSPENDED"   # only an SU reopens


def test_failed_save_leaves_balance_unchanged(ctx):
    ctx.store.fail_next_write = True
    with pytest.raises(StorageError):
        ctx.wallet.deposit(session_for(ctx, "alice"), "10")
    assert bal(ctx, "alice") == Decimal("30.02")


# ---------------------------------------------------------------- UC-08
def test_purchase_deducts_records_and_unlocks(ctx):
    s = session_for(ctx, "alice")
    bid = book_id(ctx, "Persuasion")                       # $8.49
    sold = ctx.catalog.get(bid)["purchase_Count"]
    res = ctx.purchases.checkout(s, [bid])
    assert res.ok and bal(ctx, "alice") == Decimal("21.53")
    assert ctx.purchases.owns(s.user_ID, bid)
    assert ctx.catalog.get(bid)["purchase_Count"] == sold + 1
    assert ctx.wallet.ledger(s.user_ID)[0]["type"] == "PURCHASE"
    view = ctx.companion.open(s, bid, 3)                   # full text unlocked
    assert not view["locked"]


def test_insufficient_funds_rejects_and_fines_one_dollar(ctx):
    s = session_for(ctx, "alice")                          # $30.02
    expensive = [book_id(ctx, t) for t in ("Moby Dick", "On the Origin of Species", "Paradise Lost")]
    res = ctx.purchases.checkout(s, expensive)             # $38.47
    assert not res.ok and res.fined and not res.suspended
    assert bal(ctx, "alice") == Decimal("29.02")
    assert ctx.wallet.ledger(s.user_ID)[0]["type"] == "FINE"
    assert not any(ctx.purchases.owns(s.user_ID, b) for b in expensive)


def test_fine_that_makes_balance_negative_suspends(ctx):
    s = session_for(ctx, "alice")
    ctx.store.update("users", "user_ID", s.user_ID, {"balance": 0.5})
    res = ctx.purchases.checkout(s, [book_id(ctx, "Dracula")])
    assert res.suspended
    u = ctx.users.get(s.user_ID)
    assert u["status"] == "SUSPENDED" and u["balance"] == -0.5
    assert ctx.store.read_all("status_changes")[-1]["to_Status"] == "SUSPENDED"


def test_cannot_buy_owned_book_or_when_suspended(ctx):
    with pytest.raises(ValidationError, match="already own"):
        ctx.purchases.checkout(session_for(ctx, "alice"), [book_id(ctx, "Emma")])
    with pytest.raises(AccountSuspended):
        ctx.purchases.checkout(session_for(ctx, "zakiah"), [book_id(ctx, "Dracula")])


def test_promotion_after_more_than_3_purchases(ctx):
    s = session_for(ctx, "ibrahim")                        # RC, $250, no purchases
    titles = ["Dracula", "Frankenstein", "The Time Machine"]
    ctx.purchases.checkout(s, [book_id(ctx, t) for t in titles])
    assert ctx.users.get(s.user_ID)["role"] == "RC"        # 3 is not "more than 3"
    res = ctx.purchases.checkout(s, [book_id(ctx, "Jane Eyre")])
    assert res.promoted and ctx.users.get(s.user_ID)["role"] == "VC"
    assert ctx.store.read_all("status_changes")[-1]["to_Role"] == "VC"


def test_promotion_after_spending_more_than_200(ctx):
    s = session_for(ctx, "ibrahim")
    bid = book_id(ctx, "Dracula")
    ctx.store.update("books", "book_ID", bid, {"price": 200.0})
    res = ctx.purchases.checkout(s, [bid])                 # exactly $200 -> not yet
    assert not res.promoted
    bid2 = book_id(ctx, "Frankenstein")
    res = ctx.purchases.checkout(s, [bid2])                # $208.99 > $200
    assert res.promoted


# ---------------------------------------------------------------- UC-09
def test_vip_pays_90_percent_rounded_and_ledger_labelled(ctx):
    s = session_for(ctx, "selina")                         # VC
    bid = book_id(ctx, "Emma")                             # 9.99 -> discount 1.00 -> 8.99
    before = bal(ctx, "selina")
    p = ctx.purchases.final_price(s.user_ID, 9.99)
    assert (p["discount"], p["paid"]) == (Decimal("1.00"), Decimal("8.99"))
    ctx.purchases.checkout(s, [bid])
    assert bal(ctx, "selina") == before - Decimal("8.99")
    assert "VIP -10%" in ctx.wallet.ledger(s.user_ID)[0]["note"]


def test_demoted_customer_pays_full_price(ctx):
    s = session_for(ctx, "selina")
    ctx.status.demote_to_rc(ctx.users.get(s.user_ID), "test")
    assert ctx.purchases.final_price(s.user_ID, 9.99)["paid"] == Decimal("9.99")


def test_promoted_customer_gets_discount_from_next_purchase(ctx):
    s = session_for(ctx, "ibrahim")
    ctx.purchases.checkout(s, [book_id(ctx, t) for t in ("Dracula", "Frankenstein", "The Time Machine")])
    res = ctx.purchases.checkout(s, [book_id(ctx, "Jane Eyre")])       # promoting purchase: full price
    assert res.promoted and res.receipt[0]["discount"] == 0
    res = ctx.purchases.checkout(s, [book_id(ctx, "Little Women")])    # next one: 10% off
    assert res.receipt[0]["discount"] == 0.9 and res.receipt[0]["paid"] == 8.09
