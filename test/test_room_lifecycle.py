"""Room lifecycle tests: when a match starts and how long a room may wait.

A match only starts with a complete roster (issue #10), and the wait window
depends on how the room was created (issue #60).
"""
import asyncio
import time

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
    monkeypatch.setattr(settings, "ROOM_WAIT_TIMEOUT", 0.05)
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
        assert timed_out["timeout"] == 0.05

    room = asyncio.run(RoomService.get_room(room_id))
    assert room["status"] == RoomService.ROOM_STATUS_CANCELLED
    assert asyncio.run(GameService.get_game(room_id)) is None


def test_direct_link_room_waits_for_players_without_the_queue_timeout(
    fake_redis, monkeypatch
):
    """Issue #60: a room opened from a link is not a matchmaking queue entry.

    The queue timeout must not cancel it; the longer room wait applies instead,
    and the timeout message reports which window was used.
    """
    monkeypatch.setattr(settings, "MATCHMAKING_TIMEOUT", 30)
    monkeypatch.setattr(settings, "ROOM_WAIT_TIMEOUT", 0.05)
    client = TestClient(api_app)
    created = _create_room(
        client,
        player_count=2,
        pieces_count=4,
        player1_id="a",
        player1_name="A",
    )

    started = time.monotonic()
    with client.websocket_connect(
        f"/ws/room/{created['room_id']}?playerId=a&playerName=A"
    ) as websocket:
        assert websocket.receive_json()["type"] == "waiting_for_players"
        assert websocket.receive_json()["type"] == "room_timeout"

    # The queue timeout (30 s) would still be waiting here.
    assert time.monotonic() - started < 5


def test_matchmaking_room_keeps_the_matchmaking_timeout(fake_redis, monkeypatch):
    """The room wait must not leak into rooms the queue created."""
    monkeypatch.setattr(settings, "MATCHMAKING_TIMEOUT", 0.05)
    monkeypatch.setattr(settings, "ROOM_WAIT_TIMEOUT", 30)

    async def _prepare() -> str:
        room = RoomService.new_room(
            "queued-room",
            player_count=2,
            pieces_count=4,
            source=RoomService.ROOM_SOURCE_MATCHMAKING,
        )
        await RoomService.save_room("queued-room", room)
        player = {"id": "a", "name": "A", "avatar": ""}
        await RoomService.register_player("queued-room", player)
        return "queued-room"

    room_id = asyncio.run(_prepare())
    client = TestClient(api_app)

    started = time.monotonic()
    with client.websocket_connect(
        f"/ws/room/{room_id}?playerId=a&playerName=A"
    ) as websocket:
        assert websocket.receive_json()["type"] == "waiting_for_players"
        assert websocket.receive_json()["type"] == "room_timeout"

    assert time.monotonic() - started < 5


def test_wait_timeout_follows_the_room_source(monkeypatch):
    monkeypatch.setattr(settings, "MATCHMAKING_TIMEOUT", 30)
    monkeypatch.setattr(settings, "ROOM_WAIT_TIMEOUT", 300)

    direct = RoomService.new_room("direct-room")
    queued = RoomService.new_room(
        "queued-room", source=RoomService.ROOM_SOURCE_MATCHMAKING
    )

    assert RoomService.wait_timeout(direct) == 300
    assert RoomService.wait_timeout(queued) == 30
    # A room document written before the source field existed is a direct room.
    assert RoomService.wait_timeout({"room_id": "legacy"}) == 300


def test_room_starts_when_the_last_player_joins(fake_redis, monkeypatch):
    monkeypatch.setattr(settings, "ROOM_WAIT_TIMEOUT", 5.0)
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
