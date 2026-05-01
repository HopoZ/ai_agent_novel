import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("novelAgentDesktop", {
  mode: "electron",
  openPath: (targetPath: string) => ipcRenderer.invoke("desktop:open-path", targetPath),
});
