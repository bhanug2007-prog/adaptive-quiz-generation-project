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
The difficulty label comes from the request plan; when the AI reviewer is set up it also judges the real
difficulty (quality_service.py, run after these checks). Passing every check does not prove a question is factually correct; lecturers review before publishing.
"""
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from app.core.config import Settings
from app.services.model_service import ModelService
from app.services.quality_service import QUALITY_REASONS
from app.validators.mathcheck import can_run_safely, math_check, needs_math
from app.validators.mcq_format import parse_mcq
from app.validators.numcheck import numeric_conflict

TFIDF_DUP = 0.80
MIN_GROUNDING = 0.20
STRICT_GROUNDING = 0.25
STRICT_STEM_GROUNDING = 0.25

REASONS = {
    "format": "broken format, missing fields or repeated options",
    "duplicate": "same as or very close to an existing question",
    "answer_in_question": "question gives the answer away",
    "explanation_number": "explanation's number contradicts the answer key",
    "not_grounded": "not supported by or too little overlap with the source passage",
    "math_wrong_key": "Python check found a different correct option",
    "math_no_match": "Python check result matches no option",
    "math_ambiguous": "Multiple options match the computed numeric answer",
    "math_unsupported": "Calculation used an unsupported expression",
    "math_unchecked": "numeric answer could not be checked",
    "quarantined_invalid_mcq": "quarantined because the question or answer key is invalid",
    "quarantine_recheck_required": "edited after quarantine; run Check again before approving",
    **QUALITY_REASONS,
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


def _non_trivial_numbers(s: str) -> set[str]:
    out = set()
    for n in re.findall(r"\b\d+(?:\.\d+)?\b", s):
        if "." in n:
            val = float(n)
            out.add(str(int(val)) if val.is_integer() else str(val))
        else:
            val = int(n)
            if val >= 10:
                out.add(str(val))
    return out


def verify_source_grounding(mcq: dict, passage: str, strict: bool = False) -> tuple[bool, float, dict]:
    """Independent grounding verification combining overall overlap, stem overlap, and strict numeric facts."""
    key = mcq["options"]["ABCD".index(mcq["answer"])]
    overall = grounding(mcq, passage)
    stem_words = _content_words(mcq["question"])
    src = _content_words(passage)
    stem_g = round(len(stem_words & src) / len(stem_words), 3) if stem_words else 1.0

    ungrounded_nums: list[str] = []
    if strict:
        src_nums = _non_trivial_numbers(passage)
        stem_nums = _non_trivial_numbers(mcq["question"])
        ungrounded = stem_nums - src_nums
        may_be_derived_calc = needs_math(mcq) and bool(re.search(r"\d", mcq["question"]))
        if not may_be_derived_calc:
            ungrounded |= (_non_trivial_numbers(key) - src_nums)
        ungrounded_nums = sorted(ungrounded)

    min_overall = STRICT_GROUNDING if strict else MIN_GROUNDING
    min_stem = STRICT_STEM_GROUNDING if strict else 0.0
    ok = (overall >= min_overall) and (stem_g >= min_stem) and (not ungrounded_nums)
    info: dict = {"grounding": overall, "stem_grounding": stem_g, "grounding_verified": ok}
    if ungrounded_nums:
        info["ungrounded_numbers"] = ungrounded_nums[:5]
    if not ok:
        info["rules_failed"] = True
        info["rules_reason"] = "not_grounded"
    return ok, overall, info


class Validator:
    def __init__(self, settings: Settings, model: ModelService):
        self.s, self.model = settings, model

    def check(self, raw_text: str, existing_questions: list[str], passage: str | None = None,
              grounded: bool = False, strict_grounding: bool = False, source_meta: dict | None = None) -> Checked:
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
        info: dict = {"max_similarity": sim}
        if source_meta:
            info["source"] = source_meta
        if grounded and passage:
            g_ok, _g, g_info = verify_source_grounding(mcq, passage, strict=strict_grounding)
            info.update(g_info)
            if not g_ok:
                return Checked(False, "not_grounded", mcq, info=info)
        if not self.s.math_check:
            return Checked(True, mcq=mcq, info=info)
        if not needs_math(mcq):
            return Checked(True, mcq=mcq, info=info)
        res = math_check(
            mcq,
            lambda m: self.model.chat(m, temperature=0.0, max_tokens=400),
            allow_unchecked=not self.s.math_check_strict,
            allow_without_os_limits=self.s.math_check_allow_without_os_limits,
            worker_available=can_run_safely(self.s.math_check_allow_without_os_limits),
        )
        status = res["status"]
        info["math_status"] = status
        if res.get("method"):
            info["math_method"] = res["method"]
        if res.get("note"):
            info["math_note"] = res["note"]
        if res.get("errors"):
            info["math_errors"] = res["errors"][:3]
        if status == "verified":
            return Checked(True, mcq=mcq, math_verified=True, info=info)
        if status == "not_math":
            return Checked(True, mcq=mcq, info=info)
        if status == "unchecked" and res["accept"]:
            return Checked(True, mcq=mcq, info=info)
        return Checked(False, f"math_{status}", mcq, info=info)
