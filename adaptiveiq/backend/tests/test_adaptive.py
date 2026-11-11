"""Phase 5: the adaptive engine end to end through the API (practice quizzes with the TEST-ONLY fake model):
mastery persistence, the explained difficulty history, skipped and repeated answers, the student's
difficulty and subject breakdowns, often-skipped topics, and the try-harder recommendation."""
from sqlalchemy import select

from app.ml import mastery, recommendations, weak_areas
from app.models import Question
from tests import fake_model_server
from tests.conftest import wait_run
from tests.test_ml import NOW, obs

LEVEL = {"easy": 0, "medium": 1, "hard": 2}


def _key(app, question_ids):
    """The correct option id of each question, read straight from the database (the test plays a student
    who knows the answers, or not)."""
    with app.state.db.session() as db:
        out = {}
        for q in db.scalars(select(Question).where(Question.id.in_(question_ids))):
            out[q.id] = {"right": next(o.id for o in q.options if o.is_correct),
                         "wrong": next(o.id for o in q.options if not o.is_correct), "difficulty": q.difficulty}
        return out


def _practice(st, app, pattern, topic="Paging", difficulty="adaptive"):
    """pattern: one of 'r' (right), 'w' (wrong), 's' (skip) per question."""
    fake_model_server.STATE["mode"] = "varied"
    r = st.post("/api/student/practice/generate", json={"subject": "OS", "topic": topic, "question_count": len(pattern),
                                                         "difficulty": difficulty})
    assert r.status_code == 202, r.text
    run = wait_run(st, r.json()["run_id"], timeout=60)
    assert run["status"] == "done", run
    att = st.post(f"/api/student/quizzes/{run['quiz_id']}/start").json()
    key = _key(app, [q["question_id"] for q in att["questions"]])
    for q, p in zip(att["questions"], pattern):
        if p == "s":
            continue
        oid = key[q["question_id"]]["right" if p == "r" else "wrong"]
        assert st.put(f"/api/student/attempts/{att['session_id']}/answers/{q['question_id']}",
                      json={"option_id": oid}).status_code == 200
    res = st.post(f"/api/student/attempts/{att['session_id']}/submit").json()
    return res, key, r.json()


def _topic(st, name="Paging"):
    return next(t for t in st.get("/api/student/mastery").json()["topics"] if t["topic"] == name)


def test_mastery_counts_right_wrong_and_skipped_and_keeps_history(course_setup, app):
    st = course_setup["st"]
    _practice(st, app, "rrwws")
    t = _topic(st)
    assert (t["correct"], t["incorrect"], t["skipped"], t["answers"]) == (2, 2, 1, 5)
    assert t["label"] != "insufficient_evidence"                        # 5 different questions
    first = st.get("/api/student/mastery/history", params={"topic_key": t["topic_key"]}).json()["points"]
    _practice(st, app, "rrrrr")
    hist = st.get("/api/student/mastery/history", params={"topic_key": t["topic_key"]}).json()["points"]
    assert len(hist) == 2 and hist[0] == first[0]                       # the old snapshot is never overwritten
    assert hist[1]["score"] > hist[0]["score"] and hist[1]["answers"] == 10


def test_fewer_than_five_questions_is_insufficient_evidence(course_setup, app):
    st = course_setup["st"]
    res, _, _ = _practice(st, app, "rrrrr", topic="Segmentation")
    assert res["topics"][0]["mastery_label"] != "insufficient_evidence"
    e = mastery.estimate(obs("1111"), NOW)                              # 4 different questions
    assert e.label == "insufficient_evidence"
    again = obs("1111") + obs("1111")                                   # the same 4 questions answered twice
    assert mastery.estimate(again, NOW).label == "insufficient_evidence"


def test_difficulty_changes_one_level_at_a_time_with_a_reason(course_setup, app):
    st = course_setup["st"]
    levels = []
    for pattern in ("rrrrr", "rrrrr", "rrrrr", "wwwww", "wwwww"):
        res, key, started = _practice(st, app, pattern)
        levels.append(started["difficulty_note"])
    t = _topic(st)
    hist = st.get("/api/student/mastery/history", params={"topic_key": t["topic_key"]}).json()["points"]
    assert len(hist) == 5
    for p in hist:
        assert p["difficulty_reason"]                                   # every decision is explained
    seq = [p["next_difficulty"] for p in hist]
    assert seq[0] == "medium" or seq[0] in LEVEL
    for a, b in zip(seq, seq[1:]):
        if a in LEVEL and b in LEVEL:
            assert abs(LEVEL[a] - LEVEL[b]) <= 1, seq                   # never two levels at once
    assert "hard" in seq                                                # strong results stepped up
    assert LEVEL[seq[-1]] < LEVEL["hard"]                               # wrong answers stepped down again
    assert hist[-1]["previous_difficulty"] == seq[-2]
    # the next adaptive practice uses the stored decision and says why
    nxt = st.post("/api/student/practice/generate", json={"subject": "OS", "topic": "Paging", "question_count": 5,
                                                           "difficulty": "adaptive"}).json()
    assert nxt["difficulty_note"] == hist[-1]["difficulty_reason"]
    wait_run(st, nxt["run_id"], timeout=60)


def test_repeated_questions_count_half():
    from dataclasses import replace
    first = obs("11111")
    seen_again = [replace(o, repeat=True) for o in obs("00000")]          # the same 5 questions, flagged as repeats
    new = obs("00000", start_id=10)
    with_repeats = mastery.estimate(first + seen_again, NOW)
    with_new = mastery.estimate(first + new, NOW)
    assert with_repeats.evidence < with_new.evidence
    assert with_repeats.score > with_new.score                          # repeated misses weigh half


def test_student_breakdowns_by_difficulty_and_subject(course_setup, app):
    st = course_setup["st"]
    _, key, _ = _practice(st, app, "rwrsr", difficulty="mixed")
    tr = st.get("/api/student/trends").json()
    by = {d["difficulty"]: d for d in tr["by_difficulty"]}
    assert sum(d["answered"] for d in tr["by_difficulty"]) == 4 and sum(d["skipped"] for d in tr["by_difficulty"]) == 1
    assert sum(d["correct"] for d in tr["by_difficulty"]) == 3
    for d in by.values():
        assert d["accuracy"] == (round(d["correct"] / d["answered"], 3) if d["answered"] else None)
    assert tr["by_subject"] == [{"subject": "OS", "correct": 3, "answered": 4, "skipped": 1, "topics": 1, "accuracy": 0.75}]


def test_unreleased_assessment_results_are_not_in_the_breakdowns(course_setup, app):
    cs = course_setup
    lec, st = cs["lec"], cs["st"]
    fake_model_server.STATE["mode"] = "clean"
    body = {"course_id": cs["course"]["id"], "subject_id": cs["subject"]["id"], "topic_id": cs["topic"]["id"],
            "title": "Manual release quiz", "question_count": 5, "difficulty": "mixed"}
    run = wait_run(lec, lec.post("/api/lecturer/generate", json=body).json()["run_id"], timeout=60)
    qid = run["quiz_id"]
    for it in lec.get(f"/api/lecturer/quizzes/{qid}").json()["items"]:
        lec.post(f"/api/lecturer/questions/{it['question']['id']}/review", json={"action": "approve"})
    lec.patch(f"/api/lecturer/quizzes/{qid}", json={"contribution_pct": 10, "feedback_release": "manual"})
    assert lec.post(f"/api/lecturer/quizzes/{qid}/publish").status_code == 200
    att = st.post(f"/api/student/quizzes/{qid}/start").json()
    q = att["questions"][0]
    st.put(f"/api/student/attempts/{att['session_id']}/answers/{q['question_id']}", json={"option_id": q["options"][0]["id"]})
    st.post(f"/api/student/attempts/{att['session_id']}/submit")
    tr = st.get("/api/student/trends").json()
    assert all(d["answered"] == 0 and d["skipped"] == 0 for d in tr["by_difficulty"]) and tr["by_subject"] == []
    lec.post(f"/api/lecturer/quizzes/{qid}/release-feedback")
    tr = st.get("/api/student/trends").json()
    assert sum(d["answered"] for d in tr["by_difficulty"]) == 1 and sum(d["skipped"] for d in tr["by_difficulty"]) == 4


def test_often_skipped_topics_are_listed_apart_from_weak_ones(course_setup, app):
    st = course_setup["st"]
    _practice(st, app, "rrsss", topic="Deadlocks")
    _practice(st, app, "rrrrs", topic="Threads")
    w = st.get("/api/student/weak-areas").json()
    names = [x["topic"] for x in w["often_skipped"]]
    assert names == ["Deadlocks"]                                        # 60% skipped; Threads 20% is under 30%
    assert w["often_skipped"][0]["skipped_pct"] == 60.0 and "30%" in w["often_skipped_rule"]


def test_try_harder_recommendation_only_after_demonstrated_mastery():
    ready = mastery.estimate(obs("1101111111"), NOW)                   # proficient 83%, last 5 all right
    strong = mastery.estimate(obs("1111111111", start_id=20), NOW)     # strong: keep it fresh, no push
    thin = mastery.estimate(obs("111", start_id=40), NOW)              # not enough evidence
    weak = mastery.estimate(obs("0001000100", start_id=60), NOW)
    assert (ready.label, strong.label, thin.label, weak.label) == ("proficient", "strong", "insufficient_evidence",
                                                                   "needs_improvement")
    infos = [recommendations.TopicInfo(k, "OS", n, e, weak_areas.classify(e), d, None, i)
             for i, (k, n, e, d) in enumerate([("t:1", "Paging", ready, "hard"), ("t:2", "Scheduling", strong, "hard"),
                                               ("t:3", "Threads", thin, "mixed"), ("t:4", "Deadlocks", weak, "easy")])]
    recos = recommendations.build(infos, {})
    kinds = [(r.kind, r.topic_label) for r in recos]
    assert ("try_harder", "Paging") in kinds
    assert not any(k == "try_harder" and n != "Paging" for k, n in kinds)
    assert not any(n == "Scheduling" for _, n in kinds)
    assert kinds[0] == ("practice_topic", "Deadlocks") and kinds[-1] == ("try_harder", "Paging")   # lowest priority
    th = next(r for r in recos if r.kind == "try_harder")
    assert th.reason == ("You are doing well on Paging (mastery 83%, 100% of your last 5 answers correct), "
                         "so try a hard quiz next.")
    assert th.payload["difficulty"] == "hard"
