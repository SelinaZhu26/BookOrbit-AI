# BookOrbit AI

**An AI-enabled multimodal smart bookstore** for CSC 322 Software Engineering at The City College of New York.

Team: Zakiah Almontaser, Yixin Chen, Evan Florentino, Ibrahim Rahat, Selina Zhu

BookOrbit AI is a local desktop bookstore application. Customers sign in with face recognition. They can browse and search the catalog, including by cover image, and get personalized recommendations. They can buy books from a prepaid wallet, write moderated reviews, chat with an AI assistant, and read public-domain books with an AI Reading Companion. Super-Users manage the catalog, the taboo word list, suspended accounts and the book classification lists.

---

## 1. Features

| Area | What it does |
|---|---|
| Biometric accounts | Register with a face photo and sign in by face (YOLO detection + embeddings). A username locks for 5 minutes after 3 failed attempts. |
| Catalog | Visitors and Super-Users see the Top 3 popular books. Customers can browse by category and search by title, author, keyword, year or cover image (OpenCLIP). Each book has a details page. |
| Recommendations | Customers get "Recommended for You" based on their purchases and browsing history. |
| Wallet & purchases | Customers deposit funds, see a ledger and buy books. VIP Customers get 10% off. An insufficient balance costs a $1.00 fine, and a negative balance suspends the account. |
| Reviews & moderation | Up to 3 taboo words are masked; more than 3 blocks the review and issues a warning. A blocked review demotes a VIP to RC, and a Registered Customer is suspended on the 3rd warning. Ratings are weighted, with verified buyers counting twice. |
| AI Chatbot | Answers come from a local LLM through Ollama, grounded in store data with RAG. What each role may ask is restricted. Super-Users can ask admin questions, answered from facts computed from the data files. |
| Smart Reading Companion | Summarize a chapter, explain a passage, define a word or take a quiz, using only the book's own text. |
| Super-User tools | Add books, manage taboo words, reopen suspended accounts, view the No-Order and To-Order lists. |

**Roles:** VS = Visitor, RC = Registered Customer, VC = VIP Customer, SU = Super-User.

---

## 2. Setup

```bash
git clone https://github.com/<team-account>/BookOrbit-AI.git
cd BookOrbit-AI

python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows
.venv\Scripts\activate

pip install -r requirements.txt
```

### Real / AI modes (optional)

```bash
pip install -r requirements-real.txt

ollama pull llama3.2:3b          # on laptops with little RAM, use llama3.2:1b
ollama pull nomic-embed-text
```

Copy the environment template and edit the values for your machine, such as the Ollama address, the model names and which AI modes are turned on:

```bash
cp .env.example .env
```

Without the real-mode packages, an Ollama server or a webcam, the AI components fall back to lightweight stubs. Everything else in the app still works, and the test suite runs on any laptop.

---

## 3. Running the application

```bash
python seed.py     # creates data/ with demo users, books, reviews and policies
python app.py      # starts the BookOrbit AI desktop application
```

Running `seed.py` again resets the demo data. `data/` is created at run time, and each team member rebuilds it with `seed.py`.

---

## 4. Running the tests

```bash
python -m unittest discover -s tests -v
```

Run a single area:

```bash
python -m unittest tests.test_reviews -v
```

`tests/test_llm_live.py` and parts of `tests/test_real_modes.py` need Ollama and the real-mode packages. Run them only when those are installed and running.

| Test file | Covers |
|---|---|
| `test_auth.py` | Registration, face sign-in, attempt lockout |
| `test_catalog.py` | Browse, search, book details |
| `test_covers.py` | Cover-image search and the cover index |
| `test_recommendations.py` | Popular books and personalized recommendations |
| `test_wallet_purchase.py` | Deposits, purchases, VIP discount, fines, suspension |
| `test_reviews.py` | Taboo masking and blocking, warnings, demotion, weighted ratings, order lists |
| `test_chatbot.py`, `test_rag.py`, `test_llm.py`, `test_llm_live.py` | Chatbot permissions, retrieval, LLM client |
| `test_companion.py`, `test_texts.py` | Reading Companion and book text processing |
| `test_filestore.py`, `test_seed.py` | Text-file storage and demo data |
| `test_real_modes.py`, `test_ui_smoke.py` | Real-mode switching and UI start-up |

---

## 5. Git Repository

Repository address: `https://github.com/<team-account>/BookOrbit-AI` (to be completed by the team).

All project materials, including source code, documentation, test cases, and supporting data, are maintained in the repository:

```
BookOrbit-AI/
|
|-- README.md                  Setup and run instructions
|-- requirements.txt           Python dependencies
|-- requirements-real.txt      Additional dependencies for real/AI modes
|-- .env.example               Environment variable template
|-- .gitignore                 Files and directories excluded from Git
|-- app.py                     Application entry point
|-- seed.py                    Creates and initializes demo data
|-- CLAUDE.md                  Project development guidance
|
|-- docs/
|   |-- SRS.md                 Software Requirements Specification
|   |-- ASSUMPTIONS.md         Project assumptions
|   |-- PROGRESS.md            Development progress
|   `-- BookOrbit_AI_Phase2_Design_Report.pdf
|                              Phase 2 Design Report
|
|-- bookorbit/
|   |-- __init__.py
|   |-- config.py              Application configuration
|   |-- clock.py               Time-related utilities
|   |-- rules.py               Business rules
|   |-- money.py               Financial operations
|   |-- errors.py              Application errors
|   |-- app_context.py         Application context
|   |
|   |-- ui/
|   |   |-- __init__.py
|   |   |-- main_window.py     Main application window
|   |   |-- screens.py         Application screens
|   |   `-- widgets.py         Reusable UI components
|   |
|   |-- ai/
|   |                          AI and language-model components
|   |
|   |-- persistence/
|   |                          Data storage and persistence components
|   |
|   `-- services/
|                              Application service components
|
|-- tests/
|   |-- __init__.py
|   |-- helpers.py
|   |-- test_auth.py           Authentication tests
|   |-- test_catalog.py        Book catalog tests
|   |-- test_chatbot.py        Chatbot tests
|   |-- test_companion.py      Reading Companion tests
|   |-- test_covers.py         Book cover tests
|   |-- test_filestore.py      File storage tests
|   |-- test_llm.py            Language model tests
|   |-- test_llm_live.py       Live language model tests
|   |-- test_rag.py            Retrieval-Augmented Generation tests
|   |-- test_real_modes.py     Real-mode functionality tests
|   |-- test_recommendations.py Recommendation tests
|   |-- test_reviews.py        Review functionality tests
|   |-- test_seed.py           Seed data tests
|   |-- test_texts.py          Text processing tests
|   |-- test_ui_smoke.py       UI smoke tests
|   `-- test_wallet_purchase.py Wallet and purchase tests
|
|-- seed_texts/
|                              Sample book texts and policy documents
|
`-- data/
    |-- books.txt
    |-- users.txt
    |-- reviews.txt
    |-- purchases.txt
    |-- transactions.txt
    |-- reading_progress.txt
    |-- browse_history.txt
    |-- chat_log.txt
    |-- policies.txt
    |-- warnings.txt
    |-- login_attempts.txt
    |-- status_changes.txt
    |-- biometrics.txt
    |-- rag_chunks.txt
    |-- covers/
    |-- rag/
    |-- samples/
    `-- texts/
```

**Note:** `.venv/`, `.git/`, and `__pycache__/` are excluded because they are environment, version-control, and generated cache directories rather than project source materials. The `ai/`, `persistence/`, and `services/` folders are shown without individual filenames because their contents were not fully enumerated in the uploaded archive listing.

This structure is intended to reflect the Smart Bookstore project organization for the BookOrbit AI repository.

---

## Data storage

There is no database server. Each entity is stored in its own text file under `data/`, with one JSON object per line. Only the persistence layer (FileStore) reads or writes these files, and rewrites go through a temporary file and an atomic rename so a crash cannot leave a half-written file. Every change to money is recorded as a ledger transaction, and every role or status change is logged in `status_changes.txt`.

**Privacy:** only face *embeddings* are stored, never raw photos. `data/biometrics/` must never be committed.
