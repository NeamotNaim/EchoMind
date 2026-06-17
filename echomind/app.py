"""EchoMind Flask application factory.

Run locally:
    python app.py
"""

import logging
import os

from flask import Flask

from config import Config
from models.database import db

from routes.main import main_bp
from routes.session import session_bp
from routes.memoir import memoir_bp

from anthropic import Anthropic

from band.room_manager import BandRoomManager
from agents.interviewer import InterviewerAgent
from agents.organiser import OrganiserAgent
from agents.factchecker import FactCheckerAgent
from agents.storyteller import StorytellerAgent
from agents.legacybuilder import LegacyBuilderAgent

from utils.pdf_generator import MemoirPDFGenerator
from utils.qr_generator import QRGenerator
from utils.history_lookup import HistoryLookup


# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("echomind")


def _make_anthropic(api_key: str):
    """Create an Anthropic client if a key is provided, else return None."""
    if not api_key:
        logger.warning(
            "ANTHROPIC_API_KEY not set — agents will use heuristic fallbacks."
        )
        return None
    try:
        return Anthropic(api_key=api_key)
    except Exception as exc:  # pragma: no cover
        logger.error("Could not create Anthropic client: %s", exc)
        return None


def create_app() -> Flask:
    """Application factory."""
    app = Flask(__name__)
    app.config.from_object(Config)

    # Ensure storage directories exist
    for d in (
        app.config.get("MEMOIR_DIR"),
        app.config.get("QR_DIR"),
    ):
        try:
            os.makedirs(d, exist_ok=True)
        except Exception as exc:
            logger.warning("Could not create %s: %s", d, exc)

    # Database
    db.init_app(app)
    with app.app_context():
        db.create_all()

    # Services
    anthropic_client = _make_anthropic(app.config.get("ANTHROPIC_API_KEY", ""))
    band_manager = BandRoomManager(
        api_key=app.config.get("BAND_API_KEY", ""),
        room_id=app.config.get("BAND_ROOM_ID", ""),
    )
    history_lookup = HistoryLookup()
    pdf_generator = MemoirPDFGenerator()
    qr_generator = QRGenerator()

    # Agents
    interviewer = InterviewerAgent(anthropic_client, band_manager)
    organiser = OrganiserAgent(anthropic_client, band_manager)
    factchecker = FactCheckerAgent(anthropic_client, band_manager, history_lookup)
    storyteller = StorytellerAgent(anthropic_client, band_manager)
    legacybuilder = LegacyBuilderAgent(
        anthropic_client,
        band_manager,
        pdf_generator,
        qr_generator,
        db,
        base_url=app.config.get("BASE_URL", "http://localhost:5000"),
        memoir_dir=app.config.get("MEMOIR_DIR", "static/memoirs"),
        qr_dir=app.config.get("QR_DIR", "static/qrcodes"),
    )

    # Make services accessible to blueprints via app context
    app.interviewer = interviewer
    app.organiser = organiser
    app.factchecker = factchecker
    app.storyteller = storyteller
    app.legacybuilder = legacybuilder
    app.band = band_manager

    # Register blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(session_bp)
    app.register_blueprint(memoir_bp)

    # Seed demo memoir if DEMO_MODE is on
    if app.config.get("DEMO_MODE"):
        with app.app_context():
            try:
                from routes.memoir import _seed_demo_memoir

                _seed_demo_memoir()
            except Exception as exc:  # pragma: no cover
                logger.warning("Demo seed failed: %s", exc)

    # Friendly error handlers
    @app.errorhandler(404)
    def not_found(e):
        from flask import render_template

        return (
            render_template(
                "base.html",
                content=(
                    "<section class='how'><h2 class='section-title'>Not found</h2>"
                    "<p style='text-align:center;'>The page you are looking for "
                    "could not be found.</p></section>"
                ),
            ),
            404,
        )

    @app.errorhandler(500)
    def server_error(e):
        from flask import render_template

        logger.exception("Server error: %s", e)
        return (
            render_template(
                "base.html",
                content=(
                    "<section class='how'><h2 class='section-title'>"
                    "Something went wrong</h2>"
                    "<p style='text-align:center;'>Please try again in a moment. "
                    "Your story is safe with us.</p></section>"
                ),
            ),
            500,
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
