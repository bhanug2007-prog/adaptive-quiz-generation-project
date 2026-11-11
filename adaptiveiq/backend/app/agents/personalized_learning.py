"""LangGraph Stage 1 Personalized Learning Agent (read-only study-plan preview).

Builds a typed StateGraph with five nodes and deterministic conditional routing
using AdaptiveIQ's existing Beta-Bernoulli mastery estimates, difficulty policy,
weak-area classification, prerequisite links, feedback-visible revision schedules,
and weekly study hours.

Stage 1 constraints:
- Strictly read-only (zero database writes, zero historical mutations).
- Zero calls to Qwen 7B or Groq (all reasoning is deterministic and policy-driven).
- Reuses existing ML policy modules without introducing a new mastery algorithm.
- Enforces student-only authorization and prevents access to other students' data
  or unreleased lecturer assessment content.
"""
from datetime import timedelta
from functools import lru_cache
from typing import TypedDict
from urllib.parse import urlencode
import uuid

from fastapi import HTTPException
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.ml import difficulty, mastery, recommendations, spaced_revision, weak_areas
from app.models import (
    GenerationRun,
    LearningPlan,
    LearningPlanExecution,
    LearningPlanItem,
    Question,
    Quiz,
    QuizSession,
    Topic,
    User,
)
from app.models.base import utcnow
from app.schemas.quizzes import PracticeGenerateRequest
from app.services import adaptive_service as ad
from app.services import attempt_service as att
from app.services import learning_service as learn
from app.services import permissions as perm
from app.services import practice_service as prac

GRAPH_VERSION = "langgraph-plan-v1"
STAGE2_GRAPH_VERSION = "langgraph-plan-v2"
ALLOWED_ACTION_BY_KIND = {
    "revisit_incorrect": "start_revision",
    "prerequisite": "start_practice",
    "practice_topic": "start_practice",
    "gather_evidence": "start_practice",
    "diagnostic_start": "start_practice",
    "try_harder": "start_practice",
    "maintain": "start_practice",
    "upcoming_assessment": "open_assessment",
}
POLICY_VERSIONS = {
    "mastery": mastery.MASTERY_VERSION,
    "difficulty": difficulty.POLICY_VERSION,
    "weak_areas": weak_areas.WEAK_VERSION,
    "recommendations": recommendations.RECO_VERSION,
    "revision": spaced_revision.REVISION_VERSION,
    "adaptive_pipeline": ad.ALGORITHM_VERSION,
}

DEFAULT_MINUTES_BY_KIND = {
    "revisit_incorrect": 20,
    "prerequisite": 40,
    "practice_topic": 40,
    "gather_evidence": 25,
    "upcoming_assessment": 45,
    "diagnostic_start": 25,
    "try_harder": 30,
    "maintain": 20,
}

KIND_ORDER = {
    "revisit_incorrect": 0,
    "prerequisite": 1,
    "practice_topic": 2,
    "gather_evidence": 3,
    "upcoming_assessment": 4,
    "diagnostic_start": 5,
    "try_harder": 6,
    "maintain": 7,
}


class LearningPlanState(TypedDict, total=False):
    # Inputs
    student_id: int
    weekly_study_hours_override: int | None
    has_hours_override: bool
    max_items: int
    scope_course_id: int | None

    # Stage 2 persistent / HITL state (unused in Stage 1 read-only preview)
    plan_id: int | None
    generation_seq: int
    plan_status: str
    last_decision: dict | None
    last_execution_result: dict | None
    last_action_error: dict | None
    pending_approval_request: dict | None

    # Node 1: Authenticate and load student evidence
    authorized: bool
    auth_error: str | None
    weekly_study_hours: int | None
    weekly_hours_source: str
    enrolled_course_ids: list[int]
    enrolled_courses: list[dict]
    evidence_summary: dict
    topics: list[dict]
    due_revisions: list[dict]
    upcoming_revisions_count: int
    upcoming_quizzes: list[dict]
    has_eligible_material: bool

    # Node 2: Build candidate learning activities
    candidate_activities: list[dict]
    routing_flags: dict
    candidate_route: str

    # Node 3: Validate recommendations and permissions
    validated_activities: list[dict]
    rejected_candidates: list[dict]
    post_validation_route: str

    # Nodes 4 & 5: Plan construction & preview response
    plan_items: list[dict]
    deferred_topics: list[dict]
    proposed_next_actions: list[dict]
    warnings: list[str]
    plan_summary: dict
    scenarios: list[str]
    primary_scenario: str
    plan_preview: dict

    # Execution trace
    node_history: list[str]
    routing_history: list[dict]


def _practice_href(subject: str, topic: str, difficulty_choice: str, topic_id: int | None = None) -> str:
    params: dict[str, str] = {}
    if subject:
        params["subject"] = subject
    if topic:
        params["topic"] = topic
    if topic_id is not None:
        params["topic_id"] = str(topic_id)
    if difficulty_choice:
        params["difficulty"] = difficulty_choice
    query = urlencode(params)
    return f"/student/practice?{query}" if query else "/student/practice"


def _make_action(
    kind: str,
    subject: str,
    topic: str,
    difficulty_choice: str,
    topic_id: int | None = None,
    quiz_id: int | None = None,
    due_count: int = 0,
    quiz_title: str | None = None,
) -> dict:
    if kind == "revisit_incorrect":
        return {
            "label": f"Start spaced revision ({due_count} due)" if due_count else "Open spaced revision",
            "action_type": "navigate_revision",
            "target_href": "/student/insights#revision",
            "prefill": {"topic": topic, "subject": subject, "due": due_count},
            "read_only_preview": True,
            "requires_approval": False,
        }
    if kind == "upcoming_assessment" and quiz_id is not None:
        return {
            "label": f"Open {quiz_title}" if quiz_title else "Open assigned assessment",
            "action_type": "open_quiz",
            "target_href": f"/student/quizzes/{quiz_id}",
            "prefill": {"quiz_id": quiz_id, "topic_id": topic_id},
            "read_only_preview": True,
            "requires_approval": False,
        }
    if kind == "prerequisite":
        label = f"Review {topic} ({difficulty_choice})"
    elif kind in ("gather_evidence", "diagnostic_start"):
        label = f"Gather evidence on {topic} (mixed)"
    elif kind == "try_harder":
        label = f"Challenge {topic} ({difficulty_choice})"
    elif kind == "maintain":
        label = f"Keep {topic} fresh"
    else:
        label = f"Practise {topic} ({difficulty_choice})"
    return {
        "label": label,
        "action_type": "prefill_practice",
        "target_href": _practice_href(subject, topic, difficulty_choice, topic_id),
        "prefill": {
            "subject": subject,
            "topic": topic,
            "topic_id": topic_id,
            "difficulty": difficulty_choice,
        },
        "read_only_preview": True,
        "requires_approval": False,
    }


def _topic_dict_to_info(t: dict, s) -> recommendations.TopicInfo:
    if t["answers"] > 0:
        # Build lightweight MasteryEstimate matching existing status/scores without recomputing from DB
        e = mastery.MasteryEstimate(
            score=float(t["score"] if t["score"] is not None else 0.5),
            lower=float(t["lower"] if t["lower"] is not None else 0.3),
            upper=float(t["upper"] if t["upper"] is not None else 0.7),
            evidence=float(t["answers"]),
            answers=int(t["answers"]),
            unique_questions=int(t["unique_questions"]),
            correct=int(t["correct"]),
            incorrect=int(t["incorrect"]),
            skipped=int(t["skipped"]),
            label=t["label"],
            evidence_level=t["evidence_level"],
            recent_accuracy=t["recent_accuracy"],
            recent_n=int(t["recent_n"]),
            historical_accuracy=t["historical_accuracy"],
            trend=t["trend"],
            details={"min_evidence": s.mastery_min_evidence},
        )
    else:
        e = None
    st = weak_areas.TopicStatus(t["status"], t["status_reason"], float(t["priority"]))
    return recommendations.TopicInfo(
        topic_key=t["topic_key"],
        subject_label=t["subject_label"],
        topic_label=t["topic_label"],
        estimate=e,
        status=st,
        next_difficulty=t["next_difficulty"],
        prerequisite_key=t.get("prerequisite_key"),
        course_topic_id=t.get("topic_id"),
    )


# ---------------- Graph Nodes ----------------

def authenticate_and_load_evidence(state: LearningPlanState, config: RunnableConfig) -> dict:
    """Node 1: Re-verify student authorization and load read-only mastery, prerequisite, revision, and schedule data."""
    cfg = config.get("configurable", {})
    db = cfg["db"]
    s = cfg["settings"]
    now = cfg.get("now") or utcnow()

    ev = learn.load_student_evidence(db, state["student_id"], s, now)
    nodes = [*state.get("node_history", []), "authenticate_and_load_evidence"]
    if not ev.get("authorized"):
        return {
            "authorized": False,
            "auth_error": ev.get("auth_error") or "Student access required.",
            "has_eligible_material": False,
            "node_history": nodes,
            "routing_history": state.get("routing_history", []),
        }

    scope_cid = state.get("scope_course_id")
    if scope_cid is not None and int(scope_cid) not in ev["enrolled_course_ids"]:
        return {
            "authorized": False,
            "auth_error": "Course not found in your active enrollments.",
            "has_eligible_material": False,
            "node_history": nodes,
            "routing_history": state.get("routing_history", []),
        }

    if state.get("has_hours_override"):
        weekly_hours = state.get("weekly_study_hours_override")
        hours_source = "preview_override"
    else:
        weekly_hours = ev["weekly_study_hours"]
        hours_source = "profile" if weekly_hours is not None else "unset"

    return {
        "authorized": True,
        "auth_error": None,
        "weekly_study_hours": weekly_hours,
        "weekly_hours_source": hours_source,
        "enrolled_course_ids": ev["enrolled_course_ids"],
        "enrolled_courses": ev["enrolled_courses"],
        "evidence_summary": ev["evidence_summary"],
        "topics": ev["topics"],
        "due_revisions": ev["due_revisions"],
        "upcoming_revisions_count": ev["upcoming_revisions_count"],
        "upcoming_quizzes": ev["upcoming_quizzes"],
        "has_eligible_material": ev["has_eligible_material"],
        "node_history": nodes,
        "routing_history": state.get("routing_history", []),
    }


def route_after_auth(state: LearningPlanState) -> str:
    return "authorized" if state.get("authorized") else "unauthorized"


def build_candidate_activities(state: LearningPlanState, config: RunnableConfig) -> dict:
    """Node 2: Build candidate learning activities from existing mastery, recommendation, revision, and quiz rules."""
    cfg = config.get("configurable", {})
    s = cfg["settings"]
    nodes = [*state.get("node_history", []), "build_candidate_activities"]
    routes = list(state.get("routing_history", []))
    routes.append({
        "from_node": "authenticate_and_load_evidence",
        "condition": "authorized",
        "to_node": "build_candidate_activities",
        "reason": "Student session and active enrollments verified.",
    })

    if not state.get("has_eligible_material"):
        flags = {
            "has_due_revision": False,
            "has_weak_prerequisite": False,
            "has_sufficient_evidence": False,
            "has_insufficient_evidence": False,
            "has_eligible_material": False,
            "primary_focus": "no_eligible_material",
        }
        return {
            "candidate_activities": [],
            "routing_flags": flags,
            "candidate_route": "no_eligible_material",
            "node_history": nodes,
            "routing_history": routes,
        }

    topics = state.get("topics", [])
    by_key = {t["topic_key"]: t for t in topics}
    due_counts = {r["topic_key"]: int(r["due_count"]) for r in state.get("due_revisions", [])}

    # Include topics that have evidence, due revision, open quizzes, eligible questions,
    # or are prerequisites of attempted/weak topics.
    referenced_prereqs = {
        t["prerequisite_key"]
        for t in topics
        if t.get("prerequisite_key") and (t["answers"] > 0 or t["due_revision_count"] > 0 or t["has_open_quiz"])
    }
    active_topics = [
        t for t in topics
        if (
            t["answers"] > 0
            or t["due_revision_count"] > 0
            or t["eligible_question_count"] > 0
            or t["has_open_quiz"]
            or t["topic_key"] in referenced_prereqs
        )
    ]

    infos = [_topic_dict_to_info(t, s) for t in active_topics]
    recos = recommendations.build(infos, due_counts)

    # Map upcoming due assessments by topic_key
    soon_by_topic: dict[str, dict] = {}
    for z in state.get("upcoming_quizzes", []):
        for k in z["topic_keys"]:
            soon_by_topic.setdefault(k, z)

    # Identify prerequisite -> dependent weak topic relationships (including not_attempted prerequisites)
    prereq_dependents: dict[str, list[dict]] = {}
    for t in active_topics:
        pk = t.get("prerequisite_key")
        if pk and pk in by_key and t["status"] in ("weak", "developing"):
            pre = by_key[pk]
            if pre["status"] in ("weak", "developing", "insufficient_evidence", "not_attempted"):
                # Trigger explicit prerequisite remediation when dependent topic is weak, or prerequisite itself is weak
                if t["status"] == "weak" or pre["status"] == "weak":
                    prereq_dependents.setdefault(pk, []).append(t)

    candidates: list[dict] = []
    seen_ids: set[str] = set()

    def _add(cand: dict):
        aid = cand["activity_id"]
        if aid not in seen_ids:
            seen_ids.add(aid)
            candidates.append(cand)

    for r in recos:
        t = by_key.get(r.topic_key)
        if t is None:
            continue
        kind = r.kind
        if kind == "practice_topic" and t["status"] == "insufficient_evidence":
            kind = "gather_evidence"
        soon = soon_by_topic.get(t["topic_key"])
        prio = float(r.priority)
        reason = r.reason
        if soon and kind in ("practice_topic", "gather_evidence", "prerequisite"):
            prio += 0.35
            reason = f"{reason} '{soon['title']}' is due {soon['due_at'][:10]}."
        elif kind == "gather_evidence":
            left = max(1, t["min_evidence"] - t["unique_questions"])
            reason = f"{reason} Answer at least {left} more different question(s) before locking difficulty."

        diff = r.payload.get("difficulty") or t["next_difficulty"]
        if kind == "revisit_incorrect":
            diff = "mixed"
        elif kind == "gather_evidence":
            diff = "mixed"

        dep_labels = [d["topic_label"] for d in prereq_dependents.get(t["topic_key"], [])] if kind == "prerequisite" else []
        blocked_by = None
        if t.get("prerequisite_key") and t["prerequisite_key"] in prereq_dependents:
            blocked_by = by_key[t["prerequisite_key"]]["topic_label"]

        _add({
            "activity_id": f"{kind}:{t['topic_key']}",
            "kind": kind,
            "topic_key": t["topic_key"],
            "topic": t["topic_label"],
            "subject": t["subject_label"],
            "course_id": t["course_id"],
            "topic_id": t["topic_id"],
            "quiz_id": soon["quiz_id"] if soon and kind == "upcoming_assessment" else None,
            "status": t["status"],
            "mastery_label": t["label"],
            "mastery_score_pct": t["score_pct"],
            "evidence_sufficient": t["evidence_sufficient"],
            "unique_questions": t["unique_questions"],
            "min_evidence": t["min_evidence"],
            "recommended_difficulty": diff,
            "priority": round(prio, 4),
            "reason": reason,
            "due_revision_count": t["due_revision_count"] if kind == "revisit_incorrect" else 0,
            "prerequisite_of": dep_labels,
            "blocked_by_prerequisite": blocked_by,
            "prerequisite_key": t.get("prerequisite_key"),
            "is_own_practice": t.get("is_own_practice", False),
            "next_action": _make_action(
                kind,
                t["subject_label"],
                t["topic_label"],
                diff,
                topic_id=t["topic_id"],
                due_count=t["due_revision_count"],
            ),
        })

    # Add prerequisite candidates missed by reco-rules-v2 (e.g., not_attempted prerequisite of a weak topic,
    # or prerequisite of a developing topic when prerequisite itself is weak)
    for pk, deps in prereq_dependents.items():
        aid = f"prerequisite:{pk}"
        if aid in seen_ids:
            continue
        pre = by_key[pk]
        dep = deps[0]
        diff = pre["next_difficulty"] if pre["answers"] > 0 else "mixed"
        prio = max(float(dep["priority"]), 1.0 if pre["status"] == "weak" else 0.7) + 0.25
        why_pre = (
            f"Review prerequisite {pre['topic_label']} before continuing {dep['topic_label']}: "
            f"{pre['status_reason'][0].lower() + pre['status_reason'][1:]}"
        )
        _add({
            "activity_id": aid,
            "kind": "prerequisite",
            "topic_key": pre["topic_key"],
            "topic": pre["topic_label"],
            "subject": pre["subject_label"],
            "course_id": pre["course_id"],
            "topic_id": pre["topic_id"],
            "quiz_id": None,
            "status": pre["status"],
            "mastery_label": pre["label"],
            "mastery_score_pct": pre["score_pct"],
            "evidence_sufficient": pre["evidence_sufficient"],
            "unique_questions": pre["unique_questions"],
            "min_evidence": pre["min_evidence"],
            "recommended_difficulty": diff,
            "priority": round(prio, 4),
            "reason": why_pre,
            "due_revision_count": 0,
            "prerequisite_of": [d["topic_label"] for d in deps],
            "blocked_by_prerequisite": None,
            "prerequisite_key": pre.get("prerequisite_key"),
            "is_own_practice": pre.get("is_own_practice", False),
            "next_action": _make_action("prerequisite", pre["subject_label"], pre["topic_label"], diff, pre["topic_id"]),
        })

    # Avoid listing the same topic twice as both `prerequisite` and redundant general practice
    prereq_topics = {c["topic_key"]: c for c in candidates if c["kind"] == "prerequisite"}
    if prereq_topics:
        deduped: list[dict] = []
        for c in candidates:
            tk = c["topic_key"]
            if tk in prereq_topics and c["kind"] in ("practice_topic", "gather_evidence", "diagnostic_start"):
                prereq_topics[tk]["priority"] = round(max(float(prereq_topics[tk]["priority"]), float(c["priority"]) + 0.1), 4)
                seen_ids.discard(c["activity_id"])
                continue
            deduped.append(c)
        candidates = deduped

    # Ensure every topic with due revision items is represented even if recommendations.build capped at 6
    for rev in state.get("due_revisions", []):
        tk = rev["topic_key"]
        aid = f"revisit_incorrect:{tk}"
        if aid in seen_ids or tk not in by_key:
            continue
        t = by_key[tk]
        due = int(rev["due_count"])
        _add({
            "activity_id": aid,
            "kind": "revisit_incorrect",
            "topic_key": tk,
            "topic": t["topic_label"],
            "subject": t["subject_label"],
            "course_id": t["course_id"],
            "topic_id": t["topic_id"],
            "quiz_id": None,
            "status": t["status"],
            "mastery_label": t["label"],
            "mastery_score_pct": t["score_pct"],
            "evidence_sufficient": t["evidence_sufficient"],
            "unique_questions": t["unique_questions"],
            "min_evidence": t["min_evidence"],
            "recommended_difficulty": "mixed",
            "priority": round(0.9 + 0.05 * min(due, 5), 4),
            "reason": f"{due} question(s) you missed on {t['topic_label']} are due for spaced revision.",
            "due_revision_count": due,
            "prerequisite_of": [],
            "blocked_by_prerequisite": None,
            "prerequisite_key": t.get("prerequisite_key"),
            "is_own_practice": t.get("is_own_practice", False),
            "next_action": _make_action("revisit_incorrect", t["subject_label"], t["topic_label"], "mixed", t["topic_id"], due_count=due),
        })

    # Add upcoming assigned assessments due within 7 days
    covered_keys = {c["topic_key"] for c in candidates}
    for z in state.get("upcoming_quizzes", []):
        first_tk = z["topic_keys"][0] if z["topic_keys"] else None
        t = by_key.get(first_tk) if first_tk else None
        if t is None:
            continue
        # Add dedicated upcoming_assessment activity if the assessment itself hasn't been started/covered
        aid = f"upcoming_assessment:{z['quiz_id']}:{t['topic_key']}"
        if t["topic_key"] not in covered_keys or z["state"] == "in_progress":
            due_iso = z["due_at"][:10]
            _add({
                "activity_id": aid,
                "kind": "upcoming_assessment",
                "topic_key": t["topic_key"],
                "topic": t["topic_label"],
                "subject": t["subject_label"],
                "course_id": t["course_id"],
                "topic_id": t["topic_id"],
                "quiz_id": z["quiz_id"],
                "status": "upcoming_assessment",
                "mastery_label": t["label"],
                "mastery_score_pct": t["score_pct"],
                "evidence_sufficient": t["evidence_sufficient"],
                "unique_questions": t["unique_questions"],
                "min_evidence": t["min_evidence"],
                "recommended_difficulty": "mixed",
                "priority": 1.15 if z["state"] == "in_progress" else 0.95,
                "reason": (
                    f"Resume assigned assessment '{z['title']}' (due {due_iso})."
                    if z["state"] == "in_progress"
                    else f"Assigned assessment '{z['title']}' is open and due {due_iso}."
                ),
                "due_revision_count": 0,
                "prerequisite_of": [],
                "blocked_by_prerequisite": None,
                "prerequisite_key": t.get("prerequisite_key"),
                "is_own_practice": False,
                "next_action": _make_action(
                    "upcoming_assessment",
                    t["subject_label"],
                    t["topic_label"],
                    "mixed",
                    topic_id=t["topic_id"],
                    quiz_id=z["quiz_id"],
                    quiz_title=z["title"],
                ),
            })

    # Add unattempted diagnostic starter items if student has eligible questions/open quiz on unattempted topics
    for t in active_topics:
        if t["status"] == "not_attempted" and (t["eligible_question_count"] > 0 or t["has_open_quiz"]):
            if any(c["topic_key"] == t["topic_key"] for c in candidates):
                continue
            _add({
                "activity_id": f"diagnostic_start:{t['topic_key']}",
                "kind": "diagnostic_start",
                "topic_key": t["topic_key"],
                "topic": t["topic_label"],
                "subject": t["subject_label"],
                "course_id": t["course_id"],
                "topic_id": t["topic_id"],
                "quiz_id": None,
                "status": "not_attempted",
                "mastery_label": "not_attempted",
                "mastery_score_pct": None,
                "evidence_sufficient": False,
                "unique_questions": 0,
                "min_evidence": t["min_evidence"],
                "recommended_difficulty": "mixed",
                "priority": 0.4,
                "reason": (
                    f"Eligible questions are ready on {t['topic_label']}, with no attempts yet; "
                    f"start a mixed quiz to gather at least {t['min_evidence']} questions of evidence."
                ),
                "due_revision_count": 0,
                "prerequisite_of": [],
                "blocked_by_prerequisite": None,
                "prerequisite_key": t.get("prerequisite_key"),
                "is_own_practice": t.get("is_own_practice", False),
                "next_action": _make_action("diagnostic_start", t["subject_label"], t["topic_label"], "mixed", t["topic_id"]),
            })

    # Strong / Proficient steady-state fallback so strong learners get maintenance guidance
    if not candidates:
        ok_topics = [t for t in active_topics if t["status"] == "ok"]
        for t in ok_topics[:3]:
            _add({
                "activity_id": f"maintain:{t['topic_key']}",
                "kind": "maintain",
                "topic_key": t["topic_key"],
                "topic": t["topic_label"],
                "subject": t["subject_label"],
                "course_id": t["course_id"],
                "topic_id": t["topic_id"],
                "quiz_id": None,
                "status": t["status"],
                "mastery_label": t["label"],
                "mastery_score_pct": t["score_pct"],
                "evidence_sufficient": t["evidence_sufficient"],
                "unique_questions": t["unique_questions"],
                "min_evidence": t["min_evidence"],
                "recommended_difficulty": t["next_difficulty"],
                "priority": 0.15,
                "reason": (
                    f"{t['topic_label']} is currently on track ({t['score_pct']}% mastery over "
                    f"{t['unique_questions']} questions); {t['next_action_text'][0].lower() + t['next_action_text'][1:]}"
                ),
                "due_revision_count": 0,
                "prerequisite_of": [],
                "blocked_by_prerequisite": None,
                "prerequisite_key": t.get("prerequisite_key"),
                "is_own_practice": t.get("is_own_practice", False),
                "next_action": _make_action("maintain", t["subject_label"], t["topic_label"], t["next_difficulty"], t["topic_id"]),
            })

    has_due = any(c["kind"] == "revisit_incorrect" for c in candidates)
    has_prereq = any(c["kind"] == "prerequisite" for c in candidates)
    has_suff = any(t["evidence_sufficient"] for t in active_topics)
    has_insuff = any(t["status"] == "insufficient_evidence" for t in active_topics)

    if has_due or has_prereq or any(c["status"] in ("weak", "developing") for c in candidates):
        primary_focus = "remediation"
    elif any(c["kind"] in ("gather_evidence", "diagnostic_start", "upcoming_assessment") for c in candidates):
        primary_focus = "gather_evidence"
    elif candidates:
        primary_focus = "challenge_and_maintain"
    else:
        primary_focus = "no_eligible_material"

    flags = {
        "has_due_revision": has_due,
        "has_weak_prerequisite": has_prereq,
        "has_sufficient_evidence": has_suff,
        "has_insufficient_evidence": has_insuff,
        "has_eligible_material": bool(candidates),
        "primary_focus": primary_focus,
    }
    return {
        "candidate_activities": candidates,
        "routing_flags": flags,
        "candidate_route": "has_candidates" if candidates else "no_eligible_material",
        "node_history": nodes,
        "routing_history": routes,
    }


def route_after_candidates(state: LearningPlanState) -> str:
    return state.get("candidate_route") or ("has_candidates" if state.get("candidate_activities") else "no_eligible_material")


def validate_recommendations_and_permissions(state: LearningPlanState, config: RunnableConfig) -> dict:
    """Node 3: Enforce student-only ownership, course enrollment, released-feedback, and policy consistency."""
    cfg = config.get("configurable", {})
    db = cfg["db"]
    now = cfg.get("now") or utcnow()

    user = db.get(User, state["student_id"])
    nodes = [*state.get("node_history", []), "validate_recommendations_and_permissions"]
    routes = list(state.get("routing_history", []))
    routes.append({
        "from_node": "build_candidate_activities",
        "condition": "has_candidates",
        "to_node": "validate_recommendations_and_permissions",
        "reason": f"Validating {len(state.get('candidate_activities', []))} candidate activity item(s) against permissions and policies.",
    })

    if user is None or not user.is_active or user.role != "student":
        return {
            "validated_activities": [],
            "rejected_candidates": [{"activity_id": "*", "reason": "unauthorized_user"}],
            "post_validation_route": "empty_after_validation",
            "node_history": nodes,
            "routing_history": routes,
        }

    enrolled_ids = set(perm.enrolled_course_ids(db, user))
    assigned_qids = set(perm.assigned_quiz_ids(db, user))
    due_by_tk = {r["topic_key"]: int(r["due_count"]) for r in state.get("due_revisions", [])}
    own_practice_keys = {t["topic_key"] for t in state.get("topics", []) if t.get("is_own_practice")}

    validated: list[dict] = []
    rejected: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()

    for cand in state.get("candidate_activities", []):
        tk = cand["topic_key"]
        kind = cand["kind"]
        pair = (kind, tk)
        if pair in seen_pairs:
            rejected.append({"activity_id": cand["activity_id"], "reason": "duplicate_candidate"})
            continue

        # 1. Course topic enrollment & active course scope
        scope_cid = state.get("scope_course_id")
        if scope_cid is not None and cand.get("course_id") != int(scope_cid):
            rejected.append({"activity_id": cand["activity_id"], "reason": "outside_selected_course_scope"})
            continue
        if tk.startswith("t:"):
            tid = cand.get("topic_id")
            topic_obj = db.get(Topic, tid) if tid is not None else None
            if (
                topic_obj is None
                or topic_obj.unit.subject.course.archived
                or topic_obj.unit.subject.course_id not in enrolled_ids
            ):
                rejected.append({"activity_id": cand["activity_id"], "reason": "not_enrolled_in_course"})
                continue

        # 2. Personal practice topic ownership scope
        if tk.startswith("p:") and tk not in own_practice_keys:
            rejected.append({"activity_id": cand["activity_id"], "reason": "practice_topic_not_owned"})
            continue

        # 3. Assigned assessment visibility & approval scope
        if kind == "upcoming_assessment":
            qid = cand.get("quiz_id")
            z = db.get(Quiz, qid) if qid is not None else None
            if (
                z is None
                or z.kind != "assessment"
                or z.status != "published"
                or z.id not in assigned_qids
                or not z.items
                or any(i.question.review_status != "approved" or (i.question.validation or {}).get("quarantined") for i in z.items)
                or att.quiz_state(z, att.sessions_for(db, z.id, user.id), now) not in ("open", "in_progress", "late_open")
            ):
                rejected.append({"activity_id": cand["activity_id"], "reason": "assessment_unavailable_or_unreleased"})
                continue

        # 4. Due spaced revision visibility scope
        if kind == "revisit_incorrect" and due_by_tk.get(tk, 0) <= 0:
            rejected.append({"activity_id": cand["activity_id"], "reason": "no_visible_due_revision"})
            continue

        # 5. Policy coherence checks
        if kind == "try_harder" and (cand["status"] != "ok" or not cand["evidence_sufficient"]):
            rejected.append({"activity_id": cand["activity_id"], "reason": "try_harder_without_sufficient_ok_mastery"})
            continue

        seen_pairs.add(pair)
        validated.append(cand)

    if not validated:
        post_route = "empty_after_validation"
    elif any(c["kind"] in ("revisit_incorrect", "prerequisite", "practice_topic") for c in validated):
        post_route = "prioritize_remediation"
    elif any(c["kind"] in ("gather_evidence", "diagnostic_start", "upcoming_assessment") for c in validated):
        post_route = "gather_evidence"
    else:
        post_route = "challenge_and_maintain"

    return {
        "validated_activities": validated,
        "rejected_candidates": rejected,
        "post_validation_route": post_route,
        "node_history": nodes,
        "routing_history": routes,
    }


def route_after_validation(state: LearningPlanState) -> str:
    return state.get("post_validation_route") or "empty_after_validation"


def _order_with_prerequisites(items: list[dict]) -> list[dict]:
    """Sorts by priority while guaranteeing prerequisite activities precede weak dependent topics."""
    ordered = sorted(
        items,
        key=lambda c: (-float(c["priority"]), KIND_ORDER.get(c["kind"], 9), c["topic"]),
    )
    # Enforce prerequisite-before-dependent invariant deterministically
    changed = True
    guard = 0
    while changed and guard < len(ordered) * 2:
        changed = False
        guard += 1
        prereq_pos = {
            c["topic_key"]: idx
            for idx, c in enumerate(ordered)
            if c["kind"] == "prerequisite"
        }
        for idx, c in enumerate(ordered):
            pk = c.get("prerequisite_key")
            if pk and pk in prereq_pos and prereq_pos[pk] > idx:
                p_idx = prereq_pos[pk]
                prereq_item = ordered.pop(p_idx)
                ordered.insert(idx, prereq_item)
                changed = True
                break
    return ordered


def _allocate_minutes(items: list[dict], total_minutes: int) -> list[int]:
    """Splits total weekly minutes across selected items cleanly in 5-minute steps."""
    if not items or total_minutes <= 0:
        return [0 for _ in items]
    weights = []
    for c in items:
        w = max(0.5, float(c["priority"]) + 0.5)
        if c["kind"] == "revisit_incorrect":
            w += 0.25
        weights.append(w)
    total_w = sum(weights) or 1.0
    # Work in 5-minute units so allocations remain clean integers summing to total_minutes
    step = 5
    units_total = max(len(items), total_minutes // step)
    raw = [units_total * w / total_w for w in weights]
    units = [max(1, int(r)) for r in raw]
    # Reconcile sum of units with exact budget (total_minutes // 5)
    target_units = total_minutes // step
    while sum(units) > target_units and any(u > 1 for u in units):
        idx = max((i for i in range(len(units)) if units[i] > 1), key=lambda i: units[i] - raw[i])
        units[idx] -= 1
    remainders = sorted(range(len(units)), key=lambda i: -(raw[i] - units[i]))
    k = 0
    while sum(units) < target_units:
        units[remainders[k % len(units)]] += 1
        k += 1
    return [u * step for u in units]


def construct_personalized_plan(state: LearningPlanState, config: RunnableConfig) -> dict:
    """Node 4: Order activities, apply prerequisites & weekly study budget, and prepare proposed next actions."""
    nodes = [*state.get("node_history", []), "construct_personalized_plan"]
    routes = list(state.get("routing_history", []))
    from_node = nodes[-2] if len(nodes) >= 2 else "build_candidate_activities"
    cond = state.get("post_validation_route") if from_node == "validate_recommendations_and_permissions" else state.get("candidate_route", "no_eligible_material")
    routes.append({
        "from_node": from_node,
        "condition": str(cond),
        "to_node": "construct_personalized_plan",
        "reason": (
            "No eligible questions or released material found; constructing empty guidance preview."
            if cond == "no_eligible_material"
            else f"Constructing ordered study plan under '{cond}' strategy."
        ),
    })

    weekly_hours = state.get("weekly_study_hours")
    hours_source = state.get("weekly_hours_source", "unset")
    max_items = int(state.get("max_items") or 6)
    ev_summary = state.get("evidence_summary", {})
    validated = [] if from_node == "build_candidate_activities" else list(state.get("validated_activities", []))

    if not validated:
        empty_reason = (
            "You are not enrolled in an active course and have no practice quiz history yet. "
            "Join a course with your lecturer's join code or open Practice Lab to upload study material."
            if ev_summary.get("enrolled_courses_count", 0) == 0
            else "No eligible approved quizzes, released revision items, or practice questions are available yet. "
                 "Wait for your lecturer to publish an assessment, or practise a course topic / upload notes in Practice Lab."
        )
        actions = [
            {
                "label": "Join or view courses",
                "action_type": "open_courses",
                "target_href": "/student/courses",
                "prefill": None,
                "read_only_preview": True,
                "requires_approval": False,
            },
            {
                "label": "Open Practice Lab",
                "action_type": "practice_lab",
                "target_href": "/student/practice",
                "prefill": None,
                "read_only_preview": True,
                "requires_approval": False,
            },
        ]
        summary = {
            "headline": "No eligible questions or study material yet.",
            "rationale": empty_reason,
            "weekly_study_hours": weekly_hours,
            "weekly_hours_source": hours_source,
            "budget_status": "empty",
            "allocated_minutes": 0,
            "allocated_hours": 0.0,
            "due_revision_total": ev_summary.get("due_revision_total", 0),
            "upcoming_revision_total": ev_summary.get("upcoming_revision_total", 0),
            "insufficient_evidence_topics": 0,
            "weak_prerequisite_topics": 0,
            "sufficient_evidence_topics": 0,
            "empty_reason": empty_reason,
        }
        return {
            "plan_items": [],
            "deferred_topics": [],
            "proposed_next_actions": actions,
            "warnings": [],
            "plan_summary": summary,
            "scenarios": ["no_eligible_material"],
            "primary_scenario": "no_eligible_material",
            "node_history": nodes,
            "routing_history": routes,
        }

    ordered = _order_with_prerequisites(validated)
    deferred: list[dict] = []

    if weekly_hours is not None and weekly_hours == 0:
        cap = min(max_items, 4)
        selected, overflow = ordered[:cap], ordered[cap:]
        minutes_list = [0 for _ in selected]
        budget_status = "zero_hours"
    elif weekly_hours is not None and weekly_hours > 0:
        total_min = int(weekly_hours) * 60
        cap = min(max_items, max(1, total_min // 20))
        selected, overflow = ordered[:cap], ordered[cap:]
        minutes_list = _allocate_minutes(selected, total_min)
        budget_status = "allocated"
    else:
        selected, overflow = ordered[:max_items], ordered[max_items:]
        minutes_list = []
        for c in selected:
            if c["kind"] == "revisit_incorrect":
                mins = min(30, max(10, 3 * max(1, c["due_revision_count"])))
                mins = int(((mins + 4) // 5) * 5)
            else:
                mins = DEFAULT_MINUTES_BY_KIND.get(c["kind"], 30)
            minutes_list.append(mins)
        budget_status = "unconfigured"

    for c in overflow:
        deferred.append({
            "topic_key": c["topic_key"],
            "topic": c["topic"],
            "subject": c["subject"],
            "kind": c["kind"],
            "reason": (
                f"Deferred so top-priority activities fit within your {weekly_hours} h/week schedule."
                if budget_status == "allocated"
                else "Deferred below the top 6 recommended study sessions."
            ),
        })

    plan_items: list[dict] = []
    for idx, (c, mins) in enumerate(zip(selected, minutes_list), start=1):
        hrs = round(mins / 60, 2) if (weekly_hours is not None or mins > 0) else None
        plan_items.append({
            "rank": idx,
            "activity_id": c["activity_id"],
            "kind": c["kind"],
            "topic_key": c["topic_key"],
            "topic": c["topic"],
            "subject": c["subject"],
            "course_id": c["course_id"],
            "topic_id": c["topic_id"],
            "quiz_id": c["quiz_id"],
            "status": c["status"],
            "mastery_label": c["mastery_label"],
            "mastery_score_pct": c["mastery_score_pct"],
            "evidence_sufficient": c["evidence_sufficient"],
            "unique_questions": c["unique_questions"],
            "min_evidence": c["min_evidence"],
            "recommended_difficulty": c["recommended_difficulty"],
            "priority": c["priority"],
            "estimated_minutes": mins,
            "estimated_hours": hrs,
            "reason": c["reason"],
            "due_revision_count": c["due_revision_count"],
            "prerequisite_of": c["prerequisite_of"],
            "blocked_by_prerequisite": c["blocked_by_prerequisite"],
            "next_action": c["next_action"],
        })

    scenarios: list[str] = []
    if any(t["evidence_sufficient"] for t in state.get("topics", [])):
        scenarios.append("sufficient_evidence")
    if any(t["status"] == "insufficient_evidence" for t in state.get("topics", [])) or any(c["kind"] in ("gather_evidence", "diagnostic_start") for c in plan_items):
        scenarios.append("insufficient_evidence")
    if any(c["kind"] == "prerequisite" for c in plan_items):
        scenarios.append("weak_prerequisite")
    if any(c["kind"] == "revisit_incorrect" for c in plan_items):
        scenarios.append("due_revision")
    if budget_status == "allocated":
        scenarios.append("weekly_budget_applied")
    elif budget_status == "zero_hours":
        scenarios.append("weekly_budget_zero")
    else:
        scenarios.append("weekly_budget_unset")

    # Pick clearest primary scenario tag
    if "weak_prerequisite" in scenarios:
        primary_scenario = "weak_prerequisite"
    elif "due_revision" in scenarios:
        primary_scenario = "due_revision"
    elif "insufficient_evidence" in scenarios and "sufficient_evidence" not in scenarios:
        primary_scenario = "insufficient_evidence"
    elif "sufficient_evidence" in scenarios:
        primary_scenario = "sufficient_evidence"
    else:
        primary_scenario = scenarios[0]

    warnings: list[str] = []
    min_ev = ev_summary.get("min_evidence_threshold", 5)
    insuff_topics = [
        t for t in state.get("topics", [])
        if t["status"] == "insufficient_evidence" and t["answers"] > 0
    ]
    if insuff_topics:
        sample = ", ".join(t["topic_label"] for t in insuff_topics[:3])
        warnings.append(
            f"Fewer than {min_ev} distinct questions answered on {sample}; estimates are tentative until more evidence is gathered."
        )
    if budget_status == "zero_hours":
        warnings.append(
            "Your weekly study hours are set to 0 in Profile, so 0 minutes were scheduled. Update Profile when ready to allocate time."
        )
    elif budget_status == "unconfigured":
        warnings.append(
            "Add your weekly study hours in Profile to tailor these suggested durations to your available week."
        )
    if deferred:
        warnings.append(f"{len(deferred)} lower-priority topic(s) were deferred to keep this plan realistic.")

    # Proposed global next actions (top distinct item actions + Profile if hours unset/0)
    proposed_actions: list[dict] = []
    seen_hrefs: set[str] = set()
    for item in plan_items[:4]:
        act = item["next_action"]
        if act["target_href"] not in seen_hrefs:
            seen_hrefs.add(act["target_href"])
            proposed_actions.append(act)
    if budget_status in ("unconfigured", "zero_hours"):
        proposed_actions.append({
            "label": "Update weekly study hours in Profile",
            "action_type": "open_profile",
            "target_href": "/student/profile",
            "prefill": None,
            "read_only_preview": True,
            "requires_approval": False,
        })

    allocated_min = sum(i["estimated_minutes"] for i in plan_items)
    allocated_hrs = round(allocated_min / 60, 2)
    first = plan_items[0]
    if first["kind"] == "prerequisite" and first.get("prerequisite_of"):
        headline = f"Start with prerequisite '{first['topic']}' before revisiting '{first['prerequisite_of'][0]}'."
    elif first["kind"] == "prerequisite":
        headline = f"Start with prerequisite '{first['topic']}' before dependent topics."
    elif first["kind"] == "revisit_incorrect":
        headline = f"Clear {ev_summary.get('due_revision_total', first['due_revision_count'])} due revision question(s) starting with '{first['topic']}'."
    elif first["kind"] in ("gather_evidence", "diagnostic_start"):
        headline = f"Build mastery evidence on '{first['topic']}' with a short mixed quiz."
    else:
        headline = f"Focus first on '{first['topic']}' ({first['recommended_difficulty']} level)."

    rationale_parts = [
        f"Built deterministically across {len(plan_items)} prioritized session(s)",
        (
            f"fitted to {weekly_hours} h/week ({allocated_min} min total)."
            if budget_status == "allocated"
            else "with 0 scheduled minutes (0 h/week configured)."
            if budget_status == "zero_hours"
            else f"totalling ~{allocated_hrs} h of suggested study time."
        ),
    ]
    if ev_summary.get("due_revision_total", 0) > 0:
        rationale_parts.append(f"Includes {ev_summary['due_revision_total']} due Leitner revision question(s).")
    if ev_summary.get("upcoming_revision_total", 0) > 0 and ev_summary.get("due_revision_total", 0) == 0:
        rationale_parts.append(f"{ev_summary['upcoming_revision_total']} spaced-revision item(s) are scheduled for later.")

    summary = {
        "headline": headline,
        "rationale": " ".join(rationale_parts),
        "weekly_study_hours": weekly_hours,
        "weekly_hours_source": hours_source,
        "budget_status": budget_status,
        "allocated_minutes": allocated_min,
        "allocated_hours": allocated_hrs,
        "due_revision_total": ev_summary.get("due_revision_total", 0),
        "upcoming_revision_total": ev_summary.get("upcoming_revision_total", 0),
        "insufficient_evidence_topics": len(insuff_topics),
        "weak_prerequisite_topics": sum(1 for c in plan_items if c["kind"] == "prerequisite"),
        "sufficient_evidence_topics": ev_summary.get("sufficient_evidence_topics", 0),
        "empty_reason": None,
    }
    return {
        "plan_items": plan_items,
        "deferred_topics": deferred,
        "proposed_next_actions": proposed_actions,
        "warnings": warnings,
        "plan_summary": summary,
        "scenarios": scenarios,
        "primary_scenario": primary_scenario,
        "node_history": nodes,
        "routing_history": routes,
    }


def return_plan_preview(state: LearningPlanState, config: RunnableConfig) -> dict:
    """Node 5: Finalize the immutable Stage 1 plan preview response and execution trace."""
    cfg = config.get("configurable", {})
    now = cfg.get("now") or utcnow()
    nodes = [*state.get("node_history", []), "return_plan_preview"]
    routes = list(state.get("routing_history", []))
    prev_node = nodes[-2] if len(nodes) >= 2 else "authenticate_and_load_evidence"

    if not state.get("authorized"):
        routes.append({
            "from_node": prev_node,
            "condition": "unauthorized",
            "to_node": "return_plan_preview",
            "reason": state.get("auth_error") or "Student authorization check failed.",
        })
        routing_mode = "unauthorized"
        summary = {
            "headline": "Student authorization required.",
            "rationale": state.get("auth_error") or "Only active student accounts may generate a study-plan preview.",
            "weekly_study_hours": None,
            "weekly_hours_source": "unset",
            "budget_status": "empty",
            "allocated_minutes": 0,
            "allocated_hours": 0.0,
            "due_revision_total": 0,
            "upcoming_revision_total": 0,
            "insufficient_evidence_topics": 0,
            "weak_prerequisite_topics": 0,
            "sufficient_evidence_topics": 0,
            "empty_reason": state.get("auth_error") or "Student access required.",
        }
        preview = {
            "agent": "personalized_learning",
            "stage": 1,
            "mode": "deterministic_preview",
            "llm_used": False,
            "read_only": True,
            "graph_version": GRAPH_VERSION,
            "policy_versions": POLICY_VERSIONS,
            "generated_at": now.isoformat(),
            "scenario": "unauthorized",
            "scenarios": ["unauthorized"],
            "routing_mode": routing_mode,
            "summary": summary,
            "items": [],
            "deferred_topics": [],
            "proposed_next_actions": [],
            "warnings": [],
            "graph_trace": {"nodes_visited": nodes, "edges_taken": routes},
        }
        return {"plan_preview": preview, "node_history": nodes, "routing_history": routes}

    if prev_node == "validate_recommendations_and_permissions":
        routes.append({
            "from_node": prev_node,
            "condition": "empty_after_validation",
            "to_node": "return_plan_preview",
            "reason": "All candidate activities were filtered out by permission or policy checks.",
        })
        routing_mode = "empty_after_validation"
        summary = {
            "headline": "No eligible study activities passed permission checks.",
            "rationale": "Candidate activities were excluded because they referenced inaccessible or unreleased content.",
            "weekly_study_hours": state.get("weekly_study_hours"),
            "weekly_hours_source": state.get("weekly_hours_source", "unset"),
            "budget_status": "empty",
            "allocated_minutes": 0,
            "allocated_hours": 0.0,
            "due_revision_total": 0,
            "upcoming_revision_total": state.get("upcoming_revisions_count", 0),
            "insufficient_evidence_topics": 0,
            "weak_prerequisite_topics": 0,
            "sufficient_evidence_topics": 0,
            "empty_reason": "No permitted questions or study material are currently available.",
        }
        preview = {
            "agent": "personalized_learning",
            "stage": 1,
            "mode": "deterministic_preview",
            "llm_used": False,
            "read_only": True,
            "graph_version": GRAPH_VERSION,
            "policy_versions": POLICY_VERSIONS,
            "generated_at": now.isoformat(),
            "scenario": "no_eligible_material",
            "scenarios": ["no_eligible_material"],
            "routing_mode": routing_mode,
            "summary": summary,
            "items": [],
            "deferred_topics": [],
            "proposed_next_actions": [
                {
                    "label": "Join or view courses",
                    "action_type": "open_courses",
                    "target_href": "/student/courses",
                    "prefill": None,
                    "read_only_preview": True,
                    "requires_approval": False,
                },
                {
                    "label": "Open Practice Lab",
                    "action_type": "practice_lab",
                    "target_href": "/student/practice",
                    "prefill": None,
                    "read_only_preview": True,
                    "requires_approval": False,
                },
            ],
            "warnings": [],
            "graph_trace": {"nodes_visited": nodes, "edges_taken": routes},
        }
        return {"plan_preview": preview, "node_history": nodes, "routing_history": routes}

    routes.append({
        "from_node": "construct_personalized_plan",
        "condition": "plan_ready",
        "to_node": "return_plan_preview",
        "reason": "Study-plan preview assembled without modifying persistent records.",
    })
    routing_mode = state.get("post_validation_route") or state.get("candidate_route") or "no_eligible_material"
    preview = {
        "agent": "personalized_learning",
        "stage": 1,
        "mode": "deterministic_preview",
        "llm_used": False,
        "read_only": True,
        "graph_version": GRAPH_VERSION,
        "policy_versions": POLICY_VERSIONS,
        "generated_at": now.isoformat(),
        "scenario": state.get("primary_scenario", "no_eligible_material"),
        "scenarios": state.get("scenarios", ["no_eligible_material"]),
        "routing_mode": routing_mode,
        "summary": state["plan_summary"],
        "items": state.get("plan_items", []),
        "deferred_topics": state.get("deferred_topics", []),
        "proposed_next_actions": state.get("proposed_next_actions", []),
        "warnings": state.get("warnings", []),
        "graph_trace": {"nodes_visited": nodes, "edges_taken": routes},
    }
    return {"plan_preview": preview, "node_history": nodes, "routing_history": routes}


@lru_cache(maxsize=1)
def compile_learning_plan_graph():
    """Builds and compiles the Stage 1 LangGraph StateGraph once cleanly."""
    builder = StateGraph(LearningPlanState)

    builder.add_node("authenticate_and_load_evidence", authenticate_and_load_evidence)
    builder.add_node("build_candidate_activities", build_candidate_activities)
    builder.add_node("validate_recommendations_and_permissions", validate_recommendations_and_permissions)
    builder.add_node("construct_personalized_plan", construct_personalized_plan)
    builder.add_node("return_plan_preview", return_plan_preview)

    builder.add_edge(START, "authenticate_and_load_evidence")
    builder.add_conditional_edges(
        "authenticate_and_load_evidence",
        route_after_auth,
        {
            "authorized": "build_candidate_activities",
            "unauthorized": "return_plan_preview",
        },
    )
    builder.add_conditional_edges(
        "build_candidate_activities",
        route_after_candidates,
        {
            "has_candidates": "validate_recommendations_and_permissions",
            "no_eligible_material": "construct_personalized_plan",
        },
    )
    builder.add_conditional_edges(
        "validate_recommendations_and_permissions",
        route_after_validation,
        {
            "prioritize_remediation": "construct_personalized_plan",
            "gather_evidence": "construct_personalized_plan",
            "challenge_and_maintain": "construct_personalized_plan",
            "empty_after_validation": "return_plan_preview",
        },
    )
    builder.add_edge("construct_personalized_plan", "return_plan_preview")
    builder.add_edge("return_plan_preview", END)

    return builder.compile()


# ---------------- Stage 2: Persistent HITL Workflow ----------------

def _stage2_action_for_item(item: dict) -> dict:
    """Builds Stage 2 server-controlled action metadata (never auto-executed)."""
    kind = item["kind"]
    action_type = ALLOWED_ACTION_BY_KIND.get(kind)
    base = dict(item.get("next_action") or {})
    if action_type == "start_revision":
        due = int(item.get("due_revision_count") or 0)
        return {
            "label": f"Start Due Revision ({due} due)" if due else "Start Due Revision",
            "action_type": "start_revision",
            "target_href": "/student/insights#revision",
            "prefill": {"topic_key": item["topic_key"], "topic": item["topic"], "due": due},
            "read_only_preview": False,
            "requires_approval": True,
        }
    if action_type == "open_assessment":
        return {
            "label": base.get("label") or "Open Assigned Assessment",
            "action_type": "open_assessment",
            "target_href": base.get("target_href") or f"/student/quizzes/{item.get('quiz_id')}",
            "prefill": {"quiz_id": item.get("quiz_id"), "topic_id": item.get("topic_id")},
            "read_only_preview": False,
            "requires_approval": True,
        }
    diff = item.get("recommended_difficulty") or "mixed"
    return {
        "label": f"Start Recommended Practice ({diff})",
        "action_type": "start_practice",
        "target_href": _practice_href(item["subject"], item["topic"], diff, item.get("topic_id")),
        "prefill": {
            "subject": item["subject"],
            "topic": item["topic"],
            "topic_id": item.get("topic_id"),
            "difficulty": diff,
        },
        "read_only_preview": False,
        "requires_approval": True,
    }


def _recompute_plan_status_from_db(db, plan: LearningPlan) -> str:
    """Computes overall persistent plan status from active-epoch items (never overwrites dismissed/expired)."""
    if plan.status in ("dismissed", "expired"):
        return plan.status
    active_items = [i for i in plan.items if i.revision_epoch == plan.generation_seq]
    if not active_items:
        return "proposed"
    statuses = [i.status for i in active_items]
    if all(s == "dismissed" for s in statuses):
        return "dismissed"
    if all(s in ("completed", "dismissed") for s in statuses):
        return "completed" if any(s == "completed" for s in statuses) else "dismissed"
    if any(s in ("in_progress", "approved", "completed") for s in statuses):
        return "in_progress"
    return "awaiting_approval"


def prepare_persistent_plan(state: LearningPlanState, config: RunnableConfig) -> dict:
    """Stage 2 Node 5: Prepares server-validated HITL recommendations before awaiting student approval."""
    nodes = [*state.get("node_history", []), "prepare_persistent_plan"]
    routes = list(state.get("routing_history", []))
    prev_node = nodes[-2] if len(nodes) >= 2 else "authenticate_and_load_evidence"

    if not state.get("authorized"):
        routes.append({
            "from_node": prev_node,
            "condition": "unauthorized",
            "to_node": "prepare_persistent_plan",
            "reason": state.get("auth_error") or "Student authorization check failed.",
        })
        return {
            "plan_status": "failed",
            "pending_approval_request": None,
            "node_history": nodes,
            "routing_history": routes,
        }

    if prev_node == "validate_recommendations_and_permissions":
        routes.append({
            "from_node": prev_node,
            "condition": "empty_after_validation",
            "to_node": "prepare_persistent_plan",
            "reason": "All candidate activities were filtered out by permission or policy checks.",
        })
        plan_items: list[dict] = []
        summary = {
            "headline": "No eligible study activities passed permission checks.",
            "rationale": "Candidate activities were excluded because they referenced inaccessible or unreleased content.",
            "weekly_study_hours": state.get("weekly_study_hours"),
            "weekly_hours_source": state.get("weekly_hours_source", "unset"),
            "budget_status": "empty",
            "allocated_minutes": 0,
            "allocated_hours": 0.0,
            "due_revision_total": 0,
            "upcoming_revision_total": state.get("upcoming_revisions_count", 0),
            "insufficient_evidence_topics": 0,
            "weak_prerequisite_topics": 0,
            "sufficient_evidence_topics": 0,
            "empty_reason": "No permitted questions or study material are currently available.",
        }
        actions = [
            {
                "label": "Join or view courses",
                "action_type": "open_courses",
                "target_href": "/student/courses",
                "prefill": None,
                "read_only_preview": True,
                "requires_approval": False,
            },
            {
                "label": "Open Practice Lab",
                "action_type": "practice_lab",
                "target_href": "/student/practice",
                "prefill": None,
                "read_only_preview": True,
                "requires_approval": False,
            },
        ]
        routing_mode = "empty_after_validation"
        scenarios = ["no_eligible_material"]
        primary_scenario = "no_eligible_material"
    else:
        routes.append({
            "from_node": prev_node,
            "condition": "plan_ready",
            "to_node": "prepare_persistent_plan",
            "reason": "Prepared persistent learning plan; pausing for explicit student approval.",
        })
        plan_items = [
            {**item, "next_action": _stage2_action_for_item(item)}
            for item in state.get("plan_items", [])
        ]
        summary = state["plan_summary"]
        actions = list(state.get("proposed_next_actions", []))
        routing_mode = state.get("post_validation_route") or state.get("candidate_route") or "no_eligible_material"
        scenarios = state.get("scenarios", ["no_eligible_material"])
        primary_scenario = state.get("primary_scenario", "no_eligible_material")

    plan_status = "awaiting_approval" if plan_items else "proposed"
    pending_req = {
        "plan_id": state.get("plan_id"),
        "student_id": state["student_id"],
        "generation_seq": int(state.get("generation_seq") or 1),
        "actionable_activity_ids": [i["activity_id"] for i in plan_items],
        "default_activity_id": plan_items[0]["activity_id"] if plan_items else None,
        "prompt": (
            f"Waiting for your approval before starting {plan_items[0]['topic']} or another recommended step."
            if plan_items
            else "No eligible activities yet. Refresh your plan after joining a course or taking a quiz."
        ),
    }

    return {
        "plan_items": plan_items,
        "plan_summary": summary,
        "proposed_next_actions": actions,
        "post_validation_route": routing_mode,
        "scenarios": scenarios,
        "primary_scenario": primary_scenario,
        "plan_status": plan_status,
        "last_action_error": None,
        "pending_approval_request": pending_req,
        "node_history": nodes,
        "routing_history": routes,
    }


def route_after_prepare(state: LearningPlanState) -> str:
    return "await_approval" if state.get("authorized") else "finalize"


def await_student_approval(state: LearningPlanState, config: RunnableConfig) -> dict:
    """Stage 2 Node 6: Pauses via LangGraph interrupt() until explicit student resume command."""
    cfg = config.get("configurable", {})
    expected_sid = cfg.get("expected_student_id")
    if expected_sid is not None and int(expected_sid) != int(state["student_id"]):
        raise HTTPException(404, "Learning plan not found.")

    payload = state.get("pending_approval_request") or {
        "plan_id": state.get("plan_id"),
        "student_id": state["student_id"],
        "generation_seq": int(state.get("generation_seq") or 1),
        "actionable_activity_ids": [i["activity_id"] for i in state.get("plan_items", [])],
        "default_activity_id": state["plan_items"][0]["activity_id"] if state.get("plan_items") else None,
        "prompt": "Approve an activity to execute, dismiss or postpone it, or refresh recommendations.",
    }
    decision = interrupt(payload)
    if not isinstance(decision, dict):
        decision = {"decision_type": "close"}

    dtype = str(decision.get("decision_type") or "").strip().lower()
    nodes = [*state.get("node_history", []), "await_student_approval"]
    routes = list(state.get("routing_history", []))
    routes.append({
        "from_node": "await_student_approval",
        "condition": dtype or "unknown",
        "to_node": (
            "revalidate_and_execute_action"
            if dtype == "approve"
            else "record_student_decision"
            if dtype in ("dismiss", "postpone")
            else "authenticate_and_load_evidence"
            if dtype == "refresh"
            else "finalize_plan"
        ),
        "reason": f"Student resumed workflow with '{dtype or 'close'}' decision.",
    })

    out: dict = {
        "last_decision": decision,
        "last_action_error": None,
        "node_history": nodes[-40:],
        "routing_history": routes[-40:],
    }
    if dtype == "refresh":
        out["generation_seq"] = int(state.get("generation_seq") or 1) + 1
        out["has_hours_override"] = bool(decision.get("has_hours_override"))
        out["weekly_study_hours_override"] = decision.get("weekly_hours")
        out["last_execution_result"] = None
        out["last_action_error"] = None
        out["plan_status"] = "proposed"
        out["candidate_activities"] = []
        out["validated_activities"] = []
        out["rejected_candidates"] = []
        out["plan_items"] = []
        out["deferred_topics"] = []
        out["proposed_next_actions"] = []
        out["warnings"] = []
        out["plan_summary"] = {}
        out["scenarios"] = []
        out["primary_scenario"] = ""
        out["post_validation_route"] = ""
        out["candidate_route"] = ""
        out["pending_approval_request"] = None
    return out


def route_after_approval(state: LearningPlanState) -> str:
    if not state.get("authorized"):
        return "finalize"
    dtype = str((state.get("last_decision") or {}).get("decision_type") or "").lower()
    if dtype == "approve":
        return "execute_action"
    if dtype in ("dismiss", "postpone"):
        return "record_decision"
    if dtype == "refresh":
        return "refresh"
    return "finalize"


def _resolve_plan_item_for_action(db, plan: LearningPlan, requested_activity_id: str | None) -> LearningPlanItem:
    active_items = [i for i in plan.items if i.revision_epoch == plan.generation_seq]
    if not active_items:
        raise HTTPException(409, "This learning plan has no active recommendations. Refresh the plan first.")

    if requested_activity_id:
        for item in active_items:
            if item.activity_id == requested_activity_id:
                return item
        if any(i.activity_id == requested_activity_id and i.revision_epoch < plan.generation_seq for i in plan.items):
            raise HTTPException(409, "That recommendation was superseded when the plan refreshed.")
        raise HTTPException(404, "Activity not found in this learning plan.")

    if plan.selected_activity_id:
        for item in active_items:
            if item.activity_id == plan.selected_activity_id and item.status in ("pending", "postponed", "in_progress"):
                return item

    for item in active_items:
        if item.status in ("pending", "postponed"):
            return item
    raise HTTPException(409, "No pending activities remain to approve in this plan.")


def _active_execution_reuse(db, item: LearningPlanItem, exec_row: LearningPlanExecution, now, *, model_service=None) -> dict | None:
    """Returns serialized execution result when an already committed activity is still active (prevents duplicates)."""
    if exec_row.action_type == "start_practice" and exec_row.status == "handoff" and item.status == "in_progress":
        if model_service is not None:
            try:
                mstate, _ = model_service.health()
                if mstate == "ok":
                    return None
            except Exception:
                pass
        return {
            "action_type": "start_practice",
            "execution_status": "handoff",
            "activity_id": item.activity_id,
            "quiz_id": None,
            "session_id": None,
            "generation_run_id": None,
            "destination_href": exec_row.destination_href,
            "reused_existing": True,
            "message": (exec_row.result_payload or {}).get("message") or f"Practice Lab handoff for {item.topic_label} is already active.",
            "executed_at": (exec_row.finished_at or exec_row.created_at or now).isoformat(),
        }
    if exec_row.action_type == "start_practice" and exec_row.generation_run_id:
        run = db.get(GenerationRun, exec_row.generation_run_id)
        if run is None:
            return None
        submitted = False
        if exec_row.quiz_id:
            submitted = (
                db.scalar(
                    select(QuizSession.id).where(
                        QuizSession.quiz_id == exec_row.quiz_id,
                        QuizSession.student_id == exec_row.student_id,
                        QuizSession.status == "submitted",
                    ).limit(1)
                )
                is not None
            )
        if not submitted and (run.status in ("queued", "running") or (run.status == "done" and run.ready > 0)):
            return {
                "action_type": "start_practice",
                "execution_status": "reused_existing",
                "activity_id": item.activity_id,
                "quiz_id": exec_row.quiz_id,
                "session_id": exec_row.session_id,
                "generation_run_id": exec_row.generation_run_id,
                "destination_href": exec_row.destination_href,
                "reused_existing": True,
                "message": f"Practice quiz generation for {item.topic_label} is already active.",
                "executed_at": (exec_row.finished_at or exec_row.created_at or now).isoformat(),
            }
    elif exec_row.action_type == "start_revision" and exec_row.session_id:
        sess = db.get(QuizSession, exec_row.session_id)
        if sess is not None and sess.status == "in_progress":
            return {
                "action_type": "start_revision",
                "execution_status": "reused_existing",
                "activity_id": item.activity_id,
                "quiz_id": exec_row.quiz_id,
                "session_id": exec_row.session_id,
                "generation_run_id": None,
                "destination_href": exec_row.destination_href,
                "reused_existing": True,
                "message": f"Your active spaced revision session for {item.topic_label} is ready.",
                "executed_at": (exec_row.finished_at or exec_row.created_at or now).isoformat(),
            }
    elif exec_row.action_type == "open_assessment" and exec_row.status == "handoff" and item.status == "in_progress":
        return {
            "action_type": "open_assessment",
            "execution_status": "handoff",
            "activity_id": item.activity_id,
            "quiz_id": exec_row.quiz_id,
            "session_id": None,
            "generation_run_id": None,
            "destination_href": exec_row.destination_href,
            "reused_existing": True,
            "message": f"Assessment '{item.topic_label}' handoff is already active.",
            "executed_at": (exec_row.finished_at or exec_row.created_at or now).isoformat(),
        }
    return None


def revalidate_and_execute_action(state: LearningPlanState, config: RunnableConfig) -> dict:
    """Stage 2 Node 7A: Server-side permission/eligibility revalidation & idempotent action execution."""
    cfg = config.get("configurable", {})
    db = cfg["db"]
    s = cfg["settings"]
    now = cfg.get("now") or utcnow()
    expected_sid = cfg.get("expected_student_id")
    model_service = cfg.get("model_service")
    generation_service = cfg.get("generation_service")
    document_store = cfg.get("document_store")

    decision = state.get("last_decision") or {}
    nodes = [*state.get("node_history", []), "revalidate_and_execute_action"]
    routes = list(state.get("routing_history", []))

    user = db.get(User, state["student_id"])
    if (
        user is None
        or not user.is_active
        or user.role != "student"
        or (expected_sid is not None and int(expected_sid) != user.id)
    ):
        db.rollback()
        raise HTTPException(403, "This page is for students.")

    plan = db.get(LearningPlan, state["plan_id"])
    if plan is None or plan.student_id != user.id:
        db.rollback()
        raise HTTPException(404, "Learning plan not found.")

    plan_id = plan.id
    exec_box: list[int] = []
    try:
        return _revalidate_and_execute_impl(
            db=db,
            s=s,
            user=user,
            plan=plan,
            decision=decision,
            now=now,
            model_service=model_service,
            generation_service=generation_service,
            document_store=document_store,
            nodes=nodes,
            routes=routes,
            exec_box=exec_box,
        )
    except HTTPException as exc:
        db.rollback()
        if exec_box:
            stale = db.get(LearningPlanExecution, exec_box[0])
            if stale is not None and stale.status == "executing":
                stale.status = "failed"
                stale.error = (getattr(exc, "detail", None) or str(exc) or type(exc).__name__)[:380]
                stale.finished_at = now
                db.commit()
        refreshed_plan = db.get(LearningPlan, plan_id)
        return {
            "last_execution_result": None,
            "last_action_error": {"status_code": exc.status_code, "detail": exc.detail},
            "plan_status": (
                _recompute_plan_status_from_db(db, refreshed_plan)
                if refreshed_plan is not None
                else (state.get("plan_status") or "awaiting_approval")
            ),
            "node_history": nodes[-40:],
            "routing_history": routes[-40:],
        }


def _revalidate_and_execute_impl(
    *,
    db,
    s,
    user: User,
    plan: LearningPlan,
    decision: dict,
    now,
    model_service,
    generation_service,
    document_store,
    nodes: list[str],
    routes: list[dict],
    exec_box: list[int],
) -> dict:
    if plan.status in ("dismissed", "expired"):
        db.rollback()
        raise HTTPException(409, f"Cannot execute actions on a {plan.status} plan.")

    item = _resolve_plan_item_for_action(db, plan, decision.get("activity_id"))
    if item.status == "completed":
        db.rollback()
        raise HTTPException(409, "This activity has already been completed.")
    if item.status == "dismissed":
        db.rollback()
        raise HTTPException(409, "This dismissed recommendation cannot be started unless the plan is refreshed.")
    if item.status == "superseded":
        db.rollback()
        raise HTTPException(409, "This recommendation was replaced when the plan refreshed.")

    action_type = ALLOWED_ACTION_BY_KIND.get(item.kind)
    if action_type is None:
        db.rollback()
        raise HTTPException(400, f"Unsupported action for learning plan item '{item.kind}'.")

    idem_key = (decision.get("idempotency_key") or "").strip()

    # 1. Exact idempotency key lookup (also recovers from crashes after DB commit before checkpoint save)
    if idem_key:
        existing_idem = db.scalar(
            select(LearningPlanExecution).where(
                LearningPlanExecution.plan_id == plan.id,
                LearningPlanExecution.activity_id == item.activity_id,
                LearningPlanExecution.idempotency_key == idem_key,
            )
        )
        if existing_idem and existing_idem.status in ("executed", "handoff"):
            cached = dict(existing_idem.result_payload or {})
            res_payload = {
                "action_type": existing_idem.action_type,
                "execution_status": "reused_existing",
                "activity_id": item.activity_id,
                "quiz_id": existing_idem.quiz_id,
                "session_id": existing_idem.session_id,
                "generation_run_id": existing_idem.generation_run_id,
                "destination_href": existing_idem.destination_href,
                "reused_existing": True,
                "message": cached.get("message") or "Returned previously executed action without duplicating work.",
                "executed_at": (existing_idem.finished_at or existing_idem.created_at or now).isoformat(),
            }
            if item.status in ("pending", "approved", "postponed"):
                item.status = "in_progress"
                item.approval_status = "handoff" if existing_idem.status == "handoff" else "executed"
                item.execution_ref = res_payload
                plan.selected_activity_id = item.activity_id
                plan.action_approval_status = item.approval_status
                plan.last_execution_ref = res_payload
                plan.status = _recompute_plan_status_from_db(db, plan)
                db.commit()
            return {
                "last_execution_result": res_payload,
                "last_action_error": None,
                "plan_status": plan.status,
                "node_history": nodes[-40:],
                "routing_history": routes[-40:],
            }

    # 2. Active-execution & post-crash reconciliation on this item even without idempotency_key
    prior_execs = list(
        db.scalars(
            select(LearningPlanExecution)
            .where(
                LearningPlanExecution.plan_id == plan.id,
                LearningPlanExecution.item_id == item.id,
                LearningPlanExecution.action_type == action_type,
                LearningPlanExecution.status.in_(("executed", "handoff")),
            )
            .order_by(LearningPlanExecution.id.desc())
        )
    )
    for prev_exec in prior_execs:
        reused = _active_execution_reuse(db, item, prev_exec, now, model_service=model_service)
        if reused is not None:
            # Ensure item/plan reflect executed state even if previous run crashed before saving checkpoint/item update
            item.status = "in_progress"
            item.approval_status = "handoff" if prev_exec.status == "handoff" else "executed"
            item.execution_ref = reused
            plan.selected_activity_id = item.activity_id
            plan.action_approval_status = item.approval_status
            plan.last_execution_ref = reused
            plan.status = _recompute_plan_status_from_db(db, plan)
            db.commit()
            return {
                "last_execution_result": reused,
                "last_action_error": None,
                "plan_status": plan.status,
                "node_history": nodes[-40:],
                "routing_history": routes[-40:],
            }

    # 3. Record intent ledger row first
    ledger_key = idem_key or uuid.uuid4().hex
    exec_row = LearningPlanExecution(
        plan_id=plan.id,
        item_id=item.id,
        student_id=user.id,
        activity_id=item.activity_id,
        action_type=action_type,
        idempotency_key=ledger_key,
        status="executing",
    )
    db.add(exec_row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing_race = db.scalar(
            select(LearningPlanExecution).where(
                LearningPlanExecution.plan_id == plan.id,
                LearningPlanExecution.activity_id == item.activity_id,
                LearningPlanExecution.idempotency_key == ledger_key,
            )
        )
        if existing_race and existing_race.status in ("executed", "handoff"):
            res_payload = {
                "action_type": existing_race.action_type,
                "execution_status": "reused_existing",
                "activity_id": item.activity_id,
                "quiz_id": existing_race.quiz_id,
                "session_id": existing_race.session_id,
                "generation_run_id": existing_race.generation_run_id,
                "destination_href": existing_race.destination_href,
                "reused_existing": True,
                "message": "Concurrent approval resolved idempotently.",
                "executed_at": (existing_race.finished_at or existing_race.created_at or now).isoformat(),
            }
            return {
                "last_execution_result": res_payload,
                "last_action_error": None,
                "plan_status": _recompute_plan_status_from_db(db, plan),
                "node_history": nodes[-40:],
                "routing_history": routes[-40:],
            }
        raise HTTPException(409, "Action execution is already in progress.") from None
    exec_box.append(exec_row.id)

    result_payload: dict
    try:
        if action_type == "start_revision":
            rev = learn.start_spaced_revision(
                db,
                user,
                s,
                topic_key=item.topic_key,
                reuse_active=True,
                now=now,
            )
            dest = f"/student/attempts/{rev['session_id']}"
            exec_status = "reused_existing" if rev.get("reused_existing") else "started"
            msg = (
                f"Opened your active spaced revision session for {item.topic_label}."
                if rev.get("reused_existing")
                else f"Started spaced revision quiz for {item.topic_label} ({rev['question_count']} due question(s))."
            )
            result_payload = {
                "action_type": "start_revision",
                "execution_status": exec_status,
                "activity_id": item.activity_id,
                "quiz_id": rev["quiz_id"],
                "session_id": rev["session_id"],
                "generation_run_id": None,
                "destination_href": dest,
                "reused_existing": bool(rev.get("reused_existing")),
                "message": msg,
                "executed_at": now.isoformat(),
            }
            # Re-fetch persistent rows in case start_spaced_revision committed inside start_attempt
            exec_row = db.get(LearningPlanExecution, exec_row.id)
            item = db.get(LearningPlanItem, item.id)
            plan = db.get(LearningPlan, plan.id)
            exec_row.status = "executed"
            exec_row.quiz_id = rev["quiz_id"]
            exec_row.session_id = rev["session_id"]
            exec_row.destination_href = dest
            exec_row.result_payload = result_payload
            exec_row.finished_at = now

            item.status = "in_progress"
            item.approval_status = "executed"
            item.approved_at = item.approved_at or now
            item.execution_ref = result_payload

            plan.selected_activity_id = item.activity_id
            plan.action_approval_status = "executed"
            plan.last_execution_ref = result_payload
            plan.status = _recompute_plan_status_from_db(db, plan)
            db.commit()

        elif action_type == "start_practice":
            if item.topic_key.startswith("t:"):
                tid = item.topic_id
                t = db.get(Topic, tid) if tid is not None else None
                enrolled = set(perm.enrolled_course_ids(db, user))
                if t is None or f"t:{t.id}" != item.topic_key or t.unit.subject.course.archived or t.unit.subject.course_id not in enrolled:
                    raise HTTPException(404, "Topic is no longer available in your active courses.")
                subj_val, top_val, unit_val, verified_tid = t.unit.subject.name, t.name, t.unit.name, t.id
            elif item.topic_key.startswith("p:"):
                owns_p = (
                    db.scalar(
                        select(Question.id).where(
                            Question.owner_id == user.id,
                            Question.topic_key == item.topic_key,
                            Question.review_status == "personal",
                        ).limit(1)
                    )
                    is not None
                    or db.scalar(
                        select(QuizSession.id)
                        .join(Quiz, Quiz.id == QuizSession.quiz_id)
                        .where(QuizSession.student_id == user.id, Quiz.owner_id == user.id)
                        .limit(1)
                    )
                    is not None
                )
                if not owns_p:
                    raise HTTPException(403, "Personal practice topic does not belong to your account.")
                subj_val, top_val, unit_val, verified_tid = item.subject_label, item.topic_label, None, None
            else:
                raise HTTPException(400, "Invalid topic scope for practice generation.")

            diff = item.recommended_difficulty if item.recommended_difficulty in ("easy", "medium", "hard", "mixed") else "mixed"
            req_body = PracticeGenerateRequest(
                source_mode="topic",
                subject=subj_val,
                topic=top_val,
                topic_id=verified_tid,
                unit=unit_val,
                question_count=5,
                difficulty=diff,
                confidence_enabled=True,
            )

            def _bind_before_commit(quiz: Quiz, run: GenerationRun) -> None:
                dest_url = prac.validated_practice_href(subj_val, top_val, diff, topic_id=verified_tid, run_id=run.id)
                payload = {
                    "action_type": "start_practice",
                    "execution_status": "started",
                    "activity_id": item.activity_id,
                    "quiz_id": quiz.id,
                    "session_id": None,
                    "generation_run_id": run.id,
                    "destination_href": dest_url,
                    "reused_existing": False,
                    "message": f"Started {diff} practice quiz generation for {top_val}.",
                    "executed_at": now.isoformat(),
                }
                exec_row.status = "executed"
                exec_row.quiz_id = quiz.id
                exec_row.generation_run_id = run.id
                exec_row.destination_href = dest_url
                exec_row.result_payload = payload
                exec_row.finished_at = now

                item.status = "in_progress"
                item.approval_status = "executed"
                item.approved_at = item.approved_at or now
                item.execution_ref = payload

                plan.selected_activity_id = item.activity_id
                plan.action_approval_status = "executed"
                plan.last_execution_ref = payload
                plan.status = _recompute_plan_status_from_db(db, plan)

            started = prac.start_practice_generation(
                db,
                user,
                s,
                req_body,
                model_service=model_service,
                generation_service=generation_service,
                document_store=document_store,
                enforce_unarchived_course=True,
                allow_offline_handoff=True,
                on_before_commit=_bind_before_commit,
            )
            if started["handoff"]:
                dest_url = started["destination_href"]
                result_payload = {
                    "action_type": "start_practice",
                    "execution_status": "handoff",
                    "activity_id": item.activity_id,
                    "quiz_id": None,
                    "session_id": None,
                    "generation_run_id": None,
                    "destination_href": dest_url,
                    "reused_existing": False,
                    "message": started["message"],
                    "executed_at": now.isoformat(),
                }
                exec_row.status = "handoff"
                exec_row.destination_href = dest_url
                exec_row.result_payload = result_payload
                exec_row.finished_at = now

                item.status = "in_progress"
                item.approval_status = "handoff"
                item.approved_at = item.approved_at or now
                item.execution_ref = result_payload

                plan.selected_activity_id = item.activity_id
                plan.action_approval_status = "handoff"
                plan.last_execution_ref = result_payload
                plan.status = _recompute_plan_status_from_db(db, plan)
                db.commit()
            else:
                result_payload = dict(exec_row.result_payload)

        elif action_type == "open_assessment":
            if item.quiz_id is None:
                raise HTTPException(409, "No assigned assessment is linked to this recommendation.")
            z = perm.student_quiz(db, user, item.quiz_id)
            if (
                z.kind != "assessment"
                or z.status != "published"
                or not z.items
                or any(i.question.review_status != "approved" or (i.question.validation or {}).get("quarantined") for i in z.items)
            ):
                raise HTTPException(409, "This assessment is no longer available.")
            if att.quiz_state(z, att.sessions_for(db, z.id, user.id), now) not in ("open", "in_progress", "late_open"):
                raise HTTPException(409, "This assessment window is closed or already submitted.")

            dest = f"/student/quizzes/{z.id}"
            result_payload = {
                "action_type": "open_assessment",
                "execution_status": "handoff",
                "activity_id": item.activity_id,
                "quiz_id": z.id,
                "session_id": None,
                "generation_run_id": None,
                "destination_href": dest,
                "reused_existing": False,
                "message": f"Validated assessment '{z.title}'. Review any instructions or monitoring notice before starting.",
                "executed_at": now.isoformat(),
            }
            exec_row.status = "handoff"
            exec_row.quiz_id = z.id
            exec_row.destination_href = dest
            exec_row.result_payload = result_payload
            exec_row.finished_at = now

            item.status = "in_progress"
            item.approval_status = "handoff"
            item.approved_at = item.approved_at or now
            item.execution_ref = result_payload

            plan.selected_activity_id = item.activity_id
            plan.action_approval_status = "handoff"
            plan.last_execution_ref = result_payload
            plan.status = _recompute_plan_status_from_db(db, plan)
            db.commit()
    except Exception as exc:
        db.rollback()
        if exec_box:
            stale = db.get(LearningPlanExecution, exec_box[0])
            if stale is not None and stale.status == "executing":
                stale.status = "failed"
                stale.error = (getattr(exc, "detail", None) or str(exc) or type(exc).__name__)[:380]
                stale.finished_at = now
                db.commit()
        raise

    return {
        "last_execution_result": result_payload,
        "last_action_error": None,
        "plan_status": plan.status,
        "node_history": nodes[-40:],
        "routing_history": routes[-40:],
    }


def record_student_decision(state: LearningPlanState, config: RunnableConfig) -> dict:
    """Stage 2 Node 7B: Records explicit dismiss or postpone decision without altering mastery or quiz marks."""
    cfg = config.get("configurable", {})
    db = cfg["db"]
    now = cfg.get("now") or utcnow()
    expected_sid = cfg.get("expected_student_id")
    decision = state.get("last_decision") or {}
    nodes = [*state.get("node_history", []), "record_student_decision"]
    routes = list(state.get("routing_history", []))

    user = db.get(User, state["student_id"])
    if (
        user is None
        or not user.is_active
        or user.role != "student"
        or (expected_sid is not None and int(expected_sid) != user.id)
    ):
        db.rollback()
        raise HTTPException(403, "This page is for students.")

    plan = db.get(LearningPlan, state["plan_id"])
    if plan is None or plan.student_id != user.id:
        db.rollback()
        raise HTTPException(404, "Learning plan not found.")

    plan_id = plan.id
    dtype = str(decision.get("decision_type") or "").lower()
    scope = str(decision.get("scope") or "item").lower()
    note = decision.get("note")

    try:
        if dtype == "dismiss" and scope == "plan":
            active_items = [i for i in plan.items if i.revision_epoch == plan.generation_seq]
            for it in active_items:
                if it.status in ("pending", "postponed", "in_progress"):
                    it.status = "dismissed"
                    it.approval_status = "dismissed"
                    it.decision_note = note
            plan.status = "dismissed"
            plan.action_approval_status = "dismissed"
            result_payload = {
                "action_type": "dismiss",
                "execution_status": "recorded",
                "activity_id": None,
                "quiz_id": None,
                "session_id": None,
                "generation_run_id": None,
                "destination_href": None,
                "reused_existing": False,
                "message": "Learning plan dismissed.",
                "executed_at": now.isoformat(),
            }
            plan.last_execution_ref = result_payload
            db.commit()
            return {
                "last_execution_result": result_payload,
                "last_action_error": None,
                "plan_status": plan.status,
                "node_history": nodes[-40:],
                "routing_history": routes[-40:],
            }

        item = _resolve_plan_item_for_action(db, plan, decision.get("activity_id"))
        if item.status == "completed":
            raise HTTPException(409, "Completed activities cannot be dismissed or postponed.")
        if item.status == "superseded":
            raise HTTPException(409, "Superseded recommendations cannot be modified.")

        if dtype == "dismiss":
            if item.status != "dismissed":
                item.status = "dismissed"
                item.approval_status = "dismissed"
                item.decision_note = note
                exec_rec = LearningPlanExecution(
                    plan_id=plan.id,
                    item_id=item.id,
                    student_id=user.id,
                    activity_id=item.activity_id,
                    action_type="dismiss",
                    idempotency_key=uuid.uuid4().hex,
                    status="recorded",
                    result_payload={"note": note},
                    finished_at=now,
                )
                db.add(exec_rec)
            msg = f"Dismissed recommendation '{item.topic_label}'."
        elif dtype == "postpone":
            days = max(1, min(30, int(decision.get("postpone_days") or 2)))
            until = now + timedelta(days=days)
            item.status = "postponed"
            item.approval_status = "postponed"
            item.postponed_until = until
            item.decision_note = note
            exec_rec = LearningPlanExecution(
                plan_id=plan.id,
                item_id=item.id,
                student_id=user.id,
                activity_id=item.activity_id,
                action_type="postpone",
                idempotency_key=uuid.uuid4().hex,
                status="recorded",
                result_payload={"postpone_days": days, "postponed_until": until.isoformat(), "note": note},
                finished_at=now,
            )
            db.add(exec_rec)
            msg = f"Postponed '{item.topic_label}' for {days} day(s)."
        else:
            raise HTTPException(400, "Unsupported decision type.")

        result_payload = {
            "action_type": dtype,
            "execution_status": "recorded",
            "activity_id": item.activity_id,
            "quiz_id": None,
            "session_id": None,
            "generation_run_id": None,
            "destination_href": None,
            "reused_existing": False,
            "message": msg,
            "executed_at": now.isoformat(),
        }
        plan.selected_activity_id = item.activity_id
        plan.action_approval_status = dtype if dtype in ("dismiss", "postpone") else f"{dtype}d"
        if dtype == "dismiss":
            plan.action_approval_status = "dismissed"
        elif dtype == "postpone":
            plan.action_approval_status = "postponed"
        plan.last_execution_ref = result_payload
        plan.status = _recompute_plan_status_from_db(db, plan)
        db.commit()
    except HTTPException as exc:
        db.rollback()
        refreshed_plan = db.get(LearningPlan, plan_id)
        return {
            "last_execution_result": None,
            "last_action_error": {"status_code": exc.status_code, "detail": exc.detail},
            "plan_status": (
                _recompute_plan_status_from_db(db, refreshed_plan)
                if refreshed_plan is not None
                else (state.get("plan_status") or "awaiting_approval")
            ),
            "node_history": nodes[-40:],
            "routing_history": routes[-40:],
        }
    except Exception:
        db.rollback()
        raise

    return {
        "last_execution_result": result_payload,
        "last_action_error": None,
        "plan_status": plan.status,
        "node_history": nodes[-40:],
        "routing_history": routes[-40:],
    }


def route_after_action(state: LearningPlanState) -> str:
    if state.get("last_action_error"):
        return "finalize" if state.get("plan_status") in ("completed", "dismissed", "expired", "failed") else "await_more"
    if state.get("plan_status") in ("completed", "dismissed", "expired", "failed"):
        return "finalize"
    return "await_more"


def finalize_plan(state: LearningPlanState, config: RunnableConfig) -> dict:
    """Stage 2 terminal node reached when the plan is dismissed, completed, expired, or unauthorized."""
    nodes = [*state.get("node_history", []), "finalize_plan"]
    routes = list(state.get("routing_history", []))
    prev = nodes[-2] if len(nodes) >= 2 else "await_student_approval"
    routes.append({
        "from_node": prev,
        "condition": state.get("plan_status") or "finalize",
        "to_node": "finalize_plan",
        "reason": f"Workflow ended with status '{state.get('plan_status', 'completed')}'.",
    })
    return {
        "node_history": nodes[-40:],
        "routing_history": routes[-40:],
    }


def compile_persistent_learning_plan_graph(checkpointer):
    """Compiles the Stage 2 persistent, interrupt/resume HITL LangGraph StateGraph with checkpointer."""
    builder = StateGraph(LearningPlanState)

    builder.add_node("authenticate_and_load_evidence", authenticate_and_load_evidence)
    builder.add_node("build_candidate_activities", build_candidate_activities)
    builder.add_node("validate_recommendations_and_permissions", validate_recommendations_and_permissions)
    builder.add_node("construct_personalized_plan", construct_personalized_plan)
    builder.add_node("prepare_persistent_plan", prepare_persistent_plan)
    builder.add_node("await_student_approval", await_student_approval)
    builder.add_node("revalidate_and_execute_action", revalidate_and_execute_action)
    builder.add_node("record_student_decision", record_student_decision)
    builder.add_node("finalize_plan", finalize_plan)

    builder.add_edge(START, "authenticate_and_load_evidence")
    builder.add_conditional_edges(
        "authenticate_and_load_evidence",
        route_after_auth,
        {
            "authorized": "build_candidate_activities",
            "unauthorized": "prepare_persistent_plan",
        },
    )
    builder.add_conditional_edges(
        "build_candidate_activities",
        route_after_candidates,
        {
            "has_candidates": "validate_recommendations_and_permissions",
            "no_eligible_material": "construct_personalized_plan",
        },
    )
    builder.add_conditional_edges(
        "validate_recommendations_and_permissions",
        route_after_validation,
        {
            "prioritize_remediation": "construct_personalized_plan",
            "gather_evidence": "construct_personalized_plan",
            "challenge_and_maintain": "construct_personalized_plan",
            "empty_after_validation": "prepare_persistent_plan",
        },
    )
    builder.add_edge("construct_personalized_plan", "prepare_persistent_plan")
    builder.add_conditional_edges(
        "prepare_persistent_plan",
        route_after_prepare,
        {
            "await_approval": "await_student_approval",
            "finalize": "finalize_plan",
        },
    )
    builder.add_conditional_edges(
        "await_student_approval",
        route_after_approval,
        {
            "execute_action": "revalidate_and_execute_action",
            "record_decision": "record_student_decision",
            "refresh": "authenticate_and_load_evidence",
            "finalize": "finalize_plan",
        },
    )
    builder.add_conditional_edges(
        "revalidate_and_execute_action",
        route_after_action,
        {
            "await_more": "await_student_approval",
            "finalize": "finalize_plan",
        },
    )
    builder.add_conditional_edges(
        "record_student_decision",
        route_after_action,
        {
            "await_more": "await_student_approval",
            "finalize": "finalize_plan",
        },
    )
    builder.add_edge("finalize_plan", END)

    return builder.compile(checkpointer=checkpointer)

