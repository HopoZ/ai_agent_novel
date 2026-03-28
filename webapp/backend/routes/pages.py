from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse

from webapp.backend.paths import LEGACY_INDEX_HTML, VITE_DIST_DIR

router = APIRouter(tags=["pages"])


@router.get("/", response_class=HTMLResponse)
def index():
    vite_index = VITE_DIST_DIR / "index.html"
    if vite_index.exists():
        return FileResponse(str(vite_index), media_type="text/html")
    return FileResponse(str(LEGACY_INDEX_HTML), media_type="text/html")
