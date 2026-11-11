"""Personalised recommendations (version RECO_VERSION). Every recommendation carries its reason.

Kinds: prerequisite, practice_topic (weak, developing or not enough evidence), revisit_incorrect (spaced
revision is due) and, since v2, try_harder: a topic where mastery and recent answers are high enough for the
difficulty policy to step up (the same thresholds as difficulty.next_action), with the lowest priority.
"""
from dataclasses import dataclass, field

from app.ml.difficulty import next_action
from app.ml.mastery import MasteryEstimate, pct100
from app.ml.weak_areas import TopicStatus

RECO_VERSION = "reco-rules-v2"
MAX_RECOMMENDATIONS = 6


@dataclass
class TopicInfo:
    topic_key: str
    subject_label: str
    topic_label: str
    estimate: MasteryEstimate | None
    status: TopicStatus
    next_difficulty: str
    prerequisite_key: str | None = None
    course_topic_id: int | None = None


@dataclass
class Reco:
    kind: str
    topic_key: str
    subject_label: str
    topic_label: str
    reason: str
    priority: float
    payload: dict = field(default_factory=dict)


def build(topics: list[TopicInfo], due_revision: dict[str, int]) -> list[Reco]:
    """topics: every topic the student has evidence on, plus enrolled course topics.
    due_revision: topic_key -> number of spaced-revision questions due now."""
    by_key = {t.topic_key: t for t in topics}
    out: list[Reco] = []
    for t in topics:
        e, st = t.estimate, t.status
        prefill = {"subject": t.subject_label, "topic": t.topic_label, "difficulty": t.next_difficulty,
                   "topic_id": t.course_topic_id}
        if st.status == "weak":
            pre = by_key.get(t.prerequisite_key) if t.prerequisite_key else None
            if pre and pre.status.status in ("weak", "developing", "insufficient_evidence"):
                out.append(Reco("prerequisite", pre.topic_key, pre.subject_label, pre.topic_label,
                                f"Review {pre.topic_label} first: it is a prerequisite of {t.topic_label}, "
                                f"where {st.reason[0].lower() + st.reason[1:]}", st.priority + 0.2,
                                {"subject": pre.subject_label, "topic": pre.topic_label,
                                 "difficulty": pre.next_difficulty, "topic_id": pre.course_topic_id}))
            out.append(Reco("practice_topic", t.topic_key, t.subject_label, t.topic_label,
                            f"Practise {t.topic_label} because {st.reason[0].lower() + st.reason[1:]}",
                            st.priority, prefill))
        elif st.status == "developing":
            out.append(Reco("practice_topic", t.topic_key, t.subject_label, t.topic_label,
                            f"A short {t.next_difficulty} quiz on {t.topic_label} would help: {st.reason[0].lower() + st.reason[1:]}",
                            st.priority, prefill))
        elif st.status == "insufficient_evidence" and e is not None:
            out.append(Reco("practice_topic", t.topic_key, t.subject_label, t.topic_label,
                            f"Try a mixed quiz on {t.topic_label}: {st.reason[0].lower() + st.reason[1:]}",
                            st.priority, prefill))
        elif st.status == "ok" and e is not None and next_action(e)[0] == "try_harder":
            out.append(Reco("try_harder", t.topic_key, t.subject_label, t.topic_label,
                            f"You are doing well on {t.topic_label} (mastery {pct100(e.score)}%, {pct100(e.recent_accuracy)}% "
                            f"of your last {e.recent_n} answers correct), so try a {t.next_difficulty} quiz next.",
                            0.05, prefill))
        due = due_revision.get(t.topic_key, 0)
        if due:
            out.append(Reco("revisit_incorrect", t.topic_key, t.subject_label, t.topic_label,
                            f"{due} question(s) you missed on {t.topic_label} are due for spaced revision.",
                            0.9 + 0.05 * min(due, 5), {"topic_key": t.topic_key, "due": due}))
    seen, uniq = set(), []
    for r in sorted(out, key=lambda r: -r.priority):
        k = (r.kind, r.topic_key)
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return uniq[:MAX_RECOMMENDATIONS]
