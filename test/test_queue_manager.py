import pytest
from unittest.mock import AsyncMock, MagicMock
from app.managers.queue_manager import QueueManager

@pytest.mark.asyncio
async def test_queue_manager_connect():
    """
    Test that connection is successfully accepted and registered.
    """
    manager = QueueManager()
    mock_ws = AsyncMock()
    
    await manager.connect("player1", mock_ws)
    
    mock_ws.accept.assert_called_once()
    assert "player1" in manager.active_connections
    assert manager.active_connections["player1"] == mock_ws


def test_queue_manager_disconnect():
    """
    Test that connection is correctly unregistered upon disconnect.
    """
    manager = QueueManager()
    mock_ws = MagicMock()
    manager.active_connections["player1"] = mock_ws
    
    manager.disconnect("player1")
    
    assert "player1" not in manager.active_connections


@pytest.mark.asyncio
async def test_queue_manager_send_match_found():
    """
    Test that match_found JSON payload is sent correctly to the target player's websocket.
    """
    manager = QueueManager()
    mock_ws = AsyncMock()
    manager.active_connections["player1"] = mock_ws
    
    matched_players = [
        {"id": "player1", "name": "Amir", "avatar": ""},
        {"id": "player2", "name": "Ali", "avatar": ""}
    ]
    
    await manager.send_match_found("player1", "test-room-uuid", matched_players, 3)
    
    expected_payload = {
        "type": "match_found",
        "room_id": "test-room-uuid",
        "players": matched_players,
        "pieces_count": 3,
    }
    mock_ws.send_json.assert_called_once_with(expected_payload)