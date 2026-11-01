# AdaptiveIQ architecture

AdaptiveIQ is three separate services. The browser never loads the model.

```
 Browser (React + Vite)
    │  HTTPS, httpOnly session cookie
    ▼
 FastAPI backend ──────────────► PostgreSQL (SQLAlchemy + Alembic)
    │  question generation only
    ▼
 Model service: llama.cpp llama-server running qwen7b-mcq-Q4_K_M.gguf
 (OpenAI-compatible /v1/chat/completions, /health)
```

| Part | Responsibility | Does NOT do |
| --- | --- | --- |
| Frontend | Landing page, student portal, lecturer portal, charts | Never sees answer keys before submission; never calls the model |
| Backend API | Auth, permissions, courses, quizzes, attempts, scoring, analytics, exports | No model weights loaded in-process |
| Generation service (in backend) | Builds prompts, calls the model service, validates each question, stores drafts | Does not decide mastery or difficulty |
| Adaptive engine (`app/ml`) | Mastery, weak areas, next difficulty, recommendations, spaced revision | Does not call the LLM |
| Model service | Text generation from Qwen2.5-7B (fine-tuned or base) | No access to the database |

Question generation (the LLM) and performance analysis (the adaptive engine) are separate components. Qwen never produces a mastery score.

## Course hierarchy

`Institution → Course → Subject → Unit → Topic → Quiz`. A lecturer owns courses. The institution is optional for now; the column exists so several institutions can be supported later.

## Database relationships

```
users 1─1 student_profiles / lecturer_profiles
users(lecturer) 1─* courses 1─* course_enrollments *─1 users(student)
courses 1─* subjects 1─* units 1─* topics 1─* learning_objectives
quizzes *─* questions            (through quiz_questions: position, marks)
questions 1─4 answer_options     (exactly one is_correct)
quizzes 1─* quiz_assignments     (course-wide or one student)
quizzes 1─* quiz_sessions 1─* student_answers
quiz_sessions 1─1 quiz_results
users(student) 1─* topic_mastery_snapshots   (history, one row per recalculation)
users(student) 1─* learning_recommendations
users(student) 1─* revision_schedules *─1 questions
generation_runs *─1 model_versions ; questions *─1 generation_runs
questions 1─* question_review_records
users 1─* external_integrations ; quizzes 1─* form_exports
```

Full column list: `backend/app/models/`. Migrations: `backend/alembic/versions/`.

Rules the schema enforces:
- `answer_options`: unique `(question_id, label)`; the API guarantees exactly 4 options and one correct.
- `course_enrollments`: unique `(course_id, student_id)`.
- `student_answers`: unique `(session_id, question_id)`.
- `quiz_sessions`: unique `(quiz_id, student_id, attempt_no)`.
- Indexes on every foreign key used in analytics filters.

Topic identity: course topics are keyed `t:<topic id>`. Personal practice on a free-text topic is keyed `p:<subject>|<topic>` (lower-cased), so mastery works for both without inventing course records.

## User journeys

**Student**
1. Registers with email and password, or is added to a course by a lecturer.
2. Joins a course with the lecturer's join code.
3. Opens Assigned Quizzes, starts an attempt; answers are saved on every change; submits.
4. Sees the result (when the lecturer's feedback setting allows) and topic-wise performance.
5. The feedback loop updates mastery, weak areas, recommendations and next difficulty.
6. Opens Practice Lab, picks a weak topic (prefilled), generates a personal quiz at the recommended difficulty, optionally rates confidence per answer.
7. Missed questions enter spaced revision and come back on schedule.

**Lecturer**
1. Registers with email, password and the lecturer invite code.
2. Creates a course, subjects, units and topics; shares the join code or adds students by email.
3. Quiz builder: chooses topic, count, difficulty mix and optional source text; the model generates drafts.
4. Reviews every question: edit, change key, regenerate one, reject, approve. Nothing is published unreviewed.
5. Previews the student view, sets marks, window, attempts, time limit, feedback release, contribution %, then publishes.
6. Watches class analytics, the student × topic heatmap, question analytics and insights; exports CSV.
7. Exports an approved quiz to Google Forms (when configured) or copies it manually.

## Model inference integration

- `MODEL_BASE_URL` points at llama-server (laptop CPU, a GPU laptop on the LAN, or a protected remote server). `MODEL_API_KEY` is sent as a Bearer token.
- `MODEL_VARIANT=finetuned|base`. Base adds two worked examples to the prompt. Both are recorded in `model_versions`, and every generated question stores which model wrote it.
- One background worker generates one question at a time, because the model answers one request at a time. Users can have one active generation at a time; the queue is capped.
- Each question goes through the validation pipeline (see `docs/ML_EVALUATION.md`) with up to 3 attempts.
- A temporary notebook URL (Colab/Kaggle tunnel) is development only, never production.

## Security

- Passwords: bcrypt. Sessions: signed JWT (type `session`, with a per-user token version) in an httpOnly, SameSite=Lax cookie; `Secure` in production. Sessions expire after `SESSION_HOURS`.
- Logout and password change bump the user's token version, so the old cookie stops working on the server, not only in the browser (this also ends the user's other sessions).
- CSRF: every state-changing `/api` request must carry `X-Requested-With: AdaptiveIQ`, and its `Origin` (or `Referer`) must be this site or a configured frontend origin. Either failure returns 403.
- Email verification: new accounts get a signed link (type `verify_email`, 48 h). Until it is opened, joining courses, generating, publishing, enrolling and Google export are refused. Verification and session tokens are typed, so one can never be used as the other.
- Lecturer sign-up needs `LECTURER_INVITE_CODE`; the code is never returned by the API, wrong codes are rate-limited per client (5 per 10 minutes). Expiring per-person invitations are on the roadmap.
- Every endpoint checks role, ownership and enrollment in the backend (`app/services/permissions.py`); a resource you may not see returns 404.
- Answer keys are only sent to the quiz owner, or to the student after submission when feedback is released.
- Login attempts are rate-limited; request sizes and reference text are capped. Security headers are set on every response.
- Reference text is passed to the model as content inside the user message, never as system instructions. The model API key stays on the backend.
- Logs never contain passwords, session tokens, reference text or student answers. One development-only exception: without SMTP settings the verification email, including its link, is written to the backend log. Production refuses to start without SMTP when verification is on.
- Production refuses to start with the development secret, a placeholder secret, insecure cookies or SQLite. In production an email that cannot be sent is logged without its body, so a link never reaches the logs.
- Model-written Python (the calculation check) is untrusted and runs behind independent layers (`app/validators/mathcheck.py`): a static check of the code (allowed imports only, no dangerous names, no `_` attributes, no while loops); a whitelist of builtins and an import hook inside the child; a separate `python -I -S -B` process in an empty temporary folder with an empty environment and a wall-clock timeout; on Linux/macOS OS limits of 512 MB memory, 5 s CPU, no file writes and 32 open files; and on Linux, when the kernel allows it, an empty network namespace. `/api/health` reports which layers are active. Windows has no OS limits, so there the check does not run unless `MATH_CHECK_ALLOW_WITHOUT_OS_LIMITS=true`; numeric questions are then marked "unchecked" for the lecturer. In Docker the network-namespace layer is usually not allowed; the other layers apply.
- Attempts: saving an answer, checking it and submitting lock the attempt row (`SELECT ... FOR UPDATE` on PostgreSQL), and the database allows one result per attempt and one answer per question. A repeated or simultaneous submit returns the first result and never scores twice (`tests/test_edge_cases.py`).

## Phases

| Phase | Scope |
| --- | --- |
| 1 | Landing page, auth, both portals, courses/topics, AI generation, validation, review, attempts, scoring, results |
| 2 | Mastery, weak areas, difficulty adaptation, feedback loop, recommendations, heatmap, question analytics |
| 3 | CSV reports, spaced revision, confidence tracking, objective coverage, difficulty calibration, Google Forms interface |
| 4 | End-to-end tests, deployment guide, synthetic demo data, evaluation report |
