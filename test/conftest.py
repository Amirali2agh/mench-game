"""Shared test doubles.

The services talk to Redis directly, so every test patches the module-level
``redis_client`` of the service under test with a small in-memory fake. Tests
must never require (or mutate) a running Redis instance.
"""

import asyncio
import json
import time

import pytest

from app.services import room_service as RoomService


class FakeRedis:
    """Minimal async Redis stand-in covering the commands the app uses."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value, ex=None, nx: bool = False):
        if nx and key in self.values:
            return None
        self.values[key] = value
        return True

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            removed += 1 if self.values.pop(key, None) is not None else 0
            removed += 1 if self.lists.pop(key, None) is not None else 0
        return removed

    async def lrange(self, key: str, start: int, end: int):
        items = self.lists.get(key, [])
        return items[start:] if end == -1 else items[start : end + 1]

    async def rpush(self, key: str, *values: str) -> int:
        self.lists.setdefault(key, []).extend(values)
        return len(self.lists[key])

    async def lpush(self, key: str, *values: str) -> int:
        items = self.lists.setdefault(key, [])
        for value in values:
            items.insert(0, value)
        return len(items)

    async def llen(self, key: str) -> int:
        return len(self.lists.get(key, []))

    async def lpop(self, key: str):
        items = self.lists.get(key, [])
        return items.pop(0) if items else None

    async def lrem(self, key: str, count: int, value: str) -> int:
        items = self.lists.get(key, [])
        removed = items.count(value)
        self.lists[key] = [item for item in items if item != value]
        return removed

    async def ltrim(self, key: str, start: int, end: int) -> bool:
        items = self.lists.get(key, [])
        self.lists[key] = items[start:] if end == -1 else items[start : end + 1]
        return True

    async def eval(self, script: str, numkeys: int, *args):
        """Run the matchmaking claim script against the in-memory structures.

        The fake implements exactly the one script the service uses; any other
        script fails loudly instead of silently returning the wrong shape.
        """
        if "mensch:claim-queue:v1" not in script:
            raise NotImplementedError("FakeRedis only implements the claim-queue script")

        keys = args[:numkeys]
        argv = args[numkeys:]
        queue_key, marker_key = keys
        player_id, target_players = str(argv[0]), int(argv[1])

        previous = self.values.get(marker_key)
        if previous and previous != queue_key:
            self.lists[previous] = [
                item for item in self.lists.get(previous, []) if item != player_id
            ]
        self.lists[queue_key] = [
            item for item in self.lists.get(queue_key, []) if item != player_id
        ]
        self.lists.setdefault(queue_key, []).append(player_id)
        self.values[marker_key] = queue_key

        if len(self.lists[queue_key]) < target_players:
            return []

        claimed = self.lists[queue_key][:target_players]
        self.lists[queue_key] = self.lists[queue_key][target_players:]
        for claimed_id in claimed:
            claimed_marker = f"player:{claimed_id}:queue"
            if self.values.get(claimed_marker) == queue_key:
                del self.values[claimed_marker]
        return claimed

    async def expire(self, key: str, seconds: int) -> bool:
        return True

    async def blpop(self, keys, timeout: float = 0):
        """Block until an item shows up or the timeout expires.

        Real Redis blocks for ``timeout`` seconds; polling keeps the fake usable
        from concurrent coroutines in the same event loop. A zero timeout means
        "do not wait" so a misconfigured test can never hang.
        """
        if isinstance(keys, str):
            keys = [keys]
        deadline = time.monotonic() + (timeout or 0)
        while True:
            for key in keys:
                items = self.lists.get(key, [])
                if items:
                    return key, items.pop(0)
            if not timeout or time.monotonic() >= deadline:
                return None
            await asyncio.sleep(0.01)


#: Module-level ``redis_client`` bindings replaced by the fake in every test.
REDIS_TARGETS = (
    "app.services.room_service.redis_client",
    "app.services.game_service.redis_client",
    "app.services.queue_service.redis_client",
    "app.api.websocket.room.redis_client",
    "app.api.websocket.queue.redis_client",
    "app.api.rooms.redis_client",
)


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()
    for target in REDIS_TARGETS:
        monkeypatch.setattr(target, fake)
    return fake


@pytest.fixture
def room_factory(fake_redis):
    """Create a room with a complete roster and start its match."""

    def _create(
        room_id: str = "room-1",
        player_count: int = 2,
        pieces_count: int = 4,
        coin_bet: int = 0,
        player_ids: tuple[str, ...] | None = None,
    ) -> dict:
        ids = player_ids or tuple(f"p{index + 1}" for index in range(player_count))

        async def _run() -> dict:
            room = RoomService.new_room(
                room_id,
                player_count=player_count,
                pieces_count=pieces_count,
                coin_bet=coin_bet,
            )
            await RoomService.save_room(room_id, room)
            for player_id in ids:
                player = {"id": player_id, "name": f"Player {player_id}", "avatar": ""}
                await fake_redis.set(f"player:{player_id}:meta", json.dumps(player))
                room, _seat, error = await RoomService.register_player(room_id, player)
                assert error is None, error
            state = await RoomService.start_game(room_id, room)
            assert state is not None, "a complete roster must start the match"
            return state

        return asyncio.run(_run())

    return _create
