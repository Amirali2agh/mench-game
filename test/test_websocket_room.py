"""
Tests for the active game-room WebSocket endpoint.

Note: this file was previously named ``test-websocket-room.py`` (hyphens), which
pytest's default ``python_files = test_*.py`` pattern never collects. The file
name and the mocks below were both broken, so these tests never ran.

These tests run against the real service layer with an in-memory Redis fake, so
they exercise the room bootstrap (roster -> game state) instead of mocking it.
"""
import asyncio
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.websocket.room import router
from app.services import room_service as RoomService

# Setup a dummy FastAPI app to test the websocket room router in isolation
api_app = FastAPI()
api_app.include_router(router)


def seed_room(fake_redis, room_id="room1", players=("p1", "p2"), player_count=2):
    """Create a room with a complete roster and return it."""

    async def _seed():
        room = RoomService.new_room(room_id, player_count=player_count)
        await RoomService.save_room(room_id, room)
        for index, player_id in enumerate(players):
            player = {"id": player_id, "name": f"Player {index}", "avatar": ""}
            await fake_redis.set(f"player:{player_id}:meta", json.dumps(player))
            room, _seat, error = await RoomService.register_player(room_id, player)
            assert error is None
        return room

    return asyncio.run(_seed())


def test_websocket_room_connection_and_sync(fake_redis):
    """
    Joining a room must broadcast the current game state to the new client.
    """
    seed_room(fake_redis)

    client = TestClient(api_app)
    with client.websocket_connect("/ws/room/room1?playerId=p1&playerName=Amir") as websocket:
        data = websocket.receive_json()
        assert data["type"] == "sync_state"
        assert data["game"]["room_id"] == "room1"
        assert [player["id"] for player in data["game"]["players"]] == ["p1", "p2"]


def test_websocket_room_rejects_an_unseated_player(fake_redis):
    """A full room must not accept a third connection."""
    seed_room(fake_redis)

    client = TestClient(api_app)
    with client.websocket_connect("/ws/room/room1?playerId=intruder&playerName=X") as websocket:
        message = websocket.receive_json()
        assert message["type"] == "error"
        assert message["message"] == "Room is full"


def test_websocket_room_roll_dice_action(fake_redis, monkeypatch):
    """
    Sending roll_dice must call GameService and broadcast the resulting state.
    """
    seed_room(fake_redis)
    monkeypatch.setattr("app.services.game_service.random.randint", lambda low, high: 6)

    client = TestClient(api_app)
    with client.websocket_connect("/ws/room/room1?playerId=p1&playerName=Amir") as websocket:
        # Ignore the initial sync broadcast
        assert websocket.receive_json()["type"] == "sync_state"

        websocket.send_json({"action": "roll_dice"})

        message = websocket.receive_json()
        assert message["type"] == "sync_state"
        assert message["game"]["dice"] == 6
        assert message["game"]["dice_rolled"] is True
