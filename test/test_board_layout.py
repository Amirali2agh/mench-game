"""Geometry tests for the shared 40-cell track (issue #11)."""
from app.services.board_layout import (
    TRACK_LENGTH,
    track_offsets,
    track_offsets_for_state,
)
from app.services.game_service import GameService


def test_two_player_seats_start_exactly_twenty_cells_apart():
    first, second = track_offsets(2)

    assert (second - first) % TRACK_LENGTH == 20


def test_four_player_seats_are_evenly_spaced():
    offsets = track_offsets(4)

    gaps = [
        (offsets[index + 1] - offsets[index]) % TRACK_LENGTH
        for index in range(len(offsets) - 1)
    ]
    assert gaps == [10, 10, 10]
    assert (offsets[0] - offsets[-1]) % TRACK_LENGTH == 10
    assert sorted(offsets) == [0, 10, 20, 30]


def test_seat_offsets_are_stable_and_ordered_by_seat():
    assert track_offsets(4) == (20, 30, 0, 10)
    assert track_offsets(2) == (20, 0)
    assert track_offsets(1) == (20,)
    assert track_offsets(0) == ()


def test_state_offsets_fall_back_to_four_corners_for_oversized_rosters():
    state = {"player_count": 2, "players": [{"id": str(index)} for index in range(3)]}

    assert len(track_offsets_for_state(state)) == 4


def test_state_offsets_use_the_configured_player_count():
    state = {"player_count": 2, "players": [{"id": "0"}, {"id": "1"}]}

    assert track_offsets_for_state(state) == track_offsets(2)


def test_two_player_capture_happens_on_the_facing_cell():
    """Player 0 relative 20 and player 1 relative 0 occupy the same cell."""
    state = {
        "player_count": 2,
        "players": [{"id": "red"}, {"id": "green"}],
        "pieces": {"red": [20, -1, -1, -1], "green": [0, -1, -1, -1]},
    }

    captured = GameService._handle_captures(state, "red", 20)

    assert captured
    assert state["pieces"]["green"][0] == -1


def test_two_player_pieces_never_capture_from_ten_cells_away():
    """Regression: the old 4-player offsets (20/30) put the starts 10 apart."""
    state = {
        "player_count": 2,
        "players": [{"id": "red"}, {"id": "green"}],
        "pieces": {"red": [10, -1, -1, -1], "green": [0, -1, -1, -1]},
    }

    captured = GameService._handle_captures(state, "red", 10)

    assert not captured
    assert state["pieces"]["green"][0] == 0


def test_oversized_roster_cannot_index_out_of_range():
    state = {
        "player_count": 4,
        "players": [{"id": f"p{index}"} for index in range(5)],
        "pieces": {f"p{index}": [0, -1, -1, -1] for index in range(5)},
    }

    # Must not raise even though there are more players than corner seats.
    GameService._handle_captures(state, "p0", 0)
