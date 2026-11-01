"""End-to-end check against a RUNNING AdaptiveIQ with the REAL Qwen model (no stand-in).

It does, through the public API, exactly what a lecturer and a student would do, and checks every result
against the rules in app/ml:

  1. the backend is up and reports the model "ok"
  2. a lecturer creates a course, subject, unit and topic, and generates 5 questions with the real model
  3. every question's automatic-check results are printed (rejections, calculation check, similarity)
  4. the lecturer approves them and publishes the quiz
  5. a separate student joins, answers 3 right, 1 wrong and skips 1, and submits
  6. the score, mastery estimate, weak-area status and recommendations are compared with what the rules
     in app/ml say they must be for exactly those answers
  7. after you restart the services, `--after-restart` signs in again and checks that the quiz, the
     attempt, the result and the mastery estimate are all still there and unchanged

Usage (backend folder, with the backend and llama-server already running, email verification OFF):

    python -m scripts.real_model_check --url http://localhost:8000 --invite YOUR_INVITE_CODE
    (stop and start the backend and the model, or `docker compose restart`)
    python -m scripts.real_model_check --url http://localhost:8000 --after-restart

With Docker use --url http://localhost:8088 . Add --reference notes.txt to generate from your own notes.
A report is written to evaluation/results/real_model_check_<time>.md and the ids to
evaluation/results/real_model_check_state.json (needed by --after-restart).
"""
import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.ml import mastery, weak_areas

RESULTS = Path(__file__).resolve().parents[1] / "evaluation" / "results"
STATE = RESULTS / "real_model_check_state.json"
PASSWORD = "CheckPass123"
PLAN = ["right", "right", "right", "wrong", "skip"]          # what the student does on questions 1..5


class Report:
    def __init__(self):
        self.lines, self.failures = [], 0

    def say(self, text=""):
        print(text)
        self.lines.append(text)

    def check(self, ok: bool, what: str, detail: str = ""):
        self.failures += 0 if ok else 1
        self.say(f"- [{'PASS' if ok else 'FAIL'}] {what}" + (f": {detail}" if detail else ""))
        return ok

    def save(self, title: str) -> Path:
        RESULTS.mkdir(parents=True, exist_ok=True)
        p = RESULTS / f"real_model_check_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        p.write_text(f"# {title}\n\n" + "\n".join(self.lines) + "\n")
        return p


def client(url: str) -> httpx.Client:
    return httpx.Client(base_url=url, timeout=60, headers={"X-Requested-With": "AdaptiveIQ", "Origin": url})


def ok(r: httpx.Response, what: str) -> dict:
    if r.status_code >= 400:
        sys.exit(f"Stopped: {what} failed with {r.status_code}: {r.text[:400]}")
    return r.json() if r.content else {}


def expected_for(questions: list[dict]) -> mastery.MasteryEstimate:
    """The estimate app/ml/mastery.py must produce for the planned answers (all given just now)."""
    now = datetime.now(timezone.utc)
    obs = [mastery.Observation(q["id"], {"right": True, "wrong": False, "skip": None}[plan], q["difficulty"], now)
           for q, plan in zip(questions, PLAN)]
    return mastery.estimate(obs, now)


def run(a) -> int:
    rep = Report()
    lec, st = client(a.url), client(a.url)
    rep.say(f"Server: {a.url}  ·  {datetime.now().isoformat(timespec='seconds')}\n")

    rep.say("## 1. Health")
    h = ok(lec.get("/api/health"), "health")
    rep.say(f"Database: {h['database_engine']}  ·  model: {h['model']['name']} ({h['model']['variant']}, "
            f"{h['model']['quantization']})  ·  calculation check: {h.get('math_check')}")
    if not rep.check(h["model"]["state"] == "ok", "model is reachable", h["model"].get("detail") or ""):
        rep.say("Start llama-server with the GGUF (see README) and run this again.")
        return 1
    if h["email"]["verification_required"]:
        sys.exit("Stopped: set REQUIRE_EMAIL_VERIFICATION=false in backend/.env for this check, then restart.")

    rep.say("\n## 2. Lecturer builds a course and generates 5 questions")
    tag = uuid.uuid4().hex[:6]
    lec_email, st_email = f"realcheck.lecturer.{tag}@example.com", f"realcheck.student.{tag}@example.com"
    ok(lec.post("/api/auth/register", json={"email": lec_email, "password": PASSWORD, "full_name": "Real Check Lecturer",
                                             "role": "lecturer", "invite_code": a.invite}), "lecturer registration")
    course = ok(lec.post("/api/lecturer/courses", json={"code": f"RC{tag[:4].upper()}",
                                                        "title": "Real model check (test data)"}), "create course")
    subj = ok(lec.post(f"/api/lecturer/courses/{course['id']}/subjects",
                       json={"name": a.subject, "quiz_weight_cap_pct": 20}), "create subject")
    unit = ok(lec.post(f"/api/lecturer/subjects/{subj['id']}/units", json={"name": "Unit 1"}), "create unit")
    topic = ok(lec.post(f"/api/lecturer/units/{unit['id']}/topics", json={"name": a.topic}), "create topic")
    body = {"course_id": course["id"], "subject_id": subj["id"], "topic_id": topic["id"], "title": "Real model check quiz",
            "question_count": 5, "difficulty": "mixed"}
    if a.reference:
        body["reference_text"] = Path(a.reference).read_text(encoding="utf-8")
    run_ = ok(lec.post("/api/lecturer/generate", json=body), "start generation")
    started, last = time.time(), None
    while run_["status"] in ("queued", "running"):
        if time.time() - started > a.timeout_min * 60:
            sys.exit(f"Stopped: generation did not finish in {a.timeout_min} minutes.")
        time.sleep(5)
        run_ = ok(lec.get(f"/api/generation/{run_['run_id']}"), "generation status")
        line = f"  {run_['stage']} · {run_['ready']}/{run_['total']} ready · {run_['attempts']} model calls"
        if line != last:
            print(line)
            last = line
    rep.say(f"Run finished: **{run_['status']}** in {run_['elapsed_s']:.0f} s, {run_['ready']}/{run_['total']} questions "
            f"passed the checks, {run_['attempts']} model calls, grounded on {run_.get('grounded_on')}.")
    for k, n in (run_.get("rejected") or {}).items():
        if n:
            rep.say(f"  rejected {n} × {run_['rejected_reasons'].get(k, k)}")
    rep.check(run_["status"] == "done" and run_["ready"] == 5, "all 5 questions generated", run_.get("error") or "")
    if run_["ready"] < 5:
        rep.say("The rest of the check needs 5 questions. Generate again or look at the rejection reasons above.")
        rep.say(f"\nReport: {rep.save('Real model check')}")
        return 1

    rep.say("\n## 3. Questions and their automatic checks")
    quiz_id = run_["quiz_id"]
    quiz = ok(lec.get(f"/api/lecturer/quizzes/{quiz_id}"), "quiz detail")
    questions = [it["question"] for it in quiz["items"]]
    for i, q in enumerate(questions, 1):
        v = q.get("validation") or {}
        key = next(o["text"] for o in q["options"] if o["is_correct"])
        rep.say(f"{i}. [{q['difficulty']}] {q['text']}")
        rep.say(f"   options: {' | '.join(o['text'] for o in q['options'])}  ·  key: {key}")
        rep.say(f"   calculation check: {v.get('math_status', 'not numeric')}  ·  closest existing question: "
                f"{round((v.get('max_similarity') or 0) * 100)}% shared wording"
                + (f"  ·  word overlap with reference: {round(v['grounding'] * 100)}%" if v.get("grounding") is not None else ""))
    rep.say("Read each question yourself: the checks cannot prove a question is factually correct.")

    rep.say("\n## 4. Approve and publish")
    for q in questions:
        ok(lec.post(f"/api/lecturer/questions/{q['id']}/review", json={"action": "approve"}), "approve")
    ok(lec.patch(f"/api/lecturer/quizzes/{quiz_id}", json={"contribution_pct": 10}), "settings")
    rep.check(lec.post(f"/api/lecturer/quizzes/{quiz_id}/publish").status_code == 200, "quiz published")

    rep.say("\n## 5. Student joins, answers 3 right, 1 wrong, skips 1, submits")
    ok(st.post("/api/auth/register", json={"email": st_email, "password": PASSWORD, "full_name": "Real Check Student",
                                            "role": "student"}), "student registration")
    ok(st.post("/api/student/courses/join", json={"join_code": course["join_code"]}), "join course")
    att = ok(st.post(f"/api/student/quizzes/{quiz_id}/start"), "start attempt")
    by_id = {q["id"]: q for q in questions}
    ordered = [by_id[x["question_id"]] for x in att["questions"]]          # the order the student sees
    for q, plan in zip(ordered, PLAN):
        if plan == "skip":
            continue
        opt = next(o["id"] for o in q["options"] if o["is_correct"] == (plan == "right"))
        ok(st.put(f"/api/student/attempts/{att['session_id']}/answers/{q['id']}", json={"option_id": opt}), "save answer")
    res = ok(st.post(f"/api/student/attempts/{att['session_id']}/submit"), "submit")

    rep.say("\n## 6. Results compared with the rules")
    rep.check((res["correct"], res["incorrect"], res["unanswered"]) == (3, 1, 1), "right / wrong / skipped counts",
              f"{res['correct']} / {res['incorrect']} / {res['unanswered']}")
    rep.check(abs(res["percentage"] - 60.0) < 1e-6, "percentage = 3 of 5 marks", f"{res['percentage']}%")
    rep.check(abs((res["contribution_earned"] or 0) - 6.0) < 1e-6, "contribution = 60% of 10%", str(res["contribution_earned"]))
    exp = expected_for(ordered)
    rows = ok(st.get("/api/student/mastery"), "mastery")["topics"]
    row = next((r for r in rows if r["topic_key"] == f"t:{topic['id']}"), None)
    if rep.check(row is not None, "topic appears on My Progress"):
        rep.check(abs(row["score_100"] - mastery.pct100(exp.score)) <= 1, "mastery score matches the formula",
                  f"app {row['score_100']}/100, formula {mastery.pct100(exp.score)}/100")
        rep.check(row["label"] == exp.label, "mastery label matches", f"{row['label']} vs {exp.label}")
        rep.check((row["correct"], row["incorrect"], row["skipped"]) == (3, 1, 1), "evidence counts", str(row["explanation"]))
    status = weak_areas.classify(exp).status
    weak = ok(st.get("/api/student/weak-areas"), "weak areas")
    in_weak = any(r["topic_key"] == f"t:{topic['id']}" for r in weak.get("weak", []))
    rep.check(in_weak == (status == "weak"), "weak-area status matches", f"expected '{status}'")
    recos = ok(st.get("/api/student/recommendations"), "recommendations")
    has_reco = any(r["topic_key"] == f"t:{topic['id']}" for r in recos)
    rep.check(has_reco == (status in ("weak", "developing", "insufficient_evidence")), "recommendation present when expected",
              f"status '{status}', {len(recos)} recommendation(s)")

    RESULTS.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"url": a.url, "lecturer": lec_email, "student": st_email, "password": PASSWORD,
                                 "quiz_id": quiz_id, "session_id": att["session_id"], "topic_key": f"t:{topic['id']}",
                                 "result": {k: res[k] for k in ("correct", "incorrect", "unanswered", "percentage")},
                                 "score_100": row["score_100"] if row else None,
                                 "question_ids": [q["id"] for q in questions]}, indent=2))
    rep.say(f"\n{'All checks passed.' if rep.failures == 0 else f'{rep.failures} check(s) FAILED.'} "
            "Now restart the backend and the model, then run with --after-restart.")
    rep.say(f"Report: {rep.save('Real model check')}")
    return 1 if rep.failures else 0


def after_restart(a) -> int:
    rep = Report()
    if not STATE.exists():
        sys.exit("No saved state: run the check without --after-restart first.")
    s = json.loads(STATE.read_text())
    url = a.url or s["url"]
    lec, st = client(url), client(url)
    rep.say(f"Server: {url}  ·  {datetime.now().isoformat(timespec='seconds')} (after restart)\n")
    h = ok(lec.get("/api/health"), "health")
    rep.check(h["status"] == "ok", "backend and database are up", h["database_engine"])
    rep.check(h["model"]["state"] == "ok", "model is reachable again", h["model"].get("detail") or "")
    rep.check(lec.post("/api/auth/login", json={"email": s["lecturer"], "password": s["password"]}).status_code == 200,
              "lecturer can sign in")
    quiz = lec.get(f"/api/lecturer/quizzes/{s['quiz_id']}")
    rep.check(quiz.status_code == 200 and quiz.json()["status"] == "published", "published quiz is still there")
    if quiz.status_code == 200:
        rep.check(sorted(it["question"]["id"] for it in quiz.json()["items"]) == sorted(s["question_ids"]),
                  "same 5 questions")
    rep.check(st.post("/api/auth/login", json={"email": s["student"], "password": s["password"]}).status_code == 200,
              "student can sign in")
    res = st.get(f"/api/student/attempts/{s['session_id']}/result")
    if rep.check(res.status_code == 200, "submitted attempt and result are still there"):
        r = res.json()
        rep.check({k: r[k] for k in s["result"]} == s["result"], "result unchanged", str(s["result"]))
    rows = ok(st.get("/api/student/mastery"), "mastery")["topics"]
    row = next((x for x in rows if x["topic_key"] == s["topic_key"]), None)
    rep.check(row is not None and abs(row["score_100"] - s["score_100"]) <= 1, "mastery estimate unchanged",
              f"{row['score_100'] if row else None}/100 vs {s['score_100']}/100 before")
    rep.say(f"\n{'All checks passed.' if rep.failures == 0 else f'{rep.failures} check(s) FAILED.'}")
    rep.say(f"Report: {rep.save('Real model check after restart')}")
    return 1 if rep.failures else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default=None, help="backend or Docker address, e.g. http://localhost:8000")
    ap.add_argument("--invite", default="", help="LECTURER_INVITE_CODE from backend/.env")
    ap.add_argument("--subject", default="Operating Systems")
    ap.add_argument("--topic", default="CPU Scheduling")
    ap.add_argument("--reference", help="a .txt file of notes to generate from")
    ap.add_argument("--timeout-min", type=int, default=60, help="how long generation may take")
    ap.add_argument("--after-restart", action="store_true")
    a = ap.parse_args()
    if a.after_restart:
        sys.exit(after_restart(a))
    a.url = a.url or "http://localhost:8000"
    sys.exit(run(a))


if __name__ == "__main__":
    main()
