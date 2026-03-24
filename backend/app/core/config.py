from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Resolve .env relative to this file: backend/app/core/config.py -> backend/.env
_env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=_env_path)


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Project Raven"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/raven"

    # OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/callback"

    # Google Maps
    GOOGLE_MAPS_API_KEY: str = ""

    # Interswitch
    INTERSWITCH_CLIENT_ID: str = ""
    INTERSWITCH_CLIENT_SECRET: str = ""
    INTERSWITCH_BASE_URL: str = "https://sandbox.interswitchng.com"

    model_config = {"env_file": str(_env_path), "extra": "ignore"}


settings = Settings()
