# ML evaluation: methods, results so far, and how to reproduce them

AdaptiveIQ has two kinds of intelligence, kept apart on purpose:

1. **Question generation** by a large language model (fine-tuned Qwen2.5-7B-Instruct, a decoder-only Transformer).
2. **The adaptive engine** (`backend/app/ml`): mastery estimation, weak-area rules, difficulty adaptation, recommendations, spaced revision, confidence calibration and question statistics. It never calls the LLM, and the LLM never produces a mastery score.

Each part is evaluated differently. This document says what is measured, what has been measured so far, and what has not. **Nothing here is measured on real students yet.** The adaptive-engine numbers come from simulations with synthetic students, and the model numbers so far come from a small pilot with AI-assisted grading.

---

## 1. Question generation

### 1.1 What has been measured so far (preliminary)

These come from the team's earlier notebooks (`adaptive-quiz/results/`). Correctness was graded with AI assistance (the `claude_grade` column); the human-grading column in those files is empty. Treat them as a pilot, not as accuracy figures.

| Model | Items | Judged correct (AI-assisted) |
|---|---|---|
| Qwen2.5-1.5B-Instruct (zero-shot) | 30 | 16 |
| Qwen2.5-3B-Instruct (zero-shot) | 30 | 18 |
| Qwen2.5-7B-Instruct (zero-shot) | 30 | 25 |
| Qwen2.5-7B-Instruct, two worked examples (the app's `base` variant) | 30 | 26 |
| Qwen2.5-7B fine-tuned (LoRA), same 30 pilot items | 30 | 24 |
| Qwen2.5-7B fine-tuned, all 90 inputs | 90 | 67 |
| Qwen2.5-7B fine-tuned, 18 new formula-heavy topics chosen by the team | 18 | 9 |

FLAN-T5 was tried first and dropped: most of its outputs were not usable questions.

What this does and does not show: with 30 items, a 95% interval around 24/30 runs from about 63% to 91%, and around 26/30 from about 70% to 95%. The intervals overlap heavily, so **these results cannot say which 7B variant is better.** They do show that the 7B models are far ahead of the 1.5B and 3B ones and of FLAN-T5, and that formula-heavy topics are the weak spot (hence the Python maths check in the pipeline).

### 1.2 The comparison that will settle it

Both 7B variants are run on the **same held-out items** with the **same prompt code and checks the app uses**, then graded **blind by people**.

| Dimension | How it is measured | Automatic or human |
|---|---|---|
| Answer correctness | The marked option is right and the others are wrong | Human (blind) |
| Topic relevance | The question tests the requested topic and passage | Human (blind) |
| Difficulty | The question matches the requested level | Human (blind) |
| Structure | 4 non-empty, distinct options, exactly one valid key, parsable format | Automatic |
| Duplicates | Near-identical to an earlier question in the run (text + TF-IDF similarity) | Automatic |
| Reliability | First-try pass rate, final pass rate within 3 attempts, retry rate, failures, seconds per call, rejection reasons | Automatic |
| Human review in the app | Lecturer approve, reject and edit rates per model version (`GET /api/lecturer/model-quality`, Question Analytics page) | From real use |

**Test items.** `adaptive-quiz/data/clean/test.jsonl`: 1,190 rows, split by topic from the training data, so no test topic was seen in fine-tuning. The script samples items stratified by difficulty, one per topic, with a fixed seed (60 items by default: 20 easy, 20 medium, 20 hard).

**Statistics.** Each rate is reported with a 95% Wilson interval. The two models are compared with an exact McNemar test on the paired items, because only items where the models disagree carry information. With a second grader, Cohen's kappa shows how far the graders agree. A p-value above 0.05 means the data cannot separate the models; it does not mean they are equal.

**Run it** (one model at a time on the laptop; start llama-server with the matching GGUF first):

```bash
cd backend
python -m evaluation.evaluate_generation --variant base      --base-url http://127.0.0.1:8080 --test-file ../../data/clean/test.jsonl --n 60 --seed 7
python -m evaluation.evaluate_generation --variant finetuned --base-url http://127.0.0.1:8080 --test-file ../../data/clean/test.jsonl --n 60 --seed 7
python -m evaluation.make_grading_sheet --a evaluation/results/generation_base_....csv --b evaluation/results/generation_finetuned_....csv
#   fill correct / on_topic / difficulty with 1 or 0 in evaluation/results/grading_sheet.csv (Excel is fine)
python -m evaluation.score_grading --sheet evaluation/results/grading_sheet.csv --key evaluation/results/grading_sheet_KEY_do_not_open_until_graded.json
```

On a laptop CPU one call takes roughly 1 to 2 minutes, so 60 items per model is a few hours each; a GPU host is much faster.

**Results:** not run yet. Fill this table from `grading_sheet.scores.json` once it is:

| | Base 7B | Fine-tuned 7B | McNemar p |
|---|---|---|---|
| Answer correctness | | | |
| Topic relevance | | | |
| Difficulty match | | | |
| First-try pass rate (automatic) | | | |
| Final pass rate within 3 tries | | | |
| Seconds per call | | | |

### 1.3 What the automatic checks can and cannot catch

Passing every check means a question is well-formed, not a duplicate, does not give its answer away, is supported by the reference passage when one is given, and, for numeric questions, that an independent Python calculation agrees with the key. It does **not** prove a conceptual question is correct. That is why lecturer assessments require human approval of every question, and why student practice quizzes are labelled as AI-generated and not reviewed.

---

## 2. Topic mastery estimation

**Method** (`app/ml/mastery.py`, version `mastery-beta-v3`). A Beta-Bernoulli estimate: each answer adds a weighted count to correct or incorrect; weight = recency (half-life 21 days) × difficulty (a correct hard answer and a wrong easy answer count more) × repeat (an already-seen question counts half). A skipped question counts as half a wrong answer and is always shown separately. The app shows the estimate out of 100, an 80% likely range, the evidence behind it, a trend, the confidence in the estimate and a next action. With fewer than 5 different questions, no label is given ("insufficient evidence"). Mastery is recalculated only from submitted attempts, never from autosaved answers. Every label threshold is compared on the whole number shown on screen (half rounds up), so a label never disagrees with the score next to it. v3 replaced the trend's z-test with Fisher's exact test (below).

**Baseline.** Plain accuracy (share correct, skips counted as wrong) with the same 5-question minimum and the same label cut-offs.

**Simulation** (`python -m evaluation.simulate_mastery`; tables regenerated on 2 Nov 2026, because the saved ones predated the rule that compares labels on the shown whole number. Error and coverage did not change; label agreement and over-claim moved by up to 1.5 points). Synthetic students answer questions under a Rasch model, P(correct) = sigmoid(θ − b) with b = −1, 0, +1 for easy, medium, hard. "True mastery" is P(correct) on a medium question. 2,000 students per seed, 5 seeds; mean ± sd across seeds. Scenarios: stable ability with a random mix of difficulties; stable ability but mostly easy questions (skewed); ability rising by 1.5 logits over 30 answers, one a day (improving). Over-claim means a label higher than the true one, the costly error, since a student told they have mastered a topic stops practising it.

#### Scenario: stable

| answers | MAE Beta | MAE baseline | label acc. Beta | label acc. baseline | over-claim Beta | over-claim baseline | 80% coverage | trend up | trend down |
|---|---|---|---|---|---|---|---|---|---|
| 3 | 0.143 ± 0.003 | 0.220 ± 0.005 | n/a | n/a | n/a | n/a | 83.6% ± 1.2 | 0.0% ± 0.0 | 0.0% ± 0.0 |
| 5 | 0.126 ± 0.003 | 0.168 ± 0.004 | 56.7% ± 0.9 | 56.1% ± 1.2 | 18.0% ± 0.5 | 25.4% ± 0.3 | 83.6% ± 0.8 | 0.0% ± 0.0 | 0.0% ± 0.0 |
| 10 | 0.102 ± 0.002 | 0.119 ± 0.002 | 63.0% ± 0.9 | 60.9% ± 0.4 | 14.0% ± 0.7 | 25.5% ± 0.4 | 83.8% ± 1.3 | 0.5% ± 0.1 | 0.4% ± 0.2 |
| 20 | 0.079 ± 0.001 | 0.085 ± 0.002 | 68.6% ± 0.7 | 70.0% ± 0.6 | 10.9% ± 0.6 | 16.1% ± 0.4 | 86.0% ± 1.2 | 1.1% ± 0.1 | 1.1% ± 0.1 |
| 30 | 0.068 ± 0.000 | 0.071 ± 0.001 | 72.3% ± 0.5 | 74.7% ± 0.9 | 9.0% ± 0.4 | 11.5% ± 0.5 | 86.9% ± 0.4 | 1.1% ± 0.2 | 1.3% ± 0.1 |

#### Scenario: skewed

| answers | MAE Beta | MAE baseline | label acc. Beta | label acc. baseline | over-claim Beta | over-claim baseline | 80% coverage | trend up | trend down |
|---|---|---|---|---|---|---|---|---|---|
| 3 | 0.146 ± 0.001 | 0.230 ± 0.001 | n/a | n/a | n/a | n/a | 82.6% ± 0.4 | 0.0% ± 0.0 | 0.0% ± 0.0 |
| 5 | 0.130 ± 0.001 | 0.183 ± 0.002 | 53.2% ± 1.4 | 46.5% ± 0.8 | 26.4% ± 0.9 | 44.7% ± 0.8 | 82.1% ± 0.3 | 0.0% ± 0.0 | 0.0% ± 0.0 |
| 10 | 0.107 ± 0.001 | 0.143 ± 0.002 | 58.3% ± 1.3 | 44.2% ± 0.8 | 24.0% ± 0.7 | 52.0% ± 0.8 | 82.2% ± 0.4 | 0.3% ± 0.1 | 0.4% ± 0.1 |
| 20 | 0.086 ± 0.001 | 0.119 ± 0.001 | 64.9% ± 1.3 | 49.5% ± 1.3 | 21.9% ± 0.8 | 48.2% ± 1.4 | 82.2% ± 0.7 | 0.9% ± 0.3 | 1.4% ± 0.3 |
| 30 | 0.077 ± 0.001 | 0.109 ± 0.002 | 68.1% ± 1.2 | 53.0% ± 0.8 | 20.7% ± 1.0 | 45.6% ± 0.8 | 82.4% ± 0.9 | 0.6% ± 0.1 | 1.5% ± 0.2 |

#### Scenario: improving

| answers | MAE Beta | MAE baseline | label acc. Beta | label acc. baseline | over-claim Beta | over-claim baseline | 80% coverage | trend up | trend down |
|---|---|---|---|---|---|---|---|---|---|
| 3 | 0.144 ± 0.001 | 0.219 ± 0.002 | n/a | n/a | n/a | n/a | 83.2% ± 0.7 | 0.0% ± 0.0 | 0.0% ± 0.0 |
| 5 | 0.129 ± 0.002 | 0.169 ± 0.002 | 51.8% ± 1.1 | 52.8% ± 0.9 | 15.0% ± 0.8 | 23.9% ± 0.3 | 82.4% ± 0.9 | 0.0% ± 0.0 | 0.0% ± 0.0 |
| 10 | 0.112 ± 0.003 | 0.128 ± 0.003 | 51.2% ± 1.1 | 57.1% ± 0.7 | 8.2% ± 1.0 | 18.4% ± 0.9 | 80.0% ± 0.7 | 0.6% ± 0.1 | 0.3% ± 0.1 |
| 20 | 0.119 ± 0.002 | 0.131 ± 0.002 | 36.8% ± 1.3 | 50.4% ± 1.2 | 1.9% ± 0.3 | 3.6% ± 0.2 | 65.9% ± 1.1 | 2.2% ± 0.2 | 0.4% ± 0.2 |
| 30 | 0.139 ± 0.001 | 0.161 ± 0.002 | 22.8% ± 1.1 | 37.0% ± 0.8 | 0.2% ± 0.2 | 0.3% ± 0.1 | 45.5% ± 1.1 | 2.6% ± 0.8 | 0.2% ± 0.2 |


**What the simulation shows**

- The Beta estimate has a lower error than plain accuracy in every scenario and at every number of answers, and the gap is largest with few answers and when a student mostly sees easy questions.
- It over-claims much less: in the skewed case about 21 to 26% against 45 to 52% for plain accuracy.
- Its exact-label agreement is slightly lower than the baseline's in the stable case after 20 or more answers. This is the price of the conservative "strong" rule (the whole 80% range must sit above 0.80), which turns some truly strong students into "proficient". That trade was chosen on purpose.
- The 80% range covers the true value 82 to 87% of the time when ability is stable in this simulation. It is still an approximation: the answers are weighted, so it is not a calibrated statistical interval, and it has not been checked on real students. When ability rises steadily, the estimate lags behind and coverage falls to about 46% by 30 answers. Recency weighting with a 21-day half-life is not enough for fast learners.
- Trend detection: a plain 20-point threshold on the last 5 answers flagged about 20% of students with unchanged ability as improving or declining. Version 2 added a two-proportion z-test, which brought false flags to about 2 to 3% in each direction. An external review pointed out that a z-test is unreliable with only 5 answers on one side, and checking every possible small table confirmed it: for example it called 0 of 5 right after 3 of 5 a decline, while Fisher's exact test gives p = 0.17. Version 3 uses Fisher's exact test (two-sided, 5% level, `mastery.fisher_exact_p`, checked against scipy on every table in the tests). False flags are now about 0.5 to 1.5% in each direction. The cost: the trend fires even more rarely, only about 2.6% of the improving students are flagged by 30 answers. The app therefore says "No clear change" rather than "Stable", and the trend is a secondary signal, not part of the score.
- The 5-question minimum is a policy, not a statistical threshold: the error at 5 answers (about 0.13) is only a little lower than at 3 (about 0.14). The range and evidence level carry the uncertainty; the minimum stops a label from appearing on almost nothing.

**Half-life sweep** (same model, 30 answers, 2,000 students, one seed):

| Half-life (days) | Stable: error | Stable: 80% coverage | Improving: error | Improving: 80% coverage |
|---|---|---|---|---|
| 7 | 0.081 | 0.90 | 0.121 | 0.75 |
| 14 | 0.071 | 0.89 | 0.131 | 0.56 |
| 21 (current) | 0.068 | 0.87 | 0.137 | 0.47 |
| 42 | 0.066 | 0.83 | 0.144 | 0.37 |
| no decay | 0.066 | 0.79 | 0.152 | 0.28 |

A shorter half-life follows improving students better but is noisier for stable ones. It is one setting, `MASTERY_HALF_LIFE_DAYS`; choosing it well needs real data.

---

## 3. Difficulty adaptation

**Policy** (`app/ml/difficulty.py`, `difficulty-policy-v1`): with insufficient evidence the next practice quiz mixes easy, medium and hard. With evidence, it steps up one level when the score is at least 0.75, the lower bound at least 0.60 and recent accuracy at least 80%; it steps down one level when the score is below 0.50 or recent accuracy is 40% or lower; otherwise it stays. A step needs at least 3 recent answers and is never more than one level. Every change comes with its reason, shown to the student.

**Simulation** (`python -m evaluation.simulate_adaptive`): 8 practice quizzes of 5 questions on one topic per synthetic student, against "always medium" and "always mixed". The measure is how well each question's difficulty fits the student: the share answered with a 50 to 85% chance of success. That band is a common rule of thumb for practice and is an assumption here.

#### static ability

| policy | in 50-85% band | too hard (<40%) | too easy (>90%) | mean abs(p - 0.7) | level changes per student |
|---|---|---|---|---|---|
| adaptive | 69.9% ± 1.2 | 12.9% ± 1.0 | 1.6% ± 0.2 | 0.148 ± 0.004 | 1.788 ± 0.023 |
| fixed | 45.6% ± 1.4 | 34.8% ± 0.7 | 1.3% ± 0.2 | 0.238 ± 0.003 | 0.000 ± 0.000 |
| mixed | 45.9% ± 0.5 | 31.5% ± 0.8 | 5.1% ± 0.2 | 0.235 ± 0.003 | 0.000 ± 0.000 |

#### learning ability

| policy | in 50-85% band | too hard (<40%) | too easy (>90%) | mean abs(p - 0.7) | level changes per student |
|---|---|---|---|---|---|
| adaptive | 61.3% ± 0.7 | 6.3% ± 0.2 | 11.8% ± 0.3 | 0.144 ± 0.001 | 1.850 ± 0.013 |
| fixed | 56.1% ± 0.7 | 14.6% ± 0.5 | 10.0% ± 0.2 | 0.173 ± 0.003 | 0.000 ± 0.000 |
| mixed | 47.5% ± 0.7 | 15.9% ± 0.4 | 17.9% ± 0.8 | 0.192 ± 0.002 | 0.000 ± 0.000 |


**What it shows.** Under these assumptions the adaptive policy puts more questions in the target band than either fixed baseline, and far fewer questions that are too hard (13% against 32 to 35% for static ability). For students who are learning it still does better than the baselines, but it gives slightly more too-easy questions than always-medium, because stepping up is deliberately strict. It changes level about twice per student over 8 quizzes, so it is not jumpy. **This does not show that students learn more.** That needs real students, for example comparing pre- and post-test scores between groups using adaptive and fixed practice.

---

## 4. Weak-area detection

Transparent rules (`app/ml/weak_areas.py`, `weak-rules-v2`): weak means "needs improvement", or "developing"/"proficient" with a clear decline (the same significance-tested trend as above). Unattempted topics are never called weak. No supervised model is trained, because there are no trustworthy "truly weak" labels yet; K-Means was deliberately not used, since clusters would add a claim of machine learning without adding meaning. Once real outcomes exist (for example a later exam score per topic), these rules become the baseline for a supervised model, judged by precision, recall and F1 on held-out students.

Topics the student often leaves blank (at least 5 questions seen and 30% or more skipped) are listed separately, not as weak, because skipping can mean running out of time. Weak areas are per topic; there is no per learning-objective breakdown yet, because questions are not tagged with objectives.

## 5. Other parts of the engine

| Part | Rule | Evaluation plan |
|---|---|---|
| Recommendations (`reco-rules-v2`) | At most 6, each with its reason: practise a weak topic at the suggested level, a weak prerequisite first, revisit missed questions, and (lowest priority, added 2 Nov) try a harder quiz once a topic is mastered with enough evidence and the difficulty rule says step up | Share followed, and mastery change on that topic afterwards |
| Spaced revision (`leitner-v1`) | Missed or skipped questions enter box 1; intervals 1, 3, 7, 14, 30 days; a wrong answer goes back to box 1 | Retention on revision items against items not scheduled |
| Confidence calibration | Needs 10 rated answers and 3 per level before showing a pattern | Whether "sure but wrong" falls over time |
| Question statistics | Facility p, point-biserial discrimination, expected p range by difficulty; no flag below 10 answers | Lecturer agreement with the flags |

## 6. Reproduce

```bash
cd backend
python -m evaluation.simulate_mastery    # writes evaluation/results/mastery_simulation.json
python -m evaluation.simulate_adaptive   # writes evaluation/results/adaptive_simulation.json
python -m pytest tests/test_ml.py tests/test_evaluation.py
```

Every simulation uses fixed seeds, so the tables above come out the same on any machine.
