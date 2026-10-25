/**
 * Geometry helpers for the piece hop animation.
 *
 * Pieces are positioned with `transform: translate3d()`, which the compositor
 * animates without a layout or paint pass. These helpers turn a logical step
 * range into the per-cell transform values so a single Web Animation can hop a
 * piece across the board while React renders the final position only once.
 */
export interface GridPoint {
  r: number;
  c: number;
}

export interface CellGeometry {
  /** Size of one grid cell in pixels (one eleventh of the board). */
  pitch: number;
  /** Rendered diameter of a piece in pixels. */
  size: number;
  /** Horizontal/vertical nudge used to fan out stacked pieces. */
  overlap: number;
}

/** How long one cell of the hop takes, in milliseconds. */
export const HOP_STEP_MS = 140;

/**
 * How long a piece takes to fly between the board and its base, in ms.
 *
 * A capture and a release are not a walk along the track, so they do not scale
 * with the distance: one straight flight of the same length every time.
 */
export const TRANSIT_MS = 320;

/** Transform that centres a piece inside `point`. */
export function pieceTransform(point: GridPoint, geometry: CellGeometry): string {
  const { pitch, size, overlap } = geometry;
  const x = point.c * pitch + (pitch - size) / 2 + overlap;
  const y = point.r * pitch + (pitch - size) / 2 - overlap;
  return `translate3d(${x}px, ${y}px, 0)`;
}

/**
 * Cell coordinates for every position the piece visits, from `from` (the
 * current cell, used as the first keyframe) to `to` (inclusive).
 */
export function hopPoints(
  from: number,
  to: number,
  coordOf: (position: number) => GridPoint,
): GridPoint[] {
  const points: GridPoint[] = [];
  for (let position = from; position <= to; position++) {
    points.push(coordOf(position));
  }
  return points;
}

/** Horizontal offset of a piece inside a stack of `count` pieces. */
export function stackOffset(index: number, count: number, spacing = 5): number {
  if (count <= 1) return 0;
  return (index - (count - 1) / 2) * spacing;
}
