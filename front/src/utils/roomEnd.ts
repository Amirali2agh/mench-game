/**
 * How a room socket that stopped talking is reported to the player.
 *
 * A room can end for four different reasons and only one of them is a
 * connection problem:
 *
 * * `none` — the transport dropped while the room was still alive.
 * * `timeout` — the server cancelled the room because its roster never
 *   completed (`room_timeout`, issue #60).
 * * `rejected` — the server refused the player (authentication, full room).
 * * `left` — the player closed the room themselves.
 *
 * The generic "connection lost" overlay used to appear for all four, because
 * `ws.onclose` fired after the terminal server message. Keeping the decision
 * here means the rule is unit tested instead of living inside an effect.
 */

/** Why the room socket ended; `none` while it is still supposed to work. */
export type RoomEndReason = "none" | "timeout" | "rejected" | "left";

/** Connection health reported to the overlay. */
export type DropHealth = "stable" | "disconnected";

/** Headline of the dedicated screen for an expired room wait. */
export const ROOM_TIMEOUT_MESSAGE = "زمان انتظار برای تکمیل بازیکنان به پایان رسید.";

/**
 * Explanation and next step under the headline.
 *
 * The room is cancelled, so reopening the same link cannot work; the player
 * needs a fresh room from the host.
 */
export const ROOM_WAIT_ENDED_MESSAGE =
  "بازیکن دیگری به بازی نپیوست و این اتاق بسته شد. برای شروع یک بازی تازه، از میزبان لینک جدید بگیرید.";

/**
 * Health to report when the socket closes or the browser goes offline.
 *
 * Only an unexplained drop is a connection problem; a room that ended on
 * purpose must not raise the "اتصال قطع شد" overlay.
 */
export function healthAfterSocketDrop(reason: RoomEndReason): DropHealth {
  return reason === "none" ? "disconnected" : "stable";
}

/** True when the room wait expired, i.e. the dedicated screen should show. */
export function isRoomWaitOver(reason: RoomEndReason): boolean {
  return reason === "timeout";
}
