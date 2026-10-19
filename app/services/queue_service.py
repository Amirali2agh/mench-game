import json
import uuid
from app.redis_client import redis_client
from app.utils.redis_keys import RedisKeys

class QueueService:
    """
    Service to handle matchmaking queue operations using Redis.
    Supports dynamic matchmaking based on both player count and piece count.
    """

    @staticmethod
    async def add_to_queue(player_id: str, player_name: str, avatar_url: str, target_players: int, pieces_count: int) -> dict | None:
        """
        Adds a player to the matchmaking queue and metadata store.
        If enough players are present, creates a room and returns the room details.
        """
        player_meta_key = f"player:{player_id}:meta"
        meta_data = {
            "id": player_id,
            "name": player_name,
            "avatar": avatar_url
        }
        await redis_client.set(player_meta_key, json.dumps(meta_data), ex=3600)

        queue_key = RedisKeys.matchmaking_queue(target_players, pieces_count)
        queue_players = await redis_client.lrange(queue_key, 0, -1)
        if player_id not in queue_players:
            await redis_client.rpush(queue_key, player_id)

        queue_length = await redis_client.llen(queue_key)
        if queue_length >= target_players:
            matched_ids = []
            for _ in range(target_players):
                pid = await redis_client.lpop(queue_key)
                if pid:
                    matched_ids.append(pid)

            if len(matched_ids) == target_players:
                room_id = str(uuid.uuid4())
                players_with_meta = []

                players_meta = {}
                for index, pid in enumerate(matched_ids, start=1):
                    await redis_client.set(RedisKeys.player_room(pid), room_id, ex=7200)
                    p_meta = await redis_client.get(f"player:{pid}:meta")
                    player_meta = json.loads(p_meta) if p_meta else {"id": pid, "name": f"Player {pid}", "avatar": ""}
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
                    }),
                    ex=7200,
                )

                # Every matched player gets a notification: they may be
                # connected to a different worker than the one that completed
                # the match, so the WebSocket watcher reads it from here.
                for matched_id in matched_ids:
                    notification_key = RedisKeys.queue_notifications(matched_id)
                    await redis_client.rpush(
                        notification_key,
                        json.dumps({
                            "room_id": room_id,
                            "pieces_count": pieces_count,
                        }),
                    )
                    await redis_client.expire(notification_key, 300)

                return {
                    "room_id": room_id,
                    "players": players_with_meta,
                    "pieces_count": pieces_count
                }

            for pid in matched_ids:
                await redis_client.lpush(queue_key, pid)

        return None

    @staticmethod
    async def remove_from_queue(player_id: str, target_players: int, pieces_count: int) -> None:
        """
        Removes a player from the queue when they disconnect or cancel.
        """
        queue_key = RedisKeys.matchmaking_queue(target_players, pieces_count)
        await redis_client.lrem(queue_key, 0, player_id)
