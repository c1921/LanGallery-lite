from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_EXTENSIONS: frozenset[str] = frozenset(
    {"jpg", "jpeg", "png", "webp", "gif", "bmp"}
)


@dataclass(frozen=True, slots=True)
class AppConfig:
    gallery_dir: Path
    recursive: bool
    extensions: frozenset[str]
    frontend_dist: Path | None = None
