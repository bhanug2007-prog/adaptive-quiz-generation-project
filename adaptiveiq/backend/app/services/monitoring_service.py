"""Assessment integrity monitoring: settings, event checks and the neutral review summary.

The browser detects events (page hidden, fullscreen exit, no face or several faces in the camera image,
speech-like sound) and sends only those events. No video, image or audio ever reaches the server.
The summary below never says "cheating": it says Normal, Event recorded or Needs review, with the reasons,
and the lecturer decides. See docs/MONITORING.md for the rules and their limits."""
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import MonitoringEvent, MonitoringSession, Quiz, QuizSession
from app.models.base import utcnow

ALGORITHM = "monitor-rules-v1"
KINDS = {
    "activity_warning",
    "monitoring_started",            # details: camera / microphone permission result
    "page_hidden", "page_visible",   # page_visible.duration_ms = how long the quiz page was hidden
    "fullscreen_enter", "fullscreen_exit",
    "face_none", "face_multiple",    # duration_ms = how long it lasted; details.faces = most faces seen
    "camera_denied", "camera_lost",
    "speech",                        # duration_ms = length of the speech-like sound
    "microphone_denied", "microphone_lost",
}
SIGNAL_KINDS = {
    "page_hidden", "fullscreen_exit", "face_none", "face_multiple", "speech",
    "camera_lost", "microphone_lost", "camera_denied", "microphone_denied",
}
DEVICE_STATES = {"granted", "denied", "unavailable", "not_requested"}

# Thresholds for "Needs review" (any one is enough). Below them, recorded events give "Event recorded".
REVIEW_HIDDEN_COUNT = 3              # times the quiz page was hidden
REVIEW_HIDDEN_S = 60                 # total seconds hidden
REVIEW_FULLSCREEN_EXITS = 2          # only when fullscreen is required
REVIEW_NO_FACE_S = 30                # total seconds with no face
REVIEW_MULTIPLE_FACES = 1            # periods with more than one face
SPEECH_PROLONGED_S = 10              # one stretch of speech-like sound this long is "prolonged"
REVIEW_SPEECH_S = 60                 # total seconds of speech-like sound

MAX_EVENTS_PER_ATTEMPT = 2000        # a broken or looping browser cannot fill the database
LATE_UPLOAD_S = 120                  # events may still arrive this long after submission (network delay)
CLOCK_SLACK = timedelta(minutes=5)   # browser clock tolerance

WARNING_SIGNALS = {"face_multiple": "camera", "face_none": "camera", "speech": "microphone",
                   "page_hidden": "tab", "fullscreen_exit": "fullscreen"}


def warning_policy(s) -> dict:
    return {"threshold": s.monitoring_warning_threshold, "cooldown_ms": s.monitoring_warning_cooldown_ms,
            "persistence_ms": {k: getattr(s, f"monitoring_warning_{k}_ms") for k in WARNING_SIGNALS}}


def warning_state(m, events) -> dict:
    # Only server-confirmed new warnings count. Historical telemetry is never reclassified.
    history = [{"seq": e.seq, "kind": (e.details or {}).get("signal"), "at": e.client_at,
                "incident_id": e.details.get("incident_id")}
               for e in events if e.kind == "activity_warning" and (e.details or {}).get("confirmed")]
    policy = (m.settings or {}).get("warning_policy")
    threshold = policy["threshold"] if policy else 3
    return {"warning_count": len(history), "warning_threshold": threshold,
            "review_required": len(history) >= threshold, "warning_history": history}


def confirm_warning(m, e, details, events) -> bool:
    policy = (m.settings or {}).get("warning_policy")
    signal = details.get("signal")
    setting = WARNING_SIGNALS.get(signal)
    if not policy or not setting or not details.get("incident_id"):
        return False
    enabled = m.settings.get(setting)
    if not enabled or enabled == "off" or (e.duration_ms or 0) < policy["persistence_ms"][signal]:
        return False
    for old in events:
        d = old.details or {}
        if old.kind != "activity_warning" or d.get("signal") != signal:
            continue
        if d.get("incident_id") == details["incident_id"]:
            return False
        if d.get("confirmed") and abs((e.at - old.client_at).total_seconds() * 1000) < policy["cooldown_ms"]:
            return False
    return True


def quiz_settings(z: Quiz) -> dict | None:
    """What this quiz monitors, or None when nothing is monitored (practice quizzes never are)."""
    if z.kind != "assessment":
        return None
    out = {"tab": bool(z.monitor_tab), "fullscreen": z.monitor_fullscreen or "off",
           "camera": bool(z.monitor_camera), "microphone": bool(z.monitor_microphone)}
    if not (out["tab"] or out["camera"] or out["microphone"] or out["fullscreen"] != "off"):
        return None
    return out


def for_attempt(db: Session, sess: QuizSession) -> MonitoringSession | None:
    return db.scalar(select(MonitoringSession).where(MonitoringSession.session_id == sess.id))


def open_session(db: Session, sess: QuizSession, settings: dict) -> MonitoringSession:
    """Called when a student who agreed starts a monitored attempt. Settings are copied, so a later change
    to the quiz does not change what this attempt was told."""
    m = for_attempt(db, sess)
    if m is None:
        m = MonitoringSession(session_id=sess.id, quiz_id=sess.quiz_id, student_id=sess.student_id,
                              settings=settings, consented_at=utcnow(), camera="not_requested",
                              microphone="not_requested", event_count=0, dropped_events=0)
        db.add(m)
    return m


def accept_time(sess: QuizSession, at: datetime, now: datetime) -> bool:
    """An event must fall inside the attempt (with clock slack)."""
    end = (sess.submitted_at or now) + CLOCK_SLACK
    return sess.started_at - CLOCK_SLACK <= at <= min(end, now + CLOCK_SLACK)


def can_upload(sess: QuizSession, now: datetime) -> bool:
    if sess.status == "in_progress":
        return True
    return sess.submitted_at is not None and now - sess.submitted_at <= timedelta(seconds=LATE_UPLOAD_S)


def zero_counts() -> dict:
    return {"tab_switches": 0, "hidden_s": 0.0, "fullscreen_exits": 0, "no_face": 0, "no_face_s": 0.0,
            "multiple_faces": 0, "multiple_faces_s": 0.0, "speech": 0, "speech_s": 0.0, "speech_prolonged": 0,
            "camera_issues": 0, "microphone_issues": 0}


def event_source(kind: str, details: dict | None = None) -> str:
    d = details or {}
    if kind == "activity_warning":
        return event_source(d.get("signal", "unknown"))
    if kind == "student_report":
        return "Student report"
    if kind in ("page_hidden", "page_visible"):
        return "Window focus monitor" if d.get("reason") == "window_blur" else "Tab visibility monitor"
    if kind in ("fullscreen_enter", "fullscreen_exit"):
        return "Fullscreen monitor"
    if kind in ("face_none", "face_multiple", "camera_denied", "camera_lost"):
        return "Camera face detector"
    if kind in ("speech", "microphone_denied", "microphone_lost"):
        return "Microphone audio monitor"
    if kind == "monitoring_started":
        return "Monitoring setup"
    return "Browser monitor"


def event_device_state(kind: str, details: dict | None = None, m: MonitoringSession | None = None) -> dict | None:
    d = details or {}
    if kind == "monitoring_started":
        out = {k: d[k] for k in ("camera", "microphone") if d.get(k) in DEVICE_STATES}
        return out or None
    if kind in ("face_none", "face_multiple"):
        return {"camera": "granted"}
    if kind == "camera_denied":
        r = d.get("reason")
        return {"camera": r if r in DEVICE_STATES else "denied"}
    if kind == "camera_lost":
        return {"camera": "unavailable"}
    if kind == "speech":
        return {"microphone": "granted"}
    if kind == "microphone_denied":
        r = d.get("reason")
        return {"microphone": r if r in DEVICE_STATES else "denied"}
    if kind == "microphone_lost":
        return {"microphone": "unavailable"}
    return None


def signal_availability(st: dict | None, camera: str, microphone: str, events: list[MonitoringEvent],
                        last_event_at: datetime | None, has_monitoring_session: bool = True) -> dict:
    """Indicates whether each monitoring signal was active, unavailable, or not monitored."""
    if not has_monitoring_session:
        return {"tab": "not_monitored", "fullscreen": "not_monitored", "camera": "not_monitored",
                "microphone": "not_monitored"}
    st = st or {}
    telemetry_never_arrived = (len(events) == 0 and last_event_at is None
                               and camera == "not_requested" and microphone == "not_requested")
    tab = "not_monitored" if not st.get("tab") else ("unavailable" if telemetry_never_arrived else "active")
    fullscreen = ("not_monitored" if (st.get("fullscreen") or "off") == "off"
                  else ("unavailable" if telemetry_never_arrived else "active"))
    detector_failed = any(e.kind == "camera_lost" and (e.details or {}).get("reason") == "face detector could not load"
                          for e in events)
    if not st.get("camera") and camera == "not_requested":
        cam = "not_monitored"
    elif camera in ("denied", "unavailable", "not_requested") or detector_failed:
        cam = "unavailable"
    else:
        cam = "active"
    if not st.get("microphone") and microphone == "not_requested":
        mic = "not_monitored"
    elif microphone in ("denied", "unavailable", "not_requested"):
        mic = "unavailable"
    else:
        mic = "active"
    return {"tab": tab, "fullscreen": fullscreen, "camera": cam, "microphone": mic}


def summarize(m: MonitoringSession, events: list[MonitoringEvent]) -> dict:
    """Counts per signal and the neutral status with its reasons."""
    st = m.settings or {}
    c = zero_counts()
    for e in events:
        sec = (e.duration_ms or 0) / 1000
        if e.kind == "page_hidden":
            c["tab_switches"] += 1
        elif e.kind == "page_visible":
            c["hidden_s"] += sec
        elif e.kind == "fullscreen_exit":
            c["fullscreen_exits"] += 1
        elif e.kind == "face_none":
            c["no_face"] += 1
            c["no_face_s"] += sec
        elif e.kind == "face_multiple":
            c["multiple_faces"] += 1
            c["multiple_faces_s"] += sec
        elif e.kind == "speech":
            c["speech"] += 1
            c["speech_s"] += sec
            c["speech_prolonged"] += sec >= SPEECH_PROLONGED_S
        elif e.kind in ("camera_denied", "camera_lost"):
            c["camera_issues"] += 1
        elif e.kind in ("microphone_denied", "microphone_lost"):
            c["microphone_issues"] += 1
    for k in ("hidden_s", "no_face_s", "multiple_faces_s", "speech_s"):
        c[k] = round(c[k], 1)

    avail = signal_availability(st, m.camera, m.microphone, events, m.last_event_at, has_monitoring_session=True)
    enabled = [k for k, v in avail.items() if v != "not_monitored"]
    if not enabled:
        monitoring_state = "not_monitored"
    elif all(avail[k] == "unavailable" for k in enabled):
        monitoring_state = "unavailable"
    elif any(avail[k] == "unavailable" for k in enabled):
        monitoring_state = "partial"
    else:
        monitoring_state = "active"

    reasons = []
    warnings = warning_state(m, events)
    if warnings["review_required"]:
        reasons.append(f"{warnings['warning_count']} activity warnings recorded; lecturer review required.")
    if c["tab_switches"] >= REVIEW_HIDDEN_COUNT:
        reasons.append(f"The quiz page was hidden {c['tab_switches']} times.")
    if c["hidden_s"] >= REVIEW_HIDDEN_S:
        reasons.append(f"The quiz page was hidden for {round(c['hidden_s'])} seconds in total.")
    if st.get("fullscreen") == "required" and c["fullscreen_exits"] >= REVIEW_FULLSCREEN_EXITS:
        reasons.append(f"Fullscreen was required and was left {c['fullscreen_exits']} times.")
    if c["no_face_s"] >= REVIEW_NO_FACE_S:
        reasons.append(f"No face was detected for {round(c['no_face_s'])} seconds in total.")
    if c["multiple_faces"] >= REVIEW_MULTIPLE_FACES:
        reasons.append(f"More than one face was detected {c['multiple_faces']} "
                       f"{'time' if c['multiple_faces'] == 1 else 'times'}.")
    if c["speech_prolonged"]:
        reasons.append(f"Speech-like sound lasted {SPEECH_PROLONGED_S} seconds or more "
                       f"{c['speech_prolonged']} {'time' if c['speech_prolonged'] == 1 else 'times'}.")
    elif c["speech_s"] >= REVIEW_SPEECH_S:
        reasons.append(f"Speech-like sound was detected for {round(c['speech_s'])} seconds in total.")
    if st.get("camera") and m.camera in ("denied", "unavailable"):
        reasons.append("The camera was required but permission was not given or no camera was found.")
    if st.get("microphone") and m.microphone in ("denied", "unavailable"):
        reasons.append("The microphone was required but permission was not given or no microphone was found.")

    has_signal = any(e.kind in SIGNAL_KINDS for e in events) or bool(warnings["warning_count"])
    telemetry_missing = (not events and m.last_event_at is None
                         and m.camera == "not_requested" and m.microphone == "not_requested")
    if reasons:
        status = "needs_review"
    elif has_signal:
        status = "event_recorded"
        reasons.append("Some events were recorded, all below the review thresholds.")
    elif monitoring_state == "not_monitored":
        status = "not_monitored"
    elif telemetry_missing:
        status = "unavailable"
        reasons.append("No monitoring telemetry was received for this attempt; monitoring data is unavailable.")
    elif monitoring_state in ("unavailable", "partial"):
        status = "unavailable"
        reasons.append("Device permission or telemetry for at least one monitored signal is unavailable.")
    else:
        status = "normal"
    if m.dropped_events:
        reasons.append(f"{m.dropped_events} events were not stored (outside the attempt's time or over the limit).")
    return {"status": status, "reasons": reasons, "counts": c, "algorithm": ALGORITHM,
            "signal_availability": avail, "monitoring_state": monitoring_state,
            "has_recorded_events": has_signal}


def quiz_monitoring_summary(db: Session, z: Quiz) -> dict:
    """Compact summary shown on lecturer quiz list and quiz details views."""
    st = quiz_settings(z)
    ms = list(db.scalars(select(MonitoringSession).where(MonitoringSession.quiz_id == z.id)))
    attempt_count = db.scalar(select(func.count()).select_from(QuizSession).where(QuizSession.quiz_id == z.id)) or 0
    with_events = 0
    awaiting_review = 0
    needs_review = 0
    unavailable_count = max(0, attempt_count - len(ms)) if st is not None else 0
    for m in ms:
        ev = list(db.scalars(select(MonitoringEvent).where(MonitoringEvent.monitoring_session_id == m.id)))
        s = summarize(m, ev)
        if s["has_recorded_events"]:
            with_events += 1
        if s["status"] == "needs_review":
            needs_review += 1
        if s["monitoring_state"] in ("unavailable", "partial"):
            unavailable_count += 1
        if m.review is None and s["status"] in ("needs_review", "event_recorded", "unavailable"):
            awaiting_review += 1
    return {
        "enabled": st is not None,
        "attempt_count": attempt_count,
        "monitored_count": len(ms),
        "with_events": with_events,
        "needs_review": needs_review,
        "unavailable_count": unavailable_count,
        "awaiting_review": awaiting_review,
    }


def rules() -> dict:
    return {"algorithm": ALGORITHM, "needs_review_when": [
        f"the quiz page is hidden {REVIEW_HIDDEN_COUNT} or more times, or for {REVIEW_HIDDEN_S} seconds or more in total",
        f"fullscreen is required and is left {REVIEW_FULLSCREEN_EXITS} or more times",
        f"no face is detected for {REVIEW_NO_FACE_S} seconds or more in total",
        "more than one face is detected at least once (seen in two checks in a row)",
        f"speech-like sound lasts {SPEECH_PROLONGED_S} seconds or more at once, or {REVIEW_SPEECH_S} seconds in total",
        "a required camera or microphone was not allowed or not found"],
        "note": "These are signals for you to review, not proof of anything. A hidden page can be a notification; "
                "no face can be poor lighting; speech-like sound can be noise; a detected face is not checked "
                "against the student's identity."}


def purge_old(db: Session, retention_days: int) -> int:
    """Deletes monitoring data older than the retention period. Returns how many sessions were removed."""
    if retention_days <= 0:
        return 0
    cut = utcnow() - timedelta(days=retention_days)
    ids = list(db.scalars(select(MonitoringSession.id).where(MonitoringSession.created_at < cut)))
    if ids:
        db.execute(delete(MonitoringEvent).where(MonitoringEvent.monitoring_session_id.in_(ids)))
        db.execute(delete(MonitoringSession).where(MonitoringSession.id.in_(ids)))
        db.commit()
    return len(ids)
