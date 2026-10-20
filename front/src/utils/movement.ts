/**
 * Movement legality of a single piece.
 *
 * The client only needs these rules to grey out a piece the player cannot move
 * and to offer the one automatic move; the server still decides the outcome.
 * They used to live inline in `GameBoard` and duplicated the engine by hand, so
 * nothing caught a drift. They now live here, are unit tested by
 * `movement.test.ts`, and that test uses the same table as the backend test
 * `test/test_movement_rules.py` — if the engine changes, one of the two fails.
 *
 * Mirrors `GameService._calculate_new_position` and
 * `GameService._is_home_position_available` (`app/services/game_service.py`).
 */
import { HOME_END, HOME_START } from "./boardCoordinates.ts";

/** Board position of a piece that has not been released from its yard yet. */
export const YARD_POSITION = -1;

export interface MoveTarget {
  /** True when the dice value may legally advance this piece. */
  valid: boolean;
  /** Position the piece would occupy; the current one when the move is invalid. */
  position: number;
}

/**
 * Position a piece reaches after `dice`, ignoring other pieces.
 *
 * Leaving the yard needs a six; on the track a move may not overshoot the goal
 * cell, so `current + dice` stops at `HOME_END`.
 */
export function nextPosition(current: number, dice: number): MoveTarget {
  if (current === YARD_POSITION) {
    return dice === 6 ? { valid: true, position: 0 } : { valid: false, position: current };
  }

  const target = current + dice;
  if (target <= HOME_END) {
    return { valid: true, position: target };
  }
  return { valid: false, position: current };
}

/**
 * Whether a home-column cell is free for `pieceIndex`.
 *
 * Home cells hold a single piece; track cells may be shared (and the engine
 * resolves the capture).
 */
export function isHomeCellFree(
  pieces: readonly number[],
  pieceIndex: number,
  position: number,
): boolean {
  if (position < HOME_START || position > HOME_END) {
    return true;
  }
  return pieces.every(
    (otherPosition, index) => index === pieceIndex || otherPosition !== position,
  );
}

/** True when `pieceIndex` may legally move with `dice`. */
export function canMovePiece(
  pieces: readonly number[],
  pieceIndex: number,
  dice: number | null,
): boolean {
  if (dice === null) return false;
  const current = pieces[pieceIndex];
  if (current === undefined) return false;

  const target = nextPosition(current, dice);
  if (!target.valid) return false;
  return isHomeCellFree(pieces, pieceIndex, target.position);
}
