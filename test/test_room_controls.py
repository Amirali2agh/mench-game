"""Room control actions: rematch and pass_turn ownership (issue #14).

``next_round`` and ``restart_game`` are one action: a finished game can be
restarted by a seated player, never while a match is still running. ``pass_turn``
belongs to the active player only and is refused while that player can still move.
"""
import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.websocket.room import router
from app.services import room_service as RoomService
from app.services.game_service import GameService

api_app = FastAPI()
api_app.include_router(router)


def _finish(room_id: str, winner_id: str = "p1") -> None:
    async def _run() -> None:
        state = await GameService.get_game(room_id)
        assert state is not None
        state["status"] = "finished"
        state["winner_id"] = winner_id
        await GameService.save_game(room_id, state)

    asyncio.run(_run())


def _prime_roll(room_id: str, dice: int, pieces: list[int] | None = None) -> None:
    async def _run() -> None:
        state = await GameService.get_game(room_id)
        assert state is not None
        state["dice"] = dice
        state["dice_rolled"] = True
        if pieces is not None:
            state["pieces"]["p1"] = pieces
        await GameService.save_game(room_id, state)

    asyncio.run(_run())


def test_rematch_requires_a_finished_game(room_factory):
    room = room_factory()

    with pytest.raises(ValueError, match="still in progress"):
        asyncio.run(RoomService.start_rematch(room["room_id"], "p1"))


def test_rematch_rejects_a_player_outside_the_roster(room_factory):
    room = room_factory()
    _finish(room["room_id"])

    with pytest.raises(ValueError, match="seated"):
        asyncio.run(RoomService.start_rematch(room["room_id"], "intruder"))


def test_rematch_preserves_the_roster_and_settings(room_factory):
    room = room_factory(coin_bet=150, pieces_count=3)
    room_id = room["room_id"]
    _finish(room_id)

    new_state = asyncio.run(RoomService.start_rematch(room_id, "p2"))

    assert new_state["status"] == "playing"
    assert new_state["winner_id"] is None
    assert [player["id"] for player in new_state["players"]] == ["p1", "p2"]
    assert new_state["coin_bet"] == 150
    assert new_state["pieces_count"] == 3
    assert new_state["pieces"]["p1"] == [-1, -1, -1]

    stored = asyncio.run(GameService.get_game(room_id))
    assert stored["status"] == "playing"
    room_meta = asyncio.run(RoomService.get_room(room_id))
    assert room_meta["status"] == RoomService.ROOM_STATUS_PLAYING
    assert room_meta["coin_bet"] == 150


def test_rematch_clears_the_previous_winner_report_guard(room_factory):
    room = room_factory()
    room_id = room["room_id"]
    _finish(room_id)
    assert asyncio.run(RoomService.claim_winner_report(room_id)) is True

    asyncio.run(RoomService.start_rematch(room_id, "p1"))

    # The new match must be able to report its own winner.
    assert asyncio.run(RoomService.claim_winner_report(room_id)) is True


def test_next_round_over_the_socket_starts_a_new_game(room_factory):
    room = room_factory()
    room_id = room["room_id"]
    _finish(room_id)

    client = TestClient(api_app)
    with client.websocket_connect(f"/ws/room/{room_id}?playerId=p1&playerName=P1") as websocket:
        assert websocket.receive_json()["type"] == "sync_state"

        websocket.send_json({"action": "next_round"})
        message = websocket.receive_json()

        assert message["type"] == "sync_state"
        assert message["game"]["status"] == "playing"
        assert message["game"]["winner_id"] is None
        assert message["game"]["pieces"]["p1"] == [-1] * 4


def test_next_round_is_rejected_while_the_game_is_running(room_factory):
    room = room_factory()
    room_id = room["room_id"]

    client = TestClient(api_app)
    with client.websocket_connect(f"/ws/room/{room_id}?playerId=p1&playerName=P1") as websocket:
        assert websocket.receive_json()["type"] == "sync_state"

        websocket.send_json({"action": "next_round"})
        error = websocket.receive_json()

        assert error["type"] == "error"
        assert error["message"] == "The current game is still in progress"


def test_restart_game_is_an_alias_for_next_round(room_factory):
    room = room_factory()
    room_id = room["room_id"]
    _finish(room_id)

    client = TestClient(api_app)
    with client.websocket_connect(f"/ws/room/{room_id}?playerId=p2&playerName=P2") as websocket:
        assert websocket.receive_json()["type"] == "sync_state"

        websocket.send_json({"action": "restart_game"})
        message = websocket.receive_json()

        assert message["type"] == "sync_state"
        assert message["game"]["status"] == "playing"


def test_pass_turn_requires_the_active_player(room_factory):
    room = room_factory()
    room_id = room["room_id"]

    client = TestClient(api_app)
    with client.websocket_connect(f"/ws/room/{room_id}?playerId=p2&playerName=P2") as websocket:
        assert websocket.receive_json()["type"] == "sync_state"

        websocket.send_json({"action": "pass_turn"})
        error = websocket.receive_json()

        assert error["type"] == "error"
        assert error["message"] == "Not your turn"

    state = asyncio.run(GameService.get_game(room_id))
    assert state["current_turn"] == 0


def test_pass_turn_is_refused_while_a_legal_move_exists(room_factory):
    room = room_factory()
    room_id = room["room_id"]
    _prime_roll(room_id, dice=6)

    with pytest.raises(ValueError, match="legal move"):
        asyncio.run(GameService.pass_turn(room_id, "p1"))


def test_pass_turn_rotates_and_clears_the_roll(room_factory):
    room = room_factory()
    room_id = room["room_id"]
    # Every piece is blocked inside the home column, so nothing can move.
    _prime_roll(room_id, dice=6, pieces=[43, 43, 43, 43])

    client = TestClient(api_app)
    with client.websocket_connect(f"/ws/room/{room_id}?playerId=p1&playerName=P1") as websocket:
        assert websocket.receive_json()["type"] == "sync_state"

        websocket.send_json({"action": "pass_turn"})
        message = websocket.receive_json()

        assert message["type"] == "sync_state"
        assert message["game"]["current_turn"] == 1
        assert message["game"]["dice"] is None
        assert message["game"]["dice_rolled"] is False


def test_pass_turn_is_rejected_when_the_game_is_over(room_factory):
    room = room_factory()
    room_id = room["room_id"]
    _finish(room_id)

    with pytest.raises(ValueError, match="not active"):
        asyncio.run(GameService.pass_turn(room_id, "p1"))
