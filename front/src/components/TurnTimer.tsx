/**
 * Per-turn countdown ring.
 *
 * The countdown lives in its own component on purpose: it changes every second,
 * and the board used to re-render the grid, the pieces and the player panels
 * with it. Isolating the interval here keeps those one-second updates to a
 * single small SVG.
 */
import React, { useEffect, useRef, useState } from "react";

export const TURN_TIMEOUT_SECONDS = 45;

const RADIUS = 19;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

export interface TurnTimerProps {
  /** Only the active player shows (and runs) the countdown. */
  active: boolean;
  /** Changing this resets the countdown, e.g. `"2:playing"` on a new turn. */
  resetKey: string;
  /** Called once when the countdown reaches zero while active. */
  onTimeout: () => void;
}

const TurnTimer: React.FC<TurnTimerProps> = ({ active, resetKey, onTimeout }) => {
  const [secondsLeft, setSecondsLeft] = useState(TURN_TIMEOUT_SECONDS);
  // Keep the latest callback without restarting the interval on every render.
  const onTimeoutRef = useRef(onTimeout);
  onTimeoutRef.current = onTimeout;

  useEffect(() => {
    setSecondsLeft(TURN_TIMEOUT_SECONDS);
    if (!active) return;

    let fired = false;
    const interval = window.setInterval(() => {
      setSecondsLeft((previous) => {
        if (previous > 1) return previous - 1;
        window.clearInterval(interval);
        if (!fired) {
          fired = true;
          onTimeoutRef.current();
        }
        return 0;
      });
    }, 1000);

    return () => window.clearInterval(interval);
  }, [active, resetKey]);

  if (!active) return null;

  const elapsed = (TURN_TIMEOUT_SECONDS - secondsLeft) / TURN_TIMEOUT_SECONDS;

  return (
    <svg
      className="absolute inset-0 w-full h-full -rotate-90"
      viewBox="0 0 42 42"
      aria-hidden="true"
    >
      <circle
        cx="21"
        cy="21"
        r={RADIUS}
        fill="none"
        stroke="rgba(251,191,36,0.25)"
        strokeWidth="2.5"
      />
      <circle
        cx="21"
        cy="21"
        r={RADIUS}
        fill="none"
        stroke="#F59E0B"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeDasharray={`${CIRCUMFERENCE}`}
        strokeDashoffset={`${elapsed * CIRCUMFERENCE}`}
        className="transition-[stroke-dashoffset] duration-1000 ease-linear"
      />
    </svg>
  );
};

export default TurnTimer;
