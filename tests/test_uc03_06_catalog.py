"""UC-03 View Popular Books, UC-04 Browse and Search Books,
UC-05 View Book Details and Reviews, UC-06 Receive Personalized Recommendations."""
import cv2
import numpy as np
import pytest

from bookorbit.errors import BiometricError, NotFoundError
from bookorbit.services.base import Session
from tests.helpers import book_id, session_for


# ---------------------------------------------------------------- UC-03
def test_popular_books_ranked_by_views_plus_3x_purchases(ctx):
    top = ctx.recs.popular(3)
    assert len(top) == 3
    scores = [b["browse_Count"] + 3 * b["purchase_Count"] for b in top]
    assert scores == sorted(scores, reverse=True)
    best_other = max(b["browse_Count"] + 3 * b["purchase_Count"] for b in ctx.store.read_all("books")
                     if b["book_ID"] not in {t["book_ID"] for t in top})
    assert min(scores) >= best_other


def test_visitor_and_su_home_show_popular_books(ctx):
    for s in (Session(), session_for(ctx, "admin")):
        rec = ctx.recs.personalized(s, 3)
        assert not rec["personal"] and len(rec["books"]) == 3


def test_popular_with_small_or_empty_catalog(ctx):
    books = ctx.store.read_all("books")
    ctx.store.write_all("books", books[:2])
    assert len(ctx.recs.popular(3)) == 2
    ctx.store.write_all("books", [])
    assert ctx.recs.popular(3) == []


# ---------------------------------------------------------------- UC-04
def test_browse_by_category_author_title_keyword(ctx):
    sci = ctx.catalog.search(category="Science")
    assert sci.total == 3 and all(b["category"] == "Science" for b in sci.books)
    austen = ctx.catalog.search(query="austen", field="author")
    assert austen.total == 4
    assert ctx.catalog.search(query="moby", field="title").books[0]["title"] == "Moby Dick"
    kw = ctx.catalog.search(query="whale", field="keyword")
    assert [b["title"] for b in kw.books] == ["Moby Dick"]


def test_search_by_year_range_and_invalid_range(ctx):
    r = ctx.catalog.search(query="1800-1820", field="year")
    assert r.total > 0 and all(1800 <= b["pub_Year"] <= 1820 for b in r.books)
    bad = ctx.catalog.search(query="1900-1800", field="year")
    assert "year" in bad.errors and bad.total == 0
    bad2 = ctx.catalog.search(query="nineteen", field="year")
    assert "year" in bad2.errors


def test_twelve_per_page_and_no_results(ctx):
    r1 = ctx.catalog.search(page=1)
    r3 = ctx.catalog.search(page=3)
    assert len(r1.books) == 12 and r1.pages == 3 and len(r3.books) == 32 - 24
    none = ctx.catalog.search(query="zzzz-no-such-book")
    assert none.total == 0 and none.message == "No books found"


def _photo_of_cover(path):
    img = cv2.imread(str(path))
    h, w = img.shape[:2]
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[30, 20], [w - 10, 0], [w - 25, h - 15], [0, h - 30]])
    warped = cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, dst), (w + 30, h + 30),
                                 borderValue=(210, 210, 210))
    warped = cv2.convertScaleAbs(cv2.GaussianBlur(warped, (3, 3), 0), alpha=0.9, beta=15)
    return cv2.imencode(".jpg", warped)[1].tobytes()


@pytest.mark.parametrize("title", ["Moby Dick", "Emma", "Relativity: The Special and General Theory", "Hamlet"])
def test_cover_search_finds_book_from_a_photo(ctx, title):
    bid = book_id(ctx, title)
    res = ctx.catalog.cover_search(_photo_of_cover(ctx.config.data_dir / f"covers/{bid}.png"))
    assert res.books[0]["book_ID"] == bid
    assert len(res.books) <= 5 and all(s >= 0.25 for s in res.similarities.values())


def test_cover_search_rejects_non_images(ctx):
    with pytest.raises(BiometricError, match="JPG or PNG"):
        ctx.catalog.cover_search(b"this is not an image")


# ---------------------------------------------------------------- UC-05
def test_view_adds_one_view_and_records_it_for_customers(ctx):
    bid = book_id(ctx, "Dracula")
    before = ctx.catalog.get(bid)["browse_Count"]
    events = len(ctx.store.read_all("browse_history"))
    ctx.catalog.view(bid, Session())                           # visitor: counter only
    assert len(ctx.store.read_all("browse_history")) == events
    ctx.catalog.view(bid, session_for(ctx, "alice"))           # RC: counter + event
    assert ctx.catalog.get(bid)["browse_Count"] == before + 2
    assert ctx.store.read_all("browse_history")[-1]["book_ID"] == bid


def test_vip_sees_vip_price(ctx):
    b = ctx.catalog.get(book_id(ctx, "Emma"))           # $9.99
    assert str(ctx.catalog.display_price(b, "VC")["final"]) == "8.99"
    assert str(ctx.catalog.display_price(b, "RC")["final"]) == "9.99"


def test_removed_book_is_unavailable(ctx):
    with pytest.raises(NotFoundError, match="Book unavailable"):
        ctx.catalog.view("B-9999", Session())


def test_reviews_newest_first(ctx):
    revs = ctx.reviews.published(book_id(ctx, "Moby Dick"))
    assert len(revs) == 4
    keys = [r["created_At"] + r["review_ID"] for r in revs]
    assert keys == sorted(keys, reverse=True)


# ---------------------------------------------------------------- UC-06
def test_personal_recommendations_follow_history_and_skip_owned(ctx):
    s = session_for(ctx, "alice")                       # bought Emma, viewed Austen books
    rec = ctx.recs.personalized(s, 3)
    assert rec["personal"]
    titles = [b["title"] for b in rec["books"]]
    assert "Emma" not in titles
    assert all(b["author"] == "Jane Austen" for b in rec["books"])
    assert all(rec["reasons"][b["book_ID"]] for b in rec["books"])


def test_no_history_gets_popular_books(ctx):
    rec = ctx.recs.personalized(session_for(ctx, "ibrahim"), 3)
    assert not rec["personal"] and rec["title"] == "Popular right now" and len(rec["books"]) == 3


def test_fewer_scored_books_are_filled_with_popular(ctx):
    s = session_for(ctx, "evan")                        # one Children book only
    rec = ctx.recs.personalized(s, 9)
    assert len(rec["books"]) == 9
    assert book_id(ctx, "Alice's Adventures in Wonderland") not in [b["book_ID"] for b in rec["books"]]
