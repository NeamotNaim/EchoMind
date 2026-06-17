"""@organiser agent — sorts the raw transcript into thematic chapters."""

import json
import logging
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


CHAPTER_CATEGORIES: Dict[str, str] = {
    "childhood": "Childhood & Family Origins",
    "school": "School & Growing Up",
    "love": "Love & Relationships",
    "career": "Career & Life's Work",
    "adventures": "Adventures & Travel",
    "proud": "Proudest Moments",
    "hardships": "Hardest Times & What They Taught",
    "wisdom": "Wisdom & Advice for the Future",
}


SYSTEM_PROMPT = (
    "You are a skilled archivist and oral historian. You receive raw "
    "interview transcripts and organise the stories within them into "
    "meaningful thematic chapters for a life memoir. Output a structured "
    "JSON object with chapter names as keys and arrays of memory "
    "excerpts as values. Be faithful to the person's voice — do not "
    "paraphrase or interpret. Post your structured output to Band and "
    "mention @factchecker."
)


class OrganiserAgent:
    """Reads a transcript and organises it into chapter buckets."""

    def __init__(self, anthropic_client, band_manager):
        self.client = anthropic_client
        self.band = band_manager
        self.system_prompt = SYSTEM_PROMPT

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def organise_transcript(self, transcript: str, session_id: str) -> Dict[str, List[str]]:
        """Use Claude (or a heuristic fallback) to bucket memories into chapters."""
        chapters: Dict[str, List[str]] = {key: [] for key in CHAPTER_CATEGORIES}

        # Try Claude first; if unavailable or it fails, fall back to the
        # keyword heuristic so the pipeline still produces a memoir.
        llm_chapters: Optional[Dict] = None
        try:
            llm_chapters = self._claude_organise(transcript)
        except Exception as exc:
            logger.warning("Claude organise failed: %s — using heuristic", exc)

        if llm_chapters:
            for key, items in llm_chapters.items():
                canonical = self._canonical_key(key)
                if canonical is None:
                    continue
                for item in items or []:
                    if isinstance(item, str) and item.strip():
                        chapters[canonical].append(item.strip())
        else:
            logger.info("Organiser: using heuristic fallback for session %s", session_id)
            self._heuristic_organise(transcript, chapters)

        # Drop empty chapters for output
        clean = {CHAPTER_CATEGORIES[k]: v for k, v in chapters.items() if v}

        # Post to Band and @mention @factchecker
        try:
            payload = json.dumps(clean, ensure_ascii=False, indent=2)
            msg = (
                "Chapters organised. Memory buckets ready.\n\n"
                f"```json\n{payload}\n```\n\n"
                "@factchecker please add historical context to these memories."
            )
            self.band.mention_agent("organiser", "factchecker", msg)
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to post organised chapters to Band: %s", exc)

        return clean

    def handle_band_mention(self, message_content: str, session_id: str) -> Dict[str, List[str]]:
        """Called when @organiser is mentioned in Band."""
        # Try to extract a transcript block from the message
        transcript = self._extract_transcript(message_content)
        return self.organise_transcript(transcript, session_id)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _claude_organise(self, transcript: str) -> Optional[Dict[str, List[str]]]:
        """Ask Claude to classify memories into the canonical chapter set."""
        if not self.client:
            return None

        keys_hint = ", ".join(f'"{k}"' for k in CHAPTER_CATEGORIES.keys())
        user_prompt = (
            "Read the interview transcript below and classify each distinct "
            "memory/story the subject shared into one of these chapter keys:\n"
            f"{keys_hint}.\n\n"
            "Respond ONLY with a JSON object. Keys must be the chapter keys "
            "listed above. Values are arrays of short memory excerpts quoted "
            "or lightly summarised from the transcript (preserve the subject's "
            "voice where possible). If a chapter has no memories, omit it.\n\n"
            f"Transcript:\n{transcript}"
        )

        text = self._call_claude(user_prompt, max_tokens=2000)
        if not text:
            return None
        # Try to find a JSON block in the response
        json_text = self._extract_json(text)
        if not json_text:
            return None
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as exc:
            logger.warning("Claude JSON parse failed: %s", exc)
            return None
        if not isinstance(data, dict):
            return None
        # Normalise keys
        normalised: Dict[str, List[str]] = {}
        for key, value in data.items():
            canonical = self._canonical_key(key)
            if canonical is None:
                continue
            if isinstance(value, list):
                normalised[canonical] = [str(v) for v in value if v]
            elif isinstance(value, str):
                normalised[canonical] = [value]
        return normalised

    def _call_claude(self, user_prompt: str, max_tokens: int = 2000) -> str:
        """Call Claude with simple retry logic."""
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
    def _canonical_key(key: str) -> Optional[str]:
        """Map any reasonable key to a canonical chapter key."""
        if not key:
            return None
        k = re.sub(r"[^a-z]+", "", key.lower())
        for canonical in CHAPTER_CATEGORIES:
            if k == canonical or canonical in k or k in canonical:
                return canonical
        return None

    @staticmethod
    def _extract_json(text: str) -> Optional[str]:
        """Find a JSON object in a Claude response."""
        if not text:
            return None
        # Look for ```json ... ``` first
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence:
            return fence.group(1)
        # Otherwise find the first { ... } block
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1]
        return None

    @staticmethod
    def _extract_transcript(message: str) -> str:
        """Pull a transcript out of a Band mention message."""
        if not message:
            return ""
        # Drop the @organiser prefix
        body = re.sub(r"^@organiser\s*", "", message.strip())
        # Strip any leading meta lines before a "Subject:" or "Interviewer:" line
        m = re.search(r"(Subject:|Interviewer:|Life Story Interview)", body)
        if m:
            return body[m.start():]
        return body

    @staticmethod
    def _heuristic_organise(transcript: str, chapters: Dict[str, List[str]]) -> None:
        """Keyword-based fallback for bucketing memory lines."""
        if not transcript:
            return
        keyword_map: Dict[str, List[str]] = {
            "childhood": ["child", "born", "grew up", "mother", "father", "parents", "home"],
            "school": ["school", "teacher", "class", "lesson", "learned", "pupil", "headmaster"],
            "love": ["love", "wife", "husband", "kiss", "marriage", "married", "dance", "romance"],
            "career": ["work", "job", "teaching", "teacher", "nurse", "doctor", "office", "profession"],
            "adventures": ["travel", "trip", "journey", "abroad", "voyage", "holiday"],
            "proud": ["proud", "achievement", "accomplished", "best moment"],
            "hardships": ["hard", "loss", "died", "war", "illness", "difficult", "suffered"],
            "wisdom": ["advice", "wisdom", "learn", "future", "grandchild", "remember"],
        }
        for line in transcript.splitlines():
            low = line.lower()
            if not low.strip():
                continue
            for key, kws in keyword_map.items():
                if any(kw in low for kw in kws):
                    chapters[key].append(line.strip())
                    break
