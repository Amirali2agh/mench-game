"""A per-room mutation lock shared by every reader-modifier-writer path.

Game state is a single Redis blob that each action reads, mutates and writes
back. Without serialization two overlapping actions (double roll, double move, a
move racing the forfeit timer, two players registering at once) both read the
same snapshot and the last write wins, silently losing the other action.

The lock is a short-lived Redis lease (``SET key token NX PX ttl``) so it works
across workers, and the release is token-checked so a slow action can never
delete a lock that has already been re-acquired by someone else.
"""

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from app.redis_client import redis_client
from app.utils.redis_keys import RedisKeys

logger = logging.getLogger(__name__)

#: How long a lock survives if its holder dies before releasing it.
LOCK_TTL_MS = 5000

#: How long an action waits for a lock before giving up.
LOCK_WAIT_SECONDS = 2.0

#: Poll interval while waiting for a busy lock.
LOCK_RETRY_INTERVAL = 0.01

_RELEASE_LOCK_SCRIPT = """
-- mensch:release-lock:v1
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""


class RoomLockTimeout(ValueError):
    """Raised when another action holds the room lock for too long.

    It derives from ``ValueError`` so the WebSocket handler reports it to the
    client as a normal action error instead of a generic internal failure.
    """


@asynccontextmanager
async def room_lock(
    room_id: str,
    *,
    ttl_ms: int = LOCK_TTL_MS,
    wait_seconds: float = LOCK_WAIT_SECONDS,
):
    """Hold the mutation lock of ``room_id`` for the duration of the block."""
    key = RedisKeys.room_lock(room_id)
    token = uuid.uuid4().hex
    loop = asyncio.get_running_loop()
    deadline = loop.time() + wait_seconds

    while True:
        if await redis_client.set(key, token, nx=True, px=ttl_ms):
            break
        if loop.time() >= deadline:
            raise RoomLockTimeout("The room is busy, try again in a moment")
        await asyncio.sleep(LOCK_RETRY_INTERVAL)

    try:
        yield
    finally:
        try:
            await redis_client.eval(_RELEASE_LOCK_SCRIPT, 1, key, token)
        except Exception as exc:  # pragma: no cover - Redis failure path
            # Never mask the action's own exception: the lease expires anyway.
            logger.warning("Could not release room lock %s: %s", key, exc)
