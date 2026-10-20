"""Room lifecycle shared by the REST and WebSocket entry points.

A room owns its roster and its game settings. The game state is only created
once the configured number of players has joined, so a four-player room can
never start (and rotate turns) with a partial roster.
"""

import asyncio
import json

from app.config import settings
from app.redis_client import redis_client
from app.services.game_service import GameService
from app.utils.room_lock import room_lock

DEFAULT_PLAYER_COUNT = 2
DEFAULT_PIECES_COUNT = 4

ROOM_STATUS_WAITING = "waiting"
ROOM_STATUS_PLAYING = "playing"
ROOM_STATUS_FINISHED = "finished"
ROOM_STATUS_CANCELLED = "cancelled"

#: How the room came to exist, which decides how long it may wait for players.
#: A room opened from a link is not a queue entry, so the matchmaking timeout
#: must never cancel it (issue #60).
ROOM_SOURCE_DIRECT = "direct"
ROOM_SOURCE_MATCHMAKING = "matchmaking"

#: How often a waiting WebSocket checks whether the roster has been completed.
ROOM_READY_POLL_INTERVAL = 0.25

#: Lifetime of the one-shot "winner already reported" claim.
WINNER_REPORT_TTL = 24 * 60 * 60


def room_meta_key(room_id: str) -> str:
    return f"room:{room_id}:meta"


def new_room(
    room_id: str,
    player_count: int = DEFAULT_PLAYER_COUNT,
    pieces_count: int = DEFAULT_PIECES_COUNT,
    coin_bet: int = 0,
    source: str = ROOM_SOURCE_DIRECT,
) -> dict:
    """Build an empty room document; settings live inside the metadata blob."""
    return {
        "room_id": room_id,
        "players": [],
        "players_meta": {},
        "player_count": player_count,
        "pieces_count": pieces_count,
        "coin_bet": coin_bet,
        "status": ROOM_STATUS_WAITING,
        "source": source,
    }


def wait_timeout(room: dict) -> float:
    """How long a room without a complete roster may wait, in seconds.

    Rooms the matchmaking queue created keep the short queue window; a room
    shared as a link gets `ROOM_WAIT_TIMEOUT`, because a host may need minutes to
    get a friend in. Documents written before `source` existed are direct rooms.
    """
    if room.get("source") == ROOM_SOURCE_MATCHMAKING:
        return settings.MATCHMAKING_TIMEOUT
    return settings.ROOM_WAIT_TIMEOUT


async def get_room(room_id: str) -> dict | None:
    raw = await redis_client.get(room_meta_key(room_id))
    return json.loads(raw) if raw else None


async def save_room(room_id: str, room: dict) -> None:
    await redis_client.set(room_meta_key(room_id), json.dumps(room))


def roster(room: dict) -> list[dict]:
    """Return the seated players in seat order."""
    players_meta = room.get("players_meta") or {}
    seated = [entry for entry in players_meta.values() if (entry or {}).get("id")]
    return seated


def required_players(room: dict) -> int:
    return int(room.get("player_count") or DEFAULT_PLAYER_COUNT)


def pieces_count(room: dict) -> int:
    return int(room.get("pieces_count") or DEFAULT_PIECES_COUNT)


def coin_bet(room: dict) -> int:
    return int(room.get("coin_bet") or 0)


def is_full(room: dict) -> bool:
    return len(roster(room)) >= required_players(room)


def seat_of(room: dict, player_id: str) -> int | None:
    for seat, entry in (room.get("players_meta") or {}).items():
        if (entry or {}).get("id") == player_id:
            return int(seat)
    return None


async def register_player(
    room_id: str, player: dict
) -> tuple[dict | None, int | None, str | None]:
    """Seat ``player`` in the first free slot.

    Returns ``(room, seat, error)``. Re-registering a seated player is a no-op,
    which keeps WebSocket reconnects idempotent. The read-modify-write runs
    under the room lock so two players connecting at the same time can never be
    seated in the same slot.
    """
    async with room_lock(room_id):
        room = await get_room(room_id)
        if room is None:
            return None, None, "Room not found"

        existing_seat = seat_of(room, player["id"])
        if existing_seat is not None:
            return room, existing_seat, None

        capacity = required_players(room)
        if len(roster(room)) >= capacity:
            return room, None, "Room is full"
        if room.get("status") != ROOM_STATUS_WAITING:
            return room, None, "Room is no longer accepting players"

        players_meta = room.setdefault("players_meta", {})
        open_seat = next(
            (
                seat
                for seat in range(1, capacity + 1)
                if not (players_meta.get(str(seat)) or {}).get("id")
            ),
            None,
        )
        if open_seat is None:
            return room, None, "Room is full"

        players_meta[str(open_seat)] = player
        room["players"] = [entry["id"] for entry in roster(room)]
        await save_room(room_id, room)
        return room, open_seat, None


async def start_game(room_id: str, room: dict) -> dict | None:
    """Create the game state once the roster is complete, otherwise ``None``."""
    async with room_lock(room_id):
        current = await get_room(room_id)
        if current is None:
            return None
        # Keep the caller's view of the roster in sync with the stored one.
        room.update(current)

        state = await GameService.get_game(room_id)
        if state:
            return state

        if not is_full(room):
            return None

        state = await GameService.create_game(
            room_id,
            roster(room),
            pieces_count=pieces_count(room),
            player_count=required_players(room),
            coin_bet=coin_bet(room),
        )
        room["players"] = [entry["id"] for entry in roster(room)]
        room["status"] = ROOM_STATUS_PLAYING
        await save_room(room_id, room)
        return state


async def wait_for_game(room_id: str, timeout: float) -> dict | None:
    """Wait until another connection completes the roster, or time out."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        state = await GameService.get_game(room_id)
        if state:
            return state
        remaining = deadline - loop.time()
        if remaining <= 0:
            return None
        await asyncio.sleep(min(ROOM_READY_POLL_INTERVAL, remaining))


def winner_report_key(room_id: str) -> str:
    return f"room:{room_id}:winner_reported"


async def claim_winner_report(room_id: str) -> bool:
    """Reserve the single winner report of the current match.

    ``report_winner`` pays out the prize, so only the first caller may report:
    a duplicated forfeit timer or a reconnect must never pay twice. The claim is
    released when a rematch starts, so the next match reports its own winner.
    """
    claimed = await redis_client.set(
        winner_report_key(room_id), "1", nx=True, ex=WINNER_REPORT_TTL
    )
    return bool(claimed)


async def clear_winner_report(room_id: str) -> None:
    await redis_client.delete(winner_report_key(room_id))


async def start_rematch(room_id: str, player_id: str) -> dict:
    """Restart a finished match with the same roster and settings.

    Only a seated player may restart, and only once the previous match is over,
    so a rematch can never wipe a game that is still being played. The lock
    makes the "is it finished?" check and the replacement state one step: two
    simultaneous rematch requests cannot both reset the board.
    """
    async with room_lock(room_id):
        room = await get_room(room_id)
        if room is None:
            raise ValueError("Room not found")

        state = await GameService.get_game(room_id)
        if state is None:
            raise ValueError("Game not found")
        if state.get("status") != "finished":
            raise ValueError("The current game is still in progress")

        players = state.get("players") or []
        if player_id not in {player["id"] for player in players}:
            raise ValueError("Only a seated player can start a rematch")

        new_state = await GameService.create_game(
            room_id,
            players,
            pieces_count=int(state.get("pieces_count") or pieces_count(room)),
            player_count=int(state.get("player_count") or required_players(room)),
            coin_bet=coin_bet(room) or int(state.get("coin_bet") or 0),
        )
        room["status"] = ROOM_STATUS_PLAYING
        await save_room(room_id, room)
        await clear_winner_report(room_id)
        return new_state


async def cancel_room(room_id: str, room: dict) -> None:
    """Close a room whose roster could not be completed in time."""
    async with room_lock(room_id):
        room["status"] = ROOM_STATUS_CANCELLED
        await save_room(room_id, room)
