/** 与后端 JSON / SSE 通信的薄封装 */
import { getNovelAgentDesktop } from "../desktop";

export function logDebug(msg: string) {
  console.log("[debug]", msg);
}

export async function apiJson(url: string, method: string, body: unknown) {
  const desk = getNovelAgentDesktop();
  if (desk?.apiJson) {
    return await desk.apiJson(url, method, body);
  }
  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let data: unknown = null;
  try {
    data = JSON.parse(text);
  } catch {
    data = { raw: text };
  }
  if (!res.ok) {
    const d = data as { detail?: unknown };
    const msg = d && d.detail != null ? d.detail : JSON.stringify(data);
    logDebug(`API error: ${method} ${url} -> ${res.status} ${msg}`);
    throw new Error(String(msg));
  }
  return data;
}

export async function apiSse(
  url: string,
  method: string,
  body: unknown,
  onEvent: (evt: { event: string; data: unknown }) => void,
  signal?: AbortSignal
) {
  const desk = getNovelAgentDesktop();
  if (desk?.apiSseOpen && desk?.onSseEvent && desk?.onSseEnd && desk?.onSseError && desk?.apiSseClose) {
    const streamId = (globalThis.crypto?.randomUUID?.() || `${Date.now()}_${Math.random()}`).replace(/[^a-zA-Z0-9_-]/g, "");
    let streamErr: Error | null = null;
    let resolveWait: (() => void) | null = null;
    const cleanupFns: Array<() => void> = [];
    const cleanup = () => {
      while (cleanupFns.length) {
        try {
          cleanupFns.pop()?.();
        } catch {
          /* ignore */
        }
      }
    };
    const disposeEvent = desk.onSseEvent((payload) => {
      if (payload.streamId !== streamId) return;
      onEvent({ event: payload.event, data: payload.data });
    });
    cleanupFns.push(disposeEvent);
    const disposeEnd = desk.onSseEnd((payload) => {
      if (payload.streamId !== streamId) return;
      cleanup();
      resolveWait?.();
    });
    cleanupFns.push(disposeEnd);
    const disposeError = desk.onSseError((payload) => {
      if (payload.streamId !== streamId) return;
      streamErr = new Error(payload.message || "SSE stream error");
      cleanup();
      resolveWait?.();
    });
    cleanupFns.push(disposeError);
    const onAbort = () => {
      void desk.apiSseClose?.(streamId);
      cleanup();
      resolveWait?.();
    };
    signal?.addEventListener("abort", onAbort, { once: true });
    try {
      await desk.apiSseOpen(streamId, url, method, body);
      await new Promise<void>((resolve) => {
        resolveWait = resolve;
      });
      if (streamErr) throw streamErr;
      return;
    } finally {
      signal?.removeEventListener("abort", onAbort);
      cleanup();
    }
  }

  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
    signal,
  });
  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `HTTP ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buf = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    buf = buf.replace(/\r\n/g, "\n");

    while (true) {
      const idx = buf.indexOf("\n\n");
      if (idx === -1) break;
      const raw = buf.slice(0, idx);
      buf = buf.slice(idx + 2);

      const lines = raw.split("\n").map((l) => l.trimEnd());
      let evName = "message";
      let dataLine = "";
      for (const ln of lines) {
        if (ln.startsWith("event:")) evName = ln.slice("event:".length).trim();
        if (ln.startsWith("data:")) dataLine += ln.slice("data:".length).trim();
      }
      if (!dataLine) continue;
      try {
        const parsed = JSON.parse(dataLine) as { data?: unknown };
        onEvent({ event: evName, data: parsed?.data });
      } catch {
        onEvent({ event: evName, data: { raw: dataLine } });
      }
    }
  }
}
