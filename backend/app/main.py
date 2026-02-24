from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import AppConfig, DEFAULT_EXTENSIONS
from .gallery_service import (
    GalleryIndexService,
    InvalidFolderPathError,
    InvalidMediaPathError,
    resolve_media_path,
)
from .schemas import (
    FolderCoverItem,
    FolderImagesResponse,
    FolderInfo,
    FolderListResponse,
    HealthResponse,
    ImageItem,
    IndexStatusResponse,
)
from .thumb_service import ThumbnailBuildError, ThumbnailService


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    default_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    parser = argparse.ArgumentParser(description="LanGallery Lite")
    parser.add_argument("--gallery-dir", required=True, help="Local image folder.")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind.")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind.")
    parser.add_argument(
        "--recursive",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Recursively scan subfolders.",
    )
    parser.add_argument(
        "--extensions",
        default=",".join(sorted(DEFAULT_EXTENSIONS)),
        help="Comma-separated allowed image extensions.",
    )
    parser.add_argument(
        "--frontend-dist",
        default=str(default_dist),
        help="Built frontend dist directory.",
    )
    parser.add_argument(
        "--index-ttl-seconds",
        type=int,
        default=60,
        help="Max age in seconds before index refresh is triggered.",
    )
    parser.add_argument(
        "--thumb-enabled",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable disk thumbnail cache.",
    )
    parser.add_argument(
        "--thumb-cache-dir",
        default=None,
        help="Thumbnail cache directory. Defaults to <gallery>/.cache/thumbs.",
    )
    parser.add_argument(
        "--thumb-size",
        type=int,
        default=1080,
        help="Default thumbnail max edge size.",
    )
    parser.add_argument(
        "--thumb-quality",
        type=int,
        default=82,
        help="JPEG thumbnail quality.",
    )
    return parser.parse_args(argv)


def _parse_extensions(raw: str) -> frozenset[str]:
    values = {item.strip().lower().lstrip(".") for item in raw.split(",") if item.strip()}
    if not values:
        raise ValueError("No valid image extension configured.")
    return frozenset(values)


def build_config(args: argparse.Namespace) -> AppConfig:
    gallery_dir = Path(args.gallery_dir).expanduser().resolve()
    if not gallery_dir.is_dir():
        raise ValueError(f"Gallery directory does not exist: {gallery_dir}")

    frontend_dist = Path(args.frontend_dist).expanduser().resolve()
    if not frontend_dist.is_dir():
        frontend_dist = None

    if args.index_ttl_seconds < 1:
        raise ValueError("Index TTL must be >= 1 second.")
    if args.thumb_size < 1:
        raise ValueError("Thumbnail size must be >= 1.")
    if not (1 <= args.thumb_quality <= 100):
        raise ValueError("Thumbnail quality must be between 1 and 100.")

    thumb_cache_dir = (
        Path(args.thumb_cache_dir).expanduser().resolve()
        if args.thumb_cache_dir
        else (gallery_dir / ".cache" / "thumbs")
    )

    return AppConfig(
        gallery_dir=gallery_dir,
        recursive=bool(args.recursive),
        extensions=_parse_extensions(args.extensions),
        frontend_dist=frontend_dist,
        index_ttl_seconds=args.index_ttl_seconds,
        thumb_enabled=bool(args.thumb_enabled),
        thumb_cache_dir=thumb_cache_dir,
        thumb_size=args.thumb_size,
        thumb_quality=args.thumb_quality,
    )


def create_app(config: AppConfig) -> FastAPI:
    app = FastAPI(title="LanGallery Lite", version="0.1.0")
    app.state.config = config

    thumb_service = ThumbnailService(
        cache_dir=(config.thumb_cache_dir or (config.gallery_dir / ".cache" / "thumbs")),
        default_size=config.thumb_size,
        quality=config.thumb_quality,
    )
    index_service = GalleryIndexService(
        config=config,
        ttl_seconds=config.index_ttl_seconds,
        thumb_url_builder=(thumb_service.build_thumb_url if config.thumb_enabled else None),
    )
    index_service.warmup_async()
    app.state.index_service = index_service
    app.state.thumb_service = thumb_service

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get("/api/index/status", response_model=IndexStatusResponse)
    def index_status() -> IndexStatusResponse:
        status = index_service.status()
        return IndexStatusResponse(
            last_built_at=status.last_built_at,
            age_seconds=status.age_seconds,
            building=status.building,
            image_count=status.image_count,
            folder_count=status.folder_count,
        )

    @app.get("/api/images", response_model=FolderListResponse)
    def images(
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=200),
        refresh: bool = Query(default=False),
    ) -> FolderListResponse:
        folder_page = index_service.list_folder_covers(
            page=page,
            page_size=page_size,
            refresh=refresh,
        )
        items = [
            FolderCoverItem(
                id=folder.id,
                name=folder.name,
                rel_dir=folder.rel_dir,
                cover=ImageItem(
                    id=folder.cover.id,
                    name=folder.cover.name,
                    rel_path=folder.cover.rel_path,
                    mtime=folder.cover.mtime,
                    size=folder.cover.size,
                    url=folder.cover.url,
                    thumb_url=folder.cover.thumb_url,
                ),
                image_count=folder.image_count,
                latest_mtime=folder.latest_mtime,
            )
            for folder in folder_page.items
        ]
        return FolderListResponse(
            items=items,
            total=folder_page.total,
            page=folder_page.page,
            page_size=folder_page.page_size,
            total_pages=folder_page.total_pages,
        )

    @app.get("/api/images/{rel_dir:path}", response_model=FolderImagesResponse)
    def folder_images(
        rel_dir: str,
        refresh: bool = Query(default=False),
    ) -> FolderImagesResponse:
        try:
            folder = index_service.list_folder_images(rel_dir, refresh=refresh)
        except InvalidFolderPathError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Folder not found.") from exc

        items = [
            ImageItem(
                id=image.id,
                name=image.name,
                rel_path=image.rel_path,
                mtime=image.mtime,
                size=image.size,
                url=image.url,
                thumb_url=image.thumb_url,
            )
            for image in folder.items
        ]
        return FolderImagesResponse(
            folder=FolderInfo(
                rel_dir=folder.rel_dir,
                name=folder.name,
                total=len(items),
            ),
            items=items,
        )

    @app.get("/api/thumb/{rel_path:path}")
    def thumb(
        rel_path: str,
        size: int | None = Query(default=None, ge=64, le=2048),
    ):
        try:
            source_path = resolve_media_path(config, rel_path)
        except InvalidMediaPathError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Image not found.") from exc

        if not config.thumb_enabled:
            return FileResponse(source_path)

        rel = source_path.relative_to(config.gallery_dir).as_posix()
        try:
            thumb_path = thumb_service.ensure_thumbnail(
                source_path=source_path,
                rel_path=rel,
                size=size,
            )
        except ThumbnailBuildError:
            return FileResponse(source_path)

        return FileResponse(thumb_path, media_type="image/jpeg")

    @app.get("/api/media/{rel_path:path}")
    def media(rel_path: str):
        try:
            path = resolve_media_path(config, rel_path)
        except InvalidMediaPathError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Image not found.") from exc
        return FileResponse(path)

    if config.frontend_dist is not None:
        app.mount("/", StaticFiles(directory=config.frontend_dist, html=True), name="frontend")
    else:

        @app.get("/", include_in_schema=False)
        def root_info() -> JSONResponse:
            return JSONResponse(
                {
                    "message": "Frontend dist not found. Run `npm run build` in frontend.",
                    "api": "/api/images",
                }
            )

    return app


def run(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    config = build_config(args)
    app = create_app(config)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    run()
