from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from .config import AppConfig


class InvalidMediaPathError(ValueError):
    """Raised when a media path escapes the configured gallery root."""


class InvalidFolderPathError(ValueError):
    """Raised when a folder path escapes the configured gallery root."""


@dataclass(frozen=True, slots=True)
class GalleryImage:
    id: str
    name: str
    rel_path: str
    mtime: str
    size: int
    url: str
    thumb_url: str


@dataclass(frozen=True, slots=True)
class GalleryFolderCover:
    id: str
    name: str
    rel_dir: str
    cover: GalleryImage
    image_count: int
    latest_mtime: str


@dataclass(frozen=True, slots=True)
class FolderCoverPage:
    items: list[GalleryFolderCover]
    total: int
    page: int
    page_size: int
    total_pages: int


@dataclass(frozen=True, slots=True)
class GalleryFolderImages:
    rel_dir: str
    name: str
    items: list[GalleryImage]


@dataclass(frozen=True, slots=True)
class GalleryIndexSnapshot:
    folders_ordered: list[GalleryFolderCover]
    images_by_folder: dict[str, list[GalleryImage]]
    images_ordered: list[GalleryImage]

    @property
    def folder_count(self) -> int:
        return len(self.folders_ordered)

    @property
    def image_count(self) -> int:
        return len(self.images_ordered)


@dataclass(frozen=True, slots=True)
class GalleryIndexStatus:
    last_built_at: str | None
    age_seconds: int | None
    building: bool
    image_count: int
    folder_count: int


def _iter_files(root: Path, recursive: bool):
    iterator = root.rglob("*") if recursive else root.glob("*")
    for path in iterator:
        if path.is_file():
            yield path


def _is_supported_image(path: Path, extensions: frozenset[str]) -> bool:
    suffix = path.suffix.lower().lstrip(".")
    return bool(suffix) and suffix in extensions


def _image_dir(rel_path: str) -> str:
    folder = Path(rel_path).parent.as_posix()
    return folder if folder not in ("", ".") else "."


def _folder_display_name(rel_dir: str) -> str:
    if rel_dir == ".":
        return "根目录"
    return Path(rel_dir).name


def _media_url(rel_path: str) -> str:
    return f"/api/media/{quote(rel_path, safe='/')}"


def _thumb_url(rel_path: str, size: int) -> str:
    return f"/api/thumb/{quote(rel_path, safe='/')}?size={size}"


def _default_thumb_builder(config: AppConfig) -> Callable[[str], str]:
    if not config.thumb_enabled:
        return _media_url

    size = max(1, int(config.thumb_size))
    return lambda rel_path: _thumb_url(rel_path, size)


def _scan_images(
    config: AppConfig,
    thumb_url_builder: Callable[[str], str] | None = None,
) -> list[tuple[float, GalleryImage]]:
    thumb_builder = thumb_url_builder or _default_thumb_builder(config)
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
            url=_media_url(rel_path),
            thumb_url=thumb_builder(rel_path),
        )
        records.append((stats.st_mtime, image))

    records.sort(key=lambda entry: entry[0], reverse=True)
    return records


def _build_snapshot(
    config: AppConfig,
    thumb_url_builder: Callable[[str], str] | None = None,
) -> GalleryIndexSnapshot:
    records = _scan_images(config, thumb_url_builder)

    groups: dict[str, list[tuple[float, GalleryImage]]] = {}
    for entry in records:
        rel_dir = _image_dir(entry[1].rel_path)
        groups.setdefault(rel_dir, []).append(entry)

    folders: list[tuple[float, GalleryFolderCover]] = []
    images_by_folder: dict[str, list[GalleryImage]] = {}
    for rel_dir, entries in groups.items():
        latest_entry = max(entries, key=lambda item: item[0])
        cover_image = max(entries, key=lambda item: (item[1].name, item[1].rel_path))[1]
        folder = GalleryFolderCover(
            id=rel_dir,
            name=_folder_display_name(rel_dir),
            rel_dir=rel_dir,
            cover=cover_image,
            image_count=len(entries),
            latest_mtime=latest_entry[1].mtime,
        )
        folders.append((latest_entry[0], folder))
        images_by_folder[rel_dir] = [item[1] for item in entries]

    folders.sort(key=lambda item: (-item[0], item[1].rel_dir))
    return GalleryIndexSnapshot(
        folders_ordered=[item[1] for item in folders],
        images_by_folder=images_by_folder,
        images_ordered=[entry[1] for entry in records],
    )


def _empty_snapshot() -> GalleryIndexSnapshot:
    return GalleryIndexSnapshot(
        folders_ordered=[],
        images_by_folder={},
        images_ordered=[],
    )


class GalleryIndexService:
    def __init__(
        self,
        config: AppConfig,
        ttl_seconds: int | None = None,
        thumb_url_builder: Callable[[str], str] | None = None,
    ) -> None:
        self._config = config
        self._ttl_seconds = max(1, ttl_seconds if ttl_seconds is not None else config.index_ttl_seconds)
        self._thumb_url_builder = thumb_url_builder or _default_thumb_builder(config)

        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._snapshot = _empty_snapshot()
        self._initialized = False
        self._building = False
        self._last_built_at: datetime | None = None
        self._last_built_monotonic: float | None = None

    def warmup_async(self) -> None:
        self._trigger_background_build(force=True)

    def list_folder_covers(
        self,
        page: int,
        page_size: int,
        refresh: bool = False,
    ) -> FolderCoverPage:
        if page < 1:
            raise ValueError("Page must be at least 1.")
        if page_size < 1:
            raise ValueError("Page size must be at least 1.")

        snapshot = self._ensure_snapshot(refresh=refresh)
        total = snapshot.folder_count
        total_pages = (total + page_size - 1) // page_size if total else 0
        start = (page - 1) * page_size
        end = start + page_size
        items = snapshot.folders_ordered[start:end] if start < total else []
        return FolderCoverPage(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    def list_folder_images(self, rel_dir: str, refresh: bool = False) -> GalleryFolderImages:
        resolved_dir = resolve_folder_path(self._config, rel_dir)
        snapshot = self._ensure_snapshot(refresh=refresh)
        items = snapshot.images_by_folder.get(resolved_dir, [])
        if not items:
            raise FileNotFoundError(resolved_dir)

        return GalleryFolderImages(
            rel_dir=resolved_dir,
            name=_folder_display_name(resolved_dir),
            items=items,
        )

    def list_images(self, refresh: bool = False) -> list[GalleryImage]:
        snapshot = self._ensure_snapshot(refresh=refresh)
        return snapshot.images_ordered

    def status(self) -> GalleryIndexStatus:
        with self._lock:
            age_seconds: int | None = None
            if self._last_built_monotonic is not None:
                age_seconds = int(max(0.0, time.monotonic() - self._last_built_monotonic))
            return GalleryIndexStatus(
                last_built_at=self._last_built_at.isoformat() if self._last_built_at else None,
                age_seconds=age_seconds,
                building=self._building,
                image_count=self._snapshot.image_count,
                folder_count=self._snapshot.folder_count,
            )

    def refresh_sync(self) -> None:
        self._build_sync()

    def _ensure_snapshot(self, refresh: bool) -> GalleryIndexSnapshot:
        if refresh:
            self._build_sync()
            with self._lock:
                return self._snapshot

        with self._lock:
            initialized = self._initialized
            expired = self._is_expired_locked()

        if not initialized:
            self._build_sync()
        elif expired:
            self._trigger_background_build(force=True)

        with self._lock:
            return self._snapshot

    def _is_expired_locked(self) -> bool:
        if not self._initialized:
            return True
        if self._last_built_monotonic is None:
            return True
        return (time.monotonic() - self._last_built_monotonic) >= self._ttl_seconds

    def _trigger_background_build(self, force: bool) -> None:
        with self._condition:
            if self._building:
                return
            if not force and not self._is_expired_locked():
                return
            self._building = True

        thread = threading.Thread(target=self._build_worker, daemon=True)
        thread.start()

    def _build_worker(self) -> None:
        snapshot: GalleryIndexSnapshot | None = None
        try:
            snapshot = _build_snapshot(self._config, self._thumb_url_builder)
        finally:
            with self._condition:
                if snapshot is not None:
                    self._snapshot = snapshot
                    self._initialized = True
                    self._last_built_at = datetime.now(timezone.utc)
                    self._last_built_monotonic = time.monotonic()
                self._building = False
                self._condition.notify_all()

    def _build_sync(self) -> None:
        with self._condition:
            while self._building:
                self._condition.wait()
            self._building = True

        snapshot: GalleryIndexSnapshot | None = None
        try:
            snapshot = _build_snapshot(self._config, self._thumb_url_builder)
        finally:
            with self._condition:
                if snapshot is not None:
                    self._snapshot = snapshot
                    self._initialized = True
                    self._last_built_at = datetime.now(timezone.utc)
                    self._last_built_monotonic = time.monotonic()
                self._building = False
                self._condition.notify_all()


def list_images(config: AppConfig) -> list[GalleryImage]:
    snapshot = _build_snapshot(config)
    return snapshot.images_ordered


def list_folder_covers(config: AppConfig, page: int, page_size: int) -> FolderCoverPage:
    if page < 1:
        raise ValueError("Page must be at least 1.")
    if page_size < 1:
        raise ValueError("Page size must be at least 1.")

    snapshot = _build_snapshot(config)
    total = snapshot.folder_count
    total_pages = (total + page_size - 1) // page_size if total else 0
    start = (page - 1) * page_size
    end = start + page_size
    items = snapshot.folders_ordered[start:end] if start < total else []

    return FolderCoverPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


def resolve_folder_path(config: AppConfig, rel_dir: str) -> str:
    normalized = rel_dir.replace("\\", "/").strip()
    normalized = normalized.strip("/")
    if normalized in ("", "."):
        normalized = "."

    candidate = (config.gallery_dir / Path(normalized)).resolve()

    try:
        candidate.relative_to(config.gallery_dir)
    except ValueError as exc:
        raise InvalidFolderPathError("Illegal folder path.") from exc

    if not candidate.is_dir():
        raise FileNotFoundError(candidate)

    resolved = candidate.relative_to(config.gallery_dir).as_posix()
    return resolved if resolved not in ("", ".") else "."


def list_folder_images(config: AppConfig, rel_dir: str) -> GalleryFolderImages:
    resolved_dir = resolve_folder_path(config, rel_dir)
    snapshot = _build_snapshot(config)
    items = snapshot.images_by_folder.get(resolved_dir, [])

    if not items:
        raise FileNotFoundError(resolved_dir)

    return GalleryFolderImages(
        rel_dir=resolved_dir,
        name=_folder_display_name(resolved_dir),
        items=items,
    )


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
