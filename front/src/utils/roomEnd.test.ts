/**
 * How a room socket that fell silent is reported to the player.
 *
 * Run with `npm test` (node --test). The bug in issue #60 was that a terminal
 * server message (`room_timeout`) still produced the generic "connection lost"
 * overlay, because `ws.onclose` ran afterwards and marked the socket as
 * disconnected. The decision now lives here so it can be tested without a
 * browser.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  ROOM_TIMEOUT_MESSAGE,
  ROOM_WAIT_ENDED_MESSAGE,
  healthAfterSocketDrop,
  isRoomWaitOver,
} from "./roomEnd.ts";

describe("healthAfterSocketDrop", () => {
  it("reports a real transport loss", () => {
    assert.equal(healthAfterSocketDrop("none"), "disconnected");
  });

  it("stays stable after the server ended the wait", () => {
    assert.equal(healthAfterSocketDrop("timeout"), "stable");
  });

  it("stays stable after the server rejected the player", () => {
    assert.equal(healthAfterSocketDrop("rejected"), "stable");
  });

  it("stays stable after the player left", () => {
    assert.equal(healthAfterSocketDrop("left"), "stable");
  });
});

describe("isRoomWaitOver", () => {
  it("is true only for the room wait timeout", () => {
    assert.equal(isRoomWaitOver("timeout"), true);
    assert.equal(isRoomWaitOver("none"), false);
    assert.equal(isRoomWaitOver("rejected"), false);
    assert.equal(isRoomWaitOver("left"), false);
  });
});

describe("room messages", () => {
  it("explains the wait timeout to the player", () => {
    assert.match(ROOM_TIMEOUT_MESSAGE, /زمان انتظار/);
    assert.match(ROOM_WAIT_ENDED_MESSAGE, /لینک/);
  });
});
