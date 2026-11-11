# Question quality review (Phase 3)

Every question generated for a lecturer goes through two checks before the lecturer sees it:

1. **Python checks**, always (`backend/app/services/validation_service.py`): format, near-duplicates,
   answer give-away, explanation numbers, word overlap with the reference passage, and the sandboxed
   maths check.
2. **AI review**, when `GROK_API_KEY` is set (`backend/app/services/quality_service.py`). Grok judges:
   - whether the marked answer is correct;
   - whether the question tests the topic;
   - its real difficulty (easy, medium or hard);
   - the wrong options;
   - whether more than one option could be correct;
   - ambiguity;
   - whether the explanation supports the answer;
   - clarity.

   It replies in JSON. The reply is validated against a fixed schema before it is used.

The pass or fail decision is made in Python from those individual answers, in this order:

1. wrong answer;
2. more than one correct option;
3. ambiguous;
4. off topic;
5. explanation does not support the answer;
6. weak options;
7. unclear;
8. difficulty differs from the one requested;
9. score below `QUALITY_MIN_SCORE`.

The reviewer's own "passed" field is recorded, but it never passes a question on its own. The AI review is an extra screen, not the truth. The lecturer still reviews and approves every question before a quiz can be published.

## Retries and failed questions

- A question that fails either check is regenerated, up to `MAX_ATTEMPTS_PER_QUESTION` (3). Only that one question is regenerated, from a different context.
- In a lecturer draft, a question that never passes is **kept** with its best attempt. It is marked **Failed checks** with the reason. It is not approved automatically, and approving it asks for confirmation.
- The lecturer can edit it, regenerate it or reject it. They can also press **Check again**, which reruns the checks on the current version. "Failed checks" is cleared only when the check that failed now passes. An AI-review failure is cleared only by an AI review.
- Student practice and single-question regeneration keep only questions that pass.

## Difficulty mix

When a run finishes, it compares the requested mix (for example 3 easy, 4 medium, 3 hard) with the levels the AI reviewer judged. It reports whether they match and which questions differ. This appears under the generation progress and in `quality` on `GET /api/generation/{run_id}`. Without the AI review, the difficulty labels are the requested ones and the report says so.

## Fallback when Grok is not available

The app works the same without Grok. Each question then shows "AI review not done" with the reason.

| Situation | What happens |
|---|---|
| No `GROK_API_KEY` | Python checks only |
| Timeout, connection error, HTTP 5xx | One retry after 2 s, then Python checks only for that question |
| Rate limit (429), no quota or credit, refused key, unknown model | Python checks only, and Grok calls pause for `GROK_COOLDOWN_S` (default 300 s) so a broken account is not called for every question |
| Reply that is not valid JSON or does not match the schema | Python checks only for that question |

`GET /api/health` shows the reviewer's state under `quality_review`. The state is `ready`, `paused`, `not_configured` or `off`.

## Privacy and cost

- The key stays on the backend. It is never returned by any API response (tested).
- Only these are sent to Grok:
  - the question and its four options;
  - the marked answer and the explanation;
  - the subject, the topic and the requested difficulty;
  - the source passage, up to 2000 characters.

  No student data is ever sent (tested).
- Student practice questions are not sent by default (`QUALITY_CHECK_PRACTICE=false`), to avoid one API call per practice question.

## Records

Every checked attempt is stored in the `question_evaluations` table (migration `0003`). This includes rejected attempts, which have no question row, so a run's decisions can be audited. `GET /api/lecturer/questions/{id}/evaluations` returns a question's log.

## Settings (`backend/.env`)

```
QUALITY_CHECK=true
QUALITY_CHECK_PRACTICE=false
QUALITY_CHECK_DIFFICULTY=true
QUALITY_MIN_SCORE=60
GROK_API_KEY=
GROK_BASE_URL=https://api.x.ai/v1
GROK_MODEL=grok-4.3
GROK_TIMEOUT_S=45
GROK_COOLDOWN_S=300
```

Set `GROK_MODEL` to a model name that your xAI account lists. `grok-4.3` is xAI's current text model (November 2026);
older names such as `grok-3` were retired on 15 May 2026, and `grok-latest` is not a valid name.

## What is tested, and what is not

- **Tested:** 19 backend tests (`backend/tests/test_quality.py`) and 8 frontend tests (`frontend/src/components/lecturer/__tests__/quality.test.jsx`). The backend tests run on SQLite and on PostgreSQL 16. They use a test-only fake Grok server (`backend/tests/fake_grok_server.py`) and the fake model.
- **Not verified yet:** the real xAI API. Nobody has run it with a real key. How good Grok's judgements are on real Qwen questions has not been measured. Its difficulty judgement in particular should be compared with lecturer labels before it is trusted.
