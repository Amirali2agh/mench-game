/**
 * Backend origin resolution for every environment the client runs in.
 *
 * The browser bundle must not hard-code a host or a port: production is served
 * by a reverse proxy that forwards `/api/*` and `/ws/*` to the backend, so a
 * production build talks to its own origin. The Vite dev server, on the other
 * hand, runs on a different port than uvicorn, so development falls back to
 * port 8000 of the page host.
 *
 * Both origins can be pinned at build time with `VITE_API_BASE_URL` and
 * `VITE_WS_BASE_URL` (see `front/.env.example`), which is how a client is
 * pointed at an API on a different origin.
 */

/** The part of `window.location` the resolution needs. */
export interface PageLocation {
  protocol: string;
  /** Host name without the port, e.g. `localhost`. */
  hostname: string;
  /** Host with the port when it is not the scheme default, e.g. `localhost:3000`. */
  host: string;
}

export interface BackendOriginConfig {
  /** Build-time override for the REST origin, e.g. `https://api.example.com`. */
  apiBaseUrl?: string;
  /** Build-time override for the WebSocket origin, e.g. `wss://api.example.com`. */
  wsBaseUrl?: string;
  location: PageLocation;
  /** True for the Vite dev server, where the backend lives on another port. */
  isDev: boolean;
  /** Dev backend port; overridable so tests and unusual setups stay explicit. */
  devBackendPort?: string;
}

/** Port uvicorn listens on in the documented local setup. */
export const DEV_BACKEND_PORT = "8000";

function normalizeBaseUrl(value: string | undefined): string {
  return (value ?? "").trim().replace(/\/+$/, "");
}

function schemeFor(location: PageLocation, secure: "http" | "ws"): string {
  const isSecure = location.protocol === "https:";
  if (secure === "ws") return isSecure ? "wss" : "ws";
  return isSecure ? "https" : "http";
}

function devOrigin(config: BackendOriginConfig, secure: "http" | "ws"): string {
  const port = config.devBackendPort || DEV_BACKEND_PORT;
  return `${schemeFor(config.location, secure)}://${config.location.hostname}:${port}`;
}

/**
 * REST origin. An empty string means "same origin": `fetch("/api/...")` then
 * goes through the reverse proxy, which is what a production build wants.
 */
export function resolveApiBaseUrl(config: BackendOriginConfig): string {
  const configured = normalizeBaseUrl(config.apiBaseUrl);
  if (configured) return configured;
  return config.isDev ? devOrigin(config, "http") : "";
}

/**
 * WebSocket origin. Unlike REST the browser needs an absolute URL here, so the
 * production fallback keeps the page host (and its port, when any) and only
 * swaps the scheme to `ws`/`wss`.
 */
export function resolveWsBaseUrl(config: BackendOriginConfig): string {
  const configured = normalizeBaseUrl(config.wsBaseUrl);
  if (configured) return configured;
  if (config.isDev) return devOrigin(config, "ws");
  return `${schemeFor(config.location, "ws")}://${config.location.host}`;
}
