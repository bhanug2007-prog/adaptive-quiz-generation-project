"""Edge cases raised in the external review: boundaries, small samples, denominators, repeats."""
from datetime import datetime, timedelta, timezone

import pytest

from app.ml import confidence, difficulty, mastery, question_stats, recommendations, spaced_revision, weak_areas
from app.services.grading import score
from tests.conftest import register
from tests.test_flow import _approve_all, _draft

NOW = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


def est(**kw):
    base = dict(score=0.6, lower=0.4, upper=0.8, evidence=8, answers=8, unique_questions=8, correct=5, incorrect=3,
                skipped=0, label="developing", evidence_level="moderate", recent_accuracy=0.6, recent_n=5,
                historical_accuracy=0.6)
    base.update(kw)
    return mastery.MasteryEstimate(**base)


# ---------- adaptive difficulty: every threshold boundary ----------

@pytest.mark.parametrize("kw,expected", [
    (dict(score=0.75, lower=0.60, recent_accuracy=0.80), "hard"),       # all exactly on the step-up line
    (dict(score=0.7449, lower=0.60, recent_accuracy=0.80), "medium"),   # shown 74 -> stays
    (dict(score=0.75, lower=0.5949, recent_accuracy=0.80), "medium"),   # lower shown 59 -> stays
    (dict(score=0.75, lower=0.60, recent_accuracy=0.60), "medium"),
    (dict(score=0.50, recent_accuracy=0.60), "medium"),                 # 50 is not below 50
    (dict(score=0.4949, recent_accuracy=0.60), "easy"),                 # shown 49 -> down
    (dict(score=0.60, recent_accuracy=0.40), "easy"),                   # 40% recent -> down
    (dict(score=0.60, recent_accuracy=0.4051), "medium"),               # shown 41% -> stays
    (dict(score=0.30, recent_accuracy=0.0, recent_n=2), "medium"),      # fewer than 3 recent answers: no step
    (dict(score=0.95, lower=0.85, recent_accuracy=1.0, recent_n=2), "medium"),
    (dict(label="insufficient_evidence", score=0.95, lower=0.85, recent_accuracy=1.0), "mixed"),
])
def test_difficulty_boundaries(kw, expected):
    assert difficulty.next_difficulty(est(**kw), "medium")[0] == expected


def test_difficulty_never_jumps_two_levels_or_past_the_ends():
    assert difficulty.next_difficulty(est(score=0.95, lower=0.85, recent_accuracy=1.0), "easy")[0] == "medium"
    assert difficulty.next_difficulty(est(score=0.95, lower=0.85, recent_accuracy=1.0), "hard")[0] == "hard"
    assert difficulty.next_difficulty(est(score=0.2, recent_accuracy=0.0), "hard")[0] == "medium"
    assert difficulty.next_difficulty(est(score=0.2, recent_accuracy=0.0), "easy")[0] == "easy"


# ---------- weak areas and recommendations ----------

def test_insufficient_evidence_and_unattempted_are_never_weak():
    assert weak_areas.classify(None).status == "not_attempted"
    assert weak_areas.classify(est(label="insufficient_evidence", score=0.1, unique_questions=4)).status == "insufficient_evidence"


def _info(key, e, pre=None):
    return recommendations.TopicInfo(key, "OS", key, e, weak_areas.classify(e), "easy", pre)


def test_prerequisite_comes_before_the_weak_topic():
    weak = est(label="needs_improvement", score=0.3)
    recos = recommendations.build([_info("deadlocks", weak, pre="sync"), _info("sync", weak)], {})
    kinds = [(r.kind, r.topic_key) for r in recos]
    assert kinds.index(("prerequisite", "sync")) < kinds.index(("practice_topic", "deadlocks"))


def test_strong_prerequisite_is_not_recommended():
    recos = recommendations.build([_info("deadlocks", est(label="needs_improvement", score=0.3), pre="sync"),
                                   _info("sync", est(label="proficient", score=0.8))], {})
    assert not any(r.kind == "prerequisite" for r in recos)


def test_recommendations_are_capped_at_six():
    weak = est(label="needs_improvement", score=0.3)
    assert len(recommendations.build([_info(f"t{i}", weak) for i in range(10)], {})) == 6


# ---------- spaced revision: dates and repeats ----------

def test_revision_schedule_dates_and_resets():
    box, due, st = spaced_revision.after_answer(None, False, NOW)
    assert (box, due, st) == (1, NOW + timedelta(days=1), "active")
    for b, days in ((1, 3), (2, 7), (3, 14), (4, 30)):
        assert spaced_revision.after_answer(b, True, NOW)[:2] == (b + 1, NOW + timedelta(days=days))
    assert spaced_revision.after_answer(5, True, NOW) == (5, None, "retired")
    assert spaced_revision.after_answer(4, False, NOW)[:2] == (1, NOW + timedelta(days=1))   # wrong -> back to 1 day
    assert spaced_revision.after_answer(None, True, NOW) == (0, None, "none")                # right first time: never scheduled


# ---------- confidence: small samples give no conclusion ----------

def test_confidence_needs_ten_ratings_and_three_per_level():
    nine = [(3, False)] * 9
    out = confidence.calibration(nine)
    assert out["pattern"] is None and "9 so far" in out["message"]
    out = confidence.calibration([(3, False)] * 2 + [(2, True)] * 8)
    assert out["levels"][2]["accuracy"] is None                  # only 2 'Sure' answers: no rate shown
    assert out["pattern"] == "calibrated"                        # and no overconfidence claim from 2 answers


# ---------- question statistics: zero variance and small n ----------

def test_discrimination_edge_cases():
    assert question_stats.point_biserial([1] * 12, [0.5 + i / 100 for i in range(12)]) is None   # everyone right
    assert question_stats.point_biserial([1, 0] * 6, [0.5] * 12) is None                          # rest scores all equal
    assert question_stats.point_biserial([1, 0] * 4, [0.9, 0.1] * 4) is None                      # fewer than 10 answers
    rep = question_stats.question_report("easy", 0, 9, 0, [], [0] * 9, [0.5] * 9)
    assert rep["flags"] == [] and rep["enough_data"] is False


# ---------- scoring ----------

def test_scoring_edge_cases():
    assert score(0, 0, False, "none", 0, True, 10)["percentage"] == 0.0              # zero-mark quiz never divides by 0
    r = score(3, 4, True, "penalty", 20, True, 10)
    assert (r["percentage"], r["final_percentage"], r["contribution_earned"]) == (75.0, 60.0, 6.0)
    assert score(3, 4, True, "accept", 20, True, 10)["final_percentage"] == 75.0     # late but no penalty policy
    assert score(3, 4, False, "penalty", 20, True, 10)["final_percentage"] == 75.0   # on time: no penalty
    assert score(3, 4, False, "none", 0, False, 10)["contribution_earned"] is None    # ungraded adds nothing


# ---------- API: weight cap boundary, join codes, autosave races, denominators ----------

def test_weight_cap_is_inclusive(course_setup):
    lec = course_setup["lec"]
    run = _draft(course_setup, 1)
    _approve_all(lec, run["quiz_id"])
    lec.patch(f"/api/lecturer/quizzes/{run['quiz_id']}", json={"contribution_pct": 20})     # cap is exactly 20
    assert lec.post(f"/api/lecturer/quizzes/{run['quiz_id']}/publish").status_code == 200
    run2 = _draft(course_setup, 1)
    _approve_all(lec, run2["quiz_id"])
    lec.patch(f"/api/lecturer/quizzes/{run2['quiz_id']}", json={"contribution_pct": 0.5})
    r = lec.post(f"/api/lecturer/quizzes/{run2['quiz_id']}/publish")
    assert r.status_code == 422 and "at most 0%" in r.json()["detail"]


def test_replaced_join_code_stops_working(course_setup):
    lec, cid = course_setup["lec"], course_setup["course"]["id"]
    old = course_setup["course"]["join_code"]
    new = lec.post(f"/api/lecturer/courses/{cid}/join-code").json()["join_code"]
    assert new != old
    other = course_setup["make_client"]()
    register(other, "student")
    assert other.post("/api/student/courses/join", json={"join_code": old}).status_code in (403, 404)
    assert other.post("/api/student/courses/join", json={"join_code": new}).status_code == 200


def test_repeated_saves_keep_the_last_answer_and_submit_locks_it(course_setup):
    lec, st = course_setup["lec"], course_setup["st"]
    run = _draft(course_setup, 2)
    _approve_all(lec, run["quiz_id"])
    lec.post(f"/api/lecturer/quizzes/{run['quiz_id']}/publish")
    att = st.post(f"/api/student/quizzes/{run['quiz_id']}/start").json()
    q = att["questions"][0]
    sid, qid = att["session_id"], q["question_id"]
    for o in q["options"]:                                   # rapid re-saves, as a double-click would send
        assert st.put(f"/api/student/attempts/{sid}/answers/{qid}", json={"option_id": o["id"]}).status_code == 200
    again = st.post(f"/api/student/quizzes/{run['quiz_id']}/start").json()
    saved = {a["question_id"]: a["option_id"] for a in again["answers"]} if isinstance(again["answers"], list) \
        else {int(k): v["option_id"] for k, v in again["answers"].items()}
    assert saved[qid] == q["options"][-1]["id"]
    first = st.post(f"/api/student/attempts/{sid}/submit").json()
    again = st.post(f"/api/student/attempts/{sid}/submit")                            # double-click on Submit
    assert again.status_code == 200 and again.json() == first                          # same result, not re-scored
    late = st.put(f"/api/student/attempts/{sid}/answers/{qid}", json={"option_id": q["options"][0]["id"]})
    assert late.status_code == 409                                                     # no edits after submission


def test_late_submission_gets_the_penalty(course_setup, app):
    lec, st = course_setup["lec"], course_setup["st"]
    run = _draft(course_setup, 1)
    _approve_all(lec, run["quiz_id"])
    due = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    closes = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    lec.patch(f"/api/lecturer/quizzes/{run['quiz_id']}", json={"due_at": due, "closes_at": closes, "late_policy": "penalty",
                                                              "late_penalty_pct": 10, "contribution_pct": 10})
    assert lec.post(f"/api/lecturer/quizzes/{run['quiz_id']}/publish").status_code == 200
    att = st.post(f"/api/student/quizzes/{run['quiz_id']}/start").json()
    full = lec.get(f"/api/lecturer/quizzes/{run['quiz_id']}").json()["items"][0]["question"]
    right = next(o["id"] for o in full["options"] if o["is_correct"])
    st.put(f"/api/student/attempts/{att['session_id']}/answers/{full['id']}", json={"option_id": right})
    from app.models import Quiz
    with app.state.db.session() as db:                        # the due date passes while the attempt is open
        db.get(Quiz, run["quiz_id"]).due_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    res = st.post(f"/api/student/attempts/{att['session_id']}/submit").json()
    assert res["percentage"] == 100.0 and res["final_percentage"] == 90.0 and res["contribution_earned"] == 9.0


def test_class_average_uses_each_students_latest_attempt(course_setup):
    lec, st = course_setup["lec"], course_setup["st"]
    run = _draft(course_setup, 1)
    _approve_all(lec, run["quiz_id"])
    lec.patch(f"/api/lecturer/quizzes/{run['quiz_id']}", json={"attempts_allowed": 2, "contribution_pct": 5})
    lec.post(f"/api/lecturer/quizzes/{run['quiz_id']}/publish")
    full = lec.get(f"/api/lecturer/quizzes/{run['quiz_id']}").json()["items"][0]["question"]
    right = next(o["id"] for o in full["options"] if o["is_correct"])
    wrong = next(o["id"] for o in full["options"] if not o["is_correct"])
    for choice in (wrong, right):                              # first attempt 0%, second 100%
        att = st.post(f"/api/student/quizzes/{run['quiz_id']}/start").json()
        st.put(f"/api/student/attempts/{att['session_id']}/answers/{full['id']}", json={"option_id": choice})
        assert st.post(f"/api/student/attempts/{att['session_id']}/submit").status_code == 200
    perf = lec.get(f"/api/lecturer/courses/{course_setup['course']['id']}/analytics").json()
    assert perf["average"] == 100.0 and perf["submissions"] == 1


def test_simultaneous_submits_score_once(course_setup, app):
    """Two Submit requests at the same moment: one result, one mastery snapshot per topic."""
    import threading

    from sqlalchemy import func, select

    from app.models import QuizResult, TopicMasterySnapshot
    lec, st = course_setup["lec"], course_setup["st"]
    run = _draft(course_setup, 2)
    _approve_all(lec, run["quiz_id"])
    lec.post(f"/api/lecturer/quizzes/{run['quiz_id']}/publish")
    att = st.post(f"/api/student/quizzes/{run['quiz_id']}/start").json()
    sid = att["session_id"]
    clients = [course_setup["make_client"]() for _ in range(4)]
    for c in clients:
        c.cookies.update(st.cookies)
    codes = []
    barrier = threading.Barrier(len(clients))

    def go(c):
        barrier.wait()
        codes.append(c.post(f"/api/student/attempts/{sid}/submit").status_code)
    threads = [threading.Thread(target=go, args=(c,)) for c in clients]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert codes == [200] * len(clients)
    with app.state.db.session() as db:
        assert db.scalar(select(func.count()).select_from(QuizResult).where(QuizResult.session_id == sid)) == 1
        snaps = db.scalar(select(func.count()).select_from(TopicMasterySnapshot)
                          .where(TopicMasterySnapshot.trigger_session_id == sid))
        assert snaps == 1
