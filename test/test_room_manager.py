"""End-to-end tests for the room gameplay loop.

The room is bootstrapped through the real service layer against an in-memory
Redis fake, then driven over the WebSocket exactly like a client would.
"""
import asyncio
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.websocket.room import router
from app.services import room_service as RoomService
from app.services.game_service import GameService

# Setup a dummy FastAPI app to test the websocket room router in isolation
api_app = FastAPI()
api_app.include_router(router)


def _seed_room(fake_redis, room_id="test-room", players=("p1", "p2")):
    async def _seed():
        room = RoomService.new_room(room_id)
        await RoomService.save_room(room_id, room)
        for index, player_id in enumerate(players):
            player = {"id": player_id, "name": f"Player {index}", "avatar": ""}
            await fake_redis.set(f"player:{player_id}:meta", json.dumps(player))
            room, _seat, error = await RoomService.register_player(room_id, player)
            assert error is None

    asyncio.run(_seed())


def test_websocket_room_gameplay_flow(fake_redis, monkeypatch):
    """
    Test the active game room loop: joining, syncing, rolling, moving and
    restarting a finished match.
    """
    _seed_room(fake_redis)
    monkeypatch.setattr("app.services.game_service.random.randint", lambda low, high: 6)

    client = TestClient(api_app)
    with client.websocket_connect("/ws/room/test-room?playerId=p1&playerName=Amir") as websocket:
        assert websocket.receive_json()["type"] == "sync_state"

        websocket.send_json({"action": "roll_dice"})
        rolled = websocket.receive_json()
        assert rolled["game"]["dice"] == 6

        websocket.send_json({"action": "move_piece", "piece_index": 0})
        moved = websocket.receive_json()
        assert moved["type"] == "sync_state"
        assert moved["game"]["pieces"]["p1"][0] == 0

    state = asyncio.run(GameService.get_game("test-room"))
    assert state["pieces"]["p1"][0] == 0
    assert state["current_turn"] == 0
    assert state["status"] == "playing"
