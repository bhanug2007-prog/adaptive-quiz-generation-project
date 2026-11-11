# Assessment integrity monitoring

Optional, per assessment, switched on by the lecturer in **Quiz → Settings → Integrity monitoring**.
It records events for the lecturer to review. It does not prove or prevent cheating, and it never labels a
student as cheating. Practice quizzes are never monitored.

## What can be switched on

| Setting | What the browser does | Event(s) stored |
|---|---|---|
| Record when students leave the quiz page | Page Visibility API: the quiz tab is hidden (another tab, another window, minimised) and shown again | `page_hidden`, `page_visible` with how long it was hidden |
| Full screen: record, or required | Fullscreen API. "Required" hides the questions until the student returns (timer keeps running, answers stay saved) | `fullscreen_enter`, `fullscreen_exit` |
| Camera | MediaPipe Face Detector (BlazeFace short range) runs **in the browser** every 1.5 s (`MONITORING_FACE_INTERVAL_MS`) and counts faces. An episode starts only after 2 checks in a row agree | `face_none`, `face_multiple` with duration and the most faces seen; `camera_denied`, `camera_lost` |
| Microphone | Energy-based voice activity detection **in the browser** (Web Audio level against an adaptive background level; at least 1 s to be reported) | `speech` with duration; `microphone_denied`, `microphone_lost` |

No image, video or audio is stored or sent. Only the event, its time (browser clock), its length and, for
faces, a count. The model files are served from this site (`frontend/public/mediapipe/`), not from a CDN.

## Student side

1. The quiz page lists exactly what is recorded and why, says how long it is kept, and says to contact the
   lecturer for another way to take the assessment. **Start** stays disabled until the student ticks
   "I have read what is recorded and agree". The API refuses to start a monitored attempt without it (428).
2. In the quiz, a short screen asks them to turn monitoring on (the browser then asks for camera and
   microphone permission). Saying no does not block the quiz; the lecturer sees that permission was not given.
3. While answering, the header shows "Monitored", "Camera on", "Microphone on". After leaving the page or
   full screen, a message says it was recorded. If the camera cannot see a face, a hint says so.
4. After submitting, the result page lists everything that was recorded about the attempt.

Events wait in the browser (sessionStorage) while offline and are sent again; the server ignores a sequence
number it already has, so retries never duplicate. Events are accepted until 2 minutes after submission and
only within the attempt's time (5 minutes clock slack). At most 2000 events per attempt.

## Lecturer side

**Quiz → Monitoring** lists each monitored attempt with a neutral status and the counts behind it, sorted
with the ones to review first. **Timeline** shows every event. The lecturer can record their own outcome,
"No concern" or "Follow up with student", with a private note.

| Status | Meaning |
|---|---|
| Normal | Nothing but start-up events (monitoring on, entered full screen) |
| Event recorded | Some events, all below the thresholds |
| Needs review | At least one threshold reached (the reasons are listed) |

Thresholds (`backend/app/services/monitoring_service.py`, `monitor-rules-v1`):

- quiz page hidden 3 or more times, or 60 seconds or more in total
- full screen required and left 2 or more times
- no face for 30 seconds or more in total
- more than one face at least once (2 checks in a row)
- speech-like sound for 10 seconds or more at once, or 60 seconds in total
- a required camera or microphone not allowed or not found

## Storage, access and retention

- Tables `monitoring_sessions` (one per monitored attempt: settings copied at consent, permission results,
  the lecturer's review) and `monitoring_events` (migration `0005_monitoring`, which also adds the four
  `monitor_*` columns to `quizzes`, all off for existing quizzes).
- Only the lecturer who owns the quiz can see its monitoring (other lecturers get 404, students 403).
  A student can see only their own attempt's events.
- Settings cannot change once students have started the quiz, like the other attempt settings.
- Data older than `MONITORING_RETENTION_DAYS` (default 180; 0 keeps it) is deleted when the server starts and
  when a lecturer opens a monitoring report.

## What was tested

- Backend `tests/test_monitoring.py` (10): off by default; consent required (428) and not asked again on resume;
  settings locked after attempts; events stored once, retries counted as duplicates, unknown kinds and times
  outside the attempt rejected, extra detail fields dropped; uploads close 2 minutes after submission;
  neutral statuses and reasons for three students (no "cheat" or "suspicious" anywhere); a denied required
  camera needs review; owner-only access; retention purge; practice never monitored.
- Frontend `monitoring/__tests__/monitoring.test.js` (16): voice activity detection (speech, short noises,
  pauses between words, a steady fan fading out, a long conversation, the absolute floor), face episodes,
  the event queue offline and after a reload.
- Frontend `components/student/__tests__/monitoring.test.jsx` (9): consent on the quiz page, the gate,
  page-leave events and message, sequence numbers after a reload, a denied camera, events sent at submit,
  the lecturer report and review, the settings form.
- Browser `e2e/monitoring.spec.js` in real Chromium with its fake camera and microphone: the lecturer turns
  monitoring on, the student agrees, the real MediaPipe detector runs and reports "no face" (the fake camera
  shows a test pattern), the result page shows the record, and the lecturer sees "Event recorded" and the timeline.

## Limits (be honest about these)

- A browser cannot see other devices, other apps, a second screen, notes on the desk or someone out of shot.
  It cannot tell which site or app was opened. Leaving the page can be a notification or an accident.
- Face detection only counts faces. It does not check identity. Poor light, a turned head or a cap can give
  "no face". A photo or a face on a poster can count as a face.
- "More than one face" was tested with simulated detector output only; no real images of people were used.
- Speech detection measures loudness, not words: music, a cough, traffic or a sudden steady noise can count
  (a steady noise fades out in about 7 seconds). A student who whispers may not be detected.
- Mobile browsers (iPhone Safari) do not support the Fullscreen API on pages; "required" then does not hide
  the questions there.
- The time limit starts when the attempt starts, so the monitoring screen and permission prompts use a few
  seconds of it. The quiz page explains monitoring before the student starts.
- The student can see their record but there is no in-app way to dispute it; that goes through the lecturer.
- Speech-to-text (for example a local Whisper model) is not implemented.
