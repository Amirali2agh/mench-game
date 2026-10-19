"""Matchmaking queue service contract (issue #18).

The queue is mutated by a single Lua script so that enqueue + claim is one
atomic Redis operation. These tests pin the service side of that contract: which
script is called, what it returns, and what happens when a claim cannot be
committed.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.services.queue_service import QueueService


def _eval_args(mock_redis) -> tuple:
    assert mock_redis.eval.await_count == 1
    return mock_redis.eval.await_args.args


@pytest.mark.asyncio
async def test_add_to_queue_waits_when_the_queue_is_not_full():
    with patch("app.services.queue_service.redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.eval.return_value = []

        result = await QueueService.add_to_queue(
            player_id="p1",
            player_name="Amir",
            avatar_url="http://avatar.com/1",
            target_players=2,
            pieces_count=4,
        )

        assert result is None
        mock_redis.set.assert_any_call(
            "player:p1:meta",
            json.dumps({"id": "p1", "name": "Amir", "avatar": "http://avatar.com/1"}),
            ex=3600,
        )

        script, numkeys, *args = _eval_args(mock_redis)
        assert "claim-queue" in script
        assert numkeys == 2
        assert args[0] == "matchmaking:queue:2p:4pieces"
        assert args[1] == "player:p1:queue"
        assert args[2] == "p1"
        assert args[3] == 2

        # The list is no longer touched command by command.
        mock_redis.lrange.assert_not_called()
        mock_redis.llen.assert_not_called()
        mock_redis.lpop.assert_not_called()
        mock_redis.rpush.assert_not_called()


@pytest.mark.asyncio
async def test_add_to_queue_claims_a_full_match():
    with patch("app.services.queue_service.redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.eval.return_value = ["p1", "p2"]
        mock_redis.get.side_effect = [
            json.dumps({"id": "p1", "name": "Amir", "avatar": "avatar1"}),
            json.dumps({"id": "p2", "name": "Ali", "avatar": "avatar2"}),
        ]

        result = await QueueService.add_to_queue(
            player_id="p2",
            player_name="Ali",
            avatar_url="avatar2",
            target_players=2,
            pieces_count=2,
        )

        assert result is not None
        assert result["pieces_count"] == 2
        assert [player["id"] for player in result["players"]] == ["p1", "p2"]

        room_id = result["room_id"]
        written_keys = [call.args[0] for call in mock_redis.set.call_args_list if call.args]
        assert f"room:{room_id}:meta" in written_keys

        # Settings live in the room document only: no legacy side keys.
        assert f"room:{room_id}:pieces_count" not in written_keys
        assert f"room:{room_id}:player_count" not in written_keys

        # Both players get a notification for the per-worker watcher.
        notified = [call.args[0] for call in mock_redis.rpush.call_args_list if call.args]
        assert "queue:notify:p1" in notified
        assert "queue:notify:p2" in notified

        # A failed match is never rolled back with lpush.
        mock_redis.lpush.assert_not_called()


@pytest.mark.asyncio
async def test_add_to_queue_persists_complete_room_roster():
    with patch("app.services.queue_service.redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.eval.return_value = ["p1", "p2"]
        mock_redis.get.side_effect = [
            json.dumps({"id": "p1", "name": "Amir", "avatar": ""}),
            json.dumps({"id": "p2", "name": "Ali", "avatar": ""}),
        ]

        result = await QueueService.add_to_queue("p2", "Ali", "", 2, 4)

        room_id = result["room_id"]
        calls = [
            call for call in mock_redis.set.call_args_list
            if call.args and call.args[0] == f"room:{room_id}:meta"
        ]
        assert calls, "matchmaking must persist complete room metadata"

        room_meta = json.loads(calls[-1].args[1])
        assert room_meta["players"] == ["p1", "p2"]
        assert room_meta["players_meta"]["1"]["name"] == "Amir"
        assert room_meta["players_meta"]["2"]["name"] == "Ali"
        assert room_meta["player_count"] == 2
        assert room_meta["pieces_count"] == 4
        assert f"room:{room_id}:pieces_count" not in {
            call.args[0] for call in mock_redis.set.call_args_list if call.args
        }


@pytest.mark.asyncio
async def test_add_to_queue_falls_back_to_a_placeholder_profile():
    with patch("app.services.queue_service.redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.eval.return_value = ["ghost", "p2"]
        mock_redis.get.side_effect = [None, json.dumps({"id": "p2", "name": "Ali", "avatar": ""})]

        result = await QueueService.add_to_queue("p2", "Ali", "", 2, 4)

        assert result is not None
        assert result["players"] == [
            {"id": "ghost", "name": "Player ghost", "avatar": ""},
            {"id": "p2", "name": "Ali", "avatar": ""},
        ]


@pytest.mark.asyncio
async def test_remove_from_queue_clears_the_player_marker():
    with patch("app.services.queue_service.redis_client", new_callable=AsyncMock) as mock_redis:
        queue_key = "matchmaking:queue:2p:3pieces"
        mock_redis.get.return_value = queue_key

        await QueueService.remove_from_queue("p1", 2, pieces_count=3)

        mock_redis.lrem.assert_awaited_once_with(queue_key, 0, "p1")
        mock_redis.delete.assert_awaited_once_with("player:p1:queue")


@pytest.mark.asyncio
async def test_remove_from_queue_keeps_a_marker_of_another_queue():
    with patch("app.services.queue_service.redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.get.return_value = "matchmaking:queue:4p:2pieces"

        await QueueService.remove_from_queue("p1", 2, pieces_count=3)

        mock_redis.delete.assert_not_awaited()
