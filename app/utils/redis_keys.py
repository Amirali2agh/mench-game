class RedisKeys:
    """
    Utility class to generate standardized and typo-safe Redis keys
    used across the matchmaking, player tracking, and game state management.
    """

    @staticmethod
    def matchmaking_queue(player_count: int, pieces_count: int) -> str:
        """
        Returns the key for the matchmaking queue based on player count and pieces count.
        Example output: "matchmaking:queue:4p:3pieces"
        """
        return f"matchmaking:queue:{player_count}p:{pieces_count}pieces"

    @staticmethod
    def room_state(room_id: str) -> str:
        """
        Returns the key for the active game room state (JSON or Hash).
        """
        return f"room:{room_id}:state"

    @staticmethod
    def room_players(room_id: str) -> str:
        """
        Returns the key for the set of player IDs currently inside a room.
        """
        return f"room:{room_id}:players"

    @staticmethod
    def player_room(player_id: str) -> str:
        """
        Returns the key mapping a player ID to their current room ID.
        Useful to reconnect a player to their active game.
        """
        return f"player:{player_id}:room"

    @staticmethod
    def room_lock(room_id: str) -> str:
        """
        Returns the key of the short-lived mutation lease of a room.

        Every read-modify-write of the room document or the game state runs
        while holding this lock, so concurrent actions cannot lose updates.
        """
        return f"room:{room_id}:lock"

    @staticmethod
    def player_queue(player_id: str) -> str:
        """
        Returns the key remembering which matchmaking queue a player joined.

        It lets a player who changes player/piece counts leave the previous
        queue atomically instead of being matchable from two queues at once.
        """
        return f"player:{player_id}:queue"

    @staticmethod
    def queue_notifications(player_id: str) -> str:
        """
        Returns the per-player match inbox written by the matchmaking queue.
        Example output: "queue:notify:12345"
        """
        return f"queue:notify:{player_id}"

    @staticmethod
    def player_disconnect(player_id: str) -> str:
        """
        Returns the key storing the timestamp when a player disconnected.
        Used to enforce the 60-second forfeit/disconnect timeout.
        """
        return f"player:{player_id}:disconnect_time"