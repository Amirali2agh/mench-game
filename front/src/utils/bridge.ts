/**
 * Message bridge to parent app (Porteghal WebView/iframe).
 */
import { resolveApiBaseUrl, resolveWsBaseUrl } from "./backendOrigin.ts";

/** The React Native WebView injects this handle into the page. */
interface BridgeWindow extends Window {
  ReactNativeWebView?: { postMessage?: (message: string) => void };
}

export function sendToParent(
  type: string,
  payload?: Record<string, unknown>,
): void {
  const message = JSON.stringify({ type, ...payload });

  if (typeof window === "undefined") return;
  const bridgeWindow = window as unknown as BridgeWindow;

  // React Native WebView bridge
  bridgeWindow.ReactNativeWebView?.postMessage?.(message);

  // Standard iframe parent communication, with a console fallback when the
  // game runs standalone.
  if (window.parent && window.parent !== window) {
    window.parent.postMessage(message, "*");
  } else {
    console.debug("[Bridge]", message);
  }
}

/**
 * Parse URL query parameters (supports ?key=value&key2=value2).
 */
export function getQueryParams(): Record<string, string> {
  const params: Record<string, string> = {};
  if (typeof window === "undefined") return params;
  const search = window.location.search.substring(1);
  if (!search) return params;
  search.split("&").forEach((part) => {
    const [key, val] = part.split("=");
    if (key && val) params[decodeURIComponent(key)] = decodeURIComponent(val);
  });
  return params;
}

/**
 * REST origin for the current build.
 *
 * A production build returns "" (same origin), so requests go through the
 * reverse proxy; `VITE_API_BASE_URL` points the client at another origin.
 */
export function getApiBaseUrl(): string {
  return resolveApiBaseUrl({
    apiBaseUrl: import.meta.env.VITE_API_BASE_URL,
    location: window.location,
    isDev: import.meta.env.DEV,
  });
}

/**
 * WebSocket origin for the current build.
 *
 * Production uses the page host, development falls back to the local backend
 * port, and `VITE_WS_BASE_URL` overrides both.
 */
export function getWsBaseUrl(): string {
  return resolveWsBaseUrl({
    wsBaseUrl: import.meta.env.VITE_WS_BASE_URL,
    location: window.location,
    isDev: import.meta.env.DEV,
  });
}
