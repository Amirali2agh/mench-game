// front/src/utils/boardCoordinates.ts
// Single source of truth for the 11x11 Mensch board geometry.
//
// The circular track is canonical: every seat's start cell, home column and yard
// corner is derived from the fixed corner offsets below. The identical table
// lives in the backend (app/services/board_layout.py) and
// boardCoordinates.test.ts fails when the two drift apart.
//
// Seats are ordered red, blue, green, yellow and always sit on their own corner:
// red = bottom-left, blue = top-left, green = top-right, yellow = bottom-right.

export interface GridCoord {
  r: number;
  c: number;
}

/** A corner of the board, as used by the four player panels and the yards. */
export type Corner = "tl" | "tr" | "bl" | "br";

/** The side of the center goal that a seat's home column arrives from. */
export type Side = "top" | "right" | "bottom" | "left";

/** The circular part of the board: positions 0-39 of every player. */
export const TRACK_LENGTH = 40;
/** First cell of a player's private home column. */
export const HOME_START = 40;
/** Last cell of a player's private home column. */
export const HOME_END = 43;
/** The center goal. Never sent as a piece position; winning means filling 40-43. */
export const GOAL = 44;

/**
 * Absolute track offset of every seat, in seat order.
 * Must match CORNER_OFFSETS in app/services/board_layout.py.
 */
export const CORNER_OFFSETS = [20, 30, 0, 10] as const;

/** Fixed yard corner of every seat (used when the server sends no offsets). */
export const SEAT_CORNERS: readonly Corner[] = ["bl", "tl", "tr", "br"];

/** Home column side of every seat, in seat order. */
export const SEAT_SIDES: readonly Side[] = ["bottom", "left", "top", "right"];

const CORNER_BY_OFFSET: Record<number, Corner> = {
  0: "tr",
  10: "br",
  20: "bl",
  30: "tl",
};

/**
 * 40-cell circular track (0-39), following the path clockwise around the board.
 * The start cell of a seat is `circularTrack[CORNER_OFFSETS[seat]]`.
 */
export const circularTrack: GridCoord[] = [
  { r: 0, c: 6 },
  { r: 1, c: 6 },
  { r: 2, c: 6 },
  { r: 3, c: 6 },
  { r: 4, c: 6 } /* ← added missing cell — connects (3,6)→(4,7) */,
  { r: 4, c: 7 },
  { r: 4, c: 8 },
  { r: 4, c: 9 },
  { r: 4, c: 10 },
  { r: 5, c: 10 },
  { r: 6, c: 10 },
  { r: 6, c: 9 },
  { r: 6, c: 8 },
  { r: 6, c: 7 },
  { r: 6, c: 6 },
  { r: 7, c: 6 },
  { r: 8, c: 6 },
  { r: 9, c: 6 },
  { r: 10, c: 6 },
  { r: 10, c: 5 },
  { r: 10, c: 4 },
  { r: 9, c: 4 },
  { r: 8, c: 4 },
  { r: 7, c: 4 },
  { r: 6, c: 4 },
  { r: 6, c: 3 },
  { r: 6, c: 2 },
  { r: 6, c: 1 },
  { r: 6, c: 0 },
  { r: 5, c: 0 },
  { r: 4, c: 0 },
  { r: 4, c: 1 },
  { r: 4, c: 2 },
  { r: 4, c: 3 },
  { r: 4, c: 4 },
  { r: 3, c: 4 },
  { r: 2, c: 4 },
  { r: 1, c: 4 },
  { r: 0, c: 4 },
  { r: 0, c: 5 },
];

/** Track cell where every seat enters the board, in seat order. */
export const START_CELLS: GridCoord[] = CORNER_OFFSETS.map(
  (offset) => circularTrack[offset],
);

/**
 * Home column of every seat, ordered from the track towards the goal.
 * Cell 0 is position 40 and cell 3 is position 43.
 */
export const HOME_COLUMNS: GridCoord[][] = [
  [
    { r: 9, c: 5 },
    { r: 8, c: 5 },
    { r: 7, c: 5 },
    { r: 6, c: 5 },
  ], // red, from the bottom
  [
    { r: 5, c: 1 },
    { r: 5, c: 2 },
    { r: 5, c: 3 },
    { r: 5, c: 4 },
  ], // blue, from the left
  [
    { r: 1, c: 5 },
    { r: 2, c: 5 },
    { r: 3, c: 5 },
    { r: 4, c: 5 },
  ], // green, from the top
  [
    { r: 5, c: 9 },
    { r: 5, c: 8 },
    { r: 5, c: 7 },
    { r: 5, c: 6 },
  ], // yellow, from the right
];

export const goalCoord: GridCoord = { r: 5, c: 5 };

/** Pieces in the yard are drawn by the yard component, not on the grid. */
export const YARD_SENTINEL: GridCoord = { r: -1, c: -1 };

/**
 * Corner of a seat, according to the offsets the server resolved for the match.
 * The offsets are what actually drive the board, so a two-player match puts the
 * second seat on the opposite corner instead of the neighbouring one.
 */
export function cornerForSeat(
  trackOffsets: readonly number[] | undefined,
  seat: number,
): Corner {
  const offset = trackOffsets?.[seat];
  if (offset !== undefined) {
    const corner = CORNER_BY_OFFSET[offset];
    if (corner) return corner;
  }
  return SEAT_CORNERS[seat] ?? "bl";
}

/** Absolute track offset of a seat for the current match. */
export function trackOffsetForSeat(
  trackOffsets: readonly number[] | undefined,
  seat: number,
): number {
  return trackOffsets?.[seat] ?? CORNER_OFFSETS[seat] ?? 0;
}

/**
 * Canonical seat (red/blue/green/yellow) that owns a track offset.
 * A corner always keeps its own color, so the second player of a two-player
 * match is the green player on the opposite corner, not a recolored blue one.
 */
export function seatForOffset(offset: number): number {
  const index = CORNER_OFFSETS.indexOf(offset as (typeof CORNER_OFFSETS)[number]);
  return index >= 0 ? index : 0;
}

/** Canonical color seat of a seat in the running match. */
export function seatColorIndex(
  trackOffsets: readonly number[] | undefined,
  seat: number,
): number {
  return seatForOffset(trackOffsetForSeat(trackOffsets, seat));
}

/**
 * Translate a seat-relative position into a board cell.
 *
 * Positions 0-39 walk the shared track, 40-43 walk the seat's home column, and
 * anything else (the yard, -1) returns YARD_SENTINEL because yard pieces are
 * rendered by the yard itself.
 */
export function getGridCoordinates(
  seat: number,
  pos: number,
  trackOffset?: number,
): GridCoord {
  if (pos >= 0 && pos <= TRACK_LENGTH - 1) {
    const offset = trackOffset ?? CORNER_OFFSETS[seat] ?? 0;
    return circularTrack[(pos + offset) % TRACK_LENGTH];
  }
  if (pos >= HOME_START && pos <= HOME_END) {
    // The home column belongs to the corner, not to the seat index.
    const colorSeat = seatForOffset(trackOffset ?? CORNER_OFFSETS[seat] ?? 0);
    return HOME_COLUMNS[colorSeat]?.[pos - HOME_START] ?? goalCoord;
  }
  if (pos === GOAL) {
    return goalCoord;
  }
  return YARD_SENTINEL;
}

export function getArrowRotation(coord: GridCoord): string {
  const { r, c } = coord;
  if (c === 6 && r >= 0 && r <= 3) return "rotate-90";
  if (r === 4 && c >= 6 && c <= 10) return "rotate-0";
  if (r === 5 && c === 10) return "rotate-90";
  if (r === 6 && c >= 6 && c <= 10) return "rotate-180";
  if (c === 6 && r >= 7 && r <= 10) return "rotate-90";
  if (r === 10 && c === 5) return "rotate-180";
  if (c === 4 && r >= 6 && r <= 10) return "rotate-270";
  if (r === 6 && c >= 0 && c <= 3) return "rotate-180";
  if (r === 5 && c === 0) return "rotate-270";
  if (r === 4 && c >= 0 && c <= 4) return "rotate-0";
  if (c === 4 && r >= 0 && r <= 3) return "rotate-270";
  if (r === 0 && c === 5) return "rotate-0";
  return "";
}
