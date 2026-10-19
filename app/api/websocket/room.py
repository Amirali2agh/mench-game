import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.config import settings
from app.managers.room_manager import room_manager
from app.services import room_service as RoomService
from app.services.game_service import GameService
from app.redis_client import redis_client
from app.services.prize_service import report_winner, update_room_status

logger = logging.getLogger(__name__)

router = APIRouter()


async def forfeit_active_player(room_id: str, player_id: str) -> None:
    """
    Callback executed when a player stays disconnected past the forfeit window.

    A two-player match ends immediately with the remaining player as the winner.
    With more players the disconnected one is eliminated and the match keeps
    going, so a single dropped client can never hand the prize to an arbitrary
    opponent. The winner is reported once per match by ``report_game_winner``.
    """
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
    await room_manager.broadcast(room_id, {"type": "sync_state", "game": state})
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
    """
    while True:
        data = await websocket.receive_text()

        try:
            message = json.loads(data)
            action = message.get("action")

            if action == "roll_dice":
                state = await GameService.roll_dice(room_id, player_id)
                await room_manager.broadcast(room_id, {"type": "sync_state", "game": state})

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
                await room_manager.broadcast(room_id, {"type": "sync_state", "game": state})
                await report_game_winner(room_id, state)

            elif action in ("next_round", "restart_game"):
                # One rematch action: ``restart_game`` stays as a server-side
                # alias so older clients keep working.
                state = await RoomService.start_rematch(room_id, player_id)
                room_manager.cancel_disconnect_timers(room_id)
                await room_manager.broadcast(room_id, {"type": "sync_state", "game": state})

            elif action == "chat":
                chat_text = message.get("message", "").strip()
                sender_name = message.get("playerName", player_name)
                if chat_text:
                    await room_manager.broadcast(room_id, {
                        "type": "chat",
                        "player_id": player_id,
                        "player_name": sender_name,
                        "message": chat_text,
                    })

            elif action == "pass_turn":
                state = await GameService.pass_turn(room_id, player_id)
                await room_manager.broadcast(room_id, {"type": "sync_state", "game": state})

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
        room = RoomService.new_room(room_id)
        await RoomService.save_room(room_id, room)

    room, _seat, error = await RoomService.register_player(room_id, player)
    if error or room is None:
        await websocket.send_json(
            {"type": "error", "message": error or "Room is unavailable"}
        )
        return None

    state = await RoomService.start_game(room_id, room)
    if state:
        return state

    await room_manager.broadcast(room_id, {
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
    await room_manager.broadcast(room_id, {
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
    playerId: str = Query(...),
    playerName: str = Query(...)
):
    """
    WebSocket endpoint for active Mensch game rooms.
    The complete roster is persisted in Redis; the game starts as soon as every
    configured seat is filled.
    """
    await room_manager.connect(room_id, playerId, websocket)

    try:
        player = await _load_player_meta(playerId, playerName)
        state = await _prepare_room(websocket, room_id, player)
        if state is None:
            room_manager.disconnect(room_id, playerId, websocket)
            await websocket.close()
            return

        await room_manager.broadcast(room_id, {"type": "sync_state", "game": state})
        await handle_gameplay_loop(websocket, room_id, playerId, playerName)

    except WebSocketDisconnect:
        room_manager.disconnect(room_id, playerId, websocket)
        room_manager.start_disconnect_timer(room_id, playerId, forfeit_active_player)
    except Exception:
        room_manager.disconnect(room_id, playerId, websocket)
        room_manager.start_disconnect_timer(room_id, playerId, forfeit_active_player)


@router.websocket("/ws/game/{room_id}/{player_num}")
async def websocket_game_endpoint(
    websocket: WebSocket,
    room_id: str,
    player_num: str,
):
    """
    Porteghal-compatible WebSocket endpoint.
    """
    room_meta = await RoomService.get_room(room_id)

    if room_meta:
        players_meta = room_meta.get("players_meta", {})
        player_meta = players_meta.get(player_num, {})
        player_id = player_meta.get("id", f"player_{player_num}")
        player_name = player_meta.get("name", f"بازیکن {player_num}")
    else:
        player_id = f"player_{player_num}"
        player_name = f"بازیکن {player_num}"
        players_meta = {}
        player_meta = {"id": player_id, "name": player_name, "avatar": ""}

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

        await room_manager.broadcast(room_id, {"type": "sync_state", "game": state})
        await handle_gameplay_loop(websocket, room_id, player_id, player_name)

    except WebSocketDisconnect:
        room_manager.disconnect(room_id, player_id, websocket)
        room_manager.start_disconnect_timer(room_id, player_id, forfeit_active_player)
    except Exception:
        room_manager.disconnect(room_id, player_id, websocket)
        room_manager.start_disconnect_timer(room_id, player_id, forfeit_active_player)
