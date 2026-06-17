"""Configuration module for EchoMind.

Loads all environment variables and exposes them as a Flask-compatible
config object. Sensible defaults are provided so the app can boot in
demo mode without any credentials.
"""

import os
from dotenv import load_dotenv

# Load .env if present (no-op if missing)
load_dotenv()


class Config:
    """Flask configuration values for EchoMind."""

    # Flask secret key (sessions, flashes, etc.)
    SECRET_KEY = os.getenv("SECRET_KEY", "echomind-hackathon-2026")

    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///echomind.db")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///echomind.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Anthropic Claude
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

    # Band platform
    BAND_API_KEY = os.getenv("BAND_API_KEY", "")
    BAND_ROOM_ID = os.getenv("BAND_ROOM_ID", "")

    # Deployment / share links
    BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")

    # Demo mode (True by default so judges can see the app immediately)
    DEMO_MODE = os.getenv("DEMO_MODE", "True").lower() in ("1", "true", "yes", "on")

    # Paths
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    MEMOIR_DIR = os.path.join(BASE_DIR, "static", "memoirs")
    QR_DIR = os.path.join(BASE_DIR, "static", "qrcodes")
