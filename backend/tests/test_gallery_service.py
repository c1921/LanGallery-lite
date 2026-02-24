from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.config import AppConfig
from backend.app.gallery_service import (
    InvalidMediaPathError,
    list_images,
    resolve_media_path,
)


def _write_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _create_temp_dir() -> Path:
    root = Path(".test-work")
    root.mkdir(exist_ok=True)
    temp_dir = root / uuid4().hex
    temp_dir.mkdir(parents=True, exist_ok=False)
    return temp_dir


def test_list_images_recursive_and_sorted_by_mtime() -> None:
    tmp_path = _create_temp_dir()
    newer = tmp_path / "newer.jpg"
    older = tmp_path / "nested" / "older.png"
    ignored = tmp_path / "nested" / "note.txt"

    _write_file(newer, b"\xff\xd8\xff")
    _write_file(older, b"\x89PNG\r\n\x1a\n")
    _write_file(ignored, b"ignore")

    os.utime(older, (1000, 1000))
    os.utime(newer, (2000, 2000))

    config = AppConfig(
        gallery_dir=tmp_path.resolve(),
        recursive=True,
        extensions=frozenset({"jpg", "png"}),
    )
    images = list_images(config)

    assert [item.rel_path for item in images] == ["newer.jpg", "nested/older.png"]
    assert images[0].url == "/api/media/newer.jpg"


def test_list_images_non_recursive() -> None:
    tmp_path = _create_temp_dir()
    top = tmp_path / "top.jpg"
    nested = tmp_path / "nested" / "inside.jpg"
    _write_file(top, b"\xff\xd8\xff")
    _write_file(nested, b"\xff\xd8\xff")

    config = AppConfig(
        gallery_dir=tmp_path.resolve(),
        recursive=False,
        extensions=frozenset({"jpg"}),
    )
    images = list_images(config)

    assert [item.rel_path for item in images] == ["top.jpg"]


def test_resolve_media_path_blocks_traversal() -> None:
    tmp_path = _create_temp_dir()
    image = tmp_path / "safe.jpg"
    _write_file(image, b"\xff\xd8\xff")

    config = AppConfig(
        gallery_dir=tmp_path.resolve(),
        recursive=True,
        extensions=frozenset({"jpg"}),
    )

    with pytest.raises(InvalidMediaPathError):
        resolve_media_path(config, "../safe.jpg")
