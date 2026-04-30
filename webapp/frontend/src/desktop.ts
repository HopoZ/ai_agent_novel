/** Electron preload 注入的桌面能力（仅安装版窗口内存在） */

export type OpenPathResult = { ok: boolean; error?: string };
export type DesktopSseEventPayload = { streamId: string; event: string; data: unknown };
export type DesktopSseEndPayload = { streamId: string };
export type DesktopSseErrorPayload = { streamId: string; message: string };

export type NovelAgentDesktopApi = {
  mode: string;
  openPath?: (targetPath: string) => Promise<OpenPathResult>;
  apiJson?: (url: string, method: string, body?: unknown) => Promise<unknown>;
  apiSseOpen?: (
    streamId: string,
    url: string,
    method: string,
    body?: unknown
  ) => Promise<{ ok: boolean; streamId: string }>;
  apiSseClose?: (streamId: string) => Promise<{ ok: boolean }>;
  onSseEvent?: (handler: (payload: DesktopSseEventPayload) => void) => () => void;
  onSseEnd?: (handler: (payload: DesktopSseEndPayload) => void) => () => void;
  onSseError?: (handler: (payload: DesktopSseErrorPayload) => void) => () => void;
};

export function getNovelAgentDesktop(): NovelAgentDesktopApi | undefined {
  return (window as unknown as { novelAgentDesktop?: NovelAgentDesktopApi }).novelAgentDesktop;
}
