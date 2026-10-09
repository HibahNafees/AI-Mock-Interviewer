import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

# Load backend/.env before the Config class reads os.environ below.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(days=7)
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    CORS_ORIGINS = [
        o.strip()
        for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
        if o.strip()
    ]
    FIRE_API_KEY = os.environ.get("FIRE_API_KEY")
    FIRE_BASE_URL = os.environ.get("FIRE_BASE_URL", "https://fire.prosaga.net")
    FIRE_MONTHLY_BUDGET_USD = float(os.environ.get("FIRE_MONTHLY_BUDGET_USD", "1"))


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-secret"
    JWT_SECRET_KEY = "test-jwt-secret-that-is-long-enough-for-hs256"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS: dict = {}
    FIRE_API_KEY = None
