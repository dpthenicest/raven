from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Resolve .env relative to this file: backend/app/core/config.py -> backend/.env
_env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=_env_path)

# Absolute path to backend/ directory
_backend_dir = Path(__file__).resolve().parents[2]


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

    # Google Cloud (Document AI)
    DOCUMENT_AI_PROJECT_ID: str = ""
    DOCUMENT_AI_LOCATION: str = "us"
    DOCUMENT_AI_PROCESSOR_ID: str = ""

    # Monnify
    MONNIFY_API_KEY: str = ""
    MONNIFY_SECRET_KEY: str = ""
    MONNIFY_CONTRACT_CODE: str = ""
    MONNIFY_BASE_URL: str = "https://sandbox.monnify.com"
    MONNIFY_REDIRECT_URL: str = "http://localhost:3000/payment/callback"

    model_config = {"env_file": str(_env_path), "extra": "ignore"}


settings = Settings()
