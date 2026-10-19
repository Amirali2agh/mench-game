import asyncio
from asyncio import sleep as async_sleep
from fastapi import WebSocket

class RoomManager:
    """
    Manages active in-memory WebSocket connections for game rooms
    and handles player disconnection timeouts (60-second forfeit rule).
    """
    def __init__(self):
        # Maps room_id -> {player_id: WebSocket}
        self.rooms: dict[str, dict[str, WebSocket]] = {}
        # Maps room_id -> {player_id: asyncio.Task} to track active forfeit timers
        self.disconnect_tasks: dict[str, dict[str, asyncio.Task]] = {}

    async def connect(self, room_id: str, player_id: str, websocket: WebSocket) -> None:
        """
        Registers a player's WebSocket connection within a specific room.
        Cancels any active forfeit timer for this player if they are reconnecting.
        """
        await websocket.accept()
        
        if room_id not in self.rooms:
            self.rooms[room_id] = {}
        self.rooms[room_id][player_id] = websocket

        # Reconnection check: Cancel the active 60-second forfeit timer if it exists
        self._cancel_disconnect_task(room_id, player_id)

    def disconnect(self, room_id: str, player_id: str, websocket: WebSocket | None = None) -> None:
        """
        Removes a player's WebSocket connection from the active room dictionary.
        Does NOT end the game; the 60-second forfeit timer must be started separately.
        """
        if (
            room_id in self.rooms
            and player_id in self.rooms[room_id]
            and (websocket is None or self.rooms[room_id][player_id] is websocket)
        ):
            del self.rooms[room_id][player_id]
            if not self.rooms[room_id]:
                del self.rooms[room_id]

    def start_disconnect_timer(self, room_id: str, player_id: str, forfeit_callback) -> None:
        """
        Spawns a background task that waits for 60 seconds.
        If the player does not reconnect within this period, the forfeit callback is executed.
        """
        if room_id not in self.disconnect_tasks:
            self.disconnect_tasks[room_id] = {}
        
        # Prevent duplicate forfeit tasks for the same player in this room
        self._cancel_disconnect_task(room_id, player_id)

        # Schedule the asynchronous forfeit timer task
        task = asyncio.create_task(self._forfeit_timer(room_id, player_id, forfeit_callback))
        self.disconnect_tasks.setdefault(room_id, {})[player_id] = task

    async def broadcast(self, room_id: str, message: dict) -> None:
        """
        Sends a JSON payload to all currently connected players in a room.
        """
        if room_id in self.rooms:
            targets = list(self.rooms[room_id].values())
            for ws in targets:
                try:
                    await ws.send_json(message)
                except Exception:
                    # Silently handle disconnected sockets during broadcast
                    pass

    def cancel_disconnect_timers(self, room_id: str) -> None:
        """
        Cancels every pending forfeit timer of a room.

        A rematch starts a fresh match, so a timer armed during the previous one
        must not knock a player out of the new game.
        """
        for player_id in list(self.disconnect_tasks.get(room_id, {})):
            self._cancel_disconnect_task(room_id, player_id)

    def _cancel_disconnect_task(self, room_id: str, player_id: str) -> None:
        """
        Cancels and cleans up an active forfeit task.
        """
        if room_id in self.disconnect_tasks and player_id in self.disconnect_tasks[room_id]:
            task = self.disconnect_tasks[room_id][player_id]
            task.cancel()
            del self.disconnect_tasks[room_id][player_id]
            if not self.disconnect_tasks[room_id]:
                del self.disconnect_tasks[room_id]

    async def _forfeit_timer(self, room_id: str, player_id: str, forfeit_callback) -> None:
        """
        Asynchronous sleep timer that runs the forfeit callback after 60 seconds
        unless canceled due to reconnection.
        """
        try:
            await async_sleep(60)  # Wait for 60 seconds using the locally bound async_sleep
            # Timer completed! Execute forfeit callback to handle game closure
            await forfeit_callback(room_id, player_id)
        except asyncio.CancelledError:
            # Task was canceled because player reconnected successfully
            pass
        finally:
            # Cleanup the reference to the completed/canceled task
            if room_id in self.disconnect_tasks and player_id in self.disconnect_tasks[room_id]:
                del self.disconnect_tasks[room_id][player_id]

# Global single instance of RoomManager
room_manager = RoomManager()
