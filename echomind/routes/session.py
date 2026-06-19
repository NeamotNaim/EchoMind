"""Session routes — the live interview and the build-memoir API.

The interview is driven by the Flask app calling Gemini directly (not via
Band). When the interview completes, the transcript is posted to the
Band room and the 5 standalone agents take over.

The `/api/build-memoir` endpoint is the contract the LegacyBuilder Band
agent calls to assemble the final PDF.
"""

import json
import logging
import os
import re
import uuid
from typing import Dict, List, Optional

from flask import (
    Blueprint, current_app, jsonify, render_template, request,
)

from models.database import Session, Memoir, db
from utils.gemini_client import GeminiClient, follow_up_question
from utils.pdf_generator import MemoirPDFGenerator
from utils.qr_generator import QRGenerator

logger = logging.getLogger(__name__)
session_bp = Blueprint("session", __name__)


# The 12 interview questions. Loaded once at import time.
INTERVIEW_QUESTIONS: List[str] = [
    "Let's start at the very beginning. Where were you born, and what do you remember most about the place you grew up?",
    "Tell me about your parents. What kind of people were they?",
    "What's your earliest memory — the very first thing you can remember?",
    "What were you like as a child? Were you adventurous, shy, curious?",
    "Tell me about school. Was there a teacher who changed your life, or a moment that stands out?",
    "When did you first fall in love? Tell me about that person.",
    "What was the hardest thing you ever went through? How did you survive it?",
    "What are you most proud of in your life?",
    "If you could relive one single day of your life, which day would it be and why?",
    "What do you wish you had known at 20 that you know now?",
    "What do you want the people you love to remember about you?",
    "Is there anything you've never told anyone that you'd like to say now?",
]

INTERVIEWER_SYSTEM_PROMPT = (
    "You are a compassionate, skilled oral historian conducting a "
    "life-story interview. Your job is to help elderly or dying people "
    "tell the stories that matter most to them before it is too late. "
    "Ask one question at a time. Never rush. Use simple, direct "
    "language. Never sound clinical or cold."
)

MIN_EXCHANGES = 6
TARGET_EXCHANGES = 15


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _load_conversation(sess: Session) -> List[Dict[str, str]]:
    """Parse the conversation_json column into a list of message dicts."""
    if not sess.conversation_json:
        return []
    try:
        return json.loads(sess.conversation_json)
    except json.JSONDecodeError:
        return []


def _save_conversation(sess: Session, history: List[Dict[str, str]]) -> None:
    """Persist the conversation history to the Session row."""
    sess.conversation_json = json.dumps(history, ensure_ascii=False)
    db.session.commit()


def _get_gemini() -> GeminiClient:
    """Get the shared Gemini client from app config."""
    client = getattr(current_app, "gemini", None)
    if client is None:
        client = GeminiClient(
            api_key=current_app.config.get("GOOGLE_API_KEY", "")
        )
        current_app.gemini = client
    return client


def _compile_transcript(history: List[Dict[str, str]], subject_name: str) -> str:
    """Build a readable transcript string from conversation history."""
    lines = [f"Life Story Interview — {subject_name}", "=" * 50, ""]
    for m in history:
        role = m.get("role", "")
        content = (m.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            lines.append(f"Subject: {content}")
        elif role == "assistant":
            lines.append(f"Interviewer: {content}")
        else:
            lines.append(f"{role.capitalize()}: {content}")
        lines.append("")
    return "\n".join(lines)


def _subject_signals_finish(answer: str) -> bool:
    """Heuristic: if the subject seems to be wrapping up, finish early."""
    if not answer:
        return False
    text = answer.lower().strip()
    triggers = [
        "that's all", "i think that's it", "i'm done", "no more",
        "that's everything", "i've told you everything", "i'm finished",
    ]
    return any(t in text for t in triggers)


# ----------------------------------------------------------------------
# Pages
# ----------------------------------------------------------------------
@session_bp.route("/session/<session_id>")
def show_session(session_id: str):
    """Render the interview page for a session."""
    sess = Session.query.get(session_id)
    if sess is None:
        return render_template("base.html", content="<p>Session not found.</p>"), 404

    history = _load_conversation(sess)

    # Seed the first interviewer question if the conversation is empty
    if not history:
        first_q = INTERVIEW_QUESTIONS[0]
        history.append({"role": "assistant", "content": first_q})
        _save_conversation(sess, history)

    return render_template("session.html", session=sess, history=history)


@session_bp.route("/session/<session_id>/waiting")
def waiting(session_id: str):
    """Render the waiting/processing screen."""
    sess = Session.query.get(session_id)
    if sess is None:
        return render_template("base.html", content="<p>Session not found.</p>"), 404
    return render_template("waiting.html", session=sess)


# ----------------------------------------------------------------------
# Conversation
# ----------------------------------------------------------------------
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

    history = _load_conversation(sess)
    history.append({"role": "user", "content": user_msg})
    exchanges = sum(1 for m in history if m.get("role") == "user")
    question_index = exchanges  # 0-based count of questions asked

    # Decide completion
    if exchanges >= TARGET_EXCHANGES or (
        exchanges >= MIN_EXCHANGES and _subject_signals_finish(user_msg)
    ):
        closing = (
            "Thank you for sharing all of this with me. Your stories are "
            "going to be preserved beautifully for your family."
        )
        history.append({"role": "assistant", "content": closing})
        _save_conversation(sess, history)
        _post_transcript_to_band(sess, history)
        return jsonify({"question": closing, "complete": True})

    # Pick the next question (scripted or via Gemini)
    gemini = _get_gemini()
    next_q = follow_up_question(
        gemini, INTERVIEW_QUESTIONS, history, question_index
    )
    history.append({"role": "assistant", "content": next_q})
    _save_conversation(sess, history)

    return jsonify({"question": next_q, "complete": False})


@session_bp.route("/session/<session_id>/status")
def session_status(session_id: str):
    """Return JSON with the current session status and share token if ready."""
    sess = Session.query.get(session_id)
    if sess is None:
        return jsonify({"error": "Session not found"}), 404

    data: Dict = {"status": sess.status, "session_id": sess.id}
    if sess.memoir is not None:
        data["share_url"] = f"/memoir/{sess.memoir.share_token}"
        data["share_token"] = sess.memoir.share_token
    # Seconds since the session was last updated — used by the waiting page
    # to decide whether to show a "stuck, please retry" hint.
    try:
        from datetime import datetime
        if sess.updated_at:
            if isinstance(sess.updated_at, str):
                last = datetime.fromisoformat(sess.updated_at)
            else:
                last = sess.updated_at
            data["elapsed"] = max(0, int((datetime.utcnow() - last).total_seconds()))
    except Exception:
        pass
    return jsonify(data)


@session_bp.route("/session/<session_id>/memoir-token")
def memoir_token(session_id: str):
    """Convenience endpoint the waiting page polls for the share URL."""
    sess = Session.query.get(session_id)
    if sess is None or sess.memoir is None:
        return jsonify({"status": sess.status if sess else "unknown"})
    return jsonify(
        {
            "status": sess.status,
            "share_token": sess.memoir.share_token,
            "share_url": f"/memoir/{sess.memoir.share_token}",
        }
    )


# ----------------------------------------------------------------------
# Build memoir API (called by the LegacyBuilder Band agent)
# ----------------------------------------------------------------------
@session_bp.route("/api/build-memoir", methods=["POST"])
def build_memoir_api():
    """Receive chapters JSON, build PDF + QR + share URL, persist to DB.

    Body:
        {
          "subject_name":  str,
          "chapters_json": str  # JSON string of {chapter: text}
        }

    Returns:
        {
          "share_url": "/memoir/<token>",
          "share_token": "...",
          "pdf_path":  "..."
        }
    """
    payload = request.get_json(silent=True) or {}
    subject_name = (payload.get("subject_name") or "").strip() or "Unknown"
    chapters_json_raw = payload.get("chapters_json") or "{}"

    # chapters_json may already be a dict or a JSON string
    if isinstance(chapters_json_raw, dict):
        chapters = chapters_json_raw
    else:
        try:
            chapters = json.loads(chapters_json_raw)
        except json.JSONDecodeError:
            logger.warning("build-memoir: chapters_json not valid JSON, wrapping")
            chapters = {"Memoir": str(chapters_json_raw)}

    if not chapters or not isinstance(chapters, dict):
        return jsonify({"error": "chapters_json must be a non-empty object"}), 400

    # Normalise values to strings
    normalised: Dict[str, str] = {}
    for k, v in chapters.items():
        if isinstance(v, str):
            normalised[str(k)] = v
        elif isinstance(v, list):
            normalised[str(k)] = "\n\n".join(str(x) for x in v if x)
        else:
            normalised[str(k)] = str(v)

    # Persist a Session + Memoir row so the share link can look them up.
    # We associate the memoir with whatever session matches subject_name
    # most recently in `processing` state, or create a synthetic one.
    sess = (
        Session.query.filter_by(subject_name=subject_name, status="processing")
        .order_by(Session.updated_at.desc())
        .first()
    )
    if sess is None:
        sess = (
            Session.query.filter_by(subject_name=subject_name)
            .order_by(Session.updated_at.desc())
            .first()
        )
    if sess is None:
        sess = Session(
            subject_name=subject_name,
            status="processing",
            conversation_json=json.dumps([]),
        )
        db.session.add(sess)
        db.session.commit()

    share_token = uuid.uuid4().hex
    share_url_path = f"/memoir/{share_token}"
    base_url = current_app.config.get("BASE_URL", "http://localhost:5000").rstrip("/")
    share_url_full = f"{base_url}{share_url_path}"

    memoir_dir = current_app.config.get("MEMOIR_DIR", "static/memoirs")
    qr_dir = current_app.config.get("QR_DIR", "static/qrcodes")
    os.makedirs(memoir_dir, exist_ok=True)
    os.makedirs(qr_dir, exist_ok=True)

    pdf_path = os.path.join(memoir_dir, f"{sess.id}.pdf")
    qr_path = os.path.join(qr_dir, f"{sess.id}.png")

    # Generate PDF
    try:
        MemoirPDFGenerator().generate(
            subject_name, sess.subject_birth_year, normalised, pdf_path
        )
    except Exception as exc:
        logger.exception("PDF generation failed for session %s: %s", sess.id, exc)
        return jsonify({"error": f"PDF generation failed: {exc}"}), 500

    # Generate QR
    try:
        QRGenerator().generate(share_url_full, qr_path)
    except Exception as exc:
        logger.warning("QR generation failed (continuing): %s", exc)
        qr_path = ""

    # Save memoir row
    try:
        memoir = Memoir.query.filter_by(session_id=sess.id).first()
        if memoir is None:
            memoir = Memoir(session_id=sess.id)
        memoir.chapters_json = json.dumps(normalised, ensure_ascii=False)
        memoir.pdf_path = pdf_path or None
        memoir.qr_path = qr_path or None
        memoir.share_token = share_token
        db.session.add(memoir)

        sess.status = "complete"
        db.session.commit()
    except Exception as exc:
        logger.exception("DB save failed: %s", exc)
        db.session.rollback()
        return jsonify({"error": f"DB save failed: {exc}"}), 500

    return jsonify(
        {
            "share_url": share_url_path,
            "share_token": share_token,
            "pdf_path": pdf_path,
        }
    )


# ----------------------------------------------------------------------
# Band handoff
# ----------------------------------------------------------------------
def _post_transcript_to_band(sess: Session, history: List[Dict[str, str]]) -> None:
    """Mark the session as processing and notify the Band room.

    Posts to `POST /api/v1/agent/chats/<room_id>/messages` using the
    Interviewer agent's own credentials (it is the first participant in
    the room by design) so the message lands in the agent room, and
    mentions the Organiser so the Organiser's polling loop picks it up
    and starts the pipeline.

    Auth: the Band platform uses the `X-API-Key` header (NOT
    `Authorization: Bearer`).
    """
    import json as _json
    import yaml as _yaml  # type: ignore
    import requests as _requests

    sess.status = "processing"
    db.session.commit()

    transcript = _compile_transcript(history, sess.subject_name)

    rest_base = current_app.config.get(
        "BAND_REST_URL", "https://app.band.ai/"
    ).rstrip("/")
    room_id = os.getenv("BAND_ROOM_ID", "").strip()

    if not room_id:
        logger.error(
            "BAND_ROOM_ID is not set in .env — cannot post to Band. "
            "Get the room UUID from any agent log line 'chat_room:<UUID>'."
        )
        return

    # Load two agent credentials:
    #  - sender_key/agent_id: a room member we use to POST the message
    #    (any of Organiser/FactChecker/Storyteller/LegacyBuilder works,
    #    but NOT the Organiser mentioning itself — Band rejects that
    #    with `cannot_mention_self` 422). We use the FactChecker.
    #  - organiser_agent_id: the @mention target that triggers the
    #    pipeline (this is the @organiser tag the prompt looks for).
    sender_api_key = None
    sender_agent_id = None
    organiser_agent_id = None
    try:
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "agent_config.yaml",
        )
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as fh:
                data = _yaml.safe_load(fh) or {}
            # Use FactChecker as sender (room member, not the target)
            sender_api_key = (
                (data.get("factchecker") or {}).get("api_key") or ""
            ).strip()
            sender_agent_id = (
                (data.get("factchecker") or {}).get("agent_id") or ""
            ).strip()
            organiser_agent_id = (
                (data.get("organiser") or {}).get("agent_id") or ""
            ).strip()
    except Exception as exc:
        logger.warning("Could not read agent_config.yaml: %s", exc)

    if not sender_api_key or not organiser_agent_id:
        logger.error(
            "FactChecker api_key or Organiser agent_id missing in "
            "agent_config.yaml — cannot post to Band."
        )
        return

    # Ensure every agent in agent_config.yaml is a participant of the
    # Band room. Without this, @mentions to a missing agent return
    # 422 mentioned_participant_not_in_room. We use the sender's
    # (FactChecker's) key — it's a guaranteed room member.
    try:
        import yaml as _yaml2  # type: ignore
        _cfg_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "agent_config.yaml",
        )
        if os.path.exists(_cfg_path):
            with open(_cfg_path, "r", encoding="utf-8") as _fh:
                _data = _yaml2.safe_load(_fh) or {}
            for _name, _entry in _data.items():
                _aid = (_entry.get("agent_id") or "").strip()
                if not _aid:
                    continue
                _resp = _requests.post(
                    f"{rest_base}/api/v1/agent/chats/{room_id}/participants",
                    headers={
                        "Content-Type": "application/json",
                        "X-API-Key": sender_api_key,
                    },
                    json={
                        "participant": {
                            "participant_id": _aid,
                            "role": "member",
                        }
                    },
                    timeout=5,
                )
                # 201 = added, 4xx (already in room) = fine
                if _resp.status_code not in (200, 201):
                    logger.debug(
                        "Ensure %s in room: %s %s",
                        _name, _resp.status_code, _resp.text[:120],
                    )
    except Exception as exc:
        logger.warning("Could not ensure room participants: %s", exc)

    content = (
        f"New interview complete for {sess.subject_name}. "
        f"Session: {sess.id}\n\nFull transcript:\n\n{transcript}"
    )

    url = f"{rest_base}/api/v1/agent/chats/{room_id}/messages"
    body = {
        "message": {
            "content": content,
            "mentions": [{"id": organiser_agent_id}],
        }
    }
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": sender_api_key,
    }

    try:
        resp = _requests.post(url, json=body, headers=headers, timeout=10)
        if resp.status_code >= 400:
            logger.error(
                "Band transcript post returned %s: %s",
                resp.status_code, resp.text[:300],
            )
            return
        logger.info(
            "Posted transcript to Band room %s for %s (session %s, status %s)",
            room_id, sess.subject_name, sess.id, resp.status_code,
        )
    except Exception as exc:
        logger.error("Band transcript post failed: %s", exc)