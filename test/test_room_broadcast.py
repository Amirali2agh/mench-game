"""Room/queue socket registry behaviour (issue #21).

Broadcasts used to swallow every send error and keep dead sockets forever, a
reconnect left an orphaned socket behind, and an internal error was treated as
a disconnect that forfeited a live match.
"""

import asyncio
import logging
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.managers.queue_manager import QueueManager
from app.managers.room_manager import RoomManager, room_manager

client = TestClient(app)


class FakeSocket:
    """Minimal WebSocket double for the manager."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.messages: list[dict] = []
        self.closed_with: int | None = None
        self.accepted = False

    async def accept(self) -> None:
        self.accepted = True

    async def close(self, code: int = 1000) -> None:
        self.closed_with = code

    async def send_json(self, message: dict) -> None:
        if self.fail:
            raise RuntimeError("socket is gone")
        self.messages.append(message)


def test_broadcast_prunes_and_logs_failed_sockets(caplog):
    async def run() -> None:
        manager = RoomManager()
        healthy, dead = FakeSocket(), FakeSocket(fail=True)
        await manager.connect("room-1", "p1", healthy)
        await manager.connect("room-1", "p2", dead)

        with caplog.at_level(logging.WARNING):
            failed = await manager.broadcast("room-1", {"type": "sync_state"})

        assert failed == ["p2"]
        assert "p2" not in manager.rooms["room-1"]
        assert healthy.messages == [{"type": "sync_state"}]
        assert "Broadcast to room-1/p2 failed" in caplog.text

    asyncio.run(run())


def test_broadcast_reports_every_failed_socket():
    async def run() -> None:
        manager = RoomManager()
        await manager.connect("room-2", "p1", FakeSocket(fail=True))
        await manager.connect("room-2", "p2", FakeSocket(fail=True))

        failed = await manager.broadcast("room-2", {"type": "sync_state"})

        assert sorted(failed) == ["p1", "p2"]
        assert "room-2" not in manager.rooms

    asyncio.run(run())


def test_broadcast_does_not_wait_for_a_slow_socket():
    """A stalled send must not delay delivery to the other players."""

    async def run() -> None:
        manager = RoomManager()
        slow_started = asyncio.Event()
        slow_release = asyncio.Event()
        fast_delivered = asyncio.Event()

        class SlowSocket(FakeSocket):
            async def send_json(self, message: dict) -> None:
                slow_started.set()
                await slow_release.wait()
                await super().send_json(message)

        class FastSocket(FakeSocket):
            async def send_json(self, message: dict) -> None:
                await super().send_json(message)
                fast_delivered.set()

        await manager.connect("room-3", "slow", SlowSocket())
        await manager.connect("room-3", "fast", FastSocket())

        broadcaster = asyncio.create_task(manager.broadcast("room-3", {"type": "x"}))
        await asyncio.wait_for(slow_started.wait(), timeout=1)
        await asyncio.wait_for(fast_delivered.wait(), timeout=1)
        slow_release.set()
        await asyncio.wait_for(broadcaster, timeout=1)

    asyncio.run(run())


def test_reconnect_closes_the_previous_socket():
    async def run() -> None:
        manager = RoomManager()
        first, second = FakeSocket(), FakeSocket()

        await manager.connect("room-4", "p1", first)
        await manager.connect("room-4", "p1", second)

        assert first.closed_with == 1000
        assert manager.rooms["room-4"]["p1"] is second

    asyncio.run(run())


def test_queue_notification_failure_drops_the_socket(caplog):
    async def run() -> None:
        manager = QueueManager()
        await manager.connect("p1", FakeSocket(fail=True))

        with caplog.at_level(logging.WARNING):
            await manager.send_match_found("p1", "room-5", [], 4)

        assert "p1" not in manager.active_connections
        assert "Match notification to p1 failed" in caplog.text

    asyncio.run(run())


@pytest.mark.asyncio
async def test_failed_broadcast_arms_the_forfeit_timer(fake_redis):
    from app.api.websocket.room import broadcast_room

    async def run() -> None:
        dead = FakeSocket(fail=True)
        await room_manager.connect("prune-room", "p1", dead)

        await broadcast_room("prune-room", {"type": "sync_state"})

        assert "p1" in room_manager.disconnect_tasks.get("prune-room", {})
        room_manager._cancel_disconnect_task("prune-room", "p1")
        await asyncio.sleep(0)
        room_manager.rooms.pop("prune-room", None)

    await run()


def test_internal_error_does_not_start_a_forfeit_timer(fake_redis, room_factory, monkeypatch):
    """A bug in the handler must close the socket, not forfeit the player."""
    room_factory(room_id="boom-room", player_ids=("p1", "p2"))

    async def explode(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.api.websocket.room._prepare_room", explode)

    with client.websocket_connect(
        "/ws/room/boom-room?playerId=p1&playerName=Player"
    ) as websocket:
        with pytest.raises(WebSocketDisconnect):
            websocket.receive_json()

    assert "boom-room" not in room_manager.disconnect_tasks


def test_reconnect_does_not_arm_a_forfeit_timer(fake_redis, room_factory):
    """Replacing a socket must not forfeit the still-connected player."""
    room_factory(room_id="re-room", player_ids=("p1", "p2"))
    url = "/ws/room/re-room?playerId=p1&playerName=Player"

    with client.websocket_connect(url) as first:
        assert first.receive_json()["type"] == "sync_state"
        with client.websocket_connect(url) as second:
            assert second.receive_json()["type"] == "sync_state"
            # The replaced socket's handler runs right after the close; give it
            # a moment and then check that only a live player is left.
            time.sleep(0.05)
            assert "re-room" not in room_manager.disconnect_tasks
