"""AdaptiveIQ API. Run: uvicorn app.main:app --reload (from backend/)."""
import logging
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.validators.mathcheck import can_run_safely, sandbox_layers
from app.api import (auth, courses, generation, integrations, lecturer_analytics, lecturer_quizzes, questions, reports,
                     student_analytics, student_quizzes)
from app.core.config import Settings, get_settings
from app.core.db import Database
from app.core.security import LoginLimiter
from app.services.mailer import Mailer
from app.services.generation_service import GenerationService
from app.services.model_service import ModelService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("adaptiveiq")

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "AdaptiveIQ"
MAX_BODY = 256 * 1024                                   # reference text is capped at 12k characters anyway


def _origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower() if parts.scheme and parts.netloc else ""


def origin_allowed(request: Request, allowed: set[str]) -> bool:
    """CSRF check on unsafe requests: a browser sends Origin (or at least Referer); it must be this
    app's own origin or a configured frontend origin. Requests with neither header are not from a
    browser page, so the custom-header check is what protects them."""
    origin = request.headers.get("origin")
    if origin is None or origin == "null":
        ref = request.headers.get("referer")
        origin = _origin_of(ref) if ref else origin
    if origin is None:
        return True
    own = f"{request.url.scheme}://{request.headers.get('host', '')}".lower()
    return origin.lower() in allowed or origin.lower() == own


def create_app(settings: Settings | None = None, start_worker: bool = True) -> FastAPI:
    s = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_worker:
            app.state.generation.start()
        yield
        app.state.model.close()

    app = FastAPI(title="AdaptiveIQ API", version="1.0.0", lifespan=lifespan,
                  description="AI-generated assessments, adaptive practice and learning analytics.")
    app.state.settings = s
    app.state.db = Database(s.database_url)
    app.state.model = ModelService(s)
    app.state.generation = GenerationService(s, app.state.db, app.state.model)
    app.state.login_limiter = LoginLimiter(s.login_max_failures, s.login_window_minutes * 60)
    app.state.invite_limiter = LoginLimiter(s.invite_max_failures, s.login_window_minutes * 60)
    app.state.resend_limiter = LoginLimiter(1, 60)
    app.state.mailer = Mailer(s)
    allowed_origins = {o.strip().rstrip("/").lower() for o in s.allowed_origins.split(",") if o.strip()}
    allowed_origins.add(s.frontend_url.rstrip("/").lower())

    app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in s.allowed_origins.split(",") if o.strip()],
                       allow_credentials=True, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                       allow_headers=["Content-Type", "X-Requested-With"])

    @app.middleware("http")
    async def guard(request: Request, call_next):
        # Cookie sessions + a custom header: browsers cannot send this header cross-site without a CORS
        # preflight, which only the configured origins pass. Blocks cross-site form posts (CSRF).
        if request.method in UNSAFE and request.url.path.startswith("/api/") \
                and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
            return JSONResponse({"detail": "Missing request header. Reload the page and try again."}, status_code=403)
        if request.method in UNSAFE and request.url.path.startswith("/api/") and not origin_allowed(request, allowed_origins):
            return JSONResponse({"detail": "This request came from a site that is not allowed."}, status_code=403)
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > MAX_BODY:
            return JSONResponse({"detail": "Request is too large."}, status_code=413)
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        if request.url.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        msgs = []
        for e in exc.errors():
            field = ".".join(str(p) for p in e.get("loc", []) if p not in ("body", "query", "path"))
            msg = str(e.get("msg", "Invalid value")).removeprefix("Value error, ")
            msgs.append(f"{field}: {msg}" if field else msg)
        return JSONResponse({"detail": "; ".join(msgs) or "Invalid request."}, status_code=422)

    @app.get("/api/health", tags=["health"])
    def health():
        state, detail = app.state.model.health()
        db_ok = True
        try:
            with app.state.db.engine.connect() as c:
                c.exec_driver_sql("SELECT 1")
        except Exception:
            db_ok = False
        return {"status": "ok" if db_ok else "degraded", "database": "ok" if db_ok else "unreachable",
                "database_engine": s.database_engine, "environment": s.environment,
                "email": {"verification_required": s.require_email_verification, "smtp_configured": s.smtp_configured},
                "model": {"state": state, "detail": detail, "variant": s.model_variant, "name": s.model_name,
                          "base_model": s.model_base_id, "quantization": s.model_quantization},
                "generation_queue": app.state.generation.queue_length(),
                "google_forms_configured": s.google_forms_configured,
                "math_check": {"enabled": s.math_check and can_run_safely(s.math_check_allow_without_os_limits),
                               "sandbox": sandbox_layers()}}

    for r in (auth, courses, generation, questions, lecturer_quizzes, student_quizzes, student_analytics,
              lecturer_analytics, reports, integrations):
        app.include_router(r.router)
    return app


app = create_app()
