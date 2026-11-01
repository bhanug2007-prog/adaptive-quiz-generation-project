"""Google Forms export and the manual copy export that always works."""
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import get_db, get_settings_dep, require_lecturer, verified_lecturer
from app.integrations import google_forms as gf
from app.models import ExternalIntegration, FormExport, Quiz, User
from app.models.base import utcnow
from app.services import permissions as perm

router = APIRouter(prefix="/api", tags=["integrations"])


def _quiz_payload(z: Quiz) -> dict:
    not_ok = [i.position + 1 for i in z.items if i.question.review_status != "approved"]
    if not z.items:
        raise HTTPException(422, "The quiz has no questions.")
    if not_ok:
        raise HTTPException(422, f"Approve every question before exporting (not approved: {', '.join(map(str, not_ok))}).")
    return {"title": z.title, "instructions": z.instructions,
            "questions": [{"text": i.question.text, "marks": i.marks, "explanation": i.question.explanation,
                           "options": [o.text for o in i.question.options],
                           "correct": next(o.text for o in i.question.options if o.is_correct)} for i in z.items]}


@router.get("/integrations/google/status")
def google_status(user: User = Depends(require_lecturer), db: Session = Depends(get_db),
                  s: Settings = Depends(get_settings_dep)):
    row = db.scalar(select(ExternalIntegration).where(ExternalIntegration.user_id == user.id,
                                                      ExternalIntegration.provider == "google_forms"))
    return {"configured": s.google_forms_configured, "connected": bool(row and row.status == "connected"),
            "tested_against_google": False,
            "message": None if s.google_forms_configured else
            "Google Forms export is not set up on this server yet. Use the manual export meanwhile."}


@router.get("/integrations/google/connect")
def google_connect(user: User = Depends(require_lecturer), s: Settings = Depends(get_settings_dep)):
    if not s.google_forms_configured:
        raise HTTPException(503, "Google Forms export is not set up on this server (no OAuth client).")
    return {"auth_url": gf.auth_url(s, user.id)}


@router.get("/integrations/google/callback")
def google_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None,
                    db: Session = Depends(get_db), s: Settings = Depends(get_settings_dep)):
    target = s.frontend_url.rstrip("/") + "/lecturer/settings"
    uid = gf.read_state(s, state) if state else None
    if error or not code or uid is None:
        return RedirectResponse(target + "?google=failed")
    try:
        tok = gf.exchange_code(s, code)
    except gf.FormsError:
        return RedirectResponse(target + "?google=failed")
    row = db.scalar(select(ExternalIntegration).where(ExternalIntegration.user_id == uid,
                                                      ExternalIntegration.provider == "google_forms"))
    if row is None:
        row = ExternalIntegration(user_id=uid, provider="google_forms", status="connected", scopes=" ".join(gf.SCOPES))
        db.add(row)
    old = gf.decrypt_token(row.token_encrypted, s.secret_key) if row.token_encrypted else {}
    if not tok.get("refresh_token") and old:
        tok["refresh_token"] = old.get("refresh_token")
    row.status, row.token_encrypted, row.expires_at = "connected", gf.encrypt_token(tok, s.secret_key), gf.expires_at(tok)
    db.commit()
    return RedirectResponse(target + "?google=connected")


@router.delete("/integrations/google", status_code=204)
def google_disconnect(user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    row = db.scalar(select(ExternalIntegration).where(ExternalIntegration.user_id == user.id,
                                                      ExternalIntegration.provider == "google_forms"))
    if row:
        db.delete(row)
        db.commit()


@router.post("/lecturer/quizzes/{quiz_id}/google-form")
def export_to_google(quiz_id: int, user: User = Depends(verified_lecturer), db: Session = Depends(get_db),
                     s: Settings = Depends(get_settings_dep)):
    z = perm.own_quiz(db, user, quiz_id)
    payload = _quiz_payload(z)
    if not s.google_forms_configured:
        raise HTTPException(503, "Google Forms export is not set up on this server. Use the manual export.")
    row = db.scalar(select(ExternalIntegration).where(ExternalIntegration.user_id == user.id,
                                                      ExternalIntegration.provider == "google_forms"))
    tok = gf.decrypt_token(row.token_encrypted, s.secret_key) if row and row.token_encrypted else None
    if not tok:
        raise HTTPException(409, "Connect your Google account first (Settings).")
    try:
        if row.expires_at is None or row.expires_at <= utcnow():
            tok = gf.refresh(s, tok)
            row.token_encrypted, row.expires_at = gf.encrypt_token(tok, s.secret_key), gf.expires_at(tok)
        res = gf.create_form(tok, payload)
    except gf.FormsError as e:
        row.status = "expired" if "connect" in str(e).lower() else row.status
        db.add(FormExport(quiz_id=z.id, user_id=user.id, status="failed", error=str(e)))
        db.commit()
        raise HTTPException(502, str(e))
    except httpx.HTTPError as e:                     # network failure talking to Google
        db.add(FormExport(quiz_id=z.id, user_id=user.id, status="failed", error="Could not reach Google."))
        db.commit()
        raise HTTPException(502, "Could not reach Google. Check the internet connection and try again.") from e
    ex = FormExport(quiz_id=z.id, user_id=user.id, status=res["status"], form_id=res["form_id"],
                    responder_url=res["responder_url"], edit_url=res["edit_url"], error=res["error"])
    db.add(ex)
    db.commit()
    return {"status": ex.status, "form_id": ex.form_id, "responder_url": ex.responder_url, "edit_url": ex.edit_url,
            "error": ex.error}


@router.get("/lecturer/quizzes/{quiz_id}/google-form/exports")
def list_exports(quiz_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    z = perm.own_quiz(db, user, quiz_id)
    rows = db.scalars(select(FormExport).where(FormExport.quiz_id == z.id).order_by(FormExport.id.desc()))
    return [{"status": r.status, "responder_url": r.responder_url, "edit_url": r.edit_url, "error": r.error,
             "created_at": r.created_at} for r in rows]


@router.get("/lecturer/quizzes/{quiz_id}/export", response_class=PlainTextResponse)
def manual_export(quiz_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    """Plain text to paste into Google Forms (or any LMS) by hand. Includes the answer key."""
    z = perm.own_quiz(db, user, quiz_id)
    p = _quiz_payload(z)
    lines = [p["title"], ""]
    if p["instructions"]:
        lines += [p["instructions"], ""]
    for n, q in enumerate(p["questions"], 1):
        lines.append(f"{n}. {q['text']} ({q['marks']:g} mark{'s' if q['marks'] != 1 else ''})")
        for letter, o in zip("ABCD", q["options"]):
            lines.append(f"   {letter}) {o}")
        lines.append(f"   Answer: {'ABCD'[q['options'].index(q['correct'])]}) {q['correct']}")
        if q["explanation"]:
            lines.append(f"   Explanation: {q['explanation']}")
        lines.append("")
    return "\n".join(lines)
