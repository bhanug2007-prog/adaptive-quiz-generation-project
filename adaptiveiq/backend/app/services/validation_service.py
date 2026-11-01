"""Checks every generated question before it is stored.

Pipeline (each step can reject the question; the reason is counted on the generation run):
 1. parse the model's text into question / 4 options / answer letter / explanation (structured output)
 2. schema + required fields: non-empty question (>= 10 chars), 4 non-empty options
 3. options unique (case and space insensitive)
 4. the answer letter is one of A-D
 5. duplicate check against questions already accepted in this run and the topic's question bank:
    exact or near-exact text (difflib ratio >= duplicate_threshold), or TF-IDF word-overlap cosine >= TFIDF_DUP.
    TF-IDF compares shared words and word pairs; it is not a semantic (meaning) embedding, so a reworded
    duplicate with different words can pass. Lecturer review is the backstop.
 6. give-away check: the stem must not contain the full answer text
 7. explanation numbers must agree with the marked answer
 8. source overlap, when reference material was supplied: the question + key + explanation must share
    enough content words with the passage it came from. Overlap is a cheap screen, not proof that the
    passage supports the question; factual support is judged by the lecturer and in offline evaluation
 9. Python maths check for numeric questions (the model writes a program; a sandbox runs it)
The difficulty label comes from the request plan and is checked against the allowed set at the API.
Passing every check does not prove a question is factually correct; lecturers review before publishing.
"""
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from app.core.config import Settings
from app.services.model_service import ModelService
from app.validators.mathcheck import can_run_safely, math_check, needs_math
from app.validators.mcq_format import parse_mcq
from app.validators.numcheck import numeric_conflict

TFIDF_DUP = 0.80
MIN_GROUNDING = 0.20

REASONS = {
    "format": "broken format, missing fields or repeated options",
    "duplicate": "same as or very close to an existing question",
    "answer_in_question": "question gives the answer away",
    "explanation_number": "explanation's number contradicts the answer key",
    "not_grounded": "too little word overlap with the reference passage",
    "math_wrong_key": "Python check found a different correct option",
    "math_no_match": "Python check result matches no option",
    "math_unchecked": "numeric answer could not be checked",
}

STOP = set("""a an the of to in on for and or is are was were be been being by with as at from that this these
those which what when where who whom whose why how it its into than then there their they them can could may
might will would shall should do does did not no yes if else so such any all each other some most more less
one two three four following true false correct incorrect option options answer question""".split())


@dataclass
class Checked:
    ok: bool
    reason: str | None = None
    mcq: dict | None = None
    math_verified: bool = False
    info: dict = field(default_factory=dict)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", s.lower()).strip()


def _content_words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z][a-z0-9]+|\d+(?:\.\d+)?", s.lower()) if w not in STOP and len(w) > 2 or w.isdigit()}


def tfidf_similarity(a: str, others: list[str]) -> float:
    """Highest TF-IDF cosine similarity (word 1-2 grams) between `a` and any of `others`."""
    if not others:
        return 0.0
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError:                                          # scikit-learn missing: fall back to difflib only
        return 0.0
    try:
        m = TfidfVectorizer(ngram_range=(1, 2), stop_words="english").fit_transform([a] + others)
    except ValueError:                                           # only stop words
        return 0.0
    return float(cosine_similarity(m[0:1], m[1:]).max())


def is_duplicate(question: str, existing: list[str], threshold: float) -> tuple[bool, float]:
    q = _norm(question)
    for x in existing:
        if q == _norm(x) or SequenceMatcher(None, q, _norm(x)).ratio() >= threshold:
            return True, 1.0
    sim = tfidf_similarity(question, existing)
    return sim >= TFIDF_DUP, round(sim, 3)


def gives_answer_away(mcq: dict) -> bool:
    key = _norm(mcq["options"]["ABCD".index(mcq["answer"])])
    others = [_norm(o) for i, o in enumerate(mcq["options"]) if "ABCD"[i] != mcq["answer"]]
    q = _norm(mcq["question"])
    return len(key.split()) >= 3 and key in q and not any(o and o in q for o in others)


def grounding(mcq: dict, passage: str) -> float:
    """Share of the question's content words (stem + key + explanation) that appear in the passage."""
    key = mcq["options"]["ABCD".index(mcq["answer"])]
    words = _content_words(" ".join([mcq["question"], key, mcq.get("explanation") or ""]))
    if not words:
        return 1.0
    src = _content_words(passage)
    return round(len(words & src) / len(words), 3)


class Validator:
    def __init__(self, settings: Settings, model: ModelService):
        self.s, self.model = settings, model

    def check(self, raw_text: str, existing_questions: list[str], passage: str | None = None,
              grounded: bool = False) -> Checked:
        mcq = parse_mcq(raw_text)
        if mcq is None or len(mcq["question"]) < 10:
            return Checked(False, "format")
        dup, sim = is_duplicate(mcq["question"], existing_questions, self.s.duplicate_threshold)
        if dup:
            return Checked(False, "duplicate", mcq, info={"similarity": sim})
        if gives_answer_away(mcq):
            return Checked(False, "answer_in_question", mcq)
        if numeric_conflict(mcq):
            return Checked(False, "explanation_number", mcq)
        info = {"max_similarity": sim}
        if grounded and passage:
            g = grounding(mcq, passage)
            info["grounding"] = g
            if g < MIN_GROUNDING:
                return Checked(False, "not_grounded", mcq, info=info)
        if not self.s.math_check:
            return Checked(True, mcq=mcq, info=info)
        if not can_run_safely(self.s.math_check_allow_without_os_limits):
            # No OS sandbox limits on this machine (Windows): never run model-written code here.
            if not needs_math(mcq):
                return Checked(True, mcq=mcq, info=info)
            info["math_status"] = "unchecked"
            info["math_note"] = "Python check skipped: this machine cannot sandbox it (use Docker or Linux)."
            if self.s.math_check_strict:
                return Checked(False, "math_unchecked", mcq, info=info)
            return Checked(True, mcq=mcq, info=info)
        res = math_check(mcq, lambda m: self.model.chat(m, temperature=0.0, max_tokens=400),
                         allow_unchecked=not self.s.math_check_strict)
        status = res["status"]
        info["math_status"] = status
        if status == "verified":
            return Checked(True, mcq=mcq, math_verified=True, info=info)
        if status == "not_math" or (status == "unchecked" and res["accept"]):
            return Checked(True, mcq=mcq, info=info)
        return Checked(False, f"math_{status}", mcq, info=info)
