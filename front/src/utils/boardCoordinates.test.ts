/**
 * Geometry tests for the board.
 *
 * Run with `npm test` (node --test). These cover the invariants the rendering
 * relies on: every start cell is the track cell of the seat's corner offset, the
 * home column starts right next to the last track cell of that seat, and the
 * offsets match the backend.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  CORNER_OFFSETS,
  HOME_COLUMNS,
  HOME_END,
  HOME_START,
  SEAT_CORNERS,
  SEAT_SIDES,
  START_CELLS,
  TRACK_LENGTH,
  YARD_SENTINEL,
  circularTrack,
  cornerForSeat,
  getGridCoordinates,
  goalCoord,
  seatColorIndex,
  trackOffsetForSeat,
  yardCentreForSeat,
  yardSlotCentreForPiece,
} from "./boardCoordinates.ts";

const BACKEND_LAYOUT = new URL(
  "../../../app/services/board_layout.py",
  import.meta.url,
);

test("the track has 40 unique cells", () => {
  assert.equal(circularTrack.length, TRACK_LENGTH);
  const seen = new Set(circularTrack.map((cell) => `${cell.r},${cell.c}`));
  assert.equal(seen.size, TRACK_LENGTH, "track cells must not repeat");
});

test("every seat starts on the cell of its corner offset", () => {
  for (let seat = 0; seat < CORNER_OFFSETS.length; seat += 1) {
    const expected = circularTrack[CORNER_OFFSETS[seat]];
    assert.deepEqual(START_CELLS[seat], expected);
  }
});

test("start cells are distinct and sit on the four corners", () => {
  const corners = new Set(START_CELLS.map((cell) => `${cell.r},${cell.c}`));
  assert.equal(corners.size, 4);
  assert.deepEqual(SEAT_CORNERS.slice().sort(), ["bl", "br", "tl", "tr"]);
});

test("each home column starts next to the last track cell of its seat", () => {
  for (let seat = 0; seat < CORNER_OFFSETS.length; seat += 1) {
    const lastTrackCell =
      circularTrack[(CORNER_OFFSETS[seat] + TRACK_LENGTH - 1) % TRACK_LENGTH];
    const firstHomeCell = HOME_COLUMNS[seat][0];
    const distance =
      Math.abs(lastTrackCell.r - firstHomeCell.r) +
      Math.abs(lastTrackCell.c - firstHomeCell.c);

    assert.equal(
      distance,
      1,
      `seat ${seat}: home column must start next to ${JSON.stringify(lastTrackCell)}`,
    );
    assert.equal(HOME_COLUMNS[seat].length, HOME_END - HOME_START + 1);
  }
});

test("home columns walk towards the goal without overlapping the track", () => {
  const trackCells = new Set(circularTrack.map((cell) => `${cell.r},${cell.c}`));

  for (const column of HOME_COLUMNS) {
    for (const cell of column) {
      assert.equal(
        trackCells.has(`${cell.r},${cell.c}`),
        false,
        "a home cell must not be a track cell",
      );
    }
    const last = column[column.length - 1];
    const distanceToGoal =
      Math.abs(last.r - goalCoord.r) + Math.abs(last.c - goalCoord.c);
    assert.equal(distanceToGoal, 1, "the last home cell touches the goal");
  }
});

test("two players use facing corners, twenty cells apart", () => {
  const twoPlayerOffsets = [CORNER_OFFSETS[0], CORNER_OFFSETS[2]];

  assert.deepEqual(twoPlayerOffsets, [20, 0]);
  assert.equal(
    Math.abs(twoPlayerOffsets[0] - twoPlayerOffsets[1]) % TRACK_LENGTH,
    20,
  );
  assert.equal(cornerForSeat(twoPlayerOffsets, 0), "bl");
  assert.equal(cornerForSeat(twoPlayerOffsets, 1), "tr");
});

test("four players sit on four different corners", () => {
  const corners = CORNER_OFFSETS.map((_, seat) =>
    cornerForSeat(CORNER_OFFSETS, seat),
  );

  assert.deepEqual(corners, ["bl", "tl", "tr", "br"]);
  assert.deepEqual(corners, SEAT_CORNERS);
});

test("cornerForSeat falls back to the fixed plan without offsets", () => {
  assert.equal(cornerForSeat(undefined, 0), "bl");
  assert.equal(cornerForSeat([], 2), "tr");
});

test("every seat owns one side of the goal", () => {
  assert.deepEqual(SEAT_SIDES, ["bottom", "left", "top", "right"]);
  assert.equal(new Set(SEAT_SIDES).size, 4);
});

test("positions map to the expected cells", () => {
  assert.deepEqual(getGridCoordinates(0, 0, 20), circularTrack[20]);
  assert.deepEqual(getGridCoordinates(1, 0, 0), circularTrack[0]);
  assert.deepEqual(getGridCoordinates(0, 39, 20), circularTrack[19]);
  assert.deepEqual(getGridCoordinates(0, HOME_START, 20), HOME_COLUMNS[0][0]);
  assert.deepEqual(getGridCoordinates(0, HOME_END, 20), HOME_COLUMNS[0][3]);
  assert.deepEqual(getGridCoordinates(0, -1, 20), YARD_SENTINEL);
  assert.deepEqual(getGridCoordinates(0, HOME_END + 1, 20), goalCoord);
});

test("a base centre sits in the middle of its corner", () => {
  assert.deepEqual(yardCentreForSeat(CORNER_OFFSETS, 0), { r: 8.5, c: 1.5 });
  assert.deepEqual(yardCentreForSeat(CORNER_OFFSETS, 1), { r: 1.5, c: 1.5 });
  assert.deepEqual(yardCentreForSeat(CORNER_OFFSETS, 2), { r: 1.5, c: 8.5 });
  assert.deepEqual(yardCentreForSeat(CORNER_OFFSETS, 3), { r: 8.5, c: 8.5 });
  // A two-player match seats the second player on the opposite corner.
  assert.deepEqual(yardCentreForSeat([20, 0], 1), { r: 1.5, c: 8.5 });
});

test("base slots sit one cell apart around the centre", () => {
  const slots = [0, 1, 2, 3].map((index) =>
    yardSlotCentreForPiece(CORNER_OFFSETS, 0, index),
  );

  assert.deepEqual(slots, [
    { r: 7.5, c: 0.5 },
    { r: 7.5, c: 2.5 },
    { r: 9.5, c: 0.5 },
    { r: 9.5, c: 2.5 },
  ]);
});

test("the offsets match the backend seat plan", () => {
  const source = readFileSync(BACKEND_LAYOUT, "utf8");
  const match = source.match(/CORNER_OFFSETS\s*=\s*\(([^)]*)\)/);
  assert.ok(match, "CORNER_OFFSETS must exist in app/services/board_layout.py");

  const backend = match[1]
    .split(",")
    .map((value) => Number.parseInt(value.trim(), 10))
    .filter((value) => !Number.isNaN(value));

  assert.deepEqual(backend, [...CORNER_OFFSETS]);
});

test("the second player of a two-player match is the green player", () => {
  const twoPlayerOffsets = [20, 0];

  assert.equal(seatColorIndex(twoPlayerOffsets, 0), 0); // red
  assert.equal(seatColorIndex(twoPlayerOffsets, 1), 2); // green
  assert.deepEqual(
    getGridCoordinates(1, HOME_START, 0),
    HOME_COLUMNS[2][0],
    "the green seat walks the top home column",
  );
});

test("four players keep their own color", () => {
  for (let seat = 0; seat < CORNER_OFFSETS.length; seat += 1) {
    assert.equal(seatColorIndex(CORNER_OFFSETS, seat), seat);
  }
});

test("trackOffsetForSeat prefers the offsets of the running match", () => {
  assert.equal(trackOffsetForSeat([20, 0], 1), 0);
  assert.equal(trackOffsetForSeat(undefined, 2), CORNER_OFFSETS[2]);
  assert.equal(trackOffsetForSeat([], 3), CORNER_OFFSETS[3]);
});
