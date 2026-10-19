import logging

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.redis_client import redis_client

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check():
    """
    Report whether the API can actually serve game traffic.

    Redis holds every queue, room and game state, so an instance that cannot
    reach it is unusable. Answering 200 in that case keeps a broken instance in
    rotation behind a load balancer or a container runtime, so a dependency
    failure is reported as 503 instead.
    """
    try:
        await redis_client.ping()
    except Exception as exc:
        logger.warning("Health check failed: Redis is unreachable: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy", "redis": "unavailable"},
        )

    return {"status": "healthy", "redis": "ok"}
