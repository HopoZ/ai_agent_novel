# 做成 Electron 安装包并发 GitHub Release

目标：在 Windows 上得到 **NSIS 一键安装程序**（如 `AI Novel Agent-1.0.0-Setup.exe`），上传到 **GitHub Releases**，用户无需安装 Python。

---

## 1. 你需要什么

- **本机**：Node.js 18+、Python 3.11+（与 `requirements.txt` 一致）、已 `pip install -r requirements.txt` 与 `pip install pyinstaller`。
- **仓库**：克隆完整源码（含 `webapp/`、`agents/`、`electron/`、`packaging/pyinstaller/`）。

---

## 2. 一键构建（推荐）

在**仓库根目录**：

```powershell
.\build-windows-release.bat
```

或：

```powershell
.\scripts\build-windows-release.ps1
```

脚本顺序：**构建 Vue 前端** → **PyInstaller 生成 `novel-backend.exe`** → 复制到 **`electron/resources/backend/`** → **electron-builder 打 NSIS 安装包**。

**产物目录**：`electron/release/`  
典型文件：`AI Novel Agent-<version>-Setup.exe`（名称见 `electron/package.json` 的 `version`、`productName`）。

仅重打 Electron、不重做 PyInstaller 时：

```powershell
.\scripts\build-windows-release.ps1 -SkipPyInstaller
```

---

## 3. 发 GitHub Release

1. 在仓库页 **Releases** → **Draft a new release**。
2. 填 Tag / 标题 / 说明。
3. **上传** `electron/release/` 里生成的 **`*-Setup.exe`**（及可选 `.blockmap` 若你用自动更新）。
4. **不要**把 `novel-backend.exe`、`electron/release/`、根目录 `dist/` 等提交进 Git（已在 **`.gitignore`** 中忽略）；只把**安装包**作为 Release 附件。

---

## 4. 安装版运行时数据放哪

主程序 **`AI Novel Agent.exe`** 同级的 **`data/`** 目录（由 Electron 设置 `NOVEL_AGENT_STORAGE_DIR`）：

- `data/lores/` — 设定 `.md`
- `data/outputs/` — 生成正文与调试落盘
- `data/novels/<uuid>/novel.db` — SQLite
- `data/user_settings.json` — Web 里保存的 API 密钥等
- `data/novel-backend.log` — 后端日志

详见 **`electron/README.md`**。

---

## 5. 常见坑（备忘）

| 现象 | 原因与处理 |
|------|------------|
| 后端秒退 code=1 | PyInstaller 未打 **`--collect-submodules webapp`** → `ModuleNotFoundError: webapp.backend`。脚本已包含；勿删。 |
| `webapp/static` 不存在 | 空目录未进包；**`webapp/backend/app.py`** 启动时会 `mkdir`；仓库里已有占位 **`webapp/static/README.txt`**。 |
| 调试文件找不到 | 曾写相对路径 **`outputs/`**；已改为 **`get_outputs_root()`**，与 **`data/outputs`** 一致。 |
| 等 120s 才超时 | 后端未监听；看 **`data/novel-backend.log`**。 |
| Electron 下载慢 | 设 **`ELECTRON_MIRROR`**（见 **`electron/README.md`**）。 |
| NSIS 配置报错 | `oneClick` 与 `allowToChangeInstallationDirectory` 冲突；当前 **`package.json`** 已改为 **`oneClick: false`**。 |

---

## 6. 与「只开发 Python / Web」的关系

不设 **`NOVEL_AGENT_STORAGE_DIR`** 时，行为与以前一致：仓库根 **`lores/`**、**`outputs/`**、**`storage/`**。Electron 安装版才注入环境变量。

---

## 7. 相关文件索引

| 路径 | 作用 |
|------|------|
| `build-windows-release.bat` | 根目录一键入口 |
| `scripts/build-windows-release.ps1` | 完整构建脚本 |
| `electron/package.json` | `dist` / `dist:dir`、`electron-builder`、NSIS |
| `electron/src/main/index.ts` | 启动后端、`data/` 路径、日志、`shell.openPath` |
| `packaging/pyinstaller/run_uvicorn.py` | 冻结时 **`chdir(_MEIPASS)`** |
| `agents/persistence/env_paths.py` | `STORAGE` / `OUTPUTS` / lores 解析 |
