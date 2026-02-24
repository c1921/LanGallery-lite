from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from .config import AppConfig


class InvalidMediaPathError(ValueError):
    """Raised when a media path escapes the configured gallery root."""


@dataclass(frozen=True, slots=True)
class GalleryImage:
    id: str
    name: str
    rel_path: str
    mtime: str
    size: int
    url: str


def _iter_files(root: Path, recursive: bool):
    iterator = root.rglob("*") if recursive else root.glob("*")
    for path in iterator:
        if path.is_file():
            yield path


def _is_supported_image(path: Path, extensions: frozenset[str]) -> bool:
    suffix = path.suffix.lower().lstrip(".")
    return bool(suffix) and suffix in extensions


def list_images(config: AppConfig) -> list[GalleryImage]:
    records: list[tuple[float, GalleryImage]] = []

    for file_path in _iter_files(config.gallery_dir, config.recursive):
        if not _is_supported_image(file_path, config.extensions):
            continue

        stats = file_path.stat()
        rel_path = file_path.relative_to(config.gallery_dir).as_posix()
        image = GalleryImage(
            id=rel_path,
            name=file_path.name,
            rel_path=rel_path,
            mtime=datetime.fromtimestamp(
                stats.st_mtime, tz=timezone.utc
            ).isoformat(),
            size=stats.st_size,
            url=f"/api/media/{quote(rel_path, safe='/')}",
        )
        records.append((stats.st_mtime, image))

    records.sort(key=lambda entry: entry[0], reverse=True)
    return [entry[1] for entry in records]


def resolve_media_path(config: AppConfig, rel_path: str) -> Path:
    normalized = rel_path.replace("\\", "/")
    candidate = (config.gallery_dir / Path(normalized)).resolve()

    try:
        candidate.relative_to(config.gallery_dir)
    except ValueError as exc:
        raise InvalidMediaPathError("Illegal media path.") from exc

    if not candidate.is_file():
        raise FileNotFoundError(candidate)

    if not _is_supported_image(candidate, config.extensions):
        raise FileNotFoundError(candidate)

    return candidate
