import os
from unittest import mock
from app.config import Settings

def test_default_settings():
    """تست بررسی صحت لود شدن مقادیر پیش‌فرض تنظیمات"""
    settings = Settings()
    
    # بررسی مقادیر پیش‌فرض عمومی
    assert settings.PROJECT_NAME == "Mensch Multiplayer Game"
    # Debug mode must be opt-in: it exposes the /api/dev cheat endpoints.
    assert settings.DEBUG is False
    
    # بررسی مقادیر پیش‌فرض رادیس
    expected_host = os.getenv("REDIS_HOST", "localhost")
    assert settings.REDIS_HOST == expected_host
    assert settings.REDIS_PORT == 6379
    assert settings.REDIS_DB == 0
    assert settings.REDIS_PASSWORD is None
    
    # بررسی مقادیر پیش‌فرض زمان‌بندی بازی
    assert settings.DISCONNECT_TIMEOUT == 60
    assert settings.MATCHMAKING_TIMEOUT == 30


def test_settings_override_via_env():
    """تست بررسی اینکه آیا تنظیمات با متغیرهای محیطی به درستی بازنویسی و تبدیل نوع می‌شوند یا خیر"""
    # ایجاد متغیرهای محیطی موقت برای تست با استفاده از mock.patch.dict
    mock_env = {
        "PROJECT_NAME": "Test Mensch Game",
        "REDIS_PORT": "8888",
        "DISCONNECT_TIMEOUT": "30"
    }
    
    with mock.patch.dict(os.environ, mock_env):
        settings = Settings()
        
        # بررسی اعمال متغیرهای محیطی جدید
        assert settings.PROJECT_NAME == "Test Mensch Game"
        
        # بررسی تبدیل خودکار نوع داده رشته در متغیر محیطی به نوع داده عدد در پایدنتیک
        assert settings.REDIS_PORT == 8888
        assert settings.DISCONNECT_TIMEOUT == 30