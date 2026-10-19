"""Matchmaking under concurrency (issue #18).

The old implementation did ``lrange`` -> ``rpush`` -> ``llen`` -> ``lpop`` in
separate round trips, so two workers could both believe they had a full queue,
pop a partial roster, and "roll back" with ``lpush``, which reversed the queue
order. Enqueue and claim are now a single atomic script.
"""

import asyncio

import pytest

from app.services.queue_service import QueueService

QUEUE_KEY = "matchmaking:queue:2p:4pieces"


def _join(player_id: str, target_players: int = 2, pieces_count: int = 4):
    return QueueService.add_to_queue(
        player_id, player_id.upper(), "", target_players, pieces_count
    )


@pytest.mark.asyncio
async def test_two_players_racing_create_exactly_one_room(fake_redis):
    results = await asyncio.gather(_join("p1"), _join("p2"))

    created = [result for result in results if result]
    assert len(created) == 1
    assert [player["id"] for player in created[0]["players"]] == ["p1", "p2"]
    assert fake_redis.lists.get(QUEUE_KEY, []) == []


@pytest.mark.asyncio
async def test_six_players_racing_create_three_rooms_without_duplicates(fake_redis):
    results = await asyncio.gather(*(_join(f"p{index}") for index in range(1, 7)))

    created = [result for result in results if result]
    assert len(created) == 3
    assert len({result["room_id"] for result in created}) == 3

    seated = [player["id"] for result in created for player in result["players"]]
    assert sorted(seated) == [f"p{index}" for index in range(1, 7)]
    assert len(seated) == len(set(seated))

    assert fake_redis.lists.get(QUEUE_KEY, []) == []


@pytest.mark.asyncio
async def test_enqueueing_twice_does_not_duplicate_the_player(fake_redis):
    assert await _join("p1") is None
    assert await _join("p1") is None

    assert fake_redis.lists[QUEUE_KEY] == ["p1"]


@pytest.mark.asyncio
async def test_switching_settings_removes_the_player_from_the_old_queue(fake_redis):
    await _join("p1", pieces_count=4)
    assert fake_redis.lists["matchmaking:queue:2p:4pieces"] == ["p1"]

    await _join("p1", pieces_count=2)

    assert fake_redis.lists.get("matchmaking:queue:2p:4pieces", []) == []
    assert fake_redis.lists["matchmaking:queue:2p:2pieces"] == ["p1"]


def test_failed_room_creation_returns_players_without_reversing(fake_redis):
    """A claim that cannot be committed must not reverse the queue.

    The old rollback used ``lpush`` in claim order, so ``[p1, p2, p3]`` became
    ``[p2, p1, p3]``. The players return to the tail in their original order.
    """
    fake_redis.lists[QUEUE_KEY] = ["p1", "p2", "p3"]
    original_set = fake_redis.set

    async def failing_set(key, value, *args, **kwargs):
        if str(key).startswith("room:") and str(key).endswith(":meta"):
            raise RuntimeError("redis write failed")
        return await original_set(key, value, *args, **kwargs)

    fake_redis.set = failing_set

    with pytest.raises(RuntimeError):
        asyncio.run(_join("p4"))

    assert fake_redis.lists[QUEUE_KEY] == ["p3", "p4", "p1", "p2"]
    # A room that was never persisted must not leave a mapping behind.
    assert fake_redis.values.get("player:p1:room") is None
    assert fake_redis.values.get("player:p2:room") is None
