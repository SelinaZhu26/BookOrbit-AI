"""ChatbotService - UC-12 Interact with AI Chatbot, UC-13 Access Additional
Chatbot Information (spec items 3 and 9).

Step 1  classify the question: ADMIN, ACCOUNT, RECOMMEND, BOOK_TEXT, STORE, GENERAL
Step 2  check the role may ask it (the answers get richer from VS to RC to VC to SU)
Step 3  RAG first: if local store files answer it, reply from them and say so
Step 4  otherwise delegate to the local LLM (Ollama) and say so

Permission matrix (what each role gets):
  intent      VS                 RC                   VC                        SU
  STORE       yes                yes                  yes                       yes
  RECOMMEND   popular books      personal picks       personal picks + reasons  popular + order lists
  ACCOUNT     -                  own account          own account + VIP savings -
  BOOK_TEXT   -                  -                    passages from all books   passages from all books
  GENERAL     -                  local LLM            local LLM                 local LLM
  ADMIN       -                  -                    -                         finance report, users, lists
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .. import clock
from ..ai.llm_client import LLMClient, LLMUnavailable
from ..ai.rag import RAGRetriever
from ..ai.texts import tokenize
from ..errors import PermissionDenied
from ..money import D
from .admin_service import AdminService
from .base import ServiceBase, Session
from .recommendation_engine import RecommendationEngine

DENIED = "That information isn't available for your account type."
STORE_ONLY = "I can only answer questions about the store."
OFFLINE = "The assistant is offline - please try again later."

ADMIN_EXAMPLES = [
    "Show the finance report",
    "Which accounts are suspended?",
    "Who has warnings?",
    "What is on the No-Order and To-Order lists?",
    "What are the total sales and fines?",
]

ADMIN_RE = re.compile(r"\b(finance|financial|revenue|sales|income|profits?|earnings|fines collected|"
                      r"total (?:fines|deposits|balances?|sales)|no[- ]order|to[- ]order|order lists?|"
                      r"best[- ]?sell\w*|top (?:spenders|customers)|admin report)\b"
                      r"|\b(which|who|list|show|all|how many)\b.*\b(suspended|warnings?|accounts|users|"
                      r"customers|vips?|spenders)\b", re.I)
ACCOUNT_RE = re.compile(r"\bmy (balance|account|warnings?|orders?|purchases?|status|ledger|money|funds|"
                        r"wallet|savings|discount|books|vip)\b"
                        r"|\b(am i|have i|do i have|how much money|what have i|did i buy)\b", re.I)
RECOMMEND_RE = re.compile(r"\b(recommend|suggest|what should i read|something to read|similar to|"
                          r"books? like|good books?|popular|trending|best books?)\b", re.I)
BOOK_TEXT_RE = re.compile(r"\b(in the (book|novel|play|poem|text)|happens? in|passage|quote|scene|"
                          r"character|who is .+ in|what does .+ say|chapter)\b", re.I)
STORE_WORDS = set(tokenize("store shop bookstore bookorbit hours open close contact email support price "
                           "cost costs buy purchase membership vip fine fines suspend suspended policy "
                           "policies refund review reviews rating taboo register registration sign login "
                           "face camera balance deposit funds book books author catalog category team "
                           "member companion chatbot discount promotion warning warnings privacy"))


@dataclass
class ChatAnswer:
    text: str
    source: str            # RAG / LLM / ADMIN / ACCOUNT / DENIED / OFFLINE / HELP
    label: str
    books: list = field(default_factory=list)
    table: list = field(default_factory=list)
    examples: list = field(default_factory=list)


class ChatbotService(ServiceBase):
    def __init__(self, store, config, rag: RAGRetriever, llm: LLMClient,
                 admin: AdminService, recs: RecommendationEngine):
        super().__init__(store, config)
        self.rag = rag
        self.llm = llm
        self.admin = admin
        self.recs = recs

    # ------------------------------------------------------------ classify
    def _catalog_hits(self, question: str) -> list[dict]:
        q = question.lower()
        qtok = set(tokenize(question))
        hits = []
        for b in self.store.read_all("books"):
            title = b["title"].lower()
            title_tok = set(tokenize(b["title"]))
            surname = b["author"].split()[-1].lower()
            if title in q or (title_tok and title_tok <= qtok and len(title_tok) >= 1 and len(" ".join(title_tok)) > 3) \
                    or (len(surname) > 3 and re.search(rf"\b{re.escape(surname)}\b", q)):
                hits.append(b)
        return hits[:5]

    def classify(self, question: str) -> str:
        q = question.strip()
        if ACCOUNT_RE.search(q):
            return "ACCOUNT"
        if ADMIN_RE.search(q):
            return "ADMIN"
        if RECOMMEND_RE.search(q):
            return "RECOMMEND"
        if BOOK_TEXT_RE.search(q) and self._catalog_hits(q):
            return "BOOK_TEXT"
        if self._catalog_hits(q) or set(tokenize(q)) & STORE_WORDS:
            return "STORE"
        hits = self.rag.search(q, {"PUBLIC"}, k=1)
        if self.rag.is_relevant(hits):
            return "STORE"
        return "GENERAL"

    ALLOWED = {
        "VS": {"STORE", "RECOMMEND"},
        "RC": {"STORE", "RECOMMEND", "ACCOUNT", "GENERAL"},
        "VC": {"STORE", "RECOMMEND", "ACCOUNT", "GENERAL", "BOOK_TEXT"},
        "SU": {"STORE", "RECOMMEND", "GENERAL", "BOOK_TEXT", "ADMIN"},
    }

    # --------------------------------------------------------------- main
    def ask(self, session: Session, question: str) -> ChatAnswer:
        question = (question or "").strip()[:500]
        if not question:
            return ChatAnswer("Type a question first.", "HELP", "")
        intent = self.classify(question)
        role = session.role
        if session.wallet_only and intent not in ("STORE", "ACCOUNT"):
            ans = ChatAnswer(DENIED + " (Your account is suspended.)", "DENIED", "")
        elif intent == "ADMIN" and role == "SU":
            ans = self.admin_answer(session, question)                       # UC-13
        elif role == "VS" and intent == "GENERAL":
            ans = ChatAnswer(STORE_ONLY, "DENIED", "")
        elif intent == "ACCOUNT" and role == "SU":
            ans = ChatAnswer("Super-User accounts have no store balance. Ask for the finance report "
                             "to see customer balances.", "HELP", "", examples=ADMIN_EXAMPLES)
        elif intent not in self.ALLOWED[role]:
            hint = {"ACCOUNT": " Sign in to ask about your account.",
                    "BOOK_TEXT": " Searching inside the books is a VIP feature; RC customers can use the "
                                 "Reading Companion on their own books."}.get(intent, "")
            ans = ChatAnswer(DENIED + (hint if role != "VS" or intent == "ACCOUNT" else ""), "DENIED", "")
        elif intent == "ACCOUNT":
            ans = self.account_answer(session, question)
        elif intent == "RECOMMEND":
            ans = self.recommend_answer(session, question)
        elif intent == "BOOK_TEXT":
            ans = self.book_text_answer(session, question)
        elif intent == "STORE":
            ans = self.store_answer(session, question)
        else:
            ans = self.general_answer(question)
        self.store.append("chat_log", {
            "chat_ID": self.store.next_id("chat_log", "chat_ID", "M-", 6),
            "user_ID": session.user_ID, "role": role, "question": question, "intent": intent,
            "answer": ans.text, "source": ans.source, "created_At": clock.now_iso()})
        return ans

    # ------------------------------------------------------------ helpers
    def _llm(self, system: str, prompt: str) -> str:
        return self.llm.chat(system, prompt)

    @staticmethod
    def _catalog_fact(b: dict) -> str:
        rating = f"weighted rating {b['weighted_Avg']:.2f} from {b['rating_Count']} ratings" \
            if b["rating_Count"] else "no ratings yet"
        text = "the full text is available in the Reading Companion" if b.get("text_Path") else \
            "no Reading Companion text"
        return (f"“{b['title']}” by {b['author']} ({b['pub_Year']}), category {b['category']}, "
                f"price ${D(b['price']):,.2f}, {rating}; {text}. {b['description']}")

    def store_answer(self, session: Session, question: str) -> ChatAnswer:
        books = self._catalog_hits(question)
        hits = self.rag.search(question, {"PUBLIC"}, k=3)
        relevant = self.rag.is_relevant(hits, min_coverage=0.34, min_score=1.0)
        context = [self._catalog_fact(b) for b in books]
        context += [f"[{h.chunk['title']}] {h.chunk['text']}" for h in hits if relevant or not books][:3]
        if not context:
            if session.role == "VS":
                return ChatAnswer(STORE_ONLY + " I couldn't find that in the store's information.", "DENIED", "")
            return self.general_answer(question)
        label = "[Store data] Answered via RAG from the store's local files"
        try:
            text = self._llm(
                "You are BookOrbit AI, the assistant of a small bookstore. Answer ONLY from the context. "
                "Be brief (max 4 sentences). If the context does not contain the answer, say so.",
                "Context:\n" + "\n".join(f"- {c}" for c in context) + f"\n\nQuestion: {question}")
        except LLMUnavailable:
            if books:
                text = " ".join(self._catalog_fact(b) for b in books[:2])
            else:
                text = self.rag.best_sentences(question, hits[0].chunk["text"], 3)
            label += " (LLM offline - showing the matching store information)"
        return ChatAnswer(text, "RAG", label, books=books[:4])

    def general_answer(self, question: str) -> ChatAnswer:
        try:
            text = self._llm("You are a helpful, concise assistant inside the BookOrbit AI bookstore app. "
                             "Answer in at most 5 sentences.", question)
        except LLMUnavailable:
            return ChatAnswer(OFFLINE + " (This question is not about the store, so it needs the local LLM.)",
                              "OFFLINE", "")
        return ChatAnswer(text, "LLM", f"[General AI] Not found in the store's files - answered by the local "
                                       f"LLM (Ollama, {self.llm.model})")

    def account_answer(self, session: Session, question: str) -> ChatAnswer:
        u = self.users.get(session.user_ID)
        purchases = self.store.filter("purchases", user_ID=u["user_ID"])
        books = {b["book_ID"]: b for b in self.store.read_all("books")}
        owned = [books[p["book_ID"]]["title"] for p in purchases if p["book_ID"] in books]
        facts = [f"Balance: ${D(u['balance']):,.2f}",
                 f"Account type: {'VIP Customer' if u['role'] == 'VC' else 'Registered Customer'}",
                 f"Status: {u['status'].title()}",
                 f"Warnings: {u['warnings']} of 3",
                 f"Books bought: {len(purchases)}" + (f" ({', '.join(owned[:5])})" if owned else "")]
        if u["role"] == "RC":
            left_n = max(0, self.config.vip_min_purchases + 1 - u["promo_Purchases"])
            left_s = max(D(0), D(self.config.vip_min_spent) + D("0.01") - D(u["promo_Spent"]))
            facts.append(f"VIP progress: {u['promo_Purchases']} purchases and ${D(u['promo_Spent']):,.2f} "
                         f"since joining; {left_n} more purchase(s) or ${left_s:,.2f} more spending to become VIP")
        else:
            saved = sum((D(p["discount"]) for p in purchases), D(0))
            facts.append(f"VIP savings so far: ${saved:,.2f} (10% off every purchase)")
        return ChatAnswer("Here is your account summary:\n" + "\n".join("• " + f for f in facts),
                          "ACCOUNT", "[Store data] From your account files (RAG over your own records)")

    def recommend_answer(self, session: Session, question: str) -> ChatAnswer:
        if session.role == "VS":
            books = self.recs.popular(3)
            return ChatAnswer("Our most popular books right now are: " +
                              "; ".join(f"“{b['title']}” by {b['author']}" for b in books) +
                              ". Sign in to get picks based on your own reading.",
                              "RAG", "[Store data] Popular books from the store's files", books=books)
        if session.role == "SU":
            lists = self.admin.finance_facts(session)
            books = self.recs.popular(3)
            text = ("Most popular: " + "; ".join(b["title"] for b in books) +
                    ". To-Order list: " + (", ".join(lists["to_order"]) or "empty") + ".")
            return ChatAnswer(text, "RAG", "[Store data] Popularity and order lists", books=books)
        n = 4 if session.role == "VC" else 3
        rec = self.recs.personalized(session, n)
        books = rec["books"]
        if session.role == "VC":
            lines = [f"“{b['title']}” by {b['author']} — {rec['reasons'].get(b['book_ID'], 'popular')}"
                     for b in books]
            text = "VIP picks for you:\n" + "\n".join("• " + l for l in lines)
        else:
            text = "You might like: " + "; ".join(f"“{b['title']}” by {b['author']}" for b in books) + "."
        return ChatAnswer(text, "RAG", "[Store data] Recommendations from your browsing and purchases", books=books)

    def book_text_answer(self, session: Session, question: str) -> ChatAnswer:
        books = [b for b in self._catalog_hits(question) if b.get("text_Path")]
        if not books:
            return self.store_answer(session, question)
        book = books[0]
        hits = self.rag.search(question, {"BOOK_TEXT"}, book_ID=book["book_ID"], k=3)
        if not hits:
            return self.store_answer(session, question)
        passages = [h.chunk["text"] for h in hits]
        label = f"[Store data] Answered via RAG from the text of “{book['title']}”"
        try:
            text = self._llm("Answer the reader's question using ONLY the passages from the book. "
                             "Quote short phrases when useful. Max 5 sentences.",
                             "Passages:\n" + "\n---\n".join(passages) + f"\n\nQuestion: {question}")
        except LLMUnavailable:
            text = "Most relevant passage: “" + self.rag.best_sentences(question, passages[0], 3) + "”"
            label += " (LLM offline - showing the best matching passage)"
        return ChatAnswer(text, "RAG", label, books=[book])

    # ================================================================ UC-13
    def admin_answer(self, session: Session, question: str) -> ChatAnswer:
        if session.role != "SU":
            raise PermissionDenied(DENIED)
        f = self.admin.finance_facts(session)
        q = question.lower()
        rows: list[tuple[str, str]] = []
        if re.search(r"financ|revenue|sales|income|earn|profit|report|deposit|fine|balance", q):
            rows += [("Total sales", f"${f['total_sales']:,.2f} ({f['books_sold']} books)"),
                     ("VIP discounts given", f"${f['vip_discounts']:,.2f}"),
                     ("Deposits", f"${f['deposits']:,.2f}"),
                     ("Fines collected", f"${f['fines']:,.2f} ({f['fine_count']} fines)"),
                     ("Customer balances held", f"${f['customer_balances']:,.2f}"),
                     ("Top books", ", ".join(f"{t} ({n})" for t, n in f["top_books"]) or "none")]
        if re.search(r"suspend|report", q):
            rows.append(("Suspended accounts", ", ".join(f["suspended"]) or "none"))
        if re.search(r"warning|report", q):
            rows.append(("Warnings", ", ".join(f"{u}: {n}" for u, n in f["warnings"].items()) or "none"))
        if re.search(r"order|list|report", q):
            rows.append(("No-Order list", ", ".join(f["no_order"]) or "empty"))
            rows.append(("To-Order list", ", ".join(f["to_order"]) or "empty"))
        if re.search(r"users|customers|vip|accounts|how many|spender", q):
            rows.append(("Customers", f"{f['customers']} ({f['vip_customers']} VIP)"))
            rows.append(("Top spenders", ", ".join(f"{u} (${s:,.2f})" for u, s in f["top_spenders"]) or "none"))
        if not rows:
            return ChatAnswer("I didn't understand that admin question. Try one of these:", "HELP",
                              "[Admin data]", examples=ADMIN_EXAMPLES)
        table = [list(r) for r in rows]
        try:
            text = self._llm("You are the bookstore's finance assistant. Write a short answer (max 4 "
                             "sentences) using ONLY these figures. Do not invent numbers.",
                             "Figures:\n" + "\n".join(f"{k}: {v}" for k, v in rows) + f"\n\nQuestion: {question}")
            label = "[Admin data] Computed from the store files and phrased by the local LLM"
        except LLMUnavailable:
            text = "Here are the figures computed from the store files:"
            label = "[Admin data] Computed from the store files (LLM offline - plain table)"
        return ChatAnswer(text, "ADMIN", label, table=table)
