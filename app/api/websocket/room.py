import json
import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from app.managers.room_manager import room_manager
from app.services.game_service import GameService
from app.redis_client import redis_client
from app.services.prize_service import report_winner, update_room_status

logger = logging.getLogger(__name__)

router = APIRouter()


async def forfeit_active_player(room_id: str, player_id: str) -> None:
    """
    Callback function executed when a player remains disconnected for more than 60 seconds.
    Sets the game status to finished and declares the remaining online opponent as the winner.
    """
    state = await GameService.get_game(room_id)
    if state and state["status"] == "playing":
        state["status"] = "finished"
        opponents = [p for p in state["players"] if p["id"] != player_id]
        if opponents:
            state["winner_id"] = opponents[0]["id"]

        await GameService.save_game(room_id, state)
        await room_manager.broadcast(room_id, {
            "type": "sync_state",
            "game": state
        })


async def report_game_winner(room_id: str, state: dict) -> None:
    """
    Report game winner to porteghal and update room status.
    Shared helper used by both WebSocket endpoints.
    """
    if state.get("status") != "finished" or not state.get("winner_id"):
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
    Handles roll_dice, move_piece, next_round, restart_game, chat, pass_turn.
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

            elif action == "next_round":
                state = await GameService.get_game(room_id)
                if state:
                    state = await GameService.create_game(room_id, state["players"], state["pieces_count"], state["player_count"])
                    await room_manager.broadcast(room_id, {"type": "sync_state", "game": state})

            elif action == "restart_game":
                state = await GameService.get_game(room_id)
                if state:
                    state = await GameService.create_game(room_id, state["players"], state["pieces_count"], state["player_count"])
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
                state = await GameService.get_game(room_id)
                if state and state["status"] == "playing":
                    state = GameService._rotate_turn(state)
                    await GameService.save_game(room_id, state)
                    await room_manager.broadcast(room_id, {"type": "sync_state", "game": state})

        except json.JSONDecodeError:
            await websocket.send_json({"type": "error", "message": "Malformed JSON payload received"})
        except ValueError as e:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception as e:
            await websocket.send_json({"type": "error", "message": f"An unexpected error occurred: {str(e)}"})


@router.websocket("/ws/room/{room_id}")
async def websocket_room_endpoint(
    websocket: WebSocket,
    room_id: str,
    playerId: str = Query(...),
    playerName: str = Query(...)
):
    """
    WebSocket endpoint for active Mensch game rooms.
    The complete matchmaking roster is persisted in Redis so the first player
    immediately receives a state containing every matched player.
    """
    await room_manager.connect(room_id, playerId, websocket)

    try:
        raw_room_meta = await redis_client.get(f"room:{room_id}:meta")
        room_meta = json.loads(raw_room_meta) if raw_room_meta else {}
        matched_players = [
            player for player in room_meta.get("players_meta", {}).values()
            if player.get("id")
        ]

        state = await GameService.get_game(room_id)
        if not state:
            raw_pieces_count = await redis_client.get(f"room:{room_id}:pieces_count")
            pieces_count = int(room_meta.get("pieces_count", raw_pieces_count or 4))

            raw_player_count = await redis_client.get(f"room:{room_id}:player_count")
            player_count = int(room_meta.get("player_count", raw_player_count or len(matched_players) or 2))

            if not matched_players:
                player_meta = await redis_client.get(f"player:{playerId}:meta")
                matched_players = [
                    json.loads(player_meta) if player_meta else {
                        "id": playerId,
                        "name": playerName,
                        "avatar": "",
                    }
                ]

            state = await GameService.create_game(
                room_id,
                matched_players,
                pieces_count,
                player_count,
            )
        else:
            known_ids = {p["id"] for p in state.get("players", [])}
            changed = False

            for player in matched_players:
                if player["id"] not in known_ids:
                    state["players"].append(player)
                    state.setdefault("pieces", {})[player["id"]] = [-1] * state.get("pieces_count", room_meta.get("pieces_count", 4))
                    changed = True

            if playerId not in known_ids and not any(p["id"] == playerId for p in matched_players):
                player_meta = await redis_client.get(f"player:{playerId}:meta")
                meta_dict = json.loads(player_meta) if player_meta else {
                    "id": playerId,
                    "name": playerName,
                    "avatar": "",
                }
                state["players"].append(meta_dict)
                state.setdefault("pieces", {})[playerId] = [-1] * state.get("pieces_count", 4)
                changed = True

            if room_meta.get("player_count"):
                state["player_count"] = int(room_meta["player_count"])

            if changed:
                await GameService.save_game(room_id, state)

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
    meta_key = f"room:{room_id}:meta"
    raw = await redis_client.get(meta_key)

    if raw:
        room_meta = json.loads(raw)
        players_meta = room_meta.get("players_meta", {})
        player_meta = players_meta.get(player_num, {})
        player_id = player_meta.get("id", f"player_{player_num}")
        player_name = player_meta.get("name", f"بازیکن {player_num}")
        room_has_meta = True
    else:
        player_id = f"player_{player_num}"
        player_name = f"بازیکن {player_num}"
        players_meta = {}
        player_meta = {"id": player_id, "name": player_name, "avatar": ""}
        room_has_meta = False

    await room_manager.connect(room_id, player_id, websocket)

    try:
        if room_has_meta:
            await websocket.send_json({
                "type": "game_info",
                "room_id": room_id,
                "player_num": int(player_num),
                "players": players_meta,
                "coin_bet": room_meta.get("coin_bet", 0),
            })

        state = await GameService.get_game(room_id)
        if state:
            await room_manager.broadcast(room_id, {"type": "sync_state", "game": state})
        else:
            pieces_count = 4
            player_count = 2
            if room_has_meta:
                pieces_count = int(room_meta.get("pieces_count", 4))
                player_count = int(room_meta.get("player_count", 2))

            matched_players = [
                player for player in players_meta.values()
                if player.get("id")
            ]
            if not matched_players:
                matched_players = [player_meta]

            state = await GameService.create_game(
                room_id,
                matched_players,
                pieces_count=pieces_count,
                player_count=player_count,
            )
            await room_manager.broadcast(room_id, {"type": "sync_state", "game": state})

        await handle_gameplay_loop(websocket, room_id, player_id, player_name)

    except WebSocketDisconnect:
        room_manager.disconnect(room_id, player_id, websocket)
        room_manager.start_disconnect_timer(room_id, player_id, forfeit_active_player)
    except Exception:
        room_manager.disconnect(room_id, player_id, websocket)
        room_manager.start_disconnect_timer(room_id, player_id, forfeit_active_player)
