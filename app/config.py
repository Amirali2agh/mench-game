import os

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # تنظیمات عمومی پروژه
    PROJECT_NAME: str = "Mensch Multiplayer Game"
    # Debug mode must be opt-in: it mounts the /api/dev cheat endpoints, which
    # can write arbitrary piece positions into live games.
    DEBUG: bool = False
    
    # تنظیمات اتصال به Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None
    
    # تنظیمات قوانین زمانی بازی
    DISCONNECT_TIMEOUT: int = 60  # مدت زمان مجاز قطع اتصال (ثانیه)
    MATCHMAKING_TIMEOUT: int = 30  # مدت زمان انتظار در صف بازی (ثانیه)
    
    # تنظیمات ادغام با Porteghal
    PORTEGHAL_API_URL: str = "http://localhost:8090"
    PORTEGHAL_API_KEY: str = ""
    # Browser origins allowed to call the API. Empty means same-origin only, so
    # the reverse proxy that serves the game needs no CORS at all. The value is
    # a comma-separated allowlist; "*" is refused outside debug mode.
    ALLOWED_CORS_ORIGINS: str = ""

    @property
    def cors_origins(self) -> list[str]:
        """Parsed CORS allowlist: trimmed, without trailing slashes."""
        return [
            origin.strip().rstrip("/")
            for origin in self.ALLOWED_CORS_ORIGINS.split(",")
            if origin.strip()
        ]

    @model_validator(mode="after")
    def _reject_wildcard_cors_outside_debug(self) -> "Settings":
        """A wildcard is a development convenience, never a production setting."""
        if not self.DEBUG and "*" in self.cors_origins:
            raise ValueError(
                "ALLOWED_CORS_ORIGINS='*' is only allowed when DEBUG=true; "
                "list the browser origins explicitly"
            )
        return self

    # پیکربندی نحوه خواندن تنظیمات
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# ایجاد یک نمونه واحد (Singleton) از کلاس تنظیمات برای استفاده در کل پروژه
settings = Settings()