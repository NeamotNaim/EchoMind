"""@storyteller agent — turns enriched memories into memoir prose."""

import json
import logging
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "You are a literary ghostwriter specialising in personal memoirs. "
    "You receive structured, historically-enriched life memories and "
    "transform them into beautifully written memoir chapters in the "
    "first person. Your job is to preserve the person's authentic voice "
    "while elevating the prose to be readable, moving, and worthy of a "
    "book. Keep specific details — names, places, objects — because "
    "specificity is what makes a memoir real. Write 300–600 words per "
    "chapter. When all chapters are written, post them to Band and "
    "mention @legacybuilder."
)


class StorytellerAgent:
    """Writes first-person prose chapters from enriched memories."""

    def __init__(self, anthropic_client, band_manager):
        self.client = anthropic_client
        self.band = band_manager
        self.system_prompt = SYSTEM_PROMPT

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def write_chapter(
        self,
        chapter_name: str,
        memories: List[Dict[str, str]],
        subject_name: str,
    ) -> str:
        """Write a single 300–600 word chapter."""
        # Try Claude first
        try:
            text = self._claude_chapter(chapter_name, memories, subject_name)
            if text and len(text.split()) >= 120:
                return text
        except Exception as exc:
            logger.warning("Claude chapter write failed: %s — using fallback", exc)

        # Heuristic fallback: stitch the memories into a simple narrative
        return self._fallback_chapter(chapter_name, memories, subject_name)

    def write_all_chapters(
        self,
        enriched_chapters: Dict[str, List[Dict[str, str]]],
        subject_name: str,
        session_id: str,
    ) -> Dict[str, str]:
        """Write prose for every chapter and post completion to Band."""
        if not enriched_chapters:
            logger.warning(
                "Storyteller: no enriched chapters to write for session %s",
                session_id,
            )
            return {}

        written: Dict[str, str] = {}
        for chapter_name, memories in enriched_chapters.items():
            try:
                written[chapter_name] = self.write_chapter(
                    chapter_name, memories, subject_name
                )
            except Exception as exc:  # pragma: no cover
                logger.error("Chapter %s failed: %s", chapter_name, exc)
                written[chapter_name] = self._fallback_chapter(
                    chapter_name, memories, subject_name
                )

        # Post to Band
        try:
            payload = json.dumps(written, ensure_ascii=False, indent=2)
            msg = (
                f"All {len(written)} chapters written. Ready for assembly.\n\n"
                f"```json\n{payload}\n```\n\n"
                "@legacybuilder please compile these into a PDF memoir."
            )
            self.band.mention_agent("storyteller", "legacybuilder", msg)
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to post written chapters to Band: %s", exc)

        return written

    def handle_band_mention(
        self, message_content: str, session_id: str, subject_name: str = "the subject"
    ) -> Dict[str, str]:
        """Called when @storyteller is mentioned in Band."""
        body = re.sub(r"^@storyteller\s*", "", message_content.strip())
        enriched = self._parse_enriched_from_message(body)
        if not enriched:
            return {}
        return self.write_all_chapters(enriched, subject_name, session_id)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _claude_chapter(
        self,
        chapter_name: str,
        memories: List[Dict[str, str]],
        subject_name: str,
    ) -> str:
        if not self.client:
            raise RuntimeError("No Anthropic client")
        memory_lines = []
        for m in memories or []:
            original = m.get("original", "")
            context = m.get("context", "")
            year = m.get("year", "")
            memory_lines.append(f"- Memory: {original}")
            if context:
                memory_lines.append(f"  Historical note: {context} (year: {year})")

        prompt = (
            f"Write a 300–600 word memoir chapter titled \"{chapter_name}\" "
            f"in the first person, in the voice of {subject_name}. "
            "Draw on the memories and historical notes below. "
            "Preserve specific names, places, objects, and the subject's "
            "own expressions wherever possible. Tone: literary but "
            "accessible, warm, human, specific. No purple prose. "
            "Weave the historical notes in as gentle context, not as a lecture. "
            "Do not include a chapter title in the body — start directly with prose.\n\n"
            "Memories and notes:\n" + "\n".join(memory_lines)
        )
        return self._call_claude(prompt, max_tokens=1500)

    def _call_claude(self, user_prompt: str, max_tokens: int = 1500) -> str:
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
    def _fallback_chapter(
        chapter_name: str,
        memories: List[Dict[str, str]],
        subject_name: str,
    ) -> str:
        """Build a simple first-person chapter from raw memories."""
        if not memories:
            return (
                f"There are stories to tell about {chapter_name.lower()}, "
                f"and {subject_name} will share them in good time."
            )
        intro = f"This is the chapter of my life I call {chapter_name.lower()}."
        body_parts: List[str] = []
        for m in memories:
            original = (m.get("original") or "").strip()
            if not original:
                continue
            # Strip "Subject:" prefix if present
            original = re.sub(r"^Subject:\s*", "", original)
            body_parts.append(original)
        if not body_parts:
            return intro + " The details of this part of my life are still coming back to me."
        body = "\n\n".join(body_parts)
        closing = (
            "These are the things I carry with me from this part of my life. "
            "They are not everything, but they are true, and that is what matters."
        )
        return f"{intro}\n\n{body}\n\n{closing}"

    @staticmethod
    def _parse_enriched_from_message(body: str) -> Dict[str, List[Dict[str, str]]]:
        """Extract the enriched-chapters dict from a Band message body."""
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
        result: Dict[str, List[Dict[str, str]]] = {}
        for k, v in data.items():
            bucket: List[Dict[str, str]] = []
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        bucket.append(
                            {
                                "original": str(item.get("original", "")),
                                "context": str(item.get("context", "")),
                                "year": item.get("year"),
                            }
                        )
                    elif isinstance(item, str):
                        bucket.append({"original": item, "context": "", "year": None})
            result[str(k)] = bucket
        return result
