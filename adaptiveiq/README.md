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

## 1. What works, and how it was checked

| Part | Status |
|---|---|
| Backend API (auth, courses, generation, review, quizzes, attempts, scoring, analytics, reports) | Done. 121 automated tests pass on PostgreSQL 16 and SQLite (`backend/tests`), including edge cases, simultaneous submits and sandbox escape attempts |
| Adaptive engine: mastery, trend, weak areas, difficulty policy, recommendations, spaced revision, confidence, question statistics | Done. Unit tests plus simulations with synthetic students ([docs/ML_EVALUATION.md](docs/ML_EVALUATION.md)) |
| Landing page, student portal, lecturer portal | Done. Build passes, 51 component tests, and one end-to-end browser test (lecturer builds and publishes a quiz, student joins and takes it) pass with the stand-in model |
| Email + password sign-in, email verification, lecturer invite code | Done and tested. Real SMTP delivery not tried yet |
| Model evaluation pipeline (base vs fine-tuned, blind human grading, McNemar test) | Done and tested with a stand-in model; **not yet run on the real models** |
| Google Forms export | Code written; **not tested against Google** (needs an OAuth client). Manual export works |
| Real Qwen model inside AdaptiveIQ | Same prompt code as QuizForge, which ran with the GGUF; **AdaptiveIQ itself not yet run against it**. Run `python -m scripts.real_model_check` (section 4) to do it in one command; it passed end to end, including a restart, with the stand-in model in Docker |
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
| [docs/ROADMAP.md](docs/ROADMAP.md) | What is not built or not verified yet |

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
