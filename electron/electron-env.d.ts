export {};

declare global {
  interface Window {
    novelAgentDesktop?: {
      mode: string;
      openPath?: (targetPath: string) => Promise<{ ok: boolean; error?: string }>;
    };
  }
}
