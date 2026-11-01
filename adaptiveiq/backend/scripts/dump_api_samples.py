"""Writes one example JSON response per API endpoint to docs/api-samples/ (frontend contract reference).

Runs entirely in memory against a temporary SQLite database and the TEST-ONLY fake model server.
All names and numbers in the output are test fixtures, not real data.

    python -m scripts.dump_api_samples
"""
import json
import socket
import sys
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.db import Base
from app.main import create_app
from tests import fake_model_server

OUT = Path(__file__).resolve().parents[2] / "docs" / "api-samples"
INVITE = "sample-invite"


def port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait(c, run_id):
    for _ in range(600):
        r = c.get(f"/api/generation/{run_id}").json()
        if r["status"] not in ("queued", "running"):
            return r
        time.sleep(0.05)
    raise RuntimeError("generation did not finish")


def flow(lec, st, saved, invite=INVITE, suffix=""):
    """The whole lecturer + student workflow. Works with TestClient or a live httpx.Client."""

    def save(name, method, path, resp):
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:2000]
        saved[name] = {"method": method, "path": path, "status": resp.status_code, "body": body}

    def get(c, name, path, **kw):
        r = c.get(path, **kw)
        save(name, "GET", path, r)
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text

    def call(c, name, method, path, **kw):
        r = c.request(method, path, **kw)
        save(name, method, path, r)
        return r.json() if r.content and r.headers.get("content-type", "").startswith("application/json") else None

    for c in (lec, st):
        c.headers.update({"X-Requested-With": "AdaptiveIQ"})
    get(lec, "health", "/api/health")
    get(lec, "auth_config", "/api/auth/config")
    call(lec, "auth_register_lecturer", "POST", "/api/auth/register", json={
        "email": f"lecturer{suffix}@example.edu", "password": "Passw0rd1", "full_name": "Sample Lecturer", "role": "lecturer",
        "invite_code": invite, "department": "DSAI"})
    call(st, "auth_register_student", "POST", "/api/auth/register", json={
        "email": f"student{suffix}@example.edu", "password": "Passw0rd1", "full_name": "Sample Student", "role": "student",
        "roll_number": "24BDS000", "program": "B.Tech DSAI", "semester": 3})
    get(st, "auth_me", "/api/auth/me")
    call(st, "auth_bad_login_401", "POST", "/api/auth/login", json={"email": f"student{suffix}@example.edu", "password": "nope"})
    call(st, "validation_422", "POST", "/api/auth/register", json={"email": "x", "password": "short", "full_name": "A"})

    course = call(lec, "lecturer_course_create", "POST", "/api/lecturer/courses", json={"code": "CS301", "title": "Operating Systems",
                                                                                        "term": "Odd 2026", "description": "Sample course"})
    cid = course["id"]
    subj = call(lec, "lecturer_subject_create", "POST", f"/api/lecturer/courses/{cid}/subjects",
                json={"name": "Operating Systems", "quiz_weight_cap_pct": 20})
    unit = call(lec, "lecturer_unit_create", "POST", f"/api/lecturer/subjects/{subj['id']}/units", json={"name": "Unit 2: Scheduling"})
    t1 = call(lec, "lecturer_topic_create", "POST", f"/api/lecturer/units/{unit['id']}/topics", json={"name": "CPU Scheduling"})
    t2 = call(lec, "lecturer_topic_create_2", "POST", f"/api/lecturer/units/{unit['id']}/topics",
              json={"name": "Round Robin", "prerequisite_topic_id": t1["id"]})
    call(lec, "lecturer_objective_create", "POST", f"/api/lecturer/topics/{t1['id']}/objectives",
         json={"text": "Compare FCFS, SJF and priority scheduling"})
    get(lec, "lecturer_courses", "/api/lecturer/courses")
    get(lec, "lecturer_course_detail", f"/api/lecturer/courses/{cid}")
    call(st, "student_join", "POST", "/api/student/courses/join", json={"join_code": course["join_code"]})
    get(st, "student_courses", "/api/student/courses")
    get(lec, "lecturer_roster", f"/api/lecturer/courses/{cid}/roster")
    call(lec, "lecturer_enroll", "POST", f"/api/lecturer/courses/{cid}/enroll", json={"emails": ["nobody@example.edu"]})
    get(lec, "topics_search", "/api/topics/search")
    get(st, "topics_search_student", "/api/topics/search")

    g = call(lec, "lecturer_generate", "POST", "/api/lecturer/generate", json={
        "course_id": cid, "subject_id": subj["id"], "topic_id": t1["id"], "title": "Scheduling quiz 1", "question_count": 5,
        "difficulty": "mixed", "reference_text": None})
    get(lec, "generation_status_running", f"/api/generation/{g['run_id']}")
    run = wait(lec, g["run_id"])
    get(lec, "generation_status_done", f"/api/generation/{g['run_id']}")
    get(lec, "generation_list", "/api/generation")
    qid = run["quiz_id"]
    quiz = get(lec, "lecturer_quiz_detail", f"/api/lecturer/quizzes/{qid}")
    call(lec, "lecturer_publish_unreviewed_422", "POST", f"/api/lecturer/quizzes/{qid}/publish")
    first = quiz["items"][0]["question"]["id"]
    for it in quiz["items"]:
        call(lec, "lecturer_review", "POST", f"/api/lecturer/questions/{it['question']['id']}/review", json={"action": "approve"})
    call(lec, "lecturer_question_edit", "PATCH", f"/api/lecturer/questions/{first}", json={"explanation": "Edited explanation."})
    call(lec, "lecturer_review", "POST", f"/api/lecturer/questions/{first}/review", json={"action": "approve", "note": "ok"})
    get(lec, "lecturer_question_history", f"/api/lecturer/questions/{first}/history")
    get(lec, "lecturer_question", f"/api/lecturer/questions/{first}")
    get(lec, "lecturer_questions_list", "/api/lecturer/questions", params={"course_id": cid})
    call(lec, "lecturer_question_create", "POST", "/api/lecturer/questions", json={
        "topic_id": t2["id"], "text": "In Round Robin scheduling, what happens when a time quantum expires?",
        "options": ["The process finishes", "The process is moved to the back of the ready queue",
                    "The process is terminated", "The CPU is idle"], "correct_label": "B", "difficulty": "easy",
        "explanation": "RR pre-empts the running process and re-queues it."})
    call(lec, "lecturer_quiz_update", "PATCH", f"/api/lecturer/quizzes/{qid}", json={
        "contribution_pct": 10, "feedback_release": "immediate", "attempts_allowed": 2, "time_limit_min": 20,
        "shuffle_questions": True, "shuffle_options": True})
    get(lec, "lecturer_quiz_preview", f"/api/lecturer/quizzes/{qid}/preview")
    call(lec, "lecturer_publish", "POST", f"/api/lecturer/quizzes/{qid}/publish")
    get(lec, "lecturer_quizzes", "/api/lecturer/quizzes")

    get(st, "student_assigned", "/api/student/quizzes/assigned")
    get(st, "student_quiz_card", f"/api/student/quizzes/{qid}")
    att = call(st, "student_start", "POST", f"/api/student/quizzes/{qid}/start")
    sid = att["session_id"]
    full = {it["question"]["id"]: it["question"] for it in lec.get(f"/api/lecturer/quizzes/{qid}").json()["items"]}
    for i, q in enumerate(att["questions"]):
        if i == 4:
            break
        right = i % 2 == 0
        oid = next(o["id"] for o in full[q["question_id"]]["options"] if o["is_correct"] == right)
        call(st, "student_save_answer", "PUT", f"/api/student/attempts/{sid}/answers/{q['question_id']}",
             json={"option_id": oid, "time_spent_s": 20, "confidence": 1 + i % 3})
    get(st, "student_attempt", f"/api/student/attempts/{sid}")
    call(st, "student_submit", "POST", f"/api/student/attempts/{sid}/submit")
    get(st, "student_result", f"/api/student/attempts/{sid}/result")

    pg = call(st, "student_practice_generate", "POST", "/api/student/practice/generate",
              json={"subject": "DBMS", "topic": "SQL joins", "question_count": 5, "difficulty": "adaptive"})
    prun = wait(st, pg["run_id"])
    get(st, "student_recommended_difficulty", "/api/student/practice/recommended-difficulty", params={"subject": "Operating Systems", "topic": "CPU Scheduling", "topic_id": t1["id"]})
    patt = call(st, "student_practice_start", "POST", f"/api/student/quizzes/{prun['quiz_id']}/start")
    pq = patt["questions"][0]
    st.put(f"/api/student/attempts/{patt['session_id']}/answers/{pq['question_id']}", json={"option_id": pq["options"][0]["id"]})
    call(st, "student_practice_check", "POST", f"/api/student/attempts/{patt['session_id']}/answers/{pq['question_id']}/check")
    call(st, "student_practice_submit", "POST", f"/api/student/attempts/{patt['session_id']}/submit")
    get(st, "student_practice_quizzes", "/api/student/quizzes/practice")
    get(st, "student_history", "/api/student/history")

    for name, path in [("overview", "/api/student/overview"), ("mastery", "/api/student/mastery"),
                       ("weak_areas", "/api/student/weak-areas"), ("question_status", "/api/student/question-status"),
                       ("trends", "/api/student/trends"), ("recommendations", "/api/student/recommendations"),
                       ("revision", "/api/student/revision"), ("confidence", "/api/student/confidence"),
                       ("study_plan", "/api/student/study-plan")]:
        get(st, f"student_{name}", path)
    get(st, "student_mastery_history", "/api/student/mastery/history", params={"subject": "Operating Systems", "topic": "CPU Scheduling", "topic_id": t1["id"]})
    call(st, "student_recommendations_refresh", "POST", "/api/student/recommendations/refresh")

    get(lec, "lecturer_overview", "/api/lecturer/overview")
    get(lec, "lecturer_course_analytics", f"/api/lecturer/courses/{cid}/analytics")
    get(lec, "lecturer_heatmap", f"/api/lecturer/courses/{cid}/heatmap")
    me = st.get("/api/auth/me").json()
    get(lec, "lecturer_heatmap_cell", f"/api/lecturer/courses/{cid}/heatmap/cell", params={"student_id": me["id"], "topic_id": t1["id"]})
    get(lec, "lecturer_quiz_question_analytics", f"/api/lecturer/quizzes/{qid}/question-analytics")
    get(lec, "lecturer_course_question_analytics", f"/api/lecturer/courses/{cid}/question-analytics")
    get(lec, "lecturer_insights", f"/api/lecturer/courses/{cid}/insights")
    get(lec, "lecturer_coverage", f"/api/lecturer/courses/{cid}/coverage")
    get(lec, "lecturer_model_quality", "/api/lecturer/model-quality")
    get(lec, "lecturer_students", "/api/lecturer/students")
    get(lec, "lecturer_student_profile", f"/api/lecturer/students/{me['id']}")
    get(lec, "lecturer_manual_export", f"/api/lecturer/quizzes/{qid}/export")
    get(lec, "lecturer_report_quiz_results_csv", f"/api/lecturer/reports/quizzes/{qid}/results.csv")
    get(lec, "google_status", "/api/integrations/google/status")
    get(lec, "google_connect_unconfigured", "/api/integrations/google/connect")
    get(lec, "google_exports", f"/api/lecturer/quizzes/{qid}/google-form/exports")
    call(lec, "lecturer_release_feedback", "POST", f"/api/lecturer/quizzes/{qid}/release-feedback")



def main():
    OUT.mkdir(parents=True, exist_ok=True)
    p = port()
    srv = fake_model_server.start(p)
    tmp = tempfile.mkdtemp()
    s = Settings(_env_file=None, environment="test", database_url=f"sqlite:///{tmp}/s.db", model_base_url=f"http://127.0.0.1:{p}",
                 lecturer_invite_code=INVITE, secret_key="sample-" + "x" * 40,
                 require_email_verification=False)
    app = create_app(s)
    Base.metadata.create_all(app.state.db.engine)
    saved = {}
    with TestClient(app) as lec, TestClient(app) as st:
        flow(lec, st, saved)
    srv.shutdown()
    for name, v in saved.items():
        (OUT / f"{name}.json").write_text(json.dumps(v, indent=2, default=str))
    (OUT / "README.md").write_text(
        "# API response samples\n\nGenerated by `python -m scripts.dump_api_samples` against an in-memory database and the "
        "TEST-ONLY fake model. Every name and number is a test fixture, not real data. Each file holds the method, path, "
        "status code and JSON body of one call.\n")
    print(f"wrote {len(saved)} samples to {OUT}")
    bad = {k: v["status"] for k, v in saved.items() if v["status"] >= 500 and not k.endswith("_unconfigured")}
    if bad:
        print("SERVER ERRORS:", bad)
        sys.exit(1)


def live(base_url, invite):
    """Fills a running backend (started with the TEST-ONLY fake model) so the UI has something to show.
    That backend must run with REQUIRE_EMAIL_VERIFICATION=false, since nobody can open the email links."""
    import httpx
    import uuid
    suffix = "-" + uuid.uuid4().hex[:6]
    with httpx.Client(base_url=base_url, timeout=60) as lec, httpx.Client(base_url=base_url, timeout=60) as st:
        flow(lec, st, {}, invite=invite, suffix=suffix)
    print(f"Seeded test data. Sign in as lecturer{suffix}@example.edu or student{suffix}@example.edu, password Passw0rd1")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", help="base URL of a running backend that uses the fake model, e.g. http://127.0.0.1:8000")
    ap.add_argument("--invite", default=INVITE, help="LECTURER_INVITE_CODE of that backend")
    a = ap.parse_args()
    live(a.live, a.invite) if a.live else main()
