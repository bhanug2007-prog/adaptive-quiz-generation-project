"""Unit tests for the adaptive engine (pure functions, no database)."""
import pytest
from datetime import datetime, timedelta, timezone

from app.ml import confidence, difficulty, mastery, question_stats, recommendations, spaced_revision, weak_areas
from app.services.generation_service import difficulty_plan, split_reference
from app.services.grading import score
from app.services.validation_service import grounding, is_duplicate

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def obs(pattern, difficulty_="medium", days_ago=0, start_id=1):
    """pattern: string of 1 (correct), 0 (wrong), s (skipped)."""
    out = []
    for k, ch in enumerate(pattern):
        out.append(mastery.Observation(question_id=start_id + k, correct=None if ch == "s" else ch == "1",
                                       difficulty=difficulty_, at=NOW - timedelta(days=days_ago, minutes=len(pattern) - k)))
    return out


def test_minimum_evidence_rule():
    e = mastery.estimate(obs("1111"), NOW)
    assert e.label == "insufficient_evidence" and e.evidence_level == "low"
    assert mastery.estimate(obs("11111"), NOW).label != "insufficient_evidence"


def test_repeating_one_question_is_not_evidence():
    same = [mastery.Observation(1, True, "medium", NOW - timedelta(minutes=k), repeat=k > 0) for k in range(10)]
    assert mastery.estimate(same, NOW).label == "insufficient_evidence"


def test_labels_order_and_interval():
    strong = mastery.estimate(obs("1" * 30, "hard"), NOW)
    weak = mastery.estimate(obs("0001000100"), NOW)
    assert strong.label == "strong" and weak.label == "needs_improvement"
    assert 0 <= weak.lower <= weak.score <= weak.upper <= 1
    mid = mastery.estimate(obs("1101011010"), NOW)
    assert mid.label in ("developing", "proficient")


def test_skips_count_as_half_wrong():
    a = mastery.estimate(obs("11111ssss"), NOW)
    b = mastery.estimate(obs("1111100000"[:9]), NOW)
    c = mastery.estimate(obs("11111"), NOW)
    assert b.score < a.score < c.score


def test_recency_and_difficulty_weighting():
    old_wrong = obs("00000", days_ago=60) + obs("11111", start_id=10)
    new_wrong = obs("11111", days_ago=60) + obs("00000", start_id=10)
    assert mastery.estimate(old_wrong, NOW).score > mastery.estimate(new_wrong, NOW).score
    assert mastery.estimate(obs("11111", "hard"), NOW).score > mastery.estimate(obs("11111", "easy"), NOW).score


def test_difficulty_policy():
    insufficient = mastery.estimate(obs("11"), NOW)
    assert difficulty.next_difficulty(insufficient, "hard")[0] == "mixed"
    good = mastery.estimate(obs("1111111111"), NOW)
    assert difficulty.next_difficulty(good, "medium")[0] == "hard"
    assert difficulty.next_difficulty(good, "hard")[0] == "hard"
    bad = mastery.estimate(obs("0100010000"), NOW)
    assert difficulty.next_difficulty(bad, "medium")[0] == "easy"


def test_single_wrong_answer_does_not_move_difficulty():
    e = mastery.estimate(obs("11011101" + "0"), NOW)       # one fresh mistake after a good run
    assert difficulty.next_difficulty(e, "medium")[0] == "medium"
    for d in ("easy", "medium", "hard"):
        nd, _ = difficulty.next_difficulty(e, d)
        assert abs(difficulty.LEVELS.index(nd) - difficulty.LEVELS.index(d)) <= 1


def test_weak_area_rules():
    assert weak_areas.classify(None).status == "not_attempted"
    assert weak_areas.classify(mastery.estimate(obs("000"), NOW)).status == "insufficient_evidence"
    assert weak_areas.classify(mastery.estimate(obs("0001000100"), NOW)).status == "weak"
    declining = mastery.estimate(obs("1111111111", days_ago=1) + obs("00100", start_id=20), NOW)
    st = weak_areas.classify(declining)
    assert st.status == "weak" and "dropped" in st.reason


def test_recommendations_explain_and_respect_prerequisites():
    weak = mastery.estimate(obs("0001000100"), NOW)
    dev = mastery.estimate(obs("1101101010", start_id=50), NOW)
    infos = [recommendations.TopicInfo("t:2", "DBMS", "SQL joins", weak, weak_areas.classify(weak), "easy", "t:1", 2),
             recommendations.TopicInfo("t:1", "DBMS", "Relational algebra", dev, weak_areas.classify(dev), "medium", None, 1),
             recommendations.TopicInfo("t:3", "DBMS", "Indexing", None, weak_areas.classify(None), "mixed", None, 3)]
    recos = recommendations.build(infos, {"t:2": 2})
    kinds = [(r.kind, r.topic_label) for r in recos]
    assert ("prerequisite", "Relational algebra") in kinds and ("practice_topic", "SQL joins") in kinds
    assert ("revisit_incorrect", "SQL joins") in kinds
    assert not any(t == "Indexing" for _, t in kinds)          # unattempted is never called weak
    assert all(r.reason for r in recos)
    assert recos[0].kind in ("prerequisite", "practice_topic")


def test_spaced_revision_boxes():
    box, due, st = spaced_revision.after_answer(None, False, NOW)
    assert (box, st) == (1, "active") and due == NOW + timedelta(days=1)
    box, due, st = spaced_revision.after_answer(1, True, NOW)
    assert box == 2 and due == NOW + timedelta(days=3)
    assert spaced_revision.after_answer(3, False, NOW)[0] == 1
    assert spaced_revision.after_answer(5, True, NOW)[2] == "retired"
    assert spaced_revision.after_answer(None, True, NOW)[2] == "none"


def test_confidence_calibration_needs_data():
    assert confidence.calibration([(3, True)] * 5)["pattern"] is None
    over = confidence.calibration([(3, False)] * 5 + [(3, True)] * 5)
    assert over["pattern"] == "overconfident"
    under = confidence.calibration([(1, True)] * 8 + [(2, True)] * 2)
    assert under["pattern"] == "underconfident"


def test_question_stats_flags_need_sample():
    few = question_stats.question_report("easy", 0, 5, 0, [], [0] * 5, [1.0] * 5)
    assert few["flags"] == [] and not few["enough_data"]
    many = question_stats.question_report("easy", 1, 9, 5, [10.0], [1] + [0] * 14, [5.0] + [1.0] * 14)
    codes = {f["code"] for f in many["flags"]}
    assert {"almost_all_missed", "high_skipping", "difficulty_mismatch"} <= codes
    assert many["discrimination"] is not None and many["discrimination"] > 0


def test_scoring_keeps_three_values_separate():
    s = score(7, 10, late=True, late_policy="penalty", late_penalty_pct=10, graded=True, contribution_pct=5)
    assert (s["raw_score"], s["percentage"], s["final_percentage"], s["contribution_earned"]) == (7, 70.0, 63.0, 3.15)
    s2 = score(7, 10, late=True, late_policy="allow", late_penalty_pct=10, graded=False, contribution_pct=5)
    assert s2["final_percentage"] == 70.0 and s2["contribution_earned"] is None


def test_generation_helpers():
    plan = difficulty_plan("mixed", 5, {"easy": 1, "medium": 3, "hard": 1})
    assert sorted(plan) == ["easy", "hard", "medium", "medium", "medium"] and plan[:3] == ["easy", "medium", "hard"]
    assert difficulty_plan("hard", 2) == ["hard", "hard"]
    text = " ".join(f"Sentence number {i} explains paging and frames." for i in range(60))
    chunks = split_reference(text)
    assert len(chunks) >= 2 and all(len(c.split()) >= 75 for c in chunks)


def test_duplicate_and_grounding_checks():
    dup, _ = is_duplicate("What does a larger quantum turn round robin into?",
                          ["What does a larger time quantum turn round robin into?"], 0.85)
    assert dup
    assert not is_duplicate("Which algorithm suits time-sharing systems?", ["What problem does aging solve?"], 0.85)[0]
    passage = "Round robin gives each process a fixed time quantum. A very large quantum makes it behave like FCFS."
    good = {"question": "What does a very large time quantum make round robin behave like?",
            "options": ["SJF", "FCFS", "Priority", "LRU"], "answer": "B", "explanation": "Large quantum behaves like FCFS."}
    bad = {"question": "Which protocol encrypts web traffic between browsers?",
           "options": ["HTTP", "TLS", "FTP", "SMTP"], "answer": "B", "explanation": "TLS encrypts HTTPS traffic."}
    assert grounding(good, passage) > 0.5 and grounding(bad, passage) < 0.2


def test_trend_compares_recent_with_earlier_answers():
    assert mastery.estimate(obs("0000011111"), NOW).trend == "improving"
    assert mastery.estimate(obs("1111100000"), NOW).trend == "declining"
    assert mastery.estimate(obs("1010110101"), NOW).trend == "stable"
    assert mastery.estimate(obs("11111"), NOW).trend == "not_enough_data"      # nothing before the last 5


def test_skips_are_not_counted_as_answered_for_trend():
    e = mastery.estimate(obs("sssss11111"), NOW)
    assert e.skipped == 5 and e.trend == "not_enough_data"


def test_next_action_follows_the_evidence():
    assert difficulty.next_action(None)[0] == "start"
    assert difficulty.next_action(mastery.estimate(obs("11"), NOW))[0] == "gather_evidence"
    assert difficulty.next_action(mastery.estimate(obs("0000000"), NOW))[0] == "revise_concept"
    assert difficulty.next_action(mastery.estimate(obs("1" * 12, "hard"), NOW))[0] in ("try_harder", "maintain")


def test_small_noisy_changes_are_not_called_a_trend():
    assert mastery.estimate(obs("1101101101", days_ago=1) + obs("01101", start_id=20), NOW).trend == "stable"
    assert mastery.estimate(obs("1111111111", days_ago=1) + obs("10100", start_id=20), NOW).trend == "declining"


def test_fisher_exact_matches_scipy_on_every_small_table():
    from scipy.stats import fisher_exact
    for n in (5, 8, 20):
        for k in range(6):
            for j in range(n + 1):
                ours = mastery.fisher_exact_p(k, 5 - k, j, n - j)
                ref = fisher_exact([[k, 5 - k], [j, n - j]]).pvalue
                assert abs(ours - ref) < 1e-9, (k, j, n, ours, ref)


def test_trend_uses_the_exact_test_not_the_z_test():
    # 0 of 5 after 3 of 5 earlier: 60 points lower, but Fisher p = 0.17, so no trend (the old z-test said declining)
    assert mastery.trend(0, 5, 3, 5)[0] == "stable"
    assert mastery.trend(0, 5, 5, 5) == ("declining", pytest.approx(0.00794, abs=1e-4))
    assert mastery.trend(5, 5, 0, 5)[0] == "improving"
    assert mastery.trend(4, 5, 0, 5)[0] == "improving"          # p = 0.048
    assert mastery.trend(4, 4, 0, 10)[0] == "not_enough_data"   # fewer than 5 recent answers


def test_trend_window_is_the_last_five_answered_in_time_order():
    # answers saved out of order: the window must follow answer time, and skips are left out of both sides
    later = obs("00000", start_id=50)                              # newest
    earlier = obs("11111", days_ago=2) + obs("sssss", days_ago=1, start_id=10)
    e = mastery.estimate(later + earlier, NOW)
    assert (e.recent_n, e.recent_accuracy, e.historical_accuracy) == (5, 0.0, 1.0)
    assert e.trend == "declining" and e.details["trend_p"] < 0.05


@pytest.mark.parametrize("pattern,level,expected", [
    ("111", "medium", (80, 59, 100, "insufficient_evidence")),
    ("11110", "medium", (71, 51, 92, "proficient")),
    ("1111s", "medium", (77, 57, 97, "proficient")),
    ("11111", "medium", (86, 70, 100, "proficient")),
    ("1111111111", "medium", (92, 82, 100, "strong")),
    ("11110", "hard", (77, 59, 96, "proficient")),
])
def test_worked_examples_in_the_feature_guide(pattern, level, expected):
    e = mastery.estimate(obs(pattern, level), NOW)
    assert (mastery.pct100(e.score), mastery.pct100(e.lower), mastery.pct100(e.upper), e.label) == expected


def test_weights_and_interval_by_hand():
    one = lambda ch, lvl="medium", days=0, repeat=False: mastery.estimate(
        [mastery.Observation(1, None if ch == "s" else ch == "1", lvl, NOW - timedelta(days=days), repeat=repeat)], NOW)
    assert one("1", "hard").details["alpha"] == 2.25          # 1 + 1.25
    assert one("0", "easy").details["beta"] == 2.25           # 1 + 1.25 (missing an easy question)
    assert one("1", "easy").details["alpha"] == 1.75
    assert one("0", "hard").details["beta"] == 1.75
    assert one("s").details["beta"] == 1.5                    # skip = half a wrong answer
    assert one("1", repeat=True).details["alpha"] == 1.5      # already-seen question counts half
    assert one("1", days=21).details["alpha"] == 1.5          # half-life 21 days
    e = one("1")
    a, b = 2.0, 1.0
    p = a / (a + b)
    half = 1.2816 * (p * (1 - p) / (a + b + 1)) ** 0.5
    assert e.score == round(p, 4) and e.lower == round(p - half, 4) and e.upper == round(min(1, p + half), 4)


def test_label_never_disagrees_with_the_shown_score():
    assert mastery.pct100(0.69996) == 70 and mastery.pct100(0.725) == 73 and mastery.pct100(0.7249) == 72
    assert mastery.label_for(0.69996, 0.5, 5, 5) == "proficient"         # shown as 70/100
    assert mastery.label_for(0.49996, 0.3, 5, 5) == "developing"         # shown as 50/100
    assert mastery.label_for(0.9, 0.79996, 5, 5) == "strong"             # range shown from 80
    assert mastery.label_for(0.6949, 0.5, 5, 5) == "developing"          # shown as 69/100
