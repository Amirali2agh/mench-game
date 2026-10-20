import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)

class QueueManager:
    """
    Manages active in-memory WebSocket connections for players 
    who are currently waiting in the matchmaking queue.
    """
    def __init__(self):
        # Maps player_id (str) to their corresponding active WebSocket connection
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, player_id: str, websocket: WebSocket) -> None:
        """
        Accepts a WebSocket connection and registers it under the player's ID.
        """
        await websocket.accept()
        self.active_connections[player_id] = websocket

    def disconnect(self, player_id: str) -> None:
        """
        Unregisters a player's WebSocket connection from the active pool.
        """
        if player_id in self.active_connections:
            del self.active_connections[player_id]

    async def send_match_found(
        self,
        player_id: str,
        room_id: str,
        players: list[dict],
        pieces_count: int,
    ) -> None:
        """
        Sends a direct notification to a specific player informing them 
        that a match has been found, providing the target room_id, the matched
        players and the piece count the room was created with.
        """
        websocket = self.active_connections.get(player_id)
        if websocket:
            payload = {
                "type": "match_found",
                "room_id": room_id,
                "players": players,
                "pieces_count": pieces_count,
            }
            try:
                await websocket.send_json(payload)
            except Exception:
                # The socket is gone; drop it so a later match does not keep
                # retrying a dead connection.
                logger.warning(
                    "Match notification to %s failed", player_id, exc_info=True
                )
                self.disconnect(player_id)

# Global single instance of QueueManager to be imported and used across routers/services
queue_manager = QueueManager()