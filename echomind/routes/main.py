"""Main routes — landing page and start-session form."""

from datetime import datetime

from flask import (
    Blueprint, current_app, redirect, render_template, request, url_for
)

from models.database import Session, db

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    """Render the landing page."""
    return render_template("index.html", year=datetime.now().year)


@main_bp.route("/start", methods=["POST"])
def start_session():
    """Create a new Session row and redirect to its interview page."""
    subject_name = (request.form.get("subject_name") or "").strip()
    if not subject_name:
        subject_name = "My Loved One"

    birth_year_raw = (request.form.get("birth_year") or "").strip()
    birth_year: int | None = None
    if birth_year_raw.isdigit():
        year_int = int(birth_year_raw)
        if 1850 <= year_int <= datetime.now().year:
            birth_year = year_int

    location = (request.form.get("location") or "").strip() or None

    sess = Session(
        subject_name=subject_name,
        subject_birth_year=birth_year,
        subject_location=location,
        status="active",
    )
    db.session.add(sess)
    db.session.commit()

    # Greet in the Band room
    try:
        current_app.band.post_message(
            f"New interview starting for {subject_name} (session: {sess.id}).",
            agent_name="interviewer",
        )
    except Exception:
        pass

    return redirect(url_for("session.show_session", session_id=sess.id))
