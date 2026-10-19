/**
 * Client-side player identity.
 *
 * The player id is only a correlation key for the WebSocket; the server still
 * owns every game action. It is generated in the browser when the host app did
 * not pass one in the URL.
 *
 * `crypto.randomUUID()` only exists in secure contexts (HTTPS or localhost), so
 * a plain-HTTP deployment would previously throw on the first render and blank
 * the whole app inside the Porteghal WebView. The fallback below works in every
 * context and stays collision-resistant by using `crypto.getRandomValues`.
 */

/** The crypto surface used here; injectable so tests need no global stubs. */
export interface RandomSource {
  randomUUID?: () => string;
  getRandomValues?: (array: Uint8Array) => Uint8Array;
}

function fallbackUuid(source: RandomSource | undefined): string {
  const bytes = new Uint8Array(16);
  if (source && typeof source.getRandomValues === "function") {
    source.getRandomValues(bytes);
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256);
    }
  }

  // RFC 4122 version 4 layout.
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;

  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return [
    hex.slice(0, 8),
    hex.slice(8, 12),
    hex.slice(12, 16),
    hex.slice(16, 20),
    hex.slice(20),
  ].join("-");
}

/**
 * Build a player id, preferring the platform UUID when the context allows it.
 *
 * The optional source is for tests; production code calls `createPlayerId()`
 * and gets the global `crypto` when the browser provides one.
 */
export function createPlayerId(source?: RandomSource): string {
  const cryptoApi =
    source ?? (typeof globalThis.crypto === "undefined" ? undefined : globalThis.crypto);

  if (cryptoApi && typeof cryptoApi.randomUUID === "function") {
    return `p-${cryptoApi.randomUUID()}`;
  }
  return `p-${fallbackUuid(cryptoApi)}`;
}
