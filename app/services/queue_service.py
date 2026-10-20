import json
import uuid

from app.redis_client import redis_client
from app.services import room_service as RoomService
from app.utils.redis_keys import RedisKeys

#: How long a queue entry and its player marker stay valid.
QUEUE_ENTRY_TTL = 3600

#: How long a matched room and its per-player mapping stay readable.
ROOM_TTL = 7200

#: How long an undelivered match notification is kept.
NOTIFICATION_TTL = 300

#: Atomic enqueue + claim.
#:
#: The previous implementation read the list, pushed, read the length and then
#: popped one id at a time, all in separate round trips: two workers could both
#: see a full queue and pop a partial roster, and its ``lpush`` rollback reversed
#: the remaining order. This script does every step in one Redis round trip, so
#: exactly one caller can claim a given set of players.
#:
#: KEYS[1] queue key
#: KEYS[2] marker key of this player (which queue they currently sit in)
#: ARGV[1] player id
#: ARGV[2] target player count
#: ARGV[3] marker TTL in seconds
_CLAIM_QUEUE_SCRIPT = """
-- mensch:claim-queue:v1
local queue_key = KEYS[1]
local marker_key = KEYS[2]
local player_id = ARGV[1]
local target_players = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])

-- Leaving a different queue first: a player who changes settings must never
-- be matchable from the old queue.
local previous_queue = redis.call('GET', marker_key)
if previous_queue and previous_queue ~= queue_key then
    redis.call('LREM', previous_queue, 0, player_id)
end

-- De-duplicate within this queue and enqueue at the tail.
redis.call('LREM', queue_key, 0, player_id)
redis.call('RPUSH', queue_key, player_id)
redis.call('SET', marker_key, queue_key, 'EX', ttl)

if redis.call('LLEN', queue_key) < target_players then
    return {}
end

local claimed = redis.call('LRANGE', queue_key, 0, target_players - 1)
if #claimed < target_players then
    return {}
end

redis.call('LTRIM', queue_key, target_players, -1)

for _, claimed_id in ipairs(claimed) do
    local claimed_marker = 'player:' .. claimed_id .. ':queue'
    if redis.call('GET', claimed_marker) == queue_key then
        redis.call('DEL', claimed_marker)
    end
end

return claimed
"""


class QueueService:
    """
    Service to handle matchmaking queue operations using Redis.
    Supports dynamic matchmaking based on both player count and piece count.
    """

    @staticmethod
    async def add_to_queue(
        player_id: str,
        player_name: str,
        avatar_url: str,
        target_players: int,
        pieces_count: int,
    ) -> dict | None:
        """
        Adds a player to the matchmaking queue and metadata store.
        If the queue is full, atomically claims the players and creates a room.
        """
        player_meta_key = f"player:{player_id}:meta"
        meta_data = {
            "id": player_id,
            "name": player_name,
            "avatar": avatar_url,
        }
        await redis_client.set(player_meta_key, json.dumps(meta_data), ex=QUEUE_ENTRY_TTL)

        queue_key = RedisKeys.matchmaking_queue(target_players, pieces_count)
        claimed = await redis_client.eval(
            _CLAIM_QUEUE_SCRIPT,
            2,
            queue_key,
            RedisKeys.player_queue(player_id),
            player_id,
            target_players,
            QUEUE_ENTRY_TTL,
        )
        matched_ids = [
            pid.decode() if isinstance(pid, bytes) else str(pid) for pid in (claimed or [])
        ]

        if not matched_ids:
            return None

        if len(matched_ids) != target_players:
            # Defensive: a conforming script only claims a full roster. If a
            # partial claim ever reaches here, return the players to the tail in
            # their original order instead of dropping or reversing them.
            for pid in matched_ids:
                await QueueService._return_to_queue(queue_key, pid)
            return None

        try:
            return await QueueService._commit_match(
                matched_ids, target_players, pieces_count
            )
        except Exception:
            # A failed room creation must leave the queue usable. Appending the
            # claimed players keeps their relative order; ``lpush`` would have
            # reversed it.
            for pid in matched_ids:
                await QueueService._return_to_queue(queue_key, pid)
            raise

    @staticmethod
    async def _return_to_queue(queue_key: str, player_id: str) -> None:
        """Return an uncommitted player to the tail of their queue.

        ``player:{id}:room`` may already point at a room that was never
        persisted, so it is cleared first. Appending keeps the queue order;
        ``lpush`` is what used to reverse it.
        """
        await redis_client.delete(RedisKeys.player_room(player_id))
        await redis_client.rpush(queue_key, player_id)

    @staticmethod
    async def _commit_match(
        matched_ids: list[str],
        target_players: int,
        pieces_count: int,
    ) -> dict:
        """Persist the room of an already claimed roster and notify everyone."""
        room_id = str(uuid.uuid4())
        players_with_meta: list[dict] = []
        players_meta: dict[str, dict] = {}

        for index, pid in enumerate(matched_ids, start=1):
            await redis_client.set(RedisKeys.player_room(pid), room_id, ex=ROOM_TTL)
            p_meta = await redis_client.get(f"player:{pid}:meta")
            player_meta = (
                json.loads(p_meta)
                if p_meta
                else {"id": pid, "name": f"Player {pid}", "avatar": ""}
            )
            players_with_meta.append(player_meta)
            players_meta[str(index)] = player_meta

        await redis_client.set(
            f"room:{room_id}:meta",
            json.dumps({
                "room_id": room_id,
                "players": [p["id"] for p in players_with_meta],
                "players_meta": players_meta,
                "player_count": target_players,
                "pieces_count": pieces_count,
                "status": "playing",
                "coin_bet": 0,
                # A matched room keeps the short queue wait window, unlike a
                # room opened from a link (issue #60).
                "source": RoomService.ROOM_SOURCE_MATCHMAKING,
            }),
            ex=ROOM_TTL,
        )

        # Every matched player gets a notification: they may be connected to a
        # different worker than the one that completed the match, so the
        # WebSocket watcher reads it from here.
        for matched_id in matched_ids:
            notification_key = RedisKeys.queue_notifications(matched_id)
            await redis_client.rpush(
                notification_key,
                json.dumps({
                    "room_id": room_id,
                    "pieces_count": pieces_count,
                }),
            )
            await redis_client.expire(notification_key, NOTIFICATION_TTL)

        return {
            "room_id": room_id,
            "players": players_with_meta,
            "pieces_count": pieces_count,
        }

    @staticmethod
    async def remove_from_queue(
        player_id: str, target_players: int, pieces_count: int
    ) -> None:
        """
        Removes a player from the queue when they disconnect or cancel.
        """
        queue_key = RedisKeys.matchmaking_queue(target_players, pieces_count)
        await redis_client.lrem(queue_key, 0, player_id)

        marker_key = RedisKeys.player_queue(player_id)
        if await redis_client.get(marker_key) == queue_key:
            await redis_client.delete(marker_key)
