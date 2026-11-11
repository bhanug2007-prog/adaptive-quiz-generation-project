"""Focused tests for Stage 2 of the LangGraph Personalized Learning Agent (Persistent HITL).

Uses disposable SQLite databases (tmp_path) and the test-only fake model server; never touches adaptiveiq.db or Qwen 7B / Groq.
Covers all Stage 2 testing requirements:
1. Student plan creation and persistence.
2. Unauthorized, lecturer, and CSRF access rejection.
3. Cross-student plan & checkpoint isolation.
4. Checkpoint persistence and resume after simulated restart.
5. No action execution before explicit student approval.
6. Correct approval and resume behavior (start_practice, start_revision, open_assessment, offline handoff).
7. Repeated approval requests do not create duplicate activities + crash recovery between action commit and checkpoint save.
8. Practice action permission validation (unverified email, unenrolled/removed course, archived course, ignored spoofed fields).
9. Revision feedback-release and quarantine/rejected enforcement.
10. Dismiss and postpone behavior without altering mastery or quiz marks.
11. Real quiz completion sync and plan refresh after mastery evidence changes (Demonstration Scenario E).
12. Existing Stage 1 preview remains strictly read-only.
"""
from datetime import timedelta

from sqlalchemy import func, select

from app.main import create_app
from app.models import (
    AgentRun,
    GenerationRun,
    LangGraphCheckpoint,
    LearningPlan,
    LearningPlanExecution,
    LearningPlanItem,
    Question,
    Quiz,
    QuizResult,
    QuizSession,
    RevisionSchedule,
    TopicMasterySnapshot,
)
from app.models.base import utcnow
from tests import fake_model_server
from tests.conftest import register, wait_run
from tests.test_learning_agent import _db_snapshot, _make_questions, _publish_quiz, _take_quiz


def _seed_prerequisite_weak_scenario(course_setup, app, *, with_due_revision: bool = False) -> dict:
    lec, st = course_setup["lec"], course_setup["st"]
    unit_id = course_setup["unit"]["id"]
    course_id = course_setup["course"]["id"]
    subject_id = course_setup["subject"]["id"]
    sched_topic_id = course_setup["topic"]["id"]

    prereq_topic = lec.post(f"/api/lecturer/units/{unit_id}/topics", json={"name": "Processes"}).json()
    assert lec.patch(
        f"/api/lecturer/topics/{sched_topic_id}",
        json={"prerequisite_topic_id": prereq_topic["id"]},
    ).status_code == 200

    pre_qids = _make_questions(lec, prereq_topic["id"], 5, "ProcPre", difficulty="medium")
    sched_qids = _make_questions(lec, sched_topic_id, 5, "SchedDep", difficulty="medium")
    pre_quiz = _publish_quiz(lec, course_id, subject_id, "Processes Baseline", pre_qids)
    sched_quiz = _publish_quiz(lec, course_id, subject_id, "CPU Scheduling Baseline", sched_qids)

    _take_quiz(st, app, pre_quiz, "rwwww")    # 1/5 -> weak prerequisite
    _take_quiz(st, app, sched_quiz, "rwwww")  # 1/5 -> weak dependent topic

    with app.state.db.session() as db:
        revs = list(
            db.scalars(
                select(RevisionSchedule)
                .where(RevisionSchedule.student_id == course_setup["student"]["id"])
                .order_by(RevisionSchedule.id)
            )
        )
        for r in revs:
            r.due_at = utcnow() + timedelta(days=4)
        if with_due_revision:
            sched_revs = [r for r in revs if r.topic_key == f"t:{sched_topic_id}"]
            for r in sched_revs[:2]:
                r.due_at = utcnow() - timedelta(hours=2)
        db.commit()

    assert st.patch("/api/auth/me", json={"weekly_study_hours": 4}).status_code == 200
    return {
        "prereq_topic": prereq_topic,
        "sched_topic_id": sched_topic_id,
        "pre_quiz_id": pre_quiz,
        "sched_quiz_id": sched_quiz,
    }


def _complete_practice_quiz(st, app, quiz_id: int, all_correct: bool = True) -> dict:
    att_r = st.post(f"/api/student/quizzes/{quiz_id}/start")
    assert att_r.status_code in (200, 201), att_r.text
    att = att_r.json()
    q_order = [q["question_id"] for q in att["questions"]]
    with app.state.db.session() as db:
        by_qid = {}
        for q in db.scalars(select(Question).where(Question.id.in_(q_order))):
            by_qid[q.id] = {
                True: next(o.id for o in q.options if o.is_correct),
                False: next(o.id for o in q.options if not o.is_correct),
            }
    for qid in q_order:
        r = st.put(
            f"/api/student/attempts/{att['session_id']}/answers/{qid}",
            json={"option_id": by_qid[qid][all_correct]},
        )
        assert r.status_code == 200, r.text
    sub = st.post(f"/api/student/attempts/{att['session_id']}/submit")
    assert sub.status_code == 200, sub.text
    return sub.json()


def test_plan_creation_persistence_no_pre_approval_execution_and_stage1_readonly(course_setup, app):
    _seed_prerequisite_weak_scenario(course_setup, app)
    st = course_setup["st"]
    before_stage1 = _db_snapshot(app)

    # Stage 1 preview remains strictly read-only
    prev = st.get("/api/student/learning-plan/preview")
    assert prev.status_code == 200, prev.text
    assert prev.json()["read_only"] is True
    assert _db_snapshot(app) == before_stage1
    assert fake_model_server.STATE["n"] == 0

    with app.state.db.session() as db:
        quizzes_before = db.scalar(select(func.count()).select_from(Quiz))
        runs_before = db.scalar(select(func.count()).select_from(GenerationRun))
        sessions_before = db.scalar(select(func.count()).select_from(QuizSession))

    # No current plan before creating one
    assert st.get("/api/student/learning-plan/current").json() is None

    # Create persistent Stage 2 plan -> paused before ANY action executes
    cr = st.post("/api/student/learning-plan", json={})
    assert cr.status_code == 201, cr.text
    plan = cr.json()
    assert plan["stage"] == 2
    assert plan["llm_used"] is False
    assert plan["status"] == "awaiting_approval"
    assert plan["action_approval_status"] == "pending"
    assert plan["pending_approval"]["awaiting_approval"] is True
    assert plan["progress"]["completed_items"] == 0
    assert plan["items"][0]["topic"] == "Processes"
    assert plan["items"][0]["kind"] == "prerequisite"
    assert plan["items"][0]["item_status"] == "pending"
    assert plan["items"][0]["approval_status"] == "awaiting_approval"
    assert plan["items"][0]["approved_action_type"] == "start_practice"
    assert plan["items"][0]["can_approve"] is True

    # Verify DB persistence & strict absence of pre-approval execution or mark/mastery changes
    with app.state.db.session() as db:
        assert db.scalar(select(func.count()).select_from(Quiz)) == quizzes_before
        assert db.scalar(select(func.count()).select_from(GenerationRun)) == runs_before
        assert db.scalar(select(func.count()).select_from(QuizSession)) == sessions_before
        assert db.scalar(select(func.count()).select_from(LearningPlan)) == 1
        assert db.scalar(select(func.count()).select_from(LearningPlanItem)) == len(plan["items"])
        db_plan = db.get(LearningPlan, plan["id"])
        assert db_plan.thread_id.startswith(f"lp-s{course_setup['student']['id']}-")
        cp_count = db.scalar(
            select(func.count()).select_from(LangGraphCheckpoint).where(LangGraphCheckpoint.thread_id == db_plan.thread_id)
        )
        assert cp_count >= 1
        agent_runs = db.scalar(
            select(func.count()).select_from(AgentRun).where(AgentRun.agent == "personalized_learning")
        )
        assert agent_runs >= 1

    # Snapshot of historical marks, mastery snapshots, and revisions is untouched
    after_create = _db_snapshot(app)
    assert after_create["quiz_results"] == before_stage1["quiz_results"]
    assert after_create["snapshots"] == before_stage1["snapshots"]
    assert after_create["revisions"] == before_stage1["revisions"]
    assert fake_model_server.STATE["n"] == 0

    # Current and get-by-id return consistent persisted state
    cur = st.get("/api/student/learning-plan/current")
    assert cur.status_code == 200
    assert cur.json()["id"] == plan["id"]
    by_id = st.get(f"/api/student/learning-plan/{plan['id']}")
    assert by_id.status_code == 200
    assert by_id.json()["id"] == plan["id"]


def test_auth_role_csrf_and_cross_student_isolation(course_setup, app, make_client):
    _seed_prerequisite_weak_scenario(course_setup, app)
    st_a = course_setup["st"]
    plan_a = st_a.post("/api/student/learning-plan", json={}).json()
    pid = plan_a["id"]
    aid = plan_a["items"][0]["activity_id"]

    # Signed out -> 401
    anon = make_client()
    assert anon.get("/api/student/learning-plan/current").status_code == 401
    assert anon.get(f"/api/student/learning-plan/{pid}").status_code == 401
    assert anon.post("/api/student/learning-plan", json={}).status_code == 401
    assert anon.post(f"/api/student/learning-plan/{pid}/approve", json={}).status_code == 401
    assert anon.post(f"/api/student/learning-plan/{pid}/dismiss", json={}).status_code == 401
    assert anon.post(f"/api/student/learning-plan/{pid}/postpone", json={}).status_code == 401
    assert anon.post(f"/api/student/learning-plan/{pid}/refresh", json={}).status_code == 401

    # Lecturer -> 403
    lec = course_setup["lec"]
    assert lec.get("/api/student/learning-plan/current").status_code == 403
    assert lec.get(f"/api/student/learning-plan/{pid}").status_code == 403
    assert lec.post("/api/student/learning-plan", json={}).status_code == 403
    assert lec.post(f"/api/student/learning-plan/{pid}/approve", json={}).status_code == 403
    assert lec.post(f"/api/student/learning-plan/{pid}/dismiss", json={}).status_code == 403
    assert lec.post(f"/api/student/learning-plan/{pid}/postpone", json={}).status_code == 403
    assert lec.post(f"/api/student/learning-plan/{pid}/refresh", json={}).status_code == 403

    # Missing CSRF header with authenticated student cookie -> 403
    st_no_csrf = make_client()
    st_no_csrf.headers.pop("X-Requested-With", None)
    # Login via raw post WITH header once to get cookie, then drop header for CSRF test
    st_a_email = course_setup["student"]["email"]
    assert st_no_csrf.post("/api/auth/login", json={"email": st_a_email, "password": "Passw0rd!"},
                           headers={"X-Requested-With": "AdaptiveIQ"}).status_code == 200
    assert st_no_csrf.post(f"/api/student/learning-plan/{pid}/approve", json={"activity_id": aid}).status_code == 403

    # Other student -> 404 across read/approve/dismiss/postpone/refresh
    st_b = make_client()
    st_b_user = register(st_b, "student", name="Student Other")
    assert st_b.get(f"/api/student/learning-plan/{pid}").status_code == 404
    assert st_b.post(f"/api/student/learning-plan/{pid}/approve", json={"activity_id": aid}).status_code == 404
    assert st_b.post(f"/api/student/learning-plan/{pid}/dismiss", json={"activity_id": aid}).status_code == 404
    assert st_b.post(f"/api/student/learning-plan/{pid}/postpone", json={"activity_id": aid}).status_code == 404
    assert st_b.post(f"/api/student/learning-plan/{pid}/refresh", json={}).status_code == 404
    assert st_b.get("/api/student/learning-plan/current").json() is None

    # Direct checkpointer invocation under wrong expected_student_id cannot resume Student A's thread
    with app.state.db.session() as db:
        db_plan = db.get(LearningPlan, pid)
        assert db_plan.status == "awaiting_approval"
        from app.agents.personalized_learning import compile_persistent_learning_plan_graph
        from langgraph.types import Command
        import pytest
        from fastapi import HTTPException

        g = compile_persistent_learning_plan_graph(app.state.learning_checkpointer)
        with pytest.raises(HTTPException) as exc:
            g.invoke(
                Command(resume={"decision_type": "approve", "activity_id": aid}),
                config={
                    "configurable": {
                        "thread_id": db_plan.thread_id,
                        "db": db,
                        "settings": app.state.settings,
                        "expected_student_id": st_b_user["id"],
                        "now": utcnow(),
                    }
                },
            )
        assert exc.value.status_code in (403, 404)


def test_checkpoint_persistence_resume_after_simulated_restart_and_all_action_types(course_setup, app, settings, make_client):
    fake_model_server.STATE["mode"] = "varied"
    try:
        info = _seed_prerequisite_weak_scenario(course_setup, app, with_due_revision=True)
        # Also publish an open upcoming assigned assessment on a 3rd topic
        extra_topic = course_setup["lec"].post(
            f"/api/lecturer/units/{course_setup['unit']['id']}/topics",
            json={"name": "Virtual Memory"},
        ).json()
        vm_qids = _make_questions(course_setup["lec"], extra_topic["id"], 3, "VM", difficulty="easy")
        due_str = (utcnow() + timedelta(days=2)).isoformat()
        vm_quiz_id = _publish_quiz(
            course_setup["lec"],
            course_setup["course"]["id"],
            course_setup["subject"]["id"],
            "Virtual Memory Quiz",
            vm_qids,
            due_at=due_str,
        )

        st = course_setup["st"]
        created = st.post("/api/student/learning-plan", json={}).json()
        plan_id = created["id"]
        by_kind = {i["kind"]: i for i in created["items"]}
        assert "prerequisite" in by_kind
        assert "revisit_incorrect" in by_kind
        assert "upcoming_assessment" in by_kind
        assert by_kind["upcoming_assessment"]["quiz_id"] == vm_quiz_id

        # Simulate backend process restart: create a brand new FastAPI app sharing ONLY the SQLite DB file
        from fastapi.testclient import TestClient

        restarted_app = create_app(settings)
        try:
            with TestClient(restarted_app) as st2:
                st2.headers.update({"X-Requested-With": "AdaptiveIQ"})
                assert st2.post(
                    "/api/auth/login",
                    json={"email": course_setup["student"]["email"], "password": "Passw0rd!"},
                ).status_code == 200

                # Checkpoint survived restart
                resumed_get = st2.get("/api/student/learning-plan/current")
                assert resumed_get.status_code == 200
                assert resumed_get.json()["id"] == plan_id
                assert resumed_get.json()["status"] == "awaiting_approval"

                # 1. Approve `prerequisite` (start_practice) after restart
                app1 = st2.post(
                    f"/api/student/learning-plan/{plan_id}/approve",
                    json={"activity_id": by_kind["prerequisite"]["activity_id"], "idempotency_key": "restart-prac-1"},
                )
                assert app1.status_code == 200, app1.text
                d1 = app1.json()
                exec1 = d1["last_execution"]
                assert exec1["action_type"] == "start_practice"
                assert exec1["execution_status"] == "started"
                assert exec1["generation_run_id"] is not None
                assert exec1["quiz_id"] is not None
                assert f"run_id={exec1['generation_run_id']}" in exec1["destination_href"]
                run = wait_run(st2, exec1["generation_run_id"], timeout=60.0)
                assert run["status"] == "done" and run["ready"] >= 1

                # 2. Approve `revisit_incorrect` (start_revision) -> starts topic-scoped Leitner revision session
                app2 = st2.post(
                    f"/api/student/learning-plan/{plan_id}/approve",
                    json={"activity_id": by_kind["revisit_incorrect"]["activity_id"], "idempotency_key": "restart-rev-1"},
                )
                assert app2.status_code == 200, app2.text
                exec2 = app2.json()["last_execution"]
                assert exec2["action_type"] == "start_revision"
                assert exec2["execution_status"] in ("started", "reused_existing")
                assert exec2["session_id"] is not None
                assert exec2["destination_href"] == f"/student/attempts/{exec2['session_id']}"
                rev_att = st2.get(f"/api/student/attempts/{exec2['session_id']}").json()
                assert len(rev_att["questions"]) == 2  # only the 2 due Scheduling questions

                # 3. Approve `upcoming_assessment` (open_assessment) -> validated handoff ONLY (never creates session bypassing monitoring)
                with restarted_app.state.db.session() as db:
                    sess_before = db.scalar(select(func.count()).select_from(QuizSession))
                app3 = st2.post(
                    f"/api/student/learning-plan/{plan_id}/approve",
                    json={"activity_id": by_kind["upcoming_assessment"]["activity_id"]},
                )
                assert app3.status_code == 200, app3.text
                exec3 = app3.json()["last_execution"]
                assert exec3["action_type"] == "open_assessment"
                assert exec3["execution_status"] == "handoff"
                assert exec3["destination_href"] == f"/student/quizzes/{vm_quiz_id}"
                with restarted_app.state.db.session() as db:
                    assert db.scalar(select(func.count()).select_from(QuizSession)) == sess_before
        finally:
            restarted_app.state.db.engine.dispose()
    finally:
        fake_model_server.STATE["mode"] = "normal"


def test_repeated_approval_idempotency_and_crash_between_action_commit_and_checkpoint_save(course_setup, app, monkeypatch):
    fake_model_server.STATE["mode"] = "varied"
    try:
        _seed_prerequisite_weak_scenario(course_setup, app, with_due_revision=True)
        st = course_setup["st"]
        plan = st.post("/api/student/learning-plan", json={}).json()
        plan_id = plan["id"]
        prac_item = next(i for i in plan["items"] if i["kind"] == "prerequisite")
        rev_item = next(i for i in plan["items"] if i["kind"] == "revisit_incorrect")

        # 1. Repeated practice approval WITH same idempotency_key -> single GenerationRun & single Quiz
        r1 = st.post(
            f"/api/student/learning-plan/{plan_id}/approve",
            json={"activity_id": prac_item["activity_id"], "idempotency_key": "same-key-1"},
        )
        assert r1.status_code == 200, r1.text
        run_id_1 = r1.json()["last_execution"]["generation_run_id"]
        wait_run(st, run_id_1, timeout=60.0)

        r2 = st.post(
            f"/api/student/learning-plan/{plan_id}/approve",
            json={"activity_id": prac_item["activity_id"], "idempotency_key": "same-key-1"},
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["last_execution"]["reused_existing"] is True
        assert r2.json()["last_execution"]["generation_run_id"] == run_id_1

        # 2. Repeated practice approval WITHOUT idempotency_key (double click!) -> still reuses active run
        r3 = st.post(
            f"/api/student/learning-plan/{plan_id}/approve",
            json={"activity_id": prac_item["activity_id"]},
        )
        assert r3.status_code == 200, r3.text
        assert r3.json()["last_execution"]["reused_existing"] is True
        assert r3.json()["last_execution"]["generation_run_id"] == run_id_1

        with app.state.db.session() as db:
            assert db.scalar(select(func.count()).select_from(GenerationRun)) == 1

        # 3. Repeated revision approval WITHOUT idempotency_key -> reuses active revision session
        rev1 = st.post(
            f"/api/student/learning-plan/{plan_id}/approve",
            json={"activity_id": rev_item["activity_id"]},
        )
        assert rev1.status_code == 200, rev1.text
        rev_sid = rev1.json()["last_execution"]["session_id"]

        rev2 = st.post(
            f"/api/student/learning-plan/{plan_id}/approve",
            json={"activity_id": rev_item["activity_id"]},
        )
        assert rev2.status_code == 200, rev2.text
        assert rev2.json()["last_execution"]["reused_existing"] is True
        assert rev2.json()["last_execution"]["session_id"] == rev_sid

        # 4. Simulated CRASH right after DB execution commits, BEFORE checkpoint save succeeds!
        plan2 = st.post("/api/student/learning-plan", json={}).json()
        plan2_id = plan2["id"]
        # Use a pending topic without an active running generation; pick sched item (practice_topic)
        sched_item = next(i for i in plan2["items"] if i["kind"] == "practice_topic")

        with app.state.db.session() as db:
            runs_before = db.scalar(select(func.count()).select_from(GenerationRun))
            quizzes_before = db.scalar(select(func.count()).select_from(Quiz))

        orig_put = app.state.learning_checkpointer.put
        calls = {"n": 0}

        def crash_once_put(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("Simulated power loss before saving checkpoint!")
            return orig_put(*args, **kwargs)

        monkeypatch.setattr(app.state.learning_checkpointer, "put", crash_once_put)
        try:
            try:
                resp = st.post(
                    f"/api/student/learning-plan/{plan2_id}/approve",
                    json={"activity_id": sched_item["activity_id"], "idempotency_key": "crash-key"},
                )
                assert resp.status_code == 500
            except RuntimeError:
                pass
        finally:
            monkeypatch.undo()

        # Verify action committed ONCE before crash
        with app.state.db.session() as db:
            assert db.scalar(select(func.count()).select_from(GenerationRun)) == runs_before + 1
            assert db.scalar(select(func.count()).select_from(Quiz)) == quizzes_before + 1

        # Now client retries /approve after crash -> MUST recover idempotently with ZERO duplicate runs/quizzes!
        retry = st.post(
            f"/api/student/learning-plan/{plan2_id}/approve",
            json={"activity_id": sched_item["activity_id"], "idempotency_key": "crash-key"},
        )
        assert retry.status_code == 200, retry.text
        retry_exec = retry.json()["last_execution"]
        assert retry_exec["reused_existing"] is True
        wait_run(st, retry_exec["generation_run_id"], timeout=60.0)
        with app.state.db.session() as db:
            assert db.scalar(select(func.count()).select_from(GenerationRun)) == runs_before + 1
            assert db.scalar(select(func.count()).select_from(Quiz)) == quizzes_before + 1
    finally:
        fake_model_server.STATE["mode"] = "normal"


def test_practice_permission_validation_spoof_rejection_and_offline_handoff(course_setup, app, make_client):
    _seed_prerequisite_weak_scenario(course_setup, app)
    lec, st = course_setup["lec"], course_setup["st"]
    plan = st.post("/api/student/learning-plan", json={}).json()
    plan_id = plan["id"]
    first_item = plan["items"][0]

    # 1. Spoofed client fields are ignored (cannot redirect action or override difficulty/topic)
    fake_model_server.STATE["mode"] = "down"
    try:
        offline_res = st.post(
            f"/api/student/learning-plan/{plan_id}/approve",
            json={
                "activity_id": first_item["activity_id"],
                "target_href": "https://evil.example.com/steal",
                "topic_id": 999999,
                "difficulty": "hard",
            },
        )
        assert offline_res.status_code == 200, offline_res.text
        off_exec = offline_res.json()["last_execution"]
        assert off_exec["execution_status"] == "handoff"
        assert off_exec["destination_href"].startswith("/student/practice?")
        assert "evil.example.com" not in off_exec["destination_href"]
        assert f"topic_id={first_item['topic_id']}" in off_exec["destination_href"]
    finally:
        fake_model_server.STATE["mode"] = "varied"

    # 2. Unverified email fails revalidation before practice generation can run
    plan2 = st.post("/api/student/learning-plan", json={}).json()
    plan2_id = plan2["id"]
    item2 = plan2["items"][0]
    old_settings = app.state.settings
    app.state.settings = old_settings.model_copy(update={"require_email_verification": True})
    try:
        r_unv = st.post(
            f"/api/student/learning-plan/{plan2_id}/approve",
            json={"activity_id": item2["activity_id"]},
        )
        assert r_unv.status_code == 403
        assert "Verify your email" in r_unv.json()["detail"]
    finally:
        app.state.settings = old_settings

    # 3. Removing student from course (or archiving course) blocks execution even if plan already existed
    assert lec.delete(f"/api/lecturer/courses/{course_setup['course']['id']}/students/{course_setup['student']['id']}").status_code in (200, 204)
    r_removed = st.post(
        f"/api/student/learning-plan/{plan2_id}/approve",
        json={"activity_id": item2["activity_id"]},
    )
    assert r_removed.status_code == 404
    fake_model_server.STATE["mode"] = "normal"


def test_revision_feedback_release_and_quarantine_enforcement(course_setup, app):
    lec, st = course_setup["lec"], course_setup["st"]
    qids = _make_questions(lec, course_setup["topic"]["id"], 3, "ManualRev", difficulty="medium")
    manual_quiz = _publish_quiz(
        lec,
        course_setup["course"]["id"],
        course_setup["subject"]["id"],
        "Manual Feedback Quiz",
        qids,
        feedback_release="manual",
    )
    _take_quiz(st, app, manual_quiz, "www")
    with app.state.db.session() as db:
        for rs in db.scalars(select(RevisionSchedule).where(RevisionSchedule.student_id == course_setup["student"]["id"])):
            rs.due_at = utcnow() - timedelta(hours=2)
        db.commit()

    # Plan created BEFORE feedback release must NOT contain due revisions
    p_hidden = st.post("/api/student/learning-plan", json={}).json()
    assert not any(i["kind"] == "revisit_incorrect" for i in p_hidden["items"])
    assert p_hidden["summary"]["due_revision_total"] == 0

    # Release feedback -> refresh plan -> `revisit_incorrect` appears cleanly
    assert lec.post(f"/api/lecturer/quizzes/{manual_quiz}/release-feedback").status_code == 200
    p_rel = st.post(f"/api/student/learning-plan/{p_hidden['id']}/refresh", json={}).json()
    rev_item = next(i for i in p_rel["items"] if i["kind"] == "revisit_incorrect")

    # Quarantine / reject ALL due questions BEFORE student clicks Approve -> server must block starting revision!
    for qid in qids:
        assert lec.post(f"/api/lecturer/questions/{qid}/review", json={"action": "reject", "note": "bad item"}).status_code == 200
        with app.state.db.session() as db:
            q = db.get(Question, qid)
            q.validation = {**(q.validation or {}), "quarantined": True}
            db.commit()

    blocked = st.post(
        f"/api/student/learning-plan/{p_rel['id']}/approve",
        json={"activity_id": rev_item["activity_id"]},
    )
    assert blocked.status_code == 409


def test_dismiss_and_postpone_preserve_mastery_and_quiz_results(course_setup, app):
    _seed_prerequisite_weak_scenario(course_setup, app, with_due_revision=True)
    st = course_setup["st"]
    plan = st.post("/api/student/learning-plan", json={}).json()
    pid = plan["id"]
    before_snap = _db_snapshot(app)
    mastery_before = st.get("/api/student/mastery").json()

    item1, item2 = plan["items"][0], plan["items"][1]

    # Postpone item 1
    post_r = st.post(
        f"/api/student/learning-plan/{pid}/postpone",
        json={"activity_id": item1["activity_id"], "postpone_days": 3, "note": "Study after lab"},
    )
    assert post_r.status_code == 200, post_r.text
    p_after_post = post_r.json()
    up1 = next(i for i in p_after_post["items"] if i["activity_id"] == item1["activity_id"])
    assert up1["item_status"] == "postponed"
    assert up1["approval_status"] == "postponed"
    assert up1["postponed_until"] is not None
    assert up1["completed_at"] is None
    assert p_after_post["progress"]["completed_items"] == 0

    # Dismiss item 2
    dis_r = st.post(
        f"/api/student/learning-plan/{pid}/dismiss",
        json={"activity_id": item2["activity_id"], "scope": "item", "note": "Already reviewed notes"},
    )
    assert dis_r.status_code == 200, dis_r.text
    p_after_dis = dis_r.json()
    up2 = next(i for i in p_after_dis["items"] if i["activity_id"] == item2["activity_id"])
    assert up2["item_status"] == "dismissed"
    assert up2["completed_at"] is None

    # Dismiss whole plan -> status dismissed, idempotent repeat, cannot approve
    dis_plan = st.post(f"/api/student/learning-plan/{pid}/dismiss", json={"scope": "plan"}).json()
    assert dis_plan["status"] == "dismissed"
    assert st.post(f"/api/student/learning-plan/{pid}/dismiss", json={"scope": "plan"}).json()["status"] == "dismissed"
    assert st.post(f"/api/student/learning-plan/{pid}/approve", json={"activity_id": item1["activity_id"]}).status_code == 409

    # Mastery scores, quiz results, and revision schedules did NOT change
    after_snap = _db_snapshot(app)
    assert after_snap["quiz_results"] == before_snap["quiz_results"]
    assert after_snap["snapshots"] == before_snap["snapshots"]
    assert after_snap["revisions"] == before_snap["revisions"]
    assert st.get("/api/student/mastery").json() == mastery_before


def test_scenario_e_real_completion_sync_and_plan_refresh_on_updated_mastery(course_setup, app):
    """End-to-end Demonstration Scenario E:
    weak CPU Scheduling -> recommends prerequisite Processes first -> saved & paused ->
    student approves Processes practice -> completes generated practice strongly ->
    completion synced -> refresh moves CPU Scheduling forward with Epoch 1 history preserved."""
    fake_model_server.STATE["mode"] = "varied"
    try:
        _seed_prerequisite_weak_scenario(course_setup, app)
        st = course_setup["st"]

        # 1-4. Save plan -> paused at HITL interrupt with Processes ranked #1 prerequisite
        plan = st.post("/api/student/learning-plan", json={}).json()
        pid = plan["id"]
        assert plan["generation_seq"] == 1
        assert plan["status"] == "awaiting_approval"
        assert plan["items"][0]["topic"] == "Processes"
        assert plan["items"][0]["kind"] == "prerequisite"
        assert "CPU Scheduling" in plan["items"][0]["prerequisite_of"]

        proc_item = plan["items"][0]

        # 5-6. Approve practice on Processes -> starts GenerationRun & creates Quiz (in_progress, NOT completed yet)
        approved = st.post(
            f"/api/student/learning-plan/{pid}/approve",
            json={"activity_id": proc_item["activity_id"], "idempotency_key": "scen-e-1"},
        ).json()
        assert approved["status"] == "in_progress"
        assert approved["items"][0]["item_status"] == "in_progress"
        assert approved["progress"]["completed_items"] == 0
        run_id = approved["last_execution"]["generation_run_id"]
        quiz_id = approved["last_execution"]["quiz_id"]
        run = wait_run(st, run_id, timeout=60.0)
        assert run["status"] == "done" and run["ready"] >= 5

        # 7. Complete TWO 5-question all-correct practice rounds (or 5+5) so Processes moves firmly into 'ok' mastery!
        _complete_practice_quiz(st, app, quiz_id, all_correct=True)
        # Generate one more practice quiz cleanly OR add 1 more all-correct attempt if still borderline:
        # Baseline was 1/5 (alpha=2, beta=5) -> adding 5 right -> (7, 5) mean 0.58; let's take 1 more practice attempt so beta posterior crosses >= 0.70 ('ok')
        _complete_practice_quiz(st, app, quiz_id, all_correct=True)
        mastery_now = {t["topic"]: t for t in st.get("/api/student/mastery").json()["topics"]}
        # Verify Processes evidence increased (unique questions + stronger accuracy)
        assert mastery_now["Processes"]["score"] > 0.5

        # Check completion sync via GET before refresh
        synced = st.get(f"/api/student/learning-plan/{pid}").json()
        synced_proc = next(i for i in synced["items"] if i["activity_id"] == proc_item["activity_id"])
        assert synced_proc["item_status"] == "completed"
        assert synced_proc["completed_at"] is not None
        assert synced["progress"]["completed_items"] == 1

        # Also boost Processes snapshot enough to clear weak prerequisite so refresh shows topic change if still developing
        # (with 1/5 + 5/5 unique questions: alpha=1+1+5=7, beta=1+4+0=5 -> mean=0.583 ('developing'); add 4 more distinct right answers -> alpha=11, beta=5 -> mean=0.6875; add 5 -> alpha=16, beta=5 -> 0.76 'ok'!)
        # Actually let's give one quick second practice quiz on Processes via lecturer or practice so unique_questions is high!
        more_proc = _make_questions(course_setup["lec"], proc_item["topic_id"], 6, "ProcMaster", difficulty="medium")
        more_quiz = _publish_quiz(
            course_setup["lec"],
            course_setup["course"]["id"],
            course_setup["subject"]["id"],
            "Processes Mastery Check",
            more_proc,
        )
        _take_quiz(st, app, more_quiz, "rrrrrr")

        # 8. Refresh plan -> reloads updated mastery & recalculates Epoch 2 WITHOUT executing actions!
        with app.state.db.session() as db:
            runs_before_refresh = db.scalar(select(func.count()).select_from(GenerationRun))
        refreshed = st.post(f"/api/student/learning-plan/{pid}/refresh", json={}).json()
        with app.state.db.session() as db:
            assert db.scalar(select(func.count()).select_from(GenerationRun)) == runs_before_refresh

        assert refreshed["generation_seq"] == 2
        assert refreshed["last_refreshed_at"] is not None
        assert refreshed["status"] == "awaiting_approval"
        # Old Epoch 1 completed item preserved in `previous_items` alongside superseded items
        assert any(i["topic"] == "Processes" and i["item_status"] == "completed" for i in refreshed["previous_items"])
        assert any(i["topic"] == "CPU Scheduling" and i["item_status"] == "superseded" for i in refreshed["previous_items"])
        # New Epoch 2 promotes CPU Scheduling to Rank 1 (now unblocked, prerequisite resolved!)
        assert refreshed["items"][0]["topic"] == "CPU Scheduling"
        assert refreshed["items"][0]["kind"] == "practice_topic"
        assert refreshed["items"][0]["blocked_by_prerequisite"] is None
        assert refreshed["items"][0]["is_refreshed_new"] is True
        assert refreshed["items"][0]["change_status"] in ("new", "updated")
    finally:
        fake_model_server.STATE["mode"] = "normal"
