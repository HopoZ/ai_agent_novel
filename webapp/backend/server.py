"""
ASGI 入口模块：`uvicorn webapp.backend.server:app`

应用本体在 `app.py` 的 `create_app()`；此处保留 `app` 与测试所需的符号导出。
"""

from webapp.backend.app import app, create_app
from webapp.backend.run_helpers import infer_time_slot
from webapp.backend.schemas import RunModeRequest

# 测试沿用旧名
_infer_time_slot = infer_time_slot

__all__ = ["app", "create_app", "RunModeRequest", "_infer_time_slot"]
