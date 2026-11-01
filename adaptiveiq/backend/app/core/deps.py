"""Request dependencies: database session, signed-in user, role checks."""
from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import read_token
from app.models import User


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Iterator[Session]:
    yield from request.app.state.db.get_session()


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    s: Settings = request.app.state.settings
    token = request.cookies.get(s.cookie_name)
    claims = read_token(token, s.secret_key) if token else None
    if not claims:
        raise HTTPException(401, "Please sign in.")
    user = db.get(User, int(claims["sub"]))
    if user is None or not user.is_active or claims.get("tv") != user.token_version:
        raise HTTPException(401, "Your session has ended. Please sign in again.")
    return user


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    try:
        return current_user(request, db)
    except HTTPException:
        return None


def is_verified(user: User, s: Settings) -> bool:
    return user.email_verified_at is not None or not s.require_email_verification


def require_verified(request: Request, user: User = Depends(current_user)) -> User:
    """For actions that matter (joining courses, generating, publishing, enrolling): the email must be verified."""
    if not is_verified(user, request.app.state.settings):
        raise HTTPException(403, f"Verify your email address first. We sent a link to {user.email}.")
    return user


def require_student(user: User = Depends(current_user)) -> User:
    if user.role != "student":
        raise HTTPException(403, "This page is for students.")
    return user


def require_lecturer(user: User = Depends(current_user)) -> User:
    if user.role != "lecturer":
        raise HTTPException(403, "This page is for lecturers.")
    return user


def verified_student(user: User = Depends(require_student), _v: User = Depends(require_verified)) -> User:
    return user


def verified_lecturer(user: User = Depends(require_lecturer), _v: User = Depends(require_verified)) -> User:
    return user
