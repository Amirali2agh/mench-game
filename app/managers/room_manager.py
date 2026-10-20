import asyncio
import logging

logger = logging.getLogger(__name__)

from asyncio import sleep as async_sleep
from fastapi import WebSocket

from app.config import settings

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

        A reconnect replaces the previous socket and closes it, so the orphaned
        connection stops receiving (and failing) broadcasts. Any active forfeit
        timer for this player is cancelled.
        """
        await websocket.accept()

        self.rooms.setdefault(room_id, {})
        previous = self.rooms[room_id].get(player_id)
        if previous is not None and previous is not websocket:
            try:
                await previous.close(code=1000)
            except Exception:
                logger.warning(
                    "Could not close the previous socket of %s/%s",
                    room_id,
                    player_id,
                    exc_info=True,
                )
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

    def is_connected(self, room_id: str, player_id: str) -> bool:
        """True while ``player_id`` has a live socket in the room."""
        return player_id in self.rooms.get(room_id, {})

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

    async def broadcast(self, room_id: str, message: dict) -> list[str]:
        """
        Sends a JSON payload to every connected player of a room.

        Sends run concurrently, so one slow socket cannot delay the others. A
        failed send is logged and the socket is dropped from the registry; the
        returned player ids are the ones the caller should start the disconnect
        flow for.
        """
        targets = list(self.rooms.get(room_id, {}).items())
        if not targets:
            return []

        results = await asyncio.gather(
            *(websocket.send_json(message) for _, websocket in targets),
            return_exceptions=True,
        )

        failed: list[str] = []
        for (player_id, websocket), result in zip(targets, results):
            if not isinstance(result, BaseException):
                continue
            logger.warning(
                "Broadcast to %s/%s failed: %r", room_id, player_id, result
            )
            self.disconnect(room_id, player_id, websocket)
            failed.append(player_id)
        return failed

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
        Asynchronous sleep timer that runs the forfeit callback after
        ``settings.DISCONNECT_TIMEOUT`` seconds unless canceled due to reconnection.
        """
        try:
            await async_sleep(settings.DISCONNECT_TIMEOUT)  # Configured forfeit window
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
