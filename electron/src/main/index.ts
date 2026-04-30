import { app, BrowserWindow, dialog, ipcMain, shell } from "electron";
import { createWriteStream, existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import net from "node:net";
import { randomUUID } from "node:crypto";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function getProjectRoot(): string {
  if (process.env.NOVEL_AGENT_PROJECT_ROOT?.trim()) {
    return path.resolve(process.env.NOVEL_AGENT_PROJECT_ROOT.trim());
  }
  return path.resolve(__dirname, "..", "..", "..");
}

function resolveBundledBackendExe(): string | null {
  if (!app.isPackaged) return null;
  const p = path.join(process.resourcesPath, "backend", "novel-backend.exe");
  return existsSync(p) ? p : null;
}

/** 安装版应用数据根目录：与主程序 exe 同级的 data/（lores、outputs、novels、日志等） */
function resolvePackagedAppDataRoot(): string {
  const exeDir = path.dirname(app.getPath("exe"));
  return path.join(exeDir, "data");
}

function buildChildEnv(): NodeJS.ProcessEnv {
  const env = { ...process.env };
  if (app.isPackaged) {
    const root = resolvePackagedAppDataRoot();
    mkdirSync(root, { recursive: true });
    mkdirSync(path.join(root, "lores"), { recursive: true });
    mkdirSync(path.join(root, "outputs"), { recursive: true });
    env.NOVEL_AGENT_STORAGE_DIR = root;
    env.SKIP_FRONTEND_BUILD = "1";
  }
  return env;
}

function resolvePipePath(): string {
  const suffix = app.isPackaged ? "prod" : "dev";
  return `\\\\.\\pipe\\ai_novel_agent_${suffix}_${app.getVersion()}`.replace(/\s+/g, "_");
}

function pythonCommandCandidates(): [string, string[]][] {
  const fromEnv = [process.env.PYTHON, process.env.PYTHON_EXE].filter(
    (x): x is string => Boolean(x?.trim())
  );
  const extra: [string, string[]][] = fromEnv.map((exe) => [exe.trim(), []]);
  if (process.platform === "win32") {
    return [
      ...extra,
      ["py", ["-3"]],
      ["py", []],
      ["python", []],
      ["python3", []],
    ];
  }
  return [...extra, ["python3", []], ["python", []]];
}

function findWorkingPython(): [string, string[]] | null {
  const root = getProjectRoot();
  for (const [cmd, prefix] of pythonCommandCandidates()) {
    const r = spawnSync(cmd, [...prefix, "-c", "import sys; sys.exit(0)"], {
      cwd: root,
      encoding: "utf8",
      timeout: 10000,
      shell: false,
    });
    if (r.status === 0) {
      return [cmd, prefix];
    }
  }
  return null;
}

let mainWindow: BrowserWindow | null = null;
let backendChild: ChildProcess | null = null;
let backendPipeServer: net.Server | null = null;
let backendSocket: net.Socket | null = null;
let backendPipePath = "";

/** 最近一次后端子进程的输出尾部（用于弹窗）；安装版完整日志在 exe 同目录 data/novel-backend.log */
let backendLogTail = "";
let backendLogPath = "";
let backendLogStream: ReturnType<typeof createWriteStream> | null = null;

function startBackendLogCapture(): void {
  try {
    backendLogStream?.end();
  } catch {
    /* ignore */
  }
  backendLogStream = null;
  backendLogTail = "";
  const dir = app.isPackaged ? resolvePackagedAppDataRoot() : app.getPath("userData");
  mkdirSync(dir, { recursive: true });
  backendLogPath = path.join(dir, "novel-backend.log");
  backendLogStream = createWriteStream(backendLogPath, { flags: "a" });
  backendLogStream.write(`\n======== ${new Date().toISOString()} 启动后端 ========\n`);
}

function onBackendOutputChunk(chunk: Buffer): void {
  const s = chunk.toString("utf8");
  try {
    backendLogStream?.write(s);
  } catch {
    /* ignore */
  }
  backendLogTail = (backendLogTail + s).slice(-12000);
}

function attachChildProcessLogging(child: ChildProcess): void {
  child.stdout?.on("data", onBackendOutputChunk);
  child.stderr?.on("data", onBackendOutputChunk);
}

function formatBackendFailureForDialog(err: unknown): string {
  const base = String(err);
  const tail = backendLogTail.trim();
  const maxSnippet = 3800;
  const snippet = tail
    ? `\n\n—— 后端最近输出 ——\n${tail.length > maxSnippet ? `…（仅末尾 ${maxSnippet} 字）\n` : ""}${tail.slice(-maxSnippet)}`
    : `\n（当前未捕获到控制台输出；可在资源管理器中打开下方日志文件查看，或在安装目录 resources\\backend 下用 cmd 手动运行 novel-backend.exe。）`;
  const logLine = backendLogPath ? `\n\n完整日志：\n${backendLogPath}` : "";
  return `${base}${snippet}${logLine}`;
}

function startPipeWorkerFromPython(py: [string, string[]], pipePath: string): boolean {
  const args = [...py[1], "-m", "webapp.backend.ipc_pipe_worker"];
  const devUseInherit = !app.isPackaged;
  if (!devUseInherit) {
    startBackendLogCapture();
  }
  try {
    backendChild = spawn(py[0], args, {
      cwd: getProjectRoot(),
      env: { ...buildChildEnv(), NOVEL_AGENT_PIPE_PATH: pipePath },
      stdio: devUseInherit ? "inherit" : (["ignore", "pipe", "pipe"] as const),
      windowsHide: process.platform === "win32",
    });
    if (!devUseInherit) {
      attachChildProcessLogging(backendChild);
    }
  } catch {
    return false;
  }
  backendChild.on("exit", (code) => {
    backendChild = null;
    if (code !== 0 && code !== null && mainWindow && !mainWindow.isDestroyed()) {
      void mainWindow.webContents.executeJavaScript(
        `document.body.innerHTML='<pre style="padding:16px;font-family:system-ui">后端已退出 (code=${code})。</pre>'`
      );
    }
  });
  return true;
}

function startPipeWorkerFromBundledExe(exePath: string, pipePath: string): boolean {
  startBackendLogCapture();
  try {
    backendChild = spawn(exePath, [], {
      cwd: path.dirname(exePath),
      env: { ...buildChildEnv(), NOVEL_AGENT_PIPE_PATH: pipePath },
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: process.platform === "win32",
    });
    attachChildProcessLogging(backendChild);
  } catch {
    return false;
  }
  backendChild.on("exit", (code) => {
    backendChild = null;
    if (code !== 0 && code !== null && mainWindow && !mainWindow.isDestroyed()) {
      void mainWindow.webContents.executeJavaScript(
        `document.body.innerHTML='<pre style="padding:16px;font-family:system-ui">内置后端已退出 (code=${code})。</pre>'`
      );
    }
  });
  return true;
}

function killBackendWorker(): void {
  try {
    backendSocket?.destroy();
  } catch {
    /* ignore */
  }
  backendSocket = null;
  try {
    backendPipeServer?.close();
  } catch {
    /* ignore */
  }
  backendPipeServer = null;
  if (backendChild) {
    try {
      backendChild.kill();
    } catch {
      /* ignore */
    }
  }
  backendChild = null;
}

function resolvePreloadPath(): string {
  const dir = path.join(__dirname, "../preload");
  const mjs = path.join(dir, "index.mjs");
  const js = path.join(dir, "index.js");
  if (existsSync(mjs)) return mjs;
  return js;
}

function createWindow(): void {
  const preloadPath = resolvePreloadPath();
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    webPreferences: {
      preload: preloadPath,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });
  const frontendUrl = process.env.NOVEL_AGENT_FRONTEND_URL?.trim();
  if (frontendUrl) {
    void mainWindow.loadURL(frontendUrl);
  } else {
    const frontendIndex = app.isPackaged
      ? path.join(process.resourcesPath, "frontend", "index.html")
      : path.join(getProjectRoot(), "webapp", "frontend", "dist", "index.html");
    if (!existsSync(frontendIndex)) {
      void dialog.showErrorBox(
        "前端页面不存在",
        `未找到前端页面：\n${frontendIndex}\n\n请先在仓库根目录执行 webapp/frontend 的构建。`
      );
      app.quit();
      return;
    }
    void mainWindow.loadFile(frontendIndex);
  }
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function startBackendOrExit(pipePath: string): boolean {
  const bundled = resolveBundledBackendExe();
  if (bundled) {
    return startPipeWorkerFromBundledExe(bundled, pipePath);
  }
  const py = findWorkingPython();
  if (!py) {
    void dialog.showErrorBox(
      "无法启动后端",
      `未找到可用的 Python 3。已尝试：${pythonCommandCandidates()
        .map(([c, p]) => (p.length ? `${c} ${p.join(" ")}` : c))
        .join(", ")}\n\n请安装 Python，或使用环境变量 PYTHON 指向解释器。\n工作目录：${getProjectRoot()}`
    );
    return false;
  }
  return startPipeWorkerFromPython(py, pipePath);
}

type PendingJson = {
  resolve: (value: unknown) => void;
  reject: (reason?: unknown) => void;
};

const pendingJson = new Map<string, PendingJson>();
const liveStreams = new Set<string>();

function sendBackendFrame(frame: Record<string, unknown>): void {
  if (!backendSocket || backendSocket.destroyed) {
    throw new Error("backend pipe not connected");
  }
  backendSocket.write(JSON.stringify(frame) + "\n");
}

function wireBackendSocket(sock: net.Socket): void {
  backendSocket = sock;
  let buf = "";
  sock.on("data", (chunk) => {
    buf += chunk.toString("utf8");
    while (true) {
      const idx = buf.indexOf("\n");
      if (idx < 0) break;
      const line = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 1);
      if (!line) continue;
      let msg: any;
      try {
        msg = JSON.parse(line);
      } catch {
        continue;
      }
      const id = String(msg.id || "");
      const kind = String(msg.kind || "");

      if (kind === "json_result") {
        const pending = pendingJson.get(id);
        if (!pending) continue;
        pendingJson.delete(id);
        if (msg.ok) pending.resolve(msg.data);
        else {
          const detail = msg?.data?.detail ?? msg?.data ?? `HTTP ${msg.status ?? 500}`;
          pending.reject(new Error(String(detail)));
        }
        continue;
      }
      if (kind === "stream_event") {
        if (!mainWindow || mainWindow.isDestroyed() || !liveStreams.has(id)) continue;
        mainWindow.webContents.send("novel-agent:sse-event", {
          streamId: id,
          event: String(msg.event || "message"),
          data: msg.data,
        });
        continue;
      }
      if (kind === "stream_end") {
        if (mainWindow && !mainWindow.isDestroyed() && liveStreams.has(id)) {
          mainWindow.webContents.send("novel-agent:sse-end", { streamId: id });
        }
        liveStreams.delete(id);
        continue;
      }
      if (kind === "error") {
        const pending = pendingJson.get(id);
        if (pending) {
          pendingJson.delete(id);
          pending.reject(new Error(String(msg.message || "backend error")));
        } else if (mainWindow && !mainWindow.isDestroyed() && liveStreams.has(id)) {
          mainWindow.webContents.send("novel-agent:sse-error", {
            streamId: id,
            message: String(msg.message || "backend stream error"),
          });
          liveStreams.delete(id);
        }
      }
    }
  });
  sock.on("close", () => {
    backendSocket = null;
    for (const [, pending] of pendingJson) {
      pending.reject(new Error("backend disconnected"));
    }
    pendingJson.clear();
    if (mainWindow && !mainWindow.isDestroyed()) {
      for (const sid of liveStreams) {
        mainWindow.webContents.send("novel-agent:sse-error", {
          streamId: sid,
          message: "backend disconnected",
        });
      }
    }
    liveStreams.clear();
  });
}

function startPipeServerAndWaitWorker(timeoutMs = 120000): Promise<void> {
  return new Promise((resolve, reject) => {
    backendPipePath = resolvePipePath();
    try {
      backendPipeServer?.close();
    } catch {
      /* ignore */
    }
    backendPipeServer = net.createServer((sock) => {
      wireBackendSocket(sock);
      resolve();
    });
    backendPipeServer.once("error", (err) => reject(err));
    backendPipeServer.listen(backendPipePath, () => {
      const timer = setTimeout(() => {
        reject(new Error(`worker 未在 ${timeoutMs}ms 内连接命名管道 ${backendPipePath}`));
      }, timeoutMs);
      backendPipeServer?.once("connection", () => clearTimeout(timer));
    });
  });
}

function waitForWorkerReadyOrExit(workerReady: Promise<void>, child: ChildProcess | null): Promise<void> {
  return new Promise((resolve, reject) => {
    let settled = false;
    const onExit = (code: number | null) => {
      if (settled) return;
      settled = true;
      reject(new Error(`后端 worker 提前退出（exit code=${code ?? "null"}）`));
    };
    child?.once("exit", onExit);
    workerReady.then(
      () => {
        if (settled) return;
        settled = true;
        child?.removeListener("exit", onExit);
        resolve();
      },
      (e) => {
        if (settled) return;
        settled = true;
        child?.removeListener("exit", onExit);
        reject(e);
      }
    );
  });
}

ipcMain.handle(
  "novel-agent:open-path",
  async (_event, targetPath: string): Promise<{ ok: boolean; error?: string }> => {
    const p = String(targetPath || "").trim();
    if (!p) {
      return { ok: false, error: "路径为空" };
    }
    const err = await shell.openPath(p);
    if (err) {
      return { ok: false, error: err };
    }
    return { ok: true };
  }
);

ipcMain.handle("novel-agent:api-json", async (_event, req: { url: string; method: string; body?: unknown }) => {
  const id = randomUUID();
  return await new Promise((resolve, reject) => {
    pendingJson.set(id, { resolve, reject });
    try {
      sendBackendFrame({
        id,
        op: "json",
        url: String(req?.url || ""),
        method: String(req?.method || "GET"),
        body: req?.body ?? null,
      });
    } catch (e) {
      pendingJson.delete(id);
      reject(e);
    }
  });
});

ipcMain.handle(
  "novel-agent:api-sse-open",
  async (_event, req: { streamId: string; url: string; method: string; body?: unknown }) => {
    const sid = String(req?.streamId || randomUUID());
    liveStreams.add(sid);
    try {
      sendBackendFrame({
        id: sid,
        op: "stream",
        url: String(req?.url || ""),
        method: String(req?.method || "POST"),
        body: req?.body ?? null,
      });
    } catch (e) {
      liveStreams.delete(sid);
      throw e;
    }
    return { ok: true, streamId: sid };
  }
);

ipcMain.handle("novel-agent:api-sse-close", async (_event, req: { streamId: string }) => {
  const sid = String(req?.streamId || "");
  liveStreams.delete(sid);
  try {
    sendBackendFrame({ id: sid, op: "stream_cancel" });
  } catch {
    /* ignore */
  }
  return { ok: true };
});

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    const pipeReady = startPipeServerAndWaitWorker(120000);
    if (!startBackendOrExit(backendPipePath)) {
      app.quit();
      return;
    }
    try {
      await waitForWorkerReadyOrExit(pipeReady, backendChild);
    } catch (e) {
      void dialog.showErrorBox("IPC 管道启动失败", formatBackendFailureForDialog(e));
      killBackendWorker();
      app.quit();
      return;
    }
    createWindow();
  });

  app.on("window-all-closed", () => {
    killBackendWorker();
    if (process.platform !== "darwin") app.quit();
  });

  app.on("before-quit", () => {
    killBackendWorker();
  });
}
