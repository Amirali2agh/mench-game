"""Room lifecycle shared by the REST and WebSocket entry points.

A room owns its roster and its game settings. The game state is only created
once the configured number of players has joined, so a four-player room can
never start (and rotate turns) with a partial roster.
"""

import asyncio
import json

from app.redis_client import redis_client
from app.services.game_service import GameService

DEFAULT_PLAYER_COUNT = 2
DEFAULT_PIECES_COUNT = 4

ROOM_STATUS_WAITING = "waiting"
ROOM_STATUS_PLAYING = "playing"
ROOM_STATUS_FINISHED = "finished"
ROOM_STATUS_CANCELLED = "cancelled"

#: How often a waiting WebSocket checks whether the roster has been completed.
ROOM_READY_POLL_INTERVAL = 0.25


def room_meta_key(room_id: str) -> str:
    return f"room:{room_id}:meta"


def new_room(
    room_id: str,
    player_count: int = DEFAULT_PLAYER_COUNT,
    pieces_count: int = DEFAULT_PIECES_COUNT,
    coin_bet: int = 0,
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
    }


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
    which keeps WebSocket reconnects idempotent.
    """
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


async def cancel_room(room_id: str, room: dict) -> None:
    """Close a room whose roster could not be completed in time."""
    room["status"] = ROOM_STATUS_CANCELLED
    await save_room(room_id, room)
