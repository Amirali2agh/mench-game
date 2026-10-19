# Mensch Game - Backend Integration & Architecture Guide

This document defines the WebSocket communication protocols, query parameters, events, and data schemas required for the Frontend developer to integrate the React + TypeScript application with this FastAPI + Redis backend.

---

## 1. Running the Backend Service

To run the backend and its Redis database locally using Docker, execute this command in the project root:
```bash
docker compose up --build

API Base URL: http://localhost:8000
WS Base URL: ws://localhost:8000
Health Check Endpoint: http://localhost:8000/health (Returns database connection health status).


2. Matchmaking Queue Connection (/ws/queue)

o enter the matchmaking queue, connect to the following WebSocket endpoint.
WebSocket URL:
ws://localhost:8000/ws/queue

Connection Query Parameters:
Param	Type	Required	Default	Purpose
playerId	string	Yes	-	Unique identifier of the current player.
playerName	string	Yes	-	Display name of the player (supports Persian characters).
playerAvatarUrl	string	No	""	URL to the player's profile avatar.
playerCount	int	No	2	Matchmaking queue capacity. Accepts 2 or 4 players.
piecesCount	int	No	4	Number of Mensch pieces to play with. Accepts 2, 3, or 4.
Match Found Event (Broadcasted by Server):
When the queue reaches the required capacity (based on playerCount and piecesCount), the server automatically groups the players, maps them to a newly created room, and broadcasts this payload to all matched players:
code
JSON
{
  "type": "match_found",
  "room_id": "a9b8c7d6-e5f4-3210-9876-543210fedcba",
  "players": [
    {
      "id": "p1",
      "name": "علی",
      "avatar": "https://example.com/avatar1.png"
    },
    {
      "id": "p2",
      "name": "رضا",
      "avatar": "https://example.com/avatar2.png"
    }
  ],
  "pieces_count": 4
}
`match_found` is delivered to every matched player and always carries
`pieces_count`; treat the field as required. Delivery goes through a per-player
Redis inbox (`queue:notify:{player_id}`), so a player may be connected to a
different worker than the one that completed the match.

Queue Timeout Event:
When no match is found within MATCHMAKING_TIMEOUT seconds, the player is removed
from the queue and receives:

{
  "type": "queue_timeout",
  "player_id": "p1"
}

The client should return to the lobby and may join the queue again.

Action Required by Frontend: Upon receiving this message, the frontend must immediately close the queue WebSocket connection and redirect the user to the active game room WebSocket.
3. Game Room Connection (/ws/room/{room_id})
To play the active game, connect to the room WebSocket endpoint.
WebSocket URL:
ws://localhost:8000/ws/room/{room_id}
Connection Query Parameters:
Param	Type	Required	Purpose
playerId	string	Yes	Unique identifier of the current player.
playerName	string	Yes	Display name of the player.
Initial Connection Sync:
As soon as any player connects, the server broadcasts the current active game board state to all connected clients inside the room:
code
JSON
{
  "type": "sync_state",
  "game": {
    "room_id": "test-room-uuid",
    "player_count": 2,
    "pieces_count": 4,
    "players": [
      {"id": "p1", "name": "علی", "avatar": "https://..."},
      {"id": "p2", "name": "رضا", "avatar": "https://..."}
    ],
    "current_turn": 0,
    "dice": null,
    "dice_rolled": false,
    "last_roll": null,
    "coin_bet": 0,
    "track_offsets": [20, 0],
    "pieces": {
      "p1": [-1, -1, -1, -1],
      "p2": [-1, -1, -1, -1]
    },
    "status": "playing",
    "winner_id": null
  }
}
`dice` is null whenever the active player has not rolled yet, including right
after a turn change: the previous player's roll is never carried into the next
turn. The last roll is still available as `last_roll` so clients can replay the
dice animation and history.

`track_offsets` maps each seat (index in `players`) to its absolute starting cell
on the circular track (section 5). Clients must use this array instead of
hard-coding offsets: it differs between 2-player and 4-player matches.
4. Gameplay Actions (Client to Server)
The client sends these stringified JSON actions to execute moves:
4.1 Roll Dice
To roll the dice on your turn:
code
JSON
{
  "action": "roll_dice"
}
4.2 Move Piece
To move a specific piece after rolling the dice. piece_index represents the index of the piece (from 0 to pieces_count - 1):
code
JSON
{
  "action": "move_piece",
  "piece_index": 0
}
4.3 Next Match (Rematch)
To start a new match on the same board with the same roster and the same settings
(pieces_count, player_count, coin_bet):
code
JSON
{
  "action": "next_round"
}
`restart_game` is accepted as an alias of the same action so older clients keep
working; new clients should send `next_round`.
The server only accepts a rematch when the room has a finished game and the
sender is seated in that room. Anything else answers with an
{"type": "error", ...} message and leaves the running match untouched. A rematch
also clears pending disconnect timers and the "winner already reported" guard, so
the new match reports its own winner.
4.4 Pass Turn
The turn timer sends `pass_turn` when the active player runs out of time:
code
JSON
{
  "action": "pass_turn"
}
Only the active player may pass, and only while no legal move is available (the
engine also passes a blocked player automatically). Passing while a move is still
possible is rejected with {"type": "error", "message": "You still have a legal
move"}.
5. Board Grid Mapping & Movement Specs
To map the relative coordinates sent by the server to the physical visual board:
Starting Base/Yard: -1 (Requires rolling a 6 to move to position 0).
Main circular Track: Positions 0 to 39 (Total 40 spaces shared by all players).
Home Column: Private path represented by positions 40, 41, 42, and 43.
Destination Goal State: A piece has finished when its relative position is
between 40 and 43. A player wins as soon as all of their pieces are there;
position 44 is never used.
Starting Absolute Offsets on the Circular Grid (one fixed offset per corner):
corner 0 = red, bottom-left = 20; corner 1 = blue, top-left = 30;
corner 2 = green, top-right = 0; corner 3 = yellow, bottom-right = 10.
For 2 Players: seat 0 uses corner 0 (index 20) and seat 1 uses corner 2 (index 0),
so the two players start exactly 20 cells apart on facing corners.
For 4 Players: seat 0 = index 20, seat 1 = index 30, seat 2 = index 0, seat 3 = index 10.
The resolved per-seat values are always sent as `track_offsets` in `sync_state`,
so clients never re-implement this table.
6. Disconnect Forfeit System (The 60-Second Rule)
If any player disconnects (due to network failure, app closing, etc.), the server arms an asynchronous 60-second forfeit timer for that player.
Reconnection: If the player connects back to ws://localhost:8000/ws/room/{room_id} before the 60 seconds expire, the forfeit timer is canceled, and they resume playing.
Forfeit Trigger: When the timer expires the disconnected player is eliminated:
- Two players: the match ends at once, status becomes "finished" and the remaining player is the winner_id.
- Three or four players: the match keeps playing, the eliminated player is skipped by the turn rotation, and the game ends only when a single player is left.
The resulting sync_state is broadcast to the room. The prize report happens exactly once per match: the first reporter claims room:{room_id}:winner_reported in Redis, and any later call (duplicate timer, reconnect) is a no-op.
code
Code
---


7. Room Start Rules and Timeout
A room starts a match only when its configured roster is complete: `player_count`
is either 2 or 4, and the game state is created once that many players have been
seated through POST /api/rooms/{room_id}/join or by connecting to the room
WebSocket. While players are still missing, every connected client receives:

{
  "type": "waiting_for_players",
  "room_id": "abc123",
  "joined": 2,
  "required": 4,
  "players": [{"id": "p1", "name": "علی", "avatar": ""}]
}

If the roster is still incomplete after MATCHMAKING_TIMEOUT seconds, the room is
cancelled: clients receive {"type": "room_timeout", "room_id": "abc123",
"joined": 2, "required": 4} and the room status becomes "cancelled". A 4-player
room with two players therefore never starts a two-player match on a four-seat
board.


Room REST Payload Rules
POST /api/rooms accepts:
- player_count: 2 or 4
- pieces_count: 2, 3 or 4
- coin_bet: integer >= 0
- player1_id (required) and player2_id (optional): [A-Za-z0-9_.-]{1,64}
- room_id (optional): [A-Za-z0-9_-]{1,64}; generated when omitted
Anything else is rejected with 422. POST /api/rooms/{room_id}/join requires a
player_id with the same format and only succeeds while the room is still waiting
for players. The room document (room:{room_id}:meta) is the single source of
truth for player_count, pieces_count and coin_bet; no side keys are written.
