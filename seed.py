"""Create (or reset) the demo data in data/.

    python seed.py                     # reset data/ with the demo catalog and users
    python seed.py --faces photos/     # also enrol faces from photos/<username>.jpg
    python seed.py --keep              # do nothing if data/ already has users

Demo accounts (enrol a face for each one you want to sign in with, see README):
    admin, yixin  Super-Users
    alice         Registered Customer, $30.02, some history
    selina        VIP Customer, $85.00
    evan          Registered Customer with 2 warnings (next blocked comment suspends him)
    zakiah        Suspended (balance -$1.00) - use her to try UC-17
    ibrahim       Registered Customer, $250.00, no history yet
"""
from __future__ import annotations

import argparse
import random
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402

from bookorbit import clock  # noqa: E402
from bookorbit.app_context import AppContext  # noqa: E402
from bookorbit.config import Config  # noqa: E402
from bookorbit.money import D  # noqa: E402
from bookorbit.persistence.filestore import FILES  # noqa: E402
from bookorbit.seed_catalog import BOOKS, POLICIES, TABOO_WORDS, USERS  # noqa: E402
from bookorbit.services.base import Session  # noqa: E402


def reset(config: Config) -> None:
    d = config.data_dir
    d.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        (d / f"{name}.txt").write_text("", encoding="utf-8")
    for sub in ("covers", "texts", "biometrics"):
        shutil.rmtree(d / sub, ignore_errors=True)
        (d / sub).mkdir()


def seed(config: Config | None = None, faces_dir: Path | None = None, quiet: bool = False,
         ctx: AppContext | None = None) -> AppContext:
    config = config or Config()
    reset(config)
    ctx = ctx or AppContext(config)
    store = ctx.store
    rng = random.Random(322)
    t0 = datetime(2026, 10, 1, 10, 0, 0)
    clock.set_now(t0)

    config.store_info_path.write_text(POLICIES, encoding="utf-8")

    # ---- books -----------------------------------------------------------
    key_to_id = {}
    for i, (key, title, author, cat, year, price, kws, desc, text, _c, _m) in enumerate(BOOKS, 1):
        bid = f"B-{i:04d}"
        key_to_id[key] = bid
        shutil.copy(ROOT / "seed_covers" / f"{key}.png", config.covers_dir / f"{bid}.png")
        text_rel = None
        if text:
            shutil.copy(config.seed_texts_dir / text, config.texts_dir / f"{bid}.txt")
            text_rel = f"texts/{bid}.txt"
        store.append("books", {
            "book_ID": bid, "title": title, "author": author, "category": cat, "keywords": kws,
            "description": desc, "pub_Year": year, "price": price, "cover_Path": f"covers/{bid}.png",
            "text_Path": text_rel, "browse_Count": rng.randint(2, 30), "purchase_Count": 0,
            "rating_Count": 0, "weighted_Avg": 0.0, "list_Status": "NONE", "indexed": False,
            "added_At": clock.now_iso()})

    # ---- users -----------------------------------------------------------
    uid = {}
    for i, (uname, name, email, role, status, balance, warnings) in enumerate(USERS, 1):
        uid[uname] = f"U-{i:04d}"
        store.append("users", {
            "user_ID": uid[uname], "username": uname, "full_Name": name, "email": email,
            "role": "SU" if role == "SU" else "RC", "status": "ACTIVE", "balance": 0.0, "warnings": 0,
            "purchase_Count": 0, "total_Spent": 0.0, "promo_Purchases": 0, "promo_Spent": 0.0,
            "suspension_Reason": None, "created_At": clock.now_iso()})

    for w in TABOO_WORDS:
        store.append("taboo_words", {"word": w, "added_By": uid["admin"], "added_At": clock.now_iso()})

    def sess(name):
        u = ctx.users.get(uid[name])
        return Session(user_ID=u["user_ID"], role=u["role"])

    def deposit(name, amount):
        clock.advance(hours=1)
        ctx.wallet.deposit(sess(name), str(amount))

    def buy(name, *keys):
        clock.advance(hours=3)
        res = ctx.purchases.checkout(sess(name), [key_to_id[k] for k in keys])
        assert res.ok, res.message

    def view(name, *keys):
        for k in keys:
            clock.advance(minutes=20)
            ctx.catalog.view(key_to_id[k], sess(name))

    def review(name, key, stars, text):
        clock.advance(hours=2)
        s = sess(name) if name else Session(visitor_key=f"seed-{rng.random()}")
        ctx.reviews.submit(s, key_to_id[key], stars, text)

    # Selina: becomes VIP the normal way (4 purchases > 3), then keeps $85.00
    deposit("selina", "150.00")
    buy("selina", "mobydick")
    buy("selina", "hamlet", "macbeth")
    buy("selina", "treasure")                      # 4th purchase -> promoted to VIP
    buy("selina", "sherlock")                      # first purchase with the 10% VIP discount
    view("selina", "sherlock", "fatherbrown", "dracula")
    # Alice: one purchase, browses Austen
    deposit("alice", "40.00")
    buy("alice", "emma")
    view("alice", "persuasion", "pride", "sense", "alice")
    # Evan, Ibrahim, Zakiah
    deposit("evan", "30.00")
    buy("evan", "alice")
    deposit("ibrahim", "250.00")
    deposit("zakiah", "5.00")
    buy("zakiah", "christmascarol")                # $4.99 -> $0.01 left

    # Reviews (weighted: verified buyers count double)
    review("selina", "mobydick", 5, "A huge, strange and wonderful book. The chapters about the sea are unforgettable.")
    review("alice", "mobydick", 4, "Long, but the ending is worth it.")
    review("evan", "mobydick", 5, "Captain Ahab is one of the great characters.")
    review(None, "mobydick", 5, "Read it in school and loved it again now.")
    review("ibrahim", "parents", 2, "The morals are too heavy for modern kids.")
    review("alice", "parents", 1, "Very dated stories, not for me.")
    review(None, "parents", 2, "Hard to finish.")
    review("selina", "parents", 1, "Preachy and slow.")
    review("alice", "emma", 4, "Emma is annoying and lovable at the same time. Funny and sharp.")
    review("selina", "hamlet", 5, "The play everyone quotes without knowing it.")
    review(None, "alice", 5, "Pure imagination - the tea party chapter is the best.")

    # Evan already has 2 warnings (two blocked comments)
    review("evan", "worlds", 1, "This is junk, stupid trash for idiot readers, total garbage.")
    review("evan", "dracula", 1, "Dumb moron writing, stupid junk and trash.")

    # Zakiah: an order she could not pay -> $1 fine -> balance -$0.99 -> suspended
    clock.advance(hours=5)
    ctx.purchases.checkout(sess("zakiah"), [key_to_id["origin"]])

    # Alice reads Emma
    ctx.companion.open(sess("alice"), key_to_id["emma"], 2)

    # Final balances of the demo design (Alice $30.02, Selina $85.00, Evan $12.00)
    for name, target in (("alice", "30.02"), ("selina", "85.00"), ("evan", "12.00")):
        u = ctx.users.get(uid[name])
        diff = D(target) - D(u["balance"])
        if diff > 0:
            deposit(name, str(diff))

    clock.set_now(None)
    # ---- indexes ---------------------------------------------------------
    texts = []
    for b in store.read_all("books"):
        t = ctx.catalog.book_text(b)
        if t:
            texts.append((b, t))
    n_chunks = ctx.rag.rebuild(POLICIES, texts)
    for b in store.read_all("books"):
        ctx.covers.add(b["book_ID"], config.data_dir / b["cover_Path"])
        store.update("books", "book_ID", b["book_ID"], {"indexed": True})

    enrolled = []
    if faces_dir:
        for uname in uid:
            for ext in ("jpg", "jpeg", "png"):
                p = Path(faces_dir) / f"{uname}.{ext}"
                if p.exists():
                    img = cv2.imread(str(p))
                    ctx.auth.enroll(uid[uname], [img])
                    enrolled.append(uname)
                    break
    if not quiet:
        print(f"Seeded {len(BOOKS)} books, {len(USERS)} users, {n_chunks} RAG chunks into {config.data_dir}")
        print("Face templates enrolled for:", ", ".join(enrolled) or "nobody yet")
        print("Enrol a face:  python tools/enroll_face.py <username>   (webcam)  or  --image photo.jpg")
    return ctx


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--faces", type=Path, help="folder with <username>.jpg photos to enrol")
    ap.add_argument("--keep", action="store_true", help="keep existing data if present")
    args = ap.parse_args()
    cfg = Config()
    if args.keep and (cfg.data_dir / "users.txt").exists() and (cfg.data_dir / "users.txt").stat().st_size:
        print("data/ already seeded - nothing to do")
    else:
        seed(cfg, args.faces)
