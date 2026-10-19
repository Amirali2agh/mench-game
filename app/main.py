from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.health import router as health_router
from app.api.rooms import router as rooms_router
from app.api.websocket.queue import router as queue_router
from app.api.websocket.room import router as room_router
from app.api.dev import router as dev_router
app = FastAPI(
    title=settings.PROJECT_NAME,
    debug=settings.DEBUG
)

def configure_cors(application: FastAPI, origins: list[str]) -> None:
    """
    Allow only the configured browser origins to call the API.

    The client is normally served by the same reverse proxy as the API, so no
    CORS headers are needed at all. When the frontend lives on another origin
    the allowlist is explicit; the API has no cookie session, so credentials
    stay disabled and the method/header lists stay minimal.
    """
    if not origins:
        return
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        allow_credentials=False,
        max_age=600,
    )


configure_cors(app, settings.cors_origins)

# Include application routers
app.include_router(health_router)
app.include_router(rooms_router)
app.include_router(queue_router)
app.include_router(room_router)

# The dev router exposes cheat endpoints that can mutate live games, so it is
# only mounted when debug mode is explicitly enabled.
if settings.DEBUG:
    app.include_router(dev_router)