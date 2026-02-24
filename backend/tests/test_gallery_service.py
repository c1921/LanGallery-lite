from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.config import AppConfig
from backend.app.gallery_service import (
    GalleryIndexService,
    InvalidFolderPathError,
    InvalidMediaPathError,
    list_folder_covers,
    list_folder_images,
    list_images,
    resolve_folder_path,
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


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def test_list_images_recursive_and_sorted_lexicographically() -> None:
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

    assert [item.rel_path for item in images] == ["nested/older.png", "newer.jpg"]
    assert images[0].url == "/api/media/nested/older.png"


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


def test_list_folder_covers_supports_paging_and_cover_selection() -> None:
    tmp_path = _create_temp_dir()

    root_a = tmp_path / "root-a.jpg"
    root_b = tmp_path / "root-b.jpg"
    album_new = tmp_path / "album" / "newer.jpg"
    album_cover = tmp_path / "album" / "z-last.jpg"
    trip = tmp_path / "trip" / "a.jpg"

    _write_file(root_a, b"\xff\xd8\xff")
    _write_file(root_b, b"\xff\xd8\xff")
    _write_file(album_new, b"\xff\xd8\xff")
    _write_file(album_cover, b"\xff\xd8\xff")
    _write_file(trip, b"\xff\xd8\xff")

    os.utime(root_a, (1100, 1100))
    os.utime(root_b, (1000, 1000))
    os.utime(album_new, (3000, 3000))
    os.utime(album_cover, (2000, 2000))
    os.utime(trip, (2500, 2500))

    config = AppConfig(
        gallery_dir=tmp_path.resolve(),
        recursive=True,
        extensions=frozenset({"jpg"}),
    )

    first_page = list_folder_covers(config=config, page=1, page_size=2)
    assert first_page.total == 3
    assert first_page.total_pages == 2
    assert [item.rel_dir for item in first_page.items] == [".", "album"]
    assert first_page.items[0].cover.rel_path == "root-b.jpg"
    assert first_page.items[1].cover.rel_path == "album/z-last.jpg"
    assert first_page.items[1].latest_mtime == _iso(3000)

    second_page = list_folder_covers(config=config, page=2, page_size=2)
    assert [item.rel_dir for item in second_page.items] == ["trip"]
    assert second_page.items[0].cover.rel_path == "trip/a.jpg"


def test_list_folder_images_returns_images_from_target_folder() -> None:
    tmp_path = _create_temp_dir()
    old_image = tmp_path / "album" / "old.jpg"
    new_image = tmp_path / "album" / "new.jpg"
    other = tmp_path / "other" / "x.jpg"
    _write_file(old_image, b"\xff\xd8\xff")
    _write_file(new_image, b"\xff\xd8\xff")
    _write_file(other, b"\xff\xd8\xff")

    os.utime(old_image, (3000, 3000))
    os.utime(new_image, (1000, 1000))
    os.utime(other, (2000, 2000))

    config = AppConfig(
        gallery_dir=tmp_path.resolve(),
        recursive=True,
        extensions=frozenset({"jpg"}),
    )

    folder = list_folder_images(config, "album")
    assert folder.rel_dir == "album"
    assert folder.name == "album"
    assert [item.rel_path for item in folder.items] == ["album/new.jpg", "album/old.jpg"]


def test_resolve_folder_path_and_list_folder_images_block_traversal() -> None:
    tmp_path = _create_temp_dir()
    image = tmp_path / "safe" / "safe.jpg"
    _write_file(image, b"\xff\xd8\xff")

    config = AppConfig(
        gallery_dir=tmp_path.resolve(),
        recursive=True,
        extensions=frozenset({"jpg"}),
    )

    assert resolve_folder_path(config, ".") == "."
    with pytest.raises(InvalidFolderPathError):
        resolve_folder_path(config, "../safe")
    with pytest.raises(FileNotFoundError):
        list_folder_images(config, "missing")


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


def test_gallery_index_service_uses_cached_snapshot_until_force_refresh() -> None:
    tmp_path = _create_temp_dir()
    image = tmp_path / "album" / "a.jpg"
    _write_file(image, b"\xff\xd8\xff")
    os.utime(image, (1000, 1000))

    config = AppConfig(
        gallery_dir=tmp_path.resolve(),
        recursive=True,
        extensions=frozenset({"jpg"}),
        index_ttl_seconds=3600,
    )

    service = GalleryIndexService(config=config, ttl_seconds=3600)
    first = service.list_folder_covers(page=1, page_size=50)
    assert first.total == 1

    image.unlink()

    cached = service.list_folder_covers(page=1, page_size=50)
    assert cached.total == 1

    refreshed = service.list_folder_covers(page=1, page_size=50, refresh=True)
    assert refreshed.total == 0


def test_gallery_index_service_status_fields() -> None:
    tmp_path = _create_temp_dir()
    image = tmp_path / "a.jpg"
    _write_file(image, b"\xff\xd8\xff")

    config = AppConfig(
        gallery_dir=tmp_path.resolve(),
        recursive=True,
        extensions=frozenset({"jpg"}),
    )
    service = GalleryIndexService(config=config)
    service.list_folder_covers(page=1, page_size=10)
    status = service.status()

    assert status.image_count == 1
    assert status.folder_count == 1
    assert status.last_built_at is not None
