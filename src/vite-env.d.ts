/// <reference types="vite/client" />

declare global {
  interface Window {
    desktop?: {
      token: () => string;
      apiBase: () => string;
      platform: () => string;
      arch: () => string;
      selectFiles: (filters?: { name: string; extensions: string[] }[]) => Promise<string[]>;
      selectDirectory: () => Promise<string>;
      openPath: (target: string) => Promise<string>;
      openExternal: (url: string) => Promise<string>;
      revealPath: (target: string) => Promise<string>;
      appInfo: () => Promise<{ version: string; platform: string; arch: string; dataDir: string; apiBase: string }>;
      onProgress: (callback: (value: { text: string; detail?: string }) => void) => () => void;
      onBackendStatus: (callback: (value: { text: string; detail?: string }) => void) => () => void;
    };
  }
}

export {};
