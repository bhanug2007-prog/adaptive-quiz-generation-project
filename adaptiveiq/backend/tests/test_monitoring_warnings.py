from sqlalchemy import select

from app.models import MonitoringEvent, MonitoringSession, QuizSession, QuizResult
from tests.conftest import register
from tests.test_monitoring import _published, _start, _send, _at


def warning(seq, signal="face_multiple", incident=None, seconds=0, duration=10000):
    return {"seq": seq, "kind": "activity_warning", "at": _at(seconds), "duration_ms": duration,
            "details": {"signal": signal, "incident_id": incident or f"incident-{seq}", "confirmed": True}}


def test_three_warnings_preserve_answers_marks_and_refresh(course_setup, app):
    cs = course_setup
    qid = _published(cs)
    st = cs["st"]
    attempt = _start(st, qid)
    sid = attempt["session_id"]
    question = attempt["questions"][0]
    response = st.put(f"/api/student/attempts/{sid}/answers/{question['question_id']}",
                      json={"option_id": question["options"][0]["id"], "confidence": 2})
    assert response.status_code == 200, response.text
    before = st.get(f"/api/student/attempts/{sid}").json()["answers"]
    for count, signal in enumerate(["face_multiple", "page_hidden", "fullscreen_exit"], 1):
        e = warning(count, signal)
        assert _send(st, sid, [e]).status_code == 200
        assert _send(st, sid, [e]).json()["duplicates"] == 1
        record = st.get(f"/api/student/attempts/{sid}/monitoring").json()
        assert record["warning_count"] == count
        assert record["review_required"] is (count == 3)
    refreshed = st.get(f"/api/student/attempts/{sid}").json()
    assert refreshed["answers"] == before and refreshed["status"] == "in_progress"
    with app.state.db.session() as db:
        assert db.get(QuizSession, sid).submitted_at is None
        assert db.scalar(select(QuizResult).where(QuizResult.session_id == sid)) is None
    row = cs["lec"].get(f"/api/lecturer/quizzes/{qid}/monitoring").json()["students"][0]
    assert row["status"] == "needs_review" and row["review_required"] and row["awaiting_review"]
    assert len(row["warning_history"]) == 3
    assert all(e["at"] for e in row["warning_history"])
    # Ordinary student submission still grades normally; later monitoring cannot alter the result.
    assert st.post(f"/api/student/attempts/{sid}/submit").status_code == 200
    with app.state.db.session() as db:
        result = db.scalar(select(QuizResult).where(QuizResult.session_id == sid))
        original = (result.raw_score, result.final_percentage, result.max_score)
    _send(st, sid, [warning(4, "speech")])
    with app.state.db.session() as db:
        result = db.scalar(select(QuizResult).where(QuizResult.session_id == sid))
        assert (result.raw_score, result.final_percentage, result.max_score) == original


def test_incident_dedup_persistence_cooldown_and_untrusted_fields(course_setup):
    st = course_setup["st"]
    sid = _start(st, _published(course_setup))["session_id"]
    events = [warning(1), warning(2, incident="incident-1", seconds=60),
              warning(3, seconds=1), warning(4, "speech", duration=500),
              warning(5, "face_none", duration=1000), warning(6, seconds=30)]
    assert _send(st, sid, events).status_code == 200
    r = st.get(f"/api/student/attempts/{sid}/monitoring").json()
    assert r["warning_count"] == 2
    assert [e["seq"] for e in r["warning_history"]] == [1, 6]
    malformed = warning(7)
    malformed["details"]["signal"] = []
    assert _send(st, sid, [malformed]).status_code == 200
    assert st.get(f"/api/student/attempts/{sid}/monitoring").json()["warning_count"] == 2


def test_reports_are_append_only_idempotent_and_authorized(course_setup, app):
    cs = course_setup
    sid = _start(cs["st"], _published(cs))["session_id"]
    _send(cs["st"], sid, [warning(1)])
    url = f"/api/student/attempts/{sid}/monitoring/reports"
    body = {"report_id": "report-1", "category": "false_alert", "event_seq": 1, "note": "Reflection in a mirror"}
    other = cs["make_client"]()
    register(other)
    assert other.post(url, json=body).status_code == 404
    assert cs["lec"].post(url, json=body).status_code == 403
    assert cs["st"].post(url, json={**body, "event_seq": 999}).status_code == 404
    assert cs["st"].post(url, json=body).status_code == 200
    assert cs["st"].post(url, json=body).status_code == 200
    r = cs["st"].get(f"/api/student/attempts/{sid}/monitoring").json()
    assert r["warning_count"] == 1 and len(r["events"]) == 2
    with app.state.db.session() as db:
        m = db.scalar(select(MonitoringSession).where(MonitoringSession.session_id == sid))
        mid = m.id
    timeline = cs["lec"].get(f"/api/lecturer/monitoring/{mid}").json()
    assert timeline["timeline"][-1]["details"]["note"] == body["note"]
    stranger = cs["make_client"]()
    register(stranger, "lecturer")
    assert stranger.get(f"/api/lecturer/monitoring/{mid}").status_code == 404


def test_policy_snapshot_and_legacy_records_unchanged(course_setup, app, settings):
    settings.monitoring_warning_threshold = 2
    settings.monitoring_warning_speech_ms = 20000
    sid = _start(course_setup["st"], _published(course_setup))["session_id"]
    settings.monitoring_warning_threshold = 9
    st = course_setup["st"]
    _send(st, sid, [warning(1), warning(2, "speech")])
    r = st.get(f"/api/student/attempts/{sid}/monitoring").json()
    assert r["warning_threshold"] == 2 and r["warning_count"] == 1
    with app.state.db.session() as db:
        m = db.scalar(select(MonitoringSession).where(MonitoringSession.session_id == sid))
        m.settings = {k: v for k, v in m.settings.items() if k != "warning_policy"}
        db.commit()
    _send(st, sid, [warning(3, "page_hidden")])
    assert st.get(f"/api/student/attempts/{sid}/monitoring").json()["warning_count"] == 1


def test_concurrent_incident_uploads_count_once(course_setup):
    from concurrent.futures import ThreadPoolExecutor
    st = course_setup["st"]
    sid = _start(st, _published(course_setup))["session_id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda seq: _send(st, sid, [warning(seq, incident="same-episode")]), [1, 2]))
    assert all(r.status_code == 200 for r in results)
    record = st.get(f"/api/student/attempts/{sid}/monitoring").json()
    assert record["warning_count"] == 1 and len(record["events"]) == 2
