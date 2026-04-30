"""PyInstaller 入口：启动 Named Pipe IPC worker（供 Electron 主进程连接）。"""

from __future__ import annotations

import os
import sys


def _bootstrap_pyinstaller_cwd() -> None:
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None)
        if base:
            os.chdir(base)


def main() -> None:
    _bootstrap_pyinstaller_cwd()
    os.environ.setdefault("SKIP_FRONTEND_BUILD", "1")
    from webapp.backend.ipc_pipe_worker import main as worker_main

    raise SystemExit(worker_main())


if __name__ == "__main__":
    main()
