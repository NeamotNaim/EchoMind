"""SQLAlchemy database models for EchoMind.

Defines two tables:
- Session: a single interview / memoir production run
  (the conversation transcript is stored inline as JSON)
- Memoir:  final output (chapters + PDF + share token)
"""

import uuid
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def _uuid() -> str:
    """Return a fresh UUID4 string."""
    return str(uuid.uuid4())


class Session(db.Model):
    """A single memoir production session for one subject."""

    __tablename__ = "sessions"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    subject_name = db.Column(db.String(200), nullable=False)
    subject_birth_year = db.Column(db.Integer, nullable=True)
    subject_location = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="active")
    # status: active | processing | complete | error
    conversation_json = db.Column(db.Text, nullable=True)  # JSON string
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    memoir = db.relationship(
        "Memoir", backref="session", uselist=False, cascade="all, delete-orphan"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "subject_name": self.subject_name,
            "subject_birth_year": self.subject_birth_year,
            "subject_location": self.subject_location,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Memoir(db.Model):
    """Final memoir output for a session."""

    __tablename__ = "memoirs"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    session_id = db.Column(
        db.String(36), db.ForeignKey("sessions.id"), unique=True, nullable=False
    )
    chapters_json = db.Column(db.Text, nullable=False)  # JSON string of chapters
    pdf_path = db.Column(db.String(500), nullable=True)
    qr_path = db.Column(db.String(500), nullable=True)
    share_token = db.Column(db.String(64), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "pdf_path": self.pdf_path,
            "qr_path": self.qr_path,
            "share_token": self.share_token,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }