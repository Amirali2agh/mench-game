"""Single source of truth for the Mensch track geometry.

The board has four corners and a shared 40-cell circular track. Every corner
owns a *fixed* absolute offset on that track, so a piece's absolute cell is
always ``(corner_offset + relative_position) % 40``::

    corner 0 (red)    ->  20   (bottom-left yard)
    corner 1 (blue)   ->  30   (top-left yard)
    corner 2 (green)  ->   0   (top-right yard)
    corner 3 (yellow) ->  10   (bottom-right yard)

Seats are assigned to corners per match size. A four-player match uses all four
corners in seat order. A two-player match uses two *facing* corners (red vs.
green) so the players start exactly 20 cells apart instead of 10.

The frontend mirror of this table lives in ``front/src/utils/boardCoordinates.ts``
(``CORNER_OFFSETS``); keep the two in sync whenever the board changes.
"""

TRACK_LENGTH = 40

#: Fixed track offset per board corner, in visual corner order.
CORNER_OFFSETS = (20, 30, 0, 10)

#: Corner seat order for a full four-player match.
FOUR_PLAYER_SEATS = (0, 1, 2, 3)

#: Corner seat order for a two-player match (facing corners: red vs. green).
TWO_PLAYER_SEATS = (0, 2)


def track_offsets(player_count: int) -> tuple[int, ...]:
    """Return the absolute track offset for every seat of a match.

    The returned tuple is indexed by seat (the position of a player in
    ``state["players"]``), which is also the seat used by the turn order.
    """
    seats = TWO_PLAYER_SEATS if player_count == 2 else FOUR_PLAYER_SEATS
    return tuple(CORNER_OFFSETS[seat] for seat in seats[: max(player_count, 0)])


def track_offsets_for_state(state: dict) -> tuple[int, ...]:
    """Resolve the seat offsets of a game state, tolerating partial states.

    Rooms only start a match once the configured roster is complete, so the
    offsets normally match the roster length exactly. Legacy or hand-built
    states may omit ``player_count`` or carry more players than their seat
    plan; in that case fall back to the full four-corner layout so indexing by
    player position can never raise ``IndexError``.
    """
    players = state.get("players") or []
    player_count = state.get("player_count") or len(players)
    offsets = track_offsets(player_count)
    if len(offsets) < len(players):
        return track_offsets(len(CORNER_OFFSETS))
    return offsets


def absolute_position(seat_offsets: tuple[int, ...], seat: int, relative_pos: int) -> int:
    """Convert a seat-relative track position into an absolute track cell.

    The seat index wraps around the available corners so that a malformed state
    with more players than seats can never raise ``IndexError``.
    """
    if not seat_offsets:
        raise ValueError("No seat offsets available")
    return (seat_offsets[seat % len(seat_offsets)] + relative_pos) % TRACK_LENGTH
