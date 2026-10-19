"""The matchmaking claim script against a real Redis (issue #18).

The in-memory fake proves the service contract; this test proves that the Lua
script itself is atomic on the real server. It uses a separate Redis database
and is skipped when no Redis is reachable.
"""

import asyncio

import pytest
import redis.asyncio as aioredis

from app.config import settings
from app.services.queue_service import QueueService

TEST_DB = 15
QUEUE_KEY = "matchmaking:queue:2p:4pieces"


def _client() -> aioredis.Redis:
    return aioredis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=TEST_DB,
        decode_responses=True,
    )


@pytest.fixture
async def real_redis(monkeypatch):
    client = _client()
    try:
        await client.ping()
    except Exception as exc:  # pragma: no cover - only without a Redis server
        await client.aclose()
        pytest.skip(f"Redis is not reachable at {settings.REDIS_HOST}:{settings.REDIS_PORT}: {exc}")

    await client.flushdb()
    monkeypatch.setattr("app.services.queue_service.redis_client", client)
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


@pytest.mark.asyncio
async def test_concurrent_players_create_rooms_without_duplicates(real_redis):
    results = await asyncio.gather(
        *(
            QueueService.add_to_queue(f"race{index}", f"Racer {index}", "", 2, 4)
            for index in range(1, 7)
        )
    )

    created = [result for result in results if result]
    assert len(created) == 3
    assert len({result["room_id"] for result in created}) == 3

    seated = [player["id"] for result in created for player in result["players"]]
    assert sorted(seated) == [f"race{index}" for index in range(1, 7)]
    assert len(seated) == len(set(seated))

    assert await real_redis.llen(QUEUE_KEY) == 0


@pytest.mark.asyncio
async def test_duplicate_enqueue_is_deduplicated(real_redis):
    await QueueService.add_to_queue("solo", "Solo", "", 2, 4)
    await QueueService.add_to_queue("solo", "Solo", "", 2, 4)

    assert await real_redis.lrange(QUEUE_KEY, 0, -1) == ["solo"]


@pytest.mark.asyncio
async def test_switching_settings_moves_the_player_between_queues(real_redis):
    await QueueService.add_to_queue("switch", "Switch", "", 2, 4)
    await QueueService.add_to_queue("switch", "Switch", "", 2, 2)

    assert await real_redis.lrange(QUEUE_KEY, 0, -1) == []
    assert await real_redis.lrange("matchmaking:queue:2p:2pieces", 0, -1) == ["switch"]
