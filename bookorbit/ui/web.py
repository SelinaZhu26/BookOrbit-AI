"""GUI layer. Every screen of Section 5 of the design report is a route here.
The business rules live in the services; routes only collect input, call a
service and show the result (memo 6.2: "keep the business rules in plain
Python classes, so the interface can change without touching the logic")."""
from __future__ import annotations

import base64
import secrets
import time
from functools import wraps

import cv2
from flask import (Flask, Response, abort, flash, jsonify, redirect, render_template, request,
                   send_from_directory, session as fsession, url_for)

from ..ai.biometric import decode_image
from ..app_context import AppContext
from ..errors import (AccountSuspended, BiometricError, BookOrbitError, NotFoundError, PermissionDenied,
                      StorageError, ValidationError)
from ..money import D, fmt
from ..services.base import ROLE_NAMES, Session
from ..services.chatbot_service import ADMIN_EXAMPLES

CAPTURES: dict[str, dict] = {}     # face frames captured from the webcam, per browser session


def create_app(ctx: AppContext) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = ctx.config.secret_key
    app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
    app.jinja_env.globals.update(fmt=fmt, D=D, ROLE_NAMES=ROLE_NAMES)

    # ------------------------------------------------------------ session
    def current() -> Session:
        s = Session(user_ID=fsession.get("user_ID"), role=fsession.get("role", "VS"),
                    visitor_key=fsession.get("visitor_key"))
        if s.user_ID:
            s = ctx.auth.refresh_session(s)
            if s.user_ID is None:
                fsession.clear()
        if not s.user_ID and not s.visitor_key:
            s.visitor_key = fsession["visitor_key"] = secrets.token_hex(8)
        return s

    def sid() -> str:
        if "sid" not in fsession:
            fsession["sid"] = secrets.token_hex(8)
        return fsession["sid"]

    @app.context_processor
    def inject():
        s = current()
        user = ctx.users.get(s.user_ID) if s.user_ID else None
        cart = fsession.get("cart", [])
        return {"S": s, "me": user, "cart_count": len(cart), "nav": request.endpoint,
                "llm_status": ctx.llm.status_text(), "face_status": ctx.biometric.status_text()}

    def roles(*allowed):
        def deco(fn):
            @wraps(fn)
            def wrapper(*a, **kw):
                s = current()
                if s.role not in allowed:
                    if s.is_visitor:
                        flash("Please sign in first.", "info")
                        return redirect(url_for("signin", next=request.path))
                    flash("You do not have permission to access this page.", "error")
                    return redirect(url_for("home"))
                return fn(*a, **kw)
            return wrapper
        return deco

    WALLET_OK = {"balance", "deposit", "signout", "static", "covers", "home", None}

    @app.before_request
    def wallet_only_guard():
        s = current()
        if s.wallet_only and request.endpoint not in WALLET_OK:
            if request.accept_mimetypes.best == "application/json" or request.is_json:
                return jsonify({"ok": False, "message": "Your account is suspended (wallet-only mode)."}), 403
            flash("Your account is suspended - only My Balance is available until a Super-User reopens it.", "error")
            return redirect(url_for("balance"))

    @app.errorhandler(PermissionDenied)
    def _perm(exc):
        flash(exc.message, "error")
        return redirect(url_for("home"))

    @app.errorhandler(404)
    def _404(exc):
        return render_template("error.html", message="Page not found"), 404

    # ------------------------------------------------------------ files
    @app.route("/favicon.ico")
    def favicon():
        return send_from_directory(app.static_folder, "favicon.svg", mimetype="image/svg+xml")

    @app.route("/covers/<path:name>")
    def covers(name):
        return send_from_directory(ctx.config.covers_dir, name, max_age=3600)

    # ============================================== Home (UC-03/04/06/07/14)
    @app.route("/")
    def home():
        s = current()
        if s.wallet_only:
            return redirect(url_for("balance"))
        rec = ctx.recs.personalized(s, 3)
        ctxv = {"rec": rec}
        if s.is_customer:
            ctxv["reading"] = ctx.companion.latest(s.user_ID)
        if s.role == "SU":
            ctxv["lists"] = ctx.ratings.order_lists(s)
            ctxv["suspended"] = ctx.admin.suspended(s)
            ctxv["actions"] = ctx.admin.recent_actions(s, 5)
        return render_template("home.html", **ctxv)

    # ============================================== UC-01 Register
    @app.route("/register", methods=["GET", "POST"])
    def register():
        s = current()
        if not s.is_visitor:
            return redirect(url_for("home"))
        form = {"full_name": "", "username": "", "email": ""}
        errors, face_error = {}, None
        tries = fsession.get("reg_tries", 0)
        if request.method == "POST":
            form = {k: request.form.get(k, "").strip() for k in form}
            errors = ctx.auth.validate_registration(form["full_name"], form["username"], form["email"])
            if not request.form.get("terms"):
                errors["terms"] = "Please accept the terms"
            images = _face_images(sid())
            if not images:
                face_error = "Capture a face photo with the camera (or choose a photo file)."
                if not ctx.camera.available():
                    face_error = ("No camera is connected - connect a camera, or choose a photo file "
                                  "of your face.")
            if not errors and images:
                try:
                    ctx.auth.register(form["full_name"], form["username"], form["email"], images)
                    CAPTURES.pop(sid(), None)
                    fsession.pop("reg_tries", None)
                    flash("Account created - please sign in", "success")
                    return redirect(url_for("signin", username=form["username"]))
                except ValidationError as exc:
                    errors.update(exc.fields)
                except BiometricError as exc:
                    CAPTURES.pop(sid(), None)
                    tries += 1
                    fsession["reg_tries"] = tries
                    if tries >= ctx.config.register_max_tries:
                        fsession.pop("reg_tries", None)
                        flash("Registration cancelled after 3 photos without exactly one face.", "error")
                        return redirect(url_for("home"))
                    face_error = f"{exc.message} (try {tries} of {ctx.config.register_max_tries})"
                except StorageError as exc:
                    flash(exc.message, "error")
        return render_template("register.html", form=form, errors=errors, face_error=face_error,
                               camera=ctx.camera.available(), bio_ok=ctx.biometric.available)

    def _face_images(key: str) -> list:
        f = request.files.get("face_photo")
        if f and f.filename:
            try:
                return [decode_image(f.read())]
            except BiometricError:
                return []
        cap = CAPTURES.get(key)
        if cap and time.time() - cap["at"] < 300:
            return cap["frames"]
        return []

    # ============================================== UC-02 Sign in
    @app.route("/signin", methods=["GET", "POST"])
    def signin():
        s = current()
        if not s.is_visitor:
            return redirect(url_for("home"))
        username = request.values.get("username", "").strip()
        step = "username"
        error = None
        if request.method == "POST":
            try:
                ctx.auth.start_sign_in(username)
                step = "face"
                if request.form.get("step") == "face":
                    images = _face_images(sid())
                    if not images:
                        error = "Capture a face sample first (or choose a photo file)."
                    else:
                        result = ctx.auth.verify_sign_in(username, images[0])
                        CAPTURES.pop(sid(), None)
                        if result.ok:
                            fsession.clear()
                            fsession["user_ID"] = result.session.user_ID
                            fsession["role"] = result.session.role
                            if result.session.wallet_only:
                                flash(result.message, "error")
                            nxt = request.args.get("next")
                            if result.session.wallet_only:
                                return redirect(url_for("balance"))
                            return redirect(nxt if nxt and nxt.startswith("/") else url_for("home"))
                        error = result.message
                        if result.locked:
                            step = "username"
            except NotFoundError as exc:
                error = exc.message
            except BiometricError as exc:
                error = exc.message
                step = "username"
        elif username and request.args.get("username"):
            step = "username"
        return render_template("signin.html", username=username, step=step, error=error,
                               camera=ctx.camera.available(), bio_ok=ctx.biometric.available)

    @app.route("/signout")
    def signout():
        cart_free = {"visitor_key": secrets.token_hex(8)}
        fsession.clear()
        fsession.update(cart_free)
        flash("You have signed out.", "info")
        return redirect(url_for("home"))

    # ------------------------------------------------------- camera
    @app.route("/camera/stream")
    def camera_stream():
        if not ctx.camera.available():
            abort(404)
        return Response(ctx.camera.mjpeg(), mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.route("/face/capture", methods=["POST"])
    def face_capture():
        """Take 3 frames from the webcam (UC-01 training samples / UC-02 sample)."""
        frames = []
        for _ in range(3 if request.args.get("purpose") == "register" else 1):
            f = ctx.camera.snapshot()
            if f is not None:
                frames.append(f)
            time.sleep(0.25)
        if not frames:
            return jsonify({"ok": False, "message": "No camera is available - choose a photo file instead."})
        return _face_preview(frames)

    @app.route("/face/upload", methods=["POST"])
    def face_upload():
        f = request.files.get("face_photo")
        try:
            img = decode_image(f.read() if f else b"")
        except BiometricError as exc:
            return jsonify({"ok": False, "message": exc.message})
        return _face_preview([img])

    def _face_preview(frames):
        try:
            faces = ctx.biometric.detect(frames[0])
        except BiometricError as exc:
            return jsonify({"ok": False, "message": exc.message})
        img = frames[0].copy()
        for fc in faces:
            x, y, w, h = map(int, fc.box)
            cv2.rectangle(img, (x, y), (x + w, y + h), (74, 176, 232), max(2, img.shape[1] // 200))
        scale = 360 / max(img.shape[:2])
        img = cv2.resize(img, None, fx=scale, fy=scale) if scale < 1 else img
        ok, jpg = cv2.imencode(".jpg", img)
        CAPTURES[sid()] = {"frames": frames, "at": time.time()}
        msg = {0: "No face found - look at the camera and try again.",
               1: "Face found - looks good."}.get(len(faces), "More than one face found - make sure only your face is visible.")
        return jsonify({"ok": len(faces) == 1, "faces": len(faces), "message": msg,
                        "preview": "data:image/jpeg;base64," + base64.b64encode(jpg.tobytes()).decode()})

    # ============================================== UC-04 Browse & Search
    @app.route("/browse")
    def browse():
        a = request.args
        field = a.get("field", "title")
        q = a.get("q", "")
        if field == "any":       # home search box: year range or keyword
            import re as _re
            field = "year" if _re.fullmatch(r"\s*\d{1,4}\s*([-–]|to)?\s*(\d{1,4})?\s*", q or "-") and q else "keyword"
        res = ctx.catalog.search(a.get("category", ""), q, field, a.get("year_from", ""), a.get("year_to", ""),
                                 a.get("sort", "title"), a.get("page", 1))
        return render_template("browse.html", res=res, categories=ctx.catalog.categories(),
                               args={**a.to_dict(), "field": field}, cover_mode=False,
                               cover_ok=ctx.covers.available)

    @app.route("/browse/cover", methods=["POST"])
    def cover_search():
        f = request.files.get("cover")
        try:
            res = ctx.catalog.cover_search(f.read() if f else b"")
        except BiometricError as exc:
            flash(exc.message, "error")
            return redirect(url_for("browse"))
        return render_template("browse.html", res=res, categories=ctx.catalog.categories(),
                               args={}, cover_mode=True, cover_ok=ctx.covers.available)

    # ============================================== UC-05 Book details
    @app.route("/books/<book_ID>")
    def book(book_ID):
        s = current()
        try:
            b = ctx.catalog.view(book_ID, s)
        except NotFoundError:
            flash("Book unavailable", "error")
            return redirect(url_for("browse"))
        owned = s.is_customer and ctx.purchases.owns(s.user_ID, book_ID)
        reviews = ctx.reviews.published(book_ID)
        user = ctx.users.get(s.user_ID) if s.user_ID else None
        return render_template("book.html", b=b, price=ctx.catalog.display_price(b, s.role), owned=owned,
                               reviews=reviews, breakdown=ctx.ratings.breakdown(book_ID),
                               own_review=ctx.reviews.own_review(s, book_ID),
                               suspended=bool(user and user["status"] == "SUSPENDED"),
                               has_text=bool(b.get("text_Path")), in_cart=book_ID in fsession.get("cart", []),
                               result=fsession.pop("review_result", None))

    # ============================================== UC-10/11 Review
    @app.route("/books/<book_ID>/review", methods=["POST"])
    def review(book_ID):
        s = current()
        try:
            out = ctx.reviews.submit(s, book_ID, request.form.get("rating"), request.form.get("comment", ""))
            if out["status"] == "BLOCKED":
                outcome = (out["warning"] or {}).get("outcome")
                if outcome == "SUSPENDED":                 # straight to wallet-only mode
                    flash(out["message"], "error")
                    return redirect(url_for("balance"))
                fsession["review_result"] = {"kind": "blocked", "message": out["message"], "outcome": outcome}
            else:
                fsession["review_result"] = {"kind": "published", "message": out["message"]}
        except ValidationError as exc:
            fsession["review_result"] = {"kind": "invalid", "message": exc.message,
                                         "rating": request.form.get("rating"),
                                         "comment": request.form.get("comment", "")}
        except (AccountSuspended, NotFoundError) as exc:
            fsession["review_result"] = {"kind": "blocked", "message": exc.message}
        return redirect(url_for("book", book_ID=book_ID) + "#reviews")

    # ============================================== Cart / Checkout (UC-08/09)
    @app.route("/cart/add/<book_ID>", methods=["POST"])
    @roles("RC", "VC")
    def cart_add(book_ID):
        s = current()
        if ctx.purchases.owns(s.user_ID, book_ID):
            flash("You already own this book", "info")
            return redirect(url_for("book", book_ID=book_ID))
        cart = fsession.get("cart", [])
        if book_ID not in cart:
            cart.append(book_ID)
        fsession["cart"] = cart
        if request.form.get("buy_now"):
            fsession["cart"] = [book_ID] + [c for c in cart if c != book_ID]
            return redirect(url_for("checkout"))
        flash("Added to your cart.", "success")
        return redirect(url_for("book", book_ID=book_ID))

    @app.route("/cart/remove/<book_ID>", methods=["POST"])
    @roles("RC", "VC")
    def cart_remove(book_ID):
        fsession["cart"] = [c for c in fsession.get("cart", []) if c != book_ID]
        return redirect(url_for("checkout"))

    @app.route("/checkout", methods=["GET", "POST"])
    @roles("RC", "VC")
    def checkout():
        s = current()
        cart = [c for c in fsession.get("cart", []) if ctx.store.find("books", book_ID=c)]
        fsession["cart"] = cart
        if request.method == "POST":
            try:
                result = ctx.purchases.checkout(s, cart)
            except BookOrbitError as exc:
                flash(exc.message, "error")
                return redirect(url_for("checkout"))
            if result.ok:
                fsession["cart"] = []
                fsession["receipt"] = {"lines": [{"title": r["title"], "book_ID": r["book_ID"],
                                                  "paid": r["paid"], "list": r["list_Price"],
                                                  "label": r["label"]} for r in result.receipt],
                                       "total": str(result.total), "balance": str(result.balance),
                                       "promoted": result.promoted}
                return redirect(url_for("receipt"))
            flash(result.message, "error")
            if result.suspended:
                return redirect(url_for("balance"))
            return redirect(url_for("checkout"))
        quote = ctx.purchases.quote(s, cart) if cart else None
        user = ctx.users.get(s.user_ID)
        return render_template("checkout.html", quote=quote, user=user)

    @app.route("/receipt")
    @roles("RC", "VC")
    def receipt():
        r = fsession.get("receipt")
        if not r:
            return redirect(url_for("orders"))
        return render_template("receipt.html", r=r)

    # ============================================== UC-07 Balance
    @app.route("/balance")
    @roles("RC", "VC")
    def balance():
        s = current()
        user = ctx.users.get(s.user_ID)
        return render_template("balance.html", user=user, ledger=ctx.wallet.ledger(s.user_ID),
                               amount_error=fsession.pop("amount_error", None),
                               status_log=ctx.status.history(s.user_ID)[:5])

    @app.route("/balance/deposit", methods=["POST"])
    @roles("RC", "VC")
    def deposit():
        s = current()
        try:
            out = ctx.wallet.deposit(s, request.form.get("amount", ""))
            flash(f"Added {fmt(out['txn']['amount'])}. New balance {fmt(out['user']['balance'])}.", "success")
            if out["note"]:
                flash(out["note"], "info")
        except ValidationError as exc:
            fsession["amount_error"] = exc.message
        except StorageError:
            flash("Could not save the deposit - nothing was changed.", "error")
        return redirect(url_for("balance"))

    # ============================================== Orders, reviews, recs
    @app.route("/orders")
    @roles("RC", "VC")
    def orders():
        s = current()
        return render_template("orders.html", orders=ctx.purchases.orders(s.user_ID))

    @app.route("/my-reviews")
    @roles("RC", "VC")
    def my_reviews():
        s = current()
        user = ctx.users.get(s.user_ID)
        return render_template("my_reviews.html", reviews=ctx.reviews.for_user(s.user_ID),
                               warnings=ctx.warnings.for_user(s.user_ID), user=user)

    @app.route("/recommendations")
    @roles("RC", "VC")
    def recommendations():
        s = current()
        return render_template("recommendations.html", rec=ctx.recs.personalized(s, 9))

    # ============================================== UC-12/13 Chatbot
    @app.route("/chat")
    def chat():
        s = current()
        examples = {"VS": ["What are your store hours?", "How much does Moby Dick cost?", "How do I become VIP?"],
                    "RC": ["What is my balance?", "Recommend me a book", "Who wrote Leaves of Grass?"],
                    "VC": ["Who is Ahab in Moby Dick?", "Recommend me a book", "How much have I saved as a VIP?"],
                    "SU": ADMIN_EXAMPLES[:3] + ["Can I get a refund?"]}[s.role]
        return render_template("chat.html", examples=examples)

    @app.route("/chat/ask", methods=["POST"])
    def chat_ask():
        s = current()
        q = (request.get_json(silent=True) or {}).get("question", "")
        ans = ctx.chatbot.ask(s, q)
        return jsonify({"text": ans.text, "label": ans.label, "source": ans.source, "table": ans.table,
                        "examples": ans.examples,
                        "books": [{"book_ID": b["book_ID"], "title": b["title"], "author": b["author"],
                                   "cover": url_for("covers", name=b["cover_Path"].split("/")[-1])}
                                  for b in ans.books]})

    # ============================================== UC-14 Reading Companion
    @app.route("/read/<book_ID>")
    @roles("RC", "VC")
    def read(book_ID):
        s = current()
        try:
            ch = request.args.get("chapter")
            view = ctx.companion.open(s, book_ID, int(ch) if ch and ch.isdigit() else None)
        except NotFoundError as exc:
            flash(exc.message, "error")
            return redirect(url_for("book", book_ID=book_ID))
        return render_template("reader.html", v=view, llm_ok=ctx.llm.available())

    @app.route("/read/<book_ID>/act", methods=["POST"])
    @roles("RC", "VC")
    def read_act(book_ID):
        s = current()
        d = request.get_json(silent=True) or {}
        try:
            out = ctx.companion.act(s, book_ID, int(d.get("chapter", 1)), d.get("action", ""),
                                    d.get("selection", ""), d.get("question", ""))
        except BookOrbitError as exc:
            out = {"ok": False, "message": exc.message}
        return jsonify(out)

    @app.route("/quiz/answer", methods=["POST"])
    @roles("RC", "VC")
    def quiz_answer():
        d = request.get_json(silent=True) or {}
        try:
            return jsonify({"ok": True, **ctx.companion.check_answer(d.get("quiz_ID", ""), int(d.get("index", -1)),
                                                                     int(d.get("choice", -1)))})
        except (BookOrbitError, ValueError) as exc:
            return jsonify({"ok": False, "message": getattr(exc, "message", str(exc))})

    # ============================================== UC-15 Manage books
    @app.route("/admin/books", methods=["GET", "POST"])
    @roles("SU")
    def admin_books():
        s = current()
        errors, form = {}, {}
        if request.method == "POST":
            form = request.form.to_dict()
            cover = request.files.get("cover")
            text = request.files.get("text")
            try:
                b = ctx.catalog.add_book(s, form, cover.read() if cover and cover.filename else None,
                                         text.read() if text and text.filename else None)
                flash(f"“{b['title']}” was added to the catalog"
                      + ("" if b["indexed"] else " (it will be indexed at the next start-up)") + ".", "success")
                return redirect(url_for("admin_books"))
            except ValidationError as exc:
                errors = exc.fields
                flash(exc.message, "error")
        books = sorted(ctx.catalog.all_books(), key=lambda b: b["book_ID"], reverse=True)
        return render_template("admin_books.html", books=books, errors=errors, form=form,
                               categories=ctx.catalog.categories(), open_form=bool(errors) or request.args.get("add"))

    # ============================================== UC-16 Taboo words
    @app.route("/admin/taboo", methods=["GET", "POST"])
    @roles("SU")
    def admin_taboo():
        s = current()
        error = None
        if request.method == "POST":
            action = request.form.get("action")
            try:
                if action == "add":
                    w = ctx.taboo.add(s, request.form.get("word", ""))
                    flash(f"“{w}” added - it applies to reviews submitted from now on.", "success")
                elif action == "edit":
                    w = ctx.taboo.edit(s, request.form.get("old", ""), request.form.get("word", ""))
                    flash(f"Word changed to “{w}”.", "success")
                elif action == "delete":
                    ctx.taboo.delete(s, request.form.get("old", ""))
                    flash("Word removed.", "success")
                return redirect(url_for("admin_taboo"))
            except ValidationError as exc:
                error = exc.message
            except NotFoundError as exc:
                flash(exc.message, "info")
                return redirect(url_for("admin_taboo"))
        return render_template("admin_taboo.html", words=ctx.taboo.records(), error=error,
                               edit=request.args.get("edit"))

    # ============================================== UC-17 Users
    @app.route("/admin/users")
    @roles("SU")
    def admin_users():
        s = current()
        users = ctx.admin.users_list(s)
        return render_template("admin_users.html", suspended=[u for u in users if u["status"] == "SUSPENDED"],
                               users=users, camera=ctx.camera.available(),
                               errors=fsession.pop("reopen_errors", {}))

    @app.route("/admin/users/<user_ID>/reopen", methods=["POST"])
    @roles("SU")
    def admin_reopen(user_ID):
        s = current()
        try:
            u = ctx.admin.reopen(s, user_ID, request.form.get("amount", ""))
            flash(f"{u['full_Name']}'s account is ACTIVE again (warnings reset to 0).", "success")
        except ValidationError as exc:
            fsession["reopen_errors"] = {user_ID: exc.message}
        except NotFoundError as exc:
            flash(exc.message, "info")
        return redirect(url_for("admin_users"))

    @app.route("/admin/users/<user_ID>/face", methods=["POST"])
    @roles("SU")
    def admin_face(user_ID):
        s = current()
        images = _face_images(sid())
        if not images:
            flash("Capture or choose a face photo first.", "error")
            return redirect(url_for("admin_users"))
        try:
            ctx.auth.enroll(user_ID, images)
            ctx.admin.log(s, "ENROLL_FACE", user_ID)
            CAPTURES.pop(sid(), None)
            flash("Face template saved - the user can now sign in.", "success")
        except BiometricError as exc:
            flash(exc.message, "error")
        return redirect(url_for("admin_users"))

    # ============================================== UC-18 Reports
    @app.route("/admin/reports", methods=["GET", "POST"])
    @roles("SU")
    def admin_reports():
        s = current()
        if request.method == "POST":
            n = ctx.ratings.recalculate_all(s)
            flash(f"Recalculated the ratings and lists of {n} books.", "success")
            return redirect(url_for("admin_reports"))
        return render_template("admin_reports.html", lists=ctx.ratings.order_lists(s),
                               facts=ctx.admin.finance_facts(s))

    return app
