import asyncio
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.config import settings
from app.managers.room_manager import room_manager
from app.services import room_service as RoomService
from app.services.game_service import GameService
from app.redis_client import redis_client
from app.services.prize_service import report_winner, update_room_status
from app.api.security import reject_websocket, resolve_websocket_player
from app.services.auth import AuthError, verify_player_token
from app.utils.identifiers import is_valid_player_id, is_valid_room_id
from app.utils.limits import (
    MAX_CHAT_CHARS,
    MAX_FRAME_BYTES,
    MAX_PLAYER_NAME_CHARS,
    TokenBucket,
    sanitize_text,
)
from app.utils.room_lock import room_lock

logger = logging.getLogger(__name__)

#: How long to keep the rolled dice on screen before handing the turn on.
AUTO_PASS_DELAY_SECONDS = 2

#: Fire-and-forget tasks keep a reference until they finish.
_background_tasks: set[asyncio.Task] = set()

router = APIRouter()


async def broadcast_room(room_id: str, message: dict) -> None:
    """
    Broadcast to the room and start the disconnect flow for dead sockets.

    ``RoomManager.broadcast`` prunes a socket whose send failed; the player is
    then on the 60-second forfeit clock like any other disconnect.
    """
    failed = await room_manager.broadcast(room_id, message)
    for player_id in failed:
        room_manager.start_disconnect_timer(
            room_id, player_id, forfeit_active_player
        )


async def auto_advance_turn(room_id: str, rolled_state: dict) -> None:
    """
    Wait for the client dice animation, then hand the turn to the next player.

    This runs as a background task so the socket's receive loop is never
    blocked; a pass_turn that lands meanwhile wins because the rotation is
    re-checked under the room lock.
    """
    await asyncio.sleep(AUTO_PASS_DELAY_SECONDS)
    try:
        state = await GameService.advance_after_roll(room_id, rolled_state)
    except Exception:
        logger.exception("Automatic turn advance failed for room %s", room_id)
        return
    if state is None:
        return
    await broadcast_room(room_id, {"type": "sync_state", "game": state})


def _spawn(coro) -> None:
    """Run ``coro`` in the background, keeping a reference until it finishes."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def forfeit_active_player(room_id: str, player_id: str) -> None:
    """
    Callback executed when a player stays disconnected past the forfeit window.

    A two-player match ends immediately with the remaining player as the winner.
    With more players the disconnected one is eliminated and the match keeps
    going, so a single dropped client can never hand the prize to an arbitrary
    opponent. The winner is reported once per match by ``report_game_winner``.
    """
    async with room_lock(room_id):
        state = await GameService.get_game(room_id)
        if not state or state.get("status") != "playing":
            return

        players = state.get("players") or []
        if player_id not in {player["id"] for player in players}:
            return

        eliminated = list(state.get("eliminated_players") or [])
        if player_id in eliminated:
            return
        eliminated.append(player_id)
        state["eliminated_players"] = eliminated

        remaining = [player for player in players if player["id"] not in eliminated]
        if len(remaining) <= 1:
            state["status"] = "finished"
            state["winner_id"] = remaining[0]["id"] if remaining else None
            state["dice"] = None
            state["dice_rolled"] = False
        elif state["players"][GameService._current_player_index(state)]["id"] == player_id:
            # The seat that just dropped out was on turn: pass it along.
            state = GameService._rotate_turn(state)

        await GameService.save_game(room_id, state)

    await broadcast_room(room_id, {"type": "sync_state", "game": state})
    await report_game_winner(room_id, state)


async def report_game_winner(room_id: str, state: dict) -> None:
    """
    Report game winner to porteghal and update room status.
    Shared helper used by both WebSocket endpoints.

    ``report_winner`` pays out the prize, so the first caller claims the match
    and every later call (duplicate timer, reconnect) is a no-op.
    """
    if state.get("status") != "finished" or not state.get("winner_id"):
        return
    if not await RoomService.claim_winner_report(room_id):
        logger.info("Winner of room %s was already reported", room_id)
        return
    try:
        meta_key = f"room:{room_id}:meta"
        raw = await redis_client.get(meta_key)
        if raw:
            meta = json.loads(raw)
            winner_player_num = next(
                (num for num, mp in meta.get("players_meta", {}).items()
                 if mp.get("id") == state["winner_id"]),
                None
            )
            if winner_player_num:
                await report_winner(
                    room_id=room_id,
                    player_id=state["winner_id"],
                    win_type="normal",
                )
            await update_room_status(room_id=room_id, status="finished")
    except Exception as exc:
        logger.warning("Prize service error for room %s: %s", room_id, exc)


async def handle_gameplay_loop(
    websocket: WebSocket,
    room_id: str,
    player_id: str,
    player_name: str,
) -> None:
    """
    Shared gameplay message loop used by both WebSocket endpoints.
    Handles roll_dice, move_piece, next_round, restart_game, chat and pass_turn.

    Frames are size-capped and rate-limited per connection so one client cannot
    flood the room or the broadcast fan-out. The chat author is the profile
    resolved at connection time, never the name in the frame.
    """
    bucket = TokenBucket()
    sender_name = sanitize_text(player_name, MAX_PLAYER_NAME_CHARS) or "بازیکن"

    while True:
        data = await websocket.receive_text()

        if len(data.encode("utf-8")) > MAX_FRAME_BYTES:
            await websocket.send_json({"type": "error", "message": "Message too large"})
            continue
        if not bucket.consume():
            await websocket.send_json({"type": "error", "message": "Too many actions"})
            continue

        try:
            message = json.loads(data)
            action = message.get("action")

            if action == "roll_dice":
                result = await GameService.roll_dice(room_id, player_id)
                await broadcast_room(
                    room_id, {"type": "sync_state", "game": result.state}
                )
                if result.auto_pass:
                    _spawn(auto_advance_turn(room_id, result.state))

            elif action == "move_piece":
                piece_index = message.get("piece_index")
                if piece_index is None:
                    await websocket.send_json({"type": "error", "message": "piece_index is required for move_piece action"})
                    continue
                try:
                    parsed_index = int(piece_index)
                except (ValueError, TypeError):
                    await websocket.send_json({"type": "error", "message": "Invalid piece_index format. Must be an integer."})
                    continue

                state = await GameService.move_piece(room_id, player_id, parsed_index)
                await broadcast_room(room_id, {"type": "sync_state", "game": state})
                await report_game_winner(room_id, state)

            elif action in ("next_round", "restart_game"):
                # One rematch action: ``restart_game`` stays as a server-side
                # alias so older clients keep working.
                state = await RoomService.start_rematch(room_id, player_id)
                room_manager.cancel_disconnect_timers(room_id)
                await broadcast_room(room_id, {"type": "sync_state", "game": state})

            elif action == "chat":
                chat_text = sanitize_text(message.get("message"), MAX_CHAT_CHARS)
                if chat_text:
                    await broadcast_room(room_id, {
                        "type": "chat",
                        "player_id": player_id,
                        "player_name": sender_name,
                        "message": chat_text,
                    })

            elif action == "pass_turn":
                state = await GameService.pass_turn(room_id, player_id)
                await broadcast_room(room_id, {"type": "sync_state", "game": state})

        except json.JSONDecodeError:
            await websocket.send_json({"type": "error", "message": "Malformed JSON payload received"})
        except ValueError as e:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception as e:
            await websocket.send_json({"type": "error", "message": f"An unexpected error occurred: {str(e)}"})


async def _load_player_meta(player_id: str, player_name: str) -> dict:
    """Prefer the stored player profile, fall back to the query parameters."""
    raw = await redis_client.get(f"player:{player_id}:meta")
    if raw:
        return json.loads(raw)
    return {"id": player_id, "name": player_name, "avatar": ""}


async def _prepare_room(websocket: WebSocket, room_id: str, player: dict) -> dict | None:
    """
    Seat the connecting player and return a playable game state.

    A room only starts once its configured roster is complete. Until then the
    connected players receive ``waiting_for_players``; if the room is still
    incomplete after ``MATCHMAKING_TIMEOUT`` it is cancelled and a
    ``room_timeout`` message is broadcast. Returns ``None`` when the game could
    not be started, in which case the caller closes the connection.
    """
    room = await RoomService.get_room(room_id)
    if room is None:
        if not settings.DEBUG:
            await websocket.send_json(
                {"type": "error", "message": "Room not found"}
            )
            return None
        room = RoomService.new_room(room_id)
        await RoomService.save_room(room_id, room)

    # Only players the room document already knows about may join. Without
    # this check any socket could append itself to a live match.
    if RoomService.seat_of(room, player["id"]) is None and not settings.DEBUG:
        await websocket.send_json(
            {"type": "error", "message": "Player is not seated in this room"}
        )
        return None

    room, _seat, error = await RoomService.register_player(room_id, player)
    if error or room is None:
        await websocket.send_json(
            {"type": "error", "message": error or "Room is unavailable"}
        )
        return None

    state = await RoomService.start_game(room_id, room)
    if state:
        return state

    await broadcast_room(room_id, {
        "type": "waiting_for_players",
        "room_id": room_id,
        "joined": len(RoomService.roster(room)),
        "required": RoomService.required_players(room),
        "players": RoomService.roster(room),
    })

    state = await RoomService.wait_for_game(room_id, settings.MATCHMAKING_TIMEOUT)
    if state:
        return state

    await RoomService.cancel_room(room_id, room)
    await broadcast_room(room_id, {
        "type": "room_timeout",
        "room_id": room_id,
        "joined": len(RoomService.roster(room)),
        "required": RoomService.required_players(room),
    })
    return None


@router.websocket("/ws/room/{room_id}")
async def websocket_room_endpoint(
    websocket: WebSocket,
    room_id: str,
    playerId: str = Query(""),
    playerName: str = Query(""),
    token: str = Query(""),
):
    """
    WebSocket endpoint for active Mensch game rooms.

    The player id comes from the signed token; ``playerId`` is only read in the
    DEBUG dev flow. The complete roster is persisted in Redis; the game starts
    as soon as every configured seat is filled.
    """
    if not is_valid_room_id(room_id):
        await reject_websocket(websocket, "Invalid room id")
        return

    player_id = await resolve_websocket_player(
        websocket, room_id=room_id, token=token, player_id=playerId
    )
    if player_id is None:
        return

    await room_manager.connect(room_id, player_id, websocket)

    try:
        player = await _load_player_meta(player_id, playerName)
        state = await _prepare_room(websocket, room_id, player)
        if state is None:
            room_manager.disconnect(room_id, player_id, websocket)
            await websocket.close()
            return

        await broadcast_room(room_id, {"type": "sync_state", "game": state})
        await handle_gameplay_loop(
            websocket, room_id, player_id, player.get("name") or playerName
        )

    except WebSocketDisconnect:
        room_manager.disconnect(room_id, player_id, websocket)
        # A reconnect replaces the socket; only a player with no live socket
        # starts the forfeit clock.
        if not room_manager.is_connected(room_id, player_id):
            room_manager.start_disconnect_timer(
                room_id, player_id, forfeit_active_player
            )
    except Exception:
        # A coding error must never forfeit a live match; log it and drop the
        # connection instead of arming the timer.
        logger.exception("Room socket failed for %s/%s", room_id, player_id)
        room_manager.disconnect(room_id, player_id, websocket)
        await websocket.close(code=1011)


@router.websocket("/ws/game/{room_id}/{player_num}")
async def websocket_game_endpoint(
    websocket: WebSocket,
    room_id: str,
    player_num: str,
    token: str = Query(""),
):
    """
    Porteghal-compatible WebSocket endpoint.

    The seat is named by the path segment, but the identity still has to be
    proven: the token must belong to the player stored for that seat.
    """
    if not is_valid_room_id(room_id) or player_num not in ("1", "2", "3", "4"):
        await reject_websocket(websocket, "Invalid room or seat")
        return

    room_meta = await RoomService.get_room(room_id)

    if room_meta:
        players_meta = room_meta.get("players_meta", {})
        player_meta = players_meta.get(player_num, {})
        seat_id = player_meta.get("id")
        player_name = player_meta.get("name", f"بازیکن {player_num}")
    else:
        seat_id = None
        player_name = f"بازیکن {player_num}"
        players_meta = {}
        player_meta = {}

    if token:
        try:
            player_id = verify_player_token(token, room_id=room_id)
        except AuthError as exc:
            await reject_websocket(websocket, f"Authentication failed: {exc}")
            return
        if not is_valid_player_id(player_id):
            await reject_websocket(
                websocket, "Authentication failed: invalid player id"
            )
            return
        if room_meta and seat_id != player_id:
            await reject_websocket(
                websocket, "Authentication failed: token does not match this seat"
            )
            return
    elif settings.DEBUG:
        player_id = seat_id or f"player_{player_num}"
    else:
        await reject_websocket(websocket, "Authentication failed: a token is required")
        return

    await room_manager.connect(room_id, player_id, websocket)

    try:
        if room_meta:
            await websocket.send_json({
                "type": "game_info",
                "room_id": room_id,
                "player_num": int(player_num),
                "players": players_meta,
                "coin_bet": room_meta.get("coin_bet", 0),
            })

        player = player_meta or {"id": player_id, "name": player_name, "avatar": ""}
        state = await _prepare_room(websocket, room_id, player)
        if state is None:
            room_manager.disconnect(room_id, player_id, websocket)
            await websocket.close()
            return

        await broadcast_room(room_id, {"type": "sync_state", "game": state})
        await handle_gameplay_loop(
            websocket, room_id, player_id, player.get("name") or player_name
        )

    except WebSocketDisconnect:
        room_manager.disconnect(room_id, player_id, websocket)
        # A reconnect replaces the socket; only a player with no live socket
        # starts the forfeit clock.
        if not room_manager.is_connected(room_id, player_id):
            room_manager.start_disconnect_timer(
                room_id, player_id, forfeit_active_player
            )
    except Exception:
        # A coding error must never forfeit a live match; log it and drop the
        # connection instead of arming the timer.
        logger.exception("Room socket failed for %s/%s", room_id, player_id)
        room_manager.disconnect(room_id, player_id, websocket)
        await websocket.close(code=1011)
