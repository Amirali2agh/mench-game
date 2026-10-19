"""REST room API contracts: validation and settings persistence (issue #16)."""
import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.rooms import router
from app.services import room_service as RoomService

api_app = FastAPI()
api_app.include_router(router)


def _valid_payload(**overrides) -> dict:
    payload = {
        "player_count": 2,
        "pieces_count": 4,
        "coin_bet": 0,
        "player1_id": "p1",
        "player1_name": "Player 1",
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    "overrides",
    [
        {"player_count": 3},
        {"player_count": 5},
        {"player_count": 0},
        {"pieces_count": 1},
        {"pieces_count": 5},
        {"coin_bet": -1},
        {"player1_id": ""},
        {"player1_id": "player one"},
        {"player1_id": "p" * 65},
        {"player2_id": "bad id"},
        {"room_id": "room:1"},
        {"room_id": "a b"},
    ],
)
def test_create_room_rejects_invalid_payloads(overrides):
    client = TestClient(api_app)

    response = client.post("/api/rooms", json=_valid_payload(**overrides))

    assert response.status_code == 422, response.text


def test_create_room_persists_the_settings_in_the_room_document(fake_redis):
    client = TestClient(api_app)
    payload = _valid_payload(player_count=2, pieces_count=3, coin_bet=75)

    response = client.post("/api/rooms", json=payload)

    assert response.status_code == 200, response.text
    room_id = response.json()["room_id"]

    raw = asyncio.run(fake_redis.get(f"room:{room_id}:meta"))
    meta = json.loads(raw)
    assert meta["player_count"] == 2
    assert meta["pieces_count"] == 3
    assert meta["coin_bet"] == 75
    assert meta["status"] == RoomService.ROOM_STATUS_WAITING

    # The legacy side keys are gone: the room document is authoritative.
    assert asyncio.run(fake_redis.get(f"room:{room_id}:pieces_count")) is None
    assert asyncio.run(fake_redis.get(f"room:{room_id}:player_count")) is None


def test_create_room_keeps_the_settings_after_a_player_joins(fake_redis):
    client = TestClient(api_app)
    created = client.post(
        "/api/rooms", json=_valid_payload(pieces_count=3, coin_bet=40)
    ).json()
    room_id = created["room_id"]

    joined = client.post(
        f"/api/rooms/{room_id}/join", json={"player_id": "p2", "player_name": "P2"}
    )

    assert joined.status_code == 200
    assert joined.json()["status"] == RoomService.ROOM_STATUS_PLAYING
    meta = json.loads(asyncio.run(fake_redis.get(f"room:{room_id}:meta")))
    assert meta["pieces_count"] == 3
    assert meta["coin_bet"] == 40


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"player_id": ""},
        {"player_id": "bad id"},
        {"player_id": "p" * 65},
    ],
)
def test_join_room_rejects_invalid_payloads(fake_redis, body):
    client = TestClient(api_app)
    created = client.post("/api/rooms", json=_valid_payload()).json()

    response = client.post(f"/api/rooms/{created['room_id']}/join", json=body)

    assert response.status_code == 422, response.text


def test_join_room_rejects_a_cancelled_room(fake_redis):
    client = TestClient(api_app)
    created = client.post(
        "/api/rooms", json=_valid_payload(player_count=4)
    ).json()
    room_id = created["room_id"]

    room = asyncio.run(RoomService.get_room(room_id))
    asyncio.run(RoomService.cancel_room(room_id, room))

    response = client.post(
        f"/api/rooms/{room_id}/join",
        json={"player_id": "p2", "player_name": "P2"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Room is no longer accepting players"


def test_join_room_is_idempotent_for_a_seated_player(fake_redis):
    client = TestClient(api_app)
    created = client.post("/api/rooms", json=_valid_payload()).json()
    room_id = created["room_id"]

    first = client.post(
        f"/api/rooms/{room_id}/join", json={"player_id": "p2", "player_name": "P2"}
    )
    second = client.post(
        f"/api/rooms/{room_id}/join", json={"player_id": "p2", "player_name": "P2"}
    )

    assert first.json()["player_num"] == 2
    assert second.json()["player_num"] == 2
    meta = json.loads(asyncio.run(fake_redis.get(f"room:{room_id}:meta")))
    assert len(meta["players"]) == 2
