from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from app.main import app

client = TestClient(app)

def test_health_check_endpoint_success():
    """
    Test that the health check endpoint returns 200 and 'healthy' status
    when Redis is reachable and pings successfully.
    """
    with patch("app.api.health.redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.ping.return_value = True

        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {
            "status": "healthy",
            "redis": "ok"
        }
        mock_redis.ping.assert_called_once()


def test_health_check_endpoint_redis_failure():
    """
    Test that the health check endpoint answers 503 when Redis is unreachable.

    Redis holds every queue, room and game state, so an instance that cannot
    reach it must not be reported as healthy to a load balancer or a container
    runtime.
    """
    with patch("app.api.health.redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.ping.side_effect = Exception("Connection lost")

        response = client.get("/health")

        assert response.status_code == 503
        assert response.json() == {
            "status": "unhealthy",
            "redis": "unavailable"
        }
        mock_redis.ping.assert_called_once()
