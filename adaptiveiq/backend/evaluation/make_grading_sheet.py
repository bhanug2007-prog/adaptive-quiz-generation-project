"""Builds a BLIND grading sheet from two evaluate_generation CSVs (same seed and test file).

    python -m evaluation.make_grading_sheet --a results/generation_base_....csv --b results/generation_finetuned_....csv

For each item both models' questions appear as X and Y in random order, so graders cannot tell which
model wrote which. The mapping is saved separately in a key file; do not open it until grading is done.
Graders fill, for every question that exists, three columns with 1 (yes) or 0 (no):
  correct      the marked answer is actually correct and the other options are wrong
  on_topic     it tests the requested topic (and the passage, when one is given)
  difficulty   its difficulty matches the requested level
plus optional notes. Two graders working independently on copies of the sheet is better than one;
score_grading.py reports their agreement when given both.
"""
import argparse
import csv
import json
import random
from pathlib import Path

COLS = ["item_id", "slot", "subject", "topic", "requested_difficulty", "context", "question", "option_a", "option_b",
        "option_c", "option_d", "marked_answer", "explanation", "correct", "on_topic", "difficulty", "notes"]


def load(p):
    with open(p, newline="", encoding="utf-8") as f:
        return {r["item_id"]: r for r in csv.DictReader(f)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--out", default=str(Path(__file__).parent / "results" / "grading_sheet.csv"))
    a = ap.parse_args()
    A, B = load(a.a), load(a.b)
    common = sorted(set(A) & set(B))
    if not common:
        raise SystemExit("The two files share no items. Run both with the same --test-file, --n and --seed.")
    va, vb = next(iter(A.values()))["variant"], next(iter(B.values()))["variant"]
    rng = random.Random(a.seed)
    rows, key = [], {}
    for iid in common:
        pair = [(va, A[iid]), (vb, B[iid])]
        rng.shuffle(pair)
        for slot, (variant, r) in zip("XY", pair):
            key[f"{iid}|{slot}"] = variant
            rows.append({"item_id": iid, "slot": slot, "subject": r["subject"], "topic": r["topic"],
                         "requested_difficulty": r["difficulty"], "context": r["context"],
                         "question": r["question"] or "(no valid question was produced)",
                         "option_a": r["option_a"], "option_b": r["option_b"], "option_c": r["option_c"],
                         "option_d": r["option_d"], "marked_answer": r["answer"], "explanation": r["explanation"],
                         "correct": "", "on_topic": "", "difficulty": "", "notes": ""})
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    keyfile = out.with_name(out.stem + "_KEY_do_not_open_until_graded.json")
    keyfile.write_text(json.dumps({"a": a.a, "b": a.b, "slots": key}, indent=2))
    print(f"{len(common)} items, {len(rows)} rows to grade -> {out}\nKey -> {keyfile}")


if __name__ == "__main__":
    main()
