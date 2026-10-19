"""The disconnect forfeit timer must use ``settings.DISCONNECT_TIMEOUT``.

A documented, configurable timeout that the implementation ignores makes every
deployment believe it controls the forfeit window while the hard-coded value
wins.
"""

import asyncio

from app.config import settings
from app.managers.room_manager import RoomManager


def _run_forfeit_timer(monkeypatch) -> tuple[list[float], list[tuple[str, str]]]:
    manager = RoomManager()
    slept: list[float] = []
    forfeited: list[tuple[str, str]] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    async def on_forfeit(room_id: str, player_id: str) -> None:
        forfeited.append((room_id, player_id))

    monkeypatch.setattr("app.managers.room_manager.async_sleep", fake_sleep)
    asyncio.run(manager._forfeit_timer("room-1", "p1", on_forfeit))
    return slept, forfeited


def test_forfeit_timer_waits_for_the_configured_timeout(monkeypatch):
    monkeypatch.setattr(settings, "DISCONNECT_TIMEOUT", 7)

    slept, forfeited = _run_forfeit_timer(monkeypatch)

    assert slept == [7]
    assert forfeited == [("room-1", "p1")]


def test_forfeit_timer_follows_a_changed_setting(monkeypatch):
    monkeypatch.setattr(settings, "DISCONNECT_TIMEOUT", 3)

    slept, _forfeited = _run_forfeit_timer(monkeypatch)

    assert slept == [3]
