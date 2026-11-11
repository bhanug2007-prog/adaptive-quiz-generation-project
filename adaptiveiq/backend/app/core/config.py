"""All settings come from environment variables or backend/.env (see .env.example)."""
from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
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
    reset_token_minutes: int = 15
    reset_request_max: int = 5
    reset_ip_max: int = 20
    reset_verify_max: int = 10
    reset_window_minutes: int = 15

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
    math_check_strict: bool = True
    # Only set on platforms without POSIX setrlimit or Windows Job Objects
    math_check_allow_without_os_limits: bool = False
    duplicate_threshold: float = 0.85
    max_queued_generations: int = 10
    max_reference_chars: int = 12000
    max_document_bytes: int = 10 * 1024 * 1024
    document_ttl_minutes: int = 30
    min_document_words: int = 40
    min_words_per_document_question: int = 22

    # Question quality evaluation (an LLM reviewer after the Python checks; see app/services/quality_service.py).
    # Without GROK_API_KEY, or when Grok is down / rate limited / out of quota, only the Python checks run
    # and every question says "AI review not done", so generation keeps working.
    quality_check: bool = True                        # run the AI reviewer on lecturer questions when a key is set
    quality_check_practice: bool = False              # also on student practice (costs one API call per question)
    quality_check_difficulty: bool = True             # a question whose judged difficulty differs is retried
    quality_min_score: int = 60                       # 0-100; below this the question is retried
    grok_api_key: str = ""                            # backend only, never sent to the browser
    grok_base_url: str = "https://api.x.ai/v1"
    grok_model: str = "grok-4.3"                      # any chat model name your xAI account can use
    grok_timeout_s: float = 45.0
    grok_cooldown_s: float = 300.0                    # pause Grok calls this long after a rate limit or quota error
    # Lecturer Insights Agent ("Ask about your class"). Without Grok it answers from fixed rules and templates.
    insights_ai: bool = True                          # let Grok pick the tools and word the answer (when a key is set)
    insights_per_10_min: int = 20                     # questions one lecturer may ask in 10 minutes
    # Assessment integrity monitoring (switched on per quiz by the lecturer; see docs/MONITORING.md)
    monitoring_retention_days: int = 180              # monitoring events older than this are deleted; 0 = keep
    monitoring_face_interval_ms: int = 1500           # how often the browser checks the camera image for faces
    monitoring_warning_threshold: int = Field(default=3, ge=1, le=100)
    monitoring_warning_cooldown_ms: int = Field(default=15000, ge=0, le=3600000)
    monitoring_warning_face_none_ms: int = Field(default=10000, ge=1000, le=300000)
    monitoring_warning_face_multiple_ms: int = Field(default=3000, ge=1000, le=300000)
    monitoring_warning_speech_ms: int = Field(default=5000, ge=1000, le=300000)
    monitoring_warning_page_hidden_ms: int = Field(default=1000, ge=0, le=300000)
    monitoring_warning_fullscreen_exit_ms: int = Field(default=1000, ge=0, le=300000)

    # Adaptive engine thresholds (documented in docs/ML_EVALUATION.md)
    mastery_min_evidence: int = 5                     # unique questions before any confident label
    mastery_half_life_days: float = 21.0              # older answers count half after this many days

    # Personalized Learning Agent (LangGraph Stage 2 persistent HITL workflow)
    # Uses SQLAlchemy tables (`lg_checkpoints`, `lg_checkpoint_blobs`, `lg_checkpoint_writes`)
    # on DATABASE_URL (SQLite locally or PostgreSQL in deployment), requiring no extra broker.
    learning_agent_checkpoint_backend: Literal["sqlalchemy"] = "sqlalchemy"
    learning_agent_plan_ttl_days: int = Field(default=30, ge=1, le=365)

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
    def grok_configured(self) -> bool:
        return bool(self.grok_api_key.strip())

    @property
    def ai_provider_id(self) -> str:
        u = self.grok_base_url.lower()
        if "groq.com" in u:
            return "groq"
        if "x.ai" in u:
            return "grok"
        return "openai_compatible"

    @property
    def ai_provider_label(self) -> str:
        u = self.grok_base_url.lower()
        if "groq.com" in u:
            return "Groq API"
        if "x.ai" in u:
            return "xAI Grok"
        return "the configured AI provider"

    @property
    def google_forms_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()
