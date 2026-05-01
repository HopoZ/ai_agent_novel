import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { app, BrowserWindow, dialog, ipcMain, shell } from "electron";

let backendProc: ChildProcessWithoutNullStreams | null = null;

function backendExePath(): string {
  return join(process.resourcesPath, "backend", "novel-backend.exe");
}

function startBackend(): void {
  const exe = backendExePath();
  if (!existsSync(exe)) {
    throw new Error(`Backend executable not found: ${exe}`);
  }
  const storageDir = join(app.getPath("exe"), "..", "data");
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
}

function createMainWindow(): void {
  const win = new BrowserWindow({
    width: 1280,
    height: 860,
    webPreferences: {
      preload: join(__dirname, "../preload/index.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  void win.loadURL("http://127.0.0.1:8000/");
}

app.whenReady().then(() => {
  ipcMain.handle("desktop:open-path", async (_, targetPath: string) => {
    try {
      await shell.openPath(targetPath);
      return { ok: true };
    } catch (error) {
      const message = error instanceof Error ? error.message : "unknown error";
      return { ok: false, error: message };
    }
  });
  try {
    startBackend();
    createMainWindow();
  } catch (error) {
    const message = error instanceof Error ? error.message : "unknown error";
    dialog.showErrorBox("AI Novel Agent startup failed", message);
    app.quit();
  }
});

app.on("window-all-closed", () => {
  if (backendProc && !backendProc.killed) {
    backendProc.kill();
  }
  app.quit();
});
