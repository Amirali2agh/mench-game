import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.config import settings
from app.managers.queue_manager import queue_manager
from app.services.queue_service import QueueService
from app.redis_client import redis_client
from app.utils.redis_keys import RedisKeys

router = APIRouter()


async def _room_players(room_id: str) -> list[dict]:
    """Resolve the matched roster from the room document."""
    raw_meta = await redis_client.get(f"room:{room_id}:meta")
    if not raw_meta:
        return []
    room_meta = json.loads(raw_meta)
    return [
        player
        for player in room_meta.get("players_meta", {}).values()
        if player.get("id")
    ]


async def _match_already_created(player_id: str) -> dict | None:
    """Return the pending match of a player, if a match already exists."""
    room_id = await redis_client.get(RedisKeys.player_room(player_id))
    if not room_id:
        return None

    raw_meta = await redis_client.get(f"room:{room_id}:meta")
    if not raw_meta:
        return None

    room_meta = json.loads(raw_meta)
    return {
        "room_id": room_id,
        "pieces_count": int(room_meta.get("pieces_count") or 0),
    }


async def _wait_for_match(
    websocket: WebSocket,
    player_id: str,
    target_players: int,
    pieces_count: int,
) -> None:
    """
    Deliver the match of a waiting player, or time the queue entry out.

    Matches arrive through a per-player Redis list, so the player can be
    connected to any worker. When nothing shows up within MATCHMAKING_TIMEOUT the
    player is removed from the queue and receives ``queue_timeout`` instead of
    waiting forever.
    """
    match = await _match_already_created(player_id)
    if match is None:
        popped = await redis_client.blpop(
            [RedisKeys.queue_notifications(player_id)],
            timeout=settings.MATCHMAKING_TIMEOUT,
        )
        if popped is not None:
            _key, raw = popped
            match = json.loads(raw)

    if match is None:
        await QueueService.remove_from_queue(player_id, target_players, pieces_count)
        await websocket.send_json({"type": "queue_timeout", "player_id": player_id})
        return

    room_id = match["room_id"]
    await websocket.send_json({
        "type": "match_found",
        "room_id": room_id,
        "players": await _room_players(room_id),
        "pieces_count": int(match.get("pieces_count") or pieces_count),
    })


@router.websocket("/ws/queue")
async def websocket_queue_endpoint(
    websocket: WebSocket,
    playerId: str = Query(...),
    playerName: str = Query(...),
    playerAvatarUrl: str = Query(""),
    playerCount: int = Query(2),
    piecesCount: int = Query(4),
):
    """Redis-backed matchmaking with worker-independent match delivery."""
    await queue_manager.connect(playerId, websocket)
    match_watch_task = None

    try:
        match_result = await QueueService.add_to_queue(
            player_id=playerId,
            player_name=playerName,
            avatar_url=playerAvatarUrl,
            target_players=playerCount,
            pieces_count=piecesCount,
        )

        if match_result:
            # This connection created the match. Other matched players keep a
            # Redis watcher, so we only need to notify the current connection
            # directly. This avoids duplicate match_found messages.
            await queue_manager.send_match_found(
                playerId,
                match_result["room_id"],
                match_result["players"],
                match_result["pieces_count"],
            )
        else:
            # The first player may be connected to a different worker from the
            # player that completes the match. Redis closes that gap.
            match_watch_task = asyncio.create_task(
                _wait_for_match(websocket, playerId, playerCount, piecesCount)
            )

        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        queue_manager.disconnect(playerId)
        await QueueService.remove_from_queue(
            playerId, playerCount, piecesCount
        )
    except Exception:
        queue_manager.disconnect(playerId)
        await QueueService.remove_from_queue(
            playerId, playerCount, piecesCount
        )
    finally:
        if match_watch_task:
            match_watch_task.cancel()
            try:
                await match_watch_task
            except asyncio.CancelledError:
                pass
