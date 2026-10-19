"""Matchmaking delivery: timeout handling and a complete match payload (#17)."""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.websocket.queue import router
from app.config import settings
from app.managers.queue_manager import QueueManager

api_app = FastAPI()
api_app.include_router(router)


def test_queue_times_out_and_leaves_the_queue(fake_redis, monkeypatch):
    monkeypatch.setattr(settings, "MATCHMAKING_TIMEOUT", 0.05)
    client = TestClient(api_app)

    with client.websocket_connect(
        "/ws/queue?playerId=solo&playerName=Solo&playerCount=2&piecesCount=4"
    ) as websocket:
        message = websocket.receive_json()

    assert message["type"] == "queue_timeout"
    assert message["player_id"] == "solo"
    assert asyncio.run(fake_redis.lrange("matchmaking:queue:2p:4pieces", 0, -1)) == []


def test_match_found_carries_the_piece_count_for_every_player(fake_redis):
    client = TestClient(api_app)

    with client.websocket_connect(
        "/ws/queue?playerId=q1&playerName=Q1&playerCount=2&piecesCount=3"
    ) as waiting:
        with client.websocket_connect(
            "/ws/queue?playerId=q2&playerName=Q2&playerCount=2&piecesCount=3"
        ) as completer:
            direct = completer.receive_json()
            watched = waiting.receive_json()

    assert direct["type"] == "match_found"
    assert direct["pieces_count"] == 3
    assert watched["type"] == "match_found"
    assert watched["pieces_count"] == 3
    assert watched["room_id"] == direct["room_id"]
    assert [player["id"] for player in watched["players"]] == ["q1", "q2"]


def test_pending_notification_is_shared_by_both_players(fake_redis):
    """Every matched player must get a match_found, not just the last one."""

    async def _check() -> None:
        from app.services.queue_service import QueueService

        await QueueService.add_to_queue("q1", "Q1", "", 2, 2)
        await QueueService.add_to_queue("q2", "Q2", "", 2, 2)
        for player_id in ("q1", "q2"):
            pending = await fake_redis.lrange(f"queue:notify:{player_id}", 0, -1)
            assert pending, f"{player_id} received no match notification"
            payload = json.loads(pending[0])
            assert payload["pieces_count"] == 2

    asyncio.run(_check())


@pytest.mark.asyncio
async def test_send_match_found_includes_the_piece_count():
    manager = QueueManager()
    websocket = AsyncMock()
    manager.active_connections["p1"] = websocket

    await manager.send_match_found("p1", "room-9", [{"id": "p1"}], 2)

    websocket.send_json.assert_awaited_once_with({
        "type": "match_found",
        "room_id": "room-9",
        "players": [{"id": "p1"}],
        "pieces_count": 2,
    })
