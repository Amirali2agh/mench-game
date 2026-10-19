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

# Set up CORS middleware to allow cross-origin requests
origins_setting = settings.ALLOWED_CORS_ORIGINS
if origins_setting == "*":
    cors_origins = ["*"]
else:
    cors_origins = [o.strip() for o in origins_setting.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include application routers
app.include_router(health_router)
app.include_router(rooms_router)
app.include_router(queue_router)
app.include_router(room_router)

# The dev router exposes cheat endpoints that can mutate live games, so it is
# only mounted when debug mode is explicitly enabled.
if settings.DEBUG:
    app.include_router(dev_router)