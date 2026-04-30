# PyInstaller 打包后端（Windows）

目标：生成 **`novel-backend.exe`**，复制到 **`electron/resources/backend/`**，再执行 `cd electron && npm run dist`。这样安装包可在无 Python 的机器上由 Electron 启动该 exe。

端到端发布（含一键脚本）见 **[`electron/ELECTRON_RELEASE.md`](../../electron/ELECTRON_RELEASE.md)**。

## 1. 环境

- 与主项目相同的 Python 3.11+ 虚拟环境
- `pip install -r requirements.txt`
- `pip install pyinstaller`

## 2. 入口脚本

- `run_uvicorn.py`：旧版 HTTP 端口模式（`uvicorn webapp.backend.server:app`）。
- `run_ipc_worker.py`：IPC 模式（Named Pipe worker，由 Electron 主进程通过 `NOVEL_AGENT_PIPE_PATH` 连接）。

## 3. 推荐命令（按报错补全 hidden-import）

在**仓库根目录**（HTTP 旧链路）：

```bash
pyinstaller --noconfirm --clean --onefile --name novel-backend ^
  packaging/pyinstaller/run_uvicorn.py ^
  --paths . ^
  --add-data "webapp/frontend/dist;webapp/frontend/dist" ^
  --add-data "webapp/static;webapp/static" ^
  --add-data "webapp/templates;webapp/templates" ^
  --collect-all uvicorn ^
  --collect-all fastapi ^
  --collect-all starlette ^
  --collect-all pydantic ^
  --collect-submodules agents ^
  --collect-submodules webapp
```

若打包 IPC worker（当前 Electron IPC 分支推荐），可将入口改为：

```bash
pyinstaller --noconfirm --clean --onefile --name novel-backend ^
  packaging/pyinstaller/run_ipc_worker.py ^
  --paths . ^
  --add-data "webapp/frontend/dist;webapp/frontend/dist" ^
  --add-data "webapp/static;webapp/static" ^
  --add-data "webapp/templates;webapp/templates" ^
  --collect-all fastapi ^
  --collect-all starlette ^
  --collect-all pydantic ^
  --collect-submodules agents ^
  --collect-submodules webapp
```

**必须**包含 **`--collect-submodules webapp`**：无论是 `run_uvicorn.py` 还是 `run_ipc_worker.py`，都要动态导入 `webapp.backend.*`，PyInstaller 静态分析易漏收；缺失时会报 `ModuleNotFoundError: No module named 'webapp.backend'`（进程立刻以 code=1 退出）。

若曾出现 **`RuntimeError: Directory 'webapp/static' does not exist`**：仓库里 **`webapp/static`** 为空目录时，`--add-data` 可能无法收录；当前已在 **`webapp/backend/app.py`** 启动时 **`mkdir`** 补目录，也可在 `webapp/static`、`webapp/templates` 放占位文件（如 `README.txt`）。

LangChain、agents 等子模块若报缺失，请追加 `--hidden-import=...` 或 `--collect-submodules agents`。

成功后把 `dist/novel-backend.exe` 复制到 **`electron/resources/backend/novel-backend.exe`**。

## 4. 运行时

入口脚本在 PyInstaller 冻结模式下都会将 **`os.chdir(sys._MEIPASS)`**，否则 Electron 子进程 `cwd` 为 `resources/backend`，相对路径 `webapp/static` 等不存在，进程会立刻退出、界面不出现。

Electron 会设置：

- `NOVEL_AGENT_STORAGE_DIR` → Electron 安装版为 **`<主程序 exe 同目录>/data`**（其下含 `lores/`、`outputs/`、`novels/` 等）；未单独设置时 **`NOVEL_AGENT_OUTPUTS_DIR`** 为 `STORAGE_DIR/outputs`  
- `SKIP_FRONTEND_BUILD=1`  
- `NOVEL_AGENT_PIPE_PATH`（IPC worker 模式必须）  
- `NOVEL_AGENT_PORT`（仅 `run_uvicorn.py` HTTP 模式使用）

## 5. 说明

- 单文件 exe 体积可能较大；首次冷启动较慢是正常现象。  
- 若 PyInstaller 与项目依赖冲突，可改为 **目录模式**（`--onedir`）并在 Electron 里指向 `novel-backend.exe` 路径。
