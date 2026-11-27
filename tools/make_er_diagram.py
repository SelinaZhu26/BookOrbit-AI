"""Draw the E-R diagram of the implemented system (docs/ER_diagram.png/.svg)
straight from the data-file schema, so the diagram and the code cannot drift.

    python tools/make_er_diagram.py      (needs Graphviz `dot`)
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# entity: (file, [(attribute, kind)])   kind: PK, FK, PK/FK or ""
ENTITIES = {
    "User": ("users.txt", [("user_ID", "PK"), ("username (unique)", ""), ("full_Name", ""), ("email", ""),
             ("role {RC, VC, SU}", ""), ("status {ACTIVE, SUSPENDED}", ""), ("balance", ""), ("warnings", ""),
             ("purchase_Count", ""), ("total_Spent", ""), ("promo_Purchases", ""), ("promo_Spent", ""),
             ("suspension_Reason", ""), ("created_At", "")]),
    "Book": ("books.txt", [("book_ID", "PK"), ("title", ""), ("author", ""), ("category", ""), ("keywords", ""),
             ("description", ""), ("pub_Year", ""), ("price", ""), ("cover_Path", ""), ("text_Path", ""),
             ("browse_Count", ""), ("purchase_Count", ""), ("rating_Count", ""), ("weighted_Avg", ""),
             ("list_Status {NONE, NO_ORDER, TO_ORDER}", ""), ("indexed", ""), ("added_At", "")]),
    "Transaction": ("transactions.txt", [("txn_ID", "PK"), ("user_ID", "FK"), ("book_ID", "FK"),
                    ("type {DEPOSIT, PURCHASE, FINE}", ""), ("amount", ""), ("balance_After", ""), ("note", ""),
                    ("created_At", "")]),
    "Purchase": ("purchases.txt", [("purchase_ID", "PK"), ("user_ID", "FK"), ("book_ID", "FK"), ("txn_ID", "FK"),
                 ("list_Price", ""), ("discount", ""), ("paid", ""), ("created_At", "")]),
    "Review": ("reviews.txt", [("review_ID", "PK"), ("book_ID", "FK"), ("user_ID", "FK (null = Visitor)"),
               ("visitor_Key", ""), ("author_Name", ""), ("role_At_Time", ""), ("rating 1-5", ""),
               ("original_Text", ""), ("display_Text", ""), ("taboo_Count", ""), ("weight 1.0 / 2.0", ""),
               ("verified_Buyer", ""), ("status {PUBLISHED, BLOCKED}", ""), ("created_At", ""), ("updated_At", "")]),
    "Warning": ("warnings.txt", [("warning_ID", "PK"), ("user_ID", "FK"), ("review_ID", "FK"), ("reason", ""),
                ("created_At", "")]),
    "TabooWord": ("taboo_words.txt", [("word", "PK"), ("added_By", "FK"), ("added_At", "")]),
    "FaceTemplate": ("biometrics.txt", [("user_ID", "PK/FK"), ("template_Path", ""), ("detector", ""),
                     ("embedder", ""), ("samples", ""), ("created_At", "")]),
    "LoginAttempt": ("login_attempts.txt", [("attempt_ID", "PK"), ("user_ID", "FK"), ("username", ""),
                     ("score", ""), ("success", ""), ("created_At", "")]),
    "BrowseEvent": ("browse_history.txt", [("event_ID", "PK"), ("user_ID", "FK"), ("book_ID", "FK"),
                    ("action VIEW", ""), ("created_At", "")]),
    "ChatMessage": ("chat_log.txt", [("chat_ID", "PK"), ("user_ID", "FK (null = Visitor)"), ("role", ""),
                    ("question", ""), ("intent", ""), ("answer", ""),
                    ("source {RAG, LLM, ADMIN, ACCOUNT, DENIED, OFFLINE}", ""), ("created_At", "")]),
    "ReadingProgress": ("reading_progress.txt", [("user_ID", "PK/FK"), ("book_ID", "PK/FK"), ("chapter", ""),
                        ("last_Action", ""), ("updated_At", "")]),
    "StatusChange": ("status_changes.txt", [("change_ID", "PK"), ("user_ID", "FK"), ("from_Role", ""), ("to_Role", ""),
                     ("from_Status", ""), ("to_Status", ""), ("reason", ""), ("by (SYSTEM or SU)", "FK"),
                     ("created_At", "")]),
    "AdminAction": ("admin_actions.txt", [("action_ID", "PK"), ("admin_ID", "FK"), ("action", ""), ("target", ""),
                    ("details", ""), ("created_At", "")]),
    "RagChunk": ("rag_chunks.txt", [("chunk_ID", "PK"), ("scope {PUBLIC, BOOK_TEXT}", ""), ("book_ID", "FK"),
                 ("title", ""), ("text", "")]),
}

# (from, to, label, from-cardinality, to-cardinality)
RELATIONS = [
    ("User", "Transaction", "has ledger", "1", "0..*"),
    ("User", "Purchase", "buys", "1", "0..*"),
    ("Book", "Purchase", "is bought in", "1", "0..*"),
    ("Purchase", "Transaction", "paid by", "1", "1"),
    ("User", "Review", "writes", "0..1", "0..*"),
    ("Book", "Review", "receives", "1", "0..*"),
    ("Review", "Warning", "causes", "1", "0..1"),
    ("User", "Warning", "receives", "1", "0..*"),
    ("User", "FaceTemplate", "enrols", "1", "0..1"),
    ("User", "LoginAttempt", "attempts", "1", "0..*"),
    ("User", "BrowseEvent", "views", "1", "0..*"),
    ("Book", "BrowseEvent", "is viewed", "1", "0..*"),
    ("User", "ChatMessage", "asks", "0..1", "0..*"),
    ("User", "ReadingProgress", "reads", "1", "0..*"),
    ("Book", "ReadingProgress", "is read", "1", "0..*"),
    ("User", "StatusChange", "changes", "1", "0..*"),
    ("User", "AdminAction", "performs (SU)", "1", "0..*"),
    ("User", "TabooWord", "maintains (SU)", "1", "0..*"),
    ("Book", "RagChunk", "is split into", "0..1", "0..*"),
]


def label(name: str, file: str, attrs) -> str:
    rows = [f'<tr><td bgcolor="#1E2A44" align="left"><font color="white"><b>{name}</b></font>'
            f'<font color="#E8B04A" point-size="9">  {file}</font></td></tr>']
    for a, kind in attrs:
        text = a.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if kind.startswith("PK"):
            text = f"<u><b>{text}</b></u>"
        tag = f'<font color="#8A5A00" point-size="9"> {kind}</font>' if kind else ""
        rows.append(f'<tr><td align="left">{text}{tag}</td></tr>')
    return '<<table border="0" cellborder="1" cellspacing="0" cellpadding="3" bgcolor="white">' + "".join(rows) + "</table>>"


def main() -> None:
    out = ROOT / "docs"
    out.mkdir(exist_ok=True)
    lines = ["digraph ER {", 'graph [rankdir=LR, splines=true, nodesep=0.35, ranksep=1.1, fontname="Helvetica", '
             'label="BookOrbit AI - E-R diagram of the implemented system (one entity = one data/*.txt file; '
             'underlined = key)", labelloc=t, fontsize=18];',
             'node [shape=plaintext, fontname="Helvetica", fontsize=10];',
             'edge [fontname="Helvetica", fontsize=9, color="#4B5563", arrowhead=none];']
    for name, (file, attrs) in ENTITIES.items():
        lines.append(f"{name} [label={label(name, file, attrs)}];")
    for a, b, lab, ca, cb in RELATIONS:
        lines.append(f'{a} -> {b} [label="{lab}", taillabel="{ca}", headlabel="{cb}", labeldistance=1.6];')
    lines.append("}")
    dot = out / "ER_diagram.dot"
    dot.write_text("\n".join(lines), encoding="utf-8")
    for fmt in ("png", "svg"):
        subprocess.run(["dot", f"-T{fmt}", "-Gdpi=110", str(dot), "-o", str(out / f"ER_diagram.{fmt}")], check=True)
    print("Wrote docs/ER_diagram.png and .svg")


if __name__ == "__main__":
    main()
