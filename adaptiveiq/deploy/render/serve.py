"""Serve the built React app and the existing API on one origin."""
from pathlib import Path

from starlette.exceptions import HTTPException
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles

from app.main import app

WEB_ROOT = Path(__file__).with_name("web")


class FrontendFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404 or path.split("/", 1)[0] in {"api", "assets"} or Path(path).suffix:
                raise
            return FileResponse(WEB_ROOT / "index.html", headers={"Cache-Control": "no-cache"})


app.mount("/", FrontendFiles(directory=WEB_ROOT, html=True), name="frontend")
