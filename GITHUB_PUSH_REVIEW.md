# GitHub push review

Reviewed 2026-11-11.
Repository: https://github.com/bhanug2007-prog/adaptive-quiz-generation-project
Remote main was verified live at fe6482b7d503b65b50c804b489dd182d090d0c81, matching local HEAD. Its 338 tracked files are already on GitHub.

## Decision

Push the modified and new files listed below together after application validation. They contain application source, database migrations 0003-0007, tests, deployment scripts, documentation, API samples, dependency manifests and the lockfile. Keep the three verification Markdown reports as engineering evidence. Keep the 229,746-byte MediaPipe face detector and its README; generated WASM is restored by the npm scripts and stays ignored.

Keep existing notebooks, research CSV results and the 12.48 MB dataset ZIP already on GitHub. Do not re-add the extracted dataset, model weights, llama binaries, app ZIP, dependencies or build output.

## Keep local (ignored)

- .env and .env.* secrets; .env.example templates remain eligible.
- .run-logs/, *.log and process metadata.
- SQLite databases and database side files, development reset outbox.
- Python/Node dependencies, build output, caches, coverage and Playwright reports.
- Private key files (*.pem, *.key).
- adaptiveiq/backend/evaluation/results/full_flow_check_*.md: local account identifiers and join codes.
- models/, llama/, *.gguf, archives except the existing dataset ZIP, extracted dataset, old apps/backups.
- Generated MediaPipe WASM and existing generated grading/generation CSV exclusions.

Ignoring files does not delete local files or remove previously published history. No currently tracked file matches the final ignore rules, so no untracking is required.

## Verification and limits

Live remote hash comparison succeeded. Common GitHub, Hugging Face, Groq/OpenAI token patterns and private-key headers were scanned in 445 candidate files before exclusions; no matches were found. The dataset ZIP was skipped as binary/large, and the face detector was skipped as binary. This is a targeted scan, not a guarantee that every kind of sensitive data is absent. Ignore-rule checks and whitespace validation passed. Application tests were not run for this file-selection review; push candidates are not a claim of release readiness. No staging, commit or push was performed.

## Modified tracked files (70)

- `.gitignore`
- `adaptiveiq/.gitignore`
- `adaptiveiq/README.md`
- `adaptiveiq/backend/.env.example`
- `adaptiveiq/backend/app/api/auth.py`
- `adaptiveiq/backend/app/api/generation.py`
- `adaptiveiq/backend/app/api/lecturer_quizzes.py`
- `adaptiveiq/backend/app/api/questions.py`
- `adaptiveiq/backend/app/api/student_analytics.py`
- `adaptiveiq/backend/app/api/student_quizzes.py`
- `adaptiveiq/backend/app/core/config.py`
- `adaptiveiq/backend/app/core/db.py`
- `adaptiveiq/backend/app/main.py`
- `adaptiveiq/backend/app/ml/recommendations.py`
- `adaptiveiq/backend/app/schemas/attempts.py`
- `adaptiveiq/backend/app/schemas/auth.py`
- `adaptiveiq/backend/app/schemas/quizzes.py`
- `adaptiveiq/backend/app/services/adaptive_service.py`
- `adaptiveiq/backend/app/services/attempt_service.py`
- `adaptiveiq/backend/app/services/class_analytics.py`
- `adaptiveiq/backend/app/services/generation_service.py`
- `adaptiveiq/backend/app/services/mailer.py`
- `adaptiveiq/backend/app/services/model_service.py`
- `adaptiveiq/backend/app/services/quiz_views.py`
- `adaptiveiq/backend/app/services/validation_service.py`
- `adaptiveiq/backend/app/validators/mathcheck.py`
- `adaptiveiq/backend/evaluation/results/adaptive_simulation.json`
- `adaptiveiq/backend/evaluation/results/adaptive_simulation.md`
- `adaptiveiq/backend/evaluation/results/mastery_simulation.json`
- `adaptiveiq/backend/evaluation/results/mastery_simulation.md`
- `adaptiveiq/backend/requirements.txt`
- `adaptiveiq/backend/scripts/dump_api_samples.py`
- `adaptiveiq/backend/tests/fake_model_server.py`
- `adaptiveiq/backend/tests/test_sandbox.py`
- `adaptiveiq/backend/tests/test_security.py`
- `adaptiveiq/docs/API.md`
- `adaptiveiq/docs/ML_EVALUATION.md`
- `adaptiveiq/docs/ROADMAP.md`
- `adaptiveiq/docs/openapi.json`
- `adaptiveiq/frontend/package-lock.json`
- `adaptiveiq/frontend/package.json`
- `adaptiveiq/frontend/playwright.config.js`
- `adaptiveiq/frontend/src/api/__tests__/client.test.js`
- `adaptiveiq/frontend/src/api/client.js`
- `adaptiveiq/frontend/src/api/endpoints.js`
- `adaptiveiq/frontend/src/app/routes.jsx`
- `adaptiveiq/frontend/src/components/lecturer/QuestionCard.jsx`
- `adaptiveiq/frontend/src/components/lecturer/QuestionReview.jsx`
- `adaptiveiq/frontend/src/components/lecturer/QuizExport.jsx`
- `adaptiveiq/frontend/src/components/lecturer/QuizSettingsForm.jsx`
- `adaptiveiq/frontend/src/components/lecturer/util.js`
- `adaptiveiq/frontend/src/components/quiz/GenerationProgress.jsx`
- `adaptiveiq/frontend/src/pages/auth/SignIn.jsx`
- `adaptiveiq/frontend/src/pages/auth/__tests__/auth.test.jsx`
- `adaptiveiq/frontend/src/pages/lecturer/ClassAnalytics.jsx`
- `adaptiveiq/frontend/src/pages/lecturer/CreateQuiz.jsx`
- `adaptiveiq/frontend/src/pages/lecturer/QuizDetail.jsx`
- `adaptiveiq/frontend/src/pages/lecturer/Quizzes.jsx`
- `adaptiveiq/frontend/src/pages/lecturer/Reports.jsx`
- `adaptiveiq/frontend/src/pages/lecturer/__tests__/lecturer.test.jsx`
- `adaptiveiq/frontend/src/pages/student/Insights.jsx`
- `adaptiveiq/frontend/src/pages/student/Practice.jsx`
- `adaptiveiq/frontend/src/pages/student/Progress.jsx`
- `adaptiveiq/frontend/src/pages/student/QuizIntro.jsx`
- `adaptiveiq/frontend/src/pages/student/QuizPlayer.jsx`
- `adaptiveiq/frontend/src/pages/student/Result.jsx`
- `adaptiveiq/frontend/src/pages/student/__tests__/student.test.jsx`
- `adaptiveiq/frontend/src/styles/components.css`
- `adaptiveiq/frontend/src/styles/lecturer.css`
- `adaptiveiq/frontend/src/styles/student.css`

## New files to include (90)

- `adaptiveiq/ACTIVITY_WARNINGS_VERIFICATION.md`
- `adaptiveiq/GROQ_REVIEW_VERIFICATION.md`
- `adaptiveiq/MONITORING_VERIFICATION.md`
- `adaptiveiq/backend/alembic/versions/0003_question_quality.py`
- `adaptiveiq/backend/alembic/versions/0004_agent_logs.py`
- `adaptiveiq/backend/alembic/versions/0005_monitoring.py`
- `adaptiveiq/backend/alembic/versions/0006_password_reset_tokens.py`
- `adaptiveiq/backend/alembic/versions/0007_learning_plans.py`
- `adaptiveiq/backend/app/agents/__init__.py`
- `adaptiveiq/backend/app/agents/checkpoint_saver.py`
- `adaptiveiq/backend/app/agents/insight_tools.py`
- `adaptiveiq/backend/app/agents/insights.py`
- `adaptiveiq/backend/app/agents/personalized_learning.py`
- `adaptiveiq/backend/app/agents/question_quality.py`
- `adaptiveiq/backend/app/agents/recorder.py`
- `adaptiveiq/backend/app/api/agents.py`
- `adaptiveiq/backend/app/api/documents.py`
- `adaptiveiq/backend/app/api/learning_agent.py`
- `adaptiveiq/backend/app/api/monitoring.py`
- `adaptiveiq/backend/app/schemas/learning_agent.py`
- `adaptiveiq/backend/app/services/document_service.py`
- `adaptiveiq/backend/app/services/learning_agent_service.py`
- `adaptiveiq/backend/app/services/learning_service.py`
- `adaptiveiq/backend/app/services/monitoring_service.py`
- `adaptiveiq/backend/app/services/password_reset.py`
- `adaptiveiq/backend/app/services/practice_service.py`
- `adaptiveiq/backend/app/services/quality_service.py`
- `adaptiveiq/backend/scripts/dev_reset_outbox.py`
- `adaptiveiq/backend/scripts/full_flow_check.py`
- `adaptiveiq/backend/scripts/live_quality_server.py`
- `adaptiveiq/backend/scripts/monitoring_test_server.py`
- `adaptiveiq/backend/tests/fake_grok_server.py`
- `adaptiveiq/backend/tests/test_adaptive.py`
- `adaptiveiq/backend/tests/test_agents.py`
- `adaptiveiq/backend/tests/test_document_generation.py`
- `adaptiveiq/backend/tests/test_learning_agent.py`
- `adaptiveiq/backend/tests/test_learning_agent_stage2.py`
- `adaptiveiq/backend/tests/test_math_validation.py`
- `adaptiveiq/backend/tests/test_monitoring.py`
- `adaptiveiq/backend/tests/test_monitoring_warnings.py`
- `adaptiveiq/backend/tests/test_password_reset.py`
- `adaptiveiq/backend/tests/test_quality.py`
- `adaptiveiq/backend/tests/test_remediation.py`
- `adaptiveiq/backend/tests/test_route_access.py`
- `adaptiveiq/deploy/hf-space/Dockerfile`
- `adaptiveiq/deploy/hf-space/README.md`
- `adaptiveiq/deploy/hf-space/create_space.py`
- `adaptiveiq/deploy/kaggle/README.md`
- `adaptiveiq/deploy/kaggle/adaptiveiq_model_server.ipynb`
- `adaptiveiq/deploy/oracle/README.md`
- `adaptiveiq/deploy/oracle/setup_model_server.sh`
- `adaptiveiq/docs/AGENTS.md`
- `adaptiveiq/docs/MONITORING.md`
- `adaptiveiq/docs/QA_REPORT.md`
- `adaptiveiq/docs/QUALITY_REVIEW.md`
- `adaptiveiq/docs/api-samples/generation_agent_steps.json`
- `adaptiveiq/docs/api-samples/generation_status_quality_mismatch.json`
- `adaptiveiq/docs/api-samples/insights_agent_run.json`
- `adaptiveiq/docs/api-samples/insights_answer_ai.json`
- `adaptiveiq/docs/api-samples/insights_answer_rules.json`
- `adaptiveiq/docs/api-samples/lecturer_question_ai_passed.json`
- `adaptiveiq/docs/api-samples/lecturer_question_failed_checks.json`
- `adaptiveiq/frontend/e2e/monitoring.spec.js`
- `adaptiveiq/frontend/e2e/warnings.spec.js`
- `adaptiveiq/frontend/public/mediapipe/README.md`
- `adaptiveiq/frontend/public/mediapipe/blaze_face_short_range.tflite`
- `adaptiveiq/frontend/scripts/copy-mediapipe.mjs`
- `adaptiveiq/frontend/scripts/live-quality-check.mjs`
- `adaptiveiq/frontend/src/components/lecturer/AgentSteps.jsx`
- `adaptiveiq/frontend/src/components/lecturer/AskClass.jsx`
- `adaptiveiq/frontend/src/components/lecturer/MonitoringReport.jsx`
- `adaptiveiq/frontend/src/components/lecturer/__tests__/agents.test.jsx`
- `adaptiveiq/frontend/src/components/lecturer/__tests__/quality.test.jsx`
- `adaptiveiq/frontend/src/components/quiz/DocumentSourcePicker.jsx`
- `adaptiveiq/frontend/src/components/student/LearningPlan.jsx`
- `adaptiveiq/frontend/src/components/student/Monitoring.jsx`
- `adaptiveiq/frontend/src/components/student/__tests__/learning_plan.test.jsx`
- `adaptiveiq/frontend/src/components/student/__tests__/monitoring.test.jsx`
- `adaptiveiq/frontend/src/components/student/__tests__/warnings.test.jsx`
- `adaptiveiq/frontend/src/monitoring/__tests__/lifecycle.test.jsx`
- `adaptiveiq/frontend/src/monitoring/__tests__/monitoring.test.js`
- `adaptiveiq/frontend/src/monitoring/__tests__/warnings.test.js`
- `adaptiveiq/frontend/src/monitoring/detectors.js`
- `adaptiveiq/frontend/src/monitoring/eventQueue.js`
- `adaptiveiq/frontend/src/monitoring/labels.js`
- `adaptiveiq/frontend/src/monitoring/useMonitoring.js`
- `adaptiveiq/frontend/src/monitoring/warnings.js`
- `adaptiveiq/frontend/src/pages/auth/ForgotPassword.jsx`
- `adaptiveiq/frontend/src/pages/auth/ResetPassword.jsx`
- `adaptiveiq/frontend/src/pages/student/__tests__/adaptive.test.jsx`

This review file (GITHUB_PUSH_REVIEW.md) may also be committed as an audit record.
