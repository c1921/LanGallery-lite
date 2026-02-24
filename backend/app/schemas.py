from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str


class ImageItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    rel_path: str
    mtime: str
    size: int
    url: str
    thumb_url: str


class FolderCoverItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    rel_dir: str
    cover: ImageItem
    image_count: int
    latest_mtime: str


class FolderListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[FolderCoverItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class FolderInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rel_dir: str
    name: str
    total: int


class FolderImagesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    folder: FolderInfo
    items: list[ImageItem]


class IndexStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    last_built_at: str | None
    age_seconds: int | None
    building: bool
    image_count: int
    folder_count: int
