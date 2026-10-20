# Mensch Game — Protocol and Architecture Reference

This document is the contract between the FastAPI + Redis backend in `app/` and
the React + TypeScript client in `front/`. It covers every WebSocket message,
the REST payloads, the board mapping, Redis keys and TTLs, and the error
messages the client can receive.

---

## 1. Running the backend

```bash
docker compose up --build
```

| Endpoint | URL |
| --- | --- |
| REST base | `http://localhost:8000` |
| WebSocket base | `ws://localhost:8000` |
| Health probe | `http://localhost:8000/health` |

`/health` reports Redis connectivity as well as process liveness. For local
(non-Docker) development see `README.md`.

---

## 2. Authentication

No endpoint trusts a client-supplied identity. A trusted backend (Porteghal)
mints a short-lived token for each player; the WebView passes it in the query
string and the server derives `player_id` from it.

```
ws://localhost:8000/ws/room/{room_id}?token={token}
```

Tokens are an HS256-style HMAC over a compact JSON payload
(`{"sub": player_id, "room": room_id?, "exp": unix_seconds}`), encoded as
`base64url(payload).base64url(signature)`:

* The secret is `GAME_TOKEN_SECRET`, falling back to `PORTEGHAL_API_KEY`.
  Without either, production refuses to mint or verify tokens.
* A room token is only accepted for that room; a token minted without a room is
  only accepted by `/ws/queue`. Tokens cannot be replayed across surfaces.
* `TOKEN_TTL_SECONDS` (3600) bounds the validity, so a lost token ages out.

| Surface | Credential |
| --- | --- |
| `POST /api/rooms`, `POST /api/rooms/{room_id}/join`, `POST /api/auth/token` | `X-API-Key` header (the shared secret) |
| `GET /api/rooms/{room_id}` | `X-API-Key`, or `?token=` of a seated player |
| `/ws/room/{room_id}`, `/ws/queue`, `/ws/game/{room_id}/{player_num}` | `?token=` |

`POST /api/rooms` answers with `player_tokens` (one token per seated player)
and `POST /api/rooms/{room_id}/join` answers with `token`, so the backend can
hand both players their credential when it opens the WebView. `POST
/api/auth/token` covers matchmaking, where no room exists yet.

Connections without a valid token are accepted, sent
`{"type": "error", "message": "Authentication failed: …"}` and closed with code
`1008`. A room socket also rejects a player the room document does not seat.

With `DEBUG=true` (local development only) a missing token falls back to the
`playerId` query parameter and rooms auto-seat unknown players.

---

## 3. Matchmaking — `/ws/queue`

```
ws://localhost:8000/ws/queue?token={token}&playerCount=2&piecesCount=4
```

| Param | Type | Required | Default | Purpose |
| --- | --- | --- | --- | --- |
| `token` | string | yes* | – | Signed identity; `player_id` comes from it |
| `playerId` | string | no | – | *DEBUG only:* identity when no token is sent |
| `playerName` | string | yes | – | Display name (Persian supported) |
| `playerAvatarUrl` | string | no | `""` | Avatar URL stored with the profile |
| `playerCount` | int | no | `2` | `2` or `4` seats |
| `piecesCount` | int | no | `4` | `2`, `3` or `4` pieces per player |

The queue key is derived from both counts, so a 2×4 queue never mixes with a
4×2 queue. Joining twice with the same `playerId` is de-duplicated. On disconnect
or timeout the player is removed from that queue.

### 3.1 Match found

When the queue reaches `playerCount`, the server seats the matched players in a
new room and notifies each of them. The player whose connection completed the
match receives the message directly; every other matched player receives it from
their per-player Redis inbox, so workers do not need to share memory.

```json
{
  "type": "match_found",
  "room_id": "a9b8c7d6-e5f4-3210-9876-543210fedcba",
  "players": [
    { "id": "p1", "name": "علی", "avatar": "https://example.com/avatar1.png" },
    { "id": "p2", "name": "رضا", "avatar": "https://example.com/avatar2.png" }
  ],
  "pieces_count": 4
}
```

`pieces_count` is always present: it is the piece count the room was created
with, not the client's requested default.

The client should close the queue socket and open
`/ws/room/{room_id}?token=…` with the token it was given.

### 3.2 Queue timeout

After `MATCHMAKING_TIMEOUT` seconds without a match the player is removed from
the queue and receives:

```json
{ "type": "queue_timeout", "player_id": "p1" }
```

The client returns to the lobby and may rejoin.

---

## 4. Game room — `/ws/room/{room_id}`

```
ws://localhost:8000/ws/room/{room_id}?token={token}
```

| Param | Type | Required | Purpose |
| --- | --- | --- | --- |
| `token` | string | yes* | Signed identity; the player must already be seated in the room |
| `playerId` | string | no | *DEBUG only:* identity when no token is sent |
| `playerName` | string | no | Fallback display name in DEBUG mode |

The display name is resolved from the stored profile (`player:{id}:meta`) when
one exists; the query parameter is only a fallback.

### 4.1 Initial sync

On connect (and after every mutation) the server broadcasts the full state to
everyone in the room:

```json
{
  "type": "sync_state",
  "game": {
    "room_id": "test-room",
    "player_count": 2,
    "pieces_count": 4,
    "players": [
      { "id": "p1", "name": "علی", "avatar": "https://…" },
      { "id": "p2", "name": "رضا", "avatar": "https://…" }
    ],
    "current_turn": 0,
    "dice": null,
    "dice_rolled": false,
    "consecutive_sixes": 0,
    "roll_sequence": 3,
    "last_roll": { "player_id": "p1", "value": 4, "roll_id": 3 },
    "pieces": { "p1": [-1, 0, -1, -1], "p2": [-1, -1, -1, -1] },
    "status": "playing",
    "winner_id": null,
    "eliminated_players": [],
    "coin_bet": 0,
    "track_offsets": [20, 0]
  }
}
```

* `dice` is `null` until the active player rolls and is reset to `null` when the
  turn advances; the previous roll is never carried into the next turn.
* `last_roll` keeps the most recent roll (with `roll_id`) so clients can replay
  the dice animation and history.
* `track_offsets` maps each seat (index in `players`) to its absolute starting
  cell on the circular track. Clients must use it instead of hard-coding
  offsets; it differs between two- and four-player matches.
* `status` is `playing` or `finished`. `winner_id` is set only when finished.
* `eliminated_players` lists seats that forfeited; turn rotation skips them.

### 4.2 Waiting for players

A room only starts a match when its configured roster is complete. Until then
every connected client receives:

```json
{
  "type": "waiting_for_players",
  "room_id": "abc123",
  "joined": 2,
  "required": 4,
  "players": [{ "id": "p1", "name": "علی", "avatar": "" }]
}
```

If the roster is still incomplete after `MATCHMAKING_TIMEOUT` seconds the room
is cancelled and clients receive:

```json
{ "type": "room_timeout", "room_id": "abc123", "joined": 2, "required": 4 }
```

A four-player room with two players therefore never starts a two-player match on
four-seat geometry.

---

## 5. Client actions (client → server)

All actions are JSON text frames. Unknown or malformed payloads receive an
`error` message and the connection stays open.

### 5.1 Roll the dice

```json
{ "action": "roll_dice" }
```

Only the active player may roll, and only once per turn. When the roll leaves
the player with no legal move, the server broadcasts the roll and advances the
turn automatically after a short delay so the client can animate it.

### 5.2 Move a piece

```json
{ "action": "move_piece", "piece_index": 0 }
```

`piece_index` is `0..pieces_count-1`. A move is rejected when the piece cannot
travel the rolled distance, when it would leave the board, or when it would land
on a home cell occupied by the same player's other piece.

### 5.3 Rematch

```json
{ "action": "next_round" }
```

`restart_game` is accepted as an alias so older clients keep working; new clients
send `next_round`. A rematch is only accepted when the previous match is
`finished` and the sender is seated in the room. It reuses the roster and the
room settings (`pieces_count`, `player_count`, `coin_bet`), clears pending
disconnect timers, and releases the one-shot winner-report claim so the new match
reports its own winner.

### 5.4 Pass the turn

```json
{ "action": "pass_turn" }
```

The client runs a 45-second turn timer and sends this when it expires. The server
accepts it only from the active player, and only when that player has no legal
move; otherwise it answers
`{"type": "error", "message": "You still have a legal move"}`.

### 5.5 Chat

```json
{ "action": "chat", "message": "سلام" }
```

The server rebroadcasts it to the room as:

```json
{
  "type": "chat",
  "player_id": "p1",
  "player_name": "علی",
  "message": "سلام"
}
```

---

## 6. Board mapping and movement

Relative coordinates used in `pieces`:

| Range | Meaning |
| --- | --- |
| `-1` | Yard (base); a roll of 6 is required to enter the track |
| `0..39` | Shared circular track (40 cells) |
| `40..43` | Private home column |

A piece has finished when its relative position is between 40 and 43. A player
wins as soon as all of their pieces are there; position 44 is never used.

Absolute track offsets, one per corner:

| Corner | Colour | Yard | Absolute offset |
| --- | --- | --- | --- |
| 0 | red | bottom-left | 20 |
| 1 | blue | top-left | 30 |
| 2 | green | top-right | 0 |
| 3 | yellow | bottom-right | 10 |

* **Two players:** seat 0 uses corner 0 (offset 20), seat 1 uses corner 2
  (offset 0). The two seats start exactly 20 cells apart on facing corners.
* **Four players:** seats use offsets `[20, 30, 0, 10]` in seat order.

A piece's absolute cell is `(track_offsets[seat] + relative_position) % 40`.
The resolved per-seat values are always sent as `track_offsets` in `sync_state`,
so clients never re-implement this table.

### 6.1 Client mapping

`front/src/utils/boardCoordinates.ts` is the single source of truth on the
client. It holds the same corner table plus the 40-cell track, the derived start
cells, home columns, yard corners and home sides per seat. Start cells, home
columns, yards, player panels and the centre goal are all derived from a seat's
track offset, so a two-player match puts the second player on the facing corner
with that corner's own colour (green opposite red).

`npm test` runs `boardCoordinates.test.ts`, which asserts these invariants and
fails if the client table drifts from `app/services/board_layout.py`.

---

## 7. Disconnect, reconnect and forfeit

1. A WebSocket close starts the forfeit timer for that player
   (`DISCONNECT_TIMEOUT`, 60 seconds by default).
2. Reconnecting to the same room with the same `playerId` cancels the timer and
   resumes play; seating is idempotent for an already seated player.
3. When the timer expires, the player is added to `eliminated_players`:
   * two players — the match ends immediately, `status` becomes `finished` and
     the remaining player is `winner_id`;
   * three or four players — the match continues, the eliminated seat is skipped
     by turn rotation, and the last remaining player wins.
4. The resulting `sync_state` is broadcast to the room.

The prize report happens exactly once per match: the first reporter claims
`room:{room_id}:winner_reported` in Redis and later calls (duplicate timer,
reconnect) are no-ops. A rematch removes that claim.

---

## 8. REST payload rules

### 8.1 `POST /api/rooms`

```json
{
  "room_id": "optional-custom-id",
  "player1_id": "p1",
  "player1_name": "علی",
  "player1_avatar": "",
  "player2_id": "p2",
  "player2_name": "رضا",
  "player2_avatar": "",
  "player_count": 2,
  "pieces_count": 4,
  "coin_bet": 0
}
```

* `player_count`: `2` or `4`.
* `pieces_count`: `2`, `3` or `4`.
* `coin_bet`: integer `>= 0`.
* `player1_id` (required), `player2_id` (optional): `[A-Za-z0-9_.-]{1,64}`.
* `room_id` (optional): `[A-Za-z0-9_-]{1,64}`; generated when omitted.

Anything else is rejected with `422`. The game starts immediately when the
roster is already complete (for example when both players are supplied).

Requires `X-API-Key`. The response adds `player_tokens`: a signed token per
seated player, which the WebView must present on its sockets.

### 8.2 `GET /api/rooms/{room_id}`

Returns the room document (`room_id`, both player profiles, `status`,
`coin_bet`), or `404`. Requires `X-API-Key`, or a `?token=` belonging to a
player seated in the room (`403` otherwise).

### 8.3 `POST /api/rooms/{room_id}/join`

```json
{ "player_id": "p2", "player_name": "رضا", "player_avatar": "" }
```

Seats the player in the first free slot and starts the match when the roster
becomes complete. Rejoining a seat the player already owns is an idempotent
no-op. Requires `X-API-Key`; the response carries the player's `token`.
`404` when the room is unknown, `400` when it is full or no longer
accepting players, and `422` for an invalid `player_id`.

### 8.4 `POST /api/auth/token`

```json
{ "player_id": "p1", "room_id": "" }
```

Mints a token for a player that has no room yet (matchmaking). Answers
`{"token": "…", "player_id": "p1", "expires_in": 3600}`; requires `X-API-Key`.
Omit `room_id` for queue tokens — a room-bound token is rejected by
`/ws/queue`.

The room document (`room:{room_id}:meta`) is the single source of truth for
`player_count`, `pieces_count` and `coin_bet`; no side keys are written.

---

## 9. Redis keys and TTLs

| Key | Type | Written by | TTL |
| --- | --- | --- | --- |
| `matchmaking:queue:{n}p:{m}pieces` | list of player ids | matchmaking | none (entries removed on disconnect/timeout) |
| `player:{id}:meta` | JSON profile | queue (`3600s`) and REST (no TTL) | `3600` from the queue |
| `player:{id}:room` | room id | matchmaking | `7200` |
| `queue:notify:{id}` | list of match payloads | matchmaking | `300`, refreshed on push |
| `room:{id}:meta` | room document JSON | REST / WebSocket / matchmaking | `7200` when created by matchmaking, otherwise none |
| `room:{id}:state` | game state JSON | game engine | `7200`, refreshed on every save |
| `room:{id}:winner_reported` | `"1"` | winner reporting | `86400`, deleted on rematch |

A lost game-state write is unrecoverable after the TTL, which is why every
mutation rewrites the whole document.

---

## 10. Error messages

Errors are sent as `{"type": "error", "message": "…"}`. The message text is
English and stable; the client maps known messages to Persian UI copy.

| Message | Cause |
| --- | --- |
| `Malformed JSON payload received` | The frame is not valid JSON |
| `Game not active` | The match is finished or the room has no state |
| `Not your turn` | The sender is not the active seat |
| `Dice already rolled` | A second `roll_dice` in the same turn |
| `Must roll dice first` | `move_piece` before rolling |
| `Dice result is unavailable` | Corrupt state without a dice value |
| `Invalid piece_index format. Must be an integer.` | Non-numeric index |
| `Invalid piece index` | Index outside `0..pieces_count-1` |
| `Invalid move selection` | The piece cannot travel the rolled distance |
| `Home cell is already occupied` | Two own pieces on one home cell |
| `You still have a legal move` | `pass_turn` while a move exists |
| `You are no longer playing this match` | The seat forfeited |
| `The current game is still in progress` | Rematch before the match ends |
| `Only a seated player can start a rematch` | Rematch from outside the roster |
| `Room is full` | Join on a complete room |
| `Room is no longer accepting players` | Join after the match started |
| `Room not found` | Unknown room id |
| `Authentication failed: …` | Missing, expired, forged or wrong-room token; the socket is closed with `1008` |
| `Player is not seated in this room` | The token's player is not in the room document |

---

## 11. Development endpoints

Mounted **only** when `DEBUG=true`; with the default `DEBUG=false` the router is
not registered at all, so every `/api/dev/*` path answers `404`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/dev/room/{room_id}` | Dump the raw game state |
| `POST` | `/api/dev/room/{room_id}/place` | Force a piece to a position |

```json
{ "player_id": "p1", "piece_index": 0, "position": 43 }
```

Never enable `DEBUG` in production.
