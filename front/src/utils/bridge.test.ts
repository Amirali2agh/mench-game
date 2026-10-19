/**
 * Bridge helper tests.
 *
 * Run with `npm test` (node --test). `getQueryParams` is how the host app
 * hand-offs identity to the game, so its parsing and URL decoding must be
 * exact: a mangled Persian name or a dropped room id strands the player.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { getQueryParams } from "./bridge.ts";

function withSearch(search: string, run: () => void): void {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "window");
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: { location: { search } },
  });
  try {
    run();
  } finally {
    if (descriptor) {
      Object.defineProperty(globalThis, "window", descriptor);
    } else {
      delete (globalThis as { window?: unknown }).window;
    }
  }
}

test("parses and decodes query parameters", () => {
  withSearch("?roomId=abc&playerName=%D8%A7%D9%85%DB%8C%D8%B1&empty=", () => {
    assert.deepEqual(getQueryParams(), { roomId: "abc", playerName: "امیر" });
  });
});

test("returns an empty object when there is no query string", () => {
  withSearch("", () => {
    assert.deepEqual(getQueryParams(), {});
  });
});

test("ignores malformed pairs", () => {
  withSearch("?a=1&broken&b=2", () => {
    assert.deepEqual(getQueryParams(), { a: "1", b: "2" });
  });
});
