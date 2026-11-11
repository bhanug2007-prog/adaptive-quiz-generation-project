"""Question quality review (Phase 3): the AI reviewer, its fallback, retries, kept failures and the
difficulty mix check. Uses the TEST-ONLY fake model and fake Grok servers, never the real services."""
import json
import os

import pytest

from app.core.config import Settings
from app.services.quality_service import (AIReviewError, QualityEvaluator, Review, decide, parse_review)
from tests import fake_grok_server, fake_model_server
from tests.conftest import INVITE, _free_port, register, wait_run
from tests.fake_grok_server import review as fake_review

GROK_KEY = "xai-test-key-never-shown-123"


def test_windows_network_denial_is_actionable_paused_and_never_ai_reviewed():
    import httpx
    from app.services.quality_service import GroqClient

    s = Settings(_env_file=None, environment="test", database_url="sqlite://",
                 grok_api_key=GROK_KEY, grok_base_url="https://api.groq.com/openai/v1")
    calls = []

    def denied(request):
        calls.append(request)
        raise httpx.ConnectError("[WinError 10013] socket access forbidden", request=request)

    client = GroqClient(s)
    client.client.close()
    client.client = httpx.Client(transport=httpx.MockTransport(denied), base_url=s.grok_base_url)
    evaluator = QualityEvaluator(s, client)
    mcq = {"question": "What is a process?", "options": ["A running program", "A disk", "A file", "A bus"],
           "answer": "A", "explanation": "A process is a program in execution."}
    try:
        first = evaluator.evaluate(mcq, "OS", "Processes", "easy")
        second = evaluator.evaluate(mcq, "OS", "Processes", "easy")
        assert len(calls) == 1
        assert first.summary()["status"] == second.summary()["status"] == "not_checked"
        assert "10013" in first.ai_error and "outside the restricted sandbox" in first.ai_error
        assert evaluator.status()["state"] == "paused"
        assert first.ai is None and GROK_KEY not in first.ai_error
    finally:
        evaluator.close()


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
                    grok_api_key=GROK_KEY, grok_base_url=f"http://127.0.0.1:{grok_port}", grok_model="grok-test",
                    grok_timeout_s=0.5, grok_cooldown_s=300)


def _generate(cs, n=3, **extra):
    body = {"course_id": cs["course"]["id"], "subject_id": cs["subject"]["id"], "topic_id": cs["topic"]["id"],
            "title": "Quality quiz", "question_count": n, "difficulty": "mixed", **extra}
    fake_model_server.STATE["mode"] = "clean"
    r = cs["lec"].post("/api/lecturer/generate", json=body)
    assert r.status_code == 202, r.text
    return wait_run(cs["lec"], r.json()["run_id"], timeout=60)


def _questions(cs, quiz_id):
    return [it["question"] for it in cs["lec"].get(f"/api/lecturer/quizzes/{quiz_id}").json()["items"]]


# ---------- the reviewer's reply ----------

def test_parse_review_accepts_fenced_json_and_rejects_bad_replies():
    r = parse_review("```json\n" + json.dumps(fake_review("easy")) + "\n```")
    assert r.quality_score == 88 and r.difficulty.assessed == "easy"
    with pytest.raises(AIReviewError) as e:
        parse_review("Looks good!")
    assert e.value.kind == "bad_response"
    bad = fake_review("easy")
    bad["difficulty"]["assessed"] = "very hard"
    with pytest.raises(AIReviewError):
        parse_review(json.dumps(bad))
    bad = fake_review("easy")
    bad["quality_score"] = 140
    with pytest.raises(AIReviewError):
        parse_review(json.dumps(bad))


def test_decision_is_made_from_the_individual_checks():
    s = Settings(_env_file=None, environment="test", database_url="sqlite://")
    ok = fake_review("medium")
    assert decide(Review.model_validate(ok), "medium", s) is None
    cases = [({"correctness": {"verdict": "incorrect"}}, "quality_incorrect"),
             ({"multiple_correct": {"value": True}}, "quality_multiple_correct"),
             ({"ambiguity": {"ambiguous": True}}, "quality_ambiguous"),
             ({"relevance": {"ok": False}}, "quality_off_topic"),
             ({"explanation": {"supports_answer": False}}, "quality_explanation"),
             ({"options": {"ok": False}}, "quality_options"),
             ({"clarity": {"ok": False}}, "quality_unclear"),
             ({"difficulty": {"assessed": "hard"}}, "quality_difficulty"),
             ({"quality_score": 40}, "quality_low_score"),
             ({"passed": False}, "quality_other")]
    for change, reason in cases:
        r = json.loads(json.dumps(ok))
        for k, v in change.items():
            r[k] = {**r[k], **v} if isinstance(v, dict) else v
        assert decide(Review.model_validate(r), "medium", s) == reason, change
    # a wrong answer is reported before a difficulty mismatch
    r = {**ok, "correctness": {"verdict": "incorrect", "note": ""}, "difficulty": {"assessed": "hard", "note": ""}}
    assert decide(Review.model_validate(r), "medium", s) == "quality_incorrect"
    # "unsure" is recorded but does not fail the question on its own
    r = {**ok, "correctness": {"verdict": "unsure", "note": ""}}
    assert decide(Review.model_validate(r), "medium", s) is None
    s2 = Settings(_env_file=None, environment="test", database_url="sqlite://", quality_check_difficulty=False)
    r = {**ok, "difficulty": {"assessed": "hard", "note": ""}}
    assert decide(Review.model_validate(r), "medium", s2) is None


def test_without_a_key_only_the_python_checks_run():
    s = Settings(_env_file=None, environment="test", database_url="sqlite://")
    ev = QualityEvaluator(s)
    mcq = {"question": "What is paging?", "options": ["a", "b", "c", "d"], "answer": "A", "explanation": "x"}
    res = ev.evaluate(mcq, "OS", "Paging", "easy")
    assert res.passed and res.evaluator == "rules" and "GROK_API_KEY" in res.ai_error
    assert res.summary()["status"] == "not_checked"
    assert ev.status()["state"] == "not_configured" and ev.calls == 0


# ---------- generation with the AI review ----------

def test_passing_review_marks_questions_and_checks_the_mix(course_setup):
    run = _generate(course_setup, 3, distribution={"easy": 1, "medium": 1, "hard": 1})
    assert run["status"] == "done", run
    qual = run["quality"]
    assert qual["ai_review"] == "used" and qual["ai_model"] == "grok-test"
    assert qual["requested"] == {"easy": 1, "medium": 1, "hard": 1} and qual["mix_matches"] is True
    assert qual["failed_kept"] == 0 and qual["mismatched_question_ids"] == []
    for q in _questions(course_setup, run["quiz_id"]):
        v = q["validation"]["quality"]
        assert v["status"] == "passed" and v["evaluator"] == "grok" and v["score"] == 88
        assert v["assessed_difficulty"] == q["difficulty"]
        assert q["review_status"] == "draft"                     # passing the review never approves
    assert fake_grok_server.STATE["auth"][0] == f"Bearer {GROK_KEY}"


def test_failed_review_regenerates_only_that_question(course_setup):
    fake_grok_server.reset("fail_first:1")
    run = _generate(course_setup, 3)
    assert run["status"] == "done", run
    assert run["rejected"].get("quality_incorrect") == 1
    assert "marked answer looks wrong" in run["rejected_reasons"]["quality_incorrect"]
    assert fake_grok_server.STATE["calls"] == 4                  # 3 questions + 1 retry, nothing regenerated twice
    log = course_setup["lec"].get(f"/api/lecturer/generation/{run['run_id']}/agent").json()
    assert log["llm_calls"] == 4                                 # the agent log counts every AI review


def test_question_that_never_passes_is_kept_as_failed_and_not_approved(course_setup):
    fake_grok_server.reset("incorrect")
    run = _generate(course_setup, 2)
    assert run["status"] == "partial", run
    assert run["ready"] == 0 and run["quality"]["failed_kept"] == 2
    assert "kept for your review" in run["stage"]
    qs = _questions(course_setup, run["quiz_id"])
    assert len(qs) == 2
    for q in qs:
        v = q["validation"]
        assert v["failed_validation"] is True and v["failure_reason"] == "quality_incorrect"
        assert v["quality"]["status"] == "failed" and v["quality"]["feedback"] == "The key is wrong."
        assert q["review_status"] == "draft"
    # each slot was tried max_attempts_per_question (3) times, every attempt is logged
    assert fake_grok_server.STATE["calls"] == 6
    log = course_setup["lec"].get(f"/api/lecturer/questions/{qs[0]['id']}/evaluations").json()
    assert log[0]["reason"] == "quality_incorrect" and log[0]["regeneration_instructions"] == "Fix the answer key."
    # cannot be published until the lecturer decides
    assert course_setup["lec"].post(f"/api/lecturer/quizzes/{run['quiz_id']}/publish").status_code in (409, 422)


def test_difficulty_mismatch_is_retried_then_reported(course_setup):
    fake_grok_server.reset("hard")
    run = _generate(course_setup, 2, distribution={"easy": 1, "medium": 0, "hard": 1})
    qual = run["quality"]
    assert run["rejected"].get("quality_difficulty") == 3           # the easy slot, 3 tries
    assert qual["failed_kept"] == 1 and qual["mix_matches"] is False
    assert qual["ai_assessed"] == {"hard": 2} and len(qual["mismatched_question_ids"]) == 1
    kept = [q for q in _questions(course_setup, run["quiz_id"]) if q["validation"].get("failed_validation")]
    assert kept[0]["difficulty"] == "easy" and kept[0]["validation"]["quality"]["assessed_difficulty"] == "hard"


@pytest.mark.parametrize("mode,kind_text,paused", [
    ("rate_limit", "rate limiting", True), ("quota", "quota", True), ("auth", "API key", True),
    ("model_not_found", "GROK_MODEL", True),
    ("bad_json", "did not reply with JSON", False), ("empty", "did not reply with JSON", False),
    ("wrong_schema", "expected format", False),
])
def test_grok_problems_fall_back_to_the_python_checks(course_setup, app, mode, kind_text, paused):
    fake_grok_server.reset(mode)
    run = _generate(course_setup, 2)
    assert run["status"] == "done", run                          # generation is never blocked by the reviewer
    assert run["quality"]["ai_review"] == "not_used" and kind_text in run["quality"]["ai_note"]
    for q in _questions(course_setup, run["quiz_id"]):
        v = q["validation"]["quality"]
        assert v["status"] == "not_checked" and v["evaluator"] == "rules" and kind_text in v["ai_error"]
    # a rate limit, quota or key error pauses Grok calls instead of trying again for every question
    assert fake_grok_server.STATE["calls"] == (1 if paused else 2)
    log = course_setup["lec"].get(f"/api/lecturer/generation/{run['run_id']}/agent").json()
    assert log["llm_calls"] == (1 if paused else 2)              # attempted reviews, even the ones that failed
    state = course_setup["lec"].get("/api/health").json()["quality_review"]
    assert state["state"] == ("paused" if paused else "ready")


def test_server_errors_and_timeouts_retry_once_then_fall_back(course_setup):
    fake_grok_server.reset("error")
    run = _generate(course_setup, 1)
    assert run["status"] == "done" and fake_grok_server.STATE["calls"] == 2
    fake_grok_server.reset("slow")
    fake_grok_server.STATE["sleep"] = 1.5                        # longer than grok_timeout_s = 0.5
    run = _generate(course_setup, 1)
    assert run["status"] == "done"
    assert "did not answer within" in run["quality"]["ai_note"]


def test_practice_is_not_sent_to_grok_by_default(course_setup):
    st = course_setup["st"]
    r = st.post("/api/student/practice/generate", json={"subject": "OS", "topic": "Paging", "question_count": 5})
    run = wait_run(st, r.json()["run_id"], timeout=60)
    assert run["status"] == "done" and fake_grok_server.STATE["calls"] == 0
    assert run["quality"]["ai_review"] == "not_used" and "practice" in run["quality"]["ai_note"]


def test_only_question_content_is_sent_and_the_key_never_reaches_the_browser(course_setup):
    run = _generate(course_setup, 2)
    sent = json.dumps(fake_grok_server.STATE["bodies"])
    student = course_setup["student"]
    assert student["email"] not in sent and student["full_name"] not in sent
    assert "Dr Lecturer" not in sent and "@" not in sent
    lec = course_setup["lec"]
    for path in (f"/api/generation/{run['run_id']}", f"/api/lecturer/quizzes/{run['quiz_id']}", "/api/health"):
        assert GROK_KEY not in lec.get(path).text


# ---------- checking again after an edit ----------

def test_edit_then_check_again_clears_the_failure(course_setup):
    lec = course_setup["lec"]
    fake_grok_server.reset("incorrect")
    run = _generate(course_setup, 1)
    q = _questions(course_setup, run["quiz_id"])[0]
    assert q["validation"]["failed_validation"]
    r = lec.patch(f"/api/lecturer/questions/{q['id']}", json={"explanation": "Fixed explanation after checking."})
    assert r.status_code == 200 and r.json()["validation"]["quality"]["stale"] is True
    fake_grok_server.reset("pass")
    r = lec.post(f"/api/lecturer/questions/{q['id']}/check-quality")
    assert r.status_code == 200, r.text
    v = r.json()["validation"]
    assert "failed_validation" not in v and v["quality"]["status"] == "passed" and "stale" not in v["quality"]
    assert r.json()["review_status"] == "draft"                    # still needs the lecturer's approval
    assert lec.post(f"/api/lecturer/questions/{q['id']}/check-quality").status_code == 429   # just checked


def test_ai_failure_is_not_cleared_without_the_ai(course_setup, app):
    lec = course_setup["lec"]
    fake_grok_server.reset("incorrect")
    run = _generate(course_setup, 1)
    q = _questions(course_setup, run["quiz_id"])[0]
    app.state.quality._pause("test pause")                        # Grok unavailable now
    r = lec.post(f"/api/lecturer/questions/{q['id']}/check-quality")
    assert r.status_code == 200, r.text
    v = r.json()["validation"]
    assert v["failed_validation"] is True and v["quality"]["status"] == "not_checked"


def test_check_quality_is_owner_only(course_setup):
    run = _generate(course_setup, 1)
    q = _questions(course_setup, run["quiz_id"])[0]
    other = course_setup["make_client"]()
    register(other, "lecturer")
    assert other.post(f"/api/lecturer/questions/{q['id']}/check-quality").status_code == 404
    assert course_setup["st"].post(f"/api/lecturer/questions/{q['id']}/check-quality").status_code == 403


def test_python_check_failures_do_not_count_as_missing_ai_review(course_setup):
    lec = course_setup["lec"]
    body = {"course_id": course_setup["course"]["id"], "subject_id": course_setup["subject"]["id"],
            "topic_id": course_setup["topic"]["id"], "title": "Mixed failures", "question_count": 3, "difficulty": "mixed"}
    fake_model_server.STATE["mode"] = "normal"                   # every 5th reply is broken, some keys are wrong
    run = wait_run(lec, lec.post("/api/lecturer/generate", json=body).json()["run_id"], timeout=60)
    assert run["rejected"].get("format") and run["status"] == "done"
    assert run["quality"]["ai_review"] == "used" and run["quality"]["ai_note"] is None


def test_grok_error_text_shows_groks_own_message():
    import httpx
    from app.services.quality_service import _grok_error_text
    r = httpx.Response(400, json={"code": "Client specified an invalid argument",
                                  "error": "The model grok-latest does not exist or your team does not have access to it."})
    assert "grok-latest does not exist" in _grok_error_text(r)
    r = httpx.Response(400, json={"error": {"message": "Model not found", "type": "invalid_request_error"}})
    assert _grok_error_text(r) == "Model not found"
    assert _grok_error_text(httpx.Response(400, text="")) == "no details"
    assert len(_grok_error_text(httpx.Response(400, text="x" * 999))) == 200


# ---------- Phase B/D hardening: schema strictness, non-override, provider naming, scrubbing ----------

def test_parse_review_handles_think_blocks_and_rejects_empty_and_bool_coercion():
    think_reply = "<think>Check options {a, b} carefully.</think>\n```json\n" + json.dumps(fake_review("medium")) + "\n```"
    parsed = parse_review(think_reply)
    assert parsed.quality_score == 88 and parsed.difficulty.assessed == "medium"

    for empty in ("", "   \n ", "[]", '{"quality_score": 88'):
        with pytest.raises(AIReviewError) as exc:
            parse_review(empty)
        assert exc.value.kind == "bad_response"

    # Boolean / string coercion must fail strict schema checks rather than coercing True -> 1 or "yes" -> True
    for mut in (
        {"quality_score": True},
        {"quality_score": "88"},
        {"passed": "yes"},
        {"passed": 1},
        {"relevance": {"ok": 1, "note": ""}},
        {"multiple_correct": {"value": "false", "note": ""}},
        {"ambiguity": {"ambiguous": 0, "note": ""}},
        {"explanation": {"supports_answer": "true", "note": ""}},
    ):
        bad = fake_review("medium")
        bad.update(mut)
        with pytest.raises(AIReviewError) as exc:
            parse_review(json.dumps(bad))
        assert exc.value.kind == "bad_response", mut


def test_ai_review_cannot_override_failed_math_or_deterministic_rules(grok_port):
    fake_grok_server.reset("pass")
    s = Settings(_env_file=None, environment="test", database_url="sqlite://",
                 grok_api_key=GROK_KEY, grok_base_url=f"http://127.0.0.1:{grok_port}",
                 grok_model="qwen/qwen3.8-27b", grok_timeout_s=1.0)
    ev = QualityEvaluator(s)
    mcq = {"question": "What is 2 + 2?", "options": ["1", "2", "3", "4"], "answer": "A", "explanation": "2 + 2 = 4"}
    try:
        res_math = ev.evaluate(mcq, "Math", "Arithmetic", "easy", rules_info={"math_status": "wrong_key"})
        assert res_math.passed is False and res_math.reason == "math_wrong_key"
        assert res_math.summary()["status"] == "failed"

        res_unchecked = ev.evaluate(mcq, "Math", "Arithmetic", "easy", rules_info={"math_status": "unchecked"})
        assert res_unchecked.passed is False and res_unchecked.reason == "math_unchecked"

        res_rule = ev.evaluate(mcq, "Math", "Arithmetic", "easy",
                               rules_info={"rules_failed": True, "rules_reason": "duplicate"})
        assert res_rule.passed is False and res_rule.reason == "duplicate"
    finally:
        ev.close()


def test_think_wrapped_review_passes_generation_cleanly(course_setup):
    fake_grok_server.reset("think_pass")
    run = _generate(course_setup, 1)
    assert run["status"] == "done" and run["quality"]["ai_review"] == "used"
    q = _questions(course_setup, run["quiz_id"])[0]
    assert q["validation"]["quality"]["status"] == "passed"
    assert q["review_status"] == "draft"


def test_provider_label_distinguishes_groq_from_xai_grok_and_scrubs_secrets():
    import httpx
    from app.services.quality_service import GrokClient, GroqClient, _grok_error_text, _provider_error_text, scrub_secrets

    assert GrokClient is GroqClient
    assert _grok_error_text is _provider_error_text

    groq_s = Settings(_env_file=None, environment="test", database_url="sqlite://",
                      grok_api_key="gsk_secret_token_987654",
                      grok_base_url="https://api.groq.com/openai/v1",
                      grok_model="qwen/qwen3.8-27b")
    assert groq_s.ai_provider_id == "groq" and groq_s.ai_provider_label == "Groq API"

    xai_s = Settings(_env_file=None, environment="test", database_url="sqlite://",
                     grok_api_key="xai-secret-token-987654",
                     grok_base_url="https://api.x.ai/v1",
                     grok_model="grok-4.3")
    assert xai_s.ai_provider_id == "grok" and xai_s.ai_provider_label == "xAI Grok"

    class _FakeHttp:
        def __init__(self, resp):
            self.resp = resp
        def post(self, *a, **kw):
            return self.resp
        def close(self):
            pass

    c = GroqClient(groq_s)
    c.client.close()
    c.client = _FakeHttp(httpx.Response(404, json={"error": {"message": "Model missing for Authorization: Bearer gsk_secret_token_987654"}}))
    ev = QualityEvaluator(groq_s, client=c)
    assert ev.status()["provider"] == "groq" and ev.status()["provider_label"] == "Groq API"
    mcq = {"question": "What is virtual memory?", "options": ["a", "b", "c", "d"], "answer": "A", "explanation": "ok"}
    res = ev.evaluate(mcq, "OS", "Memory", "easy")
    assert res.passed and res.evaluator == "rules"
    assert res.summary()["status"] == "not_checked"
    assert "Groq API" in res.ai_error and "xAI Grok" not in res.ai_error
    assert "gsk_secret_token_987654" not in res.ai_error
    assert "[redacted]" in res.ai_error
    assert ev.status()["state"] == "paused"
    assert "gsk_secret_token_987654" not in (ev.status()["detail"] or "")
    assert "custom-secret-value" not in scrub_secrets("Header Bearer custom-secret-value failed", ("custom-secret-value",))
