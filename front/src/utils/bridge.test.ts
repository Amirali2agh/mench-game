/**
 * Bridge helper tests.
 *
 * Run with `npm test` (node --test). `getQueryParams` is how the host app
 * hand-offs identity to the game, so its parsing and URL decoding must be
 * exact: a mangled Persian name or a dropped room id strands the player.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { getParentTargetOrigin, getQueryParams, sendToParent } from "./bridge.ts";

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

interface WindowStub {
  location: { search: string; origin: string };
  parent: unknown;
}

function installWindow(stub: WindowStub, run: () => void): void {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "window");
  Object.defineProperty(globalThis, "window", { configurable: true, value: stub });
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

test("bridge messages go to the embedding origin, never a wildcard", () => {
  const calls: Array<{ message: string; target: string }> = [];
  const stub: WindowStub = {
    location: { search: "", origin: "https://game.example" },
    parent: {
      postMessage: (message: string, target: string) => calls.push({ message, target }),
    },
  };

  installWindow(stub, () => sendToParent("GAME_FINISHED", { winner: "p1" }));

  assert.deepEqual(calls, [
    {
      message: '{"type":"GAME_FINISHED","winner":"p1"}',
      target: "https://game.example",
    },
  ]);
});

test("a host-declared parentOrigin wins and is normalised to its origin", () => {
  const calls: Array<{ message: string; target: string }> = [];
  const stub: WindowStub = {
    location: {
      search: "?parentOrigin=https%3A%2F%2Fhost.example%2Fsome%2Fpath",
      origin: "https://game.example",
    },
    parent: {
      postMessage: (message: string, target: string) => calls.push({ message, target }),
    },
  };

  installWindow(stub, () => sendToParent("STATE"));

  assert.deepEqual(calls, [
    { message: '{"type":"STATE"}', target: "https://host.example" },
  ]);
});

test("an unsafe parentOrigin is ignored in favour of the same origin", () => {
  for (const search of [
    "?parentOrigin=javascript%3Aalert(1)",
    "?parentOrigin=not-a-url",
  ]) {
    const stub: WindowStub = {
      location: { search, origin: "https://game.example" },
      parent: {},
    };

    installWindow(stub, () =>
      assert.equal(getParentTargetOrigin(), "https://game.example"),
    );
  }
});

test("nothing is posted when the game is not framed", () => {
  let posted = false;
  const stub: WindowStub = {
    location: { search: "", origin: "https://game.example" },
    parent: undefined,
  };
  stub.parent = stub;
  (stub as unknown as { postMessage: () => void }).postMessage = () => {
    posted = true;
  };

  installWindow(stub, () => sendToParent("STATE"));

  assert.equal(posted, false);
});
