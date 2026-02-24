from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from urllib.parse import quote

from PIL import Image, ImageOps, UnidentifiedImageError


class ThumbnailBuildError(RuntimeError):
    """Raised when a thumbnail cannot be generated."""


class ThumbnailService:
    def __init__(self, cache_dir: Path, default_size: int, quality: int) -> None:
        self._cache_dir = cache_dir
        self._default_size = default_size
        self._quality = quality
        self._locks_guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}

    def build_thumb_url(self, rel_path: str, size: int | None = None) -> str:
        actual_size = size if size is not None else self._default_size
        encoded = quote(rel_path, safe="/")
        return f"/api/thumb/{encoded}?size={actual_size}"

    def ensure_thumbnail(
        self,
        source_path: Path,
        rel_path: str,
        size: int | None = None,
    ) -> Path:
        target_size = size if size is not None else self._default_size
        if target_size < 1:
            raise ThumbnailBuildError("Thumbnail size must be positive.")

        stats = source_path.stat()
        cache_key = self._build_cache_key(
            rel_path=rel_path,
            size=target_size,
            quality=self._quality,
            source_size=stats.st_size,
            source_mtime_ns=stats.st_mtime_ns,
        )
        cache_path = self._cache_dir / cache_key[:2] / f"{cache_key}.jpg"

        if cache_path.exists():
            return cache_path

        lock = self._get_key_lock(cache_key)
        with lock:
            if cache_path.exists():
                return cache_path

            cache_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = cache_path.with_suffix(".tmp")
            try:
                with Image.open(source_path) as image:
                    image = ImageOps.exif_transpose(image)
                    if image.mode != "RGB":
                        image = image.convert("RGB")
                    image.thumbnail((target_size, target_size), Image.Resampling.LANCZOS)
                    image.save(
                        temp_path,
                        format="JPEG",
                        quality=self._quality,
                        optimize=True,
                    )
                temp_path.replace(cache_path)
            except (OSError, UnidentifiedImageError, ValueError) as exc:
                if temp_path.exists():
                    temp_path.unlink(missing_ok=True)
                raise ThumbnailBuildError(f"Failed to build thumbnail: {source_path}") from exc

        return cache_path

    def _build_cache_key(
        self,
        rel_path: str,
        size: int,
        quality: int,
        source_size: int,
        source_mtime_ns: int,
    ) -> str:
        payload = (
            f"{rel_path}|{size}|{quality}|{source_size}|{source_mtime_ns}".encode(
                "utf-8"
            )
        )
        return hashlib.sha256(payload).hexdigest()

    def _get_key_lock(self, key: str) -> threading.Lock:
        with self._locks_guard:
            existing = self._locks.get(key)
            if existing is not None:
                return existing
            lock = threading.Lock()
            self._locks[key] = lock
            return lock
