/**
 * Message bridge to parent app (Porteghal WebView/iframe).
 */
import { resolveApiBaseUrl, resolveWsBaseUrl } from "./backendOrigin";

export function sendToParent(
  type: string,
  payload?: Record<string, any>,
): void {
  const message = JSON.stringify({ type, ...payload });

  // React Native WebView bridge
  if (
    typeof window !== "undefined" &&
    (window as any).ReactNativeWebView?.postMessage
  ) {
    (window as any).ReactNativeWebView.postMessage(message);
  }
  // Standard iframe parent communication
  if (
    typeof window !== "undefined" &&
    window.parent &&
    window.parent !== window
  ) {
    window.parent.postMessage(message, "*");
  }
  // Standalone fallback
  else {
    console.log("[Bridge]", message);
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
