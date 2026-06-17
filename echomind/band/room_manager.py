"""Band coordination layer for EchoMind.

Each agent talks to the others through a Band chat room using
@mentions. The BandRoomManager wraps the REST API and falls back to a
local transcript log when Band is unavailable, so the pipeline can
continue running offline.
"""

import json
import logging
import os
from datetime import datetime
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

BAND_API_BASE = "https://api.band.ai/v1"
LOCAL_LOG = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "band_transcript.log",
)


class BandRoomManager:
    """Post messages to a Band room, with offline fallback."""

    def __init__(self, api_key: str, room_id: str, log_path: str = LOCAL_LOG):
        self.api_key = (api_key or "").strip()
        self.room_id = (room_id or "").strip()
        self.log_path = log_path
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update(
                {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
            )
        # Ensure the local log file exists so we can append later
        try:
            os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
            if not os.path.exists(self.log_path):
                with open(self.log_path, "a", encoding="utf-8"):
                    pass
        except Exception:  # pragma: no cover
            pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def post_message(
        self, content: str, agent_name: Optional[str] = None
    ) -> Optional[str]:
        """Post a message to the Band room.

        If `agent_name` is provided, prefixes content with "@agent: ".
        Returns the message ID on success, None on failure (offline log
        is always written).
        """
        prefix = f"@{agent_name}: " if agent_name else ""
        body = f"{prefix}{content}"
        # Always log locally first
        self._log("OUT", body)

        if not self.api_key or not self.room_id:
            return None

        try:
            resp = self.session.post(
                f"{BAND_API_BASE}/messages",
                json={"room_id": self.room_id, "content": body},
                timeout=5,
            )
            if resp.status_code in (200, 201):
                data = resp.json() if resp.content else {}
                return str(data.get("id") or "")
            logger.warning(
                "Band post_message returned %s: %s",
                resp.status_code,
                resp.text[:200],
            )
            return None
        except Exception as exc:  # pragma: no cover
            logger.warning("Band post_message failed: %s", exc)
            return None

    def mention_agent(
        self, from_agent: str, to_agent: str, content: str
    ) -> Optional[str]:
        """Post a message that @mentions the next agent in the pipeline."""
        body = f"@{to_agent} {content}"
        return self.post_message(body, agent_name=from_agent)

    def get_room_transcript(self, limit: int = 100) -> List[dict]:
        """Fetch recent messages from the Band room."""
        if not self.api_key or not self.room_id:
            return self._read_local_log(limit)
        try:
            resp = self.session.get(
                f"{BAND_API_BASE}/messages",
                params={"room_id": self.room_id, "limit": limit},
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return data
                if isinstance(data, dict) and "messages" in data:
                    return data["messages"]
        except Exception as exc:  # pragma: no cover
            logger.warning("Band get_room_transcript failed: %s", exc)
        return self._read_local_log(limit)

    def notify_family(self, session_id: str, share_url: str, subject_name: str = "") -> Optional[str]:
        """Post a final message announcing the memoir is ready."""
        name = subject_name or "your loved one"
        content = (
            f"The memoir for {name} is ready. "
            f"Share with family: {share_url} (session: {session_id})"
        )
        return self.post_message(content, agent_name="legacybuilder")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _log(self, direction: str, body: str) -> None:
        """Append a message to the local fallback log."""
        try:
            ts = datetime.utcnow().isoformat()
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(f"[{ts}] {direction} {body}\n")
        except Exception:  # pragma: no cover
            pass

    def _read_local_log(self, limit: int) -> List[dict]:
        """Read the last `limit` lines of the local log and return as dicts."""
        try:
            if not os.path.exists(self.log_path):
                return []
            with open(self.log_path, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
        except Exception:  # pragma: no cover
            return []
        messages = []
        for line in lines[-limit:]:
            line = line.rstrip("\n")
            if not line:
                continue
            # Format: [ts] OUT body
            try:
                ts, rest = line.split("] ", 1)
            except ValueError:
                continue
            messages.append(
                {
                    "timestamp": ts.lstrip("["),
                    "content": rest,
                }
            )
        return messages
