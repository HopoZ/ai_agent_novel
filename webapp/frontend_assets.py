from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


def frontend_need_rebuild(frontend_dir: Path, dist_dir: Path) -> bool:
    # 可通过环境变量跳过构建
    if str(os.getenv("SKIP_FRONTEND_BUILD", "")).lower() in {"1", "true", "yes"}:
        return False

    dist_index = dist_dir / "index.html"
    if not dist_index.exists():
        return True

    src_dir = frontend_dir / "src"
    if not src_dir.exists():
        return False

    latest_src_mtime = 0.0
    for p in src_dir.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in {".ts", ".tsx", ".js", ".jsx", ".vue", ".css", ".scss", ".html", ".json"}:
            continue
        latest_src_mtime = max(latest_src_mtime, p.stat().st_mtime)

    return latest_src_mtime > dist_index.stat().st_mtime


def mount_vite_assets_if_needed(app: FastAPI, dist_dir: Path) -> None:
    assets_dir = dist_dir / "assets"
    if not assets_dir.exists():
        return
    for r in app.routes:
        if getattr(r, "path", None) == "/assets":
            return
    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="vite_assets")


def run_frontend_startup(app: FastAPI, logger: Any, frontend_dir: Path, dist_dir: Path) -> None:
    if frontend_need_rebuild(frontend_dir, dist_dir):
        if not frontend_dir.exists():
            logger.warning("Frontend dir not found: %s", frontend_dir)
        else:
            logger.info("Frontend dist is stale, running npm build...")
            try:
                import subprocess

                npm_bin = "npm.cmd" if os.name == "nt" else "npm"
                if not shutil.which(npm_bin):
                    fallback = "npm"
                    npm_bin = fallback if shutil.which(fallback) else ""
                if not npm_bin:
                    logger.warning("npm executable not found in PATH, skip auto frontend build.")
                else:
                    subprocess.run([npm_bin, "run", "build"], cwd=str(frontend_dir), check=True)
                    logger.info("Frontend build finished.")
            except Exception as e:
                logger.exception("Frontend build failed: %s", e)
    else:
        logger.info("Frontend dist is up-to-date, skip build.")

    mount_vite_assets_if_needed(app, dist_dir)

