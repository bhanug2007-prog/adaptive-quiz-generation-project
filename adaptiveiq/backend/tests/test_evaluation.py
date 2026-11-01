"""The evaluation pipeline runs end to end (TEST-ONLY fake model; the numbers mean nothing)."""
import csv
import json
import subprocess
import sys

from app.core.config import Settings
from evaluation import score_grading
from evaluation.evaluate_generation import FIELDS, evaluate, sample, summary

ITEMS = [{"id": f"T{i}", "branch": "CSE", "subject": "Operating Systems", "topic": f"Topic {i}",
          "difficulty": ["easy", "medium", "hard"][i % 3], "question": "ref?",
          "context": "Round robin scheduling gives each process a time quantum. Option beta is the answer here."}
         for i in range(9)]


def test_sample_is_stratified_and_one_per_topic():
    rows = ITEMS + [dict(ITEMS[0], id="T0b")]
    s = sample(rows, 6, seed=1)
    assert len(s) == 6 and len({x["topic"] for x in s}) == 6
    assert [x["difficulty"] for x in s].count("easy") == 2
    assert [x["id"] for x in sample(rows, 6, seed=1)] == [x["id"] for x in s]


def test_pipeline_end_to_end(tmp_path, model_port):
    files = {}
    for variant in ("base", "finetuned"):
        st = Settings(_env_file=None, model_base_url=f"http://127.0.0.1:{model_port}", model_variant=variant,
                      database_url="sqlite://", math_check=True)
        rows = evaluate(ITEMS[:4], st, max_attempts=3, log=lambda *_: None)
        assert {r["variant"] for r in rows} == {variant}
        summ = summary(rows)
        assert 0 <= summ["valid_first_rate"] <= summ["valid_final_rate"] <= 1
        p = tmp_path / f"gen_{variant}.csv"
        with p.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
        files[variant] = p
    sheet = tmp_path / "sheet.csv"
    subprocess.run([sys.executable, "-m", "evaluation.make_grading_sheet", "--a", str(files["base"]), "--b",
                    str(files["finetuned"]), "--out", str(sheet)], check=True, capture_output=True)
    with sheet.open(newline="", encoding="utf-8-sig") as f:
        graded = list(csv.DictReader(f))
    assert len(graded) == 8 and "variant" not in graded[0]                 # blind: no model names in the sheet
    for k, r in enumerate(graded):
        r.update(correct=str(k % 2), on_topic="1", difficulty="0")
    with sheet.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(graded[0]))
        w.writeheader()
        w.writerows(graded)
    key = sheet.with_name("sheet_KEY_do_not_open_until_graded.json")
    out = subprocess.run([sys.executable, "-m", "evaluation.score_grading", "--sheet", str(sheet), "--key", str(key),
                          "--sheet2", str(sheet)], check=True, capture_output=True, text=True)
    rep = json.loads(sheet.with_suffix(".scores.json").read_text())
    assert set(rep["models"]) == {"base", "finetuned"} and rep["items"] == 4
    assert rep["agreement_kappa"]["on_topic"] is None or rep["agreement_kappa"]["on_topic"] == 1.0
    assert "mcnemar_exact_p" in rep["comparison"]["correct"]
    assert out.returncode == 0


def test_statistics_helpers():
    assert score_grading.mcnemar_exact(0, 0) == 1.0
    assert round(score_grading.mcnemar_exact(0, 6), 4) == 0.0312
    lo, hi = score_grading.wilson(24, 30)
    assert lo < 0.8 < hi and 0.6 < lo
    assert score_grading.kappa([1, 0, 1, 0], [1, 0, 1, 0]) == 1.0
