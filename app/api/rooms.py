import json
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from app.api.security import require_api_key, require_room_access
from app.redis_client import redis_client
from app.services import room_service as RoomService
from app.services.auth import TOKEN_TTL_SECONDS, issue_player_token

router = APIRouter(prefix="/api")

#: Player identifiers end up in Redis keys and URLs, so they stay conservative.
#: Room identifiers are even stricter because they are also part of the URL path.
PLAYER_ID_PATTERN = r"^[A-Za-z0-9_.-]{1,64}$"
ROOM_ID_PATTERN = r"^$|^[A-Za-z0-9_-]{1,64}$"

#: Board sizes the engine supports: a two- or four-seat board with 2-4 pieces.
PlayerCount = Literal[2, 4]
PiecesCount = Literal[2, 3, 4]


class CreateRoomRequest(BaseModel):
    """Room settings sent by Porteghal when it opens a match directly."""

    room_id: str = Field(default="", max_length=64, pattern=ROOM_ID_PATTERN)
    player1_id: str = Field(..., pattern=PLAYER_ID_PATTERN)
    player1_name: str = Field(default="", max_length=64)
    player1_avatar: str = Field(default="", max_length=512)
    player2_id: str = Field(default="", pattern=r"^$|" + PLAYER_ID_PATTERN)
    player2_name: str = Field(default="", max_length=64)
    player2_avatar: str = Field(default="", max_length=512)
    player_count: PlayerCount = 2
    pieces_count: PiecesCount = 4
    coin_bet: int = Field(default=0, ge=0)

    @field_validator("player1_name", "player2_name", "player1_avatar", "player2_avatar")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class RoomJoinResponse(BaseModel):
    room_id: str
    player1_id: str
    player1_name: str
    player1_avatar: str
    player2_id: str
    player2_name: str
    player2_avatar: str
    status: str
    coin_bet: int = 0
    #: Signed tokens per seated player; the WebView must present one to connect.
    player_tokens: dict[str, str] = Field(default_factory=dict)


class JoinRoomRequest(BaseModel):
    player_id: str = Field(..., pattern=PLAYER_ID_PATTERN)
    player_name: str = Field(default="", max_length=64)
    player_avatar: str = Field(default="", max_length=512)

    @field_validator("player_name", "player_avatar")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


def _player_meta(player_id: str, name: str, avatar: str) -> dict:
    return {"id": player_id, "name": name, "avatar": avatar}


@router.post(
    "/rooms",
    response_model=RoomJoinResponse,
    dependencies=[Depends(require_api_key)],
)
async def create_room(req: CreateRoomRequest):
    room_id = req.room_id or str(uuid.uuid4())[:8]
    room = RoomService.new_room(
        room_id,
        player_count=req.player_count,
        pieces_count=req.pieces_count,
        coin_bet=req.coin_bet,
    )

    # The room document is the single source of truth for the game settings.
    # Each player also gets a profile blob so reconnects and the queue watcher
    # can resolve a display name.
    await RoomService.save_room(room_id, room)

    player_tokens: dict[str, str] = {}
    for player_id, name, avatar in (
        (req.player1_id, req.player1_name, req.player1_avatar),
        (req.player2_id, req.player2_name, req.player2_avatar),
    ):
        if not player_id:
            continue
        player = _player_meta(player_id, name, avatar)
        await redis_client.set(f"player:{player_id}:meta", json.dumps(player))
        room, _seat, error = await RoomService.register_player(room_id, player)
        if error:
            raise HTTPException(status_code=409, detail=error)
        player_tokens[player_id] = issue_player_token(player_id, room_id)

    # The game only starts when every configured seat is filled.
    await RoomService.start_game(room_id, room)

    return RoomJoinResponse(
        room_id=room_id,
        player1_id=req.player1_id,
        player1_name=req.player1_name or "بازیکن ۱",
        player1_avatar=req.player1_avatar,
        player2_id=req.player2_id,
        player2_name=req.player2_name or "",
        player2_avatar=req.player2_avatar,
        status=room["status"],
        coin_bet=req.coin_bet,
        player_tokens=player_tokens,
    )


@router.get(
    "/rooms/{room_id}",
    response_model=RoomJoinResponse,
    dependencies=[Depends(require_room_access)],
)
async def get_room(room_id: str):
    room = await RoomService.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")

    meta = room.get("players_meta", {})
    p1 = meta.get("1", {})
    p2 = meta.get("2", {})

    return RoomJoinResponse(
        room_id=room_id,
        player1_id=p1.get("id", ""),
        player1_name=p1.get("name", "بازیکن ۱"),
        player1_avatar=p1.get("avatar", ""),
        player2_id=p2.get("id", ""),
        player2_name=p2.get("name", ""),
        player2_avatar=p2.get("avatar", ""),
        status=room.get("status", RoomService.ROOM_STATUS_WAITING),
        coin_bet=room.get("coin_bet", 0),
    )


@router.post(
    "/rooms/{room_id}/join",
    dependencies=[Depends(require_api_key)],
)
async def join_room(room_id: str, req: JoinRoomRequest):
    room = await RoomService.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")

    # Re-joining a seat the player already owns is a no-op (idempotent retry).
    existing_seat = RoomService.seat_of(room, req.player_id)
    if existing_seat is not None:
        return {
            "room_id": room_id,
            "player_num": existing_seat,
            "status": room.get("status"),
            "token": issue_player_token(req.player_id, room_id),
            "expires_in": TOKEN_TTL_SECONDS,
        }

    player = _player_meta(req.player_id, req.player_name, req.player_avatar)
    room, seat, error = await RoomService.register_player(room_id, player)
    if error:
        status_code = 404 if error == "Room not found" else 400
        raise HTTPException(status_code=status_code, detail=error)

    await redis_client.set(f"player:{req.player_id}:meta", json.dumps(player))
    await RoomService.start_game(room_id, room)

    return {
        "room_id": room_id,
        "player_num": seat,
        "status": room["status"],
        "token": issue_player_token(req.player_id, room_id),
        "expires_in": TOKEN_TTL_SECONDS,
    }
