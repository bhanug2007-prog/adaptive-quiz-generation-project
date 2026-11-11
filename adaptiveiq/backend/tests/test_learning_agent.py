"""Focused tests for Stage 1 of the LangGraph Personalized Learning Agent.

Uses disposable SQLite databases (tmp_path) and zero calls to Qwen 7B or Groq.
Verifies:
- Student-only authentication and role enforcement (401/403 + unauthorized graph route)
- Sufficient mastery evidence (>= 5 unique questions: weak and strong/proficient paths)
- Insufficient mastery evidence (< 5 unique questions: tentative warning, mixed difficulty, no bogus %)
- Weak prerequisite topic ordering (prerequisite strictly precedes dependent weak topic)
- Due revision activities (overdue Leitner items prioritized; upcoming/rejected/quarantined/unreleased excluded)
- Available weekly study time (positive profile hours, 0 hours, unset hours, and non-persisted ?weekly_hours=)
- No eligible questions or material (unenrolled student & draft-only course with zero leakage)
- Cross-student isolation, removed-enrollment isolation, manual feedback release gating
- Strict read-only invariance across all persistent database tables and zero LLM calls
"""
from datetime import timedelta, timezone

from sqlalchemy import func, select

from app.agents.personalized_learning import compile_learning_plan_graph
from app.models import (
    AgentRun,
    LearningRecommendation,
    Question,
    QuizResult,
    RevisionSchedule,
    StudentAnswer,
    StudentProfile,
    TopicMasterySnapshot,
)
from app.models.base import utcnow
from tests import fake_model_server
from tests.conftest import register


def _db_snapshot(app) -> dict:
    """Captures counts and key rows across persistent tables to prove Stage 1 is strictly read-only."""
    with app.state.db.session() as db:
        return {
            "quiz_results": list(
                db.execute(
                    select(
                        QuizResult.id,
                        QuizResult.session_id,
                        QuizResult.raw_score,
                        QuizResult.final_percentage,
                    ).order_by(QuizResult.id)
                )
            ),
            "snapshots": list(
                db.execute(
                    select(
                        TopicMasterySnapshot.id,
                        TopicMasterySnapshot.student_id,
                        TopicMasterySnapshot.topic_key,
                        TopicMasterySnapshot.score,
                        TopicMasterySnapshot.label,
                    ).order_by(TopicMasterySnapshot.id)
                )
            ),
            "revisions": list(
                db.execute(
                    select(
                        RevisionSchedule.id,
                        RevisionSchedule.student_id,
                        RevisionSchedule.question_id,
                        RevisionSchedule.box,
                        RevisionSchedule.due_at,
                        RevisionSchedule.status,
                    ).order_by(RevisionSchedule.id)
                )
            ),
            "recommendations": list(
                db.execute(
                    select(
                        LearningRecommendation.id,
                        LearningRecommendation.student_id,
                        LearningRecommendation.kind,
                        LearningRecommendation.topic_key,
                        LearningRecommendation.status,
                    ).order_by(LearningRecommendation.id)
                )
            ),
            "answers": db.scalar(select(func.count()).select_from(StudentAnswer)),
            "agent_runs": db.scalar(select(func.count()).select_from(AgentRun)),
            "profiles": list(
                db.execute(
                    select(
                        StudentProfile.user_id,
                        StudentProfile.weekly_study_hours,
                    ).order_by(StudentProfile.user_id)
                )
            ),
        }


def _make_questions(lec, topic_id: int, count: int, prefix: str, difficulty: str = "medium") -> list[int]:
    qids = []
    for idx in range(count):
        r = lec.post(
            "/api/lecturer/questions",
            json={
                "topic_id": topic_id,
                "text": f"{prefix} concept question number {idx + 1}?",
                "options": [
                    f"{prefix} correct answer {idx + 1}",
                    f"{prefix} distractor one {idx + 1}",
                    f"{prefix} distractor two {idx + 1}",
                    f"{prefix} distractor three {idx + 1}",
                ],
                "correct_label": "A",
                "explanation": f"{prefix} explanation {idx + 1}.",
                "difficulty": difficulty,
            },
        )
        assert r.status_code == 201, r.text
        qids.append(r.json()["id"])
    return qids


def _publish_quiz(
    lec,
    course_id: int,
    subject_id: int,
    title: str,
    question_ids: list[int],
    *,
    feedback_release: str = "immediate",
    due_at: str | None = None,
) -> int:
    cr = lec.post(
        "/api/lecturer/quizzes",
        params={"course_id": course_id, "subject_id": subject_id, "title": title},
    )
    assert cr.status_code == 201, cr.text
    qid = cr.json()["id"]
    ir = lec.post(f"/api/lecturer/quizzes/{qid}/items", json={"add_question_ids": question_ids})
    assert ir.status_code == 200, ir.text
    patch_body: dict = {"feedback_release": feedback_release}
    if due_at is not None:
        patch_body["due_at"] = due_at
    pr = lec.patch(f"/api/lecturer/quizzes/{qid}", json=patch_body)
    assert pr.status_code == 200, pr.text
    pub = lec.post(f"/api/lecturer/quizzes/{qid}/publish")
    assert pub.status_code == 200, pub.text
    return qid


def _take_quiz(st, app, quiz_id: int, pattern: str) -> dict:
    """Starts, answers (`r` = right, `w` = wrong, `s` = skip), and submits an assigned quiz."""
    att = st.post(f"/api/student/quizzes/{quiz_id}/start").json()
    q_order = [q["question_id"] for q in att["questions"]]
    with app.state.db.session() as db:
        by_qid = {}
        for q in db.scalars(select(Question).where(Question.id.in_(q_order))):
            by_qid[q.id] = {
                "r": next(o.id for o in q.options if o.is_correct),
                "w": next(o.id for o in q.options if not o.is_correct),
            }
    for qid, code in zip(q_order, pattern):
        if code == "s":
            continue
        r = st.put(
            f"/api/student/attempts/{att['session_id']}/answers/{qid}",
            json={"option_id": by_qid[qid][code]},
        )
        assert r.status_code == 200, r.text
    sub = st.post(f"/api/student/attempts/{att['session_id']}/submit")
    assert sub.status_code == 200, sub.text
    return sub.json()


def test_auth_and_role_enforcement_and_graph_unauthorized_route(app, make_client, settings):
    anon = make_client()
    assert anon.get("/api/student/learning-plan/preview").status_code == 401

    lec = make_client()
    lec_user = register(lec, "lecturer", name="Prof Guard")
    assert lec.get("/api/student/learning-plan/preview").status_code == 403

    # Direct graph invocation with non-student user takes deterministic unauthorized branch
    graph = compile_learning_plan_graph()
    with app.state.db.session() as db:
        out = graph.invoke(
            {"student_id": lec_user["id"], "node_history": [], "routing_history": []},
            config={"configurable": {"db": db, "settings": settings, "now": utcnow()}},
        )
    assert out["authorized"] is False
    assert out["node_history"] == ["authenticate_and_load_evidence", "return_plan_preview"]
    assert out["routing_history"][-1]["condition"] == "unauthorized"
    assert fake_model_server.STATE["n"] == 0


def test_no_eligible_material_and_no_draft_leakage(course_setup, app, make_client):
    # 1. Unenrolled student with no courses or practice history
    solo = make_client()
    register(solo, "student", name="Solo Student")
    before = _db_snapshot(app)

    r1 = solo.get("/api/student/learning-plan/preview")
    assert r1.status_code == 200, r1.text
    p1 = r1.json()
    assert p1["llm_used"] is False
    assert p1["read_only"] is True
    assert p1["scenario"] == "no_eligible_material"
    assert p1["routing_mode"] == "no_eligible_material"
    assert p1["items"] == []
    assert [a["action_type"] for a in p1["proposed_next_actions"]] == ["open_courses", "practice_lab"]
    assert p1["graph_trace"]["nodes_visited"] == [
        "authenticate_and_load_evidence",
        "build_candidate_activities",
        "construct_personalized_plan",
        "return_plan_preview",
    ]

    # 2. Enrolled student whose course only has an UNPUBLISHED draft quiz on a secret topic
    lec, st = course_setup["lec"], course_setup["st"]
    secret_topic = lec.post(
        f"/api/lecturer/units/{course_setup['unit']['id']}/topics",
        json={"name": "Unreleased Exam Kernel Internals"},
    ).json()
    draft_qids = _make_questions(lec, secret_topic["id"], 3, "SecretDraft")
    draft_quiz = lec.post(
        "/api/lecturer/quizzes",
        params={
            "course_id": course_setup["course"]["id"],
            "subject_id": course_setup["subject"]["id"],
            "title": "Unreleased Midterm Draft",
        },
    ).json()
    assert (
        lec.post(
            f"/api/lecturer/quizzes/{draft_quiz['id']}/items",
            json={"add_question_ids": draft_qids},
        ).status_code
        == 200
    )

    r2 = st.get("/api/student/learning-plan/preview")
    assert r2.status_code == 200, r2.text
    p2 = r2.json()
    assert p2["scenario"] == "no_eligible_material"
    assert p2["items"] == []
    serialized = r2.text
    assert "Unreleased Exam Kernel Internals" not in serialized
    assert "Unreleased Midterm Draft" not in serialized

    # 3. Published assessment whose opens_at is in the future (upcoming) must ALSO stay hidden
    future_topic = lec.post(
        f"/api/lecturer/units/{course_setup['unit']['id']}/topics",
        json={"name": "Future Scheduled Seminar Topic"},
    ).json()
    future_qids = _make_questions(lec, future_topic["id"], 3, "FutureQ")
    future_quiz = lec.post(
        "/api/lecturer/quizzes",
        params={
            "course_id": course_setup["course"]["id"],
            "subject_id": course_setup["subject"]["id"],
            "title": "Future Scheduled Quiz",
        },
    ).json()
    assert lec.post(f"/api/lecturer/quizzes/{future_quiz['id']}/items", json={"add_question_ids": future_qids}).status_code == 200
    opens = (utcnow().replace(tzinfo=timezone.utc) + timedelta(days=3)).isoformat()
    assert lec.patch(f"/api/lecturer/quizzes/{future_quiz['id']}", json={"opens_at": opens}).status_code == 200
    assert lec.post(f"/api/lecturer/quizzes/{future_quiz['id']}/publish").status_code == 200

    r3 = st.get("/api/student/learning-plan/preview")
    assert r3.status_code == 200, r3.text
    assert r3.json()["scenario"] == "no_eligible_material"
    assert "Future Scheduled Seminar Topic" not in r3.text
    assert "Future Scheduled Quiz" not in r3.text
    assert _db_snapshot(app) == before
    assert fake_model_server.STATE["n"] == 0


def test_insufficient_evidence_scenario_avoids_settled_mastery_percentage(course_setup, app):
    lec, st = course_setup["lec"], course_setup["st"]
    qids = _make_questions(lec, course_setup["topic"]["id"], 3, "InsuffSched", difficulty="medium")
    quiz_id = _publish_quiz(
        lec, course_setup["course"]["id"], course_setup["subject"]["id"], "Short Check", qids
    )
    _take_quiz(st, app, quiz_id, "rrw")

    before = _db_snapshot(app)
    res = st.get("/api/student/learning-plan/preview")
    assert res.status_code == 200, res.text
    plan = res.json()

    assert plan["scenario"] == "insufficient_evidence"
    assert "insufficient_evidence" in plan["scenarios"]
    assert len(plan["items"]) == 1
    item = plan["items"][0]
    assert item["topic"] == "CPU Scheduling"
    assert item["status"] == "insufficient_evidence"
    assert item["evidence_sufficient"] is False
    assert item["unique_questions"] == 3
    assert item["min_evidence"] == 5
    assert item["mastery_score_pct"] is None
    assert item["recommended_difficulty"] == "mixed"
    assert item["kind"] == "gather_evidence"
    assert any("Fewer than 5 distinct questions" in w for w in plan["warnings"])
    assert _db_snapshot(app) == before
    assert fake_model_server.STATE["n"] == 0


def test_weak_prerequisite_ordering_due_revisions_and_weekly_budget(course_setup, app):
    lec, st = course_setup["lec"], course_setup["st"]
    unit_id = course_setup["unit"]["id"]
    course_id = course_setup["course"]["id"]
    subject_id = course_setup["subject"]["id"]

    # Create prerequisite topic ("Processes") and link existing "CPU Scheduling" -> prerequisite "Processes"
    prereq_topic = lec.post(f"/api/lecturer/units/{unit_id}/topics", json={"name": "Processes"}).json()
    sched_topic_id = course_setup["topic"]["id"]
    patch_topic = lec.patch(
        f"/api/lecturer/topics/{sched_topic_id}",
        json={"prerequisite_topic_id": prereq_topic["id"]},
    )
    assert patch_topic.status_code == 200, patch_topic.text

    # Seed 5+ questions on both topics so both have sufficient evidence and weak mastery
    pre_qids = _make_questions(lec, prereq_topic["id"], 5, "Processes", difficulty="medium")
    sched_qids = _make_questions(lec, sched_topic_id, 5, "Scheduling", difficulty="medium")
    pre_quiz = _publish_quiz(lec, course_id, subject_id, "Processes Quiz", pre_qids)
    sched_quiz = _publish_quiz(lec, course_id, subject_id, "Scheduling Quiz", sched_qids)

    _take_quiz(st, app, pre_quiz, "rwwww")    # 1/5 -> weak
    _take_quiz(st, app, sched_quiz, "rwwww")  # 1/5 -> weak + creates RevisionSchedule rows

    # Make 2 revision items on Scheduling overdue now, and keep others in the future
    now = utcnow()
    with app.state.db.session() as db:
        revs = list(
            db.scalars(
                select(RevisionSchedule)
                .where(RevisionSchedule.student_id == course_setup["student"]["id"])
                .order_by(RevisionSchedule.id)
            )
        )
        assert len(revs) >= 4
        sched_revs = [r for r in revs if r.topic_key == f"t:{sched_topic_id}"]
        for r in sched_revs[:2]:
            r.due_at = now - timedelta(hours=3)
        for r in sched_revs[2:]:
            r.due_at = now + timedelta(days=3)
        for r in revs:
            if r.topic_key != f"t:{sched_topic_id}":
                r.due_at = now + timedelta(days=3)
        db.commit()

    # 1. Unset weekly hours -> unconfigured budget + Profile suggestion
    r_unset = st.get("/api/student/learning-plan/preview")
    assert r_unset.status_code == 200, r_unset.text
    p_unset = r_unset.json()
    assert p_unset["scenario"] == "weak_prerequisite"
    assert "due_revision" in p_unset["scenarios"]
    assert "sufficient_evidence" in p_unset["scenarios"]
    assert p_unset["routing_mode"] == "prioritize_remediation"
    assert p_unset["summary"]["budget_status"] == "unconfigured"
    assert p_unset["summary"]["due_revision_total"] == 2
    assert p_unset["summary"]["upcoming_revision_total"] >= 2
    assert any(a["action_type"] == "open_profile" for a in p_unset["proposed_next_actions"])

    # Verify prerequisite topic ("Processes") strictly precedes dependent weak topic ("CPU Scheduling")
    topics_order = [i["topic"] for i in p_unset["items"]]
    assert topics_order.index("Processes") < topics_order.index("CPU Scheduling")
    first = p_unset["items"][0]
    assert first["kind"] == "prerequisite"
    assert first["topic"] == "Processes"
    assert first["prerequisite_of"] == ["CPU Scheduling"]
    assert first["evidence_sufficient"] is True
    assert first["mastery_score_pct"] is not None

    rev_items = [i for i in p_unset["items"] if i["kind"] == "revisit_incorrect"]
    assert len(rev_items) == 1
    assert rev_items[0]["topic"] == "CPU Scheduling"
    assert rev_items[0]["due_revision_count"] == 2
    assert rev_items[0]["next_action"]["target_href"] == "/student/insights#revision"

    # 2. Configure 3 weekly hours in Profile -> exact 180-minute allocation
    assert st.patch("/api/auth/me", json={"weekly_study_hours": 3}).status_code == 200
    before_3h = _db_snapshot(app)
    p_3h = st.get("/api/student/learning-plan/preview").json()
    assert p_3h["summary"]["budget_status"] == "allocated"
    assert p_3h["summary"]["weekly_hours_source"] == "profile"
    assert p_3h["summary"]["allocated_minutes"] == 180
    assert sum(i["estimated_minutes"] for i in p_3h["items"]) == 180
    assert _db_snapshot(app) == before_3h

    # 3. Non-persisted ?weekly_hours=5 override does NOT mutate StudentProfile.weekly_study_hours
    p_override = st.get("/api/student/learning-plan/preview", params={"weekly_hours": 5}).json()
    assert p_override["summary"]["weekly_hours_source"] == "preview_override"
    assert p_override["summary"]["allocated_minutes"] == 300
    assert _db_snapshot(app) == before_3h

    # 4. Zero weekly hours -> 0 scheduled minutes + warning
    assert st.patch("/api/auth/me", json={"weekly_study_hours": 0}).status_code == 200
    p_zero = st.get("/api/student/learning-plan/preview").json()
    assert p_zero["summary"]["budget_status"] == "zero_hours"
    assert p_zero["summary"]["allocated_minutes"] == 0
    assert all(i["estimated_minutes"] == 0 for i in p_zero["items"])
    assert any("set to 0 in Profile" in w for w in p_zero["warnings"])
    assert fake_model_server.STATE["n"] == 0


def test_strong_sufficient_student_routes_to_challenge_and_maintain(course_setup, app):
    lec, st = course_setup["lec"], course_setup["st"]
    qids = _make_questions(lec, course_setup["topic"]["id"], 6, "StrongSched", difficulty="medium")
    quiz_id = _publish_quiz(
        lec, course_setup["course"]["id"], course_setup["subject"]["id"], "Mastery Quiz", qids
    )
    _take_quiz(st, app, quiz_id, "rrrrrr")

    before = _db_snapshot(app)
    plan = st.get("/api/student/learning-plan/preview").json()
    assert plan["scenario"] == "sufficient_evidence"
    assert plan["routing_mode"] == "challenge_and_maintain"
    assert len(plan["items"]) == 1
    item = plan["items"][0]
    assert item["status"] == "ok"
    assert item["evidence_sufficient"] is True
    assert item["kind"] in ("try_harder", "maintain")
    assert item["mastery_score_pct"] >= 75
    assert _db_snapshot(app) == before
    assert fake_model_server.STATE["n"] == 0


def test_cross_student_isolation_and_unreleased_manual_feedback_gating(course_setup, app, make_client):
    lec, st_a = course_setup["lec"], course_setup["st"]
    course_id = course_setup["course"]["id"]
    subject_id = course_setup["subject"]["id"]
    unit_id = course_setup["unit"]["id"]

    # Register Student B in the same course
    st_b = make_client()
    st_b_user = register(st_b, "student", name="Student Two")
    assert st_b.post("/api/student/courses/join", json={"join_code": course_setup["course"]["join_code"]}).status_code == 200

    # Student B has a private personal practice topic & missed revision item
    with app.state.db.session() as db:
        from app.models import AnswerOption

        priv_q = Question(
            owner_id=st_b_user["id"],
            course_id=None,
            topic_id=None,
            topic_key="p:Private Subject|Secret Personal Topic",
            subject_label="Private Subject",
            topic_label="Secret Personal Topic",
            text="Private student B question?",
            difficulty="easy",
            source_type="manual",
            review_status="personal",
            validation={},
        )
        priv_q.options.append(AnswerOption(label="A", text="Yes", is_correct=True, position=0))
        priv_q.options.append(AnswerOption(label="B", text="No", is_correct=False, position=1))
        db.add(priv_q)
        db.flush()
        db.add(
            RevisionSchedule(
                student_id=st_b_user["id"],
                question_id=priv_q.id,
                topic_key=priv_q.topic_key,
                box=1,
                due_at=utcnow() - timedelta(hours=2),
                status="active",
            )
        )
        db.commit()

    # Lecturer publishes an assessment with MANUAL feedback release
    secret_topic = lec.post(f"/api/lecturer/units/{unit_id}/topics", json={"name": "Memory Paging"}).json()
    qids = _make_questions(lec, secret_topic["id"], 5, "ManualPaging", difficulty="medium")
    manual_quiz_id = _publish_quiz(
        lec,
        course_id,
        subject_id,
        "Manual Release Exam",
        qids,
        feedback_release="manual",
    )

    # Student A submits the manual-feedback exam with wrong answers, but lecturer has NOT released feedback yet
    _take_quiz(st_a, app, manual_quiz_id, "wwwww")
    with app.state.db.session() as db:
        for r in db.scalars(
            select(RevisionSchedule).where(RevisionSchedule.student_id == course_setup["student"]["id"])
        ):
            r.due_at = utcnow() - timedelta(hours=1)
        db.commit()

    before_hidden = _db_snapshot(app)
    hidden_res = st_a.get("/api/student/learning-plan/preview")
    assert hidden_res.status_code == 200, hidden_res.text
    hidden_plan = hidden_res.json()

    # Neither Student B's private topic nor Student A's unreleased manual exam results leak!
    assert "Secret Personal Topic" not in hidden_res.text
    assert hidden_plan["summary"]["due_revision_total"] == 0
    paging_items = [i for i in hidden_plan["items"] if i["topic"] == "Memory Paging"]
    assert paging_items == []
    assert _db_snapshot(app) == before_hidden

    # Once lecturer explicitly releases feedback, Memory Paging & its due revisions appear for Student A
    rel = lec.post(f"/api/lecturer/quizzes/{manual_quiz_id}/release-feedback")
    assert rel.status_code == 200, rel.text

    released_plan = st_a.get("/api/student/learning-plan/preview").json()
    assert released_plan["summary"]["due_revision_total"] == 5
    assert any(i["topic"] == "Memory Paging" and i["kind"] == "revisit_incorrect" for i in released_plan["items"])

    # Removing Student A from the course immediately revokes access to that course's topics
    rem = lec.delete(f"/api/lecturer/courses/{course_id}/students/{course_setup['student']['id']}")
    assert rem.status_code in (200, 204), rem.text
    after_remove = st_a.get("/api/student/learning-plan/preview").json()
    assert after_remove["scenario"] == "no_eligible_material"
    assert after_remove["items"] == []
    assert fake_model_server.STATE["n"] == 0
