"""Regression tests for MCQ quarantine, reapproval restrictions, published/archived quiz access, and revision exclusion."""
from datetime import timedelta

from sqlalchemy import select

from app.models import GenerationRun, Question, QuestionEvaluation, RevisionSchedule
from app.models.base import utcnow
from app.services.quality_service import QualityEvaluator
from tests import fake_grok_server
from tests.conftest import register
from tests.test_flow import _approve_all, _draft
from tests.test_quality import GROK_KEY, grok_port  # noqa: F401


def _quarantine_in_db(app, qid: int):
    with app.state.db.session() as db:
        q = db.get(Question, qid)
        q.review_status = "rejected"
        v = dict(q.validation or {})
        v.update(
            quarantined=True,
            failed_validation=True,
            failure_reason="quarantined_invalid_mcq",
            failure_text="Quarantined invalid stem or answer key.",
        )
        q.validation = v
        db.commit()


def test_locked_quarantined_question_requires_duplicate_edit_and_recheck(course_setup, app):
    lec, st = course_setup["lec"], course_setup["st"]
    run = _draft(course_setup, 1)
    qid = run["quiz_id"]
    _approve_all(lec, qid)
    assert lec.post(f"/api/lecturer/quizzes/{qid}/publish").status_code == 200

    att = st.post(f"/api/student/quizzes/{qid}/start").json()
    q_id = att["questions"][0]["question_id"]
    opt_id = att["questions"][0]["options"][0]["id"]
    assert st.put(f"/api/student/attempts/{att['session_id']}/answers/{q_id}", json={"option_id": opt_id}).status_code == 200
    assert st.post(f"/api/student/attempts/{att['session_id']}/submit").status_code == 200

    _quarantine_in_db(app, q_id)

    # Locked quarantined question cannot be approved, reset, edited, or cleared
    assert lec.post(f"/api/lecturer/questions/{q_id}/review", json={"action": "approve"}).status_code == 409
    assert lec.post(f"/api/lecturer/questions/{q_id}/review", json={"action": "reset"}).status_code == 409
    assert lec.patch(f"/api/lecturer/questions/{q_id}", json={"text": "Attempted edit on locked?"}).status_code == 409
    assert lec.post(f"/api/lecturer/questions/{q_id}/check-quality").status_code == 422

    # Duplicating carries quarantine flag: cannot be approved or checked before a real content edit
    dup = lec.post(f"/api/lecturer/questions/{q_id}/duplicate")
    assert dup.status_code == 201
    copy_id = dup.json()["id"]
    assert dup.json()["review_status"] == "draft"
    assert dup.json()["validation"]["quarantined"] is True
    assert lec.post(f"/api/lecturer/questions/{copy_id}/review", json={"action": "approve"}).status_code == 422
    assert lec.post(f"/api/lecturer/questions/{copy_id}/check-quality").status_code == 422

    # Metadata-only edit (difficulty) does not lift quarantine
    only_diff = lec.patch(f"/api/lecturer/questions/{copy_id}", json={"difficulty": "hard"}).json()
    assert only_diff["validation"]["quarantined"] is True
    assert lec.post(f"/api/lecturer/questions/{copy_id}/review", json={"action": "approve"}).status_code == 422

    # Content edit lifts 'quarantined' into 'quarantine_recheck_required'
    edited = lec.patch(f"/api/lecturer/questions/{copy_id}", json={
        "text": "Which pointer updates occur when inserting at position 3 in a singly linked list?",
        "options": [
            "Only node 1 changes",
            "Node 2 next and new node next are updated",
            "Tail points to null",
            "Head is replaced",
        ],
        "correct_label": "B",
        "explanation": "Updating both node 2 next and the new node next splices the new node at position 3.",
    })
    assert edited.status_code == 200
    assert edited.json()["review_status"] == "draft"
    assert edited.json()["validation"]["quarantined"] is False
    assert edited.json()["validation"]["quarantine_recheck_required"] is True

    # Must still run check-quality before approval is allowed
    assert lec.post(f"/api/lecturer/questions/{copy_id}/review", json={"action": "approve"}).status_code == 422

    checked = lec.post(f"/api/lecturer/questions/{copy_id}/check-quality")
    assert checked.status_code == 200, checked.text
    assert "quarantine_recheck_required" not in checked.json()["validation"]
    assert "failed_validation" not in checked.json()["validation"]

    approved = lec.post(f"/api/lecturer/questions/{copy_id}/review", json={"action": "approve"})
    assert approved.status_code == 200
    assert approved.json()["review_status"] == "approved"


def test_unlocked_quarantined_question_requires_edit_and_ai_check_when_enabled(course_setup, app, grok_port):  # noqa: F811
    fake_grok_server.reset("pass")
    s_with_ai = app.state.quality.s.model_copy(update={
        "grok_api_key": GROK_KEY,
        "grok_base_url": f"http://127.0.0.1:{grok_port}",
        "grok_model": "grok-test",
        "grok_timeout_s": 0.5,
        "grok_cooldown_s": 300,
    })
    old_quality = app.state.quality
    app.state.quality = QualityEvaluator(s_with_ai)
    try:
        lec = course_setup["lec"]
        run = _draft(course_setup, 1)
        q_id = lec.get(f"/api/lecturer/quizzes/{run['quiz_id']}").json()["items"][0]["question"]["id"]

        _quarantine_in_db(app, q_id)

        # Reset moves unlocked quarantined question to draft, but approval/check remain blocked until edited
        assert lec.post(f"/api/lecturer/questions/{q_id}/review", json={"action": "approve"}).status_code == 422
        assert lec.post(f"/api/lecturer/questions/{q_id}/review", json={"action": "reset"}).status_code == 200
        assert lec.post(f"/api/lecturer/questions/{q_id}/review", json={"action": "approve"}).status_code == 422

        assert lec.patch(f"/api/lecturer/questions/{q_id}", json={
            "text": "Corrected question stem requiring AI re-check?",
            "explanation": "Corrected explanation matching the keyed answer.",
        }).status_code == 200

        # AI rejects on first check -> approval must stay blocked
        fake_grok_server.reset("incorrect")
        bad_check = lec.post(f"/api/lecturer/questions/{q_id}/check-quality")
        assert bad_check.status_code == 200
        assert bad_check.json()["validation"]["failed_validation"] is True
        assert lec.post(f"/api/lecturer/questions/{q_id}/review", json={"action": "approve"}).status_code == 422

        # Shift eval timestamp past 10s rate limit before retrying with passing AI review
        with app.state.db.session() as db:
            for ev in db.scalars(select(QuestionEvaluation).where(QuestionEvaluation.question_id == q_id)):
                ev.created_at = utcnow() - timedelta(seconds=30)
            db.commit()

        fake_grok_server.reset("pass")
        good_check = lec.post(f"/api/lecturer/questions/{q_id}/check-quality")
        assert good_check.status_code == 200
        assert "failed_validation" not in good_check.json()["validation"]
        assert lec.post(f"/api/lecturer/questions/{q_id}/review", json={"action": "approve"}).status_code == 200
    finally:
        app.state.quality.close()
        app.state.quality = old_quality


def test_rejected_and_quarantined_questions_cannot_be_added_to_draft_quizzes(course_setup, app):
    lec = course_setup["lec"]
    run = _draft(course_setup, 2)
    items = lec.get(f"/api/lecturer/quizzes/{run['quiz_id']}").json()["items"]
    rej_id = items[0]["question"]["id"]
    dup_q_src = items[1]["question"]["id"]

    assert lec.post(f"/api/lecturer/questions/{rej_id}/review", json={"action": "reject", "note": "bad"}).status_code == 200
    _quarantine_in_db(app, dup_q_src)
    dup_id = lec.post(f"/api/lecturer/questions/{dup_q_src}/duplicate").json()["id"]

    new_quiz = lec.post("/api/lecturer/quizzes", params={
        "course_id": course_setup["course"]["id"],
        "subject_id": course_setup["subject"]["id"],
        "title": "Handpicked draft quiz",
    }).json()

    r1 = lec.post(f"/api/lecturer/quizzes/{new_quiz['id']}/items", json={"add_question_ids": [rej_id]})
    assert r1.status_code == 422
    r2 = lec.post(f"/api/lecturer/quizzes/{new_quiz['id']}/items", json={"add_question_ids": [dup_id]})
    assert r2.status_code == 422
    assert lec.post(f"/api/lecturer/quizzes/{run['quiz_id']}/publish").status_code == 422


def test_archived_quiz_blocks_new_attempts_while_preserving_results_and_lecturer_analytics(course_setup, app):
    lec, st = course_setup["lec"], course_setup["st"]
    run = _draft(course_setup, 2)
    qid = run["quiz_id"]
    _approve_all(lec, qid)
    lec.patch(f"/api/lecturer/quizzes/{qid}", json={"contribution_pct": 10, "attempts_allowed": 1})
    assert lec.post(f"/api/lecturer/quizzes/{qid}/publish").status_code == 200

    # Student 1 completes the published quiz
    att = st.post(f"/api/student/quizzes/{qid}/start").json()
    sid = att["session_id"]
    q_ids = [q["question_id"] for q in att["questions"]]
    full = {it["question"]["id"]: it["question"] for it in lec.get(f"/api/lecturer/quizzes/{qid}").json()["items"]}
    right_0 = next(o["id"] for o in full[q_ids[0]]["options"] if o["is_correct"])
    assert st.put(f"/api/student/attempts/{sid}/answers/{q_ids[0]}", json={"option_id": right_0}).status_code == 200
    res_before = st.post(f"/api/student/attempts/{sid}/submit").json()
    assert res_before["percentage"] == 50.0 and res_before["contribution_earned"] == 5.0

    # Quarantine first question
    _quarantine_in_db(app, q_ids[0])

    # New student joins course
    new_st = course_setup["make_client"]()
    register(new_st, "student", name="New Enrollee")
    assert new_st.post("/api/student/courses/join", json={"join_code": course_setup["course"]["join_code"]}).status_code == 200

    # Defense-in-depth: even before archiving, start_attempt blocks an assessment containing a quarantined/rejected question
    assert new_st.post(f"/api/student/quizzes/{qid}/start").status_code == 409

    # Archive via supported mechanism: quiz disappears from student catalog & start endpoints return 404
    assert lec.post(f"/api/lecturer/quizzes/{qid}/archive").status_code == 200
    assert new_st.get("/api/student/quizzes/assigned").json() == []
    assert new_st.get(f"/api/student/quizzes/{qid}").status_code == 404
    assert new_st.post(f"/api/student/quizzes/{qid}/start").status_code == 404
    assert st.post(f"/api/student/quizzes/{qid}/start").status_code == 404

    # Historical student result, marks & history remain intact
    hist = st.get("/api/student/history").json()
    assert len(hist) == 1 and hist[0]["quiz_id"] == qid and hist[0]["percentage"] == 50.0
    res_after = st.get(f"/api/student/attempts/{sid}/result").json()
    assert res_after["percentage"] == 50.0 and res_after["contribution_earned"] == 5.0 and res_after["can_retry"] is False

    # Lecturer keeps full visibility into archived quiz and historical analytics/reports
    archived_list = lec.get("/api/lecturer/quizzes", params={"status": "archived"}).json()
    assert [z["id"] for z in archived_list] == [qid]
    assert lec.get(f"/api/lecturer/quizzes/{qid}").status_code == 200
    analytics = lec.get(f"/api/lecturer/courses/{course_setup['course']['id']}/analytics").json()
    assert analytics["average"] == 50.0 and analytics["submissions"] == 1
    csv_resp = lec.get(f"/api/lecturer/reports/quizzes/{qid}/results.csv")
    assert csv_resp.status_code == 200 and "50.0" in csv_resp.text and "Student One" in csv_resp.text


def test_spaced_revision_excludes_rejected_and_quarantined_questions(course_setup, app):
    lec, st = course_setup["lec"], course_setup["st"]
    run = _draft(course_setup, 2)
    qid = run["quiz_id"]
    _approve_all(lec, qid)
    assert lec.post(f"/api/lecturer/quizzes/{qid}/publish").status_code == 200

    att = st.post(f"/api/student/quizzes/{qid}/start").json()
    q1_id, q2_id = att["questions"][0]["question_id"], att["questions"][1]["question_id"]
    full = {it["question"]["id"]: it["question"] for it in lec.get(f"/api/lecturer/quizzes/{qid}").json()["items"]}
    wrong_1 = next(o["id"] for o in full[q1_id]["options"] if not o["is_correct"])
    # Miss Q1 and skip Q2 so both get RevisionSchedule rows
    assert st.put(f"/api/student/attempts/{att['session_id']}/answers/{q1_id}", json={"option_id": wrong_1}).status_code == 200
    assert st.post(f"/api/student/attempts/{att['session_id']}/submit").status_code == 200

    # Move both schedules due into the past
    with app.state.db.session() as db:
        for rs in db.scalars(select(RevisionSchedule).where(RevisionSchedule.student_id == course_setup["student"]["id"])):
            rs.due_at = utcnow() - timedelta(days=1)
        db.commit()

    rev_before = st.get("/api/student/revision").json()
    assert {r["question_id"] for r in rev_before["due"]} == {q1_id, q2_id}

    # Reject/quarantine Q1 even WITHOUT retiring its RevisionSchedule row directly
    assert lec.post(f"/api/lecturer/questions/{q1_id}/review", json={"action": "reject", "note": "wrong key"}).status_code == 200
    with app.state.db.session() as db:
        q1 = db.get(Question, q1_id)
        q1.validation = {**(q1.validation or {}), "quarantined": True}
        db.commit()

    rev_after = st.get("/api/student/revision").json()
    assert [r["question_id"] for r in rev_after["due"]] == [q2_id]
    assert rev_after["upcoming"] == []
    assert st.get("/api/student/overview").json()["revision_due"] == 1
    assert st.get("/api/student/trends").json()["revision"]["due_now"] == 1

    # Starting revision quiz only delivers valid question Q2, never rejected Q1
    rev_quiz = st.post("/api/student/revision/start").json()
    rev_att = st.get(f"/api/student/attempts/{rev_quiz['session_id']}").json()
    assert [q["question_id"] for q in rev_att["questions"]] == [q2_id]

    # Interrupted failed generation runs with partial drafts keep audit rows intact and stay unpublishable
    draft_run = _draft(course_setup, 2)
    with app.state.db.session() as db:
        gr = db.get(GenerationRun, draft_run["run_id"])
        gr.status = "failed"
        gr.error = "Interrupted mid-run."
        db.commit()
    assert lec.post(f"/api/lecturer/quizzes/{draft_run['quiz_id']}/publish").status_code == 422
    assert lec.get(f"/api/generation/{draft_run['run_id']}").json()["status"] == "failed"
