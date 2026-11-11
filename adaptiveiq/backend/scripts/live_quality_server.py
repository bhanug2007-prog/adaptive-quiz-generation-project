"""Opt-in live quality verification server, using a disposable DB and existing credentials.

Start explicitly with: python -m scripts.live_quality_server
No live calls happen until the test client requests generation or Check again.
Never writes configuration or connects to the normal application database.
"""
import tempfile
from pathlib import Path

import uvicorn

from app.core.config import Settings
from app.core.db import Base
from app.main import create_app


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="adaptiveiq-live-quality-") as directory:
        settings = Settings().model_copy(update={
            "database_url": f"sqlite:///{Path(directory).as_posix()}/test.db",
            "environment": "test", "secret_key": "disposable-live-review-" + "x" * 40,
            "lecturer_invite_code": "live-review-test", "require_email_verification": False,
            "monitoring_retention_days": 0, "max_attempts_per_question": 1,
            "allowed_origins": "http://localhost:5192", "frontend_url": "http://localhost:5192",
        })
        app = create_app(settings)
        Base.metadata.create_all(app.state.db.engine)
        try:
            uvicorn.run(app, host="127.0.0.1", port=8192, log_level="warning")
        finally:
            app.state.db.engine.dispose()
