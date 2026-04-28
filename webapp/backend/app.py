"""
FastAPI 应用工厂：中间件、静态资源、子路由挂载。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from webapp.backend.frontend_assets import run_frontend_startup
from webapp.backend.paths import VITE_DIST_DIR, VITE_FRONTEND_DIR
from webapp.backend.routes import graph, lore, novels, pages, settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("webapp.backend.server")


def _ensure_packaged_relative_dirs() -> None:
    """
    PyInstaller 对空目录的 --add-data 可能不产生 webapp/static，Starlette StaticFiles 会报
    Directory does not exist。启动时补建相对路径目录（cwd 在冻结模式下已为 _MEIPASS）。
    """
    for rel in ("webapp/static", "webapp/templates"):
        Path(rel).mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    run_frontend_startup(app, logger, VITE_FRONTEND_DIR, VITE_DIST_DIR)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="AI Novel Agent", lifespan=_lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _ensure_packaged_relative_dirs()
    app.mount("/static", StaticFiles(directory="webapp/static"), name="static")

    @app.middleware("http")
    async def log_http_requests(request: Request, call_next):
        query = request.url.query
        logger.info("REQ %s %s%s", request.method, request.url.path, (("?" + query) if query else ""))
        try:
            response = await call_next(request)
            logger.info("RES %s %s -> %s", request.method, request.url.path, response.status_code)
            return response
        except Exception:
            logger.exception("ERR %s %s", request.method, request.url.path)
            raise

    app.include_router(pages.router)
    app.include_router(settings.router, prefix="/api")
    app.include_router(lore.router, prefix="/api/lore")
    app.include_router(novels.router, prefix="/api/novels")
    app.include_router(graph.router, prefix="/api/novels")

    return app


app = create_app()