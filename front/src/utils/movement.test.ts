/**
 * Movement legality of a single piece.
 *
 * Run with `npm test` (node --test). The table below is shared with the backend
 * test `test/test_movement_rules.py`; the two must agree or a rules change
 * silently drifts between the board and the engine.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { HOME_END, HOME_START } from "./boardCoordinates.ts";
import {
  YARD_POSITION,
  canMovePiece,
  isHomeCellFree,
  nextPosition,
} from "./movement.ts";

/** `pieces` (must have four entries) × dice → expected move verdict. */
const MOVES: ReadonlyArray<{
  current: number;
  dice: number;
  valid: boolean;
  position: number;
}> = [
  { current: YARD_POSITION, dice: 5, valid: false, position: YARD_POSITION },
  { current: YARD_POSITION, dice: 6, valid: true, position: 0 },
  { current: 0, dice: 3, valid: true, position: 3 },
  { current: 39, dice: 4, valid: true, position: HOME_END },
  { current: 39, dice: 5, valid: false, position: 39 },
  { current: 41, dice: 2, valid: true, position: HOME_END },
  { current: 42, dice: 2, valid: false, position: 42 },
  { current: HOME_END, dice: 1, valid: false, position: HOME_END },
];

describe("nextPosition", () => {
  for (const move of MOVES) {
    it(`position ${move.current} with dice ${move.dice}`, () => {
      assert.deepEqual(nextPosition(move.current, move.dice), {
        valid: move.valid,
        position: move.position,
      });
    });
  }
});

describe("isHomeCellFree", () => {
  it("allows any track cell", () => {
    assert.equal(isHomeCellFree([3, 3, -1, -1], 0, 3), true);
  });

  it("allows an empty home cell", () => {
    assert.equal(isHomeCellFree([38, -1, -1, -1], 0, HOME_START), true);
  });

  it("allows the piece to keep its own home cell", () => {
    assert.equal(isHomeCellFree([HOME_START, -1, -1, -1], 0, HOME_START), true);
  });

  it("refuses a home cell held by another piece", () => {
    assert.equal(isHomeCellFree([38, HOME_START, -1, -1], 0, HOME_START), false);
  });
});

describe("canMovePiece", () => {
  it("uses the shared table", () => {
    for (const move of MOVES) {
      const pieces = [move.current, -1, -1, -1];
      assert.equal(
        canMovePiece(pieces, 0, move.dice),
        move.valid,
        `position ${move.current} with dice ${move.dice}`,
      );
    }
  });

  it("refuses a piece with no dice value", () => {
    assert.equal(canMovePiece([0, -1, -1, -1], 0, null), false);
  });

  it("refuses an index outside the roster", () => {
    assert.equal(canMovePiece([0, -1, -1, -1], 4, 6), false);
  });

  it("refuses a blocked home cell", () => {
    assert.equal(canMovePiece([38, HOME_START, -1, -1], 0, 2), false);
  });
});
