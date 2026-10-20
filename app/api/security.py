"""Credentials accepted by the REST and WebSocket surfaces.

Two credentials exist:

* ``X-API-Key`` for a trusted backend (Porteghal) creating rooms or minting
  player tokens.
* a signed player token in the query string for browser/WebView connections.

``DEBUG=true`` keeps both optional so the local flow (open the client with
``?roomId=..&playerId=..``) still works; production fails closed.
"""

import hmac

from fastapi import Header, HTTPException, Query, WebSocket

from app.config import settings
from app.services.auth import AuthError, verify_player_token
from app.utils.identifiers import is_valid_player_id


def api_key_matches(provided: str | None) -> bool:
    """Constant-time comparison against the configured shared secret."""
    expected = settings.PORTEGHAL_API_KEY
    if not expected:
        return False
    return hmac.compare_digest(provided or "", expected)


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Allow only the trusted backend, or the DEBUG dev flow."""
    if api_key_matches(x_api_key) or settings.DEBUG:
        return
    raise HTTPException(status_code=401, detail="A valid X-API-Key is required")


async def require_room_access(
    room_id: str,
    token: str = Query(default=""),
    x_api_key: str | None = Header(default=None),
) -> None:
    """A room document is readable by the backend or by a seated player."""
    if api_key_matches(x_api_key):
        return
    if not token and settings.DEBUG:
        return

    from app.services import room_service as RoomService

    try:
        player_id = verify_player_token(token, room_id=room_id)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail="A valid token is required") from exc

    room = await RoomService.get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    if RoomService.seat_of(room, player_id) is None:
        raise HTTPException(status_code=403, detail="Player is not seated in this room")


async def reject_websocket(websocket: WebSocket, message: str) -> None:
    """Tell the client why it was rejected, then close with policy violation."""
    await websocket.accept()
    await websocket.send_json({"type": "error", "message": message})
    await websocket.close(code=1008)


async def resolve_websocket_player(
    websocket: WebSocket,
    *,
    room_id: str | None,
    token: str,
    player_id: str,
) -> str | None:
    """
    Return the authenticated player id of a socket, or ``None`` after the
    connection has been rejected.

    The token always wins over query input; the query id only seeds the DEBUG
    dev flow.
    """
    try:
        if token:
            resolved = verify_player_token(token, room_id=room_id)
            if not is_valid_player_id(resolved):
                raise AuthError("invalid player id")
            return resolved
        if settings.DEBUG and player_id:
            if not is_valid_player_id(player_id):
                raise AuthError("invalid player id")
            return player_id
        raise AuthError("a token is required")
    except AuthError as exc:
        await reject_websocket(websocket, f"Authentication failed: {exc}")
        return None
