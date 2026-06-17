"""History lookup utility for the @factchecker agent.

Queries the public Wikipedia REST API and the DuckDuckGo Instant Answer
API to build a short historical-context paragraph for a given year and
optional keywords/location. All network calls are wrapped in try/except
and time-bounded so the pipeline never stalls on a flaky API.
"""

import re
import logging
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

WIKIPEDIA_SUMMARY_URL = (
    "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
)
DUCKDUCKGO_URL = "https://api.duckduckgo.com/"

YEAR_RE = re.compile(r"\b(1[5-9]\d{2}|20\d{2})\b")

# Cache repeated lookups so we don't hammer the APIs
_CACHE: dict = {}


class HistoryLookup:
    """Look up historical context for a given year using public APIs."""

    def __init__(self, timeout: float = 4.0):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "EchoMind/1.0 (hackathon; history lookup)",
                "Accept": "application/json",
            }
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_historical_context(
        self,
        year: int,
        location: Optional[str] = None,
        keywords: Optional[List[str]] = None,
    ) -> str:
        """Return a short context paragraph for the given year.

        Combines a Wikipedia summary of "{year}" with a DuckDuckGo
        Instant Answer lookup. Returns an empty string on total failure.
        """
        if not year:
            return ""

        cache_key = (year, location, tuple(keywords or []))
        if cache_key in _CACHE:
            return _CACHE[cache_key]

        wiki_snippet = self._wikipedia_year_summary(year)
        ddg_snippet = self._duckduckgo_snippet(year, keywords, location)

        parts: List[str] = []
        if wiki_snippet:
            parts.append(wiki_snippet)
        if ddg_snippet:
            parts.append(ddg_snippet)

        if not parts:
            context = f"In {year}, the world carried on — and your memory is part of it."
        else:
            context = f"In {year}, " + " ".join(parts[:2])

        _CACHE[cache_key] = context
        return context

    def enrich_memory(
        self,
        memory_text: str,
        year: Optional[int] = None,
        location: Optional[str] = None,
    ) -> dict:
        """Return a dict with the original memory plus historical context.

        If no year is provided, attempts to extract one from the memory
        text using a regex. If still no year, returns context-less dict.
        """
        if year is None:
            match = YEAR_RE.search(memory_text or "")
            if match:
                year = int(match.group(1))

        context = ""
        if year:
            try:
                context = self.get_historical_context(year, location=location)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("History lookup failed for %s: %s", year, exc)
                context = ""

        return {
            "original": memory_text,
            "context": context,
            "year": year,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _wikipedia_year_summary(self, year: int) -> str:
        """Fetch a short summary of the Wikipedia article for the year."""
        try:
            url = WIKIPEDIA_SUMMARY_URL.format(title=year)
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code != 200:
                return ""
            data = resp.json()
            extract = data.get("extract") or ""
            # Trim to ~2 sentences for readability
            sentences = re.split(r"(?<=[.!?])\s+", extract)
            snippet = " ".join(sentences[:2]).strip()
            return snippet
        except Exception as exc:  # pragma: no cover
            logger.debug("Wikipedia summary failed for %s: %s", year, exc)
            return ""

    def _duckduckgo_snippet(
        self,
        year: int,
        keywords: Optional[List[str]],
        location: Optional[str],
    ) -> str:
        """Fetch a DuckDuckGo Instant Answer snippet for the year."""
        try:
            q_parts = [str(year), "history"]
            if keywords:
                q_parts.extend(keywords[:3])
            if location:
                q_parts.append(location)
            params = {
                "q": " ".join(q_parts),
                "format": "json",
                "no_redirect": 1,
                "t": "echomind",
            }
            resp = self.session.get(
                DUCKDUCKGO_URL, params=params, timeout=self.timeout
            )
            if resp.status_code != 200:
                return ""
            data = resp.json()
            text = (
                data.get("AbstractText")
                or data.get("Abstract")
                or ""
            ).strip()
            if not text:
                # Try a RelatedTopic chain
                for topic in data.get("RelatedTopics", []) or []:
                    if isinstance(topic, dict) and topic.get("Text"):
                        text = topic["Text"]
                        break
            if text and len(text) > 320:
                text = text[:317].rsplit(" ", 1)[0] + "…"
            return text
        except Exception as exc:  # pragma: no cover
            logger.debug("DuckDuckGo lookup failed for %s: %s", year, exc)
            return ""
