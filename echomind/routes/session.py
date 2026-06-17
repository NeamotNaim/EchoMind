"""Session routes — the live interview and the waiting room."""

import json
import logging
import threading
from typing import List, Dict

from flask import (
    Blueprint, current_app, jsonify, redirect, render_template, request,
    url_for,
)

from models.database import Message, Session, db

logger = logging.getLogger(__name__)
session_bp = Blueprint("session", __name__)


# ----------------------------------------------------------------------
# Pipeline orchestration
# ----------------------------------------------------------------------
def _compile_transcript(messages: List[Message]) -> str:
    """Build a readable transcript string from the DB messages."""
    lines: List[str] = []
    for m in messages:
        role = m.role
        content = (m.content or "").strip()
        if not content:
            continue
        if role == "user":
            lines.append(f"Subject: {content}")
        elif role == "assistant":
            lines.append(f"Interviewer: {content}")
        else:
            label = m.agent_name or role
            lines.append(f"{label.capitalize()}: {content}")
    return "\n".join(lines)


def run_pipeline(app, session_id: str) -> None:
    """Run the full 5-agent pipeline. Designed to be launched in a thread."""
    with app.app_context():
        sess = Session.query.get(session_id)
        if sess is None:
            logger.error("Pipeline: session %s not found", session_id)
            return
        # Guard against double-fire: only run if the session is still
        # in the 'active' state. Once a pipeline has taken over, status
        # flips to 'processing' and any later caller will bail out.
        if sess.status != "active":
            logger.info(
                "Pipeline: session %s already %s — skipping",
                session_id, sess.status,
            )
            return
        sess.status = "processing"
        db.session.commit()

        try:
            messages = (
                Message.query.filter_by(session_id=session_id)
                .order_by(Message.created_at.asc())
                .all()
            )
            transcript = _compile_transcript(messages)

            interviewer = app.interviewer
            organiser = app.organiser
            factchecker = app.factchecker
            storyteller = app.storyteller
            legacybuilder = app.legacybuilder
            band = app.band

            # Agent 1 → 2
            try:
                band.mention_agent(
                    "interviewer", "organiser",
                    f"Full transcript ready for organisation:\n\n{transcript}",
                )
            except Exception as exc:
                logger.warning("Band mention to organiser failed: %s", exc)
            chapters = organiser.organise_transcript(transcript, session_id)

            # Agent 2 → 3
            try:
                band.mention_agent(
                    "organiser", "factchecker",
                    f"Chapters organised. Please enrich with historical context:\n\n{json.dumps(chapters)}",
                )
            except Exception as exc:
                logger.warning("Band mention to factchecker failed: %s", exc)
            enriched = factchecker.enrich_chapters(
                chapters, sess.subject_birth_year
            )

            # Agent 3 → 4
            try:
                band.mention_agent(
                    "factchecker", "storyteller",
                    f"Memories enriched. Please write the memoir:\n\n{json.dumps(enriched)}",
                )
            except Exception as exc:
                logger.warning("Band mention to storyteller failed: %s", exc)
            written = storyteller.write_all_chapters(
                enriched, sess.subject_name, session_id
            )

            # Agent 4 → 5
            try:
                band.mention_agent(
                    "storyteller", "legacybuilder",
                    f"Chapters written. Please assemble the PDF:\n\n{json.dumps(written)}",
                )
            except Exception as exc:
                logger.warning("Band mention to legacybuilder failed: %s", exc)
            result = legacybuilder.build_memoir(
                written, session_id, sess.subject_name, sess.subject_birth_year
            )

            logger.info("Pipeline complete for session %s: %s", session_id, result)

        except Exception as exc:
            logger.exception("Pipeline failed for session %s: %s", session_id, exc)
            try:
                sess.status = "error"
                db.session.commit()
            except Exception:
                db.session.rollback()


# ----------------------------------------------------------------------
# HTTP endpoints
# ----------------------------------------------------------------------
@session_bp.route("/session/<session_id>")
def show_session(session_id: str):
    """Render the interview page for a session."""
    sess = Session.query.get(session_id)
    if sess is None:
        return render_template("base.html", content="<p>Session not found.</p>"), 404

    # Seed the conversation with the interviewer's first question
    first_q = current_app.interviewer.questions[0]
    history: List[Dict[str, str]] = [
        {"role": "assistant", "content": first_q},
    ]

    # If there are already messages (user resumed), load them
    existing = (
        Message.query.filter_by(session_id=session_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    if existing:
        history = [{"role": m.role, "content": m.content} for m in existing]
    else:
        # Save the first question as a Message
        db.session.add(
            Message(
                session_id=session_id,
                role="assistant",
                agent_name="interviewer",
                content=first_q,
            )
        )
        db.session.commit()

    return render_template(
        "session.html",
        session=sess,
        history=history,
    )


@session_bp.route("/session/<session_id>/message", methods=["POST"])
def post_message(session_id: str):
    """Receive a user answer, return the next question."""
    sess = Session.query.get(session_id)
    if sess is None:
        return jsonify({"error": "Session not found"}), 404

    payload = request.get_json(silent=True) or {}
    user_msg = (payload.get("message") or request.form.get("message") or "").strip()
    if not user_msg:
        return jsonify({"error": "Empty message"}), 400

    interviewer = current_app.interviewer

    # Build current history from DB
    msgs = (
        Message.query.filter_by(session_id=session_id)
        .order_by(Message.created_at.asc())
        .all()
    )
    history: List[Dict[str, str]] = [
        {"role": m.role, "content": m.content} for m in msgs
    ]

    # Save the user's message
    db.session.add(
        Message(session_id=session_id, role="user", content=user_msg)
    )
    db.session.commit()

    # Process
    result = interviewer.process_answer(user_msg, history, session_id)

    # Save the assistant's reply
    db.session.add(
        Message(
            session_id=session_id,
            role="assistant",
            agent_name="interviewer",
            content=result.get("question", ""),
        )
    )
    db.session.commit()

    # Fire pipeline if session is complete
    if result.get("session_complete"):
        try:
            app_obj = current_app._get_current_object()
            t = threading.Thread(
                target=run_pipeline, args=(app_obj, session_id), daemon=True
            )
            t.start()
        except Exception as exc:
            logger.error("Could not start pipeline thread: %s", exc)

    return jsonify(
        {
            "question": result.get("question", ""),
            "complete": bool(result.get("session_complete") or result.get("complete")),
        }
    )


@session_bp.route("/session/<session_id>/status")
def session_status(session_id: str):
    """Return JSON with the current session status and share link if ready."""
    sess = Session.query.get(session_id)
    if sess is None:
        return jsonify({"error": "Session not found"}), 404

    data: Dict = {"status": sess.status, "session_id": sess.id}
    if sess.memoir is not None:
        data["share_url"] = f"/memoir/{sess.memoir.share_token}"
        data["share_token"] = sess.memoir.share_token
    return jsonify(data)


@session_bp.route("/session/<session_id>/waiting")
def waiting(session_id: str):
    """Render the waiting/processing screen."""
    sess = Session.query.get(session_id)
    if sess is None:
        return render_template("base.html", content="<p>Session not found.</p>"), 404
    return render_template("waiting.html", session=sess)
