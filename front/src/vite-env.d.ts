/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** REST origin, e.g. `https://api.example.com`; empty means same origin. */
  readonly VITE_API_BASE_URL?: string;
  /** WebSocket origin, e.g. `wss://api.example.com`; empty means the page host. */
  readonly VITE_WS_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
