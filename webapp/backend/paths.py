"""与仓库根目录相对的路径常量（启动工作目录应为项目根）。"""

from pathlib import Path

VITE_FRONTEND_DIR = Path("webapp/frontend")
VITE_DIST_DIR = VITE_FRONTEND_DIR / "dist"
LEGACY_INDEX_HTML = Path("webapp/templates/index.html")
STORAGE_NOVELS_DIR = Path("storage") / "novels"
