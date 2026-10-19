import pytest
import json
from unittest.mock import patch, AsyncMock
from app.services.queue_service import QueueService

@pytest.mark.asyncio
async def test_add_to_queue_not_enough_players():
    """
    Test that adding a player to queue stores metadata and pushes to list,
    but returns None if the matchmaking pool target is not met.
    """
    with patch("app.services.queue_service.redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.lrange.return_value = []
        mock_redis.llen.return_value = 1
        
        result = await QueueService.add_to_queue(
            player_id="p1",
            player_name="Amir",
            avatar_url="http://avatar.com/1",
            target_players=2,
            pieces_count=4
        )
        
        assert result is None
        mock_redis.set.assert_any_call(
            "player:p1:meta",
            json.dumps({"id": "p1", "name": "Amir", "avatar": "http://avatar.com/1"}),
            ex=3600
        )
        mock_redis.rpush.assert_called_once_with("matchmaking:queue:2p:4pieces", "p1")


@pytest.mark.asyncio
async def test_add_to_queue_triggers_match():
    """
    Test that adding a player to queue triggers a successful match
    when the queue length reaches the target count.
    """
    with patch("app.services.queue_service.redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.lrange.return_value = []
        mock_redis.llen.return_value = 2
        mock_redis.lpop.side_effect = ["p1", "p2"]
        mock_redis.get.side_effect = [
            json.dumps({"id": "p1", "name": "Amir", "avatar": "avatar1"}),
            json.dumps({"id": "p2", "name": "Ali", "avatar": "avatar2"})
        ]
        
        result = await QueueService.add_to_queue(
            player_id="p2",
            player_name="Ali",
            avatar_url="avatar2",
            target_players=2,
            pieces_count=2
        )
        
        assert result is not None
        assert "room_id" in result
        assert len(result["players"]) == 2
        assert result["players"][0]["id"] == "p1"
        assert result["players"][1]["id"] == "p2"
        assert result["pieces_count"] == 2
        
        room_id = result["room_id"]

        # Settings live in the room document only: no legacy side keys.
        written_keys = [
            call.args[0] for call in mock_redis.set.call_args_list if call.args
        ]
        assert f"room:{room_id}:pieces_count" not in written_keys
        assert f"room:{room_id}:player_count" not in written_keys

        # Both players get a match notification for the per-worker watcher.
        notified = [
            call.args[0] for call in mock_redis.rpush.call_args_list if call.args
        ]
        assert "queue:notify:p1" in notified
        assert "queue:notify:p2" in notified


@pytest.mark.asyncio
async def test_add_to_queue_persists_complete_room_roster():
    with patch("app.services.queue_service.redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.lrange.return_value = []
        mock_redis.llen.return_value = 2
        mock_redis.lpop.side_effect = ["p1", "p2"]
        mock_redis.get.side_effect = [
            json.dumps({"id": "p1", "name": "Amir", "avatar": ""}),
            json.dumps({"id": "p2", "name": "Ali", "avatar": ""})
        ]

        result = await QueueService.add_to_queue(
            player_id="p2",
            player_name="Ali",
            avatar_url="",
            target_players=2,
            pieces_count=4,
        )

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
async def test_remove_from_queue():
    """
    Removes a player from the correct piece-count-specific queue.
    """
    with patch("app.services.queue_service.redis_client", new_callable=AsyncMock) as mock_redis:
        await QueueService.remove_from_queue("p1", 2, pieces_count=3)
        mock_redis.lrem.assert_called_once_with("matchmaking:queue:2p:3pieces", 0, "p1")