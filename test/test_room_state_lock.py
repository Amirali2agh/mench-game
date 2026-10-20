"""Per-room mutation locking and state versioning (issue #19).

Every mutating action used to read the game state, mutate it and write it back
with no serialization, so two overlapping actions could both read the same
snapshot and the second write silently won. The lock is a Redis
``SET ... NX PX`` lease with a token-checked release; the state carries a
version so clients can drop out-of-order ``sync_state`` messages.
"""

import asyncio

import pytest

from app.services import room_service as RoomService
from app.services.game_service import GameService, RollResult
from app.utils.room_lock import RoomLockTimeout, room_lock

ROOM_ID = "lock-room"


async def _new_game(players: int = 2, pieces: int = 4, positions: list[int] | None = None) -> dict:
    state = await GameService.create_game(
        ROOM_ID,
        [{"id": f"p{index}", "name": f"P{index}", "avatar": ""} for index in range(1, players + 1)],
        pieces_count=pieces,
        player_count=players,
    )
    if positions is not None:
        state["pieces"]["p1"] = list(positions)
        await GameService.save_game(ROOM_ID, state)
    return state


def _fixed_dice(monkeypatch, value: int) -> None:
    monkeypatch.setattr("app.services.game_service.random.randint", lambda _low, _high: value)


@pytest.mark.asyncio
async def test_concurrent_rolls_are_serialized(fake_redis, monkeypatch):
    await _new_game(positions=[5, -1, -1, -1])
    _fixed_dice(monkeypatch, 3)

    results = await asyncio.gather(
        GameService.roll_dice(ROOM_ID, "p1"),
        GameService.roll_dice(ROOM_ID, "p1"),
        return_exceptions=True,
    )

    successes = [result for result in results if isinstance(result, RollResult)]
    errors = [result for result in results if isinstance(result, Exception)]

    assert len(successes) == 1
    assert len(errors) == 1
    assert "Dice already rolled" in str(errors[0])

    state = await GameService.get_game(ROOM_ID)
    assert state["roll_sequence"] == 1
    assert state["dice"] == 3


@pytest.mark.asyncio
async def test_concurrent_moves_lose_nothing(fake_redis, monkeypatch):
    await _new_game(positions=[5, -1, -1, -1])
    _fixed_dice(monkeypatch, 3)
    await GameService.roll_dice(ROOM_ID, "p1")

    results = await asyncio.gather(
        GameService.move_piece(ROOM_ID, "p1", 0),
        GameService.move_piece(ROOM_ID, "p1", 0),
        return_exceptions=True,
    )

    successes = [result for result in results if isinstance(result, dict)]
    errors = [result for result in results if isinstance(result, Exception)]

    assert len(successes) == 1
    assert len(errors) == 1
    assert "Not your turn" in str(errors[0])

    state = await GameService.get_game(ROOM_ID)
    assert state["pieces"]["p1"][0] == 8
    assert state["current_turn"] == 1


@pytest.mark.asyncio
async def test_lock_is_released_when_an_action_is_rejected(fake_redis, monkeypatch):
    await _new_game(positions=[5, -1, -1, -1])
    _fixed_dice(monkeypatch, 3)
    await GameService.roll_dice(ROOM_ID, "p1")

    with pytest.raises(ValueError):
        await GameService.move_piece(ROOM_ID, "p1", 99)

    # The rejected action must not keep the room locked.
    state = await GameService.move_piece(ROOM_ID, "p1", 0)
    assert state["pieces"]["p1"][0] == 8


@pytest.mark.asyncio
async def test_concurrent_registration_seats_both_players(fake_redis):
    room = RoomService.new_room(ROOM_ID, player_count=4)
    await RoomService.save_room(ROOM_ID, room)

    seats = await asyncio.gather(
        RoomService.register_player(ROOM_ID, {"id": "a", "name": "A", "avatar": ""}),
        RoomService.register_player(ROOM_ID, {"id": "b", "name": "B", "avatar": ""}),
    )

    assigned = sorted(seat for _room, seat, _error in seats if seat is not None)
    assert assigned == [1, 2]

    stored = await RoomService.get_room(ROOM_ID)
    assert sorted(player["id"] for player in RoomService.roster(stored)) == ["a", "b"]


@pytest.mark.asyncio
async def test_lock_times_out_instead_of_hanging(fake_redis):
    async with room_lock(ROOM_ID):
        with pytest.raises(RoomLockTimeout):
            async with room_lock(ROOM_ID, wait_seconds=0.05):
                pass


@pytest.mark.asyncio
async def test_lock_can_be_retaken_after_release(fake_redis):
    async with room_lock(ROOM_ID):
        pass

    async with room_lock(ROOM_ID, wait_seconds=0.05):
        acquired_again = True

    assert acquired_again


@pytest.mark.asyncio
async def test_state_version_advances_on_every_save(fake_redis, monkeypatch):
    state = await _new_game(positions=[5, -1, -1, -1])
    first_version = state["version"]
    _fixed_dice(monkeypatch, 3)

    rolled = await GameService.roll_dice(ROOM_ID, "p1")
    assert rolled.state["version"] > first_version

    moved = await GameService.move_piece(ROOM_ID, "p1", 0)
    assert moved["version"] > rolled.state["version"]


class _PausedAnimation:
    """Stand-in for ``asyncio`` inside the game service during the dice wait."""

    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.resume = asyncio.Event()

    async def sleep(self, _seconds: float) -> None:
        self.entered.set()
        await self.resume.wait()


@pytest.mark.asyncio
async def test_pass_turn_during_the_dice_animation_rotates_only_once(
    fake_redis, monkeypatch
):
    """The delayed advance must not rotate a turn the player already passed."""
    from app.api.websocket.room import auto_advance_turn

    await _new_game(positions=[-1, -1, -1, -1])
    _fixed_dice(monkeypatch, 3)
    animation = _PausedAnimation()
    # The delay now lives in the transport layer, not in the engine.
    monkeypatch.setattr("app.api.websocket.room.asyncio", animation)

    result = await GameService.roll_dice(ROOM_ID, "p1")
    assert result.auto_pass is True
    # The engine returns before the animation: the turn is still p1's.
    assert (await GameService.get_game(ROOM_ID))["current_turn"] == 0

    advance_task = asyncio.create_task(auto_advance_turn(ROOM_ID, result.state))
    await asyncio.wait_for(animation.entered.wait(), timeout=1)

    passed = await GameService.pass_turn(ROOM_ID, "p1")
    assert passed["current_turn"] == 1

    animation.resume.set()
    await asyncio.wait_for(advance_task, timeout=1)

    stored = await GameService.get_game(ROOM_ID)
    assert stored["current_turn"] == 1
    assert stored["dice"] is None
