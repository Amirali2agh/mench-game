import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _auth_headers() -> dict[str, str] | None:
    """
    Build the headers for a Porteghal internal API call.

    Returns None when no API key is configured. The key is never defaulted in
    code: a missing key must disable the integration loudly instead of silently
    authenticating with a value committed to the repository.
    """
    if not settings.PORTEGHAL_API_KEY:
        logger.error(
            "PORTEGHAL_API_KEY is not configured; skipping the Porteghal API call. "
            "Set it in the environment before starting the service."
        )
        return None
    return {"Content-Type": "application/json", "X-Api-Key": settings.PORTEGHAL_API_KEY}


async def update_room_status(room_id: str, status: str) -> bool:
    headers = _auth_headers()
    if headers is None:
        return False

    url = f"{settings.PORTEGHAL_API_URL}/api/internal/game-rooms/update"
    payload = {"roomId": room_id, "status": status}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return True
    except httpx.HTTPError as exc:
        logger.warning("Failed to update room %s status: %s", room_id, exc)
        return False


async def report_winner(
    room_id: str,
    player_id: str,
    win_type: str,
    game_id: str = "mench",
    amount: int = 0,
) -> bool:
    headers = _auth_headers()
    if headers is None:
        return False

    url = f"{settings.PORTEGHAL_API_URL}/api/internal/game-winner"
    payload = {
        "player_id": player_id,
        "amount": amount,
        "room_id": room_id,
        "win_type": win_type,
        "game_id": game_id,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return True
    except httpx.HTTPError as exc:
        logger.warning("Failed to report winner for room %s: %s", room_id, exc)
        return False
