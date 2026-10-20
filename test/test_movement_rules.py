"""Movement legality of a single piece (issue #25).

The client greys out an illegal piece with its own copy of these rules
(`front/src/utils/movement.ts`), so the table below is deliberately identical to
the one in `front/src/utils/movement.test.ts`. A change to the rules that misses
one of the two files fails a test instead of drifting silently.
"""

import pytest

from app.services.game_service import (
    HOME_END_POSITION,
    HOME_START_POSITION,
    GameService,
)

YARD_POSITION = -1

#: ``current`` position × dice → (valid, resulting position).
MOVES = [
    (YARD_POSITION, 5, False, YARD_POSITION),
    (YARD_POSITION, 6, True, 0),
    (0, 3, True, 3),
    (39, 4, True, HOME_END_POSITION),
    (39, 5, False, 39),
    (41, 2, True, HOME_END_POSITION),
    (42, 2, False, 42),
    (HOME_END_POSITION, 1, False, HOME_END_POSITION),
]


@pytest.mark.parametrize("current,dice,valid,position", MOVES)
def test_calculate_new_position_matches_the_client_table(current, dice, valid, position):
    assert GameService._calculate_new_position(current, dice) == (valid, position)


def test_home_cells_hold_one_piece():
    pieces = [38, HOME_START_POSITION, YARD_POSITION, YARD_POSITION]
    assert GameService._is_home_position_available(pieces, 0, HOME_START_POSITION) is False
    assert GameService._is_home_position_available(pieces, 1, HOME_START_POSITION) is True


def test_track_cells_may_be_shared():
    pieces = [3, 3, YARD_POSITION, YARD_POSITION]
    assert GameService._is_home_position_available(pieces, 0, 3) is True
