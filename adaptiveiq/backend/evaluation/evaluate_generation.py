"""Runs ONE model variant over held-out topics with the app's own prompt and checks, and writes a CSV.

Run it once per variant against the same test file and seed, so both models see exactly the same items:

    # base Qwen2.5-7B-Instruct served by llama-server on :8080
    python -m evaluation.evaluate_generation --variant base --base-url http://127.0.0.1:8080 \
        --test-file ../../data/clean/test.jsonl --n 60 --seed 7
    # fine-tuned model
    python -m evaluation.evaluate_generation --variant finetuned --base-url http://127.0.0.1:8080 \
        --test-file ../../data/clean/test.jsonl --n 60 --seed 7

The test file is the held-out split (split by topic, so no test topic was seen in training), one JSON
object per line with branch, subject, topic, difficulty and context. Items are sampled stratified by
difficulty with a fixed seed. Each item gets up to --max-attempts tries, like the app.

Measured automatically per item (reliability and structure):
  valid_first   the first output passed every automatic check
  valid_final   a passing output was found within the attempts
  attempts, reasons (why each failed attempt was rejected), seconds per call
  checks: format/structure (4 distinct options, one key), duplicate (against this run's earlier items),
  give-away, explanation-number conflict, grounding overlap with the passage, Python maths check.
Answer correctness, topic relevance and difficulty match need people: see make_grading_sheet.py.
"""
import argparse
import csv
import json
import random
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import Settings
from app.services.model_service import ModelBadResponse, ModelService
from app.services.validation_service import REASONS, Validator

FIELDS = ["item_id", "variant", "branch", "subject", "topic", "difficulty", "valid_first", "valid_final", "attempts",
          "reasons", "seconds_total", "seconds_per_call", "question", "option_a", "option_b", "option_c", "option_d",
          "answer", "explanation", "grounding", "math_status", "max_similarity", "context", "reference_question",
          "raw_last_output"]


def sample(rows: list[dict], n: int, seed: int) -> list[dict]:
    """n items, stratified by difficulty (taken in turn), at most one item per topic, reproducible."""
    rng = random.Random(seed)
    pools = {d: sorted((r for r in rows if r["difficulty"] == d), key=lambda r: r["id"]) for d in ("easy", "medium", "hard")}
    for p in pools.values():
        rng.shuffle(p)
    out, used = [], set()
    while len(out) < n and any(pools.values()):
        for d in ("easy", "medium", "hard"):
            p = pools[d]
            while p and (p[0]["subject"], p[0]["topic"]) in used:
                p.pop(0)
            if p and len(out) < n:
                r = p.pop(0)
                out.append(r)
                used.add((r["subject"], r["topic"]))
    return out


def evaluate(items, settings: Settings, max_attempts: int, log=print) -> list[dict]:
    model = ModelService(settings)
    validator = Validator(settings, model)
    existing: list[str] = []
    out = []
    try:
        for k, it in enumerate(items, 1):
            reasons, t_calls, last_raw, result = [], [], "", None
            t0 = time.time()
            for _ in range(max_attempts):
                c0 = time.time()
                try:
                    raw = model.chat(model.mcq_messages(it["subject"], it["topic"], it["difficulty"], it["context"],
                                                        branch=it.get("branch")))
                except ModelBadResponse:
                    reasons.append("bad_response")
                    continue
                finally:
                    t_calls.append(time.time() - c0)
                last_raw = raw
                c = validator.check(raw, existing, passage=it["context"], grounded=True)
                if c.ok:
                    result = c
                    break
                reasons.append(c.reason)
            m = result.mcq if result else {}
            if result:
                existing.insert(0, m["question"])
            opts = (m.get("options") or [""] * 4) + [""] * 4
            row = {"item_id": it["id"], "variant": settings.model_variant, "branch": it.get("branch", ""),
                   "subject": it["subject"], "topic": it["topic"], "difficulty": it["difficulty"],
                   "valid_first": int(bool(result) and not reasons), "valid_final": int(bool(result)),
                   "attempts": len(t_calls), "reasons": ";".join(reasons),
                   "seconds_total": round(time.time() - t0, 2),
                   "seconds_per_call": round(sum(t_calls) / len(t_calls), 2) if t_calls else "",
                   "question": m.get("question", ""), "option_a": opts[0], "option_b": opts[1], "option_c": opts[2],
                   "option_d": opts[3], "answer": m.get("answer", ""), "explanation": m.get("explanation", ""),
                   "grounding": (result.info or {}).get("grounding", "") if result else "",
                   "math_status": (result.info or {}).get("math_status", "") if result else "",
                   "max_similarity": (result.info or {}).get("max_similarity", "") if result else "",
                   "context": it["context"], "reference_question": it.get("question", ""), "raw_last_output": last_raw}
            out.append(row)
            log(f"[{k}/{len(items)}] {it['subject']} / {it['topic']} ({it['difficulty']}): "
                f"{'ok' if result else 'FAILED'} after {len(t_calls)} call(s) {('; '.join(reasons))}")
    finally:
        model.close()
    return out


def summary(rows: list[dict]) -> dict:
    n = len(rows)
    calls = sum(int(r["attempts"]) for r in rows)
    reasons = Counter(x for r in rows for x in r["reasons"].split(";") if x)
    spc = [float(r["seconds_per_call"]) for r in rows if r["seconds_per_call"] != ""]
    return {"items": n, "valid_first_rate": sum(int(r["valid_first"]) for r in rows) / n,
            "valid_final_rate": sum(int(r["valid_final"]) for r in rows) / n,
            "failure_rate": 1 - sum(int(r["valid_final"]) for r in rows) / n, "model_calls": calls,
            "retry_rate": (calls - n) / calls if calls else None,
            "avg_seconds_per_call": sum(spc) / len(spc) if spc else None,
            "rejections": {k: {"count": v, "text": REASONS.get(k, k)} for k, v in reasons.most_common()}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=["base", "finetuned"], required=True,
                    help="base adds two worked examples to the prompt, as the app does for the untrained model")
    ap.add_argument("--base-url", required=True, help="OpenAI-compatible endpoint serving that variant")
    ap.add_argument("--model-name", default="qwen7b-mcq")
    ap.add_argument("--test-file", required=True)
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--max-attempts", type=int, default=3)
    ap.add_argument("--out-dir", default=str(Path(__file__).parent / "results"))
    a = ap.parse_args()
    rows = [json.loads(l) for l in Path(a.test_file).read_text(encoding="utf-8").splitlines() if l.strip()]
    items = sample(rows, a.n, a.seed)
    s = Settings(_env_file=None, model_base_url=a.base_url, model_variant=a.variant, model_name=a.model_name,
                 database_url="sqlite://")
    res = evaluate(items, s, a.max_attempts)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(a.out_dir) / f"generation_{a.variant}_seed{a.seed}_n{len(items)}_{stamp}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(res)
    summ = summary(res)
    summ.update({"variant": a.variant, "base_url": a.base_url, "test_file": a.test_file, "seed": a.seed})
    out.with_suffix(".summary.json").write_text(json.dumps(summ, indent=2))
    print(json.dumps(summ, indent=2))
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
