"""Signed player tokens.

Nothing the client says about its identity is trusted: Porteghal (or a
deployment's own backend) mints a short-lived token signed with a shared
secret and passes it to the WebView, and the server derives the player id from
that token. Tokens are deliberately stateless — an HMAC over a small JSON
payload — so no extra Redis key has to be kept alive per connection.
"""

import base64
import hashlib
import hmac
import json
import time

from app.config import settings
from app.utils.identifiers import is_valid_player_id

#: Lifetime of a token in seconds. Long enough for a match plus reconnects.
TOKEN_TTL_SECONDS = 3600

#: Used only when DEBUG is on and no secret is configured, so the dev flow
#: stays usable. Production refuses to mint or verify tokens without a secret.
_DEBUG_SECRET = b"mensch-debug-only-token-secret"


class AuthError(ValueError):
    """Raised when a token is missing, malformed, expired or forged."""


def _secret() -> bytes:
    secret = settings.GAME_TOKEN_SECRET or settings.PORTEGHAL_API_KEY
    if secret:
        return secret.encode("utf-8")
    if settings.DEBUG:
        return _DEBUG_SECRET
    raise AuthError("GAME_TOKEN_SECRET is not configured")


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _sign(body: str) -> bytes:
    return hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest()


def issue_player_token(
    player_id: str,
    room_id: str | None = None,
    *,
    ttl: int = TOKEN_TTL_SECONDS,
    now: float | None = None,
) -> str:
    """Mint a token binding ``player_id`` (and optionally a room) for ``ttl``."""
    if not is_valid_player_id(player_id):
        raise AuthError("invalid player id")
    issued_at = time.time() if now is None else now
    payload: dict[str, object] = {"sub": player_id, "exp": int(issued_at + ttl)}
    if room_id:
        payload["room"] = room_id
    body = _encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    return f"{body}.{_encode(_sign(body))}"


def verify_player_token(
    token: str | None,
    *,
    room_id: str | None = None,
    now: float | None = None,
) -> str:
    """
    Return the player id carried by ``token``.

    ``room_id`` binds the token to a room: a room token is only accepted for
    that room, and a room token is rejected where no room is expected (the
    matchmaking queue), so a token cannot be replayed across surfaces.
    """
    if not token:
        raise AuthError("missing token")

    try:
        body, signature = token.split(".", 1)
        provided = _decode(signature)
    except (ValueError, TypeError) as exc:
        raise AuthError("malformed token") from exc

    if not hmac.compare_digest(provided, _sign(body)):
        raise AuthError("invalid token signature")

    try:
        payload = json.loads(_decode(body))
    except (ValueError, TypeError) as exc:
        raise AuthError("malformed token") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("sub"), str):
        raise AuthError("malformed token payload")

    if int(payload.get("exp") or 0) <= (time.time() if now is None else now):
        raise AuthError("token expired")

    token_room = payload.get("room")
    if room_id is not None and token_room != room_id:
        raise AuthError("token does not belong to this room")
    if room_id is None and token_room:
        raise AuthError("token is bound to a room")

    return str(payload["sub"])
