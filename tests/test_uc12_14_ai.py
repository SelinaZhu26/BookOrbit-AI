"""UC-12 Interact with AI Chatbot, UC-13 Access Additional Chatbot Information,
UC-14 Use Smart Reading Companion."""
import pytest

from bookorbit.errors import NotFoundError, PermissionDenied
from bookorbit.services.base import Session
from tests.helpers import book_id, session_for

VS = Session()


# ---------------------------------------------------------------- UC-12
def test_store_question_answered_via_rag_and_labelled(ctx):
    a = ctx.chatbot.ask(VS, "What are your store hours?")
    assert a.source == "RAG" and "RAG" in a.label and "24 hours" in a.text


def test_catalog_question_uses_live_book_data(ctx):
    a = ctx.chatbot.ask(VS, "How much does Moby Dick cost?")
    assert "$12.99" in a.text and a.books[0]["title"] == "Moby Dick"


def test_visitor_general_question_is_refused(ctx):
    a = ctx.chatbot.ask(VS, "What is the capital of France?")
    assert a.text == "I can only answer questions about the store."


def test_general_question_goes_to_llm_and_says_so(ctx_llm):
    a = ctx_llm.chatbot.ask(session_for(ctx_llm, "alice"), "What is the capital of France?")
    assert a.source == "LLM" and "[General AI]" in a.label and a.text == "LLM ANSWER"


def test_general_question_with_llm_offline(ctx):
    a = ctx.chatbot.ask(session_for(ctx, "alice"), "What is the capital of France?")
    assert a.source == "OFFLINE" and "offline" in a.text


def test_rag_answer_is_phrased_by_llm_from_context_only(ctx_llm):
    a = ctx_llm.chatbot.ask(VS, "Can I get a refund?")
    system, prompt = ctx_llm.llm.calls[-1]
    assert "ONLY from the context" in system and "cannot be refunded" in prompt
    assert a.source == "RAG"


def test_answers_get_richer_from_vs_to_rc_to_vc_to_su(ctx):
    q_account, q_book, q_admin = "What is my balance?", "Who is Ahab in Moby Dick?", "Show the finance report"
    rc, vc, su = (session_for(ctx, n) for n in ("alice", "selina", "admin"))
    assert ctx.chatbot.ask(VS, q_account).source == "DENIED"
    assert ctx.chatbot.ask(rc, q_account).source == "ACCOUNT"
    assert ctx.chatbot.ask(rc, q_book).source == "DENIED"            # VIP feature
    assert ctx.chatbot.ask(vc, q_book).source == "RAG"
    for s in (VS, rc, vc):
        assert ctx.chatbot.ask(s, q_admin).text.startswith("That information isn't available")
    assert ctx.chatbot.ask(su, q_admin).source == "ADMIN"


def test_account_answer_contains_own_figures(ctx):
    a = ctx.chatbot.ask(session_for(ctx, "alice"), "What is my balance?")
    assert "$30.02" in a.text and "Registered Customer" in a.text


def test_chat_is_logged(ctx):
    ctx.chatbot.ask(VS, "What are your store hours?")
    log = ctx.store.read_all("chat_log")[-1]
    assert log["question"] == "What are your store hours?" and log["source"] == "RAG" and log["role"] == "VS"


# ---------------------------------------------------------------- UC-13
def test_admin_figures_plain_table_when_llm_offline(ctx):
    a = ctx.chatbot.ask(session_for(ctx, "admin"), "Show the finance report")
    rows = dict(a.table)
    assert a.label.startswith("[Admin data]") and "plain table" in a.label
    assert rows["Suspended accounts"] == "zakiah"
    assert "Moby Dick" in rows["To-Order list"] and "The Parent's Assistant" in rows["No-Order list"]
    sales = sum(p["paid"] for p in ctx.store.read_all("purchases"))
    assert rows["Total sales"].startswith(f"${sales:,.2f}")


def test_admin_answer_phrased_only_from_figures(ctx_llm):
    a = ctx_llm.chatbot.ask(session_for(ctx_llm, "admin"), "Who has warnings?")
    system, prompt = ctx_llm.llm.calls[-1]
    assert "Do not invent numbers" in system and "evan: 2" in prompt
    assert a.source == "ADMIN" and a.text == "LLM ANSWER"


def test_admin_question_not_understood_shows_examples(ctx):
    a = ctx.chatbot.admin_answer(session_for(ctx, "admin"), "please do the thing")
    assert a.examples and a.source == "HELP"


def test_admin_answer_refused_for_non_su(ctx):
    with pytest.raises(PermissionDenied):
        ctx.chatbot.admin_answer(session_for(ctx, "selina"), "Show the finance report")


# ---------------------------------------------------------------- UC-14
def test_companion_opens_saved_chapter_and_saves_progress(ctx):
    s = session_for(ctx, "alice")
    bid = book_id(ctx, "Emma")
    v = ctx.companion.open(s, bid)                                  # seeded progress: chapter 2
    assert v["chapter"] == 2 and v["paragraphs"]
    ctx.companion.open(s, bid, 5)
    assert ctx.companion.progress(s.user_ID, bid)["chapter"] == 5


def test_non_owner_reads_chapter_1_only(ctx):
    s = session_for(ctx, "alice")
    bid = book_id(ctx, "Moby Dick")
    assert not ctx.companion.open(s, bid, 1)["locked"]
    v = ctx.companion.open(s, bid, 3)
    assert v["locked"] and v["message"] == "Buy the book to keep reading." and not v["paragraphs"]
    assert ctx.companion.act(s, bid, 3, "summarize")["buy"]


def test_book_without_text_has_no_companion(ctx):
    with pytest.raises(NotFoundError, match="isn't available"):
        ctx.companion.open(session_for(ctx, "alice"), book_id(ctx, "Dracula"))


def test_visitor_cannot_use_companion(ctx):
    with pytest.raises(PermissionDenied):
        ctx.companion.open(VS, book_id(ctx, "Emma"))


def test_offline_summary_quiz_and_ask_still_work(ctx):
    s = session_for(ctx, "alice")
    bid = book_id(ctx, "Emma")
    summ = ctx.companion.act(s, bid, 2, "summarize")
    assert summ["ok"] and len(summ["text"]) > 100 and "offline" in summ["source"]
    quiz = ctx.companion.act(s, bid, 2, "quiz")
    assert len(quiz["quiz"]) == 3 and all("answer_index" not in q for q in quiz["quiz"])   # hidden
    item = ctx.companion.quizzes[quiz["quiz_ID"]]["items"][0]
    assert ctx.companion.check_answer(quiz["quiz_ID"], 0, item["answer_index"])["correct"]
    assert not ctx.companion.check_answer(quiz["quiz_ID"], 0, (item["answer_index"] + 1) % 4)["correct"]
    ask = ctx.companion.act(s, bid, 2, "ask", question="Who is Mr. Knightley?")
    assert ask["ok"] and "Knightley" in ask["text"]


def test_explain_needs_selection_and_llm(ctx):
    s = session_for(ctx, "alice")
    bid = book_id(ctx, "Emma")
    assert ctx.companion.act(s, bid, 2, "explain")["message"] == "Select a passage first"
    off = ctx.companion.act(s, bid, 2, "explain", selection="a respectable family")
    assert not off["ok"] and off.get("offline")


def test_explain_and_quiz_with_llm_use_this_books_passages(ctx_llm):
    s = session_for(ctx_llm, "alice")
    bid = book_id(ctx_llm, "Emma")
    out = ctx_llm.companion.act(s, bid, 2, "explain", selection="Mr. Weston was a native of Highbury")
    system, prompt = ctx_llm.llm.calls[-1]
    assert out["ok"] and "Emma" in system and "Highbury" in prompt
    ctx_llm.llm.reply = ('[{"question":"Q1?","options":["a","b","c","d"],"answer_index":1},'
                         '{"question":"Q2?","options":["a","b","c","d"],"answer_index":2},'
                         '{"question":"Q3?","options":["a","b","c","d"],"answer_index":0}]')
    quiz = ctx_llm.companion.act(s, bid, 2, "quiz")
    assert [q["question"] for q in quiz["quiz"]] == ["Q1?", "Q2?", "Q3?"] and quiz["source"] == "LLM + this chapter"
    assert ctx_llm.companion.check_answer(quiz["quiz_ID"], 1, 2)["correct"]
