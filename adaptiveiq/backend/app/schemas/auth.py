import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


def check_password(p: str) -> str:
    if len(p) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if len(p.encode("utf-8")) > 72:
        raise ValueError("Password must be at most 72 bytes.")
    if not re.search(r"[A-Za-z]", p) or not re.search(r"\d", p):
        raise ValueError("Password must contain at least one letter and one number.")
    return p


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=2, max_length=120)
    role: Literal["student", "lecturer"] = "student"
    invite_code: str | None = Field(default=None, max_length=100)
    roll_number: str | None = Field(default=None, max_length=40)
    program: str | None = Field(default=None, max_length=120)
    semester: int | None = Field(default=None, ge=1, le=12)
    department: str | None = Field(default=None, max_length=120)

    @field_validator("password")
    @classmethod
    def _pw(cls, v: str) -> str:
        return check_password(v)

    @field_validator("full_name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 2:
            raise ValueError("Please enter your name.")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=72)

    @field_validator("new_password")
    @classmethod
    def _pw(cls, v: str) -> str:
        return check_password(v)


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    roll_number: str | None = Field(default=None, max_length=40)
    program: str | None = Field(default=None, max_length=120)
    semester: int | None = Field(default=None, ge=1, le=12)
    weekly_study_hours: int | None = Field(default=None, ge=0, le=80)
    department: str | None = Field(default=None, max_length=120)
    designation: str | None = Field(default=None, max_length=120)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=10, max_length=2000)


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    created_at: datetime
    email_verified: bool
    verification_required: bool
    roll_number: str | None = None
    program: str | None = None
    semester: int | None = None
    weekly_study_hours: int | None = None
    department: str | None = None
    designation: str | None = None


class AuthConfig(BaseModel):
    lecturer_signup_enabled: bool
    allowed_email_domains: list[str]
    email_verification_required: bool
