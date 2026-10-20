"""Limits on untrusted WebSocket/REST input.

Covers the four hardening areas: identifier syntax (Redis key safety), frame
size and action rate, and server-owned chat authorship/text.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.auth import AuthError, issue_player_token
from app.utils.identifiers import is_valid_player_id, is_valid_room_id
from app.utils.limits import MAX_CHAT_CHARS

client = TestClient(app)


def _open_room(room_factory, room_id: str = "hard-room"):
    room_factory(room_id=room_id, player_ids=("p1", "p2"))
    return room_id


def _connect(room_id: str, player_id: str = "p1", name: str = "Player"):
    return client.websocket_connect(
        f"/ws/room/{room_id}?playerId={player_id}&playerName={name}"
    )


# ─── Identifier syntax ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value",
    ["p1", "player_1", "a.b-c", "x" * 64],
)
def test_valid_player_ids(value):
    assert is_valid_player_id(value)


@pytest.mark.parametrize(
    "value",
    ["evil:key", "p1:meta", "with space", "", "x" * 65, "new\nline", 42],
)
def test_invalid_player_ids(value):
    assert not is_valid_player_id(value)


@pytest.mark.parametrize("value", ["room-1", "abc_DEF", "x" * 64])
def test_valid_room_ids(value):
    assert is_valid_room_id(value)


@pytest.mark.parametrize("value", ["bad:id", "room:meta", "../x", "with space", ""])
def test_invalid_room_ids(value):
    assert not is_valid_room_id(value)


def test_tokens_are_not_minted_for_unsafe_player_ids():
    with pytest.raises(AuthError):
        issue_player_token("evil:key")


def test_malformed_room_id_in_the_path_is_rejected():
    # The path pattern is validated before the route or any Redis access.
    assert client.get("/api/rooms/bad:id").status_code == 422


# ─── Frame size and rate ────────────────────────────────────────────────────


def test_oversized_frames_are_rejected(fake_redis, room_factory):
    room_id = _open_room(room_factory)

    with _connect(room_id) as websocket:
        assert websocket.receive_json()["type"] == "sync_state"

        websocket.send_text("x" * 5000)
        message = websocket.receive_json()
        assert message == {"type": "error", "message": "Message too large"}

        # The connection survives and still accepts a valid frame.
        websocket.send_json({"action": "noop"})
        websocket.send_json({"action": "noop"})


def test_actions_are_rate_limited(fake_redis, room_factory):
    room_id = _open_room(room_factory)

    with _connect(room_id) as websocket:
        assert websocket.receive_json()["type"] == "sync_state"

        for _ in range(10):
            websocket.send_json({"action": "noop"})
        websocket.send_json({"action": "noop"})
        message = websocket.receive_json()
        assert message == {"type": "error", "message": "Too many actions"}


# ─── Chat authorship and text ───────────────────────────────────────────────


def test_chat_author_cannot_be_spoofed(fake_redis, room_factory):
    room_id = _open_room(room_factory)

    with _connect(room_id, player_id="p1", name="Ali") as websocket:
        assert websocket.receive_json()["type"] == "sync_state"

        websocket.send_json(
            {"action": "chat", "playerName": "Admin", "message": "hello"}
        )
        chat = websocket.receive_json()
        assert chat["type"] == "chat"
        # The stored profile wins over both the query string and the frame.
        assert chat["player_name"] == "Player p1"
        assert chat["message"] == "hello"


def test_chat_text_is_sanitized_and_capped(fake_redis, room_factory):
    room_id = _open_room(room_factory)

    with _connect(room_id) as websocket:
        assert websocket.receive_json()["type"] == "sync_state"

        websocket.send_json(
            {"action": "chat", "message": "\x00hello\x07 " + "x" * 500}
        )
        chat = websocket.receive_json()
        assert chat["message"] == ("hello " + "x" * 500)[:MAX_CHAT_CHARS]
        assert "\x00" not in chat["message"]
        assert "\x07" not in chat["message"]


# ─── Malformed identifiers on the sockets ───────────────────────────────────


def test_room_socket_rejects_a_malformed_room_id(fake_redis):
    with client.websocket_connect("/ws/room/bad:id?playerId=p1") as websocket:
        message = websocket.receive_json()
        assert message["type"] == "error"
        assert message["message"] == "Invalid room id"


def test_room_socket_rejects_a_key_like_player_id(fake_redis):
    with client.websocket_connect(
        "/ws/room/room-1?playerId=evil:key&playerName=Player"
    ) as websocket:
        message = websocket.receive_json()
        assert message["type"] == "error"
        assert message["message"] == "Authentication failed: invalid player id"


def test_game_socket_rejects_a_malformed_seat(fake_redis):
    with client.websocket_connect("/ws/game/room-1/9") as websocket:
        message = websocket.receive_json()
        assert message["type"] == "error"
        assert message["message"] == "Invalid room or seat"
