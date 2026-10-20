"""Limits applied to untrusted client input.

One socket can otherwise flood actions, send megabyte frames or chat under
another player's name; these helpers keep every such path bounded.
"""

import re
import time

#: Largest accepted WebSocket text frame, in UTF-8 bytes.
MAX_FRAME_BYTES = 4096

#: Chat message length in characters, applied after sanitising.
MAX_CHAT_CHARS = 200

#: Display-name length in characters.
MAX_PLAYER_NAME_CHARS = 64

#: Token-bucket budget shared by every action a socket may send.
ACTIONS_PER_SECOND = 10.0
ACTION_BURST = 10.0

#: Control characters (including newlines) never belong in names or chat.
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class TokenBucket:
    """Per-connection action budget; create one instance per socket."""

    def __init__(
        self,
        rate: float = ACTIONS_PER_SECOND,
        capacity: float = ACTION_BURST,
        *,
        now: float | None = None,
    ) -> None:
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.updated = time.monotonic() if now is None else now

    def consume(self, amount: float = 1.0, *, now: float | None = None) -> bool:
        """Spend ``amount`` tokens, returning False when the budget is spent."""
        moment = time.monotonic() if now is None else now
        self.tokens = min(
            self.capacity, self.tokens + max(0.0, moment - self.updated) * self.rate
        )
        self.updated = moment
        if self.tokens < amount:
            return False
        self.tokens -= amount
        return True


def sanitize_text(value: object, limit: int) -> str:
    """Strip control characters, trim, and truncate to ``limit`` characters."""
    if not isinstance(value, str):
        return ""
    return _CONTROL_CHARS.sub("", value).strip()[:limit]
