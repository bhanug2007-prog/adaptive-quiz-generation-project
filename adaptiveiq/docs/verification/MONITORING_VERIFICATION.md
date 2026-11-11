# Step 5 — monitoring verification (9 November 2026)

Scope: existing assessment monitoring only, on Windows. Test data used temporary SQLite databases and the existing fake question model. No deployment, full application suite, real database migration, historical-record purge, mark/result edits, credential edits, or model configuration edits were performed.

## Confirmed implementation

- Consent is required by both the quiz introduction and start API (428 without agreement). Monitoring settings and consent time are saved per attempt; settings cannot change after attempts start. Practice is not monitored.
- Camera and microphone are requested from a student click. Permission refusal is visible and recorded, and does not prevent answering.
- MediaPipe runs locally with bundled model/WASM assets. Face episodes require two matching checks; a single face closes an absence/multiple-face episode. No identity verification is performed.
- Web Audio computes energy against an adaptive background. It reports speech-like sound, not words or proof of speech.
- Events are queued in sessionStorage and uploaded in batches. Sequence numbers and a database uniqueness constraint make repeated uploads idempotent. Unit tests cover batching, offline reload, retry, and continuing server sequence numbers.
- Lecturer reports show neutral counts, timelines, and manual review outcomes. Student endpoints check attempt ownership; lecturer endpoints check quiz ownership. Other students and lecturers are denied by focused API tests.
- Retention defaults to 180 days; zero disables deletion. Tests confirm deletion of old monitoring events/sessions using disposable records only. Actual cleanup is opportunistic on startup/report access, not a scheduled exact-time purge.
- The implemented capture/upload path sends event metadata only. No MediaRecorder or raw video/audio upload is used; extra media fields are discarded server-side.

## Focused fixes

1. Added window blur/focus handling to the existing page-leave events, deduplicating overlapping visibility changes. Closes an open away interval when monitoring finishes.
2. Stops devices if permission resolves after monitoring is cancelled/unmounted; releases microphone tracks if Web Audio setup fails. Prevents later startup stages from restarting capture after finish.
3. Failed server sequence synchronization no longer silently falls back to zero. The gate displays a reconnect/reload message instead of risking event-number collisions.
4. Fullscreen changes are deduplicated, including the initial request/event race.
5. Invalid list/object device details are discarded rather than causing a backend TypeError.
6. Added a native Python E2E server launcher compatible with Windows, with an explicitly temporary database and no project `.env` loading. Browser checks use the installed Chrome through `PLAYWRIGHT_CHROMIUM`.
7. A real browser run exposed a repeated-attempt-fetch race that cancelled the startup queue while the student clicked Start. Queue initialization now depends on the monitoring-enabled flag and attempt ID, not the identity of a refreshed settings object. Added a regression test.

## Validation

- Backend: `python -m pytest tests/test_monitoring.py -q` — **10 passed**, one pre-existing Starlette/httpx deprecation warning.
- Frontend: `npm test -- src/monitoring/__tests__ src/components/student/__tests__/monitoring.test.jsx` — **31 passed, 0 failed**. An intermittent resume failure and subsequent browser failure led to the repeated-fetch startup fix; the final focused run passed.
- Browser: `npx playwright test e2e/monitoring.spec.js` with `PLAYWRIGHT_CHROMIUM=C:\Program Files\Google\Chrome\Application\chrome.exe` — **3 passed, 0 failed** in 2.4 minutes. Fake devices only; no physical hardware claim. An earlier sandbox run failed on network access; the successful run was outside that restriction. A later startup failure was fixed as described above.

| Behavior | Evidence and limit |
|---|---|
| Consent gate | API, component and browser tests; start disabled until agreement |
| Camera/microphone permission | Browser fake-device grants; camera refusal component test; physical prompts still manual |
| Face absence | Real local MediaPipe detector on Chromium's fake test-pattern camera |
| Face present / multiple faces | Pure detector-state tests with simulated counts only; no real-person browser test |
| Audio activity | RMS and VAD unit tests with synthetic levels; browser verifies microphone startup/stop, not speech activity |
| Fullscreen | Real browser entry and exit, persisted exit event; unit deduplication and required-screen state |
| Page visibility / focus | Component visibility events and synthetic browser blur/focus; overlapping events counted once in unit tests; actual OS tab switching remains manual |
| Refresh / batching | Queue tests restore sessionStorage, keep pending events and sequence numbers; repeated-fetch regression; no full browser reload during a monitored attempt |
| Interrupted uploads | Browser intercepts uploads with 503, retains the batch, then reconnects and drains it; server tests confirm duplicate suppression |
| End of quiz | Browser checks all acquired fake media tracks are ended; unit tests check cancelled permission results and listener removal |
| Lecturer review | Browser displays timeline and neutral status and saves a no-concern note; backend checks cross-user authorization |

Browser evidence is generated under `frontend/test-results/monitoring-student.png` and `frontend/test-results/monitoring-lecturer.png`. Both screenshots contain disposable test accounts only.

## Remaining limitations and manual checklist

- Test a real single face, leaving/returning, two people, poor lighting, and camera disconnection. Multiple-face counts are unit-tested with simulated detector output, not real people.
- Test actual microphone speech, silence, background noise, whispers, permission refusal and disconnection. Energy thresholds cannot distinguish speech from other sound.
- Check real OS focus changes, real tab switches, Escape/fullscreen behavior and browser permission dialogs in the intended Windows/browser setup. Synthetic focus events verify wiring, not all OS behavior.
- Client events can be suppressed/forged. Monitoring is evidence for review, not tamper-proof enforcement or an automatic accusation.
- Queue persistence is per tab. Simultaneous tabs can choose colliding sequence numbers; clearing sessionStorage while offline can lose pending events. Long outages after submission can exceed the 120-second acceptance window. The result page does not continuously retry a final failed upload, and expired-upload 409 responses remain queued. These are not guarantees of lossless delivery.
- Device-state updates use a separate best-effort request; they are not retried like events. In-progress face/audio episodes are finalized when they end or monitoring stops, so lecturer timelines are not live continuous streams.
- Retention has no dedicated scheduler or student self-service delete/dispute interface, does not purge browser queue data, and does not address external database backups. The UI's retention wording is less precise than this trigger-based behavior (and the lecturer wording for zero days is misleading).
- Access is based on quiz ownership, rather than a general course-staff role. No broader security audit was run.

## Files changed in this verification

- `backend/app/api/monitoring.py`
- `backend/tests/test_monitoring.py`
- `backend/scripts/monitoring_test_server.py` (new)
- `frontend/src/monitoring/useMonitoring.js`
- `frontend/src/monitoring/__tests__/lifecycle.test.jsx` (new)
- `frontend/src/components/student/Monitoring.jsx`
- `frontend/playwright.config.js`
- `frontend/e2e/monitoring.spec.js`
- `MONITORING_VERIFICATION.md` (this report)

The repository already contained many modified/untracked files before this work; the list above identifies this task's edits only.
