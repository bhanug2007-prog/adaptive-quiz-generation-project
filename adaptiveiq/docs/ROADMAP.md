# Roadmap: what is not done yet

Everything in this list is either not built, or built but not verified. Nothing here is claimed as working.

## Not verified yet

- **Google Forms export** against a real Google account (needs an OAuth client; see `GOOGLE_FORMS.md`).
- **The real Qwen model inside AdaptiveIQ: automated tests.** The project team ran AdaptiveIQ with `qwen7b-mcq-Q4_K_M.gguf` on the laptop and it generates quizzes, but the automated tests still use the stand-in model server (`tests/fake_model_server.py`), and no measured run (pass rate, time per question) has been recorded yet.
- **Windows scripts** (`setup_windows.bat`, `start_windows.bat`): written for Windows, not run on Windows in this project.
- **Docker Compose** files: written, not built (no Docker daemon was available).
- **The Grok question reviewer against the real xAI API.** It is tested only with a stand-in server
  (`tests/fake_grok_server.py`); see `QUALITY_REVIEW.md`. How well its judgements, especially difficulty,
  agree with lecturers has not been measured.
- **The Lecturer Insights Agent with real Grok.** Tool choice, answer wording and the number check are tested with
  scripted replies from the stand-in server; how often real Grok answers pass the number check, and how useful
  lecturers find the answers, has not been measured (`AGENTS.md`).
- **SMTP email sending**: verification links are tested through the development outbox; real SMTP delivery has not been tried.

## Evaluation still to run

- Base vs fine-tuned Qwen 7B on the same held-out items with blind human grading (`ML_EVALUATION.md` section 1.2). The earlier pilot (30 to 90 items, AI-assisted grading) is preliminary.
- The adaptive engine on real students. Current numbers are simulations with synthetic students.
- The mastery half-life (21 days) and the trend test are fixed assumptions; fit them on real answer data.

## Planned features

- **Expiring, revocable lecturer invitations** (one token per person, with an expiry date) instead of one shared invite code. The current code is rate-limited and never returned by the API.
- Password reset by email (today a lecturer or admin resets it).
- Per-session sign-out (today sign-out ends all of a user's sessions, which is safe but blunt).
- A supervised weak-area model once real outcome labels exist, with the rules as its baseline.
- Item response theory (IRT) calibration of question difficulty once questions have enough answers.
- Multiple institutions (the column exists) and an admin role.
- Running more than one backend process: the generation queue, login limiter and invite limiter live in one process today.
