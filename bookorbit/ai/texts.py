"""Text helpers shared by the RAG retriever and the Reading Companion:
tokenising, chapter splitting, extractive summaries and offline quizzes."""
from __future__ import annotations

import random
import re
from collections import Counter

STOPWORDS = set("""
a about above after again against all am an and any are aren't as at be because been before being below
between both but by can can't cannot could couldn't did didn't do does doesn't doing don't down during each
few for from further had hadn't has hasn't have haven't having he he'd he'll he's her here here's hers herself
him himself his how how's i i'd i'll i'm i've if in into is isn't it it's its itself let's me more most mustn't
my myself no nor not of off on once only or other ought our ours ourselves out over own same shan't she she'd
she'll she's should shouldn't so some such than that that's the their theirs them themselves then there there's
these they they'd they'll they're they've this those through to too under until up very was wasn't we we'd we'll
we're we've were weren't what what's when when's where where's which while who who's whom why why's with won't
would wouldn't you you'd you'll you're you've your yours yourself yourselves tell please thank thanks know
does anyone something anything get give much many also us shall thee thou thy unto upon said one would could
""".split())

WORD_RE = re.compile(r"[A-Za-z][A-Za-z']*")


def stem(word: str) -> str:
    for suf in ("ings", "ing", "ies", "es", "s", "ed"):
        if len(word) > len(suf) + 3 and word.endswith(suf):
            return word[: -len(suf)] + ("y" if suf == "ies" else "")
    return word


def tokenize(text: str, keep_stopwords: bool = False) -> list[str]:
    toks = [w.lower().strip("'") for w in WORD_RE.findall(text or "")]
    return [stem(t) for t in toks if t and (keep_stopwords or t not in STOPWORDS) and len(t) > 1]


# ---------------------------------------------------------------- chapters
_HEADING_PATTERNS = [
    re.compile(r"^\s*(CHAPTER|Chapter)\s+[0-9IVXLC]+\.?.*$", re.M),
    re.compile(r"^\s*(Book|BOOK)\s+[IVXLC0-9]+\s*$", re.M),
    re.compile(r"^\s*Actus\s+\w+\.?.*$", re.M),
    re.compile(r"^\s*[IVXL]+\.\s+[A-Z][A-Za-z ,'\-]+$", re.M),
]


_ROMAN = re.compile(r"^[IVXLC]+\.?$")
_VOLUME = re.compile(r"^\s*(VOLUME|Volume|PART|Part)\s+([IVXLC0-9]+)\.?\s*$", re.M)


def smart_title(heading: str) -> str:
    """'CHAPTER IV. Down the Rabbit-Hole' -> 'Chapter IV. Down the Rabbit-Hole'."""
    out = []
    for w in " ".join(heading.split()).split(" "):
        if _ROMAN.match(w.upper()) and (w.isupper() or len(w) <= 4 and w.upper() == w):
            out.append(w.upper())
        elif w.isupper() and len(w) > 1:
            out.append(w.capitalize())
        else:
            out.append(w[:1].upper() + w[1:])
    return " ".join(out)


def split_chapters(text: str, words_per_part: int = 3500) -> list[dict]:
    """Return [{"title", "text"}]. Uses the book's own headings when it has at
    least 3 of them, otherwise fixed-size parts."""
    text = text.replace("\r\n", "\n")
    for pat in _HEADING_PATTERNS:
        marks = list(pat.finditer(text))
        if len(marks) >= 3:
            chapters = []
            volumes = list(_VOLUME.finditer(text))
            for i, m in enumerate(marks):
                end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
                body = text[m.end():end].strip()
                body = _VOLUME.sub("", body).strip()
                if len(body.split()) < 40 and chapters:   # stray heading (e.g. table of contents)
                    continue
                title = smart_title(m.group(0))
                vol = [v for v in volumes if v.start() < m.start()]
                if len(volumes) > 1 and vol:
                    title = f"Vol. {vol[-1].group(2)}, {title}"
                chapters.append({"title": title, "text": body})
            front = text[: marks[0].start()].strip()
            if len(front.split()) > 300:
                chapters.insert(0, {"title": "Opening", "text": front})
            if len(chapters) >= 2:
                return _split_long(chapters)
    words = text.split()
    parts = []
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    cur, count = [], 0
    for p in paras:
        cur.append(p)
        count += len(p.split())
        if count >= words_per_part:
            parts.append("\n\n".join(cur))
            cur, count = [], 0
    if cur:
        parts.append("\n\n".join(cur))
    if not parts:
        parts = [" ".join(words)]
    return [{"title": f"Part {i + 1}", "text": t} for i, t in enumerate(parts)]


def _split_long(chapters: list[dict], limit: int = 7000, size: int = 3500) -> list[dict]:
    out = []
    for ch in chapters:
        if len(ch["text"].split()) <= limit:
            out.append(ch)
            continue
        paras = [p for p in re.split(r"\n\s*\n", ch["text"]) if p.strip()]
        parts, cur, n = [], [], 0
        for p in paras:
            cur.append(p)
            n += len(p.split())
            if n >= size:
                parts.append("\n\n".join(cur))
                cur, n = [], 0
        if cur:
            parts.append("\n\n".join(cur))
        for i, t in enumerate(parts, 1):
            out.append({"title": f"{ch['title']} (part {i})", "text": t})
    return out


def strip_title_line(text: str) -> str:
    """NLTK Gutenberg files start with "[Title by Author Year]"."""
    return re.sub(r"^\s*\[[^\]]*\]\s*", "", text, count=1)


def paragraphs(text: str) -> list[str]:
    return [" ".join(p.split()) for p in re.split(r"\n\s*\n", text) if p.strip()]


# --------------------------------------------------------------- sentences
_SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[\"'A-Z])")


def sentences(text: str) -> list[str]:
    flat = " ".join(text.split())
    return [s.strip() for s in _SENT_RE.split(flat) if len(s.split()) >= 4]


def extractive_summary(text: str, n: int = 4) -> str:
    """Offline summary: the n most central sentences, in reading order."""
    sents = sentences(text)
    if len(sents) <= n:
        return " ".join(sents)
    freq = Counter(tokenize(text))
    if not freq:
        return " ".join(sents[:n])
    top = max(freq.values())
    scored = []
    for i, s in enumerate(sents):
        toks = tokenize(s)
        if not toks or len(s) > 400:
            continue
        score = sum(freq[t] / top for t in toks) / (len(toks) ** 0.6)
        scored.append((score, i))
    keep = sorted(i for _, i in sorted(scored, reverse=True)[:n])
    return " ".join(sents[i] for i in keep)


def cloze_quiz(text: str, n: int = 3, seed: int | None = None) -> list[dict]:
    """Offline 'Quiz me': fill-in-the-blank questions built from the chapter.
    Each item: {question, options[4], answer_index}."""
    rng = random.Random(seed)
    sents = [s for s in sentences(text) if 8 <= len(s.split()) <= 40]
    lower_words = Counter(w.lower() for w in WORD_RE.findall(text)
                          if w.islower() and w not in STOPWORDS and len(w) > 4 and "'" not in w)
    vocab = [w for w, c in lower_words.most_common(200)]
    honorifics = {"miss", "mrs", "mister", "sir", "lady", "lord", "madam", "master", "king", "queen"}
    caps = Counter(w for w in WORD_RE.findall(text) if w[0].isupper() and len(w) > 3 and "'" not in w
                   and w.lower() not in STOPWORDS and w.lower() not in honorifics)
    lower_all = {w.lower() for w in WORD_RE.findall(text) if w.islower()}
    names = [w for w, c in caps.most_common(40) if c >= 2 and w.lower() not in lower_all][:30]
    questions, used = [], set()
    rng.shuffle(sents)
    for s in sents:
        words = WORD_RE.findall(s)
        cands = [w for w in words if (w in names) or (w in vocab)]
        if any(w.startswith(c + "'") for w in words for c in cands):
            cands = [c for c in cands if not any(w.startswith(c + "'") for w in words)]
        cands = [w for w in cands if w.lower() not in used]
        if not cands:
            continue
        name_cands = [w for w in cands if w in names]
        target = rng.choice(name_cands if name_cands and rng.random() < 0.7 else cands)
        if target in names:
            pool = names
        else:   # distractors of a similar length read more naturally
            pool = sorted(vocab, key=lambda w: abs(len(w) - len(target)))[:25]
        distractors = [d for d in pool if d.lower() != target.lower()]
        rng.shuffle(distractors)
        if len(distractors) < 3:
            continue
        options = [target] + distractors[:3]
        rng.shuffle(options)
        blanked = re.sub(rf"\b{re.escape(target)}\b", "_____", s, count=1)
        questions.append({"question": f"Fill in the blank: “{blanked}”",
                          "options": options, "answer_index": options.index(target)})
        used.add(target.lower())
        if len(questions) == n:
            break
    return questions
