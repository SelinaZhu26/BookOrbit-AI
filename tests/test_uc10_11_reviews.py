"""UC-10 Submit Book Reviews, UC-11 Receive Review Warnings (spec item 7)."""
import pytest

from bookorbit.errors import AccountSuspended, ValidationError
from bookorbit.services.base import Session
from bookorbit.services.review_service import ModerationEngine
from tests.helpers import book_id, session_for


def test_moderation_masks_whole_words_same_length_case_insensitive():
    m = ModerationEngine(3).check("This STUPID book is not stupidity, just Junk.", ["stupid", "junk"])
    assert m.taboo_count == 2 and not m.blocked
    assert m.display_text == "This ****** book is not stupidity, just ****."


def test_more_than_three_taboo_words_blocks():
    assert not ModerationEngine(3).check("idiot dumb trash", ["idiot", "dumb", "trash"]).blocked
    assert ModerationEngine(3).check("idiot dumb trash idiot", ["idiot", "dumb", "trash"]).blocked


def test_published_review_masks_and_updates_weighted_rating(ctx):
    s = session_for(ctx, "alice")
    bid = book_id(ctx, "Dracula")
    out = ctx.reviews.submit(s, bid, 4, "Creepy and fun, only the ending felt like junk.")
    assert out["status"] == "PUBLISHED" and out["masked"] == 1
    assert out["review"]["display_Text"].endswith("felt like ****.")
    assert out["review"]["weight"] == 1.0                      # did not buy it
    b = ctx.catalog.get(bid)
    assert b["rating_Count"] == 1 and b["weighted_Avg"] == 4.0


def test_verified_buyer_counts_double(ctx):
    bid = book_id(ctx, "Emma")                                 # alice bought Emma and rated 4
    ctx.reviews.submit(session_for(ctx, "evan"), bid, 1, "Not for me.")
    b = ctx.catalog.get(bid)
    assert b["weighted_Avg"] == round((4 * 2 + 1) / 3, 2)


def test_more_than_3_ratings_put_book_on_order_lists(ctx):
    bid = book_id(ctx, "Frankenstein")
    for name, stars in (("alice", 5), ("evan", 5), ("ibrahim", 4)):
        ctx.reviews.submit(session_for(ctx, name), bid, stars, "Great.")
    assert ctx.catalog.get(bid)["list_Status"] == "NONE"       # 3 ratings is not "more than 3"
    out = ctx.reviews.submit(session_for(ctx, "selina"), bid, 5, "Brilliant.")
    assert ctx.catalog.get(bid)["list_Status"] == "TO_ORDER" and "To-Order" in out["message"]
    bid2 = book_id(ctx, "Dracula")
    for name in ("alice", "evan", "ibrahim", "selina"):
        ctx.reviews.submit(session_for(ctx, name), bid2, 1, "Boring.")
    assert ctx.catalog.get(bid2)["list_Status"] == "NO_ORDER"


@pytest.mark.parametrize("rating,comment", [(0, "ok"), (6, "ok"), (None, "ok"), (3, ""), (3, "x" * 1001)])
def test_invalid_review_input(ctx, rating, comment):
    with pytest.raises(ValidationError, match="1-5 stars"):
        ctx.reviews.submit(session_for(ctx, "alice"), book_id(ctx, "Dracula"), rating, comment)


def test_suspended_customer_cannot_review(ctx):
    with pytest.raises(AccountSuspended):
        ctx.reviews.submit(session_for(ctx, "zakiah"), book_id(ctx, "Dracula"), 5, "Hi")


def test_any_user_can_review_spec_item_7(ctx):
    bid = book_id(ctx, "Dracula")
    v = ctx.reviews.submit(Session(visitor_key="abc"), bid, 3, "Visitor opinion.")
    su = ctx.reviews.submit(session_for(ctx, "admin"), bid, 4, "Staff pick.")
    assert v["status"] == su["status"] == "PUBLISHED"
    assert v["review"]["author_Name"] == "Visitor" and v["review"]["weight"] == 1.0


def test_editing_own_review_replaces_it(ctx):
    s = session_for(ctx, "alice")
    bid = book_id(ctx, "Dracula")
    ctx.reviews.submit(s, bid, 2, "first")
    ctx.reviews.submit(s, bid, 5, "changed my mind")
    mine = [r for r in ctx.reviews.published(bid) if r["user_ID"] == s.user_ID]
    assert len(mine) == 1 and mine[0]["rating"] == 5
    assert ctx.catalog.get(bid)["rating_Count"] == 1


# ---------------------------------------------------------------- UC-11
BAD = "This is junk, stupid trash and total garbage."          # 4 taboo words


def test_blocked_comment_gives_warning_n_of_3(ctx):
    s = session_for(ctx, "alice")
    out = ctx.reviews.submit(s, book_id(ctx, "Dracula"), 1, BAD)
    assert out["status"] == "BLOCKED" and out["warning"]["outcome"] == "WARNED"
    assert "Warning 1 of 3" in out["message"]
    assert ctx.users.get(s.user_ID)["warnings"] == 1
    assert ctx.reviews.published(book_id(ctx, "Dracula")) == []          # never shown
    assert ctx.warnings.for_user(s.user_ID)[0]["review_ID"] == out["review"]["review_ID"]


def test_rc_with_more_than_2_warnings_is_suspended(ctx):
    s = session_for(ctx, "evan")                                         # already 2 warnings
    out = ctx.reviews.submit(s, book_id(ctx, "Dracula"), 1, BAD)
    assert out["warning"]["outcome"] == "SUSPENDED"
    u = ctx.users.get(s.user_ID)
    assert u["status"] == "SUSPENDED" and u["warnings"] == 3


def test_vip_with_blocked_comment_is_demoted_and_counters_reset(ctx):
    s = session_for(ctx, "selina")
    out = ctx.reviews.submit(s, book_id(ctx, "Dracula"), 1, BAD)
    assert out["warning"]["outcome"] == "DEMOTED"
    u = ctx.users.get(s.user_ID)
    assert u["role"] == "RC" and u["status"] == "ACTIVE" and u["warnings"] == 1
    assert u["promo_Purchases"] == 0 and u["promo_Spent"] == 0
    b = ctx.catalog.get(book_id(ctx, "Emma"))
    assert ctx.catalog.display_price(b, u["role"])["vip"] is False


def test_visitor_blocked_comment_has_no_account_to_warn(ctx):
    out = ctx.reviews.submit(Session(visitor_key="v1"), book_id(ctx, "Dracula"), 1, BAD)
    assert out["status"] == "BLOCKED" and out["warning"] is None


def test_new_taboo_word_applies_to_new_reviews(ctx):
    su = session_for(ctx, "admin")
    ctx.taboo.add(su, "boring")
    out = ctx.reviews.submit(session_for(ctx, "alice"), book_id(ctx, "Dracula"), 2, "So boring.")
    assert out["review"]["display_Text"] == "So ******."
