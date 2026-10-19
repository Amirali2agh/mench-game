"""Room lifecycle tests: a match only starts with a complete roster (issue #10)."""
import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.rooms import router as rooms_router
from app.api.websocket.room import router as room_router
from app.config import settings
from app.services import room_service as RoomService
from app.services.game_service import GameService

api_app = FastAPI()
api_app.include_router(rooms_router)
api_app.include_router(room_router)


def _create_room(client, **payload):
    response = client.post("/api/rooms", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_four_player_room_does_not_start_with_two_players(fake_redis):
    """Regression for the IndexError reproduction in issue #10."""
    client = TestClient(api_app)
    created = _create_room(
        client,
        player_count=4,
        pieces_count=4,
        player1_id="a",
        player1_name="A",
    )
    room_id = created["room_id"]
    assert created["status"] == "waiting"

    joined = client.post(
        f"/api/rooms/{room_id}/join", json={"player_id": "b", "player_name": "B"}
    )
    assert joined.status_code == 200
    assert joined.json()["status"] == "waiting"

    # No game state yet, so no turn can be rotated and no seat can be indexed.
    assert asyncio.run(GameService.get_game(room_id)) is None


def test_two_player_room_starts_immediately_when_both_players_are_known(fake_redis):
    client = TestClient(api_app)
    created = _create_room(
        client,
        player_count=2,
        pieces_count=4,
        player1_id="a",
        player1_name="A",
        player2_id="b",
        player2_name="B",
    )

    assert created["status"] == "playing"
    state = asyncio.run(GameService.get_game(created["room_id"]))
    assert [player["id"] for player in state["players"]] == ["a", "b"]
    assert state["track_offsets"] == [20, 0]


def test_incomplete_room_times_out_and_is_cancelled(fake_redis, monkeypatch):
    monkeypatch.setattr(settings, "MATCHMAKING_TIMEOUT", 0.05)
    client = TestClient(api_app)
    created = _create_room(
        client,
        player_count=4,
        pieces_count=4,
        player1_id="a",
        player1_name="A",
    )
    room_id = created["room_id"]
    client.post(f"/api/rooms/{room_id}/join", json={"player_id": "b", "player_name": "B"})

    with client.websocket_connect(f"/ws/room/{room_id}?playerId=a&playerName=A") as websocket:
        waiting = websocket.receive_json()
        assert waiting["type"] == "waiting_for_players"
        assert waiting["joined"] == 2
        assert waiting["required"] == 4

        timed_out = websocket.receive_json()
        assert timed_out["type"] == "room_timeout"
        assert timed_out["joined"] == 2
        assert timed_out["required"] == 4

    room = asyncio.run(RoomService.get_room(room_id))
    assert room["status"] == RoomService.ROOM_STATUS_CANCELLED
    assert asyncio.run(GameService.get_game(room_id)) is None


def test_room_starts_when_the_last_player_joins(fake_redis, monkeypatch):
    monkeypatch.setattr(settings, "MATCHMAKING_TIMEOUT", 5.0)
    client = TestClient(api_app)
    created = _create_room(
        client,
        player_count=2,
        pieces_count=3,
        player1_id="a",
        player1_name="A",
    )
    room_id = created["room_id"]

    with client.websocket_connect(f"/ws/room/{room_id}?playerId=a&playerName=A") as websocket:
        waiting = websocket.receive_json()
        assert waiting["type"] == "waiting_for_players"
        assert waiting["joined"] == 1
        assert waiting["required"] == 2

        # The second player completes the roster over REST while the first
        # connection is still waiting for a game.
        joined = client.post(
            f"/api/rooms/{room_id}/join", json={"player_id": "b", "player_name": "B"}
        )
        assert joined.status_code == 200
        assert joined.json()["player_num"] == 2
        assert joined.json()["status"] == "playing"

        synced = websocket.receive_json()
        assert synced["type"] == "sync_state"
        assert [player["id"] for player in synced["game"]["players"]] == ["a", "b"]
        assert synced["game"]["pieces_count"] == 3
        assert synced["game"]["track_offsets"] == [20, 0]


def test_join_is_rejected_once_the_room_is_full(fake_redis):
    client = TestClient(api_app)
    created = _create_room(
        client,
        player_count=2,
        player1_id="a",
        player1_name="A",
        player2_id="b",
        player2_name="B",
    )

    response = client.post(
        f"/api/rooms/{created['room_id']}/join",
        json={"player_id": "c", "player_name": "C"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Room is full"


def test_porteghal_endpoint_sends_game_info_then_state(fake_redis):
    """/ws/game/{room_id}/{player_num} must announce the roster before playing."""
    client = TestClient(api_app)
    created = _create_room(
        client,
        player_count=2,
        pieces_count=4,
        coin_bet=150,
        player1_id="a",
        player1_name="A",
        player2_id="b",
        player2_name="B",
    )
    room_id = created["room_id"]

    with client.websocket_connect(f"/ws/game/{room_id}/1") as websocket:
        game_info = websocket.receive_json()
        assert game_info["type"] == "game_info"
        assert game_info["player_num"] == 1
        assert game_info["coin_bet"] == 150

        synced = websocket.receive_json()
        assert synced["type"] == "sync_state"
        assert synced["game"]["players"][0]["id"] == "a"
