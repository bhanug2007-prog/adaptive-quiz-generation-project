"""Scores a completed grading sheet and compares the two models on the SAME items.

    python -m evaluation.score_grading --sheet results/grading_sheet.csv \
        --key results/grading_sheet_KEY_do_not_open_until_graded.json [--sheet2 second_grader.csv]

Reports, per model: answer correctness, topic relevance and difficulty match as rates with 95% Wilson
intervals (a question that was never produced counts as 0 on all three), plus the automatic reliability
numbers from the two generation CSVs. The models are compared with an exact McNemar test on the paired
items (only items where they disagree carry information). With a second grader's sheet it also reports
Cohen's kappa for each column. A p-value above 0.05 means the data cannot tell the models apart; it
does not mean they are equal. Small samples (such as 30 items) usually cannot separate close models.
"""
import argparse
import csv
import json
import math
from pathlib import Path

from evaluation.evaluate_generation import summary

COLS = ("correct", "on_topic", "difficulty")


def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return None, None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(c - h, 4), round(c + h, 4)


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact p-value; b, c = discordant pair counts."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def kappa(x: list[int], y: list[int]) -> float | None:
    n = len(x)
    if n == 0:
        return None
    po = sum(a == b for a, b in zip(x, y)) / n
    px, py = sum(x) / n, sum(y) / n
    pe = px * py + (1 - px) * (1 - py)
    return round((po - pe) / (1 - pe), 4) if pe < 1 else None


def read(p):
    with open(p, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def val(r, col) -> int:
    if r["question"].startswith("(no valid question"):
        return 0
    v = (r.get(col) or "").strip().lower()
    if v in ("1", "y", "yes", "true"):
        return 1
    if v in ("0", "n", "no", "false"):
        return 0
    raise SystemExit(f"Item {r['item_id']} slot {r['slot']}: column '{col}' must be 1 or 0, found '{r.get(col)}'.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--sheet2", help="the same sheet graded independently by a second person")
    a = ap.parse_args()
    key = json.loads(Path(a.key).read_text())
    rows = read(a.sheet)
    variants = sorted(set(key["slots"].values()))
    scores = {v: {c: {} for c in COLS} for v in variants}
    for r in rows:
        v = key["slots"][f"{r['item_id']}|{r['slot']}"]
        for c in COLS:
            scores[v][c][r["item_id"]] = val(r, c)
    report = {"items": len({r["item_id"] for r in rows}), "models": {}, "comparison": {}}
    for v in variants:
        report["models"][v] = {}
        for c in COLS:
            ks = list(scores[v][c].values())
            lo, hi = wilson(sum(ks), len(ks))
            report["models"][v][c] = {"rate": round(sum(ks) / len(ks), 4), "ci95": [lo, hi], "n": len(ks)}
    if len(variants) == 2:
        v1, v2 = variants
        for c in COLS:
            common = sorted(set(scores[v1][c]) & set(scores[v2][c]))
            b = sum(scores[v1][c][i] == 1 and scores[v2][c][i] == 0 for i in common)
            cc = sum(scores[v1][c][i] == 0 and scores[v2][c][i] == 1 for i in common)
            report["comparison"][c] = {f"only_{v1}": b, f"only_{v2}": cc, "mcnemar_exact_p": round(mcnemar_exact(b, cc), 4)}
    for name in ("a", "b"):
        gen = read(key[name])
        report["models"].setdefault(gen[0]["variant"], {})["automatic"] = summary(gen)
    if a.sheet2:
        r2 = {(r["item_id"], r["slot"]): r for r in read(a.sheet2)}
        report["agreement_kappa"] = {}
        for c in COLS:
            pairs = [(val(r, c), val(r2[(r["item_id"], r["slot"])], c)) for r in rows if (r["item_id"], r["slot"]) in r2]
            report["agreement_kappa"][c] = kappa([p[0] for p in pairs], [p[1] for p in pairs])
    out = Path(a.sheet).with_suffix(".scores.json")
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
