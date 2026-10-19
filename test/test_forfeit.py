"""Forfeit handling: one report per match and multi-player aware elimination (#15).

A disconnecting player must not hand the win to a random opponent, and the prize
report is a payment trigger, so it has to happen exactly once per match.
"""
import asyncio

import pytest

from app.api.websocket import room as room_api
from app.services.game_service import GameService


def _record_reports(monkeypatch) -> dict:
    calls = {"winner": [], "status": []}

    async def fake_report_winner(**kwargs):
        calls["winner"].append(kwargs)

    async def fake_update_room_status(**kwargs):
        calls["status"].append(kwargs)

    monkeypatch.setattr(room_api, "report_winner", fake_report_winner)
    monkeypatch.setattr(room_api, "update_room_status", fake_update_room_status)
    return calls


def test_two_player_forfeit_declares_the_opponent_the_winner(room_factory, monkeypatch):
    calls = _record_reports(monkeypatch)
    room = room_factory()
    room_id = room["room_id"]

    asyncio.run(room_api.forfeit_active_player(room_id, "p1"))

    state = asyncio.run(GameService.get_game(room_id))
    assert state["status"] == "finished"
    assert state["winner_id"] == "p2"
    assert calls["winner"] == [{"room_id": room_id, "player_id": "p2", "win_type": "normal"}]
    assert calls["status"] == [{"room_id": room_id, "status": "finished"}]


def test_winner_report_is_guarded_per_room(room_factory, monkeypatch):
    calls = _record_reports(monkeypatch)
    room = room_factory()
    room_id = room["room_id"]

    async def _finish() -> dict:
        state = await GameService.get_game(room_id)
        state["status"] = "finished"
        state["winner_id"] = "p2"
        await GameService.save_game(room_id, state)
        return state

    state = asyncio.run(_finish())

    asyncio.run(room_api.report_game_winner(room_id, state))
    asyncio.run(room_api.report_game_winner(room_id, state))

    assert len(calls["winner"]) == 1
    assert len(calls["status"]) == 1


def test_forfeit_is_idempotent_for_the_same_player(room_factory, monkeypatch):
    calls = _record_reports(monkeypatch)
    room = room_factory()
    room_id = room["room_id"]

    asyncio.run(room_api.forfeit_active_player(room_id, "p1"))
    asyncio.run(room_api.forfeit_active_player(room_id, "p1"))

    assert len(calls["winner"]) == 1


def test_four_player_forfeit_eliminates_and_keeps_playing(room_factory, monkeypatch):
    calls = _record_reports(monkeypatch)
    room = room_factory(player_count=4)
    room_id = room["room_id"]
    assert room["current_turn"] == 0

    asyncio.run(room_api.forfeit_active_player(room_id, "p1"))

    state = asyncio.run(GameService.get_game(room_id))
    assert state["status"] == "playing"
    assert state["winner_id"] is None
    assert state["eliminated_players"] == ["p1"]
    # The four-player order is [0, 3, 1, 2], so seat 3 takes over the turn.
    assert state["current_turn"] == 3
    assert calls["winner"] == []


def test_last_remaining_player_wins_a_four_player_forfeit(room_factory, monkeypatch):
    calls = _record_reports(monkeypatch)
    room = room_factory(player_count=4)
    room_id = room["room_id"]

    for player_id in ("p1", "p2", "p3"):
        asyncio.run(room_api.forfeit_active_player(room_id, player_id))

    state = asyncio.run(GameService.get_game(room_id))
    assert state["status"] == "finished"
    assert state["winner_id"] == "p4"
    assert len(calls["winner"]) == 1


def test_forfeit_from_an_unknown_player_is_ignored(room_factory):
    room = room_factory()
    room_id = room["room_id"]

    asyncio.run(room_api.forfeit_active_player(room_id, "ghost"))

    state = asyncio.run(GameService.get_game(room_id))
    assert state["status"] == "playing"
    assert state["winner_id"] is None


def test_eliminated_player_can_no_longer_act(room_factory):
    room = room_factory(player_count=4)
    room_id = room["room_id"]

    asyncio.run(room_api.forfeit_active_player(room_id, "p2"))

    with pytest.raises(ValueError, match="no longer playing"):
        asyncio.run(GameService.roll_dice(room_id, "p2"))


def test_rotation_skips_eliminated_seats():
    state = {
        "player_count": 4,
        "players": [{"id": f"p{index}"} for index in range(1, 5)],
        "pieces": {f"p{index}": [-1, -1, -1, -1] for index in range(1, 5)},
        "eliminated_players": ["p2"],
        "current_turn": 0,
    }

    GameService._rotate_turn(state)

    # Seat 3 (p4) is next in [0, 3, 1, 2] and seat 1 (p2) is out.
    assert state["current_turn"] == 3

    GameService._rotate_turn(state)

    # Seat 1 is skipped entirely.
    assert state["current_turn"] == 2
