"""Topic mastery estimation.

Method (version MASTERY_VERSION): a Beta-Bernoulli estimate with weighted evidence.

Every answer on a topic adds a weighted count to "correct" or "incorrect":

    weight = recency * difficulty * repeat

    recency    = 0.5 ** (age_days / half_life_days)   recent answers matter more
    difficulty = correct on hard 1.25, medium 1.0, easy 0.75;
                 wrong on easy 1.25, medium 1.0, hard 0.75   (missing an easy item says more)
    repeat     = 0.5 when the student has already seen that exact question (memory, not mastery)

Skipped questions in a submitted quiz count as incorrect at half weight (SKIP_WEIGHT): skipping is
weak evidence of not knowing, and ignoring it would let students raise their score by skipping.

    alpha = 1 + sum(weight of correct),  beta = 1 + sum(weight of incorrect)     (uniform prior)
    score = alpha / (alpha + beta)
    80% interval ~ score +- 1.2816 * sqrt(score (1 - score) / (alpha + beta + 1))

Labels need evidence: fewer than `min_evidence` distinct questions is always "insufficient_evidence",
whatever the accuracy. The thresholds are in LabelThresholds and can be changed in one place.

Limitations: it treats questions within a topic as interchangeable apart from their difficulty label,
it trusts the difficulty labels (see question calibration), and recency decay is a fixed assumption,
not fitted to data. Compare with the plain-accuracy baseline in evaluation/simulate_mastery.py.
"""
import math
from dataclasses import dataclass, field
from datetime import datetime

MASTERY_VERSION = "mastery-beta-v3"
SKIP_WEIGHT = 0.5
Z80 = 1.2816

CORRECT_W = {"easy": 0.75, "medium": 1.0, "hard": 1.25}
WRONG_W = {"easy": 1.25, "medium": 1.0, "hard": 0.75}

LABELS = ["insufficient_evidence", "needs_improvement", "developing", "proficient", "strong"]
LABEL_TEXT = {
    "insufficient_evidence": "Insufficient evidence",
    "needs_improvement": "Needs improvement",
    "developing": "Developing",
    "proficient": "Proficient",
    "strong": "Strong evidence of mastery",
}


@dataclass(frozen=True)
class LabelThresholds:
    strong_lower: float = 0.80        # the whole 80% interval sits above 0.80
    proficient_score: float = 0.70
    developing_score: float = 0.50


@dataclass
class Observation:
    question_id: int
    correct: bool | None              # None = skipped inside a submitted quiz
    difficulty: str
    at: datetime
    repeat: bool = False              # the student had already answered this exact question before
    time_spent_s: float | None = None


@dataclass
class MasteryEstimate:
    score: float
    lower: float
    upper: float
    evidence: float                   # weighted number of answers
    answers: int
    unique_questions: int
    correct: int
    incorrect: int
    skipped: int
    label: str
    evidence_level: str               # low | moderate | high
    recent_accuracy: float | None     # last RECENT_N answered (skips excluded)
    recent_n: int
    historical_accuracy: float | None
    trend: str = "not_enough_data"   # improving | declining | stable | not_enough_data
    details: dict = field(default_factory=dict)


RECENT_N = 5
TREND_MIN = 5                         # answered questions needed on each side (last 5, and before them)
TREND_DELTA = 0.20                    # the change must be at least 20 percentage points ...
TREND_ALPHA = 0.05                    # ... and unlikely to be chance (Fisher's exact test, two-sided, 5% level)

EVIDENCE_TEXT = {"none": "No evidence", "low": "Insufficient evidence", "moderate": "Limited evidence",
                 "high": "Stronger evidence"}
TREND_TEXT = {"improving": "Improving", "declining": "Declining", "stable": "No clear change",
              "not_enough_data": "Not enough data for a trend"}


def fisher_exact_p(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher's exact test p-value for the 2x2 table [[a, b], [c, d]].

    Sums the probabilities of every table with the same row and column totals that is no more likely
    than the observed one (the usual two-sided definition, as in scipy.stats.fisher_exact)."""
    r1, r2, c1 = a + b, c + d, a + c
    n = r1 + r2

    def prob(x):
        return math.comb(r1, x) * math.comb(r2, c1 - x) / math.comb(n, c1)

    lo, hi = max(0, c1 - r2), min(r1, c1)
    p_obs = prob(a)
    return min(1.0, sum(p for p in (prob(x) for x in range(lo, hi + 1)) if p <= p_obs * (1 + 1e-7)))


def trend(recent_correct: int, recent_n: int, hist_correct: int, hist_n: int) -> tuple[str, float | None]:
    """Compares the last RECENT_N answered questions with everything answered before them.

    Returns (trend, p-value). Five answers are noisy: a plain 20-point threshold flagged about 1 in 5
    students with unchanged ability in simulation (evaluation/simulate_mastery.py). The difference must
    also pass Fisher's exact test. Version 2 used a two-proportion z-test, which is unreliable with five
    answers on one side (it called 0 of 5 vs 3 of 5 a decline; the exact p-value is 0.17). "stable"
    therefore means "no clear change", not "proven stable"."""
    if recent_n < TREND_MIN or hist_n < TREND_MIN:
        return "not_enough_data", None
    d = recent_correct / recent_n - hist_correct / hist_n
    p = fisher_exact_p(recent_correct, recent_n - recent_correct, hist_correct, hist_n - hist_correct)
    if d >= TREND_DELTA and p < TREND_ALPHA:
        return "improving", p
    if d <= -TREND_DELTA and p < TREND_ALPHA:
        return "declining", p
    return "stable", p


def trend_reason(e: "MasteryEstimate") -> str:
    if e.trend == "not_enough_data":
        return (f"A trend needs at least {TREND_MIN} answered questions before the last {RECENT_N}, "
                f"and the last {RECENT_N} themselves.")
    base = (f"Last {e.recent_n} answers: {pct100(e.recent_accuracy)}% correct, compared with "
            f"{pct100(e.historical_accuracy)}% before that")
    if e.trend == "stable":
        return base + "; the difference is too small to be more than chance."
    return base + "."


def pct100(x: float) -> int:
    """A 0-1 value as the whole number shown on screen (half rounds up, so 72.5 shows as 73).

    Every threshold below is compared on this shown number, so a label can never disagree with the
    score next to it (for example 70/100 labelled "Developing" because the hidden value was 69.996)."""
    return int(math.floor(x * 100 + 0.5))


def evidence_level(unique_questions: int, min_evidence: int) -> str:
    if unique_questions < min_evidence:
        return "low"
    return "moderate" if unique_questions < 3 * min_evidence else "high"


def label_for(score: float, lower: float, unique_questions: int, min_evidence: int,
              t: LabelThresholds = LabelThresholds()) -> str:
    if unique_questions < min_evidence:
        return "insufficient_evidence"
    if pct100(lower) >= pct100(t.strong_lower):
        return "strong"
    if pct100(score) >= pct100(t.proficient_score):
        return "proficient"
    if pct100(score) >= pct100(t.developing_score):
        return "developing"
    return "needs_improvement"


def estimate(obs: list[Observation], now: datetime, half_life_days: float = 21.0, min_evidence: int = 5,
             thresholds: LabelThresholds = LabelThresholds()) -> MasteryEstimate:
    a, b = 1.0, 1.0
    for o in obs:
        age = max(0.0, (now - o.at).total_seconds() / 86400)
        w = 0.5 ** (age / half_life_days)
        if o.repeat:
            w *= 0.5
        level = o.difficulty if o.difficulty in CORRECT_W else "medium"
        if o.correct is True:
            a += w * CORRECT_W[level]
        elif o.correct is False:
            b += w * WRONG_W[level]
        else:
            b += w * WRONG_W[level] * SKIP_WEIGHT
    n = a + b
    score = a / n
    half = Z80 * math.sqrt(score * (1 - score) / (n + 1))
    lower, upper = max(0.0, score - half), min(1.0, score + half)

    answered = sorted([o for o in obs if o.correct is not None], key=lambda o: o.at)
    recent = answered[-RECENT_N:]
    older = answered[:-RECENT_N]
    uq = len({o.question_id for o in obs})
    lab = label_for(score, lower, uq, min_evidence, thresholds)
    tr, tp = trend(sum(o.correct for o in recent), len(recent), sum(o.correct for o in older), len(older))
    tp = round(tp, 4) if tp is not None else None
    return MasteryEstimate(
        score=round(score, 4), lower=round(lower, 4), upper=round(upper, 4), evidence=round(n - 2, 3),
        answers=len(obs), unique_questions=uq,
        correct=sum(o.correct is True for o in obs), incorrect=sum(o.correct is False for o in obs),
        skipped=sum(o.correct is None for o in obs), label=lab,
        evidence_level=evidence_level(uq, min_evidence),
        recent_accuracy=round(sum(o.correct for o in recent) / len(recent), 4) if recent else None,
        recent_n=len(recent),
        historical_accuracy=round(sum(o.correct for o in older) / len(older), 4) if older else None,
        trend=tr,
        details={"alpha": round(a, 3), "beta": round(b, 3), "half_life_days": half_life_days, "trend_p": tp,
                 "min_evidence": min_evidence, "skip_weight": SKIP_WEIGHT},
    )


def baseline_accuracy(obs: list[Observation]) -> float | None:
    """The plain baseline the Beta model is compared against: share correct, skips count as wrong."""
    return sum(o.correct is True for o in obs) / len(obs) if obs else None


def explain(e: MasteryEstimate) -> str:
    if e.label == "insufficient_evidence":
        return (f"Only {e.unique_questions} different question(s) answered so far; at least "
                f"{e.details.get('min_evidence', 5)} are needed before a mastery label is given.")
    return (f"Estimated mastery {pct100(e.score)}% (likely range {pct100(e.lower)}–{pct100(e.upper)}%) "
            f"from {e.answers} answers on {e.unique_questions} questions: {e.correct} correct, {e.incorrect} wrong, "
            f"{e.skipped} skipped. Recent answers and harder questions count more.")
