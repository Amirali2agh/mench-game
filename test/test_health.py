"""The health endpoint must reflect Redis availability (issue #22).

A health endpoint that answers 200 while its only dependency is unreachable is
worse than no health endpoint: load balancers and container runtimes keep a
broken instance in rotation.
"""

import logging

from fastapi.testclient import TestClient

from app.main import app


class _UnreachableRedis:
    async def ping(self):
        raise ConnectionError("redis is down")


class _HealthyRedis:
    async def ping(self):
        return True


def test_health_reports_503_when_redis_is_unreachable(monkeypatch, caplog):
    monkeypatch.setattr("app.api.health.redis_client", _UnreachableRedis())

    with caplog.at_level(logging.WARNING):
        response = TestClient(app).get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "unhealthy", "redis": "unavailable"}
    # The failure must be visible in the logs, not swallowed.
    assert "redis" in caplog.text.lower()


def test_health_reports_200_when_redis_answers(monkeypatch):
    monkeypatch.setattr("app.api.health.redis_client", _HealthyRedis())

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "redis": "ok"}
