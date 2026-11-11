"""Authorization is enforced by the backend, not by hidden buttons."""
from tests.conftest import register, wait_run
from tests.test_flow import _approve_all, _draft


def _published(cs):
    run = _draft(cs, 2)
    _approve_all(cs["lec"], run["quiz_id"])
    assert cs["lec"].post(f"/api/lecturer/quizzes/{run['quiz_id']}/publish").status_code == 200
    return run["quiz_id"]


def test_student_cannot_see_other_students_attempts(course_setup):
    qid = _published(course_setup)
    st = course_setup["st"]
    att = st.post(f"/api/student/quizzes/{qid}/start").json()
    st.post(f"/api/student/attempts/{att['session_id']}/submit")
    other = course_setup["make_client"]()
    register(other, "student")
    other.post("/api/student/courses/join", json={"join_code": course_setup["course"]["join_code"]})
    sid = att["session_id"]
    assert other.get(f"/api/student/attempts/{sid}").status_code == 404
    assert other.get(f"/api/student/attempts/{sid}/result").status_code == 404
    assert other.post(f"/api/student/attempts/{sid}/submit").status_code == 404
    assert other.put(f"/api/student/attempts/{sid}/answers/1", json={"option_id": None}).status_code == 404


def test_unenrolled_student_cannot_open_quiz(course_setup):
    qid = _published(course_setup)
    outsider = course_setup["make_client"]()
    register(outsider, "student")
    assert outsider.get(f"/api/student/quizzes/{qid}").status_code == 404
    assert outsider.post(f"/api/student/quizzes/{qid}/start").status_code == 404
    assert outsider.get("/api/student/quizzes/assigned").json() == []


def test_removed_student_loses_access(course_setup):
    qid = _published(course_setup)
    lec, st = course_setup["lec"], course_setup["st"]
    sid = course_setup["student"]["id"]
    assert lec.delete(f"/api/lecturer/courses/{course_setup['course']['id']}/students/{sid}").status_code == 204
    assert st.post(f"/api/student/quizzes/{qid}/start").status_code == 404
    r = st.post("/api/student/courses/join", json={"join_code": course_setup["course"]["join_code"]})
    assert r.status_code == 403


def test_lecturer_cannot_touch_another_lecturers_course(course_setup):
    qid = _published(course_setup)
    other = course_setup["make_client"]()
    register(other, "lecturer")
    cid = course_setup["course"]["id"]
    for path in (f"/api/lecturer/courses/{cid}", f"/api/lecturer/courses/{cid}/roster",
                 f"/api/lecturer/courses/{cid}/analytics", f"/api/lecturer/courses/{cid}/heatmap",
                 f"/api/lecturer/quizzes/{qid}", f"/api/lecturer/reports/quizzes/{qid}/results.csv",
                 f"/api/lecturer/reports/courses/{cid}/marks.csv", f"/api/lecturer/quizzes/{qid}/export",
                 f"/api/lecturer/students/{course_setup['student']['id']}"):
        assert other.get(path).status_code == 404, path
    assert other.post(f"/api/lecturer/quizzes/{qid}/archive").status_code == 404
    assert other.post(f"/api/lecturer/courses/{cid}/subjects", json={"name": "Hacked"}).status_code == 404
    assert other.get("/api/lecturer/students").json()["total"] == 0


def test_answer_key_never_in_student_payload_before_submission(course_setup):
    qid = _published(course_setup)
    st = course_setup["st"]
    for body in (st.post(f"/api/student/quizzes/{qid}/start").text, st.get(f"/api/student/quizzes/{qid}").text):
        assert "is_correct" not in body and "explanation" not in body and "source_excerpt" not in body


def test_student_cannot_use_lecturer_endpoints(course_setup):
    st = course_setup["st"]
    cid = course_setup["course"]["id"]
    assert st.get(f"/api/lecturer/courses/{cid}").status_code == 403
    assert st.post("/api/lecturer/generate", json={}).status_code in (403, 422)
    assert st.get("/api/lecturer/questions").status_code == 403


def test_practice_quiz_private_to_owner(course_setup):
    st = course_setup["st"]
    r = st.post("/api/student/practice/generate", json={"subject": "OS", "topic": "Deadlocks"})
    run = wait_run(st, r.json()["run_id"])
    other = course_setup["make_client"]()
    register(other, "student")
    assert other.get(f"/api/generation/{run['run_id']}").status_code == 404
    assert other.post(f"/api/student/quizzes/{run['quiz_id']}/start").status_code == 404


def test_option_from_another_question_rejected(course_setup):
    qid = _published(course_setup)
    st = course_setup["st"]
    att = st.post(f"/api/student/quizzes/{qid}/start").json()
    q1, q2 = att["questions"]
    r = st.put(f"/api/student/attempts/{att['session_id']}/answers/{q1['question_id']}",
               json={"option_id": q2["options"][0]["id"]})
    assert r.status_code == 422


def test_csv_formula_cells_neutralised(course_setup, app):
    from app.models import User
    with app.state.db.session() as db:
        u = db.get(User, course_setup["student"]["id"])
        u.full_name = "=HYPERLINK(\"http://x\")"
        db.commit()
    qid = _published(course_setup)
    text = course_setup["lec"].get(f"/api/lecturer/reports/quizzes/{qid}/results.csv").text
    assert "'=HYPERLINK" in text


def test_oversized_bodies_are_refused_even_without_content_length(make_client):
    c = make_client()
    big = b'{"email": "a@example.com", "password": "' + b"x" * (300 * 1024) + b'"}'
    r = c.post("/api/auth/login", content=big, headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    def chunks():                                     # a chunked upload sends no Content-Length
        for i in range(0, len(big), 32 * 1024):
            yield big[i:i + 32 * 1024]
    r = c.post("/api/auth/login", content=chunks(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413 and r.json()["detail"] == "Request is too large."
    small = c.post("/api/auth/login", content=iter([b'{"email": "a@example.com", ', b'"password": "wrong-pass1"}']),
                   headers={"Content-Type": "application/json"})
    assert small.status_code == 401                   # normal chunked requests still work
