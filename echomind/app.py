"""EchoMind Flask application factory.

The web app handles the interview UI and assembles the final PDF. The
five Band agents run as separate processes (`agents/run_*.py`) and
connect to Band via WebSocket. The LegacyBuilder agent calls our
`/api/build-memoir` endpoint to assemble the PDF.

Run locally:
    python app.py
"""

import logging
import os

from flask import Flask, render_template

from config import Config
from models.database import db

from routes.main import main_bp
from routes.session import session_bp
from routes.memoir import memoir_bp

from utils.gemini_client import GeminiClient


# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("echomind")


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

    # Shared Gemini client (used by the Flask-side interviewer)
    app.gemini = GeminiClient(api_key=app.config.get("GOOGLE_API_KEY", ""))

    # Register blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(session_bp)
    app.register_blueprint(memoir_bp)

    # Friendly error handlers
    @app.errorhandler(404)
    def not_found(e):
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
    port = int(os.getenv("FLASK_RUN_PORT", "5000"))
    app.run(debug=True, host="0.0.0.0", port=port)