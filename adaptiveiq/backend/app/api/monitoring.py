"""Assessment integrity monitoring endpoints.

Students: report camera and microphone permission, upload events, and see what was recorded about them.
Lecturers: see the per-student summary and timeline of their own quizzes and record their review."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import get_db, get_settings_dep, require_lecturer, require_student
from app.models import MonitoringEvent, MonitoringSession, Quiz, QuizSession, User
from app.models.base import utcnow
from app.services import monitoring_service as mon
from app.services import permissions as perm

router = APIRouter(tags=["monitoring"])
Device = Literal["granted", "denied", "unavailable", "not_requested"]


class DevicesIn(BaseModel):
    camera: Device = "not_requested"
    microphone: Device = "not_requested"


class EventIn(BaseModel):
    seq: int = Field(ge=0, le=1_000_000)
    kind: str = Field(max_length=30)
    at: datetime
    duration_ms: int | None = Field(default=None, ge=0, le=24 * 3600 * 1000)
    details: dict = Field(default_factory=dict)

    @field_validator("kind")
    @classmethod
    def _kind(cls, v):
        if v not in mon.KINDS:
            raise ValueError("Unknown event kind.")
        return v

    @field_validator("at")
    @classmethod
    def _aware(cls, v):
        if v.tzinfo is None:
            raise ValueError("Event time must include a time zone.")
        return v


class EventsIn(BaseModel):
    events: list[EventIn] = Field(min_length=1, max_length=200)


class ReviewIn(BaseModel):
    review: Literal["no_concern", "follow_up"] | None = None
    note: str | None = Field(default=None, max_length=1000)


class ReportIn(BaseModel):
    report_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    category: Literal["false_alert", "device_problem"]
    event_seq: int | None = Field(default=None, ge=0)
    note: str = Field(default="", max_length=1000)


def _details(d: dict) -> dict:
    """Keeps only the small fields the browser is expected to send."""
    out = {}
    if isinstance(d.get("faces"), int) and 0 <= d["faces"] <= 20:
        out["faces"] = d["faces"]
    for k in ("camera", "microphone"):
        if isinstance(d.get(k), str) and d[k] in mon.DEVICE_STATES:
            out[k] = d[k]
    if isinstance(d.get("reason"), str):
        out["reason"] = d["reason"][:80]
    if isinstance(d.get("signal"), str) and d["signal"] in mon.WARNING_SIGNALS:
        out["signal"] = d["signal"]
    if isinstance(d.get("incident_id"), str) and 1 <= len(d["incident_id"]) <= 80:
        out["incident_id"] = d["incident_id"]
    return out


def _monitored_attempt(db: Session, user: User, session_id: int) -> tuple[QuizSession, MonitoringSession]:
    sess = perm.student_session(db, user, session_id)
    m = mon.for_attempt(db, sess)
    if m is None:
        raise HTTPException(404, "This attempt is not monitored.")
    return sess, m


def _event(e: MonitoringEvent, m: MonitoringSession | None = None) -> dict:
    d = e.details or {}
    return {
        "seq": e.seq, "kind": e.kind, "at": e.client_at, "received_at": e.received_at,
        "uploaded": e.received_at is not None, "duration_ms": e.duration_ms,
        "source": mon.event_source(e.kind, d), "device_state": mon.event_device_state(e.kind, d, m),
        "details": d,
    }


def _events(db: Session, m: MonitoringSession) -> list[MonitoringEvent]:
    return list(db.scalars(select(MonitoringEvent).where(MonitoringEvent.monitoring_session_id == m.id)
                           .order_by(MonitoringEvent.client_at, MonitoringEvent.seq)))


def _lock(db, m):
    # Serialize uploads/report appends for this attempt on PostgreSQL and SQLite.
    db.execute(update(MonitoringSession).where(MonitoringSession.id == m.id)
               .values(event_count=MonitoringSession.event_count))
    db.refresh(m)


# ---- student ----

@router.post("/api/student/attempts/{session_id}/monitoring/devices")
def devices(session_id: int, body: DevicesIn, user: User = Depends(require_student), db: Session = Depends(get_db)):
    sess, m = _monitored_attempt(db, user, session_id)
    if not mon.can_upload(sess, utcnow()):
        raise HTTPException(409, "This attempt has ended.")
    m.camera, m.microphone = body.camera, body.microphone
    db.commit()
    return {"camera": m.camera, "microphone": m.microphone}


@router.post("/api/student/attempts/{session_id}/monitoring/events")
def upload(session_id: int, body: EventsIn, warnings: bool = False,
           user: User = Depends(require_student), db: Session = Depends(get_db)):
    sess, m = _monitored_attempt(db, user, session_id)
    now = utcnow()
    if not mon.can_upload(sess, now):
        raise HTTPException(409, "This attempt has ended.")
    _lock(db, m)
    existing = _events(db, m)
    seen = set(db.scalars(select(MonitoringEvent.seq).where(MonitoringEvent.monitoring_session_id == m.id,
                                                           MonitoringEvent.seq.in_([e.seq for e in body.events]))))
    stored = dup = dropped = 0
    for e in body.events:
        if e.seq in seen:
            dup += 1                                   # a retry after a lost response: already stored
            continue
        seen.add(e.seq)
        if m.event_count >= mon.MAX_EVENTS_PER_ATTEMPT or not mon.accept_time(sess, e.at, now):
            dropped += 1
            continue
        details = _details(e.details)
        if e.kind == "activity_warning":
            details["confirmed"] = mon.confirm_warning(m, e, details, existing)
        event = MonitoringEvent(monitoring_session_id=m.id, seq=e.seq, kind=e.kind, client_at=e.at,
                                received_at=now, duration_ms=e.duration_ms, details=details)
        db.add(event)
        existing.append(event)
        m.event_count += 1
        stored += 1
        m.last_event_at = max(m.last_event_at or e.at, e.at)
    m.dropped_events += dropped
    try:
        db.commit()
    except IntegrityError:                             # two uploads of the same batch at once
        db.rollback()
        raise HTTPException(409, "These events are already being saved. Try again.")
    return {"stored": stored, "duplicates": dup, "dropped": dropped,
            **(mon.warning_state(m, _events(db, m)) if warnings else {})}


@router.get("/api/student/attempts/{session_id}/monitoring")
def my_record(session_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)):
    """Transparency: the student can see every event recorded about their attempt."""
    sess, m = _monitored_attempt(db, user, session_id)
    ev = _events(db, m)
    return {**mon.warning_state(m, ev), "settings": m.settings, "consented_at": m.consented_at, "camera": m.camera, "microphone": m.microphone,
            "counts": mon.summarize(m, ev)["counts"], "events": [_event(e, m) for e in ev]}


@router.post("/api/student/attempts/{session_id}/monitoring/reports")
def report_problem(session_id: int, body: ReportIn, user: User = Depends(require_student),
                   db: Session = Depends(get_db)):
    _, m = _monitored_attempt(db, user, session_id)
    _lock(db, m)
    events = _events(db, m)
    reports = [e for e in events if e.kind == "student_report"]
    if any(e.details.get("report_id") == body.report_id for e in reports):
        return {"saved": True}
    if len(reports) >= 20:
        raise HTTPException(429, "Report limit reached. Please contact your lecturer.")
    if body.event_seq is not None and not any(e.seq == body.event_seq for e in events):
        raise HTTPException(404, "Event not found for this attempt.")
    # Negative sequence numbers are reserved for server-created, append-only reports.
    now = utcnow()
    db.add(MonitoringEvent(monitoring_session_id=m.id, seq=-len(reports)-1, kind="student_report",
                           client_at=now, received_at=now, details=body.model_dump()))
    m.event_count += 1
    db.commit()
    return {"saved": True}


# ---- lecturer ----

def _own_monitoring(db: Session, user: User, mid: int) -> tuple[MonitoringSession, Quiz]:
    m = db.get(MonitoringSession, mid)
    if m is None:
        raise HTTPException(404, "Monitoring record not found.")
    z = db.get(Quiz, m.quiz_id)
    if z is None or z.owner_id != user.id:
        raise HTTPException(404, "Monitoring record not found.")
    return m, z


def _row(db: Session, m: MonitoringSession, events: list[MonitoringEvent]) -> dict:
    sess = db.get(QuizSession, m.session_id)
    st = db.get(User, m.student_id)
    s = mon.summarize(m, events)
    last_event_at = m.last_event_at or max((e.client_at for e in events), default=None)
    last_received_at = max((e.received_at for e in events), default=None)
    last_activity_at = max((e.client_at for e in events if e.kind in mon.SIGNAL_KINDS), default=None) or last_event_at
    awaiting_review = (m.review is None) and (s["status"] in ("needs_review", "event_recorded", "unavailable"))
    return {**mon.warning_state(m, events), "id": m.id, "session_id": m.session_id, "student_id": m.student_id,
            "student": st.full_name if st else None, "email": st.email if st else None,
            "attempt_no": sess.attempt_no, "attempt_status": sess.status, "started_at": sess.started_at,
            "submitted_at": sess.submitted_at, "camera": m.camera, "microphone": m.microphone,
            "status": s["status"], "reasons": s["reasons"], "counts": s["counts"], "events": len(events),
            "last_event_at": last_event_at, "last_received_at": last_received_at, "last_activity_at": last_activity_at,
            "dropped_events": m.dropped_events, "signal_availability": s["signal_availability"],
            "monitoring_state": s["monitoring_state"], "has_recorded_events": s["has_recorded_events"],
            "awaiting_review": awaiting_review, "review": m.review, "review_status": m.review or "not_reviewed",
            "review_note": m.review_note, "reviewed_at": m.reviewed_at}


def _unmonitored_row(sess: QuizSession, st: User | None) -> dict:
    return {"id": None, "session_id": sess.id, "student_id": sess.student_id,
            "student": st.full_name if st else None, "email": st.email if st else None,
            "attempt_no": sess.attempt_no, "attempt_status": sess.status, "started_at": sess.started_at,
            "submitted_at": sess.submitted_at, "camera": "not_requested", "microphone": "not_requested",
            "status": "not_monitored", "reasons": ["Monitoring was not enabled when this attempt started."],
            "counts": mon.zero_counts(), "events": 0, "last_event_at": None, "last_received_at": None,
            "last_activity_at": None, "dropped_events": 0,
            "signal_availability": mon.signal_availability(None, "not_requested", "not_requested", [], None,
                                                           has_monitoring_session=False),
            "monitoring_state": "not_monitored", "has_recorded_events": False, "awaiting_review": False,
            "review": None, "review_status": "not_monitored", "review_note": None, "reviewed_at": None}


@router.get("/api/lecturer/quizzes/{quiz_id}/monitoring")
def quiz_report(quiz_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db),
                s: Settings = Depends(get_settings_dep)):
    z = perm.own_quiz(db, user, quiz_id)
    mon.purge_old(db, s.monitoring_retention_days)
    ms = list(db.scalars(select(MonitoringSession).where(MonitoringSession.quiz_id == z.id)
                         .order_by(MonitoringSession.created_at)))
    rows = [_row(db, m, _events(db, m)) for m in ms]
    monitored_sids = {m.session_id for m in ms}
    unmonitored_sessions = list(db.scalars(select(QuizSession).where(QuizSession.quiz_id == z.id)
                                           .order_by(QuizSession.started_at)))
    for sess in unmonitored_sessions:
        if sess.id not in monitored_sids:
            rows.append(_unmonitored_row(sess, db.get(User, sess.student_id)))
    order = {"needs_review": 0, "event_recorded": 1, "unavailable": 2, "normal": 3, "not_monitored": 4}
    rows.sort(key=lambda r: (order.get(r["status"], 9), (r["student"] or "").lower(), r["attempt_no"]))
    total_keys = ("needs_review", "event_recorded", "normal")
    summary = {
        "total_attempts": len(rows),
        "needs_review": sum(r["status"] == "needs_review" for r in rows),
        "event_recorded": sum(r["status"] == "event_recorded" for r in rows),
        "normal": sum(r["status"] == "normal" for r in rows),
        "unavailable": sum(r["status"] == "unavailable" for r in rows),
        "not_monitored": sum(r["status"] == "not_monitored" for r in rows),
        "with_recorded_events": sum(bool(r["has_recorded_events"]) for r in rows),
        "no_recorded_events": sum((not r["has_recorded_events"]) and r["monitoring_state"] == "active"
                                  and r["status"] == "normal" for r in rows),
        "unavailable_or_not_monitored": sum(r["monitoring_state"] in ("unavailable", "partial", "not_monitored")
                                            or r["status"] in ("unavailable", "not_monitored") for r in rows),
        "awaiting_review": sum(bool(r["awaiting_review"]) for r in rows),
        "reviewed": sum(r["review"] is not None for r in rows),
    }
    return {"quiz_id": z.id, "quiz_title": z.title, "quiz_status": z.status, "settings": mon.quiz_settings(z),
            "rules": mon.rules(), "retention_days": s.monitoring_retention_days,
            "totals": {k: sum(r["status"] == k for r in rows) for k in total_keys},
            "summary": summary, "students": rows}


@router.get("/api/lecturer/monitoring/{monitoring_id}")
def timeline(monitoring_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    m, z = _own_monitoring(db, user, monitoring_id)
    ev = _events(db, m)
    return {**_row(db, m, ev), "quiz_id": z.id, "quiz_title": z.title, "quiz_status": z.status,
            "settings": m.settings, "consented_at": m.consented_at, "dropped_events": m.dropped_events,
            "timeline": [_event(e, m) for e in ev]}


@router.post("/api/lecturer/monitoring/{monitoring_id}/review")
def review(monitoring_id: int, body: ReviewIn, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    m, _ = _own_monitoring(db, user, monitoring_id)
    m.review = body.review
    m.review_note = (body.note or "").strip() or None
    m.reviewed_by = user.id if body.review else None
    m.reviewed_at = utcnow() if body.review else None
    db.commit()
    return {"review": m.review, "review_status": m.review or "not_reviewed",
            "review_note": m.review_note, "reviewed_at": m.reviewed_at}
