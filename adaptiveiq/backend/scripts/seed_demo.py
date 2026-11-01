"""Fills the configured database with a clearly labelled DEMO course for presentations.

    python -m scripts.seed_demo            # uses DATABASE_URL from backend/.env

What it creates (all names say "Demo", emails end in @demo.example.com):
  - a demo lecturer and a course "DEMO-OS: Operating Systems (demo data)" with 5 topics and
    30 hand-written, reviewed questions (scripts/demo_questions.py)
  - two published assessments
  - 12 SYNTHETIC demo students whose answers are simulated (Rasch model, fixed seed), so the class
    analytics, heatmap and question statistics have something to show

The answers are simulated, not real student data, and every page that shows them belongs to the demo
course. It never changes or deletes anything that already exists: if the demo lecturer is already
there, it stops. Uses the app's own API in-process, so scoring and mastery run the real code.
"""
import math
import random
import sys

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.main import create_app
from app.models import LecturerProfile, StudentProfile, User
from app.models.base import utcnow
from scripts.demo_questions import TOPICS

PASSWORD = "DemoPass123"
LECTURER = "demo.lecturer@demo.example.com"
B = {"easy": -1.0, "medium": 0.0, "hard": 1.0}


def make_users(db):
    if db.scalar(select(User.id).where(User.email == LECTURER)):
        return None
    now = utcnow()
    lec = User(email=LECTURER, password_hash=hash_password(PASSWORD), full_name="Demo Lecturer", role="lecturer",
               email_verified_at=now, lecturer_profile=LecturerProfile(department="DSAI (demo)"))
    db.add(lec)
    students = []
    for i in range(1, 13):
        u = User(email=f"demo.student{i:02d}@demo.example.com", password_hash=hash_password(PASSWORD),
                 full_name=f"Demo Student {i:02d}", role="student", email_verified_at=now,
                 student_profile=StudentProfile(roll_number=f"DEMO{i:03d}", program="B.Tech DSAI (demo)", semester=5))
        db.add(u)
        students.append(u)
    db.commit()
    return lec, students


def client(app, email):
    c = TestClient(app)
    c.headers.update({"X-Requested-With": "AdaptiveIQ"})
    r = c.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    r.raise_for_status()
    return c


def ok(r, code=(200, 201)):
    if r.status_code not in code:
        raise SystemExit(f"{r.request.method} {r.request.url.path} -> {r.status_code}: {r.text[:300]}")
    return r.json()


def main():
    s = get_settings()
    app = create_app(s, start_worker=False)
    with app.state.db.session() as db:
        made = make_users(db)
    if made is None:
        print(f"Demo data is already present ({LECTURER}). Nothing was changed.")
        return
    rng = random.Random(2026)
    with TestClient(app):
        lec = client(app, LECTURER)
        course = ok(lec.post("/api/lecturer/courses", json={
            "code": "DEMO-OS", "title": "Operating Systems (demo data)", "term": "Demo",
            "description": "Demo course for presentations. Students and their answers are simulated."}))
        subj = ok(lec.post(f"/api/lecturer/courses/{course['id']}/subjects",
                           json={"name": "Operating Systems", "quiz_weight_cap_pct": 30}))
        units = {"Unit 1: Processes": ok(lec.post(f"/api/lecturer/subjects/{subj['id']}/units",
                                                   json={"name": "Unit 1: Processes"})),
                 "Unit 2: Memory": ok(lec.post(f"/api/lecturer/subjects/{subj['id']}/units",
                                               json={"name": "Unit 2: Memory"}))}
        topic_ids, question_ids = {}, {}
        for name, pre, qs in TOPICS:
            unit = units["Unit 2: Memory" if name in ("Memory Management", "Virtual Memory") else "Unit 1: Processes"]
            body = {"name": name}
            if pre:
                body["prerequisite_topic_id"] = topic_ids[pre]
            t = ok(lec.post(f"/api/lecturer/units/{unit['id']}/topics", json=body))
            topic_ids[name] = t["id"]
            question_ids[name] = []
            for d, text, opts, ans, expl in qs:
                q = ok(lec.post("/api/lecturer/questions", json={"topic_id": t["id"], "text": text, "options": opts,
                                                                 "correct_label": ans, "difficulty": d, "explanation": expl}))
                ok(lec.post(f"/api/lecturer/questions/{q['id']}/review", json={"action": "approve", "note": "Demo question"}))
                question_ids[name].append(q["id"])
        quizzes = []
        for title, names in (("Quiz 1: Scheduling and synchronization", ["CPU Scheduling", "Process Synchronization"]),
                             ("Quiz 2: Deadlocks and memory", ["Deadlocks", "Memory Management", "Virtual Memory"])):
            z = ok(lec.post("/api/lecturer/quizzes", params={"course_id": course["id"], "subject_id": subj["id"], "title": title}))
            ok(lec.post(f"/api/lecturer/quizzes/{z['id']}/items",
                        json={"add_question_ids": [q for n in names for q in question_ids[n]]}))
            ok(lec.patch(f"/api/lecturer/quizzes/{z['id']}", json={
                "contribution_pct": 10, "feedback_release": "immediate", "attempts_allowed": 1, "time_limit_min": 30,
                "instructions": "Demo assessment. Answer every question; skipped questions score zero."}))
            ok(lec.post(f"/api/lecturer/quizzes/{z['id']}/publish"))
            quizzes.append(z["id"])
        key = {}
        for zid in quizzes:
            for it in ok(lec.get(f"/api/lecturer/quizzes/{zid}"))["items"]:
                q = it["question"]
                key[q["id"]] = (q["difficulty"], q["topic"] if "topic" in q else None,
                                next(o["id"] for o in q["options"] if o["is_correct"]),
                                [o["id"] for o in q["options"] if not o["is_correct"]])
        topic_of = {qid: name for name, ids in question_ids.items() for qid in ids}

        for u in made[1]:
            st = client(app, u.email)
            ok(st.post("/api/student/courses/join", json={"join_code": course["join_code"]}))
            base = rng.gauss(0.2, 0.9)
            ability = {name: base + rng.gauss(0, 0.6) for name, _, _ in TOPICS}
            for zid in quizzes:
                att = ok(st.post(f"/api/student/quizzes/{zid}/start"))
                for q in att["questions"]:
                    d, _, right, wrong = key[q["question_id"]]
                    p = 1 / (1 + math.exp(-(ability[topic_of[q["question_id"]]] - B[d])))
                    if rng.random() < 0.06 * (1 - p):
                        continue                                   # skipped
                    correct = rng.random() < p
                    conf = 3 if (correct and rng.random() < 0.7) or (not correct and rng.random() < 0.25) else rng.choice([1, 2])
                    ok(st.put(f"/api/student/attempts/{att['session_id']}/answers/{q['question_id']}", json={
                        "option_id": right if correct else rng.choice(wrong), "confidence": conf,
                        "time_spent_s": round(rng.uniform(20, 90), 1)}))
                ok(st.post(f"/api/student/attempts/{att['session_id']}/submit"))
            st.close()
        lec.close()
    print("Demo data created (simulated students, clearly labelled).")
    print(f"  Lecturer: {LECTURER}")
    print("  Students: demo.student01@demo.example.com ... demo.student12@demo.example.com")
    print(f"  Password for all demo accounts: {PASSWORD}")


if __name__ == "__main__":
    sys.exit(main())
