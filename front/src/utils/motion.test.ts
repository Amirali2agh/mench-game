/**
 * Motion preferences.
 *
 * The board runs every move as a hop and spins the dice on every roll; both are
 * decorative, so `prefers-reduced-motion: reduce` has to turn them into plain
 * state changes.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { prefersReducedMotion } from "./motion.ts";

type FakeWindow = { matchMedia?: (query: string) => { matches: boolean } };

function withWindow(value: FakeWindow | undefined) {
  Object.defineProperty(globalThis, "window", {
    value,
    configurable: true,
    writable: true,
  });
}

test("no window (node) means motion is allowed", () => {
  withWindow(undefined);
  assert.equal(prefersReducedMotion(), false);
});

test("a browser without matchMedia keeps its animations", () => {
  withWindow({});
  assert.equal(prefersReducedMotion(), false);
});

test("the reduce preference is read at call time", () => {
  const queries: string[] = [];
  withWindow({
    matchMedia: (query) => {
      queries.push(query);
      return { matches: true };
    },
  });

  assert.equal(prefersReducedMotion(), true);
  assert.deepEqual(queries, ["(prefers-reduced-motion: reduce)"]);

  withWindow({ matchMedia: () => ({ matches: false }) });
  assert.equal(prefersReducedMotion(), false);
});
