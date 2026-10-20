"""Signed player tokens and the surfaces that require them.

The game trusts no identity taken from the client. A token minted by a trusted
backend (or in the DEBUG dev flow, absent) is the only source of ``player_id``.
"""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.auth import (
    TOKEN_TTL_SECONDS,
    AuthError,
    issue_player_token,
    verify_player_token,
)

client = TestClient(app)

API_KEY_HEADERS = {"X-API-Key": "test-api-key"}


@pytest.fixture
def production(monkeypatch):
    """Turn the DEBUG bypass off and configure both secrets."""
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "GAME_TOKEN_SECRET", "test-secret")
    monkeypatch.setattr(settings, "PORTEGHAL_API_KEY", "test-api-key")


def _create_room(room_id: str = "auth-room", **overrides) -> dict:
    payload = {
        "room_id": room_id,
        "player1_id": "p1",
        "player1_name": "Player One",
        "player2_id": "p2",
        "player2_name": "Player Two",
        "player_count": 2,
        "pieces_count": 4,
    }
    payload.update(overrides)
    response = client.post("/api/rooms", json=payload, headers=API_KEY_HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


# ─── Token primitives ───────────────────────────────────────────────────────


def test_token_round_trip_returns_the_player_id():
    token = issue_player_token("p1", "room-1")

    assert verify_player_token(token, room_id="room-1") == "p1"


def test_expired_token_is_rejected():
    token = issue_player_token("p1", "room-1", ttl=-1)

    with pytest.raises(AuthError):
        verify_player_token(token, room_id="room-1")


def test_token_is_bound_to_its_room():
    token = issue_player_token("p1", "room-1")

    with pytest.raises(AuthError):
        verify_player_token(token, room_id="room-2")


def test_room_token_cannot_be_replayed_on_the_queue():
    token = issue_player_token("p1", "room-1")

    with pytest.raises(AuthError):
        verify_player_token(token)


def test_tampered_token_is_rejected():
    token = issue_player_token("p1", "room-1")
    body, signature = token.split(".")
    forged = ("A" if body[0] != "A" else "B") + body[1:]

    with pytest.raises(AuthError):
        verify_player_token(f"{forged}.{signature}", room_id="room-1")


def test_signing_requires_a_secret_outside_debug(monkeypatch):
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "GAME_TOKEN_SECRET", "")
    monkeypatch.setattr(settings, "PORTEGHAL_API_KEY", "")

    with pytest.raises(AuthError):
        issue_player_token("p1")
    with pytest.raises(AuthError):
        verify_player_token("anything")


def test_debug_falls_back_to_a_dev_secret(monkeypatch):
    monkeypatch.setattr(settings, "DEBUG", True)
    monkeypatch.setattr(settings, "GAME_TOKEN_SECRET", "")
    monkeypatch.setattr(settings, "PORTEGHAL_API_KEY", "")

    assert verify_player_token(issue_player_token("p1")) == "p1"


# ─── REST surfaces ──────────────────────────────────────────────────────────


def test_room_creation_requires_the_api_key(production, fake_redis):
    payload = {"player1_id": "p1"}

    assert client.post("/api/rooms", json=payload).status_code == 401
    assert (
        client.post(
            "/api/rooms", json=payload, headers={"X-API-Key": "wrong"}
        ).status_code
        == 401
    )


def test_room_creation_issues_a_token_per_seated_player(production, fake_redis):
    created = _create_room()

    tokens = created["player_tokens"]
    assert set(tokens) == {"p1", "p2"}
    assert verify_player_token(tokens["p1"], room_id=created["room_id"]) == "p1"


def test_room_lookup_requires_a_seated_token(production, fake_redis):
    created = _create_room()
    room_id = created["room_id"]

    assert client.get(f"/api/rooms/{room_id}").status_code == 401

    seated = created["player_tokens"]["p1"]
    assert client.get(f"/api/rooms/{room_id}", params={"token": seated}).status_code == 200

    home_alone = issue_player_token("intruder", room_id)
    response = client.get(f"/api/rooms/{room_id}", params={"token": home_alone})
    assert response.status_code == 403


def test_join_requires_the_api_key(production, fake_redis):
    created = _create_room(player2_id="")
    room_id = created["room_id"]

    response = client.post(
        f"/api/rooms/{room_id}/join", json={"player_id": "p2", "player_name": "Two"}
    )
    assert response.status_code == 401

    response = client.post(
        f"/api/rooms/{room_id}/join",
        json={"player_id": "p2", "player_name": "Two"},
        headers=API_KEY_HEADERS,
    )
    assert response.status_code == 200
    assert verify_player_token(response.json()["token"], room_id=room_id) == "p2"


def test_token_endpoint_mints_queue_tokens(production):
    response = client.post(
        "/api/auth/token", json={"player_id": "p1"}, headers=API_KEY_HEADERS
    )
    assert response.status_code == 200
    body = response.json()
    assert body["expires_in"] == TOKEN_TTL_SECONDS
    assert verify_player_token(body["token"]) == "p1"

    assert client.post("/api/auth/token", json={"player_id": "p1"}).status_code == 401


# ─── WebSocket surfaces ─────────────────────────────────────────────────────


def test_room_socket_accepts_the_token_identity(production, fake_redis):
    created = _create_room()
    room_id = created["room_id"]
    # A conflicting playerId must be ignored: the token is the identity.
    url = (
        f"/ws/room/{room_id}?playerId=p2&playerName=Player"
        f"&token={created['player_tokens']['p1']}"
    )

    with client.websocket_connect(url) as websocket:
        message = websocket.receive_json()
        assert message["type"] == "sync_state"

        websocket.send_json({"action": "roll_dice"})
        rolled = websocket.receive_json()
        assert rolled["type"] == "sync_state"
        assert rolled["game"]["dice"] in range(1, 7)


def test_room_socket_acts_only_as_the_token_owner(production, fake_redis):
    created = _create_room()
    room_id = created["room_id"]
    # p1 holds the current turn; presenting p2's token must not let the
    # connection act for p1 even though the query string says playerId=p1.
    url = (
        f"/ws/room/{room_id}?playerId=p1&playerName=Player"
        f"&token={created['player_tokens']['p2']}"
    )

    with client.websocket_connect(url) as websocket:
        assert websocket.receive_json()["type"] == "sync_state"
        websocket.send_json({"action": "roll_dice"})
        message = websocket.receive_json()
        assert message["type"] == "error"
        assert message["message"] == "Not your turn"


def test_room_socket_rejects_an_unauthenticated_player(production, fake_redis):
    created = _create_room()
    url = f"/ws/room/{created['room_id']}?playerId=p1&playerName=Player"

    with client.websocket_connect(url) as websocket:
        message = websocket.receive_json()
        assert message["type"] == "error"
        assert "Authentication failed" in message["message"]


def test_room_socket_rejects_a_token_for_another_room(production, fake_redis):
    created = _create_room()
    foreign = issue_player_token("p1", "some-other-room")
    url = f"/ws/room/{created['room_id']}?playerId=p1&token={foreign}"

    with client.websocket_connect(url) as websocket:
        message = websocket.receive_json()
        assert message["type"] == "error"
        assert "Authentication failed" in message["message"]


def test_queue_socket_rejects_a_room_token(production, fake_redis):
    room_token = issue_player_token("p1", "room-1")
    url = f"/ws/queue?token={room_token}&playerName=Player"

    with client.websocket_connect(url) as websocket:
        message = websocket.receive_json()
        assert message["type"] == "error"
        assert "Authentication failed" in message["message"]


def test_debug_flow_still_identifies_players_from_the_query_string(
    monkeypatch, fake_redis, room_factory
):
    room_factory(room_id="dev-room", player_ids=("p1", "p2"))
    monkeypatch.setattr(settings, "DEBUG", True)

    with client.websocket_connect(
        "/ws/room/dev-room?playerId=p1&playerName=Player"
    ) as websocket:
        message = websocket.receive_json()
        assert message["type"] == "sync_state"
        assert message["game"]["players"][0]["id"] == "p1"
