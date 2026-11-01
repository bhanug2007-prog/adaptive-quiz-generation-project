"""Compares the Beta mastery estimate with the plain-accuracy baseline on SYNTHETIC students.

    python -m evaluation.simulate_mastery [--students 2000] [--seeds 5]

Scenarios
  stable    ability does not change; difficulties are a random mix of easy/medium/hard
  skewed    same, but the student mostly gets easy questions (accuracy flatters them)
  improving ability rises by +1.5 logits across the answers, one answer a day (recency matters)

Metrics, after n answers (n = 3, 5, 10, 20, 30)
  MAE        mean |estimate - true mastery|, true mastery = P(correct on a medium question)
  label acc. share of students whose label matches the true label (only where a label is given)
  coverage   share of students whose true mastery lies inside the 80% interval (target about 80%)
  over-claim share of labelled students given a HIGHER label than they deserve (the costly error:
             a student told they have mastered a topic stops practising it)
  trend      share of students whose trend is "improving" / "declining" (should be near 0 when stable)

Results go to evaluation/results/mastery_simulation.json and are printed as Markdown tables.
They are simulation results on synthetic data, not measurements on real students.
"""
import argparse
import json
import random
from pathlib import Path

from app.ml import mastery
from evaluation.sim_common import answer, day, mean_sd, sigmoid, true_label

RANK = {"needs_improvement": 0, "developing": 1, "proficient": 2, "strong": 3}

NS = [3, 5, 10, 20, 30]
OUT = Path(__file__).parent / "results" / "mastery_simulation.json"


def baseline_label(acc: float, n_unique: int, min_evidence: int = 5) -> str:
    return "insufficient_evidence" if n_unique < min_evidence else true_label(acc)


def run_scenario(name: str, students: int, seed: int) -> dict:
    rng = random.Random(seed)
    stats = {n: {"beta_err": [], "base_err": [], "beta_lab": [], "base_lab": [], "cover": [], "labelled": 0,
                 "beta_over": [], "base_over": [], "up": [], "down": []} for n in NS}
    for _ in range(students):
        theta0 = rng.gauss(0.0, 1.0)
        obs, total = [], max(NS)
        for k in range(total):
            theta = theta0 + (1.5 * k / (total - 1) if name == "improving" else 0.0)
            if name == "skewed":
                d = rng.choices(["easy", "medium", "hard"], weights=[0.7, 0.2, 0.1])[0]
            else:
                d = rng.choice(["easy", "medium", "hard"])
            obs.append(mastery.Observation(question_id=k + 1, correct=answer(rng, theta, d), difficulty=d, at=day(k)))
            n = k + 1
            if n not in stats:
                continue
            truth = sigmoid(theta)                 # current ability, medium question
            now = day(k)
            e = mastery.estimate(obs, now)
            base = mastery.baseline_accuracy(obs)
            s = stats[n]
            s["beta_err"].append(abs(e.score - truth))
            s["base_err"].append(abs(base - truth))
            s["cover"].append(e.lower <= truth <= e.upper)
            s["up"].append(e.trend == "improving")
            s["down"].append(e.trend == "declining")
            if e.label != "insufficient_evidence":
                tl, bl = true_label(truth), baseline_label(base, n)
                s["labelled"] += 1
                s["beta_lab"].append(e.label == tl)
                s["base_lab"].append(bl == tl)
                s["beta_over"].append(RANK[e.label] > RANK[tl])
                s["base_over"].append(RANK[bl] > RANK[tl])
    out = {}
    for n, s in stats.items():
        avg = lambda xs: sum(xs) / len(xs) if xs else None
        out[n] = {"beta_mae": avg(s["beta_err"]), "baseline_mae": avg(s["base_err"]),
                  "beta_label_acc": avg(s["beta_lab"]), "baseline_label_acc": avg(s["base_lab"]),
                  "interval_coverage": avg(s["cover"]), "share_labelled": s["labelled"] / students,
                  "beta_overclaim": avg(s["beta_over"]), "baseline_overclaim": avg(s["base_over"]),
                  "trend_improving": avg(s["up"]), "trend_declining": avg(s["down"])}
    return out


def summarise(runs: list[dict]) -> dict:
    keys = runs[0][NS[0]].keys()
    res = {}
    for n in NS:
        res[n] = {}
        for k in keys:
            vals = [r[n][k] for r in runs if r[n][k] is not None]
            res[n][k] = None if not vals else dict(zip(("mean", "sd"), (round(v, 4) for v in mean_sd(vals))))
    return res


def fmt(x, pct=False):
    if x is None:
        return "n/a"
    m, sd = x["mean"], x["sd"]
    return f"{m * 100:.1f}% ± {sd * 100:.1f}" if pct else f"{m:.3f} ± {sd:.3f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--students", type=int, default=2000)
    ap.add_argument("--seeds", type=int, default=5)
    a = ap.parse_args()
    report = {"note": "SYNTHETIC students (Rasch model). Not real data.", "students_per_seed": a.students,
              "seeds": list(range(a.seeds)), "algorithm": mastery.MASTERY_VERSION, "scenarios": {}}
    for name in ("stable", "skewed", "improving"):
        report["scenarios"][name] = summarise([run_scenario(name, a.students, seed) for seed in range(a.seeds)])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2))
    lines = [f"Synthetic students, {a.students} per seed, {a.seeds} seeds (mean ± sd across seeds). "
             f"Algorithm {mastery.MASTERY_VERSION}.\n"]
    for name, res in report["scenarios"].items():
        lines.append(f"### {name}\n")
        lines.append("| answers | MAE Beta | MAE baseline | label acc. Beta | label acc. baseline | over-claim Beta | "
                     "over-claim baseline | 80% coverage | trend up | trend down |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for n in NS:
            r = res[n]
            lines.append(f"| {n} | {fmt(r['beta_mae'])} | {fmt(r['baseline_mae'])} | {fmt(r['beta_label_acc'], True)} | "
                         f"{fmt(r['baseline_label_acc'], True)} | {fmt(r['beta_overclaim'], True)} | "
                         f"{fmt(r['baseline_overclaim'], True)} | {fmt(r['interval_coverage'], True)} | "
                         f"{fmt(r['trend_improving'], True)} | {fmt(r['trend_declining'], True)} |")
        lines.append("")
    text = "\n".join(lines)
    print(text)
    OUT.with_suffix(".md").write_text(text + "\n")
    print(f"Saved {OUT}")


if __name__ == "__main__":
    main()
