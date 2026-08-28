from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse

from app import deployment


def _prepare_frontend(tmp_path: Path) -> Path:
    frontend = tmp_path / "dist"
    frontend.mkdir()
    (frontend / "index.html").write_text("<html>Shaverma-chi</html>", encoding="utf-8")
    return frontend


def test_frontend_serves_webp_with_the_correct_media_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    frontend = _prepare_frontend(tmp_path)
    image = frontend / "menu-images" / "shawarma.webp"
    image.parent.mkdir()
    image.write_bytes(b"RIFF\x00\x00\x00\x00WEBP")
    monkeypatch.setattr(deployment, "static_dir", frontend)

    response = deployment.frontend("menu-images/shawarma.webp")

    assert isinstance(response, FileResponse)
    assert response.media_type == "image/webp"
    assert response.path == image


def test_frontend_returns_404_for_a_missing_static_asset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    frontend = _prepare_frontend(tmp_path)
    monkeypatch.setattr(deployment, "static_dir", frontend)

    with pytest.raises(HTTPException) as exc_info:
        deployment.frontend("menu-images/missing.webp")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Static asset not found"


def test_frontend_keeps_spa_routes_on_the_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    frontend = _prepare_frontend(tmp_path)
    monkeypatch.setattr(deployment, "static_dir", frontend)

    response = deployment.frontend("pos")

    assert isinstance(response, FileResponse)
    assert response.path == frontend / "index.html"
