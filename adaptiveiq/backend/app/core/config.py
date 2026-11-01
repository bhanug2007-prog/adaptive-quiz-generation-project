"""All settings come from environment variables or backend/.env (see .env.example)."""
from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "dev-only-change-me-dev-only-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore",
                                      protected_namespaces=())

    environment: Literal["development", "test", "production"] = "development"

    # Database: PostgreSQL in normal use; a SQLite URL also works for a quick local run or tests
    database_url: str = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/adaptiveiq"

    # Auth
    secret_key: str = DEV_SECRET                      # signs session tokens; set a long random value
    session_hours: int = 8
    cookie_name: str = "aiq_session"
    cookie_secure: bool = False                       # True behind HTTPS (required in production)
    lecturer_invite_code: str = ""                    # empty = lecturer self-registration disabled
    allowed_email_domains: str = ""                   # e.g. "gmail.com,iiitdwd.ac.in"; empty = any domain
    login_max_failures: int = 5
    login_window_minutes: int = 10
    invite_max_failures: int = 5                      # wrong lecturer invite codes per client per window

    # Email verification. Without SMTP settings the verification link is written to the backend log
    # (development only; production refuses to start without SMTP when verification is required).
    require_email_verification: bool = True
    verify_link_hours: int = 48
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_starttls: bool = True

    # Model inference service: any OpenAI-compatible chat endpoint (llama.cpp llama-server, vLLM, ...)
    model_base_url: str = "http://127.0.0.1:8080"
    model_api_key: str = ""
    model_name: str = "qwen7b-mcq"
    model_variant: Literal["finetuned", "base"] = "finetuned"
    model_base_id: str = "Qwen/Qwen2.5-7B-Instruct"
    model_adapter: str = "qwen-7b-mcq-adapter (LoRA r=16), merged"
    model_quantization: str = "GGUF Q4_K_M"
    model_timeout_s: float = 600.0
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 320

    # Generation pipeline
    default_branch: str = "CSE"
    max_attempts_per_question: int = 3
    math_check: bool = True
    math_check_strict: bool = False
    # Windows has no OS memory/CPU limits for the sandbox, so the check is skipped there unless this is set
    math_check_allow_without_os_limits: bool = False
    duplicate_threshold: float = 0.85
    max_queued_generations: int = 10
    max_reference_chars: int = 12000

    # Adaptive engine thresholds (documented in docs/ML_EVALUATION.md)
    mastery_min_evidence: int = 5                     # unique questions before any confident label
    mastery_half_life_days: float = 21.0              # older answers count half after this many days

    # Google Forms (optional; leave empty until an OAuth client exists)
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/integrations/google/callback"
    frontend_url: str = "http://localhost:5173"

    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @model_validator(mode="after")
    def _production_safety(self):
        if self.environment == "production":
            if self.secret_key == DEV_SECRET or len(self.secret_key) < 32 or "change-me" in self.secret_key:
                raise ValueError("SECRET_KEY must be set to a random value of at least 32 characters in production")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production (serve over HTTPS)")
            if self.database_engine == "sqlite":
                raise ValueError("Production needs PostgreSQL: set DATABASE_URL to a postgresql+psycopg:// URL")
            if self.require_email_verification and not self.smtp_configured:
                raise ValueError("REQUIRE_EMAIL_VERIFICATION is on, so production needs SMTP_HOST and SMTP_FROM")
        return self

    @property
    def email_domains(self) -> set[str]:
        return {d.strip().lower().lstrip("@") for d in self.allowed_email_domains.split(",") if d.strip()}

    @property
    def database_engine(self) -> str:
        return self.database_url.split(":", 1)[0].split("+", 1)[0].lower()

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    @property
    def google_forms_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()
