# Mensch Multiplayer Game

Real-time multiplayer **Mensch** (Ludo-style) game: a FastAPI + Redis backend
and a React + TypeScript frontend, integrated with the Porteghal coin platform.

Two or four players join a matchmaking queue, are seated in a room, and play a
full Mensch match over WebSockets. The server owns the rules and the state; the
client only renders and sends actions.

## Contents

- [Architecture at a glance](#architecture-at-a-glance)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Rules the engine enforces](#rules-the-engine-enforces)
- [API and WebSocket surface](#api-and-websocket-surface)
- [Tests and gates](#tests-and-gates)
- [Repository layout](#repository-layout)
- [Deployment](#deployment)
- [Contributing](#contributing)
- [License](#license)

## Architecture at a glance

```
┌──────────────────┐   REST: create / join room    ┌──────────────────────┐
│  React frontend  │ ────────────────────────────► │  FastAPI (app/)      │
│  front/src       │                               │                      │
│                  │ ◄──── sync_state, chat ────── │  room / queue WS     │
└──────────────────┘   WS: /ws/queue, /ws/room     └──────────┬───────────┘
                                                              │
                                                   ┌──────────▼───────────┐
                                                   │  Redis               │
                                                   │  queues, room meta,  │
                                                   │  game state (TTL 2h) │
                                                   └──────────────────────┘
```

* `app/api/websocket/queue.py` — matchmaking queue, per-player match inbox.
* `app/api/websocket/room.py` — the gameplay loop (dice, moves, chat, rematch)
  and the disconnect/forfeit flow.
* `app/services/game_service.py` — the game engine: moves, captures, turn
  rotation, win detection.
* `app/services/room_service.py` — room lifecycle: seating, starting a match,
  rematches, one-shot winner reporting.
* `app/services/queue_service.py` — Redis-backed matchmaking.
* `front/src/hooks/useMenschSocket.ts` — the client socket state machine.
* `front/src/utils/boardCoordinates.ts` — the client board geometry.

`ARCHITECTURE.md` is the detailed protocol reference: every WebSocket message,
the board mapping, Redis keys and TTLs.

## Quick start

### Docker Compose (backend + Redis)

```bash
docker compose up --build
# REST  http://localhost:8000
# WS    ws://localhost:8000
# Probe curl http://localhost:8000/health
```

Redis is only reachable from the compose network (it has no password), and the
backend waits for its healthcheck before starting.

The image installs the pinned runtime dependencies only and runs as an
unprivileged `app` user. Restricted networks can opt in to a mirror index:

```bash
docker build --build-arg PIP_INDEX_URL=https://mirror2.chabokan.net/pypi/simple/ .
```

The frontend is not part of this image; run it from `front/` (below) or serve
`front/dist` behind a reverse proxy (see [Deployment](#deployment)).

### Local development

Prerequisites: Python 3.12+, Node.js 24 (or 22.18+, where `npm test` can run
TypeScript through Node's built-in type stripping), a running Redis on
`127.0.0.1:6379`, and `npm`.

Backend:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # adjust values; DEBUG stays false
uvicorn app.main:app --reload --port 8000
```

Frontend (second terminal):

```bash
cd front
npm ci
npm run dev                   # Vite dev server on http://localhost:3000
```

The client never hard-codes a backend host. `npm run dev` falls back to port
8000 of the page host, while a production build uses its own origin (`/api` and
`/ws`, forwarded by the reverse proxy). Set `VITE_API_BASE_URL` and
`VITE_WS_BASE_URL` at build time to point it somewhere else; see
`front/.env.example` and `docs/deployment.md`.

## Configuration

The backend reads environment variables (and `.env`) through
`app/config.py`. `.env.example` documents every key with a safe placeholder.

| Variable | Default | Purpose |
| --- | --- | --- |
| `PROJECT_NAME` | `Mensch Multiplayer Game` | OpenAPI title |
| `DEBUG` | `false` | Mounts the `/api/dev` cheat router. Keep it `false` outside local development |
| `REDIS_HOST` | `localhost` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_DB` | `0` | Redis database index |
| `REDIS_PASSWORD` | empty | Redis password, if any |
| `DISCONNECT_TIMEOUT` | `60` | Seconds a dropped player may take to reconnect before forfeiting |
| `MATCHMAKING_TIMEOUT` | `30` | Seconds to wait for a match / for a room roster to fill |
| `PORTEGHAL_API_URL` | `http://localhost:8090` | Porteghal base URL for winner reporting |
| `PORTEGHAL_API_KEY` | empty | Porteghal internal API key. Required for payouts; when empty the service logs an error and skips the call instead of using a fallback |
| `ALLOWED_CORS_ORIGINS` | empty | Comma-separated browser origin allowlist. Empty means same-origin only (the proxy setup); `*` is refused unless `DEBUG=true` |

Never commit a real `PORTEGHAL_API_KEY`. It is read from the environment only.

The frontend has its own build-time configuration, documented in
`front/.env.example`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_API_BASE_URL` | empty (same origin) | REST origin, e.g. `https://api.example.com` |
| `VITE_WS_BASE_URL` | empty (page host) | WebSocket origin, e.g. `wss://api.example.com` |
| `VITE_ALLOWED_HOSTS` | empty (check disabled) | Dev-server host allowlist, comma separated |

`npm run dev` keeps working with nothing configured: it points at port 8000 of
the page host, where the documented local backend listens.

## Rules the engine enforces

* **Track and home:** positions `0..39` are the shared circular track, `40..43`
  are a player's private home column, `-1` is the yard.
* **Leaving the yard:** only a roll of 6 moves a piece from `-1` to position 0.
* **Moving:** a piece moves exactly the rolled value. A move that would overshoot
  position 43 is rejected.
* **Capturing:** landing on a cell occupied by an opponent on the shared track
  sends every opponent piece on that cell back to its yard.
* **Extra roll:** a 6 (or a capture) keeps the turn.
* **Three sixes:** the third consecutive 6 forfeits the turn.
* **Blocked player:** if no piece can move, the turn advances automatically.
* **Winning:** the first player with every piece in `40..43` wins. Position 44 is
  never reachable, so "finished" is a full home column, not a centre cell.
* **Turn timer:** the client runs a 45-second timer and sends `pass_turn`. The
  server only accepts it from the active player and only when no legal move is
  available.
* **Disconnect:** a dropped player has `DISCONNECT_TIMEOUT` seconds to reconnect.
  In a two-player match the timer ends the match; with more players the seat is
  eliminated and the match continues until one player is left.

Seat layout, corner colours and track offsets are defined once in
`app/services/board_layout.py` and mirrored in `front/src/utils/boardCoordinates.ts`;
the resolved per-seat offsets are sent to clients as `track_offsets`. A test
fails if the two tables drift apart.

## API and WebSocket surface

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Liveness/dependency probe |
| `POST` | `/api/rooms` | Create a room (optionally with both players) |
| `GET` | `/api/rooms/{room_id}` | Read the room document |
| `POST` | `/api/rooms/{room_id}/join` | Seat the first free player slot |
| `WS` | `/ws/queue?playerId=&playerName=&playerCount=&piecesCount=` | Matchmaking |
| `WS` | `/ws/room/{room_id}?playerId=&playerName=` | Gameplay |
| `WS` | `/ws/game/{room_id}/{player_num}` | Porteghal-compatible gameplay entry point |
| `POST` | `/api/dev/room/{room_id}/place` | Cheat endpoint, mounted only when `DEBUG=true` |

Message schemas, payload rules and error messages are documented in
`ARCHITECTURE.md`.

## Tests and gates

```bash
# Backend
python -m pytest -q

# Frontend
cd front
npx tsc --noEmit
npm run lint
npm test
npx vite build
```

The suite uses an in-memory Redis fake, so no Redis server is needed to run the
tests. The same five commands run in CI (`.github/workflows/ci.yml`), one job
each, plus a secret scan. Do not merge a pull request with a red gate.

## Repository layout

```
app/                    FastAPI application
  api/                  REST routers and WebSocket endpoints
  managers/             In-memory socket registries and timers
  services/             Game engine, rooms, matchmaking, Porteghal client
  utils/                Redis key builders
test/                   pytest suite (Redis fake in conftest.py)
front/                  React + TypeScript + Vite + Tailwind client
  src/components/       Board, dice, overlays, lobby, queue
  src/hooks/            WebSocket state machine
  src/utils/            Board geometry, bridge, colours
docs/                   Deployment notes
ARCHITECTURE.md         Protocol and data reference
```

## Deployment

See `docs/deployment.md` for a reverse-proxy layout, the systemd unit and the
configuration checklist. `.env.example` lists every variable.

## Contributing

See `CONTRIBUTING.md`: branch from `main`, open a pull request, keep the gates
green. Never push to `main` directly. UI text is Persian and right-to-left; code,
comments and commit messages are English.

## License

This software is **proprietary**, not open source. All rights reserved.

Commercial use requires a paid license:

| | |
| --- | --- |
| **Initial license** | USD **231** one-time, per organization |
| **Annual renewal** | USD **66** / year, covering updates and email support |
| **Attribution** | every product must display "Powered by [binux.tech](https://binux.tech)" |

See [LICENSE](LICENSE) for the full terms. Licensing and purchase:
**licensing@binux.tech** — https://binux.tech

Third-party dependencies (React, Vite, FastAPI, …) remain under their own
licenses and are not covered by this one.
