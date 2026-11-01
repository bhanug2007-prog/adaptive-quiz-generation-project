# AdaptiveIQ API

Generated from the code by `python -m scripts.write_api_doc`. Interactive docs: http://127.0.0.1:8000/docs
(while the backend runs). Example responses for most endpoints: `docs/api-samples/` (test data).

**Conventions**

- JSON in and out. Errors are `{"detail": "<readable message>"}`. Validation errors (422) list each field.
- Sign-in sets an httpOnly session cookie (`aiq_session`). Send requests with credentials.
- Every POST, PUT, PATCH and DELETE must send the header `X-Requested-With: AdaptiveIQ`, and the browser's
  `Origin` must be the site itself or a configured frontend origin. Otherwise the response is 403.
- 401 = not signed in or session ended; 403 = wrong role, unverified email for that action, or blocked origin;
  404 = does not exist or not yours (the API does not reveal which); 409 = conflict with the current state
  (time is up, attempts used, question already answered); 429 = rate limited; 503 = model or integration
  not available.
- Answer keys are never in student responses before feedback is released.


## Health

| Method | Path | What it does |
|---|---|---|
| GET | `/api/health` | Health |

## Auth

| Method | Path | What it does |
|---|---|---|
| GET | `/api/auth/config` | Auth Config |
| POST | `/api/auth/register` | Register |
| POST | `/api/auth/login` | Login |
| POST | `/api/auth/logout` | Logout |
| POST | `/api/auth/verify-email` | Verify Email |
| POST | `/api/auth/resend-verification` | Resend Verification |
| GET | `/api/auth/me` | Me |
| PATCH | `/api/auth/me` | Update Me |
| POST | `/api/auth/change-password` | Change Password |

## Courses

| Method | Path | What it does |
|---|---|---|
| GET | `/api/lecturer/courses` | My Courses |
| POST | `/api/lecturer/courses` | Create Course |
| GET | `/api/lecturer/courses/{course_id}` | Course Detail |
| PATCH | `/api/lecturer/courses/{course_id}` | Update Course |
| POST | `/api/lecturer/courses/{course_id}/join-code` | Rotate Join Code |
| POST | `/api/lecturer/courses/{course_id}/subjects` | Add Subject |
| PATCH | `/api/lecturer/subjects/{subject_id}` | Update Subject |
| DELETE | `/api/lecturer/subjects/{subject_id}` | Delete Subject |
| POST | `/api/lecturer/subjects/{subject_id}/units` | Add Unit |
| PATCH | `/api/lecturer/units/{unit_id}` | Rename Unit |
| DELETE | `/api/lecturer/units/{unit_id}` | Delete Unit |
| POST | `/api/lecturer/units/{unit_id}/topics` | Add Topic |
| PATCH | `/api/lecturer/topics/{topic_id}` | Update Topic |
| DELETE | `/api/lecturer/topics/{topic_id}` | Delete Topic |
| POST | `/api/lecturer/topics/{topic_id}/objectives` | Add Objective |
| DELETE | `/api/lecturer/objectives/{objective_id}` | Delete Objective |
| GET | `/api/lecturer/courses/{course_id}/roster` | Roster |
| POST | `/api/lecturer/courses/{course_id}/enroll` | Adds students who already have accounts. Unknown emails are reported back, never auto-created. |
| DELETE | `/api/lecturer/courses/{course_id}/students/{student_id}` | Marks the enrollment removed; the student's past attempts stay for the record. |
| POST | `/api/student/courses/join` | Join Course |
| GET | `/api/student/courses` | Student Courses |
| GET | `/api/topics/search` | Course topics this user can pick in a quiz form (lecturer: own courses, student: enrolled). |

## Generation

| Method | Path | What it does |
|---|---|---|
| POST | `/api/lecturer/generate` | Generate Draft |
| POST | `/api/student/practice/generate` | Generate Practice |
| POST | `/api/lecturer/questions/{question_id}/regenerate` | Regenerate Question |
| GET | `/api/generation/{run_id}` | Get Run |
| POST | `/api/generation/{run_id}/cancel` | Cancel Run |
| GET | `/api/generation` | My Runs |
| GET | `/api/student/practice/recommended-difficulty` | Practice Difficulty |

## Question bank

| Method | Path | What it does |
|---|---|---|
| GET | `/api/lecturer/questions` | List Questions |
| POST | `/api/lecturer/questions` | Create Question |
| GET | `/api/lecturer/questions/{question_id}` | Get Question |
| PATCH | `/api/lecturer/questions/{question_id}` | Edit Question |
| DELETE | `/api/lecturer/questions/{question_id}` | Delete Question |
| POST | `/api/lecturer/questions/{question_id}/review` | Review Question |
| POST | `/api/lecturer/questions/{question_id}/duplicate` | Duplicate Question |
| GET | `/api/lecturer/questions/{question_id}/history` | Review History |

## Lecturer quizzes

| Method | Path | What it does |
|---|---|---|
| GET | `/api/lecturer/quizzes` | List Quizzes |
| POST | `/api/lecturer/quizzes` | A draft quiz built by hand from the question bank (no generation). |
| GET | `/api/lecturer/quizzes/{quiz_id}` | Get Quiz |
| PATCH | `/api/lecturer/quizzes/{quiz_id}` | Update Settings |
| DELETE | `/api/lecturer/quizzes/{quiz_id}` | Delete Draft |
| POST | `/api/lecturer/quizzes/{quiz_id}/items` | Update Items |
| POST | `/api/lecturer/quizzes/{quiz_id}/publish` | Publish |
| POST | `/api/lecturer/quizzes/{quiz_id}/unpublish` | Unpublish |
| POST | `/api/lecturer/quizzes/{quiz_id}/archive` | Archive |
| POST | `/api/lecturer/quizzes/{quiz_id}/release-feedback` | Release Feedback |
| GET | `/api/lecturer/quizzes/{quiz_id}/preview` | Exactly what a student receives when starting the quiz (no answer keys). |

## Student quizzes

| Method | Path | What it does |
|---|---|---|
| GET | `/api/student/quizzes/assigned` | Assigned |
| GET | `/api/student/quizzes/practice` | Practice Quizzes |
| GET | `/api/student/quizzes/{quiz_id}` | Quiz Card |
| POST | `/api/student/quizzes/{quiz_id}/start` | Start |
| GET | `/api/student/attempts/{session_id}` | Get Attempt |
| PUT | `/api/student/attempts/{session_id}/answers/{question_id}` | Save |
| POST | `/api/student/attempts/{session_id}/answers/{question_id}/check` | Check |
| POST | `/api/student/attempts/{session_id}/submit` | Submit |
| GET | `/api/student/attempts/{session_id}/result` | Get Result |
| GET | `/api/student/history` | History |

## Student analytics

| Method | Path | What it does |
|---|---|---|
| GET | `/api/student/overview` | Overview |
| GET | `/api/student/mastery` | Mastery Map |
| GET | `/api/student/mastery/history` | Mastery History |
| GET | `/api/student/weak-areas` | Weak Areas |
| GET | `/api/student/question-status` | Three separate lists: skipped in a quiz, answered incorrectly, never attempted (in assigned quizzes). |
| GET | `/api/student/trends` | Trends |
| GET | `/api/student/recommendations` | Recommendations |
| POST | `/api/student/recommendations/{reco_id}/{action}` | Update Recommendation |
| POST | `/api/student/recommendations/refresh` | Refresh Recommendations |
| GET | `/api/student/revision` | Revision |
| POST | `/api/student/revision/start` | Builds a practice quiz from up to 10 due revision questions (no AI generation needed). |
| GET | `/api/student/confidence` | Confidence |
| GET | `/api/student/study-plan` | A week's plan from mastery, due assessments and the student's available hours. Each item says why. |

## Lecturer analytics

| Method | Path | What it does |
|---|---|---|
| GET | `/api/lecturer/overview` | Overview |
| GET | `/api/lecturer/courses/{course_id}/analytics` | Course Analytics |
| GET | `/api/lecturer/courses/{course_id}/heatmap` | Course Heatmap |
| GET | `/api/lecturer/courses/{course_id}/heatmap/cell` | Heatmap Cell |
| GET | `/api/lecturer/quizzes/{quiz_id}/question-analytics` | Quiz Question Analytics |
| GET | `/api/lecturer/courses/{course_id}/question-analytics` | Course Question Analytics |
| GET | `/api/lecturer/courses/{course_id}/insights` | Course Insights |
| GET | `/api/lecturer/courses/{course_id}/coverage` | How many approved questions and published-quiz questions assess each learning objective. |
| GET | `/api/lecturer/students` | Students |
| GET | `/api/lecturer/students/{student_id}` | Student Profile |
| GET | `/api/lecturer/model-quality` | How the question-generation model has performed for this lecturer, per model version. |

## Reports

| Method | Path | What it does |
|---|---|---|
| GET | `/api/lecturer/reports/quizzes/{quiz_id}/results.csv` | Quiz Results |
| GET | `/api/lecturer/reports/quizzes/{quiz_id}/completion.csv` | Quiz Completion |
| GET | `/api/lecturer/reports/quizzes/{quiz_id}/questions.csv` | Quiz Questions |
| GET | `/api/lecturer/reports/courses/{course_id}/marks.csv` | Student-wise marks: one row per student, one column per published quiz (latest attempt, final %). |
| GET | `/api/lecturer/reports/courses/{course_id}/topics.csv` | Course Topics |

## Integrations

| Method | Path | What it does |
|---|---|---|
| GET | `/api/integrations/google/status` | Google Status |
| GET | `/api/integrations/google/connect` | Google Connect |
| GET | `/api/integrations/google/callback` | Google Callback |
| DELETE | `/api/integrations/google` | Google Disconnect |
| POST | `/api/lecturer/quizzes/{quiz_id}/google-form` | Export To Google |
| GET | `/api/lecturer/quizzes/{quiz_id}/google-form/exports` | List Exports |
| GET | `/api/lecturer/quizzes/{quiz_id}/export` | Plain text to paste into Google Forms (or any LMS) by hand. Includes the answer key. |
