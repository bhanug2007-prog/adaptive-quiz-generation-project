"""Phase 6: assessment integrity monitoring (settings, consent, event upload, the neutral summary,
permissions and retention). The browser side is tested in the frontend; here events are sent as the browser
would send them."""
from datetime import timedelta

from sqlalchemy import select

from app.models import MonitoringEvent, MonitoringSession
from app.models.base import utcnow
from app.services import monitoring_service as mon
from tests import fake_model_server
from tests.conftest import register, wait_run

ALL_ON = {"monitor_tab": True, "monitor_fullscreen": "required", "monitor_camera": True, "monitor_microphone": True}


def _published(cs, monitoring=ALL_ON, title="Monitored quiz"):
    lec = cs["lec"]
    fake_model_server.STATE["mode"] = "clean"
    body = {"course_id": cs["course"]["id"], "subject_id": cs["subject"]["id"], "topic_id": cs["topic"]["id"],
            "title": title, "question_count": 3, "difficulty": "mixed"}
    run = wait_run(lec, lec.post("/api/lecturer/generate", json=body).json()["run_id"], timeout=60)
    qid = run["quiz_id"]
    for it in lec.get(f"/api/lecturer/quizzes/{qid}").json()["items"]:
        lec.post(f"/api/lecturer/questions/{it['question']['id']}/review", json={"action": "approve"})
    r = lec.patch(f"/api/lecturer/quizzes/{qid}", json={"contribution_pct": 5, **(monitoring or {})})
    assert r.status_code == 200, r.text
    assert lec.post(f"/api/lecturer/quizzes/{qid}/publish").status_code == 200
    return qid


def _at(sec=0):
    return (utcnow() + timedelta(seconds=sec)).isoformat()


def _start(st, qid):
    r = st.post(f"/api/student/quizzes/{qid}/start", json={"monitoring_consent": True})
    assert r.status_code == 200, r.text
    return r.json()


def _send(st, sid, events):
    return st.post(f"/api/student/attempts/{sid}/monitoring/events", json={"events": events})


def test_settings_are_off_by_default_and_saved(course_setup):
    qid = _published(course_setup, monitoring=None, title="Plain quiz")
    z = course_setup["lec"].get(f"/api/lecturer/quizzes/{qid}").json()
    assert (z["monitor_tab"], z["monitor_fullscreen"], z["monitor_camera"], z["monitor_microphone"]) == (False, "off", False, False)
    st = course_setup["st"]
    assert st.get(f"/api/student/quizzes/{qid}").json()["monitoring"] is None
    att = st.post(f"/api/student/quizzes/{qid}/start").json()          # no consent needed, nothing recorded
    assert att["monitoring"] is None
    assert _send(st, att["session_id"], [{"seq": 1, "kind": "page_hidden", "at": _at()}]).status_code == 404


def test_consent_is_required_before_a_monitored_attempt(course_setup):
    qid = _published(course_setup)
    st = course_setup["st"]
    card = st.get(f"/api/student/quizzes/{qid}").json()
    assert card["monitoring"] == {"tab": True, "fullscreen": "required", "camera": True, "microphone": True}
    r = st.post(f"/api/student/quizzes/{qid}/start")
    assert r.status_code == 428 and "monitored" in r.json()["detail"]
    assert st.post(f"/api/student/quizzes/{qid}/start", json={"monitoring_consent": False}).status_code == 428
    att = _start(st, qid)
    m = att["monitoring"]
    assert m["camera"] and m["camera_state"] == "not_requested" and m["face_interval_ms"] > 0
    # resuming the same attempt does not ask again
    again = st.post(f"/api/student/quizzes/{qid}/start")
    assert again.status_code == 200 and again.json()["session_id"] == att["session_id"]


def test_settings_locked_once_students_started(course_setup):
    qid = _published(course_setup)
    _start(course_setup["st"], qid)
    r = course_setup["lec"].patch(f"/api/lecturer/quizzes/{qid}", json={"monitor_camera": False})
    assert r.status_code == 409


def test_events_are_stored_once_and_checked(course_setup, app):
    qid = _published(course_setup)
    st = course_setup["st"]
    sid = _start(st, qid)["session_id"]
    assert st.post(f"/api/student/attempts/{sid}/monitoring/devices",
                   json={"camera": "granted", "microphone": "denied"}).status_code == 200
    batch = [{"seq": 1, "kind": "page_hidden", "at": _at()},
             {"seq": 2, "kind": "page_visible", "at": _at(5), "duration_ms": 5000},
             {"seq": 3, "kind": "face_multiple", "at": _at(8), "duration_ms": 3000,
              "details": {"faces": 2, "x": "drop me", "camera": [], "microphone": {}, "video": "discard", "audio": "discard"}}]
    assert _send(st, sid, batch).json() == {"stored": 3, "duplicates": 0, "dropped": 0}
    assert _send(st, sid, batch).json() == {"stored": 0, "duplicates": 3, "dropped": 0}     # a retried upload
    r = _send(st, sid, [{"seq": 4, "kind": "page_hidden", "at": _at(-3600)},               # before the attempt
                        {"seq": 5, "kind": "speech", "at": _at(10), "duration_ms": 1200}])
    assert r.json() == {"stored": 1, "duplicates": 0, "dropped": 1}
    assert _send(st, sid, [{"seq": 6, "kind": "screenshot", "at": _at()}]).status_code == 422   # unknown kind
    assert _send(st, sid, [{"seq": 7, "kind": "speech", "at": "2026-01-01T10:00:00"}]).status_code == 422  # no zone
    with app.state.db.session() as db:
        ev = db.scalars(select(MonitoringEvent).where(MonitoringEvent.kind == "face_multiple")).one()
        assert ev.details == {"faces": 2}
    mine = st.get(f"/api/student/attempts/{sid}/monitoring").json()                          # the student sees it too
    assert [e["kind"] for e in mine["events"]] == ["page_hidden", "page_visible", "face_multiple", "speech"]
    assert mine["microphone"] == "denied"


def test_uploads_close_after_submission(course_setup, app):
    qid = _published(course_setup)
    st = course_setup["st"]
    sid = _start(st, qid)["session_id"]
    st.post(f"/api/student/attempts/{sid}/submit")
    assert _send(st, sid, [{"seq": 1, "kind": "page_hidden", "at": _at()}]).json()["stored"] == 1   # late flush
    with app.state.db.session() as db:
        from app.models import QuizSession
        s = db.get(QuizSession, sid)
        s.submitted_at = utcnow() - timedelta(seconds=mon.LATE_UPLOAD_S + 5)
        db.commit()
    assert _send(st, sid, [{"seq": 2, "kind": "page_hidden", "at": _at()}]).status_code == 409


def test_lecturer_summary_uses_neutral_labels(course_setup):
    cs = course_setup
    qid = _published(cs)
    calm = cs["st"]
    sid1 = _start(calm, qid)["session_id"]
    calm.post(f"/api/student/attempts/{sid1}/monitoring/devices", json={"camera": "granted", "microphone": "granted"})
    _send(calm, sid1, [{"seq": 1, "kind": "fullscreen_enter", "at": _at()}])

    busy = cs["make_client"]()
    register(busy, "student", name="Student Two")
    busy.post("/api/student/courses/join", json={"join_code": cs["course"]["join_code"]})
    sid2 = _start(busy, qid)["session_id"]
    busy.post(f"/api/student/attempts/{sid2}/monitoring/devices", json={"camera": "granted", "microphone": "granted"})
    ev = []
    for i in range(3):
        ev += [{"seq": 2 * i, "kind": "page_hidden", "at": _at(i)},
               {"seq": 2 * i + 1, "kind": "page_visible", "at": _at(i + 1), "duration_ms": 25000}]
    ev += [{"seq": 10, "kind": "speech", "at": _at(5), "duration_ms": 12000},
           {"seq": 11, "kind": "face_none", "at": _at(6), "duration_ms": 4000}]
    _send(busy, sid2, ev)

    third = cs["make_client"]()
    register(third, "student", name="Student Three")
    third.post("/api/student/courses/join", json={"join_code": cs["course"]["join_code"]})
    sid3 = _start(third, qid)["session_id"]
    third.post(f"/api/student/attempts/{sid3}/monitoring/devices", json={"camera": "granted", "microphone": "granted"})
    _send(third, sid3, [{"seq": 1, "kind": "speech", "at": _at(), "duration_ms": 2000}])

    rep = cs["lec"].get(f"/api/lecturer/quizzes/{qid}/monitoring").json()
    by = {r["student"]: r for r in rep["students"]}
    assert [r["student"] for r in rep["students"]] == ["Student Two", "Student Three", "Student One"]
    assert by["Student One"]["status"] == "normal" and by["Student One"]["reasons"] == []
    assert by["Student Three"]["status"] == "event_recorded"
    two = by["Student Two"]
    assert two["status"] == "needs_review"
    assert two["counts"]["tab_switches"] == 3 and two["counts"]["hidden_s"] == 75.0
    assert two["counts"]["speech_prolonged"] == 1 and two["counts"]["no_face_s"] == 4.0
    assert any("hidden 3 times" in x for x in two["reasons"]) and any("75 seconds" in x for x in two["reasons"])
    assert rep["totals"] == {"needs_review": 1, "event_recorded": 1, "normal": 1}
    text = str(rep).lower()
    assert "cheat" not in text and "suspicious" not in text
    tl = cs["lec"].get(f"/api/lecturer/monitoring/{two['id']}").json()
    assert len(tl["timeline"]) == 8 and tl["timeline"][0]["kind"] == "page_hidden"
    r = cs["lec"].post(f"/api/lecturer/monitoring/{two['id']}/review", json={"review": "no_concern", "note": "Phone call, told me."})
    assert r.json()["review"] == "no_concern"
    assert cs["lec"].get(f"/api/lecturer/monitoring/{two['id']}").json()["review_note"] == "Phone call, told me."


def test_required_device_denied_needs_review(course_setup):
    qid = _published(course_setup)
    st = course_setup["st"]
    sid = _start(st, qid)["session_id"]
    st.post(f"/api/student/attempts/{sid}/monitoring/devices", json={"camera": "denied", "microphone": "granted"})
    _send(st, sid, [{"seq": 1, "kind": "camera_denied", "at": _at()}])
    row = course_setup["lec"].get(f"/api/lecturer/quizzes/{qid}/monitoring").json()["students"][0]
    assert row["status"] == "needs_review" and any("camera" in x for x in row["reasons"])


def test_only_the_owner_sees_monitoring(course_setup):
    cs = course_setup
    qid = _published(cs)
    sid = _start(cs["st"], qid)["session_id"]
    mid = cs["lec"].get(f"/api/lecturer/quizzes/{qid}/monitoring").json()["students"][0]["id"]
    other = cs["make_client"]()
    register(other, "lecturer", name="Other Lecturer")
    assert other.get(f"/api/lecturer/quizzes/{qid}/monitoring").status_code == 404
    assert other.get(f"/api/lecturer/monitoring/{mid}").status_code == 404
    assert other.post(f"/api/lecturer/monitoring/{mid}/review", json={"review": "follow_up"}).status_code == 404
    assert cs["st"].get(f"/api/lecturer/monitoring/{mid}").status_code == 403
    nosy = cs["make_client"]()
    register(nosy, "student", name="Student Nosy")
    assert nosy.get(f"/api/student/attempts/{sid}/monitoring").status_code == 404
    assert _send(nosy, sid, [{"seq": 1, "kind": "page_hidden", "at": _at()}]).status_code == 404


def test_old_monitoring_data_is_deleted(course_setup, app):
    qid = _published(course_setup)
    st = course_setup["st"]
    sid = _start(st, qid)["session_id"]
    _send(st, sid, [{"seq": 1, "kind": "page_hidden", "at": _at()}])
    with app.state.db.session() as db:
        m = db.scalars(select(MonitoringSession)).one()
        m.created_at = utcnow() - timedelta(days=400)
        db.commit()
        assert mon.purge_old(db, 0) == 0                              # 0 keeps everything
        assert mon.purge_old(db, 180) == 1
        assert db.scalars(select(MonitoringEvent)).all() == []


def test_practice_quizzes_are_never_monitored():
    class Z:
        kind = "practice"; monitor_tab = True; monitor_fullscreen = "required"; monitor_camera = True; monitor_microphone = True
    assert mon.quiz_settings(Z()) is None


def test_five_student_scenarios_and_filters_archived_quiz(course_setup):
    cs = course_setup
    lec = cs["lec"]
    qid = _published(cs, title="Five Scenario Quiz")

    def make_student(name):
        client = cs["make_client"]()
        register(client, "student", name=name)
        assert client.post("/api/student/courses/join", json={"join_code": cs["course"]["join_code"]}).status_code == 200
        return client

    # Student D (first user from course_setup or dedicated) - make explicit Students A..E for clarity
    stu_a = make_student("Student A Tabs")
    sid_a = _start(stu_a, qid)["session_id"]
    assert stu_a.post(f"/api/student/attempts/{sid_a}/monitoring/devices", json={"camera": "granted", "microphone": "granted"}).status_code == 200
    batch_a = [
        {"seq": 1, "kind": "monitoring_started", "at": _at(0), "details": {"camera": "granted", "microphone": "granted"}},
        {"seq": 2, "kind": "page_hidden", "at": _at(5), "details": {"reason": "window_blur"}},
        {"seq": 3, "kind": "page_visible", "at": _at(19), "duration_ms": 14000, "details": {"reason": "window_blur"}},
        {"seq": 4, "kind": "page_hidden", "at": _at(25), "details": {"reason": "tab_hidden"}},
        {"seq": 5, "kind": "page_visible", "at": _at(30), "duration_ms": 5000},
    ]
    assert _send(stu_a, sid_a, batch_a).json() == {"stored": 5, "duplicates": 0, "dropped": 0}
    assert _send(stu_a, sid_a, batch_a).json() == {"stored": 0, "duplicates": 5, "dropped": 0}
    assert stu_a.post(f"/api/student/attempts/{sid_a}/submit").status_code == 200

    # Student B: face absence + multiple faces
    stu_b = make_student("Student B Face")
    sid_b = _start(stu_b, qid)["session_id"]
    assert stu_b.post(f"/api/student/attempts/{sid_b}/monitoring/devices", json={"camera": "granted", "microphone": "granted"}).status_code == 200
    assert _send(stu_b, sid_b, [
        {"seq": 1, "kind": "monitoring_started", "at": _at(0), "details": {"camera": "granted", "microphone": "granted"}},
        {"seq": 2, "kind": "face_none", "at": _at(4), "duration_ms": 6000, "details": {"faces": 0}},
        {"seq": 3, "kind": "face_multiple", "at": _at(12), "duration_ms": 2000, "details": {"faces": 2}},
    ]).json() == {"stored": 3, "duplicates": 0, "dropped": 0}
    assert stu_b.post(f"/api/student/attempts/{sid_b}/submit").status_code == 200

    # Student C: speech-like audio activity
    stu_c = make_student("Student C Audio")
    sid_c = _start(stu_c, qid)["session_id"]
    assert stu_c.post(f"/api/student/attempts/{sid_c}/monitoring/devices", json={"camera": "granted", "microphone": "granted"}).status_code == 200
    assert _send(stu_c, sid_c, [
        {"seq": 1, "kind": "monitoring_started", "at": _at(0), "details": {"camera": "granted", "microphone": "granted"}},
        {"seq": 2, "kind": "speech", "at": _at(7), "duration_ms": 5000},
    ]).json() == {"stored": 2, "duplicates": 0, "dropped": 0}
    assert stu_c.post(f"/api/student/attempts/{sid_c}/submit").status_code == 200

    # Student D: actively monitored, zero activity events (Normal)
    stu_d = make_student("Student D Clean")
    sid_d = _start(stu_d, qid)["session_id"]
    assert stu_d.post(f"/api/student/attempts/{sid_d}/monitoring/devices", json={"camera": "granted", "microphone": "granted"}).status_code == 200
    assert _send(stu_d, sid_d, [
        {"seq": 1, "kind": "monitoring_started", "at": _at(0), "details": {"camera": "granted", "microphone": "granted"}},
    ]).json() == {"stored": 1, "duplicates": 0, "dropped": 0}
    assert stu_d.post(f"/api/student/attempts/{sid_d}/submit").status_code == 200

    # Student E: consented, but never uploaded device permissions or events (Unavailable)
    stu_e = make_student("Student E Unavailable")
    sid_e = _start(stu_e, qid)["session_id"]
    assert stu_e.post(f"/api/student/attempts/{sid_e}/submit").status_code == 200

    # Archive quiz and verify completed attempts remain fully reviewable
    assert lec.post(f"/api/lecturer/quizzes/{qid}/archive").status_code == 200
    detail = lec.get(f"/api/lecturer/quizzes/{qid}").json()
    assert detail["monitoring_summary"] == {
        "enabled": True, "attempt_count": 5, "monitored_count": 5, "with_events": 3,
        "needs_review": 1, "unavailable_count": 1, "awaiting_review": 4,
    }

    rep = lec.get(f"/api/lecturer/quizzes/{qid}/monitoring").json()
    assert rep["quiz_status"] == "archived"
    assert rep["summary"] == {
        "total_attempts": 5, "needs_review": 1, "event_recorded": 2, "normal": 1,
        "unavailable": 1, "not_monitored": 0, "with_recorded_events": 3,
        "no_recorded_events": 1, "unavailable_or_not_monitored": 1, "awaiting_review": 4, "reviewed": 0,
    }
    by = {r["student"]: r for r in rep["students"]}
    assert by["Student A Tabs"]["counts"]["tab_switches"] == 2
    assert by["Student A Tabs"]["counts"]["hidden_s"] == 19.0
    assert by["Student A Tabs"]["status"] == "event_recorded"
    assert by["Student A Tabs"]["last_event_at"] is not None
    assert by["Student A Tabs"]["attempt_status"] == "submitted"

    assert by["Student B Face"]["status"] == "needs_review"
    assert by["Student B Face"]["counts"]["no_face"] == 1
    assert by["Student B Face"]["counts"]["multiple_faces"] == 1

    assert by["Student C Audio"]["status"] == "event_recorded"
    assert by["Student C Audio"]["counts"]["speech"] == 1
    assert by["Student C Audio"]["counts"]["speech_s"] == 5.0

    assert by["Student D Clean"]["status"] == "normal"
    assert by["Student D Clean"]["monitoring_state"] == "active"
    assert by["Student D Clean"]["has_recorded_events"] is False

    # Missing telemetry MUST NOT be marked as "normal" / compliant
    assert by["Student E Unavailable"]["status"] == "unavailable"
    assert by["Student E Unavailable"]["monitoring_state"] == "unavailable"
    assert by["Student E Unavailable"]["signal_availability"] == {
        "tab": "unavailable", "fullscreen": "unavailable", "camera": "unavailable", "microphone": "unavailable",
    }

    # Check timeline details, upload status, sources, and manual review note preservation
    tl_a = lec.get(f"/api/lecturer/monitoring/{by['Student A Tabs']['id']}").json()
    assert [e["source"] for e in tl_a["timeline"]] == [
        "Monitoring setup", "Window focus monitor", "Window focus monitor",
        "Tab visibility monitor", "Tab visibility monitor",
    ]
    assert all(e["uploaded"] is True for e in tl_a["timeline"])
    assert tl_a["timeline"][2]["duration_ms"] == 14000

    tl_b = lec.get(f"/api/lecturer/monitoring/{by['Student B Face']['id']}").json()
    assert [e["device_state"] for e in tl_b["timeline"][1:]] == [{"camera": "granted"}, {"camera": "granted"}]

    mid_b = by["Student B Face"]["id"]
    r1 = lec.post(f"/api/lecturer/monitoring/{mid_b}/review", json={"review": "follow_up", "note": "Check room lighting"}).json()
    assert r1["review"] == "follow_up" and r1["review_status"] == "follow_up"
    r2 = lec.post(f"/api/lecturer/monitoring/{mid_b}/review", json={"review": None, "note": "Check room lighting"}).json()
    assert r2["review"] is None and r2["review_status"] == "not_reviewed" and r2["review_note"] == "Check room lighting"
    r3 = lec.post(f"/api/lecturer/monitoring/{mid_b}/review", json={"review": "no_concern", "note": "Check room lighting"}).json()
    assert r3["review_status"] == "no_concern" and r3["review_note"] == "Check room lighting"
    rep_after = lec.get(f"/api/lecturer/quizzes/{qid}/monitoring").json()
    assert rep_after["summary"]["awaiting_review"] == 3 and rep_after["summary"]["reviewed"] == 1
    raw = (str(rep_after) + str(tl_a) + str(tl_b)).lower()
    for banned in ("cheat", "suspicious", "guilty", "video", "transcript"):
        assert banned not in raw


def test_unmonitored_attempt_and_privacy_boundaries(course_setup):
    cs = course_setup
    qid_off = _published(cs, monitoring=None, title="Unmonitored Quiz")
    st = cs["st"]
    sid = st.post(f"/api/student/quizzes/{qid_off}/start").json()["session_id"]
    st.post(f"/api/student/attempts/{sid}/submit")

    rep = cs["lec"].get(f"/api/lecturer/quizzes/{qid_off}/monitoring").json()
    assert len(rep["students"]) == 1
    row = rep["students"][0]
    assert row["id"] is None
    assert row["status"] == "not_monitored"
    assert row["monitoring_state"] == "not_monitored"
    assert row["signal_availability"] == {
        "tab": "not_monitored", "fullscreen": "not_monitored", "camera": "not_monitored", "microphone": "not_monitored",
    }
    assert rep["summary"]["not_monitored"] == 1 and rep["summary"]["no_recorded_events"] == 0
    # Student isolation: other student cannot read or submit events; student cannot read lecturer report
    other_stu = cs["make_client"]()
    register(other_stu, "student", name="Other Student")
    assert st.get(f"/api/lecturer/quizzes/{qid_off}/monitoring").status_code == 403
    assert other_stu.get(f"/api/student/attempts/{sid}/monitoring").status_code == 404
