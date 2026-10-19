import asyncio
import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from app.api.websocket.queue import router, _wait_for_match
from app.managers.queue_manager import queue_manager

# Setup a dummy FastAPI app named api_app (renamed from test_app to suppress pytest warning)
api_app = FastAPI()
api_app.include_router(router)


def test_websocket_queue_flow():
    """
    Test the entire WebSocket matchmaking loop: connection, metadata caching,
    matching and automatic cleanup with dynamic pieces count.
    """
    with patch("app.api.websocket.queue.QueueService", new_callable=AsyncMock) as mock_service, \
         patch.object(queue_manager, "send_match_found", new_callable=AsyncMock) as mock_send_match:

        mock_service.add_to_queue.return_value = {
            "room_id": "test-room-uuid",
            "players": [
                {"id": "p1", "name": "Amir", "avatar": ""},
                {"id": "p2", "name": "Ali", "avatar": ""}
            ],
            "pieces_count": 3
        }

        client = TestClient(api_app)
        with client.websocket_connect(
            "/ws/queue?playerId=p1&playerName=Amir&playerAvatarUrl=http://avatar&playerCount=2&piecesCount=3"
        ):
            pass

        mock_service.add_to_queue.assert_called_once_with(
            player_id="p1",
            player_name="Amir",
            avatar_url="http://avatar",
            target_players=2,
            pieces_count=3
        )

        # The player who completes the match is notified directly. Other
        # players receive the same event through their Redis watcher.
        mock_send_match.assert_called_once_with(
            "p1",
            "test-room-uuid",
            mock_service.add_to_queue.return_value["players"],
            3,
        )
        mock_service.remove_from_queue.assert_called_once_with("p1", 2, 3)
        assert "p1" not in queue_manager.active_connections


@pytest.mark.asyncio
async def test_wait_for_match_reads_room_metadata_from_redis():
    websocket = AsyncMock()
    player = {"id": "p1", "name": "Amir", "avatar": ""}
    room_meta = {
        "players_meta": {
            "1": player,
            "2": {"id": "p2", "name": "Ali", "avatar": ""},
        },
        "pieces_count": 3,
    }
    stored = {
        "player:p1:room": "room-123",
        "room:room-123:meta": json.dumps(room_meta),
    }

    with patch("app.api.websocket.queue.redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.get.side_effect = lambda key: stored.get(key)

        await _wait_for_match(websocket, "p1", 2, 4)

    websocket.send_json.assert_awaited_once_with({
        "type": "match_found",
        "room_id": "room-123",
        "players": [
            {"id": "p1", "name": "Amir", "avatar": ""},
            {"id": "p2", "name": "Ali", "avatar": ""},
        ],
        "pieces_count": 3,
    })
