import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("novelAgentDesktop", {
  mode: "electron",
  openPath: (targetPath: string) =>
    ipcRenderer.invoke("novel-agent:open-path", targetPath) as Promise<{ ok: boolean; error?: string }>,
  apiJson: (url: string, method: string, body?: unknown) =>
    ipcRenderer.invoke("novel-agent:api-json", { url, method, body }) as Promise<unknown>,
  apiSseOpen: (streamId: string, url: string, method: string, body?: unknown) =>
    ipcRenderer.invoke("novel-agent:api-sse-open", { streamId, url, method, body }) as Promise<{
      ok: boolean;
      streamId: string;
    }>,
  apiSseClose: (streamId: string) =>
    ipcRenderer.invoke("novel-agent:api-sse-close", { streamId }) as Promise<{ ok: boolean }>,
  onSseEvent: (handler: (payload: { streamId: string; event: string; data: unknown }) => void) => {
    const fn = (_ev: unknown, payload: { streamId: string; event: string; data: unknown }) => handler(payload);
    ipcRenderer.on("novel-agent:sse-event", fn);
    return () => ipcRenderer.removeListener("novel-agent:sse-event", fn);
  },
  onSseEnd: (handler: (payload: { streamId: string }) => void) => {
    const fn = (_ev: unknown, payload: { streamId: string }) => handler(payload);
    ipcRenderer.on("novel-agent:sse-end", fn);
    return () => ipcRenderer.removeListener("novel-agent:sse-end", fn);
  },
  onSseError: (handler: (payload: { streamId: string; message: string }) => void) => {
    const fn = (_ev: unknown, payload: { streamId: string; message: string }) => handler(payload);
    ipcRenderer.on("novel-agent:sse-error", fn);
    return () => ipcRenderer.removeListener("novel-agent:sse-error", fn);
  },
});
