from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.config import AppConfig
from backend.app.main import create_app


def _write_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _create_temp_dir() -> Path:
    root = Path(".test-work")
    root.mkdir(exist_ok=True)
    temp_dir = root / uuid4().hex
    temp_dir.mkdir(parents=True, exist_ok=False)
    return temp_dir


def _build_client(tmp_path: Path) -> TestClient:
    old_image = tmp_path / "old.jpg"
    new_image = tmp_path / "nested" / "new.png"
    text = tmp_path / "doc.txt"

    _write_file(old_image, b"\xff\xd8\xff")
    _write_file(new_image, b"\x89PNG\r\n\x1a\n")
    _write_file(text, b"text")

    os.utime(old_image, (1000, 1000))
    os.utime(new_image, (2000, 2000))

    config = AppConfig(
        gallery_dir=tmp_path.resolve(),
        recursive=True,
        extensions=frozenset({"jpg", "png"}),
        frontend_dist=None,
    )
    app = create_app(config)
    return TestClient(app)


def test_health_endpoint() -> None:
    client = _build_client(_create_temp_dir())
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_images_endpoint_returns_sorted_images() -> None:
    client = _build_client(_create_temp_dir())
    response = client.get("/api/images")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert [item["rel_path"] for item in payload["items"]] == ["nested/new.png", "old.jpg"]


def test_media_endpoint_returns_image_file() -> None:
    client = _build_client(_create_temp_dir())
    response = client.get("/api/media/old.jpg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")


def test_media_endpoint_blocks_traversal() -> None:
    client = _build_client(_create_temp_dir())
    response = client.get("/api/media/%2E%2E/secret.jpg")
    assert response.status_code == 400
