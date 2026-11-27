"""End-to-end check in a real browser (Playwright). Not part of `pytest`;
run it against a running app whose demo users have face templates:

    python seed.py --faces my_photos/          # my_photos/<username>.jpg
    python app.py --no-open &
    python tests/e2e_browser.py --face my_photos/alice.jpg --other someone_else.jpg

It walks through all 18 use cases in the GUI and saves screenshots to e2e_shots/.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:5050")
    ap.add_argument("--face", required=True, help="photo of the person enrolled for the demo users")
    ap.add_argument("--other", required=True, help="photo of a different person")
    ap.add_argument("--chrome", default=None, help="path to a Chrome/Chromium executable")
    ap.add_argument("--shots", default=str(ROOT / "e2e_shots"))
    a = ap.parse_args()
    shots = Path(a.shots)
    shots.mkdir(exist_ok=True)
    base = a.url.rstrip("/")
    steps: list[str] = []

    def ok(msg):
        steps.append(msg)
        print("  ✓", msg)

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=a.chrome, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1360, "height": 880})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("dialog", lambda d: d.accept())                   # UC-08 confirmation

        def shot(name):
            page.screenshot(path=str(shots / f"{name}.png"))

        def sign_in(username, photo):
            page.goto(base + "/signout")
            page.goto(base + "/signin")
            page.fill("#username", username)
            page.click("#next")
            page.set_input_files("input[data-photo]", photo)
            expect(page.locator("[data-facemsg]")).to_contain_text("Face found")
            page.click("#verify")

        # ---- UC-03 / UC-04 / UC-05 as a visitor
        page.goto(base + "/")
        expect(page.locator("#rec-title")).to_have_text("Top picks this week")
        expect(page.locator("#top-books .bookcard")).to_have_count(3)
        ok("UC-03 visitor sees the top 3 popular books")
        shot("01_home_visitor")
        page.fill(".hero input[name=q]", "whale")
        page.click(".hero button[type=submit]")
        expect(page.locator("#results .bookcard")).to_have_count(1)
        page.goto(base + "/browse?category=Science")
        expect(page.locator("#result-count")).to_have_text("3 books found")
        page.goto(base + "/browse?field=year&q=1900-1800")
        expect(page.locator("#year-error")).to_be_visible()
        page.goto(base + "/browse")
        page.click("button[data-open=cover-modal]")
        page.set_input_files("#cover-file", str(_cover_photo(base, page, "B-0015")))
        page.click("#cover-modal button[type=submit]")
        expect(page.locator("#results .bookcard").first).to_have_attribute("data-book", "B-0015")
        ok("UC-04 text, category, year and cover-photo search")
        shot("02_cover_search")
        page.locator("#results .bookcard").first.click()
        expect(page.locator("#book-title")).to_have_text("Hamlet")
        ok("UC-05 book details with reviews")

        # ---- UC-10 visitor review, UC-12 visitor chat
        page.goto(base + "/books/B-0020")
        page.click("label[for=star4]")
        page.fill("#comment", "A spooky classic.")
        page.click("#submit-review")
        expect(page.locator("#review-result")).to_contain_text("Review published")
        page.goto(base + "/chat")
        page.fill("#question", "What are your store hours?")
        page.click("#send")
        expect(page.locator(".msg.bot").last).to_contain_text("24 hours")
        expect(page.locator(".msg.bot .label").last).to_contain_text("RAG")
        page.fill("#question", "What is the capital of France?")
        page.click("#send")
        expect(page.locator(".msg.bot").last).to_contain_text("I can only answer questions about the store")
        ok("UC-12 visitor chat: RAG answer labelled, general question refused")
        shot("03_chat_visitor")

        # ---- UC-01 register
        page.goto(base + "/register")
        page.fill("#full_name", "Maya Lin")
        page.fill("#username", "a")
        page.fill("#email", "bad")
        page.click("#create-account")
        expect(page.locator("[data-error=username]")).to_be_visible()
        expect(page.locator("#full_name")).to_have_value("Maya Lin")
        page.fill("#username", "maya_e2e")
        page.fill("#email", "maya@example.com")
        page.check("#terms")
        page.set_input_files("input[data-photo]", a.face)
        expect(page.locator("[data-facemsg]")).to_contain_text("Face found")
        shot("04_register")
        page.click("#create-account")
        expect(page.locator(".alert.success")).to_contain_text("Account created - please sign in")
        ok("UC-01 registration with validation and face template")

        # ---- UC-02 sign in: wrong face, then right face
        page.fill("#username", "maya_e2e")
        page.click("#next")
        page.set_input_files("input[data-photo]", a.other)
        page.wait_for_timeout(600)
        page.click("#verify")
        expect(page.locator("#signin-error")).to_contain_text("attempt 1 of 3")
        page.set_input_files("input[data-photo]", a.face)
        expect(page.locator("[data-facemsg]")).to_contain_text("Face found")
        page.click("#verify")
        expect(page.locator(".usercard .name")).to_have_text("Maya Lin")
        ok("UC-02 face sign-in rejects another person and accepts the owner")
        expect(page.locator("#rec-title")).to_have_text("Popular right now")
        ok("UC-06 new customer without history sees popular books")

        # ---- UC-07 deposit, UC-08 purchase, fine
        page.goto(base + "/balance")
        page.fill("#amount", "1.234")
        page.click("#add-funds")
        expect(page.locator("#amount-error")).to_have_text("Enter a valid amount")
        page.fill("#amount", "20")
        page.click("#add-funds")
        expect(page.locator("#balance")).to_have_text("$20.00")
        ok("UC-07 deposit validation and ledger")
        page.goto(base + "/books/B-0012")
        page.click("#buy-now")
        expect(page.locator("#total")).to_have_text("$12.99")
        page.click("#place-order")
        expect(page.locator("#receipt")).to_contain_text("Moby Dick")
        ok("UC-08 purchase with confirmation and receipt")
        shot("05_receipt")
        page.goto(base + "/books/B-0027")                         # Origin of Species $13.99 > $7.01
        page.click("#buy-now")
        expect(page.locator("#insufficient")).to_be_visible()
        page.click("#place-order")
        expect(page.locator(".alert.error[role=status]")).to_contain_text("$1.00 fine charged")
        ok("UC-08 insufficient funds -> $1 fine")

        # ---- UC-14 Reading Companion
        page.goto(base + "/read/B-0012?chapter=3")
        expect(page.locator("#page h2")).to_be_visible()
        page.click("button[data-act=quiz]")
        expect(page.locator(".quizq")).to_have_count(3)
        page.locator(".quizq").first.locator(".opt").first.click()
        expect(page.locator(".quizq [data-res]").first).not_to_be_empty()
        page.click("button[data-act=summarize]")
        expect(page.locator("#aiout")).to_contain_text("Summary")
        ok("UC-14 Reading Companion: quiz (answers hidden until answered) and summary")
        shot("06_reader")

        # ---- UC-10 / UC-11: masked review, then VIP demotion
        page.goto(base + "/books/B-0012")
        page.click("label[for=star5]")
        page.fill("#comment", "Long but never junk.")
        page.click("#submit-review")
        expect(page.locator("#review-result")).to_contain_text("1 word was masked")
        expect(page.locator("#review-list")).to_contain_text("never ****.")
        ok("UC-10 taboo word masked, verified review published")
        sign_in("selina", a.face)
        expect(page.locator("#role-label")).to_contain_text("VIP Customer")
        page.goto(base + "/books/B-0001")
        expect(page.locator("#book-price")).to_contain_text("VIP")
        ok("UC-09 VIP price shown with 10% off")
        page.click("label[for=star1]")
        page.fill("#comment", "idiot moron dumb junk")
        page.click("#submit-review")
        expect(page.locator("#review-result")).to_contain_text("no longer a VIP Customer")
        expect(page.locator("#role-label")).to_contain_text("Registered Customer")
        ok("UC-11 blocked comment -> warning and VIP demotion")
        shot("07_demoted")
        page.goto(base + "/chat")
        page.fill("#question", "What is my balance?")
        page.click("#send")
        expect(page.locator(".msg.bot").last).to_contain_text("Balance:")
        ok("UC-12 customer asks about own account")

        # ---- Super-User: UC-13, 15, 16, 17, 18
        sign_in("admin", a.face)
        page.goto(base + "/chat")
        page.fill("#question", "Show the finance report")
        page.click("#send")
        expect(page.locator(".msg.bot table")).to_contain_text("Total sales")
        ok("UC-13 SU finance report from the files")
        shot("08_admin_chat")
        page.goto(base + "/admin/books")
        page.click("button[data-toggle=add-book]")
        for k, v in {"title": "The Odyssey", "author": "Homer", "category": "Poetry", "year": "1614",
                     "price": "6.50", "keywords": "epic, sea", "description": "Odysseus goes home."}.items():
            page.fill(f"#f-{k}", v)
        page.set_input_files("#f-cover", str(ROOT / "seed_covers" / "treasure.png"))
        page.click("#save-book")
        expect(page.locator(".alert.success")).to_contain_text("was added to the catalog")
        ok("UC-15 add a book")
        page.goto(base + "/admin/taboo")
        page.fill("#new-word", "two words")
        page.click("#taboo-add button")
        expect(page.locator("#taboo-error")).to_have_text("Enter one word")
        page.fill("#new-word", "boring")
        page.click("#taboo-add button")
        expect(page.locator("tr[data-word=boring]")).to_be_visible()
        page.locator("tr[data-word=boring] .btn.danger").click()
        expect(page.locator("tr[data-word=boring]")).to_have_count(0)
        ok("UC-16 add / validate / delete taboo words")
        page.goto(base + "/admin/users")
        row = page.locator("#suspended tr[data-user=zakiah]")
        row.locator("button").click()
        expect(page.locator("[data-reopen-error]")).to_contain_text("must deposit at least")
        page.locator("#suspended tr[data-user=zakiah] input[name=amount]").fill("5")
        page.locator("#suspended tr[data-user=zakiah] button").click()
        expect(page.locator(".alert.success")).to_contain_text("ACTIVE again")
        ok("UC-17 reopen refused below $0, then reopened with a deposit")
        page.goto(base + "/admin/reports")
        page.click("#recalc")
        expect(page.locator("#to_order")).to_contain_text("Moby Dick")
        expect(page.locator("#no_order")).to_contain_text("The Parent's Assistant")
        ok("UC-18 No-Order / To-Order lists")
        shot("09_reports")
        browser.close()

    if errors:
        print("JavaScript errors:", errors)
        return 1
    print(f"\nAll {len(steps)} browser checks passed. Screenshots in {shots}")
    return 0


def _cover_photo(base, page, book_ID) -> Path:
    """Simulate a phone photo of a cover: perspective, blur, lighting."""
    import cv2
    import numpy as np
    import urllib.request
    data = urllib.request.urlopen(f"{base}/covers/{book_ID}.png").read()
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    M = cv2.getPerspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]),
                                    np.float32([[35, 25], [w - 5, 0], [w - 30, h - 10], [0, h - 35]]))
    out = cv2.warpPerspective(img, M, (w + 40, h + 40), borderValue=(190, 185, 180))
    out = cv2.convertScaleAbs(cv2.GaussianBlur(out, (3, 3), 0), alpha=0.85, beta=25)
    path = Path(tempfile.gettempdir()) / f"cover_photo_{book_ID}.jpg"
    cv2.imwrite(str(path), out)
    return path


if __name__ == "__main__":
    sys.exit(main())
