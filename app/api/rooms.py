import json
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.redis_client import redis_client
from app.services import room_service as RoomService

router = APIRouter(prefix="/api")


class CreateRoomRequest(BaseModel):
    room_id: str = ""
    player1_id: str = ""
    player1_name: str = ""
    player1_avatar: str = ""
    player2_id: str = ""
    player2_name: str = ""
    player2_avatar: str = ""
    player_count: int = 2
    pieces_count: int = 4
    coin_bet: int = 0


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


class JoinRoomRequest(BaseModel):
    player_id: str
    player_name: str = ""
    player_avatar: str = ""


def _player_meta(player_id: str, name: str, avatar: str) -> dict:
    return {"id": player_id, "name": name, "avatar": avatar}


@router.post("/rooms", response_model=RoomJoinResponse)
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
    )


@router.get("/rooms/{room_id}", response_model=RoomJoinResponse)
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


@router.post("/rooms/{room_id}/join")
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
        }

    player = _player_meta(req.player_id, req.player_name, req.player_avatar)
    room, seat, error = await RoomService.register_player(room_id, player)
    if error:
        status_code = 404 if error == "Room not found" else 400
        raise HTTPException(status_code=status_code, detail=error)

    await redis_client.set(f"player:{req.player_id}:meta", json.dumps(player))
    await RoomService.start_game(room_id, room)

    return {"room_id": room_id, "player_num": seat, "status": room["status"]}
