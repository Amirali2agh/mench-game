/**
 * Geometry of the piece hop animation.
 *
 * Run with `npm test` (node --test). These helpers replace the old per-step
 * `setState` loop; keeping the math pure means the animation path can be tested
 * without a DOM.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  HOP_STEP_MS,
  hopPoints,
  pieceTransform,
  stackOffset,
} from "./pieceMotion.ts";

const GEOMETRY = { pitch: 40, size: 32, overlap: 0 };

describe("pieceTransform", () => {
  it("centres the piece inside the cell", () => {
    assert.equal(pieceTransform({ r: 0, c: 0 }, GEOMETRY), "translate3d(4px, 4px, 0)");
  });

  it("follows the board pitch", () => {
    assert.equal(
      pieceTransform({ r: 2, c: 3 }, GEOMETRY),
      `translate3d(${3 * 40 + 4}px, ${2 * 40 + 4}px, 0)`,
    );
  });

  it("applies the stacking nudge on both axes", () => {
    assert.equal(
      pieceTransform({ r: 1, c: 1 }, { ...GEOMETRY, overlap: 5 }),
      "translate3d(49px, 39px, 0)",
    );
  });
});

describe("hopPoints", () => {
  it("includes the start cell and every cell up to the target", () => {
    const points = hopPoints(5, 8, (position) => ({ r: position, c: position + 1 }));
    assert.deepEqual(points, [
      { r: 5, c: 6 },
      { r: 6, c: 7 },
      { r: 7, c: 8 },
      { r: 8, c: 9 },
    ]);
  });

  it("is a single point when the piece does not advance", () => {
    assert.equal(hopPoints(4, 4, (position) => ({ r: 0, c: position })).length, 1);
  });

  it("runs one step per cell", () => {
    const steps = hopPoints(10, 15, (position) => ({ r: 0, c: position })).length - 1;
    assert.equal(steps * HOP_STEP_MS, 700);
  });
});

describe("stackOffset", () => {
  it("does not move a single piece", () => {
    assert.equal(stackOffset(0, 1), 0);
  });

  it("fans out a stack around its centre", () => {
    assert.deepEqual(
      [0, 1, 2].map((index) => stackOffset(index, 3)),
      [-5, 0, 5],
    );
  });
});
