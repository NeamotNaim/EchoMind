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

    # Google Gemini (used by the Flask-side interviewer)
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

    # Band platform — WebSocket + REST endpoints
    BAND_WS_URL = os.getenv(
        "BAND_WS_URL", "wss://app.band.ai/api/v1/socket/websocket"
    )
    BAND_REST_URL = os.getenv("BAND_REST_URL", "https://app.band.ai/")

    # Deployment / share links. On Railway, RAILWAY_PUBLIC_DOMAIN is auto-set
    # to the public hostname (e.g. "echomind.up.railway.app"). Fall back to
    # BASE_URL for local dev or other hosts.
    BASE_URL = os.getenv(
        "BASE_URL",
        "https://" + os.getenv("RAILWAY_PUBLIC_DOMAIN", "localhost:5000"),
    )

    # Demo mode (True by default so judges can see the app immediately)
    DEMO_MODE = os.getenv("DEMO_MODE", "True").lower() in ("1", "true", "yes", "on")

    # Paths
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    MEMOIR_DIR = os.path.join(BASE_DIR, "static", "memoirs")
    QR_DIR = os.path.join(BASE_DIR, "static", "qrcodes")
