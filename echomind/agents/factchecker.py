"""@factchecker agent — enriches memories with historical context."""

import json
import logging
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "You are a historical fact-checker and contextualiser for a life "
    "memoir project. You receive structured memory data and enrich each "
    "memory with accurate historical context from the period described. "
    "Use Wikipedia and DuckDuckGo to find real events, cultural moments, "
    "and historical facts relevant to the dates and places mentioned. "
    "Never contradict or edit the person's memory — only add surrounding "
    "historical context to help readers understand the world the person "
    "lived in. Output enriched JSON and mention @storyteller."
)


YEAR_RE = re.compile(r"\b(1[5-9]\d{2}|20\d{2})\b")


class FactCheckerAgent:
    """Adds a short historical context note to each memory."""

    def __init__(self, anthropic_client, band_manager, history_lookup):
        self.client = anthropic_client
        self.band = band_manager
        self.history = history_lookup
        self.system_prompt = SYSTEM_PROMPT

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def enrich_chapters(
        self,
        chapters_dict: Dict[str, List[str]],
        subject_birth_year: Optional[int] = None,
    ) -> Dict[str, List[Dict[str, str]]]:
        """Return chapters where each memory is enriched with context."""
        enriched: Dict[str, List[Dict[str, str]]] = {}
        for chapter_name, memories in chapters_dict.items():
            enriched_memories: List[Dict[str, str]] = []
            for memory in memories or []:
                try:
                    enriched_memories.append(
                        self._enrich_one(memory, subject_birth_year)
                    )
                except Exception as exc:  # pragma: no cover
                    logger.warning("Enrichment failed for memory: %s", exc)
                    enriched_memories.append(
                        {
                            "original": memory,
                            "context": "",
                            "year": None,
                        }
                    )
            if enriched_memories:
                enriched[chapter_name] = enriched_memories

        # Post to Band and @mention @storyteller
        try:
            payload = json.dumps(enriched, ensure_ascii=False, indent=2)
            msg = (
                "Memories enriched with historical context. Ready for writing.\n\n"
                f"```json\n{payload}\n```\n\n"
                "@storyteller please turn these memories into memoir chapters."
            )
            self.band.mention_agent("factchecker", "storyteller", msg)
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to post enriched chapters to Band: %s", exc)

        return enriched

    def handle_band_mention(
        self, message_content: str, session_id: str
    ) -> Dict[str, List[Dict[str, str]]]:
        """Called when @factchecker is mentioned in Band."""
        body = re.sub(r"^@factchecker\s*", "", message_content.strip())
        chapters = self._parse_chapters_from_message(body)
        return self.enrich_chapters(chapters)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _enrich_one(
        self, memory: str, birth_year: Optional[int]
    ) -> Dict[str, Optional[str]]:
        """Enrich a single memory string with historical context."""
        # First try to extract a year from the memory text
        match = YEAR_RE.search(memory or "")
        year = int(match.group(1)) if match else None

        # If no year in text, fall back to a year derived from birth_year
        if year is None and birth_year:
            # Use a default of "21" — the year they turned 21, a common reference
            candidate = birth_year + 21
            if 1850 <= candidate <= 2100:
                year = candidate

        context = ""
        if year is not None:
            try:
                context = self.history.enrich_memory(memory, year=year).get(
                    "context", ""
                )
            except Exception as exc:  # pragma: no cover
                logger.debug("History lookup failed in enrich_one: %s", exc)
                context = ""

        # If Claude is available, try to generate a richer note that uses
        # the context but reads like a memoir footnote. If Claude fails or
        # is unavailable, fall back to the raw context string.
        note = context
        if self.client and context:
            try:
                note = self._claude_footnote(memory, year, context)
            except Exception as exc:  # pragma: no cover
                logger.debug("Claude footnote failed: %s", exc)

        return {
            "original": memory,
            "context": note or "",
            "year": year,
        }

    def _claude_footnote(self, memory: str, year: Optional[int], context: str) -> str:
        """Ask Claude to turn raw context into a 1–2 sentence footnote."""
        prompt = (
            "Turn the following historical context into a 1–2 sentence "
            "footnote that reads naturally beneath a memoir passage. "
            "Keep it warm and informative, never pedantic. "
            "Do not contradict the subject's memory.\n\n"
            f"Memory: {memory}\n"
            f"Year: {year}\n"
            f"Context: {context}\n\n"
            "Footnote:"
        )
        text = self._call_claude(prompt, max_tokens=180)
        return (text or context).strip()

    def _call_claude(self, user_prompt: str, max_tokens: int = 400) -> str:
        """Call Claude with retry."""
        if not self.client:
            raise RuntimeError("No Anthropic client")
        import time

        last_exc: Optional[Exception] = None
        for attempt in range(2):
            try:
                msg = self.client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=max_tokens,
                    system=self.system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                parts = []
                for block in msg.content or []:
                    if getattr(block, "type", None) == "text":
                        parts.append(block.text)
                return "\n".join(parts).strip()
            except Exception as exc:
                last_exc = exc
                logger.warning("Claude call failed (attempt %s): %s", attempt + 1, exc)
                time.sleep(2)
        raise last_exc or RuntimeError("Claude call failed")

    @staticmethod
    def _parse_chapters_from_message(body: str) -> Dict[str, List[str]]:
        """Extract a chapters dict from a Band message body."""
        # Find a JSON block
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", body, re.DOTALL)
        json_text = fence.group(1) if fence else None
        if not json_text:
            start = body.find("{")
            end = body.rfind("}")
            if start != -1 and end != -1 and end > start:
                json_text = body[start : end + 1]
        if not json_text:
            return {}
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError:
            return {}
        if not isinstance(data, dict):
            return {}
        result: Dict[str, List[str]] = {}
        for k, v in data.items():
            if isinstance(v, list):
                result[str(k)] = [str(x) for x in v if x]
            elif isinstance(v, str):
                result[str(k)] = [v]
        return result
