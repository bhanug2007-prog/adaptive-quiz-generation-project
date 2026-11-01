"""End-to-end API workflow with the TEST-ONLY fake model: lecturer generates, reviews and publishes;
a student attempts; scoring, feedback release, mastery, recommendations, revision and exports follow."""
from datetime import datetime, timedelta, timezone

from tests.conftest import wait_run


def _draft(cs, n=4, **extra):
    lec = cs["lec"]
    body = {"course_id": cs["course"]["id"], "subject_id": cs["subject"]["id"], "topic_id": cs["topic"]["id"],
            "title": "Scheduling quiz 1", "question_count": n, "difficulty": "mixed", **extra}
    r = lec.post("/api/lecturer/generate", json=body)
    assert r.status_code == 202, r.text
    run = wait_run(lec, r.json()["run_id"])
    assert run["status"] in ("done", "partial"), run
    return run


def _approve_all(lec, quiz_id):
    q = lec.get(f"/api/lecturer/quizzes/{quiz_id}").json()
    for it in q["items"]:
        r = lec.post(f"/api/lecturer/questions/{it['question']['id']}/review", json={"action": "approve"})
        assert r.status_code == 200
    return lec.get(f"/api/lecturer/quizzes/{quiz_id}").json()


def test_generation_rejects_bad_questions_and_stays_draft(course_setup):
    run = _draft(course_setup, 4)
    assert run["ready"] == 4 and run["status"] == "done"
    assert run["rejected"].get("format", 0) >= 1                 # the fake model sends broken output
    assert run["rejected"].get("math_wrong_key", 0) >= 1         # and a wrong maths key the Python check catches
    quiz = course_setup["lec"].get(f"/api/lecturer/quizzes/{run['quiz_id']}").json()
    assert quiz["status"] == "draft" and len(quiz["items"]) == 4
    assert all(it["question"]["review_status"] == "draft" for it in quiz["items"])
    assert all(it["question"]["model"] for it in quiz["items"])   # model version recorded


def test_cannot_publish_unreviewed(course_setup):
    run = _draft(course_setup, 2)
    r = course_setup["lec"].post(f"/api/lecturer/quizzes/{run['quiz_id']}/publish")
    assert r.status_code == 422 and "Approve" in r.json()["detail"]


def test_edit_change_key_and_reapproval(course_setup):
    lec = course_setup["lec"]
    run = _draft(course_setup, 1)
    q = lec.get(f"/api/lecturer/quizzes/{run['quiz_id']}").json()["items"][0]["question"]
    lec.post(f"/api/lecturer/questions/{q['id']}/review", json={"action": "approve"})
    r = lec.patch(f"/api/lecturer/questions/{q['id']}", json={"correct_label": "D", "text": "Edited question text here?"})
    assert r.status_code == 200
    e = r.json()
    assert e["review_status"] == "draft"                         # edits need re-approval
    assert [o["is_correct"] for o in e["options"]] == [False, False, False, True]
    hist = lec.get(f"/api/lecturer/questions/{q['id']}/history").json()
    assert [h["action"] for h in hist] == ["approved", "edited"]
    bad = lec.patch(f"/api/lecturer/questions/{q['id']}", json={"options": ["a", "a", "b", "c"]})
    assert bad.status_code == 422


def test_regenerate_one_question(course_setup):
    lec = course_setup["lec"]
    run = _draft(course_setup, 2)
    quiz = lec.get(f"/api/lecturer/quizzes/{run['quiz_id']}").json()
    old = quiz["items"][0]["question"]["id"]
    r = lec.post(f"/api/lecturer/questions/{old}/regenerate?quiz_id={quiz['id']}")
    assert r.status_code == 202, r.text
    assert wait_run(lec, r.json()["run_id"])["status"] == "done"
    quiz2 = lec.get(f"/api/lecturer/quizzes/{quiz['id']}").json()
    assert quiz2["items"][0]["question"]["id"] != old and quiz2["items"][0]["position"] == 0
    assert lec.get(f"/api/lecturer/questions/{old}").json()["review_status"] == "rejected"


def test_full_assessment_flow(course_setup):
    lec, st = course_setup["lec"], course_setup["st"]
    run = _draft(course_setup, 4)
    qid = run["quiz_id"]
    _approve_all(lec, qid)
    r = lec.patch(f"/api/lecturer/quizzes/{qid}", json={"contribution_pct": 30})
    assert r.status_code == 200
    r = lec.post(f"/api/lecturer/quizzes/{qid}/publish")
    assert r.status_code == 422 and "20%" in r.json()["detail"]   # subject cap is 20%
    lec.patch(f"/api/lecturer/quizzes/{qid}", json={"contribution_pct": 10, "feedback_release": "manual",
                                                     "attempts_allowed": 1})
    assert lec.post(f"/api/lecturer/quizzes/{qid}/publish").status_code == 200

    cards = st.get("/api/student/quizzes/assigned").json()
    assert len(cards) == 1 and cards[0]["state"] == "open" and cards[0]["lecturer"] == "Dr Lecturer"
    att = st.post(f"/api/student/quizzes/{qid}/start").json()
    assert "is_correct" not in str(att) and "explanation" not in att["questions"][0]   # no key before submission
    assert st.post(f"/api/student/attempts/{att['session_id']}/answers/{att['questions'][0]['question_id']}/check").status_code == 403

    # correct answer for q1 via the lecturer's view, wrong for q2, q3 skipped, q4 correct
    full = {it["question"]["id"]: it["question"] for it in lec.get(f"/api/lecturer/quizzes/{qid}").json()["items"]}
    def opt(qid_, correct):
        return next(o["id"] for o in full[qid_]["options"] if o["is_correct"] == correct)
    qs = [q["question_id"] for q in att["questions"]]
    sid = att["session_id"]
    for k, choose in ((0, True), (1, False), (3, True)):
        r = st.put(f"/api/student/attempts/{sid}/answers/{qs[k]}", json={"option_id": opt(qs[k], choose), "time_spent_s": 12})
        assert r.status_code == 200, r.text
    # with attempts, locked fields may be resent unchanged but not changed
    assert lec.patch(f"/api/lecturer/quizzes/{qid}", json={"contribution_pct": 10, "title": "Scheduling quiz 1"}).status_code == 200
    assert lec.patch(f"/api/lecturer/quizzes/{qid}", json={"contribution_pct": 15}).status_code == 409
    # resuming returns the saved answers (refresh-safe)
    again = st.post(f"/api/student/quizzes/{qid}/start").json()
    assert again["session_id"] == sid and len(again["answers"]) == 3

    res = st.post(f"/api/student/attempts/{sid}/submit").json()
    assert res["feedback_available"] is False and res["percentage"] is None     # manual release
    assert st.post(f"/api/student/quizzes/{qid}/start").status_code == 409       # 1 attempt allowed
    lec.post(f"/api/lecturer/quizzes/{qid}/release-feedback")
    res = st.get(f"/api/student/attempts/{sid}/result").json()
    assert (res["correct"], res["incorrect"], res["unanswered"]) == (2, 1, 1)
    assert res["raw_score"] == 2 and res["max_score"] == 4 and res["percentage"] == 50.0
    assert res["contribution_earned"] == 5.0                                    # 50% of a 10% quiz
    assert {i["outcome"] for i in res["items"]} == {"correct", "incorrect", "skipped"}
    assert res["topics"][0]["mastery_label"] == "insufficient_evidence"        # 4 questions < 5 minimum

    # lecturer analytics and exports
    perf = lec.get(f"/api/lecturer/courses/{course_setup['course']['id']}/analytics").json()
    assert perf["average"] == 50.0 and perf["completion_rate"] == 1.0 and perf["submissions"] == 1
    hm = lec.get(f"/api/lecturer/courses/{course_setup['course']['id']}/heatmap").json()
    assert hm["students"][0]["cells"][0]["label"] == "insufficient_evidence"
    cell = lec.get(f"/api/lecturer/courses/{course_setup['course']['id']}/heatmap/cell",
                   params={"student_id": course_setup["student"]["id"], "topic_id": course_setup["topic"]["id"]}).json()
    assert cell["attempts"][0]["correct"] == 2
    csv = lec.get(f"/api/lecturer/reports/quizzes/{qid}/results.csv")
    assert csv.status_code == 200 and "50.0" in csv.text and "Student One" in csv.text
    qa = lec.get(f"/api/lecturer/quizzes/{qid}/question-analytics").json()
    assert len(qa) == 4 and all(not x["enough_data"] for x in qa)              # 1 answer: no flags claimed
    ov = lec.get("/api/lecturer/overview").json()
    assert ov["enrolled_students"] == 1 and ov["published_quizzes"] == 1

    # student analytics
    st_over = st.get("/api/student/overview").json()
    assert st_over["average_30d"]["assessment"]["average"] == 50.0 and st_over["streak_days"] == 1
    qstat = st.get("/api/student/question-status").json()
    assert len(qstat["skipped"]) == 1 and len(qstat["incorrect"]) == 1
    rev = st.get("/api/student/revision").json()
    assert len(rev["upcoming"]) == 2 and not rev["due"]                         # missed + skipped, due tomorrow


def test_practice_generation_and_check(course_setup):
    st = course_setup["st"]
    r = st.post("/api/student/practice/generate", json={"subject": "DBMS", "topic": "SQL joins", "question_count": 5,
                                                         "difficulty": "adaptive"})
    assert r.status_code == 202, r.text
    assert r.json()["difficulty_note"].startswith("No answers")
    run = wait_run(st, r.json()["run_id"])
    assert run["status"] == "done"
    att = st.post(f"/api/student/quizzes/{run['quiz_id']}/start").json()
    q = att["questions"][0]
    assert st.post(f"/api/student/attempts/{att['session_id']}/answers/{q['question_id']}/check").status_code == 422
    st.put(f"/api/student/attempts/{att['session_id']}/answers/{q['question_id']}",
           json={"option_id": q["options"][0]["id"], "confidence": 3})
    chk = st.post(f"/api/student/attempts/{att['session_id']}/answers/{q['question_id']}/check").json()
    assert "correct_option_id" in chk
    locked = st.put(f"/api/student/attempts/{att['session_id']}/answers/{q['question_id']}",
                    json={"option_id": q["options"][1]["id"]})
    assert locked.status_code == 409
    res = st.post(f"/api/student/attempts/{att['session_id']}/submit").json()
    assert res["feedback_available"] and res["kind"] == "practice"
    m = st.get("/api/student/mastery").json()
    assert any(t["topic"] == "SQL joins" for t in m["topics"])
    # practice never appears in the lecturer's graded results
    assert course_setup["lec"].get("/api/lecturer/overview").json()["recent_submissions"] == 0


def test_mastery_needs_evidence_then_labels(course_setup):
    """Ten practice answers on one topic: the label appears only after 5 distinct questions."""
    st = course_setup["st"]
    labels = []
    for _ in range(2):
        r = st.post("/api/student/practice/generate", json={"subject": "OS", "topic": "Paging", "question_count": 5})
        run = wait_run(st, r.json()["run_id"])
        att = st.post(f"/api/student/quizzes/{run['quiz_id']}/start").json()
        for q in att["questions"]:
            st.put(f"/api/student/attempts/{att['session_id']}/answers/{q['question_id']}",
                   json={"option_id": q["options"][0]["id"]})
        res = st.post(f"/api/student/attempts/{att['session_id']}/submit").json()
        labels.append(res["topics"][0]["mastery_label"])
    assert labels[0] != "insufficient_evidence" or labels[1] != "insufficient_evidence"
    hist = st.get("/api/student/mastery/history", params={"topic_key": "p:os|paging"}).json()
    assert len(hist["points"]) == 2


def test_time_limit_auto_submits(course_setup, app):
    lec, st = course_setup["lec"], course_setup["st"]
    run = _draft(course_setup, 1)
    _approve_all(lec, run["quiz_id"])
    lec.patch(f"/api/lecturer/quizzes/{run['quiz_id']}", json={"time_limit_min": 1})
    lec.post(f"/api/lecturer/quizzes/{run['quiz_id']}/publish")
    att = st.post(f"/api/student/quizzes/{run['quiz_id']}/start").json()
    from app.models import QuizSession
    with app.state.db.session() as db:                      # move the deadline into the past
        s = db.get(QuizSession, att["session_id"])
        s.deadline_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        db.commit()
    r = st.put(f"/api/student/attempts/{att['session_id']}/answers/{att['questions'][0]['question_id']}",
               json={"option_id": att["questions"][0]["options"][0]["id"]})
    assert r.status_code == 409 and "Time is up" in r.json()["detail"]
    res = st.get(f"/api/student/attempts/{att['session_id']}/result").json()
    assert res["submitted_by"] == "time_limit" and res["unanswered"] == 1


def test_window_states(course_setup):
    lec, st = course_setup["lec"], course_setup["st"]
    run = _draft(course_setup, 1)
    _approve_all(lec, run["quiz_id"])
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    later = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    lec.patch(f"/api/lecturer/quizzes/{run['quiz_id']}", json={"opens_at": future, "due_at": later})
    assert lec.post(f"/api/lecturer/quizzes/{run['quiz_id']}/publish").status_code == 200
    assert st.get("/api/student/quizzes/assigned").json()[0]["state"] == "upcoming"
    assert st.post(f"/api/student/quizzes/{run['quiz_id']}/start").status_code == 409


def test_manual_export_and_forms_not_configured(course_setup):
    lec = course_setup["lec"]
    run = _draft(course_setup, 2)
    assert lec.get(f"/api/lecturer/quizzes/{run['quiz_id']}/export").status_code == 422     # not approved yet
    _approve_all(lec, run["quiz_id"])
    txt = lec.get(f"/api/lecturer/quizzes/{run['quiz_id']}/export").text
    assert "Answer:" in txt and "1." in txt
    r = lec.post(f"/api/lecturer/quizzes/{run['quiz_id']}/google-form")
    assert r.status_code == 503 and "not set up" in r.json()["detail"]
    assert lec.get("/api/integrations/google/status").json()["configured"] is False


def test_model_offline_blocks_generation(course_setup):
    from tests import fake_model_server
    fake_model_server.STATE["mode"] = "down"
    r = course_setup["st"].post("/api/student/practice/generate", json={"subject": "OS", "topic": "Paging"})
    assert r.status_code == 503
    fake_model_server.STATE["mode"] = "normal"


def test_one_generation_at_a_time_per_user(course_setup):
    st = course_setup["st"]
    r1 = st.post("/api/student/practice/generate", json={"subject": "OS", "topic": "Paging", "question_count": 20})
    r2 = st.post("/api/student/practice/generate", json={"subject": "OS", "topic": "Paging"})
    assert r1.status_code == 202 and r2.status_code == 429
    st.post(f"/api/generation/{r1.json()['run_id']}/cancel")
    assert wait_run(st, r1.json()["run_id"])["status"] in ("cancelled", "done", "partial")


def test_model_quality_counts_reliability_and_review(course_setup):
    lec = course_setup["lec"]
    run = _draft(course_setup, 3)
    quiz = lec.get(f"/api/lecturer/quizzes/{run['quiz_id']}").json()
    ids = [it["question"]["id"] for it in quiz["items"]]
    lec.post(f"/api/lecturer/questions/{ids[0]}/review", json={"action": "approve"})
    lec.post(f"/api/lecturer/questions/{ids[1]}/review", json={"action": "reject", "note": "off topic"})
    lec.patch(f"/api/lecturer/questions/{ids[2]}", json={"explanation": "Clearer explanation."})
    v = lec.get("/api/lecturer/model-quality").json()["versions"][0]
    assert (v["questions"], v["approved"], v["rejected"], v["pending"], v["edited"]) == (3, 1, 1, 1, 1)
    assert v["approval_rate"] == 0.5 and v["model_calls"] == run["attempts"] and v["passed_checks"] == 3
    assert v["pass_rate"] == round(3 / run["attempts"], 4) and v["rejected_by_check"]
    assert course_setup["st"].get("/api/lecturer/model-quality").status_code == 403
