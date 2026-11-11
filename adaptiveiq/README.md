# AdaptiveIQ

AdaptiveIQ is an AI-assisted adaptive assessment platform. Lecturers build quizzes with a fine-tuned **Qwen2.5-7B** model, review and publish them, and see where their class is struggling. Students take assigned quizzes, generate their own practice, and get an explainable picture of what they know, with recommendations and spaced revision.

A DSAI team project at IIIT Dharwad, guided by Dr. Utkarsh Mahadeo Khaire.

```
Browser (React 19 + Vite)  --/api-->  FastAPI backend  -->  PostgreSQL
  landing page, portals                auth, permissions, quizzes, scoring,
  never sees answer keys early         adaptive engine (app/ml), analytics
                                            |
                                            | question generation only
                                            v
                                     llama.cpp llama-server
                                     qwen7b-mcq-Q4_K_M.gguf (OpenAI-compatible API)
```

The language model only writes questions. Mastery, weak areas, difficulty and recommendations come from a separate, explainable engine that never calls the model. More in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Demo

**Video:** _add your demo video link here_ (2 to 3 minutes: lecturer generates and reviews a quiz, a student takes it,
then progress, analytics and the monitoring report).

| Lecturer | Student |
|---|---|
| ![Generating questions](docs/screenshots/generate.png) | ![Taking a quiz](docs/screenshots/quiz.png) |
| ![Reviewing questions](docs/screenshots/review.png) | ![My Progress](docs/screenshots/progress.png) |
| ![Class analytics](docs/screenshots/analytics.png) | ![Monitoring consent](docs/screenshots/monitoring_consent.png) |
| ![Monitoring report](docs/screenshots/monitoring_report.png) | ![Recommendations](docs/screenshots/recommendations.png) |

Screenshots go in `docs/screenshots/` with these names. The site was demonstrated locally and is not deployed: the
7B model needs a GPU or a long CPU wait, so the project is shown through this video and the code.

## Highlights

- **Fine-tuned LLM for MCQ generation:** Qwen2.5-7B-Instruct fine-tuned with LoRA, quantised to GGUF (Q4_K_M,
  4.7 GB) and served with llama.cpp through an OpenAI-compatible API.
- **Question Quality Agent:** generates, validates (answer format, duplicates, a Python maths check), has an AI
  reviewer (Grok) score each question, regenerates failures within a retry limit, and logs every decision. It never
  publishes; a lecturer approves every question.
- **Explainable adaptive engine** (no LLM): topic mastery with recency weighting, trend, weak areas, difficulty
  adaptation, recommendations and spaced revision.
- **Lecturer Insights Agent:** answers questions like "Which topics are hardest for my class?" from read-only database
  tools, with the numbers checked against the data and students anonymised.
- **Optional integrity monitoring** with consent: page leaves, full screen, face count with MediaPipe in the browser,
  speech-like sound. Neutral wording, never labels anyone as cheating, no video or audio stored.
- **Security:** roles and permissions on every route (checked by an automated sweep of all API routes), answer keys
  never sent before submission, CSRF protection, rate limits, request size limits.

## Tech stack

React 19 + Vite · FastAPI · SQLAlchemy + Alembic · PostgreSQL 16 (or SQLite) · llama.cpp · Qwen2.5-7B (LoRA, GGUF) ·
xAI Grok (question review) · MediaPipe · Docker Compose · pytest, Vitest, Playwright

## Key results

| What | Result |
|---|---|
| Real end-to-end run with the fine-tuned model (laptop CPU, 2 Nov 2026) | 54 of 54 checks passed; 10 questions with the requested 3/4/3 difficulty mix in 994 s (about 54 s per question) |
| Hand check of those 10 questions | 7 fine, 2 with a wrong answer key, 1 duplicate in different words. This is why there is an AI reviewer and lecturer approval ([docs/QA_REPORT.md](docs/QA_REPORT.md)) |
| Pilot model comparison (30 items, AI-assisted grading, preliminary) | 1.5B: 16/30 · 3B: 18/30 · 7B: 25/30 · fine-tuned 7B: 24/30. The 7B models are far ahead; the pilot cannot separate the 7B variants ([docs/ML_EVALUATION.md](docs/ML_EVALUATION.md)) |
| Automated tests | 180 backend (SQLite and PostgreSQL), 97 frontend, 5 browser tests |
| Performance (150 synthetic students) | Lecturer insights 0.43 s after removing an N+1 query problem (was 3.5 s) |

## 1. What works, and how it was checked

| Part | Status |
|---|---|
| Backend API (auth, courses, generation, review, quizzes, attempts, scoring, analytics, reports) | Done. 180 automated tests pass on PostgreSQL 16 and SQLite (`backend/tests`), including edge cases, simultaneous submits and sandbox escape attempts |
| Adaptive engine: mastery, trend, weak areas, difficulty policy, recommendations, spaced revision, confidence, question statistics | Done. Unit tests plus simulations with synthetic students ([docs/ML_EVALUATION.md](docs/ML_EVALUATION.md)) |
| Landing page, student portal, lecturer portal | Done. Build passes, 97 component tests, and two end-to-end browser tests (lecturer builds and publishes a quiz, student joins and takes it; a monitored quiz) pass with the stand-in model |
| Email + password sign-in, email verification, lecturer invite code | Done and tested. Real SMTP delivery not tried yet |
| AI question review (Grok) after the Python checks, with retries, kept failures, difficulty-mix check and a Python-only fallback | Done and tested with a stand-in Grok server, on SQLite and PostgreSQL; **not yet run with a real xAI key** ([docs/QUALITY_REVIEW.md](docs/QUALITY_REVIEW.md)) |
| Two AI agents: the Question Quality Agent (runs generation with fixed tools and rule-based retry decisions, every step logged) and the Lecturer Insights Agent ("Ask about your class": read-only analytics tools, Grok optional, numbers checked against the data, students anonymised) | Done and tested with the stand-in model and a stand-in Grok server, on SQLite and PostgreSQL; **the Insights Agent is not yet run with a real xAI key** ([docs/AGENTS.md](docs/AGENTS.md)) |
| Assessment integrity monitoring (optional per quiz): page leaves, full screen, camera face count with MediaPipe in the browser, speech-like sound; consent screen; neutral lecturer report and timeline; no video or audio stored | Done and tested (API on SQLite and PostgreSQL, components, and real Chromium with its fake camera and microphone); **not tried with real webcams and real people yet** ([docs/MONITORING.md](docs/MONITORING.md)) |
| Model evaluation pipeline (base vs fine-tuned, blind human grading, McNemar test) | Done and tested with a stand-in model; **not yet run on the real models** |
| Google Forms export | Code written; **not tested against Google** (needs an OAuth client). Manual export works |
| Real Qwen model inside AdaptiveIQ | Run on the laptop with the GGUF model (November 2026): the full 20-step check passed (54/54), about 54 s per question on CPU. `python -m scripts.real_model_check` and `python -m scripts.full_flow_check` (section 4) do it in one command |
| Docker Compose (database, backend, website) | Built and run on Linux Docker; the browser test passes against it ([docs/DOCKER.md](docs/DOCKER.md)) |
| Qwen model container, Docker Desktop on Windows, Windows .bat scripts | Written; **not run yet** |

The full list of what is missing is in [docs/ROADMAP.md](docs/ROADMAP.md).

## 2. Run it on Windows

### 2.1 Install once

1. **Python 3.11 or newer** from https://www.python.org/downloads/ . Tick **Add python.exe to PATH**.
2. **Node.js 22 LTS** (22.12 or newer) from https://nodejs.org .
3. **PostgreSQL 16** (recommended) from https://www.postgresql.org/download/windows/ (the EDB installer). Remember the password you set for the `postgres` user. Then open **SQL Shell (psql)** from the Start menu, press Enter for the defaults, type that password, and run:

   ```sql
   CREATE DATABASE adaptiveiq;
   ```

   No PostgreSQL? Choose SQLite during setup for a quick local run. `/api/health` always shows which database is active.
4. **The model** (only needed for question generation): `qwen7b-mcq-Q4_K_M.gguf` (4.68 GB, from the Kaggle conversion notebook) and llama.cpp for Windows (https://github.com/ggml-org/llama.cpp/releases, the zip ending in `bin-win-cpu-x64.zip`).

Folder layout:

```
adaptive-quiz\
  models\qwen7b-mcq-Q4_K_M.gguf
  llama\llama-server.exe   (and its .dll files)
  adaptiveiq\              (this project)
```

### 2.2 Set up

Double-click **`setup_windows.bat`**. It installs the Python and Node packages and asks three questions:

- **PostgreSQL or SQLite.** For PostgreSQL, enter `postgresql+psycopg://postgres:YOUR_PASSWORD@127.0.0.1:5432/adaptiveiq`.
- **Lecturer invite code.** Lecturers type it when they sign up; students do not need it. Keep it private.
- **Email verification.** Without SMTP settings the verification link is printed in the backend window, so you can open it from there. Answer `n` for a local demo if you prefer.

It then creates the database tables (`alembic upgrade head`).

### 2.3 Start

Double-click **`start_windows.bat`**. It opens three windows (model, backend, website) and then http://localhost:5173 . The model takes up to a minute to load; the badge at the top right turns to **Qwen 7B online**. Close the windows to stop.

The site works without the model; only generation needs it. On a laptop CPU one question takes roughly 1 to 2 minutes, so for a live demo generate quizzes beforehand or use 5 questions with reference text.

### 2.4 Manual start (any OS)

```bash
# terminal 1: model
llama-server -m ../models/qwen7b-mcq-Q4_K_M.gguf -c 4096 --port 8080
# terminal 2: backend
cd backend
python -m venv .venv && .venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m scripts.configure_env                        # or copy .env.example to .env and edit it
python -m alembic upgrade head
uvicorn app.main:app --port 8000
# terminal 3: frontend
cd frontend && npm install && npm run dev
```

## 3. First steps in the app

1. **Create account**, choose **Lecturer**, enter the invite code. Verify your email (link in the backend window if SMTP is not set).
2. **Courses & Subjects**: create a course, a subject (set its quiz weight cap), a unit and topics. Share the course **join code** with students.
3. **Create Quiz**: pick a topic, generate, review every question (approve, edit, reject or regenerate), set the rules, publish.
4. Students **Create account** as Student, join with the code, and take the quiz under **Assigned Quizzes**. They can also generate practice quizzes, which are labelled AI-generated and not reviewed by a lecturer.
5. Results feed **My Progress** and **Learning Insights** for the student, and **Class Analytics** and **Question Analytics** for the lecturer.

## 4. Tests

```bash
cd backend && pip install -r requirements-dev.txt
python -m pytest                                        # SQLite
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/adaptiveiq_test python -m pytest   # PostgreSQL
cd ../frontend && npm test                              # component tests
npm run test:e2e                                        # browser test (starts a backend with the stand-in model)
# in a container with its own Chromium: PLAYWRIGHT_CHROMIUM=/path/to/chromium npm run test:e2e
```

**Real model check.** With llama-server running the GGUF and the backend started (email verification off):

```bash
cd backend
python -m scripts.real_model_check --url http://localhost:8000 --invite YOUR_INVITE_CODE   # Docker: --url http://localhost:8088
# restart the backend and the model (or: docker compose restart), then
python -m scripts.real_model_check --url http://localhost:8000 --after-restart
```

It generates 5 questions with the real model, prints every question with its automatic-check results, approves and publishes them, has a separate student answer 3 right, 1 wrong and skip 1, and compares the score, mastery, weak area and recommendations with the rules. After the restart it checks that everything is still there. Reports go to `backend/evaluation/results/real_model_check_*.md`.

**Full 20-step check** (the roadmap's end-to-end scenario: 10 questions with a 3/4/3 difficulty mix, the Question Quality Agent, approval, a monitored attempt, marks, mastery, released results, analytics and the Lecturer Insights Agent):

```bash
cd backend
python -m scripts.full_flow_check --url http://localhost:8000 --invite YOUR_INVITE_CODE
```

Results and what was found in Phase 7 are in [docs/QA_REPORT.md](docs/QA_REPORT.md).

Tests never use the real model: `backend/tests/fake_model_server.py` is a test-only stand-in that returns canned questions, including broken ones, to exercise every check.

To work on the UI with test data and no model: `backend/scripts/dev_fake_stack.sh` (prints test accounts).

## 5. Configuration

All settings are in `backend/.env`; every one is listed with a comment in [backend/.env.example](backend/.env.example). The ones you are most likely to change: `DATABASE_URL`, `SECRET_KEY`, `LECTURER_INVITE_CODE`, `ALLOWED_EMAIL_DOMAINS`, `REQUIRE_EMAIL_VERIFICATION` and `SMTP_*`, `MODEL_BASE_URL`, `MODEL_VARIANT` (`finetuned` or `base`).

## 6. Documents

| File | Contents |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Services, data model, user journeys, security |
| [docs/ML_EVALUATION.md](docs/ML_EVALUATION.md) | How the model and the adaptive engine are evaluated, and results so far |
| [docs/API.md](docs/API.md) | Every endpoint (generated from the code); `docs/openapi.json`; `docs/api-samples/` |
| [docs/DOCKER.md](docs/DOCKER.md) | Run everything in Docker (nothing else installed on the laptop) |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Production checklist, Docker Compose, Linux server, model hosting |
| [docs/GOOGLE_FORMS.md](docs/GOOGLE_FORMS.md) | Google Forms setup and test plan |
| [docs/AGENTS.md](docs/AGENTS.md) | The two agents: their tools, decisions, logs, privacy rules and fallbacks |
| [docs/MONITORING.md](docs/MONITORING.md) | Integrity monitoring: what is recorded, consent, review statuses, retention and limits |
| [docs/QUALITY_REVIEW.md](docs/QUALITY_REVIEW.md) | How generated questions are checked: Python checks, the Grok reviewer, retries and the fallback |
| [docs/QA_REPORT.md](docs/QA_REPORT.md) | Phase 7 test results, bugs fixed, security and performance checks |
| [docs/ROADMAP.md](docs/ROADMAP.md) | What is not built or not verified yet |
| [deploy/kaggle/README.md](deploy/kaggle/README.md) | Optional: run the model on a free Kaggle GPU for a demo |

## 7. Project layout

```
backend/
  app/api/            HTTP endpoints, one file per area
  app/services/       generation, validation, attempts, grading, analytics, permissions, mail
  app/ml/             adaptive engine (pure functions, unit tested)
  app/models/         SQLAlchemy tables;  alembic/  migrations
  app/validators/     answer-format, number and Python maths checks
  app/integrations/   Google Forms
  evaluation/         simulations and the model evaluation pipeline
  scripts/            setup helper, test-data seeding, API doc generator
  tests/
frontend/
  src/pages/          landing, auth, student, lecturer
  src/components/     ui kit, charts, landing, student, lecturer
  src/api/            API client (one place for every endpoint)
  e2e/                Playwright test
docs/
```
