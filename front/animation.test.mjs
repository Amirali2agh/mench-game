#!/usr/bin/env node
/**
 * Animation regression suite for the board.
 *
 * It mounts the real `<GameBoard>` (through `animation-lab.html`) in a headless
 * browser and asserts on **what the browser paints**: the rect of every piece,
 * the computed transform, the CSS/Web animations that actually run, and the
 * per-frame path of a hop. Geometry expectations come from the product module
 * (`src/utils/boardCoordinates.ts`), so the checks are the same ones the board
 * itself uses.
 *
 *   npm run test:anim                 # all checks
 *   npm run test:anim -- S1 S5        # only some checks
 *   ANIM_SUITE_URL=http://127.0.0.1:5173 npm run test:anim   # reuse a dev server
 *
 * Needs a browser that puppeteer can launch:
 *   npm i -D puppeteer && npx puppeteer browsers install chrome-headless-shell
 *
 * Deliberately NOT part of `npm test`: it needs a browser, and CI has none yet
 * (issue #24). Seven checks are red on purpose: each one is the acceptance
 * criterion of an open issue (#65-#71) and goes green when that issue is fixed.
 * The remaining four are guards and must stay green.
 */
import { spawn } from "node:child_process";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { existsSync } from "node:fs";

import {
  HOME_COLUMNS,
  getGridCoordinates,
} from "./src/utils/boardCoordinates.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.ANIM_SUITE_PORT || 9910);
const BASE = process.env.ANIM_SUITE_URL || `http://127.0.0.1:${PORT}`;
/** Track offsets the harness fixture uses, in seat order. */
const OFFSETS = [20, 30, 0, 10];
const LOCAL_SEAT = 0;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/* --------------------------------------------------------------- Chromium */
const BROWSER_CANDIDATES = [
  process.env.PUPPETEER_EXECUTABLE_PATH,
  "/home/dev/docs/.puppeteer-cache/chrome-headless-shell/linux-148.0.7778.97/chrome-headless-shell-linux64/chrome-headless-shell",
  "/home/dev/.cache/puppeteer/chrome-headless-shell/linux-148.0.7778.97/chrome-headless-shell-linux64/chrome-headless-shell",
].filter(Boolean);

async function loadPuppeteer() {
  try {
    return (await import("puppeteer")).default;
  } catch {
    console.error(
      "This suite drives a real browser.\n" +
        "  npm i -D puppeteer\n" +
        "  npx puppeteer browsers install chrome-headless-shell\n",
    );
    process.exit(2);
  }
}

async function launchBrowser(puppeteer) {
  const options = {
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
    defaultViewport: { width: 520, height: 900 },
  };
  const executable = BROWSER_CANDIDATES.find((path) => existsSync(path));
  if (executable) options.executablePath = executable;
  try {
    return await puppeteer.launch({ ...options, headless: "shell" });
  } catch {
    return await puppeteer.launch({ ...options, headless: true });
  }
}

/* -------------------------------------------------------------------- lab */
async function waitForLab(timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${BASE}/animation-lab.html`);
      if (response.ok) return;
    } catch {
      /* not up yet */
    }
    await sleep(300);
  }
  throw new Error(`dev server never answered on ${BASE}`);
}

async function startServer() {
  if (process.env.ANIM_SUITE_URL) {
    await waitForLab();
    return null;
  }
  const child = spawn(
    "npx",
    ["vite", "--host", "127.0.0.1", "--port", String(PORT), "--strictPort"],
    { cwd: HERE, stdio: "ignore" },
  );
  await waitForLab();
  return child;
}

/* ----------------------------------------------------------------- probe */
/**
 * Installed into every document. Everything it needs is defined inside, because
 * puppeteer serialises the function to the page.
 */
function installProbe() {
  const grid = () => document.querySelector(".grid.grid-cols-11");
  const overlay = () => document.querySelector("div.absolute.inset-0.z-20");

  /** Every 11x11 cell that is rendered, with its real rect. */
  const cells = () => {
    const root = grid();
    if (!root) return [];
    const board = root.getBoundingClientRect();
    const out = [];
    root.querySelectorAll(":scope > div").forEach((el) => {
      if (!el.style.gridRowStart || !el.style.gridColumnStart) return;
      const box = el.getBoundingClientRect();
      out.push({
        r: Number(el.style.gridRowStart) - 1,
        c: Number(el.style.gridColumnStart) - 1,
        left: box.left - board.left,
        top: box.top - board.top,
        w: box.width,
        h: box.height,
        bg: el.style.backgroundColor || "",
        cx: box.left + box.width / 2,
        cy: box.top + box.height / 2,
      });
    });
    return out;
  };

  const pieces = () => {
    const layer = overlay();
    const root = grid();
    if (!layer || !root) return [];
    const pitch = root.getBoundingClientRect().width / 11;
    const board = layer.getBoundingClientRect();
    const candidates = Array.from(layer.querySelectorAll("div")).filter(
      (element) =>
        element.dataset.piece !== undefined ||
        element.getAttribute("role") === "button",
    );
    return candidates.map((el) => {
      // `data-piece` is the hook the suite uses; the aria-label keeps older
      // markup measurable.
      const label = /^مهره (\d+)$/.exec(el.getAttribute("aria-label") || "");
      const index = el.dataset.piece ?? (label ? label[1] : null);
      const inline = el.style.transform || "";
      const translate = /translate3d\((-?[\d.]+)px,\s*(-?[\d.]+)px/.exec(inline);
      const computed = getComputedStyle(el);
      const matrix = /matrix\(([^)]*)\)/.exec(computed.transform || "");
      const parts = matrix ? matrix[1].split(",").map(Number) : null;
      const box = el.getBoundingClientRect();
      const x = translate ? Number(translate[1]) : 0;
      const y = translate ? Number(translate[2]) : 0;
      const size = box.width;
      // Works whether the highlight lives on this element or on a child: a
      // wrapper-based fix must not make the check blind.
      const highlight = el
        .getAnimations({ subtree: true })
        .some(
          (animation) =>
            typeof CSSAnimation !== "undefined" && animation instanceof CSSAnimation,
        );
      return {
        /** Piece index, 1-based. */
        idx: index === null ? -1 : Number(index),
        highlight,
        inlineX: translate ? x : null,
        inlineY: translate ? y : null,
        /** Cell the component *intends* (decoded from its own transform). */
        tableRow: Math.round((y - (pitch - size) / 2) / pitch),
        tableCol: Math.round((x - (pitch - size) / 2) / pitch),
        computedX: parts ? parts[4] : null,
        computedY: parts ? parts[5] : null,
        computed: computed.transform,
        animationName: computed.animationName,
        zIndex: computed.zIndex,
        relX: +(box.left - board.left).toFixed(2),
        relY: +(box.top - board.top).toFixed(2),
        centerX: box.left + box.width / 2,
        centerY: box.top + box.height / 2,
        size,
      };
    });
  };

  /** Cell each piece is painted over, plus its painted vs intended geometry. */
  const under = () => {
    const cellList = cells();
    return pieces().map((piece) => {
      const covered = cellList.find(
        (cell) =>
          Math.abs(piece.centerX - cell.cx) <= cell.w / 2 &&
          Math.abs(piece.centerY - cell.cy) <= cell.h / 2,
      );
      return {
        idx: piece.idx,
        intended: [piece.tableRow, piece.tableCol],
        covered: covered ? [covered.r, covered.c] : null,
        coveredBg: covered ? covered.bg : null,
        animationName: piece.animationName,
        highlight: piece.highlight,
        zIndex: piece.zIndex,
        computedX: piece.computedX,
        computedY: piece.computedY,
        inlineX: piece.inlineX,
        inlineY: piece.inlineY,
      };
    });
  };

  /** The four translucent corner triangles of the centre goal. */
  const goal = () => {
    const cell = document.querySelector('.grid > div[class*="col-start-6"]');
    if (!cell) return null;
    const box = cell.getBoundingClientRect();
    const wrapper = cell.querySelector("div.rounded-lg.overflow-hidden");
    const triangles = [];
    if (wrapper) {
      Array.from(wrapper.children).forEach((el) => {
        if (el.style.width !== "0px" || el.style.height !== "0px") return;
        const anchor = ["left", "right", "top", "bottom"].find(
          (side) => el.style[side] === "0px",
        );
        const style = getComputedStyle(el);
        // Tailwind's preflight gives every element a grey border colour, so the
        // seat colour is not simply "the non-transparent border".
        triangles.push({
          anchor: anchor || null,
          colors: ["Top", "Right", "Bottom", "Left"].map(
            (side) => style[`border${side}Color`],
          ),
        });
      });
    }
    return {
      cx: box.left + box.width / 2,
      cy: box.top + box.height / 2,
      triangles,
    };
  };

  const isQuiet = () =>
    pieces().every(
      (piece) =>
        piece.computedX !== null &&
        Math.abs(piece.computedX - piece.inlineX) < 0.5 &&
        Math.abs(piece.computedY - piece.inlineY) < 0.5,
    );

  /** Sample every piece on every animation frame. */
  const start = () => {
    const cellList = cells();
    const capture = { frames: [], stop: false };
    window.__animCapture = capture;
    const tick = () => {
      capture.frames.push({
        t: Number(performance.now().toFixed(1)),
        pieces: pieces().map((piece) => {
          let nearest = null;
          let best = Infinity;
          for (const cell of cellList) {
            const distance = Math.hypot(
              cell.cx - piece.centerX,
              cell.cy - piece.centerY,
            );
            if (distance < best) {
              best = distance;
              nearest = cell;
            }
          }
          return {
            idx: piece.idx,
            relX: piece.relX,
            relY: piece.relY,
            cell: nearest ? `${nearest.r},${nearest.c}` : null,
            animationName: piece.animationName,
          };
        }),
      });
      if (!capture.stop) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
    return true;
  };

  window.__probe = { cells, pieces, under, goal, isQuiet, start };
}

/* ------------------------------------------------------------------ driver */
class Driver {
  constructor(page) {
    this.page = page;
  }

  sleep(ms) {
    return sleep(ms);
  }

  lab(method, ...args) {
    return this.page.evaluate(
      (name, parameters) => window.__lab[name](...parameters),
      method,
      args,
    );
  }

  probe(method, ...args) {
    return this.page.evaluate(
      (name, parameters) => window.__probe[name](...parameters),
      method,
      args,
    );
  }

  /** Open a fresh mount with a fixture; no setup hop is ever animated. */
  async open({ pieces = [0, 3, -1, -1], turn = 1 } = {}) {
    const query = new URLSearchParams({
      pieces: pieces.join(","),
      turn: String(turn),
    });
    await this.page.goto(`${BASE}/animation-lab.html?${query}`, {
      waitUntil: "networkidle0",
    });
    await this.page.waitForFunction(() => Boolean(window.__lab), {
      timeout: 20_000,
    });
    const expected = pieces.filter((position) => position >= 0).length;
    await this.page.waitForFunction(
      (count) => window.__probe.pieces().length === count,
      { timeout: 10_000 },
      expected,
    );
    await this.waitQuiet();
  }

  async waitQuiet(timeoutMs = 8000) {
    const deadline = Date.now() + timeoutMs;
    let stable = 0;
    while (Date.now() < deadline) {
      if (await this.probe("isQuiet")) {
        stable += 1;
        if (stable >= 2) return;
      } else {
        stable = 0;
      }
      await sleep(60);
    }
    throw new Error("the board never settled");
  }

  async startSampler() {
    await this.probe("start");
  }

  async stopSampler() {
    return this.page.evaluate(() => {
      window.__animCapture.stop = true;
      return window.__animCapture.frames;
    });
  }
}

/* ----------------------------------------------------------------- frames */
/** Cell sequence of one piece, one entry per cell change. */
function cellSequence(frames, pieceIdx) {
  const sequence = [];
  for (const frame of frames) {
    const piece = frame.pieces.find((entry) => entry.idx === pieceIdx);
    if (!piece || !piece.cell) continue;
    if (!sequence.length || sequence[sequence.length - 1].cell !== piece.cell) {
      sequence.push(piece);
    }
  }
  return sequence;
}

/** Distinct painted positions of one piece, for "did it move at all" checks. */
function paintedPositions(frames, pieceIdx) {
  const seen = new Set();
  for (const frame of frames) {
    const piece = frame.pieces.find((entry) => entry.idx === pieceIdx);
    seen.add(piece ? `${piece.relX},${piece.relY}` : "absent");
  }
  return [...seen];
}

function assertAdjacentCells(sequence, label) {
  for (let index = 1; index < sequence.length; index += 1) {
    const [row, column] = sequence[index - 1].cell.split(",").map(Number);
    const [nextRow, nextColumn] = sequence[index].cell.split(",").map(Number);
    const distance =
      Math.abs(row - nextRow) + Math.abs(column - nextColumn);
    if (distance > 1) {
      throw new Error(
        `${label}: the piece jumped ${distance} cells between two frames ` +
          `(${sequence[index - 1].cell} -> ${sequence[index].cell}); ` +
          `it must walk cell to cell`,
      );
    }
  }
}

const near = (a, b, tolerance = 0.5) => Math.abs(a - b) <= tolerance;
const sameCell = (actual, expected) =>
  actual !== null && actual[0] === expected.r && actual[1] === expected.c;
const format = (cell) => (cell ? `[${cell[0]},${cell[1]}]` : "nothing");

/* ----------------------------------------------------------------- checks */
const CHECKS = [
  {
    id: "S0",
    issue: "#66",
    title: "a piece is painted over the cell the geometry tables give it",
    async run(t) {
      const positions = [0, 5, 20, 40];
      await t.open({ pieces: positions, turn: 1 });
      const painted = await t.probe("under");
      const wrong = [];
      for (const piece of painted) {
        const position = positions[piece.idx - 1];
        const expected = getGridCoordinates(LOCAL_SEAT, position, OFFSETS[LOCAL_SEAT]);
        if (!sameCell(piece.covered, expected)) {
          wrong.push(
            `piece ${piece.idx} (position ${position}): tables say [${expected.r},${expected.c}] ` +
              `(${describeCell(expected)}) but it is painted over ${format(piece.covered)}` +
              (piece.coveredBg ? ` (bg ${piece.coveredBg})` : ""),
          );
        }
      }
      // Same invariant for a seat whose home column is not mirror-symmetric.
      await t.open({ pieces: [-1, -1, -1, -1], turn: 2 });
      await t.lab("setPieces", 1, [43, 0]);
      await sleep(150);
      await t.waitQuiet();
      const blue = await t.probe("under");
      for (const piece of blue) {
        const position = piece.idx === 1 ? 43 : 0;
        const expected = getGridCoordinates(1, position, OFFSETS[1]);
        if (!sameCell(piece.covered, expected)) {
          wrong.push(
            `blue piece (position ${position}): tables say [${expected.r},${expected.c}] ` +
              `(${describeCell(expected)}) but it is painted over ${format(piece.covered)}` +
              (piece.coveredBg ? ` (bg ${piece.coveredBg})` : ""),
          );
        }
      }
      if (wrong.length) {
        throw new Error(
          `${wrong.length} piece(s) stand on the wrong cell:\n  ${wrong.join("\n  ")}`,
        );
      }
    },
  },

  {
    id: "S1",
    issue: "#65",
    title: "a playable piece stays on its own cell",
    async run(t) {
      await t.open({ pieces: [0, 3], turn: 0 });
      await t.lab("roll", 6);
      await sleep(400);
      const painted = await t.probe("under");
      const playable = painted.filter((piece) => piece.highlight);
      if (playable.length === 0) {
        throw new Error(
          "no piece advertises a highlight after rolling a 6 — the check cannot see the bug",
        );
      }
      const moved = painted.filter(
        (piece) =>
          !near(piece.computedX, piece.inlineX, 1) ||
          !near(piece.computedY, piece.inlineY, 1),
      );
      if (moved.length) {
        throw new Error(
          `${moved.length}/${painted.length} piece(s) left their cell while playable:\n` +
            moved
              .map(
                (piece) =>
                  `  piece ${piece.idx}: intended (${piece.inlineX}, ${piece.inlineY}) ` +
                  `but painted (${piece.computedX}, ${piece.computedY}) with animation-name=${piece.animationName}`,
              )
              .join("\n"),
        );
      }
    },
  },

  {
    id: "S2",
    issue: "#67",
    title: "a captured piece travels back to its base",
    async run(t) {
      await t.open({ pieces: [6], turn: 1 });
      await t.startSampler();
      await t.lab("move", 0, -1);
      await sleep(600);
      const positions = paintedPositions(await t.stopSampler(), 1);
      if (positions.length <= 2) {
        throw new Error(
          `the piece was painted at only ${positions.length} position(s) ` +
            `(${positions.join(" -> ")}): it pops instead of animating`,
        );
      }
    },
  },

  {
    id: "S3",
    issue: "#68",
    title: "a piece leaving the yard travels onto the board",
    async run(t) {
      await t.open({ pieces: [-1], turn: 1 });
      await t.startSampler();
      await t.lab("move", 0, 0);
      await sleep(600);
      const positions = paintedPositions(await t.stopSampler(), 1);
      if (positions.length <= 2) {
        throw new Error(
          `the piece was painted at only ${positions.length} position(s) ` +
            `(${positions.join(" -> ")}): it pops instead of animating`,
        );
      }
    },
  },

  {
    id: "S4",
    issue: "#69",
    title: "each centre-goal triangle points at its own home column",
    async run(t) {
      await t.open({ pieces: [-1, -1, -1, -1], turn: 1 });
      const goal = await t.probe("goal");
      const cells = await t.probe("cells");
      if (!goal || goal.triangles.length !== 4) {
        throw new Error("could not find the four goal triangles");
      }
      const seatRgb = [
        [249, 65, 68],
        [39, 125, 161],
        [67, 170, 139],
        [249, 199, 79],
      ];
      const wrong = [];
      // The fixture is a four-player match, so seat index == colour seat.
      for (let seat = 0; seat < 4; seat += 1) {
        const [firstRow, firstColumn] = [
          HOME_COLUMNS[seat][0].r,
          HOME_COLUMNS[seat][0].c,
        ];
        const homeCell = cells.find(
          (cell) => cell.r === firstRow && cell.c === firstColumn,
        );
        if (!homeCell) continue;
        const dx = homeCell.cx - goal.cx;
        const dy = homeCell.cy - goal.cy;
        const side =
          Math.abs(dx) > Math.abs(dy)
            ? dx > 0
              ? "right"
              : "left"
            : dy > 0
              ? "bottom"
              : "top";
        const rgb = seatRgb[seat];
        const usesSeatColour = (color) => {
          if (!color) return false;
          const match = /(\d+),\s*(\d+),\s*(\d+)/.exec(color);
          return (
            match &&
            Number(match[1]) === rgb[0] &&
            Number(match[2]) === rgb[1] &&
            Number(match[3]) === rgb[2]
          );
        };
        const triangle = goal.triangles.find((candidate) =>
          candidate.colors.some(usesSeatColour),
        );
        if (!triangle) {
          wrong.push(`seat ${seat}: no triangle uses its colour`);
        } else if (triangle.anchor !== side) {
          wrong.push(
            `seat ${seat}: its home column is rendered on the ${side} of the goal, ` +
              `but the triangle is anchored ${triangle.anchor}`,
          );
        }
      }
      if (wrong.length) throw new Error(wrong.join("\n"));
    },
  },

  {
    id: "S5",
    issue: "#70",
    title: "states arriving mid-hop do not teleport the piece",
    async run(t) {
      await t.open({ pieces: [0], turn: 1 });
      await t.startSampler();
      await t.lab("move", 0, 4);
      await sleep(150); // still inside the 4-step hop
      await t.lab("move", 0, 6);
      await sleep(150); // and still inside the re-targeted hop
      await t.lab("move", 0, 8);
      await sleep(1400);
      const frames = await t.stopSampler();
      assertAdjacentCells(cellSequence(frames, 1), "states arriving mid-hop");
    },
  },

  {
    id: "S6",
    issue: "#71",
    title: "prefers-reduced-motion removes the hop",
    async run(t) {
      await t.page.emulateMediaFeatures([
        { name: "prefers-reduced-motion", value: "reduce" },
      ]);
      try {
        await t.open({ pieces: [0], turn: 1 });
        await t.startSampler();
        await t.lab("move", 0, 4);
        await sleep(900);
        const sequence = cellSequence(await t.stopSampler(), 1);
        if (sequence.length > 2) {
          throw new Error(
            `with prefers-reduced-motion: reduce the piece still walked through ` +
              `${sequence.length} cells (${sequence.map((entry) => entry.cell).join(" -> ")})`,
          );
        }
      } finally {
        await t.page.emulateMediaFeatures([]);
      }
    },
  },

  {
    id: "S7",
    issue: null,
    title: "guard: a resting piece is painted exactly at its transform",
    async run(t) {
      await t.open({ pieces: [0, 3], turn: 1 });
      const painted = await t.probe("under");
      const drifting = painted.filter(
        (piece) =>
          !near(piece.computedX, piece.inlineX) ||
          !near(piece.computedY, piece.inlineY),
      );
      if (drifting.length) {
        throw new Error(
          `${drifting.length} resting piece(s) are painted away from their transform: ` +
            drifting
              .map((piece) => `piece ${piece.idx} (${piece.animationName})`)
              .join(", "),
        );
      }
      const animated = painted.filter((piece) => piece.highlight);
      if (animated.length) {
        throw new Error("a resting piece still has a CSS animation attached");
      }
    },
  },

  {
    id: "S8",
    issue: null,
    title: "guard: a 4-step move walks every cell and lands on the target",
    async run(t) {
      await t.open({ pieces: [0], turn: 1 });
      await t.startSampler();
      await t.lab("move", 0, 4);
      await sleep(900);
      const frames = await t.stopSampler();
      const sequence = cellSequence(frames, 1);
      assertAdjacentCells(sequence, "4-step move");
      if (sequence.length < 5) {
        throw new Error(
          `the hop covered ${sequence.length} cells instead of 5: ` +
            sequence.map((entry) => entry.cell).join(" -> "),
        );
      }
      await t.waitQuiet();
      // The absolute cell is check S0's invariant; here we only require the
      // piece to end where a piece that started on 4 is painted.
      const moved = (await t.probe("under")).find((entry) => entry.idx === 1);
      await t.open({ pieces: [4], turn: 1 });
      const resting = (await t.probe("under")).find((entry) => entry.idx === 1);
      if (!moved || !resting || format(moved.covered) !== format(resting.covered)) {
        throw new Error(
          `the piece ended on ${format(moved && moved.covered)} but a piece resting on 4 ` +
            `is painted over ${format(resting && resting.covered)}`,
        );
      }
    },
  },

  {
    id: "S9",
    issue: null,
    title: "guard: a hop into the home stretch stays contiguous",
    async run(t) {
      await t.open({ pieces: [38], turn: 1 });
      await t.startSampler();
      await t.lab("move", 0, 42);
      await sleep(900);
      const sequence = cellSequence(await t.stopSampler(), 1);
      assertAdjacentCells(sequence, "hop into the home stretch");
      await t.waitQuiet();
      const painted = await t.probe("under");
      const expected = getGridCoordinates(LOCAL_SEAT, 42, OFFSETS[LOCAL_SEAT]);
      const piece = painted.find((entry) => entry.idx === 1);
      if (!piece || !sameCell(piece.covered, expected)) {
        throw new Error(
          `the piece does not end on [${expected.r},${expected.c}]: ${format(piece && piece.covered)}`,
        );
      }
    },
  },

  {
    id: "S10",
    issue: null,
    title: "guard: two pieces on one cell fan out instead of overlapping",
    async run(t) {
      await t.open({ pieces: [0, 0], turn: 1 });
      const painted = await t.probe("under");
      if (painted.length !== 2) {
        throw new Error(`expected 2 pieces on the board, found ${painted.length}`);
      }
      const [first, second] = painted;
      if (
        first.covered === null ||
        second.covered === null ||
        first.covered[0] !== second.covered[0] ||
        first.covered[1] !== second.covered[1]
      ) {
        throw new Error(
          "two pieces on the same cell are painted over different cells: " +
            `${format(first.covered)} vs ${format(second.covered)}`,
        );
      }
      const gap =
        Math.abs(first.inlineX - second.inlineX) +
        Math.abs(first.inlineY - second.inlineY);
      if (gap < 4) {
        throw new Error(`the stacked pieces are only ${gap.toFixed(1)}px apart`);
      }
    },
  },
];

/* Cell colour of a table coordinate, for readable failure messages. */
function describeCell(cell) {
  if (cell.r === 5 && cell.c === 5) return "the goal";
  for (let seat = 0; seat < HOME_COLUMNS.length; seat += 1) {
    if (HOME_COLUMNS[seat].some((home) => home.r === cell.r && home.c === cell.c)) {
      return `home column of seat ${seat}`;
    }
  }
  return "a track cell";
}

/* ------------------------------------------------------------------- main */
async function main() {
  const only = process.argv.slice(2).filter((argument) => /^S\d+$/.test(argument));
  const selected = only.length
    ? CHECKS.filter((check) => only.includes(check.id))
    : CHECKS;
  if (selected.length === 0) {
    console.error(`no check matched ${only.join(" ")}`);
    process.exit(2);
  }

  const puppeteer = await loadPuppeteer();
  const server = await startServer();
  const browser = await launchBrowser(puppeteer);
  const page = await browser.newPage();
  page.on("pageerror", (error) => console.log(`  [pageerror] ${error.message}`));
  await page.evaluateOnNewDocument(installProbe);

  const driver = new Driver(page);
  const failures = [];
  console.log(`animation suite — ${BASE}\n`);

  for (const check of selected) {
    const label = check.issue ? `${check.id} ${check.issue}` : check.id;
    try {
      await check.run(driver);
      console.log(`✓ ${label}  ${check.title}`);
    } catch (error) {
      failures.push({ check, error });
      console.log(`✗ ${label}  ${check.title}`);
      for (const line of String(error.message).split("\n")) {
        console.log(`      ${line}`);
      }
    }
  }

  await browser.close();
  if (server) server.kill();

  const passed = selected.length - failures.length;
  console.log(`\n${passed}/${selected.length} checks passed`);
  if (failures.length) {
    console.log(
      "failing: " +
        failures
          .map(({ check }) => (check.issue ? `${check.id} (${check.issue})` : check.id))
          .join(", "),
    );
    process.exit(1);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
