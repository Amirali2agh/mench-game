// front/src/components/GameBoard.tsx
// Complete visual redesign matching the reference Ludo game UI

import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { GameState } from "../types";
import { playerColors } from "../utils/colors";
import {
  HOME_COLUMNS,
  SEAT_CORNERS,
  START_CELLS,
  cornerForSeat,
  getArrowRotation,
  getGridCoordinates,
  goalSideForHomeColumn,
  goalCoord,
  yardSlotCentreForPiece,
  GridCoord,
  seatColorIndex,
  trackOffsetForSeat,
  type Corner,
  type Side,
} from "../utils/boardCoordinates";
import Dice from "./Dice";
import TurnTimer from "./TurnTimer";
import {
  HOP_STEP_MS,
  TRANSIT_MS,
  hopPoints,
  pieceTransform,
  stackOffset,
  type GridPoint,
} from "../utils/pieceMotion";
import { canMovePiece } from "../utils/movement";
import { prefersReducedMotion } from "../utils/motion";
import type { ChatMessage } from "../hooks/useMenschSocket";

interface GameBoardProps {
  gameState: GameState;
  localPlayerId: string;
  onRollDice: () => void;
  onMovePiece: (pieceIndex: number) => void;
  onLeave: () => void;
  chatMessages: ChatMessage[];
  onSendChat: (text: string) => void;
  onPassTurn: () => void;
}

const COLOR_BY_SEAT: Record<number, string> = {
  0: "#F94144", // red
  1: "#277DA1", // blue
  2: "#43AA8B", // green
  3: "#F9C74F", // yellow
};

function getColorForVisualIdx(seat: number): string {
  return COLOR_BY_SEAT[seat] || "#999";
}

/** Grid placement of the four yards, keyed by the corner the seat owns. */
const YARD_CLASSES: Record<Corner, string> = {
  tl: "col-start-1 col-end-5 row-start-1 row-end-5",
  tr: "col-start-8 col-end-12 row-start-1 row-end-5",
  bl: "col-start-1 col-end-5 row-start-8 row-end-12",
  br: "col-start-8 col-end-12 row-start-8 row-end-12",
};

const YARD_CORNERS: Corner[] = ["tl", "tr", "bl", "br"];

/**
 * Side of the goal each triangle belongs to, in colour-seat order.
 *
 * Derived from the home columns rather than from the seat index: a two-player
 * match can seat any colour on any corner, and the triangle has to follow the
 * column that actually leads into the goal.
 */
const GOAL_SIDES: Side[] = HOME_COLUMNS.map(goalSideForHomeColumn);

/** Track cell -> seat, so a cell can be painted without hard-coded coordinates. */
const START_CELL_SEATS = new Map<string, number>(
  START_CELLS.map((cell, seat) => [`${cell.r},${cell.c}`, seat] as const),
);

/** Home column cell -> seat. */
const HOME_CELL_SEATS = new Map<string, number>(
  HOME_COLUMNS.flatMap((cells, seat) =>
    cells.map((cell) => [`${cell.r},${cell.c}`, seat] as const),
  ),
);

/**
 * Cell coordinates (fractional) that a piece is painted at right now.
 *
 * Reading the painted transform instead of the last committed position is what
 * keeps a hop that is superseded mid-flight from jumping: the new keyframes
 * start where the piece actually is.
 */
function paintedPoint(element: HTMLElement, pitch: number): GridPoint | null {
  const matrix = /matrix\(([^)]*)\)/.exec(getComputedStyle(element).transform);
  if (!matrix) return null;
  const parts = matrix[1].split(",").map(Number);
  if (parts.length < 6) return null;
  const pad = (pitch - pitch * 0.8) / 2;
  return { r: (parts[5] - pad) / pitch, c: (parts[4] - pad) / pitch };
}

/** Triangle of the center goal that leads into the home column of a seat. */
function goalTriangleStyle(side: Side, color: string): React.CSSProperties {
  const size = "clamp(8px,1.5vmin,18px)";
  const base: React.CSSProperties = { position: "absolute", width: 0, height: 0 };
  switch (side) {
    case "top":
      return {
        ...base,
        top: 0,
        left: "50%",
        transform: "translateX(-50%)",
        borderLeft: `${size} solid transparent`,
        borderRight: `${size} solid transparent`,
        borderBottom: `${size} solid ${color}`,
      };
    case "bottom":
      return {
        ...base,
        bottom: 0,
        left: "50%",
        transform: "translateX(-50%)",
        borderLeft: `${size} solid transparent`,
        borderRight: `${size} solid transparent`,
        borderTop: `${size} solid ${color}`,
      };
    case "left":
      return {
        ...base,
        left: 0,
        top: "50%",
        transform: "translateY(-50%)",
        borderTop: `${size} solid transparent`,
        borderBottom: `${size} solid transparent`,
        borderRight: `${size} solid ${color}`,
      };
    case "right":
      return {
        ...base,
        right: 0,
        top: "50%",
        transform: "translateY(-50%)",
        borderTop: `${size} solid transparent`,
        borderBottom: `${size} solid transparent`,
        borderLeft: `${size} solid ${color}`,
      };
  }
}

/** The glass disc every piece is drawn with (board, base and in-flight). */
const PieceDisc: React.FC<{ color: string; className?: string }> = ({
  color,
  className = "",
}) => (
  <div
    className={`rounded-full bg-white shadow-[0_3px_8px_rgba(0,0,0,0.25)] flex items-center justify-center relative ${className}`}
  >
    <div
      className="w-[70%] h-[70%] rounded-full relative overflow-hidden"
      style={{ backgroundColor: color }}
    >
      <div className="absolute inset-0 bg-gradient-to-br from-white/40 via-white/10 to-transparent rounded-full" />
    </div>
    <div className="absolute top-[8%] left-[15%] w-[30%] h-[20%] rounded-full bg-white/60 blur-[1px] rotate-[-20deg]" />
  </div>
);

const PlayerAvatar: React.FC<{ name: string; avatar?: string }> = ({
  name,
  avatar,
}) => {
  const initials = name?.charAt(0) || "?";
  return (
    <div className="w-[42px] h-[42px] rounded-full bg-gradient-to-br from-slate-200 to-slate-300 flex items-center justify-center overflow-hidden shadow-inner text-slate-600 font-bold text-lg">
      {avatar ? (
        <img src={avatar} alt={name} className="w-full h-full object-cover" />
      ) : (
        initials
      )}
    </div>
  );
};

const BoardGrid = React.memo(function BoardGrid() {
  // The 89 board cells never change: memoising them keeps rolls, hops and the
  // turn timer from reconciling the grid on every state update.
  return (
    <>
        {Array.from({ length: 11 }).map((_, rIdx) => {
          return Array.from({ length: 11 }).map((_, cIdx) => {
            if (rIdx < 4 && cIdx < 4) return null;
            if (rIdx < 4 && cIdx >= 7) return null;
            if (rIdx >= 7 && cIdx < 4) return null;
            if (rIdx >= 7 && cIdx >= 7) return null;

            if (rIdx === goalCoord.r && cIdx === goalCoord.c) {
              return (
                <div
                  key={`cell-${rIdx}-${cIdx}`}
                  className="col-start-6 col-end-7 row-start-6 row-end-7 flex items-center justify-center relative"
                >
                  <div className="w-full h-full rounded-lg overflow-hidden relative">
                    {GOAL_SIDES.map((side, colorSeat) => (
                      <div
                        key={`goal-${side}`}
                        style={goalTriangleStyle(
                          side,
                          `${getColorForVisualIdx(colorSeat)}66`,
                        )}
                      />
                    ))}
                    <div className="absolute inset-[25%] rounded-full bg-[#E8D3B0]/50 border border-[#D4C4A0]" />
                  </div>
                </div>
              );
            }

            const cellKey = `${rIdx},${cIdx}`;
            const startSeat = START_CELL_SEATS.get(cellKey);
            const homeSeat = HOME_CELL_SEATS.get(cellKey);
            const isPlainCell =
              startSeat === undefined && homeSeat === undefined;
            const cellBackground =
              startSeat !== undefined
                ? getColorForVisualIdx(startSeat)
                : homeSeat !== undefined
                  ? `${getColorForVisualIdx(homeSeat)}4D`
                  : undefined;

            const arrowRotation = getArrowRotation({
              r: rIdx,
              c: cIdx,
            });

            return (
              <div
                key={`cell-${rIdx}-${cIdx}`}
                style={{
                  gridRowStart: rIdx + 1,
                  gridColumnStart: cIdx + 1,
                  backgroundColor: cellBackground,
                }}
                className={`rounded-full border ${
                  isPlainCell
                    ? "border-[#D4C4A0]/60 shadow-[0_1px_2px_rgba(0,0,0,0.08)]"
                    : homeSeat !== undefined
                      ? "border-transparent"
                      : "border-white/40 shadow-inner"
                } flex items-center justify-center relative transition-colors duration-300 aspect-square p-[0.15vmin]`}
              >
                {isPlainCell ? (
                  <svg
                    className={`w-2/5 h-2/5 text-[#C4B89A]/60 ${arrowRotation}`}
                    fill="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path d="M8 5v14l11-7z" />
                  </svg>
                ) : null}
              </div>
            );
          });
        })}
    </>
  );
});

export const GameBoard: React.FC<GameBoardProps> = ({
  gameState,
  localPlayerId,
  onRollDice,
  onMovePiece,
  onLeave,
  chatMessages,
  onSendChat,
  onPassTurn,
}) => {
  const [isSpinning, setIsSpinning] = useState(false);
  const [chatInput, setChatInput] = useState("");
  const [leaveConfirmOpen, setLeaveConfirmOpen] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const lastRollSignatureRef = useRef<string | null>(null);
  const [visibleRoll, setVisibleRoll] = useState<{
    playerId: string;
    value: number;
  } | null>(null);
  const [rollingRollId, setRollingRollId] = useState<number | null>(null);

  // Every hook below must run on every render, so derive safe values first and
  // only then render the loading state.
  const players = useMemo(() => gameState?.players ?? [], [gameState?.players]);
  const pieces = useMemo(() => gameState?.pieces ?? {}, [gameState?.pieces]);
  const pieces_count = gameState?.pieces_count ?? 4;
  const current_turn = gameState?.current_turn ?? 0;
  const lastRoll = gameState?.last_roll ?? null;
  const localPlayerIdx = players.findIndex((p) => p?.id === localPlayerId);
  const isMyTurn = current_turn === localPlayerIdx;
  const localDice = gameState?.dice ?? null;

  // Keep an automatic pass result visible briefly, even after current_turn advances.
  useEffect(() => {
    if (!lastRoll) {
      setVisibleRoll(null);
      return;
    }

    const signature = String(
      lastRoll.roll_id ?? `${lastRoll.player_id}:${lastRoll.value}`,
    );
    if (lastRollSignatureRef.current === signature) return;

    lastRollSignatureRef.current = signature;
    setVisibleRoll({ playerId: lastRoll.player_id, value: lastRoll.value });
    const rollId = lastRoll.roll_id ?? 0;
    setRollingRollId(rollId);
    const timer = window.setTimeout(
      () =>
        setRollingRollId((current) => (current === rollId ? null : current)),
      1300,
    );
    return () => window.clearTimeout(timer);
  }, [lastRoll]);

  // ═══ Step-by-step piece animation state ═══
  const realPositionsRef = useRef<Record<string, number>>({});
  const [visualPositions, setVisualPositions] = useState<
    Record<string, number>
  >({});
  const pieceRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const animationsRef = useRef<Map<string, Animation>>(new Map());
  /** Track positions a running hop started and ends at, for the next state. */
  const hopMetaRef = useRef<Map<string, { from: number; to: number }>>(new Map());
  const [animInitialized, setAnimInitialized] = useState(false);

  /**
   * Flights between the board and a base (a capture or, later, a release).
   * They are not walks along the track: the piece leaves the cell grid, so the
   * destination element is suppressed until the flight lands.
   */
  interface Transit {
    key: string;
    from: GridPoint;
    to: GridPoint;
    /** Board position committed when the flight lands (-1 = back in the base). */
    target: number;
    /**
     * A released piece has no element on the board yet, so the flight is drawn
     * by a stand-in that the overlay mounts at the base.
     */
    ghost: boolean;
  }
  const [transits, setTransits] = useState<Record<string, Transit>>({});
  const startedTransitsRef = useRef<Set<string>>(new Set());

  // Auto-scroll chat to bottom on new messages
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);


  const getVisualIdx = (backendIdx: number) => {
    // Player indices are also the color indices. Keep a piece on its own
    // home stretch after the four-player board layout changes.
    return backendIdx;
  };

  const allRenderedPieces: {
    playerIdx: number;
    vIdx: number;
    playerId: string;
    pieceIdx: number;
    pos: number;
    visualPos: number;
    coord: GridCoord;
    /** True while this piece is drawn flying out of its base. */
    ghost: boolean;
    /** Position inside the stack of pieces sharing a cell. */
    stackIndex: number;
    stackCount: number;
  }[] = [];
  players.forEach((player, playerIdx) => {
    if (!player) return;
    const vIdx = getVisualIdx(playerIdx);
    const playerPieces = pieces[player.id] || [];
    for (let i = 0; i < (pieces_count || 4); i++) {
      const realPos = playerPieces[i] !== undefined ? playerPieces[i] : -1;
      const key = `${player.id}-${i}`;
      const transit = transits[key];
      const ghost = transit?.ghost ? transit : null;
      // A released piece is not on the board yet: the stand-in draws it coming
      // out of the base, and the real piece takes over when the flight lands.
      const visualPos = ghost ? -1 : (visualPositions[key] ?? realPos);
      const coord = ghost
        ? ghost.from
        : getGridCoordinates(
            vIdx,
            visualPos,
            trackOffsetForSeat(gameState.track_offsets, vIdx),
          );
      allRenderedPieces.push({
        playerIdx,
        vIdx,
        playerId: player.id,
        pieceIdx: i,
        pos: realPos,
        visualPos,
        coord,
        ghost: Boolean(ghost),
        stackIndex: 0,
        stackCount: 1,
      });
    }
  });

  // Group pieces by cell in one pass instead of filtering the whole list for
  // every piece, and remember each piece's fan-out position.
  const stackCounts = new Map<string, number>();
  for (const piece of allRenderedPieces) {
    if (piece.visualPos < 0) continue;
    const cellKey = `${piece.coord.r},${piece.coord.c}`;
    piece.stackIndex = stackCounts.get(cellKey) ?? 0;
    stackCounts.set(cellKey, piece.stackIndex + 1);
  }
  for (const piece of allRenderedPieces) {
    if (piece.visualPos < 0) continue;
    piece.stackCount =
      stackCounts.get(`${piece.coord.r},${piece.coord.c}`) ?? 1;
  }

  const isPieceMovable = useCallback(
    (pieceIdx: number): boolean => {
      if (!isMyTurn || !gameState?.dice_rolled) return false;
      // The rules live in utils/movement.ts next to the test that mirrors the
      // engine, so the board cannot drift from the backend's legality checks.
      return canMovePiece(pieces[localPlayerId] || [], pieceIdx, localDice);
    },
    [gameState?.dice_rolled, isMyTurn, localDice, localPlayerId, pieces],
  );

  const autoActionRollRef = useRef<string | null>(null);
  useEffect(() => {
    if (!isMyTurn || !gameState?.dice_rolled || localDice === null) {
      autoActionRollRef.current = null;
      return;
    }

    const myPieces = pieces[localPlayerId] || [];
    const movablePieces = myPieces
      .map((_, pieceIdx) => pieceIdx)
      .filter(isPieceMovable);

    if (movablePieces.length !== 1) {
      autoActionRollRef.current = null;
      return;
    }

    const rollKey = `${current_turn}:${localDice}:${myPieces.join(",")}`;
    if (autoActionRollRef.current === rollKey) return;

    autoActionRollRef.current = rollKey;
    const timer = window.setTimeout(() => {
      onMovePiece(movablePieces[0]);
    }, 1300);

    return () => window.clearTimeout(timer);
  }, [
    current_turn,
    gameState?.dice_rolled,
    isPieceMovable,
    isMyTurn,
    localDice,
    localPlayerId,
    onMovePiece,
    pieces,
  ]);

  const handleDiceClick = () => {
    if (!isMyTurn || isSpinning || gameState?.dice_rolled) return;
    setIsSpinning(true);
    onRollDice();
  };

  // Stop spinning when the WebSocket confirms the roll result
  useEffect(() => {
    if (
      isSpinning &&
      gameState.dice !== null
    ) {
      const timer = setTimeout(() => setIsSpinning(false), 1300);
      return () => clearTimeout(timer);
    }
  }, [isSpinning, gameState.dice]);

  // ═══ 45s turn timer ═══
  // The countdown itself lives in <TurnTimer>, so its 1 s ticks never re-render
  // the board.
  const hasActedRef = useRef(false);

  // ═══ Board measurement for piece animation ═══
  const boardRef = useRef<HTMLDivElement>(null);
  const [cellPitch, setCellPitch] = useState(0);

  useLayoutEffect(() => {
    const board = boardRef.current;
    if (!board) return;
    const measure = () => {
      const grid = board.querySelector(".grid");
      if (!grid) return;
      const rect = grid.getBoundingClientRect();
      setCellPitch(rect.width / 11);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(board);
    return () => ro.disconnect();
  }, []);

  // Animate moves with one Web Animation per piece. The piece hops cell by
  // cell on the compositor and React commits the final positions once when the
  // hop ends, so a move costs two board renders instead of one per cell.
  useEffect(() => {
    if (!gameState?.pieces || !players.length) return;

    if (!animInitialized) {
      const initial: Record<string, number> = {};
      players.forEach((player) => {
        if (!player) return;
        const playerPieces = pieces[player.id] || [];
        for (let i = 0; i < (pieces_count || 4); i++) {
          const key = `${player.id}-${i}`;
          const pos = playerPieces[i] !== undefined ? playerPieces[i] : -1;
          initial[key] = pos;
          realPositionsRef.current[key] = pos;
        }
      });
      setVisualPositions(initial);
      setAnimInitialized(true);
      return;
    }

    const immediate: Record<string, number> = {};

    players.forEach((player, seat) => {
      if (!player) return;
      const playerPieces = pieces[player.id] || [];
      for (let i = 0; i < (pieces_count || 4); i++) {
        const key = `${player.id}-${i}`;
        const to = playerPieces[i] !== undefined ? playerPieces[i] : -1;
        const from = realPositionsRef.current[key];
        realPositionsRef.current[key] = to;
        if (from === undefined || from === to) continue;

        const element = pieceRefs.current.get(key);

        // A capture and a release leave the cell grid: one flight between the
        // piece's cell (or nothing, when it is still in the base) and its base
        // slot. The destination is suppressed until the flight lands.
        if (
          (from < 0 || to < 0) &&
          cellPitch > 0 &&
          (from < 0 || element) &&
          !prefersReducedMotion()
        ) {
          const seatVIdx = getVisualIdx(seat);
          const offset = trackOffsetForSeat(gameState.track_offsets, seatVIdx);
          const base = yardSlotCentreForPiece(gameState.track_offsets, seat, i);
          const released = from < 0;
          setTransits((previous) => ({
            ...previous,
            [key]: {
              key,
              from: released ? base : getGridCoordinates(seatVIdx, from, offset),
              to: to < 0 ? base : getGridCoordinates(seatVIdx, to, offset),
              target: to,
              ghost: released,
            },
          }));
          // The stand-in draws a released piece; the real one appears on
          // landing. A captured piece keeps its element until the flight ends.
          if (released) immediate[key] = -1;
          continue;
        }

        if (!element || cellPitch <= 0 || to <= from || prefersReducedMotion()) {
          immediate[key] = to;
          continue;
        }

        const seatVIdx = getVisualIdx(seat);
        const coordOf = (position: number) =>
          getGridCoordinates(
            seatVIdx,
            position,
            trackOffsetForSeat(gameState.track_offsets, seatVIdx),
          );

        // A newer state supersedes the hop that is still in flight. Start the
        // replacement where the piece is painted, not at the previous target:
        // otherwise the piece teleports forward and skips the cells it has not
        // walked yet.
        const inFlight = animationsRef.current.get(key);
        const inFlightMeta = hopMetaRef.current.get(key);
        let startPosition = from;
        const painted = inFlight ? paintedPoint(element, cellPitch) : null;
        if (inFlight && inFlightMeta) {
          const timing = inFlight.effect?.getComputedTiming();
          const progress =
            typeof timing?.progress === "number" ? timing.progress : 1;
          const position =
            inFlightMeta.from + (inFlightMeta.to - inFlightMeta.from) * progress;
          startPosition = Math.min(
            to,
            Math.max(inFlightMeta.from, Math.ceil(position - 1e-3)),
          );
        }
        inFlight?.cancel();
        animationsRef.current.delete(key);
        hopMetaRef.current.delete(key);

        const cells = hopPoints(startPosition, to, coordOf);
        const points = painted ? [painted, ...cells] : cells;
        const geometry = { pitch: cellPitch, size: cellPitch * 0.8, overlap: 0 };
        const animation = element.animate(
          points.map((point) => ({ transform: pieceTransform(point, geometry) })),
          { duration: HOP_STEP_MS * (points.length - 1), easing: "linear" },
        );
        animationsRef.current.set(key, animation);
        hopMetaRef.current.set(key, { from: startPosition, to });
        const finalTransform = pieceTransform(points[points.length - 1], geometry);
        void animation.finished.then(
          () => {
            animationsRef.current.delete(key);
            hopMetaRef.current.delete(key);
            // Pin the finished position first: a render that lands before the
            // commit must not snap the piece back for a frame.
            element.style.transform = finalTransform;
            setVisualPositions((prev) => ({ ...prev, [key]: to }));
          },
          () => {
            // cancelled: the newer state decides the position
            hopMetaRef.current.delete(key);
          },
        );
      }
    });

    if (Object.keys(immediate).length) {
      setVisualPositions((prev) => ({ ...prev, ...immediate }));
    }
  }, [
    animInitialized,
    cellPitch,
    gameState?.pieces,
    gameState?.track_offsets,
    pieces,
    pieces_count,
    players,
  ]);

  // One straight flight from the board to the base, or the other way round.
  useLayoutEffect(() => {
    if (cellPitch <= 0) return;
    const geometry = { pitch: cellPitch, size: cellPitch * 0.8, overlap: 0 };

    Object.values(transits).forEach((transit) => {
      if (startedTransitsRef.current.has(transit.key)) return;
      const element = pieceRefs.current.get(transit.key);

      const land = (pin: boolean) => {
        startedTransitsRef.current.delete(transit.key);
        animationsRef.current.delete(transit.key);
        if (pin && element) {
          element.style.transform = pieceTransform(transit.to, geometry);
        }
        // A newer state may already own this piece: only commit our target if
        // nothing has moved it since the flight started.
        if (realPositionsRef.current[transit.key] === transit.target) {
          setVisualPositions((previous) => ({
            ...previous,
            [transit.key]: transit.target,
          }));
        }
        setTransits((previous) => {
          if (!previous[transit.key]) return previous;
          const next = { ...previous };
          delete next[transit.key];
          return next;
        });
      };

      if (!element) {
        // Nothing to draw (the piece unmounted mid-flight): just commit.
        land(false);
        return;
      }

      startedTransitsRef.current.add(transit.key);
      const animation = element.animate(
        [
          { transform: pieceTransform(transit.from, geometry) },
          { transform: pieceTransform(transit.to, geometry) },
        ],
        { duration: TRANSIT_MS, easing: "cubic-bezier(0.4, 0, 0.2, 1)" },
      );
      animationsRef.current.set(transit.key, animation);

      void animation.finished.then(
        () => land(true),
        () => land(false), // cancelled: the newer state decides the position
      );
    });
  }, [cellPitch, transits]);

  // Cancel hops that are still running when the board unmounts.
  useEffect(() => {
    const animations = animationsRef.current;
    return () => {
      animations.forEach((animation) => animation.cancel());
      animations.clear();
    };
  }, []);

  useEffect(() => {
    hasActedRef.current = false;
    setIsSpinning(false);
  }, [gameState?.current_turn, gameState?.status]);

  const handleTurnTimeout = useCallback(() => {
    if (current_turn === localPlayerIdx && !hasActedRef.current) {
      onPassTurn();
    }
  }, [current_turn, localPlayerIdx, onPassTurn]);

  useEffect(() => {
    // Drive the latch from the roll flag only: a leftover dice value must never
    // mark the next player's turn as already acted upon.
    if (gameState?.dice_rolled) {
      hasActedRef.current = true;
    }
  }, [gameState?.dice_rolled]);

  if (!gameState || !gameState.players || !gameState.pieces) {
    return (
      <div className="fixed inset-0 bg-[#F9F6F0] flex items-center justify-center">
        <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-b-2 border-amber-500"></div>
      </div>
    );
  }

  const trackOffsets = gameState.track_offsets;
  /** Canonical color seat (red/blue/green/yellow) of a seat. */
  const colorSeatOf = (seat: number) => seatColorIndex(trackOffsets, seat);
  const colorOfSeat = (seat: number) => getColorForVisualIdx(colorSeatOf(seat));


  const getPlayerPanelPosition = (playerIdx: number): Corner | null => {
    if (!players[playerIdx]) return null;
    return cornerForSeat(gameState.track_offsets, playerIdx);
  };

  const renderBaseYard = (colorSeat: number) => {
    const theme = playerColors[colorSeat];
    if (!theme) return null;
    const ownerIdx = players.findIndex((_, i) => colorSeatOf(i) === colorSeat);
    const isOwned = ownerIdx !== -1;
    const isPlayerActive = isOwned && current_turn === ownerIdx;
    const color = getColorForVisualIdx(colorSeat);

    return (
      <div
        className={`w-full h-full rounded-[clamp(8px,1.5vmin,18px)] ${theme.bg} border-[clamp(1px,0.2vmin,2.5px)] ${
          isPlayerActive
            ? "border-amber-400 shadow-[0_0_16px_rgba(251,191,36,0.4)]"
            : "border-white/20"
        } ${!isOwned ? "opacity-30 grayscale" : ""} flex items-center justify-center relative shadow-[inset_0_4px_10px_rgba(0,0,0,0.15)] transition-colors duration-300`}
      >
        <div className="grid grid-cols-2 grid-rows-2 gap-[clamp(3px,0.5vmin,8px)] p-[clamp(4px,0.8vmin,12px)] w-full h-full">
          {Array.from({ length: 4 }).map((_, idx) => {
            const slotKey =
              ownerIdx >= 0 && players[ownerIdx]
                ? `${players[ownerIdx].id}-${idx}`
                : "";
            // A captured piece is still flying towards the base: do not draw a
            // second copy there until it lands.
            const slotTaken =
              ownerIdx >= 0 &&
              players[ownerIdx] &&
              pieces[players[ownerIdx].id]?.[idx] === -1 &&
              !transits[slotKey];
            const isMovablePiece =
              ownerIdx === localPlayerIdx &&
              slotTaken &&
              isMyTurn &&
              localDice === 6 &&
              gameState.dice_rolled;
            return (
              <div
                key={idx}
                className="w-full h-full rounded-full bg-black/15 shadow-[inset_0_2px_6px_rgba(0,0,0,0.3)] border border-white/5 flex items-center justify-center relative"
              >
                {slotTaken && (
                  <div
                    role="button"
                    tabIndex={isMovablePiece ? 0 : -1}
                    aria-disabled={!isMovablePiece}
                    aria-label={`مهره ${idx + 1} در پایه`}
                    onClick={() => isMovablePiece && onMovePiece(idx)}
                    onKeyDown={(event) => {
                      if (!isMovablePiece) return;
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onMovePiece(idx);
                      }
                    }}
                    className={`w-[80%] h-[80%] relative ${
                      isMovablePiece
                        ? "cursor-pointer z-30 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-white rounded-full"
                        : ""
                    }`}
                  >
                    <PieceDisc
                      color={color}
                      className={`w-full h-full ${
                        isMovablePiece
                          ? "motion-safe:animate-bounce ring-2 ring-amber-400 ring-offset-1 ring-offset-transparent"
                          : ""
                      }`}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  const renderPlayerPanel = (playerIdx: number) => {
    const pos = getPlayerPanelPosition(playerIdx);
    if (!pos || !players[playerIdx]) return null;
    const p = players[playerIdx];
    const color = colorOfSeat(playerIdx);
    const isTurn = current_turn === playerIdx;

    return (
      <div
        className={`flex items-center gap-2 ${pos === "tr" || pos === "br" ? "flex-row-reverse" : ""}`}
      >
        <div
          className={`flex items-center gap-2 bg-white rounded-full shadow-[0_6px_16px_rgba(0,0,0,0.06)] px-2 py-1 ${isTurn ? "ring-2 ring-amber-400/60" : ""}`}
        >
          <div className="relative w-[42px] h-[42px] flex items-center justify-center">
            <TurnTimer
              active={isTurn && gameState.status === "playing"}
              resetKey={`${current_turn}:${gameState.status}`}
              onTimeout={handleTurnTimeout}
            />
            <PlayerAvatar name={p.name} avatar={p.avatar} />
            <div
              className="absolute -bottom-0.5 -right-0.5 w-[10px] h-[10px] rounded-full border-2 border-white"
              style={{ backgroundColor: color }}
            />
          </div>
          <div className="flex flex-col items-start leading-tight">
            <span className="text-[13px] font-semibold text-[#2C2C2C] whitespace-nowrap">
              {p.name}
            </span>
            <div className="flex items-center gap-1">
              <div
                className="w-[6px] h-[6px] rounded-full"
                style={{ backgroundColor: color }}
              />
            </div>
          </div>
        </div>
        {visibleRoll?.playerId === p.id && (
          <Dice
            key={`${p.id}-${gameState.last_roll?.roll_id ?? "legacy"}`}
            value={
              isTurn && gameState.dice_rolled && gameState.dice !== null
                ? gameState.dice
                : visibleRoll.value
            }
            isRolling={
              rollingRollId === (gameState.last_roll?.roll_id ?? 0) ||
              (isTurn && isSpinning)
            }
            rollId={gameState.last_roll?.roll_id}
          />
        )}
      </div>
    );
  };

  const playerAtCorner = (corner: Corner) =>
    players.findIndex(
      (_, seat) => cornerForSeat(gameState.track_offsets, seat) === corner,
    );
  const tlPlayer = playerAtCorner("tl");
  const trPlayer = playerAtCorner("tr");
  const blPlayer = playerAtCorner("bl");
  const brPlayer = playerAtCorner("br");

  return (
    <div className="min-h-screen w-full flex flex-col bg-[#F9F6F0] font-sans">
      {/* ═══ TOP HEADER ═══ */}
      <header className="flex items-center justify-between px-4 pt-3 pb-1">
        <button
          type="button"
          onClick={() => setLeaveConfirmOpen(true)}
          aria-label="خروج از بازی"
          className="w-[44px] h-[44px] bg-white rounded-full shadow-[0_4px_10px_rgba(0,0,0,0.05)] flex items-center justify-center active:scale-90 transition-transform focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500"
        >
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="#333"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="12" cy="5" r="1" />
            <circle cx="12" cy="12" r="1" />
            <circle cx="12" cy="19" r="1" />
          </svg>
        </button>

        <div className="bg-white rounded-full shadow-[0_4px_12px_rgba(0,0,0,0.04)] px-6 py-2">
          <span className="text-[15px] font-bold text-[#2C2C2C]">
            منچ آنلاین
          </span>
        </div>

        {/* Keeps the title centred; the old star looked like a button but did nothing. */}
        <div aria-hidden="true" className="w-[44px] h-[44px]" />
      </header>

      {/* ═══ MAIN AREA: Player panels + Board + Dice ═══ */}
      <main className="flex-1 flex flex-col px-2">
        {/* Top players row */}
        <div className="grid grid-cols-2 items-start w-full max-w-[480px] mx-auto px-1 pt-1 pb-1 min-h-[52px]">
          <div className="flex justify-start">
            {tlPlayer >= 0 && renderPlayerPanel(tlPlayer)}
          </div>
          <div className="flex justify-end">
            {trPlayer >= 0 && renderPlayerPanel(trPlayer)}
          </div>
        </div>

        {/* Board + Bottom players */}
        <div className="flex-1 flex flex-col items-center justify-center gap-1 min-h-0">
          {/* Board */}
          <div
            ref={boardRef}
            // The board is a coordinate plane, not text: pin it to LTR so the
            // grid columns and `pieceTransform()` both grow to the right. The
            // document stays RTL for the copy around the board.
            dir="ltr"
            className="relative w-[min(88vw,78vh)] aspect-square max-w-[480px] bg-[#FAF4E6] rounded-[clamp(16px,3vmin,28px)] p-[clamp(8px,1.5vmin,16px)] shadow-[0_16px_36px_rgba(0,0,0,0.08),inset_0_2px_6px_rgba(255,255,255,0.6)] border-[clamp(2px,0.4vmin,4px)] border-[#E8D3B0] flex items-center justify-center"
          >
            <div className="relative w-full h-full">
              <div className="grid grid-cols-11 grid-rows-11 gap-[0.35vmin] w-full h-full relative">
                {/* Yards */}
                {YARD_CORNERS.map((corner) => {
                  const ownerSeat = players.findIndex(
                    (_, seat) =>
                      cornerForSeat(gameState.track_offsets, seat) === corner,
                  );
                  // Empty seats keep a dimmed yard in their canonical color.
                  const yardSeat =
                    ownerSeat >= 0 ? ownerSeat : SEAT_CORNERS.indexOf(corner);
                  return (
                    <div
                      key={`yard-${corner}`}
                      className={`${YARD_CLASSES[corner]} p-[0.3vmin]`}
                    >
                      {renderBaseYard(yardSeat)}
                    </div>
                  );
                })}
                {/* Unused corners are dimmed by renderBaseYard itself. */}
                <div className="absolute inset-0 bg-white/30 rounded-xl pointer-events-none -z-10" />
                <BoardGrid />
              </div>

              {/* ═══ Animated piece overlay ═══ */}
              {cellPitch > 0 &&
                allRenderedPieces.filter((p) => p.visualPos >= 0 || p.ghost)
                  .length > 0 && (
                  <div
                    className="absolute inset-0 z-20"
                    style={{ pointerEvents: "none" }}
                  >
                    {allRenderedPieces
                      .filter((p) => p.visualPos >= 0 || p.ghost)
                      .map(({
                        vIdx,
                        playerId: pId,
                        pieceIdx,
                        coord,
                        ghost,
                        stackIndex,
                        stackCount,
                      }) => {
                        const theme = playerColors[colorSeatOf(vIdx)];
                        if (!theme) return null;
                        const isMovable =
                          !ghost &&
                          pId === localPlayerId &&
                          isPieceMovable(pieceIdx);

                        const pieceSize = cellPitch * 0.8;
                        const overlapOffset = stackOffset(stackIndex, stackCount);
                        const color = colorOfSeat(vIdx);

                        return (
                          <div
                            key={`piece-${pId}-${pieceIdx}`}
                            role="button"
                            tabIndex={isMovable ? 0 : -1}
                            aria-disabled={!isMovable}
                            aria-label={`مهره ${pieceIdx + 1}`}
                            data-piece={pieceIdx + 1}
                            onKeyDown={(event) => {
                              if (!isMovable) return;
                              if (event.key === "Enter" || event.key === " ") {
                                event.preventDefault();
                                onMovePiece(pieceIdx);
                              }
                            }}
                            ref={(element) => {
                              const key = `${pId}-${pieceIdx}`;
                              if (element) pieceRefs.current.set(key, element);
                              else pieceRefs.current.delete(key);
                            }}
                            // This element owns the placement transform and is
                            // what the hop animates. Decorations (ring, bounce)
                            // live on the inner disc: a CSS animation outranks
                            // an inline style, so putting one here would throw
                            // the piece back to left/top 0.
                            style={{
                              position: "absolute",
                              left: 0,
                              top: 0,
                              width: `${pieceSize}px`,
                              height: `${pieceSize}px`,
                              transform: pieceTransform(coord, {
                                pitch: cellPitch,
                                size: pieceSize,
                                overlap: overlapOffset,
                              }),
                              zIndex:
                                (isMovable ? 1000 : ghost ? 900 : 20) +
                                stackIndex,
                              pointerEvents: ghost ? "none" : "auto",
                            }}
                            onClick={() => isMovable && onMovePiece(pieceIdx)}
                            className="rounded-full focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-white"
                          >
                            <PieceDisc
                              color={color}
                              className={`w-full h-full ${
                                isMovable
                                  ? "cursor-pointer motion-safe:animate-bounce ring-2 ring-amber-400 ring-offset-2"
                                  : ""
                              }`}
                            />
                          </div>
                        );
                      })}
                  </div>
                )}
            </div>
          </div>

          {/* Bottom row: players + roll control (Fixed Centering with 3-column Grid) */}
          <div className="grid grid-cols-[1fr_auto_1fr] items-center w-full max-w-[480px] px-1 pb-1 min-h-[60px]">
            <div className="flex justify-start">
              {blPlayer >= 0 && renderPlayerPanel(blPlayer)}
            </div>

            {/* Roll control */}
            <div className="flex justify-center relative">
              {isMyTurn && !gameState.dice_rolled && !isSpinning && (
                <div className="absolute inset-[-4px] rounded-full bg-amber-400/20 motion-safe:animate-pulse" />
              )}
              {isMyTurn ? (
                <button
                  type="button"
                  onClick={handleDiceClick}
                  disabled={!isMyTurn || isSpinning || gameState.dice_rolled}
                  aria-label="پرتاب تاس"
                  className={`relative min-w-[136px] h-[48px] px-6 rounded-full bg-[#C17D3C] text-white font-bold text-[15px] shadow-[0_8px_18px_rgba(193,125,60,0.28)] border-2 border-[#D99A5C] flex items-center justify-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-600 focus-visible:ring-offset-2 ${
                    isMyTurn && !gameState.dice_rolled && !isSpinning
                      ? "hover:bg-[#AE6C31] active:scale-95 transition-transform cursor-pointer"
                      : "opacity-60 cursor-not-allowed"
                  }`}
                >
                  {isSpinning ? "در حال پرتاب..." : "پرتاب تاس"}
                </button>
              ) : (
                <div className="w-[56px] h-[56px]" />
              )}
            </div>

            <div className="flex justify-end">
              {brPlayer >= 0 && renderPlayerPanel(brPlayer)}
            </div>
          </div>
        </div>
      </main>

      {/* ═══ CHAT BAR ═══ */}
      <footer className="px-3 pb-[clamp(4px,1vh,8px)] pt-1">
        {chatMessages.length > 0 && (
          <div className="mx-1 mb-1 max-h-[clamp(60px,8vh,100px)] overflow-y-auto overscroll-contain rounded-xl bg-white/95 shadow-[0_2px_8px_rgba(0,0,0,0.04)] px-3 py-2 space-y-1">
            {chatMessages.map((msg, i) => (
              <div
                key={i}
                className="flex items-start gap-1.5 text-[11px] leading-tight"
              >
                <span
                  className={`font-bold whitespace-nowrap ${msg.player_id === localPlayerId ? "text-amber-600" : "text-slate-600"}`}
                >
                  {msg.player_name}:
                </span>
                <span className="text-slate-700 break-words min-w-0">
                  {msg.message}
                </span>
              </div>
            ))}
            <div ref={chatEndRef} />
          </div>
        )}
        <div className="flex items-center gap-2 bg-white rounded-full shadow-[0_4px_16px_rgba(0,0,0,0.05)] px-4 py-[10px] mx-1">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const trimmed = chatInput.trim();
              if (trimmed) {
                onSendChat(trimmed);
                setChatInput("");
              }
            }}
            className="flex-1 flex items-center gap-2"
          >
            <input
              type="text"
              maxLength={200}
              aria-label="متن پیام"
              placeholder="پیام خود را بنویسید..."
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              className="flex-1 bg-transparent text-[14px] text-[#2C2C2C] placeholder-[#9C9C9C] outline-none text-right"
            />
            <button
              type="submit"
              disabled={!chatInput.trim()}
              aria-label="ارسال پیام"
              className="flex-shrink-0 disabled:opacity-30 transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 rounded"
            >
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="#C17D3C"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </form>
        </div>
      </footer>

      {leaveConfirmOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="leave-confirm-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4 animate-fade-in"
        >
          <div className="w-full max-w-xs rounded-3xl bg-white p-6 text-center shadow-2xl">
            <h2
              id="leave-confirm-title"
              className="mb-2 text-lg font-bold text-[#2C2C2C]"
            >
              خروج از بازی؟
            </h2>
            <p className="mb-6 text-sm leading-relaxed text-slate-600">
              بازی در جریان است و با خروج شما به پایان می‌رسد.
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setLeaveConfirmOpen(false)}
                className="flex-1 rounded-xl bg-slate-100 py-3 text-sm font-bold text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
              >
                انصراف
              </button>
              <button
                type="button"
                onClick={onLeave}
                className="flex-1 rounded-xl bg-rose-500 py-3 text-sm font-bold text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-300"
              >
                خروج
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default GameBoard;
