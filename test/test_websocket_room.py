"""
Tests for the active game-room WebSocket endpoint.

Note: this file was previously named ``test-websocket-room.py`` (hyphens), which
pytest's default ``python_files = test_*.py`` pattern never collects. The file
name and the mocks below were both broken, so these tests never ran.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

from app.api.websocket.room import router

# Setup a dummy FastAPI app to test the websocket room router in isolation
api_app = FastAPI()
api_app.include_router(router)


def _game_state() -> dict:
    return {
        "room_id": "room1",
        "player_count": 2,
        "pieces_count": 4,
        "players": [{"id": "p1", "name": "Amir", "avatar": ""}],
        "current_turn": 0,
        "dice": None,
        "dice_rolled": False,
        "pieces": {"p1": [-1, -1, -1, -1]},
        "status": "playing",
        "winner_id": None,
    }


def test_websocket_room_connection_and_sync():
    """
    Joining a room must broadcast the current game state to the new client.
    """
    with patch("app.api.websocket.room.GameService", new_callable=AsyncMock) as mock_game, \
         patch("app.api.websocket.room.redis_client", new_callable=AsyncMock) as mock_redis:

        # No room metadata in Redis: the state comes from GameService.
        mock_redis.get.return_value = None
        mock_game.get_game.return_value = _game_state()

        client = TestClient(api_app)
        with client.websocket_connect("/ws/room/room1?playerId=p1&playerName=Amir") as websocket:
            data = websocket.receive_json()
            assert data["type"] == "sync_state"
            assert data["game"]["room_id"] == "room1"

        mock_game.get_game.assert_awaited()


def test_websocket_room_roll_dice_action():
    """
    Sending roll_dice must call GameService and broadcast the resulting state.
    """
    with patch("app.api.websocket.room.GameService", new_callable=AsyncMock) as mock_game, \
         patch("app.api.websocket.room.redis_client", new_callable=AsyncMock) as mock_redis:

        mock_redis.get.return_value = None
        state = _game_state()
        mock_game.get_game.return_value = state

        rolled = {**_game_state(), "dice": 6, "dice_rolled": True}
        mock_game.roll_dice.return_value = rolled

        client = TestClient(api_app)
        with client.websocket_connect("/ws/room/room1?playerId=p1&playerName=Amir") as websocket:
            # Ignore the initial sync broadcast
            assert websocket.receive_json()["type"] == "sync_state"

            websocket.send_json({"action": "roll_dice"})

            message = websocket.receive_json()
            assert message["type"] == "sync_state"
            assert message["game"]["dice"] == 6

        mock_game.roll_dice.assert_awaited_once_with("room1", "p1")
