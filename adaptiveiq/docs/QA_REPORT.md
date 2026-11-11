# Phase 7 quality assurance report

Date: 2 November 2026. Everything below was run, not assumed. Where something was **not** run (the real Qwen
model, real Grok, Windows, Docker), it says so.

## 1. Automated tests

| Suite | Command | Result |
|---|---|---|
| Backend on SQLite | `cd backend && python -m pytest` | **179 passed** |
| Backend on PostgreSQL 16 | `TEST_DATABASE_URL=postgresql+psycopg://... python -m pytest` | **179 passed** |
| Frontend components | `cd frontend && npm test` | **97 passed** (10 files) |
| Frontend build | `npm run build` | passes |
| Browser (real Chromium) | `npm run test:e2e` | **5 passed**: lecturer builds and publishes a quiz, student joins and takes it, integrity monitoring with the real MediaPipe face detector |

Added in this phase: 3 backend tests (`tests/test_route_access.py` ×2, one in `tests/test_security.py`) and two
assertions in `tests/test_quality.py`.

### Coverage against the roadmap's test list

| Area | Where it is tested |
|---|---|
| Registration, login, logout, unauthorised access, roles | `test_auth.py`, `test_account_security.py`, `test_security.py`, **`test_route_access.py`** (every API route, signed out → 401; student on lecturer routes and lecturer on student routes → 403) |
| Generation: structured output, invalid output, validation, difficulty, regeneration, retry limit, drafts | `test_flow.py`, `test_quality.py`, `test_agents.py` (stand-in model with broken replies) |
| Agents: tool choice, decisions, retries end, failures, quota exhausted, approval required | `test_agents.py`, `test_quality.py` |
| Adaptive engine: right, wrong, skipped, repeats, difficulty changes, little evidence, persistence, recommendations | `test_ml.py`, `test_adaptive.py`, `test_evaluation.py`; persistence after a restart by `scripts/real_model_check.py --after-restart` |
| Assessments: assignment, enrolment, timer, autosave, submit, duplicate submit, release | `test_flow.py`, `test_edge_cases.py`, `test_security.py` |
| Monitoring: page leave, full screen, camera denied, several faces, no face, microphone denied, speech, network loss, false alerts | `test_monitoring.py`, `frontend/src/monitoring/__tests__`, `components/student/__tests__/monitoring.test.jsx`, `e2e/monitoring.spec.js`. "Several faces" uses simulated detector output only |

## 2. The 20-step end-to-end check

New script `backend/scripts/full_flow_check.py` does the roadmap's whole scenario through the public API against
a running backend: lecturer signs in, creates course, subject, unit, topic, asks for 10 questions (3 easy, 4
medium, 3 hard), the Question Quality Agent checks them, failed ones are regenerated, every question is approved,
monitoring is turned on and the quiz published, a student joins, agrees to monitoring, answers 6 right, 2 wrong and
skips 2, monitoring events are sent, the student submits, and the script compares the marks, mastery (against
`app/ml/mastery.py`), the hidden-until-released results, recommendations, class analytics, the monitoring report
and two Lecturer Insights Agent answers with what they must be. It writes a report to
`backend/evaluation/results/full_flow_check_<time>.md`.

| Run | Model | AI reviewer | Database | Result |
|---|---|---|---|---|
| Stand-in, broken replies | test-only stand-in (`normal` mode) | none | SQLite | 62 passed, 0 failed. 4 of 10 questions still failed after the agent's 3 tries and the lecturer's regenerate; they stayed unapproved and were removed |
| Stand-in, clean replies | test-only stand-in (`varied` mode) | none | SQLite | 54 passed, 0 failed |
| Stand-in, AI reviewer rejects the first 2 | test-only stand-in | test-only Grok stand-in | PostgreSQL | 55 passed, 0 failed. The agent regenerated exactly the 2 rejected questions; the judged difficulty mix matched 3/4/3 |
| **Real Qwen 7B** (laptop, 2 Nov) | fine-tuned `qwen7b-mcq` GGUF Q4_K_M, CPU | Grok configured, but every call refused (HTTP 400, wrong `GROK_MODEL`) | SQLite | **54 passed, 0 failed**. 10/10 questions in 994 s (about 54 s per question); difficulty mix 3/4/3 |

Reading the 10 real questions by hand found three problems the automatic checks did not catch, which is why the
lecturer's approval is required:

- Q9 (SVM, w = (2, 3)): the key 0.4 is wrong. The margin is 2/‖w‖ = 2/√13 ≈ 0.55, which is not among the options.
- Q6 (hard-margin SVM on non-separable data): the key is wrong; the right option is "It cannot handle any
  misclassification at all".
- Q2 and Q8 ask the same thing in different words (difflib similarity 0.77, under the duplicate threshold).

The AI reviewer exists to catch exactly these, but in this run it was switched off by the HTTP 400. Cause: the
default `GROK_MODEL=grok-latest` is not a valid xAI model name. The default is now `grok-4.3` (xAI's current text
model), and the error now shows Grok's own message. The run should be repeated with the reviewer working.

To run it with the real model (backend and llama-server running, `REQUIRE_EMAIL_VERIFICATION=false`):

```bash
cd backend
python -m scripts.full_flow_check --url http://localhost:8000 --invite YOUR_LECTURER_INVITE_CODE
```

The approval in step 8 is automatic in the script; in real use the lecturer reads every question first.

## 3. Bugs found and fixed

| # | Problem | Fix | Proof |
|---|---|---|---|
| 1 | The Question Quality Agent's log said "0 AI calls" even when Grok reviewed every question, so the lecturer's step log under-reported AI use | Each attempted AI review is now counted (`QualityResult.ai_called`, `app/agents/question_quality.py`) | New assertions in `test_quality.py`; the PostgreSQL run above logs "12 AI review calls" |
| 2 | The 256 KB request limit only read the `Content-Length` header, so a chunked upload (no such header) of any size was read and parsed in full | `BodyLimit` middleware in `app/main.py` counts the body as it arrives and answers 413 | `test_oversized_bodies_are_refused_even_without_content_length` fails without the fix and passes with it; a live server answers 413 to a 2 MB chunked body |
| 3 | Lecturer **Insights** made 5,588 database queries (3.5 s) for a course with 150 students, because answers and questions were loaded one at a time | Answers and results are loaded with each attempt list, and questions in one query (`app/services/class_analytics.py`) | Same 150-student data: 193 queries, 0.43 s. Outputs of 9 lecturer analytics endpoints compared before and after: identical apart from a 0.0001 drift that also appears between two runs of the old code (recency weights use the current time) |

## 4. Security checks

| Check | Result |
|---|---|
| Every API route's sign-in and role check | Automated: `test_route_access.py` (all 116 route and method pairs). Public on purpose: health, register, login, logout, email verification, sign-up options, Google's OAuth redirect |
| Answer key before submission | Not in the student's attempt data (`test_security.py`, and checked again in the 20-step run) |
| Grok key | Read only by the backend from `backend/.env`; not in `frontend/src` or the built `frontend/dist` (searched); `.env` files are in `.gitignore` |
| Raw SQL built from strings | None found in `backend/app` |
| `dangerouslySetInnerHTML`, `innerHTML`, `eval` in the frontend | None |
| Known vulnerable packages | `npm audit --omit=dev`: 0. `pip-audit -r requirements.txt`: none found |
| Request size, rate limits, CSRF, cookies | 413 above 256 KB (now also for chunked bodies); login, invite code, resend email and Insights questions are rate limited; CSRF header and origin checks; HttpOnly session cookie (existing tests) |
| Not checked here | HTTPS, HSTS and a Content-Security-Policy are set by the hosting proxy and belong to Phase 8 |

## 5. Performance

Measured on this container (4 CPU cores), PostgreSQL 16, 150 synthetic students who each took 2 published
assessments (30 questions), 20 requests per endpoint, after fix 3:

| Endpoint | Median | Notes |
|---|---|---|
| Lecturer insights | 0.43 s | was 3.5 s |
| Lecturer class analytics | 0.29 s | was 0.55 s |
| Lecturer dashboard overview | 0.26 s | was 0.35 s |
| Heatmap, students list, question analytics | 0.2 to 0.8 s | unchanged; still one query per student or question, fine at this size |
| Student mastery, weak areas, recommendations, history, assigned quizzes | 6 to 46 ms | |
| Login | about 0.3 s | password hashing is slow on purpose |

Face detection in the browser (headless Chromium, 320×240 camera, CPU): the model loads in about 0.6 s; one check
takes about 8 ms (95th percentile 22 ms) and runs every 1.5 s, so well under 1% of one core.

Frontend build: the main bundle is 81 KB gzipped; charts (107 KB gzipped) and the face detector (40 KB gzipped plus
its WebAssembly) load only on the pages that use them.

Qwen generation speed is measured by the 20-step script on the laptop (seconds per question are in its report).

## 6. Model and agent evaluation

The pilot figures in `ML_EVALUATION.md` were recounted from the result files in `adaptive-quiz/results/`:
1.5B 16/30, 3B 18/30, 7B 25/30, 7B with two worked examples 26/30, fine-tuned 24/30 on the same pilot items, 67/90
on all inputs, 9/18 on the formula-heavy topics. All match. They were graded with AI assistance and the human
column is empty, so they stay labelled preliminary, and the document still says they cannot show which 7B variant
is better. The blind base-versus-fine-tuned comparison (`ML_EVALUATION.md` section 1.2) needs the laptop and
human graders; it has not been run.

Agents: in the 20-step runs the Question Quality Agent used generate, validate, duplicate check, AI review,
regenerate, save draft, difficulty-mix check and status tools, logged every decision, kept a question that never
passed as "Failed checks" and unapproved, stayed within 3 tries, and never published. The Insights Agent answered
both questions from database tools, logged its steps, refused a student, and fell back to its rule-based answer
when the AI reply was unusable.

## 7. Still to do before Phase 8

1. Done once (above). Run it again after setting `GROK_MODEL=grok-4.3`, to check the AI reviewer on real questions.
2. Try the monitored quiz yourself in a normal browser with a real camera and microphone (the browser test uses
   Chromium's fake devices).
3. Optional, needs time on the laptop and graders: the blind base-versus-fine-tuned evaluation.
