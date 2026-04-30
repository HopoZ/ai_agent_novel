# Electron 桌面端

使用 **[electron-vite](https://electron-vite.org/)** 构建 main / preload，使用 **[electron-builder](https://www.electron.build/)** 在 Windows 上打出 **NSIS 一键安装包**（`.exe`）或**免安装目录**。

发 **GitHub Release** 的步骤摘要见同目录 **[`ELECTRON_RELEASE.md`](./ELECTRON_RELEASE.md)**（本文件为参数与排错细表）。

## 前置条件

- **Node.js 18+**
- **开发 / 源码模式**：仓库根目录已执行 `pip install -r requirements.txt`
- **安装 Electron 慢或失败**：可设镜像后再 `npm install`：

  ```text
  set ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/
  ```

## 日常开发

在 **`electron/`** 目录：

```bash
npm install
npm run dev
```

前端仍可在仓库 `webapp/frontend` 用 `npm run dev`；Electron 负责拉起后端 worker、加载页面并桥接 IPC。

## IPC 架构（Named Pipe）

当前分支使用 IPC 调用链：

- Electron 主进程不再依赖 `http://127.0.0.1:8000` 承载页面；
- 页面默认加载 `webapp/frontend/dist/index.html`（可用 `NOVEL_AGENT_FRONTEND_URL` 覆盖）；
- 前端 API 调用改为 `preload -> ipcMain -> Named Pipe -> Python worker`；
- Python worker 入口：`webapp.backend.ipc_pipe_worker`。

说明：主进程支持“优先内置 `novel-backend.exe`，否则回退 Python 源码启动”两种路径，二者都走 IPC worker 协议。

## 发布 Release（推荐：仓库根目录脚本）

在 **仓库根目录**（PowerShell）执行，会依次完成：**构建 Vue 前端 -> PyInstaller 生成 `novel-backend.exe` -> 复制到 `electron/resources/backend/` -> 打 NSIS 安装包**。产物在 **`electron/release/`**，例如 **`AI Novel Agent-1.0.0-Setup.exe`**，可上传到 GitHub Releases。

```powershell
.\scripts\build-windows-release.ps1
```

- 若 **`novel-backend.exe` 已就绪**，只想重打 Electron 壳：**`.\scripts\build-windows-release.ps1 -SkipPyInstaller`**
- 若前端 **`webapp/frontend/dist` 已构建**，可：**`-SkipFrontendBuild`**
- PyInstaller 报错缺模块时，按终端提示在脚本里追加参数，或参考 **`packaging/pyinstaller/README.md`** 手工补全后重跑。

安装程序为 **NSIS 向导**（可选择安装目录）；与 `allowToChangeInstallationDirectory` 搭配时 **`oneClick` 需为 `false`**（见 `electron/package.json`）。

## 一键安装包（仅 Electron）

在 **`electron/`** 目录：

```bash
npm install
npm run dist
```

| 产物 | 路径 |
|------|------|
| 安装程序 | **`electron/release/`**，例如 **`AI Novel Agent-1.0.0-Setup.exe`** |
| 仅免安装目录（用于快速验证） | 使用下面的 `dist:dir`，输出在 **`electron/release/win-unpacked/`**，运行 **`AI Novel Agent.exe`** |

仅生成免安装目录：

```bash
npm run dist:dir
```

### Windows 打包注意

- **`signAndEditExecutable: false`**（见 `package.json`）：避免在未开启「创建符号链接」等权限时，electron-builder 拉取 **winCodeSign** 失败。
- 若仍与签名/缓存有关，可设：**`set CSC_IDENTITY_AUTO_DISCOVERY=false`**
- 若需正式分发签名，请在有证书的环境自行调整 `electron-builder` 配置；当前仓库默认关闭自动签名，便于本机打包。
- 未配置应用图标时，安装包可能使用默认 Electron 图标；可在 `build` / `buildResources` 下补充 `icon.ico` 等资源。

## 安装版里「后端」从哪来？

安装包里的主进程会**优先**启动内置的 **`novel-backend.exe`**（若存在）；否则再尝试本机 **`py` / `python`** 启动 IPC worker。安装版只注入 **`NOVEL_AGENT_STORAGE_DIR`**，指向 **单一应用数据根目录**（实现见 **`agents/persistence/env_paths.py`**：`outputs/`、`lores/`、`novels/`、`user_settings.json` 均在该根下）。

### 安装版：数据与 exe 同级（`data/`）

**所有用户数据**均在 **主程序 `AI Novel Agent.exe` 所在目录下的 `data\`**（与 **`resources`**、**`locales`** 等并列），例如：

**`C:\Users\…\AppData\Local\Programs\ai-novel-agent-electron\data\`**（具体以本机安装路径为准）

若安装到 **`Program Files`** 等受保护目录，可能因权限无法写入，需「以管理员运行」或改安装到用户目录。**便携使用**：可把 `win-unpacked` 整夹复制到 U 盘，数据会落在该目录下 `data\`。

| 内容 | 相对 `data\` | 说明 |
|------|----------------|------|
| **设定（lores）** | **`lores\`** | 与仓库 **`lores/`** 同样规则：子目录 + **`.md`** = 标签路径。放入后**重开应用**即可。 |
| **生成正文（.txt）** | **`outputs\`** | 对应开发时仓库根 **`outputs/`**。 |
| **每本小说 SQLite** | **`novels\<小说UUID>\novel.db`** | 章节、状态、图谱等。 |
| **API 密钥** | **`user_settings.json`** | 网页「API 密钥」。 |
| **后端日志** | **`novel-backend.log`** | **`novel-backend.exe`** 的 stdout/stderr。 |

开发模式（`npm run dev`）不设 **`NOVEL_AGENT_STORAGE_DIR`** 时：lores 为仓库根 **`lores/`**，输出为 **`outputs/`**，数据库为 **`storage/novels/...`**（与源码布局一致）。

| 方式 | 适用场景 | 你要做的事 |
|------|----------|------------|
| **A. 内置 `novel-backend.exe`** | 目标机**未安装 Python**，希望开箱即用 | 用 **PyInstaller** 在构建机构建 exe，放到 **`electron/resources/backend/novel-backend.exe`**，再执行 **`npm run dist`**。步骤与参数见仓库 **`packaging/pyinstaller/README.md`**（需按报错补 `--hidden-import` / `--collect-all` 等，体积与冷启动时间可能较大）。 |
| **B. 本机 Python + 源码树** | 开发机或已装 Python 的用户 | 不设 exe 时自动尝试 `py` / `python`；也可设 **`NOVEL_AGENT_PROJECT_ROOT`** 指向**完整克隆的仓库根目录**（含 `webapp/`、`agents/` 等）。 |

**说明**：`electron-builder` 将 **`resources/backend/`** 整目录打进安装包（`extraResources` → 安装后 `resources/backend/`）。占位文件见 **`resources/backend/README.txt`**。

## 无 Python 运行的前提

- **仅打 Electron 安装包**：可以，见上文 **`npm run dist`**。
- **安装后在无 Python 的机器上也能跑后端**：必须自行完成 **PyInstaller** 打包并把 **`novel-backend.exe`** 放进 **`electron/resources/backend/`** 再打安装包；依赖较多时需按 **`packaging/pyinstaller/README.md`** 迭代补全；若单文件不稳定，可改用 **`--onedir`** 并在主进程里指向对应 exe（需与当前 `main` 启动逻辑一致）。

## 环境变量摘要

| 变量 | 说明 |
|------|------|
| `NOVEL_AGENT_PORT` | 仅旧版 HTTP 启动链路使用；IPC 分支默认不使用该端口。 |
| `NOVEL_AGENT_PIPE_PATH` | 由主进程在运行时注入给 worker；通常无需手工设置。 |
| `NOVEL_AGENT_FRONTEND_URL` | 可选；Electron 窗口优先加载该 URL（用于前端独立调试）。 |
| `PYTHON` / `PYTHON_EXE` | 指定 Python 可执行文件（源码模式）。 |
| `NOVEL_AGENT_PROJECT_ROOT` | 源码模式下的**仓库根目录**。 |
| `NOVEL_AGENT_STORAGE_DIR` | 安装版为 **`<exe 所在目录>/data`**，**唯一数据根**；其下含 `lores/`、`outputs/`、`novels/` 等。 |
| `NOVEL_AGENT_OUTPUTS_DIR` | 可选；未设置时输出为 **`STORAGE_DIR/outputs`**。 |
| `NOVEL_AGENT_LORES_DIR` | 可选；未设置且已设置 **`NOVEL_AGENT_STORAGE_DIR`** 时，lores 为 **`STORAGE_DIR/lores`**。 |

## 排错提示

- **Electron 下载失败 / 极慢**：见上文 **`ELECTRON_MIRROR`**。
- **Preload 找不到**：`electron-vite` 构建后可能产出 **`preload/index.mjs`** 或 **`index.js`**；主进程会优先使用存在的文件（见 **`resolvePreloadPath`** in **`src/main/index.ts`**）。
- **后端起不来 / 弹窗只有笼统提示**：安装版会把日志写到 **`<exe 同目录>\data\novel-backend.log`**，弹窗内会附带**最近一段输出**与完整路径。

## 相关文件

- **`src/main/index.ts`**：启动 **`resources/backend/novel-backend.exe`** 或 Python IPC worker，并注入上述环境变量。
- **`package.json`**：`dist` / `dist:dir`、`electron-builder` 的 NSIS、**`extraResources`**、**`signAndEditExecutable`** 等。
