from functools import lru_cache
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


def is_cloud_host() -> bool:
    """True on Render/Docker — no desktop; Playwright runs headless on the server."""
    return bool(os.environ.get("RENDER", "").strip())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Facebook Marketplace Monitor"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    DATABASE_URL: str = "sqlite:///./marketplace_monitor.db"
    API_PORT: int = 8000

    SECRET_KEY: str = "change-this-secret-key-in-production-use-long-random-string"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Admin login — set in .env
    ADMIN_EMAIL: str = ""
    ADMIN_PASSWORD: str = ""

    # SMTP — configured in backend .env only (NOT in dashboard UI)
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "Marketplace Monitor"
    SMTP_USE_TLS: bool = True

    PLAYWRIGHT_TIMEOUT: int = 60000
    # None = use dashboard Settings toggle. False = visible Chromium, True = headless
    PLAYWRIGHT_HEADLESS: bool | None = None

    # Facebook session cookies (restored on each scan)
    FACEBOOK_SESSION_FILE: str = "data/facebook_session.json"
    FACEBOOK_PROFILE_DIR: str = "data/facebook_chrome_profile"

    @property
    def admin_email(self) -> str:
        return self.ADMIN_EMAIL.strip() if self.ADMIN_EMAIL.strip() else "admin@example.com"

    @property
    def admin_password(self) -> str:
        return self.ADMIN_PASSWORD if self.ADMIN_PASSWORD else "admin123"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    def smtp_config_dict(self) -> dict:
        return {
            "smtp_host": self.SMTP_HOST,
            "smtp_port": str(self.SMTP_PORT),
            "smtp_user": self.SMTP_USER,
            "smtp_password": self.SMTP_PASSWORD,
            "smtp_from_email": self.SMTP_FROM_EMAIL or self.SMTP_USER,
            "smtp_from_name": self.SMTP_FROM_NAME,
            "smtp_use_tls": "true" if self.SMTP_USE_TLS else "false",
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
