/**
 * Harness page for the animation suite (`npm run test:anim`).
 *
 * Mounts the real `<GameBoard>` with a synthetic game state and exposes a small
 * imperative API on `window.__lab` so the headless runner in
 * `animation.test.mjs` can drive rolls and moves and then measure what the
 * browser paints. Nothing in here is shipped: the page is only reachable from
 * `animation-lab.html`, which `vite build` never treats as an entry.
 */
import { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { GameBoard } from "../components/GameBoard";
import type { GameState } from "../types";
import "../index.css";

/** Seat the harness plays from (the first player of the fixture). */
const LOCAL_SEAT = 0;

export interface LabApi {
  get: () => GameState;
  load: (next: GameState) => void;
  reset: () => void;
  patch: (partial: Partial<GameState>) => void;
  /** Replace one seat's piece positions. */
  setPieces: (seat: number, positions: number[]) => void;
  /** Move one local piece, like the server would, and forget the dice. */
  move: (pieceIndex: number, to: number, keepDice?: boolean) => void;
  /** Apply a roll result without waiting for a socket. */
  roll: (value: number) => void;
}

declare global {
  interface Window {
    __lab?: LabApi;
  }
}

const PLAYER_IDS = ["p0", "p1", "p2", "p3"];

/** A full four-player match with two red pieces already on the track. */
export function initialState(): GameState {
  return {
    room_id: "animation-lab",
    player_count: 4,
    pieces_count: 4,
    players: [
      { id: "p0", name: "قرمز", avatar: "" },
      { id: "p1", name: "آبی", avatar: "" },
      { id: "p2", name: "سبز", avatar: "" },
      { id: "p3", name: "زرد", avatar: "" },
    ],
    current_turn: 0,
    dice: null,
    dice_rolled: false,
    last_roll: null,
    track_offsets: [20, 30, 0, 10],
    pieces: {
      p0: [0, 3, -1, -1],
      p1: [-1, -1, -1, -1],
      p2: [-1, -1, -1, -1],
      p3: [-1, -1, -1, -1],
    },
    status: "playing",
    winner_id: null,
  };
}

const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

/**
 * Build the fixture from the page URL, so every check starts from a **fresh
 * mount** (`animInitialized` is false) and no setup hop is ever animated:
 *
 *   animation-lab.html?pieces=0,5,20,40&turn=1
 */
function stateFromLocation(): GameState {
  const state = initialState();
  if (typeof window === "undefined") return state;

  const params = new URLSearchParams(window.location.search);
  const pieces = params.get("pieces");
  if (pieces !== null) {
    const positions = pieces
      .split(",")
      .map((value) => Number.parseInt(value, 10))
      .filter((value) => Number.isFinite(value));
    state.pieces[PLAYER_IDS[LOCAL_SEAT]] = positions.length ? positions : [-1];
  }

  const turn = params.get("turn");
  if (turn !== null) {
    const parsed = Number.parseInt(turn, 10);
    state.current_turn = Number.isFinite(parsed) ? parsed : 0;
  }
  return state;
}

function Lab() {
  const [state, setState] = useState<GameState>(stateFromLocation);
  // The API reads through this ref so it always sees the newest state without
  // being re-created on every render (which would race with a driver in flight).
  const stateRef = useRef<GameState>(state);
  stateRef.current = state;

  useEffect(() => {
    const mutate = (fn: (draft: GameState) => void) => {
      setState((previous) => {
        const draft = clone(previous);
        fn(draft);
        return draft;
      });
    };

    window.__lab = {
      get: () => clone(stateRef.current),
      load: (next) => setState(clone(next)),
      reset: () => setState(initialState()),
      patch: (partial) => mutate((draft) => Object.assign(draft, clone(partial))),
      setPieces: (seat, positions) =>
        mutate((draft) => {
          draft.pieces[PLAYER_IDS[seat]] = [...positions];
        }),
      move: (pieceIndex, to, keepDice) =>
        mutate((draft) => {
          draft.pieces[PLAYER_IDS[LOCAL_SEAT]][pieceIndex] = to;
          if (!keepDice) {
            draft.dice = null;
            draft.dice_rolled = false;
          }
        }),
      roll: (value) =>
        mutate((draft) => {
          draft.dice = value;
          draft.dice_rolled = true;
          draft.last_roll = {
            player_id: draft.players[draft.current_turn]?.id ?? PLAYER_IDS[0],
            value,
            roll_id: (draft.last_roll?.roll_id ?? 0) + 1,
          };
        }),
    };
    return () => {
      delete window.__lab;
    };
  }, []);

  const handleMovePiece = (pieceIndex: number) => {
    setState((previous) => {
      const draft = clone(previous);
      const current = draft.pieces[PLAYER_IDS[LOCAL_SEAT]][pieceIndex];
      draft.pieces[PLAYER_IDS[LOCAL_SEAT]][pieceIndex] =
        current < 0 ? 0 : current + (draft.dice ?? 0);
      draft.dice_rolled = false;
      return draft;
    });
  };

  return (
    <GameBoard
      gameState={state}
      localPlayerId={PLAYER_IDS[LOCAL_SEAT]}
      onRollDice={() => undefined}
      onMovePiece={handleMovePiece}
      onLeave={() => undefined}
      chatMessages={[]}
      onSendChat={() => undefined}
      onPassTurn={() => undefined}
    />
  );
}

const root = createRoot(document.getElementById("lab-root")!);
root.render(<Lab />);
