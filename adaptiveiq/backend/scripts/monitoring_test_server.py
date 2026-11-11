"""Isolated monitoring E2E server. Never loads the project's .env or database."""
import sys
import tempfile
from pathlib import Path

import uvicorn

from app.core.config import Settings
from app.core.db import Base
from app.main import create_app
from tests import fake_model_server


if __name__ == "__main__":
    port, model_port = map(int, sys.argv[1:3])
    origin = sys.argv[3]
    with tempfile.TemporaryDirectory(prefix="adaptiveiq-monitoring-") as directory:
        settings = Settings(
            _env_file=None, environment="test",
            database_url=f"sqlite:///{Path(directory).as_posix()}/test.db",
            model_base_url=f"http://127.0.0.1:{model_port}",
            model_api_key="", grok_api_key="", quality_check=False, insights_ai=False,
            lecturer_invite_code="dev-invite", require_email_verification=False,
            secret_key="monitoring-test-only-" + "x" * 40,
            allowed_origins=origin, frontend_url=origin,
        )
        fake_model_server.STATE.update(mode="clean", n=0)
        model = fake_model_server.start(model_port)
        app = create_app(settings)
        Base.metadata.create_all(app.state.db.engine)
        try:
            uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
        finally:
            model.shutdown()
            app.state.db.engine.dispose()
