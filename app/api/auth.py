"""Token minting endpoint for the trusted backend.

Porteghal has two ways to authenticate the players it sends to the game: sign
the token itself with the shared secret, or call this endpoint with its
``X-API-Key`` and forward the result. Both produce the same token shape.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.rooms import PLAYER_ID_PATTERN, ROOM_ID_PATTERN
from app.api.security import require_api_key
from app.services.auth import TOKEN_TTL_SECONDS, issue_player_token

router = APIRouter(prefix="/api", tags=["auth"])


class TokenRequest(BaseModel):
    """Identity the backend wants a token for."""

    player_id: str = Field(..., pattern=PLAYER_ID_PATTERN)
    room_id: str = Field(default="", pattern=ROOM_ID_PATTERN)


class TokenResponse(BaseModel):
    token: str
    player_id: str
    expires_in: int


@router.post(
    "/auth/token",
    response_model=TokenResponse,
    dependencies=[Depends(require_api_key)],
)
async def create_player_token(req: TokenRequest) -> TokenResponse:
    """Mint the short-lived token the WebView must present on its sockets."""
    token = issue_player_token(req.player_id, req.room_id or None)
    return TokenResponse(
        token=token,
        player_id=req.player_id,
        expires_in=TOKEN_TTL_SECONDS,
    )
