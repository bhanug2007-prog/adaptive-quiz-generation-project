# Student assessment activity warnings

Implemented 2026-11-10. No deployment, migration, historical-record backfill, mark changes, credential changes, or model configuration changes were performed.

## Behavior

- New consented, monitored assessment attempts snapshot a warning policy. Practice attempts remain unmonitored. Existing historical monitoring sessions retain their original behavior and are not reclassified.
- MediaPipe face counts, Web Audio VAD, visibility/focus, and fullscreen transitions feed persistence timers. An ongoing incident generates one warning, with its incident ID persisted in sessionStorage across reloads. A one-second recovery is needed before another incident can begin.
- Brief sounds and steady background noise do not suffice for an audio warning: VAD activity also needs recent level variation. These are heuristics, not speech recognition or speaker identification. No Groq or other model API is called for monitoring.
- Existing raw telemetry remains available. New `activity_warning` events carry signal, incident ID, duration and timestamp. The backend checks the snapshotted signal settings, persistence and cooldown, strips client-supplied confirmation, and writes its own confirmation.
- Counts and review flags are derived from confirmed stored warnings. Uploads are serialized per monitoring session, with sequence-number, incident-ID and cooldown deduplication. Counts are returned on uploads with `?warnings=true` and restored by the existing student monitoring GET endpoint.
- The red accessible banner and counter persist at/after the threshold. The third warning adds a lecturer-review reason without invoking answer saving, submission, grading, failure or zero-mark logic. Existing time-limit and required-fullscreen behavior is retained.
- Lecturer summaries and timelines expose counts, warning history and timestamps under the existing owner checks. Existing independent review reasons are retained, so device issues/raw telemetry may also request review before three warnings.
- Students can append a false-alert/device-problem report through `/api/student/attempts/{id}/monitoring/reports`, optionally linked to an event. Reports use an idempotency key, are limited to 20 per attempt, cannot alter events, and follow existing access/retention boundaries.

## Configuration

Backend environment settings apply to newly started monitored attempts; existing snapshots do not change:

| Setting | Default |
| --- | ---: |
| `MONITORING_WARNING_THRESHOLD` | 3 |
| `MONITORING_WARNING_COOLDOWN_MS` | 15000 per signal |
| `MONITORING_WARNING_FACE_MULTIPLE_MS` | 3000 |
| `MONITORING_WARNING_FACE_NONE_MS` | 10000 |
| `MONITORING_WARNING_SPEECH_MS` | 5000 |
| `MONITORING_WARNING_PAGE_HIDDEN_MS` | 1000 |
| `MONITORING_WARNING_FULLSCREEN_EXIT_MS` | 1000 |

Configuration is validated in `Settings`. Default upload batching adds up to approximately four seconds to server confirmation; background browser throttling/network loss can add latency. Offline UI shows the last confirmed count and a pending-sync message after a failed upload.

## Files changed for this task

Backend:

- `backend/app/core/config.py` — validated warning settings.
- `backend/app/api/student_quizzes.py` — snapshot policy at consented start.
- `backend/app/api/monitoring.py` — serialized acceptance, authoritative responses, report endpoint, lecturer history.
- `backend/app/services/monitoring_service.py` — policy validation, count derivation and review reason.
- `backend/tests/test_monitoring_warnings.py` — five focused backend tests.

Frontend:

- `frontend/src/api/endpoints.js` — warning response opt-in and report call.
- `frontend/src/monitoring/warnings.js` — persistent incident timers and audio variation gate.
- `frontend/src/monitoring/useMonitoring.js` — detector integration, confirmed state, pending sync, device-stop cleanup.
- `frontend/src/monitoring/labels.js` — neutral warning/report descriptions.
- `frontend/src/components/student/Monitoring.jsx` — counter, accessible banner/history, report form and consent explanation.
- `frontend/src/components/lecturer/MonitoringReport.jsx` — warning history in the lecturer timeline.
- `frontend/src/styles/student.css` — accessible red warning styling.
- `frontend/src/monitoring/__tests__/warnings.test.js` — persistence, deduplication, refresh, cooldown, audio and missing-sample tests.
- `frontend/src/components/student/__tests__/warnings.test.jsx` — first/second/third warning, report retry and practice tests.
- `frontend/e2e/warnings.spec.js` — real-browser student/lecturer workflow using disposable accounts.
- `frontend/e2e/monitoring.spec.js` — existing interruption route matches the warning query parameter.
- `ACTIVITY_WARNINGS_VERIFICATION.md` — this report.

## Verification

Only focused tests were run. Backend tests used disposable SQLite databases under `.warning-test-tmp*`; Playwright used the existing isolated test server with a temporary SQLite database, fake model server and disposable accounts. The normal application database and `.env` were not used.

- Backend: 17 distinct tests passed across focused runs. Initial `tests/test_monitoring.py tests/test_monitoring_warnings.py` run passed 16; after adding concurrent-upload coverage, all 5 tests in `test_monitoring_warnings.py` passed again. Coverage includes authorization, consent/practice boundaries, retention, repeated/concurrent uploads, threshold snapshots, review flags, answer preservation, and unchanged result marks after late monitoring uploads.
- Frontend: 43 tests passed in 5 files using `npm.cmd test -- src/monitoring/__tests__ src/components/student/__tests__/monitoring.test.jsx src/components/student/__tests__/warnings.test.jsx`.
- Playwright: the scenario in `e2e/warnings.spec.js` passed in installed Chrome. It exercised real fullscreen exit and window blur, first/second/third UI, duplicate upload, reload, preserved answers, student reporting, and authorized lecturer history. The third audio event was injected deterministically through the authenticated API; audio heuristics were tested separately. The screenshot `frontend/test-results/activity-warning-third.png` was visually inspected.
- The initial default Playwright browser launch failed. Retrying with `PLAYWRIGHT_CHROMIUM=C:\Program Files\Google\Chrome\Application\chrome.exe` ran the scenario successfully. The Windows runner remained open during teardown after reporting the passed test; it was interrupted after confirming both test-server ports had closed. This was not a clean runner exit.
- Existing FastAPI/Starlette test-client deprecation warning remains.

## Remaining limits

- Physical camera/microphone accuracy, real rooms, multiple people, and PostgreSQL concurrency were not tested; detector simulations and SQLite concurrency were tested. Browser telemetry can be blocked/tampered with and cannot establish misconduct.
- Microphone activity cannot determine who spoke or distinguish every background sound. Students can report context without removing evidence.
- Warning banners appear after server confirmation. Network interruptions, browser timer throttling and the existing 2000-event cap can limit or delay telemetry.
- Incident continuity uses sessionStorage. Ordinary refresh and upload retries are covered; clearing browser storage, independent simultaneous player tabs, or malicious incident IDs are outside the guarantee.
- Warning policies apply to new monitored attempts. Historical/in-progress sessions without a policy snapshot are not retroactively converted.
- The full suite, deployment and production database migration were not run.
