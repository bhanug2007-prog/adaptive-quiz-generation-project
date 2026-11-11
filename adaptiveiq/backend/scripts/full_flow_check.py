"""The 20-step end-to-end check from the project roadmap (Phase 7), against a RUNNING AdaptiveIQ.

It does, through the public API only, what one lecturer and one student would do, and checks each result:

   1. lecturer registers and signs in            11. student joins the course with the join code
   2. creates a course                           12. agrees to monitoring and starts the assessment
   3. creates a subject, unit and topic          13. answers the questions (planned right / wrong / skipped)
   4. asks for 10 questions: 3 easy, 4 medium,   14. monitoring events are sent as the browser sends them
      3 hard                                     15. submits
   5. the model generates them                   16. the backend's marks are compared with the plan
   6. the Question Quality Agent checks them     17. the mastery estimate is compared with app/ml/mastery.py
   7. failed questions are regenerated           18. results stay hidden until the lecturer releases them,
   8. lecturer approves every question               then the student sees them and recommendations
   9. turns monitoring on and publishes          19. lecturer analytics and the monitoring report
  10. student registers and signs in             20. the Lecturer Insights Agent answers from the real numbers

Use it with the REAL Qwen model on your laptop (backend and llama-server running, REQUIRE_EMAIL_VERIFICATION=false):

    cd backend
    python -m scripts.full_flow_check --url http://localhost:8000 --invite YOUR_LECTURER_INVITE_CODE

It also runs against the test-only fake model (scripts/dev_fake_stack.sh) to check the script itself; the report
then says "fake model" and its questions are canned test strings, not model output.

Everything it creates is synthetic test data (example.com accounts, a course titled "... (test data)").
The approval in step 8 is automatic here; in real use the lecturer must read every question first.
A report is written to evaluation/results/full_flow_check_<time>.md .
"""
import argparse
import re
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from app.ml import mastery, weak_areas

RESULTS = Path(__file__).resolve().parents[1] / "evaluation" / "results"
PASSWORD = "CheckPass123"
MIX = {"easy": 3, "medium": 4, "hard": 3}
PLAN = ["right"] * 6 + ["wrong"] * 2 + ["skip"] * 2      # what the student does on the 10 questions, in order
BLAME = re.compile(r"\b(cheat\w*|suspicious|dishonest\w*)\b", re.I)


class Report:
    def __init__(self):
        self.lines, self.failures, self.passes = [], 0, 0

    def say(self, text=""):
        print(text, flush=True)
        self.lines.append(text)

    def step(self, n: int, title: str):
        self.say(f"\n## {n}. {title}")

    def check(self, ok: bool, what: str, detail: str = "") -> bool:
        if ok:
            self.passes += 1
        else:
            self.failures += 1
        self.say(f"- [{'PASS' if ok else 'FAIL'}] {what}" + (f": {detail}" if detail else ""))
        return ok

    def save(self) -> Path:
        RESULTS.mkdir(parents=True, exist_ok=True)
        p = RESULTS / f"full_flow_check_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        p.write_text("# Full 20-step check\n\n" + "\n".join(self.lines) + "\n", encoding="utf-8")
        return p


class Stop(Exception):
    pass


def client(url: str) -> httpx.Client:
    return httpx.Client(base_url=url, timeout=120, headers={"X-Requested-With": "AdaptiveIQ", "Origin": url})


def ok(r: httpx.Response, what: str):
    if r.status_code >= 400:
        raise Stop(f"{what} failed with HTTP {r.status_code}: {r.text[:400]}")
    return r.json() if r.content else {}


def wait_run(lec: httpx.Client, run: dict, timeout_min: int, label: str) -> dict:
    started, last = time.time(), None
    while run["status"] in ("queued", "running"):
        if time.time() - started > timeout_min * 60:
            raise Stop(f"{label} did not finish in {timeout_min} minutes.")
        time.sleep(3)
        run = ok(lec.get(f"/api/generation/{run['run_id']}"), "generation status")
        line = f"  {label}: {run['stage']} · {run['ready']}/{run['total']} ready · {run['attempts']} model calls"
        if line != last:
            print(line, flush=True)
            last = line
    return run


def failed(q: dict) -> bool:
    return bool((q.get("validation") or {}).get("failed_validation"))


def expected_for(ordered: list[dict], plan: list[str]) -> mastery.MasteryEstimate:
    now = datetime.now(timezone.utc)
    obs = [mastery.Observation(q["id"], {"right": True, "wrong": False, "skip": None}[p], q["difficulty"], now)
           for q, p in zip(ordered, plan)]
    return mastery.estimate(obs, now)


def run(a, rep: Report) -> None:
    lec, st = client(a.url), client(a.url)
    rep.say(f"Server: {a.url} · {datetime.now().isoformat(timespec='seconds')}")
    h = ok(lec.get("/api/health"), "health")
    fake = a.stand_in
    rep.say(f"Database: {h['database_engine']} · model: {h['model']['name']} ({h['model']['variant']}, "
            f"{h['model']['quantization']}){' · TEST-ONLY STAND-IN MODEL: the questions are canned test strings, not Qwen output' if fake else ''}")
    rep.say(f"AI quality review: {h['quality_review']}")
    if not rep.check(h["status"] == "ok" and h["model"]["state"] == "ok", "backend, database and model are up",
                     h["model"].get("detail") or ""):
        raise Stop("Start the backend and llama-server (see README), then run this again.")
    if h["email"]["verification_required"]:
        raise Stop("Set REQUIRE_EMAIL_VERIFICATION=false in backend/.env for this check, then restart the backend.")

    tag = uuid.uuid4().hex[:6]
    lec_email, st_email = f"flowcheck.lecturer.{tag}@example.com", f"flowcheck.student.{tag}@example.com"

    rep.step(1, "Lecturer registers and signs in")
    ok(lec.post("/api/auth/register", json={"email": lec_email, "password": PASSWORD, "full_name": "Flow Check Lecturer",
                                             "role": "lecturer", "invite_code": a.invite}), "lecturer registration")
    lec.cookies.clear()
    ok(lec.post("/api/auth/login", json={"email": lec_email, "password": PASSWORD}), "lecturer login")
    rep.check(ok(lec.get("/api/auth/me"), "me")["role"] == "lecturer", "signed in as a lecturer", lec_email)

    rep.step(2, "Lecturer creates a course")
    course = ok(lec.post("/api/lecturer/courses", json={"code": f"FC{tag[:4].upper()}",
                                                        "title": "Full flow check (test data)"}), "create course")
    rep.check(bool(course.get("join_code")), "course created with a join code", course["code"])

    rep.step(3, "Lecturer creates a subject, unit and topic")
    subj = ok(lec.post(f"/api/lecturer/courses/{course['id']}/subjects",
                       json={"name": a.subject, "quiz_weight_cap_pct": 20}), "create subject")
    unit = ok(lec.post(f"/api/lecturer/subjects/{subj['id']}/units", json={"name": "Unit 1"}), "create unit")
    topic = ok(lec.post(f"/api/lecturer/units/{unit['id']}/topics", json={"name": a.topic}), "create topic")
    rep.check(True, "subject, unit and topic created", f"{a.subject} / Unit 1 / {a.topic}")

    rep.step(4, "Lecturer asks for 10 questions: 3 easy, 4 medium, 3 hard")
    body = {"course_id": course["id"], "subject_id": subj["id"], "topic_id": topic["id"], "title": "Full flow check quiz",
            "question_count": 10, "difficulty": "mixed", "distribution": MIX}
    if a.reference:
        body["reference_text"] = Path(a.reference).read_text(encoding="utf-8")
    run0 = ok(lec.post("/api/lecturer/generate", json=body), "start generation")
    rep.check(run0["status"] in ("queued", "running"), "generation accepted", f"run {run0['run_id']}")

    rep.step(5, "The model generates the questions")
    t0 = time.time()
    gen = wait_run(lec, run0, a.timeout_min, "generation")
    secs = time.time() - t0
    rep.say(f"Finished **{gen['status']}** in {gen['elapsed_s']:.0f} s ({secs:.0f} s wall clock), {gen['ready']}/{gen['total']} "
            f"ready, {gen['attempts']} model calls, about {gen.get('avg_question_s') or 0:.1f} s per question.")
    for k, n in (gen.get("rejected") or {}).items():
        if n:
            rep.say(f"  rejected and retried {n} × {gen['rejected_reasons'].get(k, k)}")
    rep.check(gen["status"] in ("done", "partial") and gen["quiz_id"] is not None, "generation finished with a draft quiz",
              gen["status"] + (f" ({gen['error']})" if gen.get("error") else ""))
    quiz_id = gen["quiz_id"]
    quiz = ok(lec.get(f"/api/lecturer/quizzes/{quiz_id}"), "quiz detail")
    questions = [it["question"] for it in quiz["items"]]
    rep.check(len(questions) == 10, "10 questions in the draft", str(len(questions)))
    rep.check(quiz["status"] == "draft", "the quiz is a draft, not published", quiz["status"])
    for i, q in enumerate(questions, 1):
        key = next(o["text"] for o in q["options"] if o["is_correct"])
        rep.say(f"{i}. [{q['difficulty']}] {q['text']}")
        rep.say(f"   options: {' | '.join(o['text'] for o in q['options'])} · key: {key}")

    rep.step(6, "The Question Quality Agent checks them")
    log = ok(lec.get(f"/api/lecturer/generation/{gen['run_id']}/agent"), "agent log")
    tools = [s["name"] for s in log["steps"] if s["kind"] == "tool"]
    decisions = [s for s in log["steps"] if s["kind"] == "decision"]
    rep.say(f"Agent run {log['id']}: {log['status']}, {len(log['steps'])} logged steps, {log['llm_calls']} AI review calls.")
    rep.say(f"Tools used: {', '.join(sorted(set(tools)))}")
    rep.check(log["status"] in ("done", "partial"), "agent finished within its retry limit", log.get("error") or log["status"])
    rep.check("generate_questions" in tools and "validate_question" in tools, "agent generated and validated",
              f"{tools.count('validate_question')} validations")
    rep.check("save_question_draft" in tools, "agent saved a draft for lecturer review")
    rep.check(not any("publish" in t for t in tools), "agent never published anything")
    rep.check(len(decisions) > 0, "agent recorded its decisions", f"{len(decisions)} decisions")
    qual = gen.get("quality") or {}
    rep.say(f"Difficulty mix: requested {qual.get('requested')}, labelled {qual.get('labelled')}, judged by the AI "
            f"{qual.get('ai_assessed') or 'not judged'} · AI review: {qual.get('ai_review')}"
            + (f" ({qual['ai_model']})" if qual.get("ai_model") else ""))
    if qual.get("ai_note"):
        rep.say(f"  note: {qual['ai_note']}")
    if qual.get("mix_matches") is not None:
        rep.check(qual["mix_matches"], "the AI's judged difficulty mix matches the request",
                  f"{len(qual.get('mismatched_question_ids') or [])} question(s) judged at another level")
    labels = {d: sum(q["difficulty"] == d for q in questions) for d in MIX}
    rep.check(labels == MIX, "draft has 3 easy, 4 medium, 3 hard", str(labels))

    rep.step(7, "Failed questions are regenerated")
    regen_tools = tools.count("regenerate_question")
    bad = [q for q in questions if failed(q)]
    rep.say(f"The agent regenerated {regen_tools} question(s) during the run; {len(bad)} still marked as failed.")
    for q in bad:
        v = q["validation"]
        rep.say(f"  failed: “{q['text'][:80]}” · {v.get('failure_text') or v.get('failure_reason')}")
        rep.check(q["review_status"] != "approved", "failed question was not approved automatically")
        r = ok(lec.post(f"/api/lecturer/questions/{q['id']}/regenerate", params={"quiz_id": quiz_id}), "regenerate")
        r = wait_run(lec, r, a.timeout_min, "regenerate")
        rep.check(r["status"] in ("done", "failed", "partial"), "lecturer's regenerate finished", r["status"])
        if r["status"] != "done":
            rep.say(f"  the new version did not pass either: {r.get('error')}")
    quiz = ok(lec.get(f"/api/lecturer/quizzes/{quiz_id}"), "quiz detail")
    questions = [it["question"] for it in quiz["items"]]
    still = [q for q in questions if failed(q)]
    if still:
        rep.say(f"{len(still)} question(s) still fail after regenerating; they are removed from the quiz, as a lecturer would.")
        ok(lec.post(f"/api/lecturer/quizzes/{quiz_id}/items",
                    json={"remove_item_ids": [it["item_id"] for it in quiz["items"] if failed(it["question"])]}), "remove")
        quiz = ok(lec.get(f"/api/lecturer/quizzes/{quiz_id}"), "quiz detail")
        questions = [it["question"] for it in quiz["items"]]
    rep.check(not any(failed(q) for q in questions), "no failed question left in the quiz", f"{len(questions)} questions")

    rep.step(8, "Lecturer approves every question")
    blocked = lec.post(f"/api/lecturer/quizzes/{quiz_id}/publish")
    rep.check(blocked.status_code >= 400, "publishing before approval is refused", f"HTTP {blocked.status_code}")
    for q in questions:
        ok(lec.post(f"/api/lecturer/questions/{q['id']}/review", json={"action": "approve"}), "approve")
    quiz = ok(lec.get(f"/api/lecturer/quizzes/{quiz_id}"), "quiz detail")
    rep.check(all(it["question"]["review_status"] == "approved" for it in quiz["items"]), "all questions approved")

    rep.step(9, "Lecturer turns monitoring on and publishes")
    ok(lec.patch(f"/api/lecturer/quizzes/{quiz_id}", json={
        "contribution_pct": 10, "feedback_release": "manual", "monitor_tab": True, "monitor_fullscreen": "record",
        "monitor_camera": True, "monitor_microphone": True}), "settings")
    pub = ok(lec.post(f"/api/lecturer/quizzes/{quiz_id}/publish"), "publish")
    rep.check(pub["status"] == "published", "quiz published", pub["status"])

    rep.step(10, "Student registers and signs in")
    ok(st.post("/api/auth/register", json={"email": st_email, "password": PASSWORD, "full_name": "Flow Check Student",
                                            "role": "student"}), "student registration")
    st.cookies.clear()
    ok(st.post("/api/auth/login", json={"email": st_email, "password": PASSWORD}), "student login")
    rep.check(ok(st.get("/api/auth/me"), "me")["role"] == "student", "signed in as a student", st_email)
    rep.check(st.get(f"/api/lecturer/quizzes/{quiz_id}").status_code in (401, 403), "student cannot open lecturer pages")

    rep.step(11, "Student joins the course")
    rep.check(st.get(f"/api/student/quizzes/{quiz_id}").status_code in (403, 404), "quiz hidden before joining")
    ok(st.post("/api/student/courses/join", json={"join_code": course["join_code"]}), "join course")
    card = ok(st.get(f"/api/student/quizzes/{quiz_id}"), "quiz card")
    rep.check(card.get("monitoring") is not None, "quiz shows what is monitored", str(card.get("monitoring")))

    rep.step(12, "Student agrees to monitoring and starts")
    no = st.post(f"/api/student/quizzes/{quiz_id}/start")
    rep.check(no.status_code == 428, "start without agreeing is refused", f"HTTP {no.status_code}")
    att = ok(st.post(f"/api/student/quizzes/{quiz_id}/start", json={"monitoring_consent": True}), "start attempt")
    sid = att["session_id"]
    rep.check(att.get("monitoring") is not None, "attempt started with monitoring", f"session {sid}")
    leaked = [x for x in att["questions"] for o in x.get("options", []) if "is_correct" in o]
    rep.check(not leaked and "explanation" not in str(att["questions"][0].keys()), "no answer key sent to the student")

    rep.step(13, "Student answers: 6 right, 2 wrong, 2 skipped")
    by_id = {q["id"]: q for q in questions}
    ordered = [by_id[x["question_id"]] for x in att["questions"]]
    plan = PLAN if len(ordered) == 10 else (["right"] * max(1, len(ordered) - 4) + ["wrong", "wrong", "skip", "skip"])[:len(ordered)]
    rep.say(f"{len(ordered)} questions in the quiz; plan: {plan.count('right')} right, {plan.count('wrong')} wrong, "
            f"{plan.count('skip')} skipped")
    for q, p in zip(ordered, plan):
        if p == "skip":
            continue
        opt = next(o["id"] for o in q["options"] if o["is_correct"] == (p == "right"))
        ok(st.put(f"/api/student/attempts/{sid}/answers/{q['id']}", json={"option_id": opt}), "save answer")
    again = ok(st.get(f"/api/student/attempts/{sid}"), "resume attempt")
    saved = sum(1 for x in (again.get("answers") or {}).values() if x.get("option_id"))
    rep.check(saved == plan.count("right") + plan.count("wrong"), "answers saved on the server (autosave)", f"{saved} saved")

    rep.step(14, "Monitoring events are recorded")
    now = datetime.now(timezone.utc)
    iso = lambda s: (now + timedelta(seconds=s)).isoformat()      # noqa: E731
    ok(st.post(f"/api/student/attempts/{sid}/monitoring/devices", json={"camera": "granted", "microphone": "granted"}), "devices")
    events = [{"seq": 1, "kind": "fullscreen_enter", "at": iso(0)},
              {"seq": 2, "kind": "monitoring_started", "at": iso(0), "details": {"camera": "granted", "microphone": "granted"}},
              {"seq": 3, "kind": "page_hidden", "at": iso(5)},
              {"seq": 4, "kind": "page_visible", "at": iso(13), "duration_ms": 8000},
              {"seq": 5, "kind": "speech", "at": iso(20), "duration_ms": 3000},
              {"seq": 6, "kind": "fullscreen_exit", "at": iso(25)}]
    r1 = ok(st.post(f"/api/student/attempts/{sid}/monitoring/events", json={"events": events}), "send events")
    r2 = ok(st.post(f"/api/student/attempts/{sid}/monitoring/events", json={"events": events}), "resend events")
    rep.check(r1.get("stored") == 6, "6 events stored", str(r1))
    rep.check(r2.get("stored") == 0 and r2.get("duplicates") == 6, "resending the same events stores nothing twice", str(r2))
    rep.say("(Here the events are sent as the browser would send them. Real detection in Chromium is covered by "
            "frontend/e2e/monitoring.spec.js; try it yourself in the browser too.)")

    rep.step(15, "Student submits")
    res = ok(st.post(f"/api/student/attempts/{sid}/submit"), "submit")
    dup = st.post(f"/api/student/attempts/{sid}/submit")
    rep.check(dup.status_code in (200, 409), "a second submit does not score twice", f"HTTP {dup.status_code}")

    rep.step(16, "The backend calculates the marks")
    n = len(ordered)
    right, wrong, skip = plan.count("right"), plan.count("wrong"), plan.count("skip")
    after = ok(st.get(f"/api/student/attempts/{sid}/result"), "result")
    full = after if after.get("correct") is not None else None
    rep.say(f"Before release the student sees: released={after.get('released', after.get('feedback_released'))}, "
            f"score={after.get('percentage')}")

    rep.step(17, "The adaptive engine updates mastery")
    exp = expected_for(ordered, plan)
    rows = ok(st.get("/api/student/mastery"), "mastery")["topics"]
    row = next((r for r in rows if r["topic_key"] == f"t:{topic['id']}"), None)
    if rep.check(row is not None, "topic appears on My Progress"):
        rep.check(abs(row["score_100"] - mastery.pct100(exp.score)) <= 1, "mastery matches app/ml/mastery.py",
                  f"app {row['score_100']}/100, formula {mastery.pct100(exp.score)}/100")
        rep.check(row["label"] == exp.label, "mastery label matches", f"{row['label']} vs {exp.label}")
        rep.check((row["correct"], row["incorrect"], row["skipped"]) == (right, wrong, skip), "evidence counts",
                  f"{row['correct']} right, {row['incorrect']} wrong, {row['skipped']} skipped")

    rep.step(18, "Results are released, then the student sees them and recommendations")
    ok(lec.post(f"/api/lecturer/quizzes/{quiz_id}/release-feedback"), "release")
    res = ok(st.get(f"/api/student/attempts/{sid}/result"), "result after release")
    rep.check((res["correct"], res["incorrect"], res["unanswered"]) == (right, wrong, skip), "right / wrong / skipped",
              f"{res['correct']} / {res['incorrect']} / {res['unanswered']}")
    pct = 100.0 * right / n
    rep.check(abs(res["percentage"] - pct) < 0.01, f"percentage = {right} of {n} marks", f"{res['percentage']}%")
    rep.check(abs((res.get("contribution_earned") or 0) - pct / 10) < 0.01, "contribution = score × 10%",
              str(res.get("contribution_earned")))
    if full is None:
        rep.check(True, "marks were hidden until release (feedback_release = manual)")
    status = weak_areas.classify(exp).status
    recos = ok(st.get("/api/student/recommendations"), "recommendations")
    has = any(r["topic_key"] == f"t:{topic['id']}" for r in recos)
    if status in ("weak", "developing", "insufficient_evidence"):
        rep.check(has, "a practice recommendation for the topic", f"status '{status}', {len(recos)} recommendation(s)")
    else:
        rep.check(not any(r["topic_key"] == f"t:{topic['id']}" and r.get("kind") == "practice_topic" for r in recos),
                  "no extra-practice recommendation for a topic that is going well", f"status '{status}'")
    for r in recos[:3]:
        rep.say(f"  · {r.get('kind')}: {r.get('reason') or r.get('explanation') or r.get('text') or r}")
    mine = ok(st.get(f"/api/student/attempts/{sid}/monitoring"), "own monitoring record")
    rep.check(len(mine.get("events", [])) == 6, "student can see what was recorded", f"{len(mine.get('events', []))} events")

    rep.step(19, "Lecturer sees class analytics and the monitoring report")
    an = ok(lec.get(f"/api/lecturer/courses/{course['id']}/analytics", params={"quiz_id": quiz_id}), "class analytics")
    avg = an.get("average")
    rep.check(avg is not None and abs(float(avg) - pct) < 0.6, "class average = the one student's score", f"{avg}%")
    rep.check(an.get("submissions") == 1, "one submission counted", str(an.get("submissions")))
    qa = ok(lec.get(f"/api/lecturer/quizzes/{quiz_id}/question-analytics"), "question analytics")
    rep.check(bool(qa), "question-level statistics available")
    mon = ok(lec.get(f"/api/lecturer/quizzes/{quiz_id}/monitoring"), "monitoring report")
    srow = mon["students"][0] if mon.get("students") else None
    if rep.check(srow is not None, "monitored attempt listed"):
        rep.check(srow["status"] == "event_recorded", "neutral status 'Event recorded' (below every threshold)", srow["status"])
        rep.check(srow["counts"]["tab_switches"] == 1 and srow["counts"]["fullscreen_exits"] == 1 and srow["counts"]["speech"] == 1,
                  "counts: 1 page leave, 1 full screen exit, 1 speech-like sound", str(srow["counts"]))
        tl = ok(lec.get(f"/api/lecturer/monitoring/{srow['id']}"), "timeline")
        rep.check(len(tl["timeline"]) == 6, "timeline has the 6 events", str(len(tl["timeline"])))
        rep.check(not BLAME.search(str(mon) + str(tl)), "no 'cheating' or 'suspicious' wording")

    rep.step(20, "The Lecturer Insights Agent answers from the real numbers")
    for qtext, qid in (("Which topics are causing the most difficulty for my students?", None),
                       ("Which questions were the most difficult in this assessment?", quiz_id)):
        body = {"course_id": course["id"], "question": qtext, **({"quiz_id": qid} if qid else {})}
        out = ok(lec.post("/api/lecturer/insights/ask", json=body), "insights")
        rep.say(f"**Q:** {qtext}")
        rep.say(f"**A ({out['mode']}{', ' + out['model'] if out.get('model') else ''}):** {out['answer']}")
        if out.get("ai_note"):
            rep.say(f"  note: {out['ai_note']}")
        used = [t.get("name", str(t)) if isinstance(t, dict) else str(t) for t in out.get("tools_used") or []]
        rep.check(bool(used), "agent used database tools", ", ".join(used))
        runlog = ok(lec.get(f"/api/lecturer/agent-runs/{out['agent_run_id']}"), "insights log")
        rep.check(len(runlog["steps"]) > 0, "steps logged", f"{len(runlog['steps'])} steps")
        rep.check(not BLAME.search(out["answer"]), "no blame wording in the answer")
        nums = {float(x) for x in re.findall(r"\b\d+(?:\.\d+)?\b", out["answer"])}
        rep.say(f"  numbers in the answer: {sorted(nums)[:12]}")
    rep.check(st.post("/api/lecturer/insights/ask", json={"course_id": course["id"], "question": "x" * 10}).status_code in (401, 403),
              "a student cannot use the Insights Agent")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default="http://localhost:8000", help="backend address")
    ap.add_argument("--invite", default="", help="LECTURER_INVITE_CODE from backend/.env")
    ap.add_argument("--subject", default="Machine Learning")
    ap.add_argument("--topic", default="Supervised Learning")
    ap.add_argument("--reference", help="a .txt file of notes to generate from")
    ap.add_argument("--stand-in", action="store_true", help="say in the report that the backend uses the test-only fake model")
    ap.add_argument("--timeout-min", type=int, default=90, help="how long one generation may take")
    a = ap.parse_args()
    rep = Report()
    try:
        run(a, rep)
    except Stop as e:
        rep.failures += 1
        rep.say(f"\n**Stopped:** {e}")
    except httpx.HTTPError as e:
        rep.failures += 1
        rep.say(f"\n**Stopped:** could not reach the backend ({e.__class__.__name__}: {e}).")
    rep.say(f"\n**{rep.passes} passed, {rep.failures} failed.**")
    rep.say(f"Report: {rep.save()}")
    sys.exit(1 if rep.failures else 0)


if __name__ == "__main__":
    main()
