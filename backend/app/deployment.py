"""Single-process production entrypoint for native systemd deployments."""

import mimetypes
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.main import app as api_app

mimetypes.add_type("image/webp", ".webp")

project_dir = Path(__file__).resolve().parents[2]
static_dir = project_dir / "frontend" / "dist"
branding_dir = project_dir / "branding"

app = FastAPI(title=f"{settings.app_name} deployment", docs_url=None, redoc_url=None)
app.mount("/api", api_app)
app.mount(
    "/uploads", StaticFiles(directory=settings.upload_dir), name="deployment-uploads"
)

if branding_dir.is_dir():
    app.mount("/brand", StaticFiles(directory=branding_dir), name="deployment-brand")
if static_dir.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=static_dir / "assets"),
        name="deployment-assets",
    )


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    index = static_dir / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=503, detail="Frontend has not been built")
    requested = (static_dir / path).resolve()
    if requested.is_relative_to(static_dir) and requested.is_file():
        return FileResponse(requested)
    if Path(path).suffix:
        raise HTTPException(status_code=404, detail="Static asset not found")
    return FileResponse(index)
