/**
 * Player identity tests.
 *
 * Run with `npm test` (node --test). They cover the insecure-context case that
 * used to crash the first render: `crypto.randomUUID` is undefined when the page
 * is served over plain HTTP, so identity generation must fall back instead of
 * throwing.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { createPlayerId, type RandomSource } from "./playerIdentity.ts";

const UUID_V4 = /^p-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

test("prefers the platform UUID when the context is secure", () => {
  const id = createPlayerId({ randomUUID: () => "11111111-2222-4333-8444-555555555555" });

  assert.equal(id, "p-11111111-2222-4333-8444-555555555555");
});

test("falls back to getRandomValues without a platform UUID", () => {
  let calls = 0;
  const source: RandomSource = {
    getRandomValues: (array) => {
      calls += 1;
      array.fill(7);
      return array;
    },
  };

  const id = createPlayerId(source);

  assert.equal(calls, 1);
  assert.match(id, UUID_V4);
});

test("the fallback ids are unique per call", () => {
  let seed = 0;
  const source: RandomSource = {
    getRandomValues: (array) => {
      for (let index = 0; index < array.length; index += 1) {
        seed += 1;
        array[index] = seed % 256;
      }
      return array;
    },
  };

  assert.notEqual(createPlayerId(source), createPlayerId(source));
});

test("still produces an id when no crypto API exists at all", () => {
  const id = createPlayerId({});

  assert.match(id, UUID_V4);
});
