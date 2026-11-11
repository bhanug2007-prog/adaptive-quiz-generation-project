"""Phase 4 agents: the Question Quality Agent's step log and the Lecturer Insights Agent (tool choice,
checks on the AI's plan and answer, fallbacks, privacy, permissions, read-only). Uses the TEST-ONLY fake
model and fake Grok servers, never the real services."""
import json
import os

import pytest

from app.agents.insight_tools import TOOLS
from app.agents.insights import ungrounded_numbers
from app.core.config import Settings
from app.core.security import LoginLimiter
from tests import fake_grok_server, fake_model_server
from tests.conftest import INVITE, _free_port, register, wait_run

GROK_KEY = "xai-test-key-never-shown-456"


@pytest.fixture(scope="session")
def grok_port():
    port = _free_port()
    srv = fake_grok_server.start(port)
    yield port
    srv.shutdown()


@pytest.fixture
def settings(tmp_path, model_port, grok_port):          # overrides conftest: same, plus the fake Grok
    fake_grok_server.reset("pass")
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test.db'}"
    return Settings(_env_file=None, environment="test", database_url=url,
                    model_base_url=f"http://127.0.0.1:{model_port}", lecturer_invite_code=INVITE,
                    secret_key="test-secret-" + "x" * 40, math_check=True, require_email_verification=False,
                    quality_check=False,               # generation in these tests does not use Grok
                    grok_api_key=GROK_KEY, grok_base_url=f"http://127.0.0.1:{grok_port}", grok_model="grok-test",
                    grok_timeout_s=0.5, grok_cooldown_s=300)


def _publish(cs, n=4):
    lec = cs["lec"]
    fake_model_server.STATE["mode"] = "clean"
    body = {"course_id": cs["course"]["id"], "subject_id": cs["subject"]["id"], "topic_id": cs["topic"]["id"],
            "title": "Scheduling quiz 1", "question_count": n, "difficulty": "mixed"}
    r = lec.post("/api/lecturer/generate", json=body)
    assert r.status_code == 202, r.text
    run = wait_run(lec, r.json()["run_id"], timeout=60)
    qid = run["quiz_id"]
    for it in lec.get(f"/api/lecturer/quizzes/{qid}").json()["items"]:
        assert lec.post(f"/api/lecturer/questions/{it['question']['id']}/review", json={"action": "approve"}).status_code == 200
    lec.patch(f"/api/lecturer/quizzes/{qid}", json={"contribution_pct": 10})
    assert lec.post(f"/api/lecturer/quizzes/{qid}/publish").status_code == 200
    return run, qid


def _take(cs, client, qid, pattern):
    """pattern: one of True (right), False (wrong), None (skip) per question."""
    full = {it["question"]["id"]: it["question"] for it in cs["lec"].get(f"/api/lecturer/quizzes/{qid}").json()["items"]}
    att = client.post(f"/api/student/quizzes/{qid}/start").json()
    sid = att["session_id"]
    for q, choose in zip(att["questions"], pattern):
        if choose is None:
            continue
        oid = next(o["id"] for o in full[q["question_id"]]["options"] if o["is_correct"] == choose)
        assert client.put(f"/api/student/attempts/{sid}/answers/{q['question_id']}",
                          json={"option_id": oid, "time_spent_s": 10}).status_code == 200
    assert client.post(f"/api/student/attempts/{sid}/submit").status_code == 200


@pytest.fixture
def klass(course_setup):
    """Three students (Asha Rao, Ravi Kumar, Student One) who took one published quiz."""
    cs = course_setup
    run, qid = _publish(cs)
    students = {}
    for name, email in (("Ravi Kumar", "ravi.kumar.private@gmail.com"), ("Asha Rao", "asha.rao.private@gmail.com")):
        c = cs["make_client"]()
        register(c, "student", email=email, name=name)
        assert c.post("/api/student/courses/join", json={"join_code": cs["course"]["join_code"]}).status_code == 200
        students[name] = c
    _take(cs, cs["st"], qid, [True, False, None, True])
    _take(cs, students["Ravi Kumar"], qid, [True, True, True, True])
    _take(cs, students["Asha Rao"], qid, [False, False, False, None])
    fake_grok_server.reset("pass")
    return {**cs, "quiz_id": qid, "run": run}


def _ask(cs, question, quiz_id=None, status=200):
    r = cs["lec"].post("/api/lecturer/insights/ask", json={"course_id": cs["course"]["id"], "quiz_id": quiz_id,
                                                           "question": question})
    assert r.status_code == status, r.text
    return r.json()


def _steps(cs, run_id):
    return cs["lec"].get(f"/api/lecturer/agent-runs/{run_id}").json()


def _plan(*tools, reason="Picked for the question."):
    return json.dumps({"tools": [{"name": t, "args": a} for t, a in tools], "reason": reason})


def _answer(answer, findings=(), suggestions=(), caveats=()):
    return json.dumps({"answer": answer, "findings": list(findings), "suggestions": list(suggestions),
                       "caveats": list(caveats)})


# ---------- Question Quality Agent ----------

def test_generation_agent_logs_tools_and_decisions_and_never_publishes(course_setup):
    lec = course_setup["lec"]
    fake_model_server.STATE.update(mode="normal", n=0)     # every 5th reply broken, one wrong maths key
    body = {"course_id": course_setup["course"]["id"], "subject_id": course_setup["subject"]["id"],
            "topic_id": course_setup["topic"]["id"], "title": "Agent quiz", "question_count": 5, "difficulty": "mixed"}
    run = wait_run(lec, lec.post("/api/lecturer/generate", json=body).json()["run_id"], timeout=60)
    log = lec.get(f"/api/lecturer/generation/{run['run_id']}/agent").json()
    assert log["agent"] == "question_quality" and log["status"] == run["status"]
    names = [s["name"] for s in log["steps"]]
    assert names[0] == "prepare_contexts" and "plan" in names
    for tool in ("generate_questions", "validate_question", "check_duplicate_questions", "save_question_draft",
                 "check_difficulty_distribution", "get_generation_status"):
        assert tool in names, tool
    assert names[-1] == "await_lecturer_approval"
    assert "regenerate_question" in names and "retry" in names          # the broken reply / wrong key was retried
    retry = next(s for s in log["steps"] if s["name"] == "retry")
    assert "Only this question" in retry["result"]["because"] or "unusable" in retry["result"]["because"]
    # never more than 3 tries for one question
    tries = [s["args"]["try"] for s in log["steps"] if s["name"] in ("generate_questions", "regenerate_question")]
    assert max(tries) <= 3
    assert not any("publish" in n for n in names)
    quiz = lec.get(f"/api/lecturer/quizzes/{run['quiz_id']}").json()
    assert quiz["status"] == "draft"
    assert all(it["question"]["review_status"] != "approved" for it in quiz["items"])
    saved = [s for s in log["steps"] if s["name"] == "save_question_draft"]
    assert len(saved) == len(quiz["items"])


def test_generation_agent_log_is_owner_only(course_setup):
    lec = course_setup["lec"]
    fake_model_server.STATE["mode"] = "clean"
    body = {"course_id": course_setup["course"]["id"], "subject_id": course_setup["subject"]["id"],
            "topic_id": course_setup["topic"]["id"], "title": "Agent quiz", "question_count": 5, "difficulty": "easy"}
    run = wait_run(lec, lec.post("/api/lecturer/generate", json=body).json()["run_id"], timeout=60)
    other = course_setup["make_client"]()
    register(other, "lecturer")
    assert other.get(f"/api/lecturer/generation/{run['run_id']}/agent").status_code == 404
    assert course_setup["st"].get(f"/api/lecturer/generation/{run['run_id']}/agent").status_code == 403
    rid = lec.get(f"/api/lecturer/generation/{run['run_id']}/agent").json()["id"]
    assert other.get(f"/api/lecturer/agent-runs/{rid}").status_code == 404


# ---------- Lecturer Insights Agent: without Grok ----------

def test_without_grok_the_keyword_router_and_templates_answer_from_real_numbers(klass, app):
    app.state.quality.client = None                     # as with an empty GROK_API_KEY
    out = _ask(klass, "How is the class doing overall?")
    assert out["mode"] == "rules" and "GROK_API_KEY" in out["ai_note"] and out["model"] is None
    assert [t["name"] for t in out["tools_used"]] == ["get_class_analytics"]
    perf = klass["lec"].get(f"/api/lecturer/courses/{klass['course']['id']}/analytics").json()
    assert f"{perf['average']}%" in out["answer"] and f"{perf['submissions']} submissions" in out["answer"]
    assert fake_grok_server.STATE["calls"] == 0
    log = _steps(klass, out["agent_run_id"])
    assert log["llm_calls"] == 0 and log["status"] == "done"
    assert [s["name"] for s in log["steps"]] == ["route_by_keywords", "get_class_analytics"]


def test_without_grok_students_are_named_for_the_lecturer(klass, app):
    app.state.quality.client = None
    out = _ask(klass, "Which students need support?")
    assert [t["name"] for t in out["tools_used"]] == ["get_student_performance"]
    text = " ".join([out["answer"], *out["findings"], *out["suggestions"]])
    assert "Asha Rao" in text and "Student 1" not in text


def test_topics_with_little_evidence_are_called_out(klass, app):
    app.state.quality.client = None
    klass["lec"].post(f"/api/lecturer/units/{klass['unit']['id']}/topics", json={"name": "Deadlocks"})   # no answers
    out = _ask(klass, "Which topics are weak?")
    assert "get_topic_mastery" in [t["name"] for t in out["tools_used"]]
    # CPU Scheduling has 10 answered questions (judged); Deadlocks has none (not judged)
    assert any(f.startswith("CPU Scheduling:") and "over 10 answers" in f for f in [out["answer"], *out["findings"]])
    assert "1 of 2 topics have fewer than 10 answers, so they are not judged (insufficient evidence)." in out["caveats"]
    assert not any("cheat" in x.lower() for x in out["findings"] + out["suggestions"])


# ---------- with Grok ----------

def test_ai_plan_and_grounded_answer_with_names_kept_away_from_grok(klass):
    fake_grok_server.STATE["script"] = [
        _plan(("get_student_performance", {})),
        _answer("Student 2 did best and Student 1 needs support; 3 students took the quiz.",
                findings=["Student 1 answered no question correctly."], suggestions=["Check in with Student 1."]),
    ]
    out = _ask(klass, "How are Ravi Kumar and asha rao (asha.rao.private@gmail.com) doing?")
    assert out["mode"] == "ai" and out["model"] == "grok-test" and out["ai_note"] is None
    assert out["answer"] == "Ravi Kumar did best and Asha Rao needs support; 3 students took the quiz."
    assert out["suggestions"] == ["Check in with Asha Rao."]
    sent = json.dumps(fake_grok_server.STATE["bodies"])
    for private in ("Ravi", "Asha", "Student One", "private@gmail.com", "@gmail.com"):
        assert private not in sent, private
    assert "Student 2" in sent and "[email]" in sent
    assert fake_grok_server.STATE["auth"][0] == f"Bearer {GROK_KEY}"
    names = [s["name"] for s in _steps(klass, out["agent_run_id"])["steps"]]
    assert names == ["plan_tools", "use_ai_plan", "get_student_performance", "write_answer", "accept_answer"]


def test_invented_numbers_are_rejected_and_the_template_answer_is_shown(klass):
    fake_grok_server.STATE["script"] = [_plan(("get_class_analytics", {})),
                                        _answer("The class average is 73.4%, up 12 points.")]
    out = _ask(klass, "What is the class average?")
    assert out["mode"] == "rules" and "not in the data" in out["ai_note"]
    assert "73.4" not in out["answer"]
    log = _steps(klass, out["agent_run_id"])
    rej = next(s for s in log["steps"] if s["name"] == "reject_answer")
    assert "73.4" in rej["result"]["because"]


def test_unknown_student_labels_and_cheating_claims_are_rejected(klass):
    fake_grok_server.STATE["script"] = [_plan(("get_student_performance", {})), _answer("Student 9 is behind.")]
    assert _ask(klass, "Who is behind?")["mode"] == "rules"
    fake_grok_server.STATE["script"] = [_plan(("get_student_performance", {})),
                                        _answer("Student 2 probably cheated on the quiz.")]
    out = _ask(klass, "Who did best?")
    assert out["mode"] == "rules" and "cheat" not in json.dumps(out).lower()


def test_plan_with_unknown_tools_or_other_courses_quizzes_is_refused(klass):
    fake_grok_server.STATE["script"] = [
        _plan(("delete_quiz", {"quiz_id": klass["quiz_id"]}), ("get_class_analytics", {"quiz_id": 999999}),
              ("get_topic_mastery", {"student_id": 5})),
        _answer("Here is the topic picture."),
    ]
    out = _ask(klass, "Tell me about topics")
    log = _steps(klass, out["agent_run_id"])
    refused = [s for s in log["steps"] if s["name"] in ("refuse_tool", "refuse_args")]
    assert [s["name"] for s in refused] == ["refuse_tool", "refuse_tool", "refuse_args"]
    assert [t["name"] for t in out["tools_used"]] == ["get_topic_mastery"]
    assert out["tools_used"][0]["args"] == {}


def test_at_most_three_tools_run(klass):
    fake_grok_server.STATE["script"] = [
        _plan(*[(t, {}) for t in ("get_class_analytics", "get_topic_mastery", "get_question_statistics",
                                  "get_student_performance", "get_assessment_results")]),
        _answer("A summary."),
    ]
    out = _ask(klass, "Give me everything")
    assert len(out["tools_used"]) == 3
    assert "limit_tools" in [s["name"] for s in _steps(klass, out["agent_run_id"])["steps"]]


def test_unreadable_plan_falls_back_to_keywords_but_still_words_the_answer(klass):
    fake_grok_server.STATE["script"] = ["Sure! I'd use some tools.", _answer("Scores are listed by quiz.")]
    out = _ask(klass, "Show the quiz results")
    assert out["mode"] == "ai" and [t["name"] for t in out["tools_used"]] == ["get_assessment_results"]
    names = [s["name"] for s in _steps(klass, out["agent_run_id"])["steps"]]
    assert names[:2] == ["plan_tools", "route_by_keywords"]


def test_quota_error_pauses_grok_and_the_next_question_uses_no_calls(klass):
    fake_grok_server.STATE["script"] = [(429, {"error": "You have exhausted your monthly quota"})]
    out = _ask(klass, "How is the class doing?")
    assert out["mode"] == "rules" and "quota" in out["ai_note"]
    calls = fake_grok_server.STATE["calls"]
    out2 = _ask(klass, "How is the class doing?")
    assert out2["mode"] == "rules" and "paused" in out2["ai_note"].lower()
    assert fake_grok_server.STATE["calls"] == calls


def test_off_topic_question_runs_no_tools(klass):
    fake_grok_server.STATE["script"] = [json.dumps({"tools": [], "reason": "Not about the course."})]
    out = _ask(klass, "What is the weather in Dharwad?")
    assert out["tools_used"] == [] and "only answer questions about this course" in out["answer"]


def test_insights_ai_switch_off_uses_no_grok(klass, app):
    app.state.quality.s = app.state.quality.s.model_copy(update={"insights_ai": False})
    klass["lec"].app.dependency_overrides = {}
    from app.core.deps import get_settings_dep
    app.dependency_overrides[get_settings_dep] = lambda: app.state.quality.s
    try:
        out = _ask(klass, "How is the class doing?")
    finally:
        app.dependency_overrides.clear()
    assert out["mode"] == "rules" and "INSIGHTS_AI" in out["ai_note"] and fake_grok_server.STATE["calls"] == 0


# ---------- safety ----------

def test_permissions(klass):
    other = klass["make_client"]()
    register(other, "lecturer")
    body = {"course_id": klass["course"]["id"], "question": "How is the class doing?"}
    assert other.post("/api/lecturer/insights/ask", json=body).status_code == 404
    assert klass["st"].post("/api/lecturer/insights/ask", json=body).status_code == 403
    mine = other.post("/api/lecturer/courses", json={"code": "X1", "title": "Other"}).json()
    r = other.post("/api/lecturer/insights/ask", json={"course_id": mine["id"], "quiz_id": klass["quiz_id"],
                                                       "question": "How did this quiz go?"})
    assert r.status_code == 404                          # a quiz from someone else's course
    out = _ask(klass, "How did this quiz go?", quiz_id=klass["quiz_id"])
    assert other.get(f"/api/lecturer/agent-runs/{out['agent_run_id']}").status_code == 404
    hist = klass["lec"].get(f"/api/lecturer/insights/history?course_id={klass['course']['id']}").json()
    assert hist[0]["id"] == out["agent_run_id"] and "steps" not in hist[0]
    assert other.get(f"/api/lecturer/insights/history?course_id={klass['course']['id']}").status_code == 404


def test_the_agent_is_read_only(klass, app):
    lec, cid = klass["lec"], klass["course"]["id"]
    before = (lec.get(f"/api/lecturer/quizzes/{klass['quiz_id']}").json(),
              lec.get(f"/api/lecturer/courses/{cid}/analytics").json())
    fake_grok_server.STATE["script"] = [_plan(("create_lecturer_report", {})), _answer("A report.")]
    _ask(klass, "Write me a report")
    app.state.quality.client = None
    _ask(klass, "Write me a report")
    after = (lec.get(f"/api/lecturer/quizzes/{klass['quiz_id']}").json(),
             lec.get(f"/api/lecturer/courses/{cid}/analytics").json())
    assert before == after
    assert all(n.startswith(("get_", "create_lecturer_report")) for n in TOOLS)


def test_questions_are_rate_limited(klass, app):
    app.state.insights_limiter = LoginLimiter(2, 600)
    app.state.quality.client = None
    _ask(klass, "How is the class doing?")
    _ask(klass, "How is the class doing?")
    r = klass["lec"].post("/api/lecturer/insights/ask", json={"course_id": klass["course"]["id"],
                                                              "question": "And now?"})
    assert r.status_code == 429


def test_number_check():
    data = json.dumps({"average_pct": 66.7, "submissions": 3, "count": 1200, "title": "Quiz 2"})
    assert ungrounded_numbers(["Average 66.7% (about 67%) over 3 submissions and 1,200 answers in Quiz 2; Student 14 is fine."],
                              [data]) == []
    assert ungrounded_numbers(["Average 71%."], [data]) == ["71"]
    assert ungrounded_numbers(["Pass rate is 100%."], [data]) == ["100"]


# ---------- Phase C/E hardening: missing data, 0% guard, think blocks, single-name PII, audit scrubbing ----------

def test_missing_analytics_data_is_reported_explicitly(course_setup, app):
    lec = course_setup["lec"]
    empty_course = lec.post("/api/lecturer/courses", json={"code": "EMPTY101", "title": "Fresh Course"}).json()
    app.state.quality.client = None
    r = lec.post("/api/lecturer/insights/ask", json={"course_id": empty_course["id"], "question": "Give me an overview report"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["mode"] == "rules"
    combined = " ".join([out["answer"], *out["findings"], *out["caveats"]])
    assert "No submitted attempts yet" in combined
    assert "no published assessments yet" in combined.lower()
    assert "No students are enrolled" in combined

    # Course with an enrolled student & published quiz from klass setup, before anyone submits
    _, qid = _publish(course_setup, n=2)
    r2 = lec.post("/api/lecturer/insights/ask", json={"course_id": course_setup["course"]["id"], "quiz_id": qid,
                                                       "question": "Which students need support on this quiz?"})
    assert r2.status_code == 200, r2.text
    out2 = r2.json()
    assert out2["mode"] == "rules"
    combined2 = " ".join([out2["answer"], *out2["caveats"]])
    assert "no quiz submissions have been recorded yet" in combined2
    assert "1 student enrolled" in combined2


def test_ai_0_pct_hallucination_rejected_when_no_submissions_exist(course_setup):
    # Course with 0 published quizzes: completion_pct and score metrics are all null -> 0% must be rejected
    fake_grok_server.STATE["script"] = [
        _plan(("get_class_analytics", {})),
        _answer("The class average score is 0%."),
    ]
    out = _ask(course_setup, "How is the class doing?")
    assert out["mode"] == "rules"
    assert "not in the data" in out["ai_note"]
    assert "0%" not in out["answer"]
    names = [s["name"] for s in _steps(course_setup, out["agent_run_id"])["steps"]]
    assert "reject_answer" in names

    # Publish a quiz with 0 submissions: completion_pct is genuinely 0.0, score/accuracy metrics remain null
    _publish(course_setup, n=2)
    fake_grok_server.STATE["script"] = [
        _plan(("get_class_analytics", {})),
        _answer("The class average is 0%."),
    ]
    out_avg = _ask(course_setup, "How did the quiz go?")
    assert out_avg["mode"] == "rules" and "0%" not in out_avg["answer"]

    fake_grok_server.STATE["script"] = [
        _plan(("get_class_analytics", {})),
        _answer("No submissions have been recorded yet (0% completion)."),
    ]
    out2 = _ask(course_setup, "What is the completion?")
    assert out2["mode"] == "ai" and "0% completion" in out2["answer"]


def test_boolean_quiz_ids_refused_in_plan_and_think_wrapped_replies_work(klass):
    fake_grok_server.STATE["script"] = [
        "<think>Choosing tools and checking boolean {quiz_id}</think>\n```json\n"
        + _plan(("get_class_analytics", {"quiz_id": True}),
                ("get_assessment_results", {"quiz_id": False}),
                ("get_student_performance", {}))
        + "\n```",
        "<think>Formatting final answer...</think>\n```json\n"
        + _answer("Student 1 has a 0% score.")
        + "\n```",
    ]
    out = _ask(klass, "Who needs help?")
    assert out["mode"] == "ai"
    assert out["answer"] == "Asha Rao has a 0% score."
    assert [t["name"] for t in out["tools_used"]] == ["get_student_performance"]
    log = _steps(klass, out["agent_run_id"])
    refused = [s for s in log["steps"] if s["name"] == "refuse_tool"]
    assert len(refused) == 2


def test_single_first_name_pii_and_secrets_never_reach_llm_or_audit_logs(klass):
    fake_grok_server.STATE["script"] = [
        _plan(("get_student_performance", {})),
        _answer("Student 1 is struggling and needs help."),
    ]
    out = _ask(klass, "How is Asha doing right now?")
    assert out["mode"] == "ai"
    assert out["answer"] == "Asha Rao is struggling and needs help."

    sent = json.dumps(fake_grok_server.STATE["bodies"])
    assert "Asha" not in sent and "asha" not in sent and "Ravi" not in sent
    assert "Student 1" in sent

    run_log = _steps(klass, out["agent_run_id"])
    raw_log = json.dumps(run_log)
    assert "Asha" not in raw_log and "asha" not in raw_log and "Ravi" not in raw_log
    assert GROK_KEY not in raw_log and "@gmail.com" not in raw_log
    assert "Student 1" in json.dumps(run_log["input"])

    # Auth/404 error pauses LLM immediately without calling write_answer, and never logs API keys
    fake_grok_server.reset("model_not_found")
    out_err = _ask(klass, f"Why did Bearer {GROK_KEY} fail?")
    assert out_err["mode"] == "rules"
    assert fake_grok_server.STATE["calls"] == 1
    assert "GROK_MODEL" in out_err["ai_note"]
    err_log = json.dumps(_steps(klass, out_err["agent_run_id"]))
    assert GROK_KEY not in err_log
    assert "[redacted]" in err_log


def test_empty_answer_falls_back_to_rules_safely(klass):
    fake_grok_server.STATE["script"] = [_plan(("get_class_analytics", {})), "   \n  "]
    out = _ask(klass, "How is the class doing?")
    assert out["mode"] == "rules"
    assert "empty reply" in out["ai_note"] and "did not reply with JSON" in out["ai_note"]
    assert "%" in out["answer"]
