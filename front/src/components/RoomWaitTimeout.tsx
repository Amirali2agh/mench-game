/**
 * Terminal screen for a room whose wait window expired (issue #60).
 *
 * A room opened from a link is cancelled when its roster never completes. The
 * socket then closes, which used to raise the generic "اتصال قطع شد" overlay:
 * the player saw a network error for a room that had simply timed out. This
 * screen says what happened, and that the same link cannot be reused.
 */
import React from "react";

import { ROOM_TIMEOUT_MESSAGE, ROOM_WAIT_ENDED_MESSAGE } from "../utils/roomEnd";

export const RoomWaitTimeout: React.FC = () => (
  <div
    className="flex items-center justify-center min-h-screen bg-backgroundPrimary px-4"
    role="status"
    aria-live="polite"
  >
    <div className="w-full max-w-sm p-8 rounded-3xl bg-slate-900/95 border border-amber-500/30 text-center shadow-2xl">
      <h2 className="text-xl font-extrabold text-slate-100 mb-3">
        {ROOM_TIMEOUT_MESSAGE}
      </h2>
      <p className="text-sm text-slate-400 leading-relaxed">
        {ROOM_WAIT_ENDED_MESSAGE}
      </p>
    </div>
  </div>
);

export default RoomWaitTimeout;
