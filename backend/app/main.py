from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import AppConfig, DEFAULT_EXTENSIONS
from .gallery_service import InvalidMediaPathError, list_images, resolve_media_path
from .schemas import HealthResponse, ImageItem, ImageListResponse


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

    return AppConfig(
        gallery_dir=gallery_dir,
        recursive=bool(args.recursive),
        extensions=_parse_extensions(args.extensions),
        frontend_dist=frontend_dist,
    )


def create_app(config: AppConfig) -> FastAPI:
    app = FastAPI(title="LanGallery Lite", version="0.1.0")
    app.state.config = config

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

    @app.get("/api/images", response_model=ImageListResponse)
    def images() -> ImageListResponse:
        items = [
            ImageItem(
                id=image.id,
                name=image.name,
                rel_path=image.rel_path,
                mtime=image.mtime,
                size=image.size,
                url=image.url,
            )
            for image in list_images(config)
        ]
        return ImageListResponse(items=items, total=len(items))

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
