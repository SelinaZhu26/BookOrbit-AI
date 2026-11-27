"""GUI tests: every screen renders for every role and the 18 use cases work
end-to-end through the GUI routes (forms, redirects, messages)."""
import io
import re

import cv2
import pytest

from bookorbit.ui.web import CAPTURES, create_app
from tests.helpers import book_id, face, make_ctx


def png(img):
    return io.BytesIO(cv2.imencode(".png", img)[1].tobytes())


@pytest.fixture
def app_ctx(tmp_path):
    ctx = make_ctx(tmp_path)
    app = create_app(ctx)
    app.config["TESTING"] = True
    CAPTURES.clear()
    return app, ctx


def sign_in(client, username, person):
    r = client.post("/signin", data={"username": username, "step": "username"})
    assert b"Verify face and sign in" in r.data
    return client.post("/signin", data={"username": username, "step": "face",
                                        "face_photo": (png(face(person)), "me.png")},
                       content_type="multipart/form-data", follow_redirects=True)


PAGES = {
    "VS": ["/", "/browse", "/browse?category=Science", "/books/B-0012", "/chat", "/signin", "/register"],
    "RC": ["/", "/browse", "/books/B-0012", "/chat", "/balance", "/orders", "/my-reviews", "/recommendations",
           "/checkout", "/read/B-0001", "/read/B-0012?chapter=3"],
    "SU": ["/", "/browse", "/books/B-0012", "/chat", "/admin/books", "/admin/taboo", "/admin/users",
           "/admin/reports", "/admin/books?add=1", "/admin/taboo?edit=junk"],
}


@pytest.mark.parametrize("role,user,person", [("VS", None, None), ("RC", "alice", 13), ("SU", "admin", 11)])
def test_every_screen_renders(app_ctx, role, user, person):
    app, _ = app_ctx
    c = app.test_client()
    if user:
        assert b"Sign Out" in sign_in(c, user, person).data
    for url in PAGES[role]:
        r = c.get(url)
        assert r.status_code == 200, url
        assert b"Traceback" not in r.data


def test_role_based_sidebar(app_ctx):
    app, _ = app_ctx
    c = app.test_client()
    home = c.get("/").data.decode()
    assert "Register" in home and "My Balance" not in home and "Manage Books" not in home
    sign_in(c, "selina", 14)
    home = c.get("/").data.decode()
    assert "VIP Customer" in home and "My Balance" in home and "Manage Books" not in home
    c.get("/signout")
    sign_in(c, "admin", 11)
    home = c.get("/").data.decode()
    assert all(x in home for x in ("Manage Books", "Taboo Words", "User Management", "Reports"))


def test_permissions_redirect(app_ctx):
    app, _ = app_ctx
    c = app.test_client()
    assert c.get("/admin/users").status_code == 302
    assert "/signin" in c.get("/balance").headers["Location"]
    sign_in(c, "alice", 13)
    r = c.get("/admin/reports", follow_redirects=True)
    assert b"You do not have permission" in r.data


# ------------------------------------------------------------------- UC-01/02
def test_register_then_sign_in_through_gui(app_ctx):
    app, ctx = app_ctx
    c = app.test_client()
    r = c.post("/register", data={"full_name": "Maya Lin", "username": "maya", "email": "maya@x.com", "terms": "1",
                                  "face_photo": (png(face(60)), "m.png")},
               content_type="multipart/form-data", follow_redirects=True)
    assert b"Account created - please sign in" in r.data
    r = sign_in(c, "maya", 60)
    assert b"Maya Lin" in r.data and b"Registered Customer" in r.data


def test_register_errors_keep_values_and_three_bad_photos_cancel(app_ctx):
    app, _ = app_ctx
    c = app.test_client()
    r = c.post("/register", data={"full_name": "Maya", "username": "a", "email": "bad"},
               content_type="multipart/form-data")
    html = r.data.decode()
    assert 'data-error="username"' in html and 'data-error="email"' in html and 'value="Maya"' in html
    for i in range(1, 4):
        r = c.post("/register", data={"full_name": "Maya", "username": "maya2", "email": "m@x.com", "terms": "1",
                                      "face_photo": (png(face(0)), "noface.png")},
                   content_type="multipart/form-data", follow_redirects=True)
        if i < 3:
            assert f"try {i} of 3".encode() in r.data
    assert b"Registration cancelled" in r.data


def test_sign_in_wrong_face_then_lock(app_ctx):
    app, _ = app_ctx
    c = app.test_client()
    assert b"attempt 1 of 3" in sign_in(c, "alice", 90).data
    assert b"attempt 2 of 3" in sign_in(c, "alice", 91).data
    assert b"locked for 5 minutes" in sign_in(c, "alice", 92).data
    r = c.post("/signin", data={"username": "alice", "step": "username"})
    assert b"Too many attempts" in r.data
    r = c.post("/signin", data={"username": "ghost", "step": "username"})
    assert b"No account with that username" in r.data


# ------------------------------------------------------------------- UC-03..06
def test_home_and_search_through_gui(app_ctx):
    app, ctx = app_ctx
    c = app.test_client()
    assert b"Top picks this week" in c.get("/").data
    r = c.get("/browse?field=any&q=1800-1820").data.decode()
    assert "books found" in r and "Emma" in r
    r = c.get("/browse?field=year&q=1900-1800").data.decode()
    assert 'id="year-error"' in r
    r = c.get("/browse?q=zzzz").data.decode()
    assert "No books found" in r and "Clear filters" in r
    img = cv2.imread(str(ctx.config.data_dir / "covers" / f"{book_id(ctx, 'Hamlet')}.png"))
    r = c.post("/browse/cover", data={"cover": (io.BytesIO(cv2.imencode('.jpg', img)[1].tobytes()), "c.jpg")},
               content_type="multipart/form-data").data.decode()
    first = re.search(r'data-book="(B-\d+)"', r).group(1)
    assert first == book_id(ctx, "Hamlet") and "cover match" in r


def test_book_details_buttons_by_role(app_ctx):
    app, ctx = app_ctx
    c = app.test_client()
    emma = book_id(ctx, "Emma")
    html = c.get(f"/books/{emma}").data.decode()
    assert "Sign in to buy" in html and "Open Reading Companion" not in html
    sign_in(c, "alice", 13)
    html = c.get(f"/books/{emma}").data.decode()
    assert "You own this book" in html and "Open Reading Companion" in html and "You reviewed this book" in html
    html = c.get(f"/books/{book_id(ctx, 'Dracula')}").data.decode()
    assert "Buy now" in html and "isn't available for this book" in html


# ------------------------------------------------------------------- UC-07..09
def test_deposit_and_checkout_through_gui(app_ctx):
    app, ctx = app_ctx
    c = app.test_client()
    sign_in(c, "alice", 13)
    r = c.post("/balance/deposit", data={"amount": "abc"}, follow_redirects=True)
    assert b"Enter a valid amount" in r.data
    r = c.post("/balance/deposit", data={"amount": "20"}, follow_redirects=True)
    assert b"$50.02" in r.data
    bid = book_id(ctx, "Persuasion")
    r = c.post(f"/cart/add/{bid}", data={"buy_now": "1"}, follow_redirects=True)
    assert b"Order summary" in r.data and b"$41.53" in r.data           # balance after purchase
    r = c.post("/checkout", follow_redirects=True)
    assert b"Receipt" in r.data and b"Persuasion" in r.data
    assert b"You own this book" in c.get(f"/books/{bid}").data


def test_insufficient_funds_fine_through_gui(app_ctx):
    app, ctx = app_ctx
    c = app.test_client()
    sign_in(c, "evan", 15)                                              # $22.01
    for t in ("Moby Dick", "On the Origin of Species"):
        c.post(f"/cart/add/{book_id(ctx, t)}")
    html = c.get("/checkout").data.decode()
    assert 'id="insufficient"' in html
    r = c.post("/checkout", follow_redirects=True)
    assert b"Insufficient funds: $1.00 fine charged." in r.data
    assert ctx.users.by_username("evan")["balance"] == 21.01


def test_vip_checkout_shows_discount(app_ctx):
    app, ctx = app_ctx
    c = app.test_client()
    sign_in(c, "selina", 14)
    c.post(f"/cart/add/{book_id(ctx, 'Emma')}")
    html = c.get("/checkout").data.decode()
    assert "VIP discount (10%)" in html and "−$1.00" in html and "$8.99" in html


# ------------------------------------------------------------------- UC-10/11
def test_review_masked_blocked_and_suspension_through_gui(app_ctx):
    app, ctx = app_ctx
    c = app.test_client()
    sign_in(c, "evan", 15)
    drac = book_id(ctx, "Frankenstein")
    r = c.post(f"/books/{drac}/review", data={"rating": "4", "comment": "Good but the lab scenes are junk."},
               follow_redirects=True).data.decode()
    assert "Review published - 1 word was masked." in r and "lab scenes are ****." in r
    r = c.post(f"/books/{drac}/review", data={"rating": "1", "comment": "junk stupid trash garbage"},
               follow_redirects=True).data.decode()
    assert "Your comment was blocked" in r and "suspended" in r
    assert "Your account is suspended" in c.get("/balance").data.decode()
    assert c.get("/browse").status_code == 302                         # wallet-only mode


def test_vip_demotion_through_gui(app_ctx):
    app, ctx = app_ctx
    c = app.test_client()
    sign_in(c, "selina", 14)
    r = c.post(f"/books/{book_id(ctx, 'Emma')}/review", data={"rating": "1", "comment": "idiot moron dumb junk"},
               follow_redirects=True).data.decode()
    assert "no longer a VIP Customer" in r and "$9.99" in r and 'id="role-label">Registered Customer' in r


def test_visitor_can_review(app_ctx):
    app, ctx = app_ctx
    c = app.test_client()
    r = c.post(f"/books/{book_id(ctx, 'Dracula')}/review", data={"rating": "5", "comment": "Spooky!"},
               follow_redirects=True).data.decode()
    assert "Review published" in r and "Spooky!" in r and "Visitor" in r


# ------------------------------------------------------------------- UC-12/13
def test_chat_endpoint_by_role(app_ctx):
    app, _ = app_ctx
    c = app.test_client()
    d = c.post("/chat/ask", json={"question": "What are your store hours?"}).get_json()
    assert d["source"] == "RAG" and "RAG" in d["label"]
    d = c.post("/chat/ask", json={"question": "Show the finance report"}).get_json()
    assert d["source"] == "DENIED"
    sign_in(c, "admin", 11)
    d = c.post("/chat/ask", json={"question": "Show the finance report"}).get_json()
    assert d["source"] == "ADMIN" and any(row[0] == "Total sales" for row in d["table"])


# ------------------------------------------------------------------- UC-14
def test_reader_through_gui(app_ctx):
    app, ctx = app_ctx
    c = app.test_client()
    sign_in(c, "alice", 13)
    moby = book_id(ctx, "Moby Dick")
    assert b"Buy the book to keep reading" in c.get(f"/read/{moby}?chapter=4").data
    d = c.post(f"/read/{book_id(ctx, 'Emma')}/act", json={"action": "quiz", "chapter": 2}).get_json()
    assert d["ok"] and len(d["quiz"]) == 3
    a = c.post("/quiz/answer", json={"quiz_ID": d["quiz_ID"], "index": 0, "choice": 0}).get_json()
    assert a["ok"] and "answer" in a
    d = c.post(f"/read/{book_id(ctx, 'Emma')}/act", json={"action": "explain", "chapter": 2}).get_json()
    assert d["message"] == "Select a passage first"


# ------------------------------------------------------------------- UC-15..18
def test_admin_screens_through_gui(app_ctx):
    app, ctx = app_ctx
    c = app.test_client()
    sign_in(c, "admin", 11)
    from tests.test_uc15_18_admin import GOOD, cover_png
    r = c.post("/admin/books", data={**GOOD, "cover": (io.BytesIO(cover_png()), "c.png")},
               content_type="multipart/form-data", follow_redirects=True).data.decode()
    assert "was added to the catalog" in r and "The Odyssey" in r
    r = c.post("/admin/books", data={**GOOD, "price": "0", "cover": (io.BytesIO(cover_png()), "c.png")},
               content_type="multipart/form-data").data.decode()
    assert 'data-error="price"' in r
    r = c.post("/admin/taboo", data={"action": "add", "word": "two words"}).data.decode()
    assert "Enter one word" in r
    r = c.post("/admin/taboo", data={"action": "add", "word": "boring"}, follow_redirects=True).data.decode()
    assert 'data-word="boring"' in r
    zid = ctx.users.by_username("zakiah")["user_ID"]
    r = c.post(f"/admin/users/{zid}/reopen", data={"amount": ""}, follow_redirects=True).data.decode()
    assert "must deposit at least $0.99" in r
    r = c.post(f"/admin/users/{zid}/reopen", data={"amount": "5"}, follow_redirects=True).data.decode()
    assert "ACTIVE again" in r and "No suspended accounts" in r
    r = c.post("/admin/reports", follow_redirects=True).data.decode()
    assert "Recalculated" in r and "Moby Dick" in r


def test_su_can_enrol_a_face_for_a_customer(app_ctx):
    app, ctx = app_ctx
    c = app.test_client()
    ib = ctx.users.by_username("ibrahim")
    ctx.store.delete("biometrics", lambda r: r["user_ID"] == ib["user_ID"])
    sign_in(c, "admin", 11)
    r = c.post(f"/admin/users/{ib['user_ID']}/face", data={"face_photo": (png(face(77)), "f.png")},
               content_type="multipart/form-data", follow_redirects=True)
    assert b"Face template saved" in r.data
    c.get("/signout")
    assert b"Ibrahim Rahat" in sign_in(c, "ibrahim", 77).data
