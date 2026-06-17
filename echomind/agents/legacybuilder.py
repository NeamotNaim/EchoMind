"""@legacybuilder agent — assembles the final PDF memoir and share link."""

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "You are the final stage of a memoir production pipeline. You "
    "receive completed memoir chapters and assemble them into a "
    "professional, beautiful PDF document. Generate a cover page with "
    "the person's name and lifespan, a table of contents, and all "
    "chapters with consistent, elegant formatting. Output the PDF file "
    "path and the shareable URL to the Band room. The family has been "
    "waiting for this."
)


class LegacyBuilderAgent:
    """Compiles the finished memoir and produces a shareable link."""

    def __init__(
        self,
        anthropic_client,
        band_manager,
        pdf_generator,
        qr_generator,
        db,
        base_url: str = "http://localhost:5000",
        memoir_dir: str = "static/memoirs",
        qr_dir: str = "static/qrcodes",
    ):
        self.client = anthropic_client
        self.band = band_manager
        self.pdf = pdf_generator
        self.qr = qr_generator
        self.db = db
        self.base_url = base_url.rstrip("/")
        self.memoir_dir = memoir_dir
        self.qr_dir = qr_dir
        self.system_prompt = SYSTEM_PROMPT

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def build_memoir(
        self,
        chapters: Dict[str, str],
        session_id: str,
        subject_name: str,
        birth_year: Optional[int] = None,
    ) -> Dict[str, str]:
        """Generate the PDF, QR code, share URL, and persist to the DB."""
        share_token = uuid.uuid4().hex
        share_url = f"{self.base_url}/memoir/{share_token}"

        # Ensure output dirs exist
        for d in (self.memoir_dir, self.qr_dir):
            try:
                os.makedirs(d, exist_ok=True)
            except Exception as exc:  # pragma: no cover
                logger.warning("Could not create dir %s: %s", d, exc)

        pdf_path = os.path.join(self.memoir_dir, f"{session_id}.pdf")
        qr_path = os.path.join(self.qr_dir, f"{session_id}.png")

        # 1. Generate the PDF
        try:
            self.pdf.generate(subject_name, birth_year, chapters, pdf_path)
        except Exception as exc:
            logger.error("PDF generation failed: %s", exc)
            pdf_path = ""

        # 2. Generate the QR code
        try:
            if share_url:
                self.qr.generate(share_url, qr_path)
        except Exception as exc:
            logger.error("QR generation failed: %s", exc)
            qr_path = ""

        # 3. Persist to the database
        from models.database import Memoir, Session  # local import to avoid cycle

        try:
            memoir = Memoir.query.filter_by(session_id=session_id).first()
            if memoir is None:
                memoir = Memoir(session_id=session_id)
            memoir.chapters_json = json.dumps(chapters, ensure_ascii=False)
            memoir.pdf_path = pdf_path or None
            memoir.qr_path = qr_path or None
            memoir.share_token = share_token
            self.db.session.add(memoir)
            self.db.session.commit()

            # Update session status
            sess = Session.query.get(session_id)
            if sess is not None:
                sess.status = "complete"
                self.db.session.commit()
        except SQLAlchemyError as exc:  # pragma: no cover
            logger.error("DB save failed: %s", exc)
            self.db.session.rollback()

        # 4. Announce in Band
        try:
            self.band.notify_family(session_id, share_url, subject_name)
        except Exception as exc:  # pragma: no cover
            logger.warning("Band notify_family failed: %s", exc)

        return {
            "pdf_path": pdf_path,
            "qr_path": qr_path,
            "share_url": share_url,
            "share_token": share_token,
        }

    def handle_band_mention(
        self,
        message_content: str,
        session_id: str,
        subject_name: str = "the subject",
        birth_year: Optional[int] = None,
    ) -> Dict[str, str]:
        """Called when @legacybuilder is mentioned in Band."""
        body = message_content
        # Strip leading mention
        import re

        body = re.sub(r"^@legacybuilder\s*", "", body.strip())
        # Try to extract a JSON chapters block
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", body, re.DOTALL)
        json_text = fence.group(1) if fence else None
        chapters: Dict[str, str] = {}
        if json_text:
            try:
                data = json.loads(json_text)
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, str):
                            chapters[str(k)] = v
            except json.JSONDecodeError:
                chapters = {}
        if not chapters:
            # Fallback: treat the whole body as a single chapter
            chapters = {"Memoir": body.strip()}
        return self.build_memoir(chapters, session_id, subject_name, birth_year)
