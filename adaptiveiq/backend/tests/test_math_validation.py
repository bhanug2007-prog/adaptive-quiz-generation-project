"""Regression tests for Windows-safe mathematical verification, restricted AST expression parsing,
isolated worker limits, fail-closed handling, Groq non-override, and generation draft safety."""
import math
import os

import pytest

from app.core.config import Settings
from app.services.quality_service import QualityEvaluator
from app.services.validation_service import Validator
from app.validators import mathcheck
from tests import fake_grok_server, fake_model_server
from tests.conftest import wait_run
from tests.test_quality import GROK_KEY, grok_port  # noqa: F401


class StubModel:
    def __init__(self, reply: str | list[str]):
        self.replies = [reply] if isinstance(reply, str) else list(reply)
        self.calls = 0

    def chat(self, *a, **k) -> str:
        idx = min(self.calls, len(self.replies) - 1)
        self.calls += 1
        return self.replies[idx]


def test_default_math_check_strict_is_true():
    s = Settings(_env_file=None, environment="development")
    assert s.math_check is True
    assert s.math_check_strict is True
    assert s.math_check_allow_without_os_limits is False


def test_restricted_expression_parser_handles_simple_math_without_worker(monkeypatch):
    val, err = mathcheck.eval_math_expression("round(2 / math.sqrt(4 + 12), 2)")
    assert err is None and val == 0.5

    # Simple expressions must NEVER invoke the Python code execution worker
    monkeypatch.setattr(mathcheck, "run_code", lambda *a, **k: (_ for _ in ()).throw(AssertionError("worker should not be called")))
    mcq = {
        "question": "A radar has PRF 10 kHz. What is its maximum unambiguous range?",
        "options": ["1.5 km", "15 km", "150 km", "1500 km"],
        "answer": "B",
        "explanation": "R = c/(2 PRF) = 15 km.",
    }
    res = mathcheck.math_check(mcq, lambda m: "```python\nc = 3e8\nprf = 10e3\nanswer = c / (2 * prf) / 1000\n```")
    assert res["status"] == "verified" and res["accept"] is True and res["method"] == "expression_parser"


def test_correct_mathematical_answer_both_tiers(settings):
    raw = ("question: An SVM hyperplane has ||w|| = 2. What is the full margin width? "
           "options: (A) 0.5 (B) 1 (C) 2 (D) 4 answer: B explanation: width = 2 / 2 = 1.")
    r1 = Validator(settings, StubModel("```python\nanswer = 2 / 2\n```")).check(raw, [])
    assert r1.ok and r1.math_verified and r1.info["math_status"] == "verified"
    assert r1.info["math_method"] == "expression_parser"

    raw2 = ("question: What is 1/2 + 1/4? options: (A) 0.25 (B) 0.5 (C) 0.75 (D) 1.0 "
            "answer: C explanation: 1/2 + 1/4 = 0.75.")
    r2 = Validator(settings, StubModel("```python\nfrom fractions import Fraction\nanswer = float(Fraction(1, 2) + Fraction(1, 4))\n```")).check(raw2, [])
    assert r2.ok and r2.math_verified and r2.info["math_status"] == "verified"
    assert r2.info["math_method"] == "isolated_worker"


def test_incorrect_answer_key_rejected(settings):
    raw = ("question: An SVM hyperplane has w = (2, 3). What is the margin width? "
           "options: (A) 0.4 (B) 0.55 (C) 0.8 (D) 1.0 answer: A "
           "explanation: 2 / sqrt(13) is 0.4.")
    # Note: deliberately make explanation agree with wrong key so numeric_conflict does not hide math_wrong_key
    res = Validator(settings, StubModel("```python\nimport math\nanswer = 2 / math.sqrt(4 + 9)\n```")).check(raw, [])
    assert not res.ok and res.reason == "math_wrong_key"
    assert res.math_verified is False and res.info["math_status"] == "wrong_key"


def test_no_correct_option_rejected(settings):
    raw = ("question: Compute margin width for ||w|| = 2.5. "
           "options: (A) 0.2 (B) 0.4 (C) 0.5 (D) 1.2 answer: C "
           "explanation: 2 / 2.5 = 0.5.")
    # Make calculation yield 0.8 (matches none of A-D) and check no_match
    res = Validator(settings, StubModel("```python\nanswer = 2 / 2.5\n```")).check(raw, [])
    assert not res.ok and res.reason == "math_no_match"
    assert res.math_verified is False and res.info["math_status"] == "no_match"


def test_ambiguous_numerical_answer_rejected(settings):
    # Case 1: two distinct options within 2% tolerance
    raw_tol = ("question: Compute 2 / 0.2. options: (A) 10.0 (B) 10.1 (C) 20.0 (D) 30.0 "
               "answer: A explanation: 2 / 0.2 = 10.0.")
    res_tol = Validator(settings, StubModel("```python\nanswer = 2 / 0.2\n```")).check(raw_tol, [])
    assert not res_tol.ok and res_tol.reason == "math_ambiguous"

    # Case 2: decimal and equivalent percentage both present
    raw_pct = ("question: What is 1/2 as a ratio? options: (A) 0.5 (B) 50% (C) 0.25 (D) 0.1 "
               "answer: A explanation: 1/2 = 0.5.")
    res_pct = Validator(settings, StubModel("```python\nanswer = 1 / 2\n```")).check(raw_pct, [])
    assert not res_pct.ok and res_pct.reason == "math_ambiguous"

    # Case 3: multi-value solver return does not crash and marks ambiguous
    res_multi = Validator(settings, StubModel("```python\nanswer = [10, 20]\n```")).check(raw_tol, [])
    assert not res_multi.ok and res_multi.reason == "math_ambiguous"

    # Case 4: ambiguous range option rejected by option_value and flagged if overlapping
    assert mathcheck.option_value("10 - 20 km") is None
    assert mathcheck.option_value("10 or 20") is None
    raw_range = ("question: What is 3 * 5? options: (A) 10 - 20 (B) 15 (C) 30 (D) 40 "
                 "answer: B explanation: 3 * 5 = 15.")
    res_range = Validator(settings, StubModel("```python\nanswer = 3 * 5\n```")).check(raw_range, [])
    assert not res_range.ok and res_range.reason == "math_ambiguous"


@pytest.mark.parametrize("bad_expr", [
    "9**9**9",
    "math.factorial(10000)",
    "math.exp(1000)",
    "1 << 10000",
    "eval('2+2')",
    "__import__('os')",
    "1 + 2j",
    "+".join(["1"] * 300),
])
def test_unsupported_and_unsafe_expressions_rejected(bad_expr, settings):
    val, err = mathcheck.eval_math_expression(bad_expr)
    assert val is None and err

    raw = ("question: Compute 2 + 2. options: (A) 2 (B) 3 (C) 4 (D) 5 "
           "answer: C explanation: 2 + 2 = 4.")
    res = Validator(settings, StubModel(f"```python\nanswer = {bad_expr}\n```")).check(raw, [])
    assert not res.ok and res.reason == "math_unsupported"
    assert res.math_verified is False

    # Unsupported expression also fails closed even if math_check_strict=False
    permissive = Validator(settings.model_copy(update={"math_check_strict": False}), StubModel("```python\nimport sympy\nanswer = 4\n```")).check(raw, [])
    assert not permissive.ok and permissive.reason == "math_unsupported"


def test_timeout_and_unavailable_worker_fail_closed(monkeypatch, settings):
    mcq = {
        "question": "Compute the constrained sum.",
        "options": ["10", "20", "30", "40"],
        "answer": "B",
        "explanation": "equals 20.",
    }

    # 1. Timeout fails closed
    timed = mathcheck.math_check(
        mcq,
        lambda m: "```python\nanswer = sum(range(10**12))\n```",
        tries=1,
        allow_unchecked=True,
        worker_timeout=1,
    )
    assert timed["status"] == "unchecked" and timed["accept"] is False
    assert "timed out" in timed["errors"]

    # 2. Unavailable worker refuses subprocess launch and fails closed
    monkeypatch.setattr(mathcheck.subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("worker must not execute")))
    monkeypatch.setattr(mathcheck.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("worker must not execute")))
    raw = ("question: Compute sum 1..5. options: (A) 10 (B) 15 (C) 20 (D) 25 "
           "answer: B explanation: sum is 15.")
    monkeypatch.setattr("app.services.validation_service.can_run_safely", lambda allow=False: False)
    res = Validator(settings, StubModel("```python\ntotal = 0\nfor i in range(1, 6):\n    total += i\nanswer = total\n```")).check(raw, [])
    assert not res.ok and res.reason == "math_unchecked"

    # 3. Runtime failure initializing Windows Job Object also fails closed without spawning Python
    if os.name == "nt":
        monkeypatch.setattr("app.services.validation_service.can_run_safely", lambda allow=False: True)
        monkeypatch.setattr(mathcheck, "can_run_safely", lambda allow=False: True)
        monkeypatch.setattr(mathcheck, "_run_windows_isolated", lambda *a, **k: (_ for _ in ()).throw(OSError("job failed")))
        res_job = Validator(settings, StubModel("```python\ntotal = 0\nfor i in range(1, 6):\n    total += i\nanswer = total\n```")).check(raw, [])
        assert not res_job.ok and res_job.reason == "math_unchecked"


def test_high_groq_score_cannot_override_failed_math(course_setup, app, grok_port):  # noqa: F811
    fake_grok_server.reset("pass")
    s_with_ai = app.state.quality.s.model_copy(update={
        "grok_api_key": GROK_KEY,
        "grok_base_url": f"http://127.0.0.1:{grok_port}",
        "grok_model": "grok-test",
        "grok_timeout_s": 0.5,
        "grok_cooldown_s": 300,
    })
    ev = QualityEvaluator(s_with_ai)
    try:
        mcq = {
            "question": "A radar has PRF 10 kHz. What is its maximum unambiguous range?",
            "options": ["1.5 km", "15 km", "150 km", "1500 km"],
            "answer": "C",
            "explanation": "R = c/(2 PRF) = 150 km.",
        }
        q_res = ev.evaluate(mcq, "Networks", "Radar", "medium", rules_info={"math_status": "wrong_key"})
        assert q_res.evaluator == "grok" and q_res.score == 88.0
        assert q_res.passed is False and q_res.reason == "math_wrong_key"
    finally:
        ev.close()

    # Full API flow: kept draft with math_wrong_key cannot be cleared by Check again even when Grok passes it
    old_quality = app.state.quality
    old_gen_quality = app.state.generation.quality
    app.state.quality = QualityEvaluator(s_with_ai)
    app.state.generation.quality = app.state.quality
    try:
        lec = course_setup["lec"]
        orig_chat = app.state.model.chat

        def math_bad_chat(messages, **kwargs):
            sys_m = messages[0]["content"]
            if "Python" in sys_m:
                return "```python\nanswer = 3e8/(2*10e3)/1000\n```"
            if "subtopics" in messages[-1]["content"]:
                return "Radar range calculation"
            if "study notes" in messages[-1]["content"]:
                return ("Radar range physics unambiguous PRF calculation notes " * 12).strip()
            return ("question: A radar has PRF 10 kHz. What is its maximum unambiguous range? "
                    "options: (A) 1.5 km (B) 15 km (C) 150 km (D) 1500 km answer: C explanation: R = c/(2 PRF) = 150 km.")

        app.state.model.chat = math_bad_chat
        try:
            r = lec.post("/api/lecturer/generate", json={
                "course_id": course_setup["course"]["id"],
                "subject_id": course_setup["subject"]["id"],
                "topic_id": course_setup["topic"]["id"],
                "title": "Math check quiz",
                "question_count": 1,
                "difficulty": "medium",
            })
            assert r.status_code == 202
            run = wait_run(lec, r.json()["run_id"], timeout=30)
            assert run["status"] == "partial" and run["quality"]["failed_kept"] == 1
            q = lec.get(f"/api/lecturer/quizzes/{run['quiz_id']}").json()["items"][0]["question"]
            assert q["review_status"] == "draft"
            assert q["validation"]["failed_validation"] is True
            assert q["validation"]["failure_reason"] == "math_wrong_key"

            # Re-running check-quality with high Groq score must NOT clear failed math check
            fake_grok_server.reset("pass")
            recheck = lec.post(f"/api/lecturer/questions/{q['id']}/check-quality")
            assert recheck.status_code == 200
            v = recheck.json()["validation"]
            assert v["failed_validation"] is True and v["failure_reason"] == "math_wrong_key"
            assert v["math_verified"] is False
        finally:
            app.state.model.chat = orig_chat
    finally:
        app.state.quality.close()
        app.state.quality = old_quality
        app.state.generation.quality = old_gen_quality


def test_generation_workflow_never_auto_approves_or_publishes_unchecked_math(course_setup, app, monkeypatch):
    lec, st = course_setup["lec"], course_setup["st"]
    orig_chat = app.state.model.chat
    monkeypatch.setattr("app.services.validation_service.can_run_safely", lambda allow=False: False)

    def unchecked_loop_model(messages, **kwargs):
        sys_m = messages[0]["content"]
        if "Python" in sys_m:
            return "```python\ntotal = 0\nfor i in range(1, 5):\n    total += i\nanswer = total\n```"
        if "B.Tech lecturer" in sys_m and "subtopics" in messages[-1]["content"]:
            return "Series calculation"
        if "B.Tech lecturer" in sys_m and "study notes" in messages[-1]["content"]:
            return ("Series summation arithmetic formula practice reference material " * 12).strip()
        return ("question: What is the sum 1+2+3+4? options: (A) 5 (B) 10 (C) 15 (D) 20 "
                "answer: B explanation: sum = 10.")

    app.state.model.chat = unchecked_loop_model
    try:
        # Lecturer draft: never auto-approved, flagged failed_validation=True with math_unchecked
        r = lec.post("/api/lecturer/generate", json={
            "course_id": course_setup["course"]["id"],
            "subject_id": course_setup["subject"]["id"],
            "topic_id": course_setup["topic"]["id"],
            "title": "Unchecked draft test",
            "question_count": 1,
            "difficulty": "easy",
        })
        run = wait_run(lec, r.json()["run_id"], timeout=30)
        assert run["status"] == "partial" and run["ready"] == 0 and run["quality"]["failed_kept"] == 1
        quiz = lec.get(f"/api/lecturer/quizzes/{run['quiz_id']}").json()
        assert quiz["status"] == "draft"
        q = quiz["items"][0]["question"]
        assert q["review_status"] == "draft"
        assert q["validation"]["failed_validation"] is True
        assert q["validation"]["failure_reason"] == "math_unchecked"
        assert q["validation"]["math_verified"] is False
        assert lec.post(f"/api/lecturer/questions/{q['id']}/review", json={"action": "approve"}).status_code == 422
        assert lec.post(f"/api/lecturer/quizzes/{run['quiz_id']}/publish").status_code == 422

        # Student practice: never saves or auto-publishes unchecked numerical question (even if math_check_strict=False)
        app.state.generation.s = app.state.generation.s.model_copy(update={"math_check_strict": False})
        app.state.generation.validator.s = app.state.generation.s
        pr = st.post("/api/student/practice/generate", json={
            "subject": "Math",
            "topic": "Series",
            "question_count": 5,
        })
        assert pr.status_code == 202, pr.text
        pr_run = wait_run(st, pr.json()["run_id"], timeout=30)
        assert pr_run["status"] == "failed" and pr_run["ready"] == 0
        from app.models import Question as QuestionModel, Quiz as QuizModel
        with app.state.db.session() as db:
            pr_quiz = db.get(QuizModel, pr_run["quiz_id"])
            assert pr_quiz is not None and pr_quiz.status == "archived" and len(pr_quiz.items) == 0
            assert db.query(QuestionModel).filter(QuestionModel.generation_run_id == pr_run["run_id"]).count() == 0
    finally:
        app.state.model.chat = orig_chat


def test_failed_and_unchecked_numerical_drafts_cannot_be_approved_or_published(course_setup, app):
    lec = course_setup["lec"]
    orig_chat = app.state.model.chat

    def radar_model(messages, **kwargs):
        sys_m = messages[0]["content"]
        if "Python" in sys_m:
            return "```python\nanswer = 3e8 / (2 * 10e3) / 1000\n```"
        if "subtopics" in messages[-1]["content"]:
            return "Radar unambiguous range"
        if "study notes" in messages[-1]["content"]:
            return ("Radar PRF maximum unambiguous range physics formula practice reference " * 12).strip()
        return ("question: A radar has PRF 10 kHz. What is its maximum unambiguous range? "
                "options: (A) 1.5 km (B) 15 km (C) 150 km (D) 1500 km answer: C explanation: R = c/(2 PRF) = 150 km.")

    app.state.model.chat = radar_model
    try:
        r = lec.post("/api/lecturer/generate", json={
            "course_id": course_setup["course"]["id"],
            "subject_id": course_setup["subject"]["id"],
            "topic_id": course_setup["topic"]["id"],
            "title": "Blocked math quiz",
            "question_count": 1,
            "difficulty": "medium",
        })
        assert r.status_code == 202, r.text
        run = wait_run(lec, r.json()["run_id"], timeout=30)
        assert run["status"] == "partial" and run["quality"]["failed_kept"] == 1
        quiz_id = run["quiz_id"]
        q = lec.get(f"/api/lecturer/quizzes/{quiz_id}").json()["items"][0]["question"]
        qid = q["id"]
        assert q["review_status"] == "draft"
        assert q["validation"]["math_status"] == "wrong_key"
        assert q["validation"]["failure_reason"] == "math_wrong_key"

        # 1. Lecturer draft with failed math cannot be approved or published
        ap1 = lec.post(f"/api/lecturer/questions/{qid}/review", json={"action": "approve"})
        assert ap1.status_code == 422, ap1.text
        assert lec.post(f"/api/lecturer/quizzes/{quiz_id}/publish").status_code == 422

        # 2. Even if an approved row has unchecked or missing math verification, publish stays blocked
        from app.models import Question as QuestionModel
        with app.state.db.session() as db:
            row = db.get(QuestionModel, qid)
            saved_validation = dict(row.validation or {})
            row.review_status = "approved"
            row.validation = {"math_verified": False, "math_status": "unchecked"}
            db.commit()
        pub_legacy = lec.post(f"/api/lecturer/quizzes/{quiz_id}/publish")
        assert pub_legacy.status_code == 422, pub_legacy.text
        assert "mathematical verification" in pub_legacy.json()["detail"]

        with app.state.db.session() as db:
            row = db.get(QuestionModel, qid)
            row.validation = {}  # AI-generated numerical question missing math_status altogether
            db.commit()
        assert lec.post(f"/api/lecturer/quizzes/{quiz_id}/publish").status_code == 422

        with app.state.db.session() as db:
            row = db.get(QuestionModel, qid)
            row.review_status = "draft"
            row.validation = saved_validation
            db.commit()

        # 3. Editing content sets math_status="unchecked" and keeps approval/publish blocked until Check again
        edited = lec.patch(f"/api/lecturer/questions/{qid}", json={
            "correct_label": "B",
            "explanation": "R = c/(2 PRF) = 15 km.",
        })
        assert edited.status_code == 200
        assert edited.json()["review_status"] == "draft"
        assert edited.json()["validation"]["math_status"] == "unchecked"
        assert edited.json()["validation"]["math_verified"] is False
        assert lec.post(f"/api/lecturer/questions/{qid}/review", json={"action": "approve"}).status_code == 422
        assert lec.post(f"/api/lecturer/quizzes/{quiz_id}/publish").status_code == 422

        # 4. Re-checking verifies the corrected numerical question, allowing approval and publication
        checked = lec.post(f"/api/lecturer/questions/{qid}/check-quality")
        assert checked.status_code == 200, checked.text
        assert checked.json()["validation"]["math_status"] == "verified"
        assert checked.json()["validation"]["math_verified"] is True
        assert "failed_validation" not in checked.json()["validation"]

        assert lec.post(f"/api/lecturer/questions/{qid}/review", json={"action": "approve"}).status_code == 200
        assert lec.post(f"/api/lecturer/quizzes/{quiz_id}/publish").status_code == 200

        # 5. Editing after approval moves it back to draft + math_status="unchecked", blocking re-approval
        assert lec.post(f"/api/lecturer/quizzes/{quiz_id}/unpublish").status_code == 200
        re_edit = lec.patch(f"/api/lecturer/questions/{qid}", json={
            "text": "A radar operates with PRF 10 kHz. Compute its maximum unambiguous range.",
        })
        assert re_edit.status_code == 200
        assert re_edit.json()["review_status"] == "draft"
        assert re_edit.json()["validation"]["math_status"] == "unchecked"
        assert lec.post(f"/api/lecturer/questions/{qid}/review", json={"action": "approve"}).status_code == 422

        # Rejecting an unverified numerical draft remains allowed
        assert lec.post(f"/api/lecturer/questions/{qid}/review", json={"action": "reject", "note": "needs review"}).status_code == 200
        assert lec.post(f"/api/lecturer/quizzes/{quiz_id}/publish").status_code == 422
    finally:
        app.state.model.chat = orig_chat
