"""Compares the adaptive difficulty policy with fixed-difficulty baselines on SYNTHETIC students.

    python -m evaluation.simulate_adaptive [--students 2000] [--seeds 5]

Each simulated student takes 8 practice quizzes of 5 questions on one topic, one quiz every two days.
Before each quiz a policy picks the difficulty from the student's answers so far:

  adaptive    app.ml.difficulty.next_difficulty (the policy the app uses), starting from "mixed"
  fixed       always "medium" (app.ml.difficulty.fixed_baseline)
  mixed       always easy, medium and hard in turn

Outcome: how well each question's difficulty fits the student, measured by the student's true chance of
answering it correctly (Rasch model, see sim_common.py):

  in band      share of questions answered with a 50-85% chance of success (challenging but doable)
  too hard     share with a chance below 40%
  too easy     share with a chance above 90%
  |p - 0.7|    mean distance from a 70% success rate

The 50-85% band is a common rule of thumb for practice, used here as an assumption; this simulation does
not measure learning gains, and it says nothing about real students until it is checked on real data.
Two populations: "static" ability, and "learning" (ability rises 1.5 logits over the 8 quizzes).
Results go to evaluation/results/adaptive_simulation.json and are printed as Markdown.
"""
import argparse
import json
import random
from pathlib import Path

from app.ml import difficulty, mastery
from app.services.generation_service import difficulty_plan
from evaluation.sim_common import answer, day, mean_sd, p_correct

QUIZZES, PER_QUIZ = 8, 5
OUT = Path(__file__).parent / "results" / "adaptive_simulation.json"


def policy_adaptive(obs, now, current):
    if not obs:
        return "mixed"
    return difficulty.next_difficulty(mastery.estimate(obs, now), current)[0]


POLICIES = {
    "adaptive": policy_adaptive,
    "fixed": lambda obs, now, cur: "medium",
    "mixed": lambda obs, now, cur: "mixed",
}


def run(policy: str, population: str, students: int, seed: int) -> dict:
    rng = random.Random(seed)
    ps, steps = [], []
    for _ in range(students):
        theta0 = rng.gauss(0.0, 1.0)
        obs, current, qid = [], None, 0
        for q in range(QUIZZES):
            now = day(2 * q)
            level = POLICIES[policy](obs, now, current)
            if current is not None and level != current:
                steps.append(1)
            current = level
            for d in difficulty_plan(level, PER_QUIZ):
                theta = theta0 + (1.5 * q / (QUIZZES - 1) if population == "learning" else 0.0)
                ps.append(p_correct(theta, d))
                qid += 1
                obs.append(mastery.Observation(question_id=qid, correct=answer(rng, theta, d), difficulty=d, at=now))
    n = len(ps)
    return {"in_band": sum(0.5 <= p <= 0.85 for p in ps) / n, "too_hard": sum(p < 0.4 for p in ps) / n,
            "too_easy": sum(p > 0.9 for p in ps) / n, "dist_07": sum(abs(p - 0.7) for p in ps) / n,
            "level_changes_per_student": len(steps) / students}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--students", type=int, default=2000)
    ap.add_argument("--seeds", type=int, default=5)
    a = ap.parse_args()
    report = {"note": "SYNTHETIC students (Rasch model). Not real data.", "students_per_seed": a.students,
              "seeds": list(range(a.seeds)), "policy": difficulty.POLICY_VERSION, "results": {}}
    print(f"Synthetic students, {a.students} per seed, {a.seeds} seeds, {QUIZZES} quizzes x {PER_QUIZ} questions "
          f"(mean ± sd across seeds)\n")
    for pop in ("static", "learning"):
        report["results"][pop] = {}
        print(f"### {pop} ability\n")
        print("| policy | in 50-85% band | too hard (<40%) | too easy (>90%) | mean abs(p - 0.7) | level changes per student |")
        print("|---|---|---|---|---|---|")
        for pol in POLICIES:
            runs = [run(pol, pop, a.students, seed) for seed in range(a.seeds)]
            agg = {k: dict(zip(("mean", "sd"), (round(v, 4) for v in mean_sd([r[k] for r in runs])))) for k in runs[0]}
            report["results"][pop][pol] = agg
            f = lambda k, pct=True: (f"{agg[k]['mean'] * 100:.1f}% ± {agg[k]['sd'] * 100:.1f}" if pct
                                     else f"{agg[k]['mean']:.3f} ± {agg[k]['sd']:.3f}")
            print(f"| {pol} | {f('in_band')} | {f('too_hard')} | {f('too_easy')} | {f('dist_07', False)} | "
                  f"{f('level_changes_per_student', False)} |")
        print()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))
    print(f"Saved {OUT}")


if __name__ == "__main__":
    main()
