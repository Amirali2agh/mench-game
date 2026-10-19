"""Turn rotation and dice-state tests (issues #10 and #13)."""
import pytest

from app.services.game_service import GameService


def _state(player_count: int, joined: int, current_turn: int = 0) -> dict:
    return {
        "player_count": player_count,
        "players": [{"id": f"p{index}"} for index in range(joined)],
        "current_turn": current_turn,
        "dice": 4,
        "dice_rolled": True,
        "consecutive_sixes": 2,
        "last_roll": {"player_id": "p0", "value": 4},
    }


@pytest.mark.parametrize("joined", [1, 2, 3])
def test_four_player_rotation_never_leaves_the_joined_roster(joined):
    """Issue #10: a 4-player room may start with fewer than four players."""
    state = _state(4, joined)

    seen = []
    for _ in range(joined * 2):
        GameService._rotate_turn(state)
        seen.append(state["current_turn"])

    assert seen == [index % joined for index in range(1, joined * 2 + 1)]


@pytest.mark.parametrize("current_turn", [4, 9, -5])
def test_rotation_clamps_an_out_of_range_current_turn(current_turn):
    """Issue #10: turn_order.index() must never raise ValueError."""
    state = _state(4, 4, current_turn=current_turn)

    GameService._rotate_turn(state)

    assert state["current_turn"] == 0


def test_rotation_cycles_back_to_the_first_seat():
    state = _state(4, 4)

    order = []
    for _ in range(4):
        order.append(state["current_turn"])
        GameService._rotate_turn(state)

    assert order == [0, 3, 1, 2]
    assert state["current_turn"] == 0


def test_rotation_clears_the_dice_but_keeps_the_last_roll():
    """Issue #13: a stale dice value must not leak into the next turn."""
    state = _state(2, 2)

    GameService._rotate_turn(state)

    assert state["dice"] is None
    assert state["dice_rolled"] is False
    assert state["last_roll"] == {"player_id": "p0", "value": 4}


def test_rotation_resets_consecutive_sixes():
    state = _state(2, 2)

    GameService._rotate_turn(state)

    assert state["consecutive_sixes"] == 0
