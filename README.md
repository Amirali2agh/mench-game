ensch Multiplayer Game Backend

A robust, real-time multiplayer backend for the classic board game **Mensch** (Ludo-style). Built with Python (**FastAPI**), **Redis** for state caching and matchmaking queue management, and asynchronous **WebSockets** for high-frequency game interactions.

---

## Features

- **Matchmaking Queue:** Dynamic, Redis-backed matchmaking queues supporting both 2-player and 4-player lobbies.
- **Dynamic Piece Counts:** Players can choose to customize matches and play with 2, 3, or 4 pieces.
- **Stateful Game Engine:** Complete Mensch gameplay rule verification (rolling, entering track, capturing, private home-stretch logic, and win-condition checks).
- **Graceful Reconnection:** Tracks player connection state. If a player disconnects, an asynchronous 60-second countdown forfeit timer starts. Reconnecting within 60 seconds cancels the forfeit and resumes play.
- **Dockerized Architecture:** Orchestrates both the FastAPI web application and the Redis cache service in isolated networks with simple docker-compose setups.
- **High-Speed Iranian Mirror Configuration:** Pre-configured Dockerfile utilizing local PyPI mirrors for fast, barrier-free container builds inside Iran.
- **Robust Test Coverage:** Integrated test suite with mocked database engines verifying matchmaking, connection lifecycles, and core mathematics of the Mensch board.

---

## Tech Stack

- **Backend Framework:** FastAPI (Python 3.12+)
- **Database / Cache:** Redis (V7+)
- **WSGI / ASGI Server:** Uvicorn
- **Object Schema & Configurations:** Pydantic / Pydantic Settings
- **Testing Engine:** Pytest / Pytest-Asyncio / Httpx
- **Containerization:** Docker & Docker Compose

---

## Getting Started

### Prerequisites
Make sure you have **Docker Desktop** installed and running on your host machine, with the **WSL 2 Integration** enabled in the Docker Desktop settings.

### Run with Docker Compose (Recommended)

To build and launch both the FastAPI backend server and the Redis database container, run the following command in the project root:

```bash
docker compose up --build
Server base URL: http://localhost:8000
WS Server URL: ws://localhost:8000
Verify Server Health
Once the containers are running, navigate to http://localhost:8000/health in your browser. You should receive a healthy response confirming Redis connectivity:
code
JSON
{
  "status": "healthy",
  "redis": "ok"
}
Running the Test Suite Locally
If you are developing locally inside WSL and want to run the test suite:
Activate your virtual environment:
code
Bash
source .venv/bin/activate
Execute Pytest:
code
Bash
pytest
The test runner will automatically collect and execute all 16 unit and integration tests across routers, managers, and service files.
Integration Spec for Frontend Developers
For detailed integration spec including WebSocket endpoint schemas, query parameters, client gameplay actions (roll_dice, move_piece), and server broadcasts (sync_state), please refer to the ARCHITECTURE.md file in the root director

---

## License

This software is **proprietary**, not open source. All rights reserved.

Commercial use requires a paid license:

| | |
|---|---|
| **Initial license** | USD **231** one-time, per organization |
| **Annual renewal** | USD **66** / year, covering updates and email support |
| **Attribution** | every product must display "Powered by [binux.tech](https://binux.tech)" |

See [LICENSE](LICENSE) for the full terms.
Licensing and purchase: **licensing@binux.tech** — https://binux.tech

Third-party dependencies (React, Vite, FastAPI, …) remain under their own
licenses and are not covered by this one.