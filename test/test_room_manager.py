import pytest
import json
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from app.api.websocket.room import router
from app.managers.room_manager import room_manager

# Setup a dummy FastAPI app to test the websocket room router in isolation
api_app = FastAPI()
api_app.include_router(router)

def test_websocket_room_gameplay_flow():
    """
    Test the entire active game room loop: joining, sync state broadcasts,
    rolling dice, moving pieces, and initiating restart actions.
    """
    # Patch GameService and redis client to mock database states
    with patch("app.api.websocket.room.GameService", new_callable=AsyncMock) as mock_game_service, \
         patch("app.api.websocket.room.redis_client", new_callable=AsyncMock) as mock_redis, \
         patch.object(room_manager, "broadcast", new_callable=AsyncMock) as mock_broadcast:
        
        # Setup mock game configurations and return values.
        # The Redis mock must be key-aware: the endpoint reads several distinct
        # keys and json.loads() each value, so a single blanket return value
        # (e.g. "4") makes json.loads produce an int and breaks the handler.
        room_settings = {
            "room:test-room:pieces_count": "4",
            "room:test-room:player_count": "2",
        }
        mock_redis.get.side_effect = lambda key: room_settings.get(key)
        
        mock_game_service.get_game.return_value = None  # First player joins triggers initialization
        mock_game_service.create_game.return_value = {
            "room_id": "test-room",
            "player_count": 1,
            "pieces_count": 4,
            "players": [{"id": "p1", "name": "Amir", "avatar": ""}],
            "current_turn": 0,
            "dice": None,
            "dice_rolled": False,
            "pieces": {"p1": [-1, -1, -1, -1]},
            "status": "playing",
            "winner_id": None
        }
        
        client = TestClient(api_app)
        
        # Act: Open WebSocket connection inside active game room
        with client.websocket_connect("/ws/room/test-room?playerId=p1&playerName=Amir") as websocket:
            
            # Action 1: Send roll_dice command
            mock_game_service.get_game.return_value = mock_game_service.create_game.return_value
            mock_game_service.roll_dice.return_value = mock_game_service.create_game.return_value
            
            websocket.send_json({"action": "roll_dice"})
            
            # Action 2: Send move_piece command
            mock_game_service.move_piece.return_value = mock_game_service.create_game.return_value
            websocket.send_json({"action": "move_piece", "piece_index": 0})
            
            # Action 3: Send restart_game command
            websocket.send_json({"action": "restart_game"})
        
        # Assert: Verify GameService called initialization and gameplay actions
        mock_game_service.create_game.assert_called()
        mock_game_service.roll_dice.assert_called_once_with("test-room", "p1")
        mock_game_service.move_piece.assert_called_once_with("test-room", "p1", 0)
        
        # Assert: Verify that room broadcast was invoked to sync connected clients
        assert mock_broadcast.call_count > 0