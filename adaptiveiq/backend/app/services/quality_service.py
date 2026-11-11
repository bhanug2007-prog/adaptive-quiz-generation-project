"""AI review of generated questions, after the Python checks in validation_service.

Order for every generated question:
 1. the Python checks (format, duplicates, give-away, numbers, source overlap, maths) - always
 2. this AI review, when GROK_API_KEY is set: correctness, topic relevance, difficulty, options,
    more than one correct option, ambiguity, explanation and clarity, returned as JSON
 3. the decision below, made in Python from the review's individual answers (the reviewer's own
    "passed" is recorded but never trusted alone)

The reviewer is an extra screen, not the truth: lecturers still review and approve every question.

Fallback: with no key, a timeout, a rate limit, quota exhaustion, a refused key or an invalid reply, the
question keeps the result of the Python checks and is marked "AI review not done" with the reason.
Rate-limit, quota and key errors pause Grok calls for GROK_COOLDOWN_S so a broken account is not
called again for every question. Nothing about students is ever sent: only the question, its options,
answer, explanation, subject, topic, requested difficulty and the source passage.
"""
import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.core.config import Settings

log = logging.getLogger("adaptiveiq.quality")
LEVELS = ("easy", "medium", "hard")
NOTE_MAX = 400
PASSAGE_MAX = 2000

LEVEL_GUIDE = ("easy = recall of one fact or definition; "
               "medium = apply one concept, compare two ideas, or a one-step calculation; "
               "hard = several steps of reasoning, analysis, or combining concepts")

SYSTEM = ("You review multiple-choice questions that another AI wrote for B.Tech university exams. "
          "Be strict and factual and judge only what is written. Reply with one JSON object and no other text.")

USER = """Subject: {subject}
Topic: {topic}
Requested difficulty: {difficulty} ({guide})
{passage_block}
Question: {question}
Options:
{options}
Marked correct answer: {answer}
Explanation: {explanation}

Check the question and reply with this JSON object (keep every note under 40 words):
{{
  "quality_score": <integer 0-100, overall fitness for a university exam>,
  "correctness": {{"verdict": "correct" | "incorrect" | "unsure", "note": "<is the marked answer right?>"}},
  "relevance": {{"ok": true | false, "note": "<does it test the topic?>"}},
  "difficulty": {{"assessed": "easy" | "medium" | "hard", "note": "<the real cognitive level, using the scale above>"}},
  "options": {{"ok": true | false, "note": "<are the wrong options distinct, plausible and clearly wrong?>"}},
  "multiple_correct": {{"value": true | false, "note": "<could more than one option be defended as correct?>"}},
  "ambiguity": {{"ambiguous": true | false, "note": "<could a well-prepared student read it two ways?>"}},
  "explanation": {{"supports_answer": true | false, "note": "<does the explanation justify the marked answer?>"}},
  "clarity": {{"ok": true | false, "note": "<is the wording clear and complete?>"}},
  "passed": true | false,
  "feedback": "<one or two sentences for the lecturer>",
  "regeneration_instructions": "<what a rewrite must fix, or empty>"
}}"""

# Shown to lecturers next to rejected attempts and kept questions (merged into validation_service.REASONS).
QUALITY_REASONS = {
    "quality_incorrect": "AI review: the marked answer looks wrong",
    "quality_multiple_correct": "AI review: more than one option could be correct",
    "quality_ambiguous": "AI review: the question can be read more than one way",
    "quality_off_topic": "AI review: does not test the requested topic",
    "quality_options": "AI review: weak or overlapping wrong options",
    "quality_explanation": "AI review: the explanation does not support the answer",
    "quality_unclear": "AI review: unclear or incomplete wording",
    "quality_difficulty": "AI review: difficulty differs from the one requested",
    "quality_low_score": "AI review: overall quality score too low",
    "quality_other": "AI review: failed for another reason (see feedback)",
}


_SECRET_PATTERNS = (
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]{8,}", re.I),
    re.compile(r"\b(?:gsk|xai|sk)_[A-Za-z0-9._\-]{8,}"),
    re.compile(r"\b(?:xai|sk)-[A-Za-z0-9._\-]{12,}"),
    re.compile(r"(https?://[^/\s:@]+:)[^@\s]+@"),
)


def scrub_secrets(text: str, extra_secrets: tuple[str, ...] = ()) -> str:
    """Removes API keys, bearer tokens, and URL credentials from logs, errors, and audit records."""
    out = str(text or "")
    for secret in extra_secrets:
        s = (secret or "").strip()
        if len(s) >= 6:
            out = out.replace(s, "[redacted]")
    out = _SECRET_PATTERNS[0].sub(r"\1[redacted]", out)
    out = _SECRET_PATTERNS[1].sub("[redacted]", out)
    out = _SECRET_PATTERNS[2].sub("[redacted]", out)
    out = _SECRET_PATTERNS[3].sub(r"\1[redacted]@", out)
    return out


def extract_json_object(text: str) -> dict:
    """Extracts the first valid JSON object from model output, stripping <think> blocks and fences."""
    raw = (text or "").strip()
    if not raw:
        raise ValueError("empty reply")
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.S | re.I).strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I).strip()
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", cleaned):
        try:
            obj, _ = dec.raw_decode(cleaned[m.start():])
            if isinstance(obj, dict):
                return obj
        except ValueError:
            continue
    raise ValueError("no JSON object in reply")


def _clip(s) -> str:
    return " ".join(str(s or "").split())[:NOTE_MAX]


def _strict_bool(v):
    if not isinstance(v, bool):
        raise ValueError("must be a boolean")
    return v


class _Note(BaseModel):
    model_config = ConfigDict(extra="ignore")
    note: str = ""

    @field_validator("note", mode="before")
    @classmethod
    def _n(cls, v):
        return _clip(v)


class _Correctness(_Note):
    verdict: Literal["correct", "incorrect", "unsure"]


class _Ok(_Note):
    ok: bool

    @field_validator("ok", mode="before")
    @classmethod
    def _b(cls, v):
        return _strict_bool(v)


class _Difficulty(_Note):
    assessed: Literal["easy", "medium", "hard"]


class _Value(_Note):
    value: bool

    @field_validator("value", mode="before")
    @classmethod
    def _b(cls, v):
        return _strict_bool(v)


class _Ambiguity(_Note):
    ambiguous: bool

    @field_validator("ambiguous", mode="before")
    @classmethod
    def _b(cls, v):
        return _strict_bool(v)


class _Explanation(_Note):
    supports_answer: bool

    @field_validator("supports_answer", mode="before")
    @classmethod
    def _b(cls, v):
        return _strict_bool(v)


class Review(BaseModel):
    """The reviewer's reply must match this strictly (wrong types, bools-as-ints, or missing keys = invalid)."""
    model_config = ConfigDict(extra="ignore")
    quality_score: int = Field(ge=0, le=100)
    correctness: _Correctness
    relevance: _Ok
    difficulty: _Difficulty
    options: _Ok
    multiple_correct: _Value
    ambiguity: _Ambiguity
    explanation: _Explanation
    clarity: _Ok
    passed: bool
    feedback: str = ""
    regeneration_instructions: str = ""

    @field_validator("quality_score", mode="before")
    @classmethod
    def _score_int(cls, v):
        if isinstance(v, bool):
            raise ValueError("quality_score cannot be a boolean")
        if isinstance(v, float) and v.is_integer():
            return int(v)
        if not isinstance(v, int):
            raise ValueError("quality_score must be an integer")
        return v

    @field_validator("passed", mode="before")
    @classmethod
    def _passed_bool(cls, v):
        return _strict_bool(v)

    @field_validator("difficulty", "correctness", mode="before")
    @classmethod
    def _lower(cls, v):
        if isinstance(v, dict):
            v = {k: (x.strip().lower() if isinstance(x, str) and k in ("assessed", "verdict") else x) for k, x in v.items()}
        return v

    @field_validator("feedback", "regeneration_instructions", mode="before")
    @classmethod
    def _c(cls, v):
        return _clip(v)


class AIReviewError(Exception):
    """kind: timeout | unavailable | rate_limited | quota | auth | config | bad_response. Message is safe to show."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


PAUSE_KINDS = {"rate_limited", "quota", "auth", "config"}


def parse_review(text: str) -> Review:
    try:
        obj = extract_json_object(text)
    except ValueError as e:
        raise AIReviewError("bad_response", "The AI reviewer did not reply with JSON.") from e
    try:
        return Review.model_validate(obj)
    except ValidationError as e:
        raise AIReviewError("bad_response", "The AI reviewer's reply did not match the expected format.") from e


def decide(r: Review, requested: str | None, s: Settings) -> str | None:
    """Returns the first failed check, or None when the question passes. Order = most serious first."""
    if r.correctness.verdict == "incorrect":
        return "quality_incorrect"
    if r.multiple_correct.value:
        return "quality_multiple_correct"
    if r.ambiguity.ambiguous:
        return "quality_ambiguous"
    if not r.relevance.ok:
        return "quality_off_topic"
    if not r.explanation.supports_answer:
        return "quality_explanation"
    if not r.options.ok:
        return "quality_options"
    if not r.clarity.ok:
        return "quality_unclear"
    if s.quality_check_difficulty and requested in LEVELS and r.difficulty.assessed != requested:
        return "quality_difficulty"
    if r.quality_score < s.quality_min_score:
        return "quality_low_score"
    if not r.passed:
        return "quality_other"
    return None


@dataclass
class QualityResult:
    passed: bool
    evaluator: str                                  # grok | rules
    reason: str | None = None
    evaluator_model: str | None = None
    score: float | None = None
    assessed_difficulty: str | None = None
    ai: dict | None = None                          # the validated review
    feedback: str | None = None
    regeneration_instructions: str | None = None
    ai_error: str | None = None
    checks: dict = field(default_factory=dict)
    ai_called: bool = False                         # a Grok request was made (counted in the agent log)

    def summary(self) -> dict:
        """Compact form stored on Question.validation["quality"] for the review screen."""
        status = "failed" if not self.passed else ("passed" if self.evaluator == "grok" else "not_checked")
        return {"status": status, "evaluator": self.evaluator,
                "model": self.evaluator_model, "score": self.score, "reason": self.reason,
                "reason_text": QUALITY_REASONS.get(self.reason) if self.reason else None,
                "assessed_difficulty": self.assessed_difficulty, "feedback": self.feedback,
                "ai": self.ai, "ai_error": self.ai_error}


def _provider_error_text(r, secret: str = "") -> str:
    """Provider error message (e.g. an unknown model name), shortened and scrubbed of any secret/key."""
    try:
        data = r.json()
        msg = data.get("error") if isinstance(data, dict) else None
        if isinstance(msg, dict):
            msg = msg.get("message")
        text = str(msg or data)
    except ValueError:
        text = r.text
    cleaned = scrub_secrets(" ".join(str(text or "").split()), (secret,))[:200]
    return cleaned or "no details"


_grok_error_text = _provider_error_text


class GroqClient:
    """OpenAI-compatible chat completions client (configured for Groq API by default, or xAI Grok)."""

    def __init__(self, s: Settings):
        self.s = s
        read_timeout = max(0.1, float(s.grok_timeout_s))
        self.client = httpx.Client(base_url=s.grok_base_url.rstrip("/"),
                                   headers={"Authorization": f"Bearer {s.grok_api_key.strip()}",
                                            "Content-Type": "application/json"},
                                   timeout=httpx.Timeout(read_timeout, connect=min(10.0, max(1.0, read_timeout))))

    def _once(self, messages: list[dict], max_tokens: int = 900) -> str:
        provider = self.s.ai_provider_label
        body = {"model": self.s.grok_model, "messages": messages, "temperature": 0.0, "max_tokens": max_tokens}
        try:
            r = self.client.post("/chat/completions", json=body)
        except httpx.TimeoutException as e:
            raise AIReviewError("timeout", f"The AI reviewer ({provider}) did not answer within {self.s.grok_timeout_s:.0f} seconds.") from e
        except httpx.HTTPError as e:
            if "10013" in str(e):
                raise AIReviewError("config", f"Windows blocked the backend's connection to {provider} (socket error 10013). "
                                             "Restart the backend with network access outside the restricted sandbox. "
                                             "Changing the API key or model will not resolve this network permission error.") from e
            raise AIReviewError("unavailable", f"Cannot reach the AI reviewer ({provider}).") from e
        if r.status_code in (401, 403):
            raise AIReviewError("auth", f"{provider} refused the API key (check GROK_API_KEY).")
        if r.status_code == 402 or (r.status_code == 429 and re.search(r"quota|credit|billing|spend", r.text, re.I)):
            raise AIReviewError("quota", f"The {provider} account has no quota or credit left.")
        if r.status_code == 429:
            raise AIReviewError("rate_limited", f"{provider} is rate limiting requests.")
        if r.status_code in (400, 404, 422):
            err_txt = _provider_error_text(r, self.s.grok_api_key)
            if r.status_code == 404 or re.search(r"model.*not found|does not exist|decommissioned|unknown model", err_txt, re.I):
                raise AIReviewError("config", f"{provider} model is unavailable or not found (HTTP {r.status_code}); "
                                              f"check GROK_MODEL. {provider} said: {err_txt}")
            raise AIReviewError("config", f"{provider} rejected the request (HTTP {r.status_code}); check GROK_MODEL. "
                                          f"{provider} said: {err_txt}")
        if r.status_code >= 400:
            raise AIReviewError("unavailable", f"{provider} returned HTTP {r.status_code}.")
        try:
            data = r.json()
            if isinstance(data, dict) and data.get("error"):
                raise AIReviewError("unavailable", f"{provider} returned an error: {_provider_error_text(r, self.s.grok_api_key)}")
            content = data["choices"][0]["message"]["content"]
        except AIReviewError:
            raise
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise AIReviewError("bad_response", f"{provider} sent a response in an unexpected format.") from e
        if not isinstance(content, str) or not content.strip():
            raise AIReviewError("bad_response", f"{provider} sent an empty reply (did not reply with JSON).")
        return content

    def chat(self, messages: list[dict], max_tokens: int = 900) -> str:
        # Only transient network/timeout/5xx errors are retried once with bounded backoff; auth, quota,
        # rate limit, bad model config, and malformed replies fail fast without burning extra requests.
        max_retries = 1
        backoff = min(1.5, max(0.25, float(self.s.grok_timeout_s) * 0.5))
        for attempt in range(max_retries + 1):
            try:
                return self._once(messages, max_tokens)
            except AIReviewError as e:
                if e.kind not in ("timeout", "unavailable") or attempt >= max_retries:
                    raise
                time.sleep(backoff * (attempt + 1))

    def close(self):
        self.client.close()


GrokClient = GroqClient


class QualityEvaluator:
    def __init__(self, s: Settings, client: GroqClient | None = None):
        self.s = s
        self.client = client if client is not None else (GroqClient(s) if s.grok_configured else None)
        self._lock = threading.Lock()
        self._paused_until = 0.0
        self._pause_reason: str | None = None
        self.calls = 0                               # AI requests made by this process (for tests and health)

    # ---------- state ----------

    def enabled_for(self, purpose: str | None) -> bool:
        if not self.s.quality_check:
            return False
        return purpose != "practice" or self.s.quality_check_practice

    def status(self) -> dict:
        with self._lock:
            paused = time.monotonic() < self._paused_until
            left = max(0, round(self._paused_until - time.monotonic())) if paused else 0
            reason = self._pause_reason if paused else None
        if not self.s.quality_check:
            state = "off"
        elif self.client is None:
            state = "not_configured"
        else:
            state = "paused" if paused else "ready"
        return {"state": state, "provider": self.s.ai_provider_id, "provider_label": self.s.ai_provider_label,
                "model": self.s.grok_model if self.client else None,
                "paused_for_s": left, "detail": reason, "practice": self.s.quality_check_practice}

    def skip_reason(self, purpose: str | None) -> str | None:
        """Why a question of this purpose gets no AI review (None when it normally would)."""
        if purpose == "practice" and self.s.quality_check and not self.s.quality_check_practice:
            return "AI review is not used for student practice questions."
        return self._unavailable_reason()

    def _pause(self, reason: str):
        clean = scrub_secrets(reason, (self.s.grok_api_key,))
        with self._lock:
            self._paused_until = time.monotonic() + self.s.grok_cooldown_s
            self._pause_reason = clean

    def _unavailable_reason(self) -> str | None:
        if not self.s.quality_check:
            return "AI review is switched off (QUALITY_CHECK=false)."
        if self.client is None:
            return "No AI reviewer is set up (GROK_API_KEY is empty)."
        with self._lock:
            if time.monotonic() < self._paused_until:
                return f"AI review paused: {self._pause_reason}"
        return None

    # ---------- shared AI access (also used by the Lecturer Insights Agent) ----------

    def llm_unavailable(self) -> str | None:
        """Why the external AI reviewer/insights provider cannot be called right now (None when it can).
        Ignores QUALITY_CHECK, which only switches the question review off."""
        if self.client is None:
            return "No AI model is set up (GROK_API_KEY is empty)."
        with self._lock:
            if time.monotonic() < self._paused_until:
                return f"AI paused: {self._pause_reason}"
        return None

    def llm_chat(self, messages: list[dict], max_tokens: int = 900) -> str:
        """One AI chat call with the same timeout, bounded retry, and pause rules as the question review.
        Raises AIReviewError (its message is safe to show and contains no secrets)."""
        why = self.llm_unavailable()
        if why:
            raise AIReviewError("unavailable", why)
        with self._lock:
            self.calls += 1
        try:
            return self.client.chat(messages, max_tokens)
        except AIReviewError as e:
            if e.kind in PAUSE_KINDS:
                self._pause(str(e))
            raise

    # ---------- review ----------

    def messages(self, mcq: dict, subject: str, topic: str, requested: str | None, passage: str | None,
                 strict_source: bool = False) -> list[dict]:
        opts = "\n".join(f"({l}) {t}" for l, t in zip("ABCD", mcq["options"]))
        if passage:
            if strict_source:
                block = (
                    "Source passage from the uploaded study material (every factual claim in the question, "
                    "correct answer, and explanation MUST be directly supported by this passage; if unsupported, "
                    "mark passed as false and explain what is unsupported in feedback):\n"
                    f"\"\"\"{passage[:PASSAGE_MAX]}\"\"\"\n"
                )
            else:
                block = f"Source passage the question was written from:\n\"\"\"{passage[:PASSAGE_MAX]}\"\"\"\n"
        else:
            block = ""
        user = USER.format(subject=subject, topic=topic, difficulty=requested or "not specified", guide=LEVEL_GUIDE,
                           passage_block=block, question=mcq["question"], options=opts, answer=mcq["answer"],
                           explanation=mcq.get("explanation") or "(none)")
        return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]

    def evaluate(self, mcq: dict, subject: str, topic: str, requested: str | None, passage: str | None = None,
                 rules_info: dict | None = None, strict_source: bool = False) -> QualityResult:
        """`mcq` normally already passed the Python checks. Never raises: an AI failure falls back to those checks.
        A high AI quality score or `passed: true` can NEVER override failed deterministic, grounding, or math checks."""
        checks = {"python_checks": "passed", **(rules_info or {})}
        ms = (rules_info or {}).get("math_status")
        math_failed = ms in {"wrong_key", "no_match", "ambiguous", "unsupported", "unchecked"} or bool(
            (rules_info or {}).get("math_failed")
        )
        rules_failed = bool((rules_info or {}).get("rules_failed")) or (rules_info or {}).get("grounding_verified") is False
        hard_failed = math_failed or rules_failed
        hard_reason = (f"math_{ms}" if ms in {"wrong_key", "no_match", "ambiguous", "unsupported", "unchecked"} else
                       (rules_info or {}).get("rules_reason") or (
                           "not_grounded" if (rules_info or {}).get("grounding_verified") is False
                           else ("math_unchecked" if math_failed else None)))
        if hard_failed:
            checks["python_checks"] = "failed"
        why = self._unavailable_reason()
        called = False
        if why is None:
            try:
                with self._lock:
                    self.calls += 1
                called = True
                review = parse_review(self.client.chat(self.messages(mcq, subject, topic, requested, passage, strict_source)))
            except AIReviewError as e:
                if e.kind in PAUSE_KINDS:
                    self._pause(str(e))
                log.warning("AI review fell back to the Python checks: %s (%s)", scrub_secrets(str(e), (self.s.grok_api_key,)), e.kind)
                why = scrub_secrets(str(e), (self.s.grok_api_key,))
            except Exception:                        # never let the reviewer break generation
                log.exception("AI review crashed")
                why = "The AI review failed unexpectedly."
            else:
                reason = decide(review, requested, self.s)
                ai = review.model_dump()
                checks["ai"] = ai
                effective_reason = hard_reason if hard_failed else reason
                return QualityResult(passed=(not hard_failed and reason is None), evaluator="grok",
                                     reason=effective_reason, evaluator_model=self.s.grok_model,
                                     score=float(review.quality_score), assessed_difficulty=review.difficulty.assessed,
                                     ai=ai, feedback=review.feedback or None,
                                     regeneration_instructions=review.regeneration_instructions or None,
                                     checks=checks, ai_called=True)
        return QualityResult(passed=not hard_failed, evaluator="rules",
                             reason=hard_reason if hard_failed else None, ai_error=why, checks=checks,
                             ai_called=called)

    def close(self):
        if self.client is not None:
            self.client.close()
