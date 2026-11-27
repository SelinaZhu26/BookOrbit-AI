"""UC-15 Add New Books, UC-16 Manage Taboo Word List, UC-17 Reopen Suspended
Accounts, UC-18 View Book Classification Lists."""
import cv2
import numpy as np
import pytest

from bookorbit.errors import NotFoundError, PermissionDenied, ValidationError
from tests.helpers import book_id, face, session_for

GOOD = {"title": "The Odyssey", "author": "Homer", "category": "Poetry", "year": "1614",
        "price": "6.50", "keywords": "epic, sea, journey", "description": "Odysseus tries to get home."}


def cover_png(seed=5):
    rng = np.random.default_rng(seed)
    img = np.full((600, 400, 3), (60, 90, 140), np.uint8)
    for _ in range(25):
        x, y = rng.integers(20, 360), rng.integers(20, 560)
        cv2.circle(img, (int(x), int(y)), int(rng.integers(8, 40)), tuple(int(c) for c in rng.integers(0, 255, 3)), -1)
    cv2.putText(img, "ODYSSEY", (40, 90), cv2.FONT_HERSHEY_DUPLEX, 1.6, (240, 230, 200), 3)
    return cv2.imencode(".png", img)[1].tobytes()


TEXT = ("BOOK I\n\n" + "Sing to me of the man, Muse, the man of twists and turns. " * 60 +
        "\n\nBOOK II\n\n" + "When young Dawn with her rose-red fingers shone once more. " * 60 +
        "\n\nBOOK III\n\n" + "The sun sprang up, leaving the brilliant waters. " * 60).encode()


# ---------------------------------------------------------------- UC-15
def test_su_adds_book_and_it_is_indexed(ctx):
    su = session_for(ctx, "admin")
    b = ctx.catalog.add_book(su, GOOD, cover_png(), TEXT)
    assert b["browse_Count"] == b["purchase_Count"] == b["rating_Count"] == 0 and b["list_Status"] == "NONE"
    assert ctx.catalog.get(b["book_ID"])["indexed"]
    res = ctx.catalog.cover_search(cover_png())                 # cover indexed for image search
    assert res.books[0]["book_ID"] == b["book_ID"]
    hits = ctx.rag.search("rose-red fingers Dawn", {"BOOK_TEXT"}, book_ID=b["book_ID"])
    assert hits                                                  # text indexed for RAG
    assert len(ctx.companion.chapters(ctx.catalog.get(b["book_ID"]))) == 3
    assert ctx.store.read_all("admin_actions")[-1]["action"] == "ADD_BOOK"
    assert ctx.catalog.search(query="odyssey").total == 1


@pytest.mark.parametrize("field,value", [("title", ""), ("author", " "), ("price", "0"), ("price", "-3"),
                                          ("price", "abc"), ("year", "nineteen"), ("description", "")])
def test_add_book_invalid_fields(ctx, field, value):
    with pytest.raises(ValidationError) as e:
        ctx.catalog.add_book(session_for(ctx, "admin"), {**GOOD, field: value}, cover_png(), None)
    assert field in e.value.fields


def test_add_book_duplicate_and_bad_files(ctx):
    su = session_for(ctx, "admin")
    with pytest.raises(ValidationError, match="already in the catalog"):
        ctx.catalog.add_book(su, {**GOOD, "title": "moby dick", "author": "Herman Melville"}, cover_png(), None)
    with pytest.raises(ValidationError) as e:
        ctx.catalog.add_book(su, GOOD, b"not an image", None)
    assert "cover" in e.value.fields
    with pytest.raises(ValidationError) as e:
        ctx.catalog.add_book(su, GOOD, cover_png(), "café".encode("latin-1") + b"\xff\xfe")
    assert "text" in e.value.fields
    with pytest.raises(ValidationError) as e:
        ctx.catalog.add_book(su, GOOD, None, None)
    assert "cover" in e.value.fields


def test_only_su_can_add_books(ctx):
    with pytest.raises(PermissionDenied):
        ctx.catalog.add_book(session_for(ctx, "selina"), GOOD, cover_png(), None)


def test_book_not_indexed_is_indexed_at_startup(ctx):
    su = session_for(ctx, "admin")
    real_add = ctx.covers.add
    ctx.covers.add = lambda *a: (_ for _ in ()).throw(RuntimeError("model not loaded"))
    b = ctx.catalog.add_book(su, GOOD, cover_png(), None)
    assert not ctx.catalog.get(b["book_ID"])["indexed"]
    ctx.covers.add = real_add
    ctx.startup()
    assert ctx.catalog.get(b["book_ID"])["indexed"]


# ---------------------------------------------------------------- UC-16
def test_taboo_add_edit_delete_and_logging(ctx):
    su = session_for(ctx, "admin")
    assert ctx.taboo.add(su, "  Rubbish ") == "rubbish"
    assert "rubbish" in ctx.taboo.words()
    ctx.taboo.edit(su, "rubbish", "drivel")
    assert "drivel" in ctx.taboo.words() and "rubbish" not in ctx.taboo.words()
    ctx.taboo.delete(su, "drivel")
    assert "drivel" not in ctx.taboo.words()
    actions = [a["action"] for a in ctx.store.read_all("admin_actions")]
    assert actions[-3:] == ["TABOO_ADD", "TABOO_EDIT", "TABOO_DELETE"]


@pytest.mark.parametrize("word,msg", [("", "Enter one word"), ("two words", "Enter one word"),
                                      ("junk", "already in the list"), ("JUNK", "already in the list")])
def test_taboo_invalid_words(ctx, word, msg):
    with pytest.raises(ValidationError, match=msg):
        ctx.taboo.add(session_for(ctx, "admin"), word)


def test_taboo_word_already_removed_by_other_su(ctx):
    a, b = session_for(ctx, "admin"), session_for(ctx, "yixin")
    ctx.taboo.delete(a, "junk")
    with pytest.raises(NotFoundError, match="already removed"):
        ctx.taboo.delete(b, "junk")


def test_only_su_manages_taboo(ctx):
    with pytest.raises(PermissionDenied):
        ctx.taboo.add(session_for(ctx, "alice"), "word")


# ---------------------------------------------------------------- UC-17
def test_reopen_refused_while_balance_negative(ctx):
    su = session_for(ctx, "admin")
    z = ctx.users.by_username("zakiah")
    assert [u["username"] for u in ctx.admin.suspended(su)] == ["zakiah"]
    with pytest.raises(ValidationError, match=r"must deposit at least \$0.99"):
        ctx.admin.reopen(su, z["user_ID"])
    assert ctx.users.get(z["user_ID"])["status"] == "SUSPENDED"


def test_reopen_after_customer_deposit_resets_warnings(ctx):
    su = session_for(ctx, "admin")
    z = ctx.users.by_username("zakiah")
    ctx.store.update("users", "user_ID", z["user_ID"], {"warnings": 3})
    ctx.wallet.deposit(session_for(ctx, "zakiah"), "10")
    u = ctx.admin.reopen(su, z["user_ID"])
    assert u["status"] == "ACTIVE" and u["warnings"] == 0
    assert ctx.store.read_all("status_changes")[-1]["to_Status"] == "ACTIVE"
    assert ctx.store.read_all("admin_actions")[-1]["action"] == "REOPEN_ACCOUNT"
    assert ctx.auth.verify_sign_in("zakiah", face(16)).session.wallet_only is False


def test_reopen_with_deposit_recorded_by_su(ctx):
    su = session_for(ctx, "admin")
    z = ctx.users.by_username("zakiah")
    u = ctx.admin.reopen(su, z["user_ID"], "20")
    assert u["status"] == "ACTIVE" and u["balance"] == 19.01
    assert ctx.wallet.ledger(z["user_ID"])[0]["note"] == "Deposit recorded by Super-User"


def test_reopen_already_reopened(ctx):
    su = session_for(ctx, "admin")
    z = ctx.users.by_username("zakiah")
    ctx.admin.reopen(su, z["user_ID"], "5")
    with pytest.raises(NotFoundError, match="already reopened"):
        ctx.admin.reopen(session_for(ctx, "yixin"), z["user_ID"])


def test_only_su_reopens(ctx):
    with pytest.raises(PermissionDenied):
        ctx.admin.reopen(session_for(ctx, "alice"), ctx.users.by_username("zakiah")["user_ID"])


# ---------------------------------------------------------------- UC-18
def test_order_lists_sorted(ctx):
    su = session_for(ctx, "admin")
    lists = ctx.ratings.order_lists(su)
    assert [b["title"] for b in lists["to_order"]] == ["Moby Dick"]
    assert [b["title"] for b in lists["no_order"]] == ["The Parent's Assistant"]
    bid = book_id(ctx, "Frankenstein")
    for n in ("alice", "evan", "ibrahim", "selina"):
        ctx.reviews.submit(session_for(ctx, n), bid, 5, "Wow")
    to = ctx.ratings.order_lists(su)["to_order"]
    assert [b["weighted_Avg"] for b in to] == sorted([b["weighted_Avg"] for b in to], reverse=True)


def test_recalculate_all_repairs_stale_values(ctx):
    su = session_for(ctx, "admin")
    bid = book_id(ctx, "Moby Dick")
    ctx.store.update("books", "book_ID", bid, {"list_Status": "NONE", "weighted_Avg": 0.0})
    assert ctx.ratings.order_lists(su)["to_order"] == []
    ctx.ratings.recalculate_all(su)
    assert [b["book_ID"] for b in ctx.ratings.order_lists(su)["to_order"]] == [bid]


def test_empty_lists_message(ctx):
    su = session_for(ctx, "admin")
    ctx.store.write_all("reviews", [])
    ctx.ratings.recalculate_all(su)
    assert ctx.ratings.order_lists(su)["message"] == "No books meet the thresholds yet"


def test_only_su_sees_lists(ctx):
    with pytest.raises(PermissionDenied):
        ctx.ratings.order_lists(session_for(ctx, "selina"))
