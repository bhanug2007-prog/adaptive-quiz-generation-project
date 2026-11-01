import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import current_user, get_db, get_settings_dep, is_verified, optional_user
from app.core.security import (burn_password_check, hash_password, make_token, make_verify_token, read_token,
                               verify_password)
from app.models import LecturerProfile, StudentProfile, User
from app.models.base import utcnow
from app.schemas.auth import (AuthConfig, ChangePasswordRequest, LoginRequest, ProfileUpdate, RegisterRequest,
                              UserOut, VerifyEmailRequest)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def user_out(u: User, s: Settings) -> UserOut:
    sp, lp = u.student_profile, u.lecturer_profile
    return UserOut(id=u.id, email=u.email, full_name=u.full_name, role=u.role, created_at=u.created_at,
                   email_verified=is_verified(u, s), verification_required=s.require_email_verification,
                   roll_number=sp.roll_number if sp else None, program=sp.program if sp else None,
                   semester=sp.semester if sp else None, weekly_study_hours=sp.weekly_study_hours if sp else None,
                   department=lp.department if lp else None, designation=lp.designation if lp else None)


def _set_session(resp: Response, s: Settings, u: User):
    token = make_token(u.id, u.role, u.token_version, s.secret_key, s.session_hours)
    resp.set_cookie(s.cookie_name, token, max_age=s.session_hours * 3600, httponly=True, secure=s.cookie_secure,
                    samesite="lax", path="/")


def _client_key(request: Request, email: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{email}|{host}"


def send_verification(request: Request, s: Settings, u: User) -> None:
    token = make_verify_token(u.id, u.email, s.secret_key, s.verify_link_hours)
    link = f"{s.frontend_url.rstrip('/')}/verify-email?token={token}"
    request.app.state.mailer.send(
        u.email, "Verify your AdaptiveIQ email address",
        f"Hello {u.full_name},\n\nOpen this link to verify your email address for AdaptiveIQ:\n{link}\n\n"
        f"The link works for {s.verify_link_hours} hours. If you did not create an account, ignore this email.\n")


@router.get("/config", response_model=AuthConfig)
def auth_config(s: Settings = Depends(get_settings_dep)):
    return AuthConfig(lecturer_signup_enabled=bool(s.lecturer_invite_code), allowed_email_domains=sorted(s.email_domains),
                      email_verification_required=s.require_email_verification)


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterRequest, request: Request, resp: Response, db: Session = Depends(get_db),
             s: Settings = Depends(get_settings_dep)):
    email = body.email.lower()
    domain = email.rsplit("@", 1)[-1]
    if s.email_domains and domain not in s.email_domains:
        raise HTTPException(422, f"Use an email address ending in {', '.join('@' + d for d in sorted(s.email_domains))}.")
    if body.role == "lecturer":
        if not s.lecturer_invite_code:
            raise HTTPException(403, "Lecturer sign-up is turned off. Ask the administrator for an account.")
        limiter = request.app.state.invite_limiter
        key = request.client.host if request.client else "unknown"
        wait = limiter.blocked(key)
        if wait:
            raise HTTPException(429, f"Too many wrong invite codes. Try again in {max(1, wait // 60)} minute(s).")
        if not hmac.compare_digest((body.invite_code or "").encode(), s.lecturer_invite_code.encode()):
            limiter.fail(key)
            raise HTTPException(403, "The lecturer invite code is not correct.")
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "An account with this email already exists. Sign in instead.")
    u = User(email=email, password_hash=hash_password(body.password), full_name=body.full_name, role=body.role)
    if body.role == "student":
        u.student_profile = StudentProfile(roll_number=body.roll_number, program=body.program, semester=body.semester)
    else:
        u.lecturer_profile = LecturerProfile(department=body.department)
    u.last_login_at = utcnow()
    db.add(u)
    db.commit()
    if s.require_email_verification:
        send_verification(request, s, u)
    _set_session(resp, s, u)
    return user_out(u, s)


@router.post("/login", response_model=UserOut)
def login(body: LoginRequest, request: Request, resp: Response, db: Session = Depends(get_db),
          s: Settings = Depends(get_settings_dep)):
    email = body.email.lower()
    limiter = request.app.state.login_limiter
    key = _client_key(request, email)
    wait = limiter.blocked(key)
    if wait:
        raise HTTPException(429, f"Too many failed sign-in attempts. Try again in {max(1, wait // 60)} minute(s).")
    u = db.scalar(select(User).where(User.email == email))
    if u is None:
        burn_password_check(body.password)
        limiter.fail(key)
        raise HTTPException(401, "Email or password is not correct.")
    if not verify_password(body.password, u.password_hash) or not u.is_active:
        limiter.fail(key)
        raise HTTPException(401, "Email or password is not correct.")
    limiter.reset(key)
    u.last_login_at = utcnow()
    db.commit()
    _set_session(resp, s, u)
    return user_out(u, s)


@router.post("/logout", status_code=204)
def logout(resp: Response, user: User | None = Depends(optional_user), db: Session = Depends(get_db),
           s: Settings = Depends(get_settings_dep)):
    # Bumping the token version invalidates this session token on the server, not just in this browser.
    # It also ends the user's sessions on other devices.
    if user is not None:
        user.token_version += 1
        db.commit()
    resp.delete_cookie(s.cookie_name, path="/")


@router.post("/verify-email", response_model=UserOut)
def verify_email(body: VerifyEmailRequest, db: Session = Depends(get_db), s: Settings = Depends(get_settings_dep)):
    claims = read_token(body.token, s.secret_key, typ="verify_email")
    u = db.get(User, int(claims["sub"])) if claims else None
    if u is None or claims.get("email") != u.email:
        raise HTTPException(400, "This verification link is not valid or has expired. Sign in and ask for a new one.")
    if u.email_verified_at is None:
        u.email_verified_at = utcnow()
        db.commit()
    return user_out(u, s)


@router.post("/resend-verification", status_code=204)
def resend_verification(request: Request, user: User = Depends(current_user), s: Settings = Depends(get_settings_dep)):
    if user.email_verified_at is not None or not s.require_email_verification:
        return
    limiter = request.app.state.resend_limiter
    if limiter.blocked(str(user.id)):
        raise HTTPException(429, "A link was sent recently. Check your inbox (and spam) or try again in a few minutes.")
    limiter.fail(str(user.id))
    send_verification(request, s, user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user), s: Settings = Depends(get_settings_dep)):
    return user_out(user, s)


@router.patch("/me", response_model=UserOut)
def update_me(body: ProfileUpdate, user: User = Depends(current_user), db: Session = Depends(get_db),
              s: Settings = Depends(get_settings_dep)):
    data = body.model_dump(exclude_unset=True)
    if "full_name" in data and data["full_name"]:
        user.full_name = " ".join(data["full_name"].split())
    if user.role == "student":
        sp = user.student_profile or StudentProfile()
        user.student_profile = sp
        for k in ("roll_number", "program", "semester", "weekly_study_hours"):
            if k in data:
                setattr(sp, k, data[k])
    else:
        lp = user.lecturer_profile or LecturerProfile()
        user.lecturer_profile = lp
        for k in ("department", "designation"):
            if k in data:
                setattr(lp, k, data[k])
    db.commit()
    return user_out(user, s)


@router.post("/change-password", status_code=204)
def change_password(body: ChangePasswordRequest, resp: Response, user: User = Depends(current_user),
                    db: Session = Depends(get_db), s: Settings = Depends(get_settings_dep)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is not correct.")
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1                         # signs out other devices
    db.commit()
    _set_session(resp, s, user)
