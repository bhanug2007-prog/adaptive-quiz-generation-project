"""Google Forms export, behind one small interface.

Status: the OAuth flow and Forms API calls below follow Google's documented REST API
(forms.create, then forms.batchUpdate with updateSettings + createItem), but they have NOT been run
against a real Google account in this project yet: that needs an OAuth client ID and secret from a
Google Cloud project (see docs/GOOGLE_FORMS.md). Until GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are set,
the API reports "not configured" and the manual copy export is offered instead. No fake form URL is
ever returned: the URL shown is the one Google's response contains.

What is sent: the quiz title and instructions, each approved question with its four options, the
correct option as the answer key, and the marks as point values. Student data is never sent.
"""
import base64
import hashlib
import json
import time
from datetime import timedelta
from urllib.parse import urlencode

import httpx
import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings
from app.models.base import utcnow

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
FORMS_URL = "https://forms.googleapis.com/v1/forms"
SCOPES = ["https://www.googleapis.com/auth/forms.body"]          # create and edit forms only


class FormsError(Exception):
    pass


def _fernet(secret: str) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(("forms-token:" + secret).encode()).digest())
    return Fernet(key)


def encrypt_token(data: dict, secret: str) -> str:
    return _fernet(secret).encrypt(json.dumps(data).encode()).decode()


def decrypt_token(blob: str, secret: str) -> dict | None:
    try:
        return json.loads(_fernet(secret).decrypt(blob.encode()))
    except (InvalidToken, ValueError):
        return None


def auth_url(s: Settings, user_id: int) -> str:
    state = jwt.encode({"uid": user_id, "exp": int(time.time()) + 600, "p": "google_forms"}, s.secret_key, algorithm="HS256")
    return AUTH_URL + "?" + urlencode({"client_id": s.google_client_id, "redirect_uri": s.google_redirect_uri,
                                       "response_type": "code", "scope": " ".join(SCOPES), "access_type": "offline",
                                       "prompt": "consent", "include_granted_scopes": "true", "state": state})


def read_state(s: Settings, state: str) -> int | None:
    try:
        claims = jwt.decode(state, s.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return claims.get("uid") if claims.get("p") == "google_forms" else None


def exchange_code(s: Settings, code: str) -> dict:
    r = httpx.post(TOKEN_URL, data={"code": code, "client_id": s.google_client_id, "client_secret": s.google_client_secret,
                                    "redirect_uri": s.google_redirect_uri, "grant_type": "authorization_code"}, timeout=20)
    if r.status_code != 200:
        raise FormsError("Google did not accept the sign-in. Please connect again.")
    tok = r.json()
    tok["obtained_at"] = int(time.time())
    return tok


def refresh(s: Settings, tok: dict) -> dict:
    if not tok.get("refresh_token"):
        raise FormsError("The Google connection has expired. Please connect again.")
    r = httpx.post(TOKEN_URL, data={"client_id": s.google_client_id, "client_secret": s.google_client_secret,
                                    "refresh_token": tok["refresh_token"], "grant_type": "refresh_token"}, timeout=20)
    if r.status_code != 200:
        raise FormsError("The Google connection has expired or was revoked. Please connect again.")
    new = r.json()
    tok.update(access_token=new["access_token"], expires_in=new.get("expires_in", 3600), obtained_at=int(time.time()))
    return tok


def expires_at(tok: dict):
    return utcnow() + timedelta(seconds=int(tok.get("expires_in", 3600)))


def build_requests(quiz: dict) -> list[dict]:
    """batchUpdate requests: turn on quiz mode, then one RADIO question per item with its key and points."""
    reqs = [{"updateSettings": {"settings": {"quizSettings": {"isQuiz": True}}, "updateMask": "quizSettings.isQuiz"}}]
    if quiz.get("instructions"):
        reqs.append({"updateFormInfo": {"info": {"description": quiz["instructions"]}, "updateMask": "description"}})
    for k, q in enumerate(quiz["questions"]):
        reqs.append({"createItem": {"location": {"index": k}, "item": {
            "title": q["text"],
            "questionItem": {"question": {
                "required": False,
                "grading": {"pointValue": max(0, int(round(q["marks"]))),
                            "correctAnswers": {"answers": [{"value": q["correct"]}]},
                            **({"generalFeedback": {"text": q["explanation"]}} if q.get("explanation") else {})},
                "choiceQuestion": {"type": "RADIO", "options": [{"value": o} for o in q["options"]]}}}}}})
    return reqs


def create_form(tok: dict, quiz: dict) -> dict:
    """Returns {"form_id", "responder_url", "edit_url", "status"} from Google's responses."""
    headers = {"Authorization": f"Bearer {tok['access_token']}"}
    r = httpx.post(FORMS_URL, json={"info": {"title": quiz["title"], "documentTitle": quiz["title"]}},
                   headers=headers, timeout=30)
    if r.status_code in (401, 403):
        raise FormsError("Google refused the request. Reconnect your Google account and allow form access.")
    if r.status_code != 200:
        raise FormsError(f"Google Forms returned HTTP {r.status_code} while creating the form.")
    form = r.json()
    form_id = form["formId"]
    out = {"form_id": form_id, "responder_url": form.get("responderUri"),
           "edit_url": f"https://docs.google.com/forms/d/{form_id}/edit", "status": "created", "error": None}
    r2 = httpx.post(f"{FORMS_URL}/{form_id}:batchUpdate", json={"requests": build_requests(quiz)}, headers=headers,
                    timeout=60)
    if r2.status_code != 200:
        out["status"] = "partial"
        out["error"] = (f"The form was created but adding the questions failed (HTTP {r2.status_code}). "
                        "Open it in Google Forms to check, or delete it and try again.")
    return out
