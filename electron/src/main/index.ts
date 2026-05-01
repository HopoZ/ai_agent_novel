import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { appendFileSync, existsSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { app, BrowserWindow, dialog, ipcMain, Menu, shell } from "electron";

let backendProc: ChildProcessWithoutNullStreams | null = null;
let mainWindow: BrowserWindow | null = null;

const BACKEND_URL = "http://127.0.0.1:8000/";
const DEBUG_ENV_KEYS = ["NOVEL_AGENT_ELECTRON_DEBUG", "ELECTRON_DEBUG"];

function isDebugMode(): boolean {
  if (process.argv.includes("--debug-electron")) {
    return true;
  }
  return DEBUG_ENV_KEYS.some((key) => process.env[key] === "1");
}

function appWorkDir(): string {
  return join(app.getPath("exe"), "..", "data");
}

function logFilePath(): string {
  return join(appWorkDir(), "logs", "electron-main.log");
}

function writeMainLog(level: "INFO" | "WARN" | "ERROR", message: string): void {
  try {
    const path = logFilePath();
    mkdirSync(join(appWorkDir(), "logs"), { recursive: true });
    appendFileSync(path, `${new Date().toISOString()} [${level}] ${message}\n`, "utf8");
  } catch {
    // Keep startup resilient even if logging fails.
  }
}

function stopBackend(reason: string): void {
  if (!backendProc || backendProc.killed) {
    return;
  }
  writeMainLog("INFO", `stopping backend reason=${reason} pid=${backendProc.pid ?? "unknown"}`);
  backendProc.kill();
}

function backendExePath(): string {
  return join(process.resourcesPath, "backend", "novel-backend.exe");
}

function startBackend(debugMode: boolean): void {
  const exe = backendExePath();
  if (!existsSync(exe)) {
    throw new Error(`Backend executable not found: ${exe}`);
  }
  const storageDir = appWorkDir();
  backendProc = spawn(exe, [], {
    cwd: join(process.resourcesPath, "backend"),
    windowsHide: true,
    env: {
      ...process.env,
      NOVEL_AGENT_STORAGE_DIR: storageDir,
      SKIP_FRONTEND_BUILD: "1",
      NOVEL_AGENT_PORT: "8000",
    },
  });
  writeMainLog("INFO", `spawned backend pid=${backendProc.pid ?? "unknown"} exe=${exe}`);
  backendProc.on("exit", (code, signal) => {
    writeMainLog("WARN", `backend exited code=${code ?? "null"} signal=${signal ?? "null"}`);
    backendProc = null;
  });
  backendProc.stdout.on("data", (chunk) => {
    writeMainLog("INFO", `[backend stdout] ${String(chunk).trimEnd()}`);
  });
  backendProc.stderr.on("data", (chunk) => {
    writeMainLog("ERROR", `[backend stderr] ${String(chunk).trimEnd()}`);
  });
  if (debugMode) {
    const health = [
      `backendExe=${exe}`,
      `backendExists=${existsSync(exe)}`,
      `backendCwd=${join(process.resourcesPath, "backend")}`,
      `backendUrl=${BACKEND_URL}`,
      `backendPid=${backendProc.pid ?? "unknown"}`,
      `logFile=${logFilePath()}`,
    ].join("\n");
    dialog.showMessageBox({
      type: "info",
      title: "Electron debug startup health",
      message: "Debug mode startup diagnostics",
      detail: health,
    }).catch(() => {});
  }
}

function createMainWindow(debugMode: boolean): void {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    webPreferences: {
      preload: join(__dirname, "../preload/index.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  if (debugMode) {
    mainWindow.webContents.openDevTools({ mode: "detach" });
    writeMainLog("INFO", "devtools opened due to debug mode");
  }
  void mainWindow.loadURL(BACKEND_URL);
}

function installAppMenu(debugMode: boolean): void {
  const template = [
    {
      label: "File",
      submenu: [
        {
          label: debugMode ? "Debug Start (Active)" : "Debug Start",
          enabled: !debugMode,
          click: () => {
            writeMainLog("INFO", "debug start requested from menu");
            const args = process.argv.filter((arg) => arg !== "--debug-electron");
            app.relaunch({ args: [...args, "--debug-electron"] });
            app.exit(0);
          },
        },
        { type: "separator" as const },
        { role: "quit" as const },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
  writeMainLog("WARN", "secondary instance detected, quitting immediately");
  app.quit();
}

app.on("second-instance", () => {
  writeMainLog("INFO", "second-instance event: focusing existing main window");
  if (!mainWindow) {
    return;
  }
  if (mainWindow.isMinimized()) {
    mainWindow.restore();
  }
  mainWindow.focus();
});

app.whenReady().then(() => {
  const debugMode = isDebugMode();
  writeMainLog("INFO", `app ready debugMode=${debugMode}`);
  ipcMain.handle("desktop:open-path", async (_, targetPath: string) => {
    try {
      const err = await shell.openPath(targetPath);
      if (err) {
        writeMainLog("ERROR", `openPath failed target=${targetPath} err=${err}`);
        return { ok: false, error: err };
      }
      writeMainLog("INFO", `openPath success target=${targetPath}`);
      return { ok: true };
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown error";
      writeMainLog("ERROR", `openPath exception target=${targetPath} err=${message}`);
      return { ok: false, error: message };
    }
  });
  try {
    installAppMenu(debugMode);
    startBackend(debugMode);
    createMainWindow(debugMode);
  } catch (error) {
    const message = error instanceof Error ? error.message : "unknown error";
    writeMainLog("ERROR", `startup failure: ${message}`);
    dialog.showErrorBox("AI Novel Agent startup failed", message);
    app.quit();
  }
});

app.on("window-all-closed", () => {
  stopBackend("window-all-closed");
  mainWindow = null;
  app.quit();
});

app.on("before-quit", () => {
  stopBackend("before-quit");
});
