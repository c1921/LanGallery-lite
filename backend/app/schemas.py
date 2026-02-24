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


class ImageListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[ImageItem]
    total: int
