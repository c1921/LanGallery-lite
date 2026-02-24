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
    root_image = tmp_path / "root.jpg"
    album_new = tmp_path / "album" / "new.png"
    album_cover = tmp_path / "album" / "z-cover.jpg"
    trip = tmp_path / "trip" / "a.jpg"
    text = tmp_path / "doc.txt"

    _write_file(root_image, b"\xff\xd8\xff")
    _write_file(album_new, b"\x89PNG\r\n\x1a\n")
    _write_file(album_cover, b"\xff\xd8\xff")
    _write_file(trip, b"\xff\xd8\xff")
    _write_file(text, b"text")

    os.utime(root_image, (1000, 1000))
    os.utime(album_new, (3000, 3000))
    os.utime(album_cover, (2000, 2000))
    os.utime(trip, (2500, 2500))

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


def test_images_endpoint_returns_folder_covers_with_paging() -> None:
    client = _build_client(_create_temp_dir())
    response = client.get("/api/images?page=1&page_size=2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["page"] == 1
    assert payload["page_size"] == 2
    assert payload["total_pages"] == 2
    assert [item["rel_dir"] for item in payload["items"]] == ["album", "trip"]
    assert payload["items"][0]["cover"]["rel_path"] == "album/z-cover.jpg"
    assert payload["items"][0]["cover"]["thumb_url"].startswith("/api/thumb/")
    assert payload["items"][0]["image_count"] == 2


def test_folder_images_endpoint_returns_folder_images() -> None:
    client = _build_client(_create_temp_dir())
    response = client.get("/api/images/album")

    assert response.status_code == 200
    payload = response.json()
    assert payload["folder"]["rel_dir"] == "album"
    assert payload["folder"]["name"] == "album"
    assert payload["folder"]["total"] == 2
    assert [item["rel_path"] for item in payload["items"]] == [
        "album/new.png",
        "album/z-cover.jpg",
    ]
    assert payload["items"][0]["thumb_url"].startswith("/api/thumb/")


def test_images_endpoint_supports_refresh_param() -> None:
    client = _build_client(_create_temp_dir())
    response = client.get("/api/images?page=1&page_size=2&refresh=true")
    assert response.status_code == 200


def test_index_status_endpoint_returns_snapshot_status() -> None:
    client = _build_client(_create_temp_dir())
    response = client.get("/api/index/status")
    assert response.status_code == 200
    payload = response.json()
    assert "building" in payload
    assert "image_count" in payload
    assert "folder_count" in payload
    assert "age_seconds" in payload


def test_folder_images_endpoint_returns_404_for_missing_folder() -> None:
    client = _build_client(_create_temp_dir())
    response = client.get("/api/images/missing")
    assert response.status_code == 404


def test_folder_images_endpoint_supports_root_folder() -> None:
    client = _build_client(_create_temp_dir())
    response = client.get("/api/images/%2E")

    assert response.status_code == 200
    payload = response.json()
    assert payload["folder"]["rel_dir"] == "."
    assert payload["folder"]["name"] == "根目录"
    assert [item["rel_path"] for item in payload["items"]] == ["root.jpg"]


def test_media_endpoint_returns_image_file() -> None:
    client = _build_client(_create_temp_dir())
    response = client.get("/api/media/root.jpg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")


def test_thumb_endpoint_returns_image_file() -> None:
    client = _build_client(_create_temp_dir())
    response = client.get("/api/thumb/root.jpg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")


def test_media_endpoint_blocks_traversal() -> None:
    client = _build_client(_create_temp_dir())
    response = client.get("/api/media/%2E%2E/secret.jpg")
    assert response.status_code == 400


def test_thumb_endpoint_blocks_traversal() -> None:
    client = _build_client(_create_temp_dir())
    response = client.get("/api/thumb/%2E%2E/secret.jpg")
    assert response.status_code == 400


def test_folder_images_endpoint_blocks_traversal() -> None:
    client = _build_client(_create_temp_dir())
    response = client.get("/api/images/%2E%2E/secret")
    assert response.status_code == 400
