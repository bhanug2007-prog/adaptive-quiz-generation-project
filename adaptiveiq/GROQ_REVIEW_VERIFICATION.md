# Real Groq question review verification — 9–10 November 2026

## Root cause and fix

The local backend had been launched inside a network-restricted sandbox. Local Qwen requests worked, but outbound HTTPS to Groq failed with Windows socket error 10013. Existing logs repeatedly reported `Cannot reach the AI reviewer (Groq API)`. A direct request in that environment reproduced `ConnectError: [WinError 10013]`; the same configured credentials and model succeeded outside it.

The normal backend on port 8000 was restarted outside the restriction, retaining the existing configuration. Automatic monitoring deletion remains disabled for this process to preserve historical records. No active generation runs existed when it was restarted. No migration or historical question recheck was run.

The client now identifies socket error 10013 as an actionable configuration/network-permission failure, explains that the backend needs network access, and uses the existing cooldown mechanism. It does not repeatedly retry this permanent network block or falsely mark the question AI-reviewed.

No change was needed to Groq credentials, base URL, model, prompts, parsing, worker, or frontend review logic. The internal legacy `evaluator="grok"` value remains for compatibility; the actual provider is **Groq**, not xAI.

## Live API evidence

Configuration was read without displaying keys:

- Base URL: `https://api.groq.com/openai/v1`
- Model: `qwen/qwen3.8-27b`
- `QUALITY_CHECK=true`; timeout 45 seconds
- Key present; never printed, logged, overwritten or committed

| Operation | Actual result |
|---|---|
| Available models with existing key | HTTP 200, 507 ms; configured model present |
| Minimal `Reply OK` request | HTTP 200, 138 ms; `OK.`, finish reason `stop` |
| Generation-worker quality evaluation | HTTP 200; parsed successfully, persisted score 95, correctness `correct`, difficulty `easy` |
| Browser Check again → backend → Groq | Backend and Groq HTTP 200; browser request-to-result 1,378 ms; same score/verdict/difficulty |

Total live calls: one model-list GET and three chat requests (minimal probe, generated-question review, manual recheck). Blocked sandbox attempts did not reach Groq. No repeated quota/credential probing or model substitution was performed.

## Complete trace with disposable data

An opt-in server created a fresh temporary SQLite database and used the existing real local Qwen model and Groq settings. Generation retries were limited to one in this disposable server to bound live calls; deterministic and mathematical validation remained enabled. The normal application configuration was not edited.

1. A disposable lecturer/course/topic requested one easy MCQ using a short process-states reference passage.
2. The real local fine-tuned Qwen generated: “Which state is a process in while it is waiting to be assigned a CPU?” Answer: Ready.
3. The generation worker's standard validation and quality evaluator ran. The run finished `done`, `ai_review=used`, `mix_matches=true`, with one stored question and no failed-kept questions.
4. Stored review: score 95/100, correctness `correct`, assessed difficulty `easy`, explanation supports answer, no ambiguity/multiple correct options, `reason=null`, `ai_error=null`. Feedback: “The question is a solid, unambiguous recall item suitable for an easy difficulty level. It accurately reflects the source material.”
5. Chrome displayed **AI review passed (95)**, the model identifier and detailed review. The question still said **Needs review** and remained a draft requiring lecturer approval.
6. Clicking **Check again** sent POST `/api/lecturer/questions/{id}/check-quality`. The page displayed the returned result, a subsequent GET matched the stored review exactly, and the result remained after a browser reload.
7. The evaluation endpoint returned two audit records: generation review and manual recheck. Existing records were retained. No approval or publishing was performed.

The frontend already refreshes the question through `onChanged` after Check again; asynchronous generation finishes before its stored review is shown. No frontend code fix was needed. This live check polled generation through the API and verified the resulting review and manual refresh in the real browser; it did not repeat the entire create-quiz wizard.

## Focused tests

- `python -m pytest tests/test_quality.py -q`: **27 passed**, one Starlette/httpx deprecation warning.
- `npm test -- src/components/lecturer/__tests__/quality.test.jsx`: **9 passed**.
- `node scripts/live-quality-check.mjs`: **passed** with real local Qwen, real Groq, real Chrome, temporary database.
- Existing tests cover denied credentials, model errors, quota/rate limits, bounded transient retries/timeouts, malformed JSON/schema, reasoning blocks, deterministic/math non-override, audit persistence and UI results. New regression verifies socket 10013 pauses after one call and stays `not_checked` without exposing keys.

## Files modified/added

- `backend/app/services/quality_service.py`: actionable Windows network-denial handling.
- `backend/tests/test_quality.py`: focused regression test.
- `backend/scripts/live_quality_server.py`: opt-in disposable server; no live requests until explicitly driven.
- `frontend/scripts/live-quality-check.mjs`: opt-in real-provider/browser verification; never run against normal data.
- `GROQ_REVIEW_VERIFICATION.md`: this report.

Generated local evidence (disposable accounts/questions only):

- `frontend/test-results/live-quality-generated.json`
- `frontend/test-results/live-quality-verified.json`
- `frontend/test-results/live-quality-generated.png`
- `frontend/test-results/live-quality-rechecked.png`

## Remaining limits

No blocker remains for the verified Groq integration. Launching the backend inside a network-denied environment will still prevent API access; use a normal local terminal or an approved network-enabled process. A health status of `ready` means configured and not paused, not a live credential/connectivity test.

Historical questions marked “AI review not done” were intentionally untouched. Lecturers can explicitly use Check again for those records. Normal approval/audit behavior was preserved; successful AI review is not automatic lecturer approval. This small conceptual MCQ is not evidence of reviewer accuracy across all subjects or numerical questions, and no numerical safety rules were relaxed. No full test suite or deployment was performed.
