"""Gemini client wrapper used by the Flask-side interviewer.

This is the only place the Flask app talks to Gemini. It mirrors the
interface the old in-process interviewer exposed (so the route code is
unchanged) while wrapping Google's `google-generativeai` SDK.

If GOOGLE_API_KEY is missing, the client is None and `generate_text`
raises a clear error. The interviewer route falls back to its scripted
question list in that case.
"""

import logging
import time
from typing import List, Optional

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiClient:
    """Thin wrapper around `google.generativeai.GenerativeModel`."""

    def __init__(self, api_key: Optional[str] = None, model_name: str = DEFAULT_MODEL):
        self.api_key = api_key or ""
        self.model_name = model_name
        self._model = None
        self._configured = False

        if not self.api_key:
            logger.warning(
                "GOOGLE_API_KEY not set — interviewer will use scripted fallback."
            )
            return

        try:
            import google.generativeai as genai

            genai.configure(api_key=self.api_key)
            self._model = genai.GenerativeModel(self.model_name)
            self._configured = True
            logger.info("Gemini client ready (model=%s)", self.model_name)
        except Exception as exc:  # pragma: no cover
            logger.error("Could not initialise Gemini: %s", exc)
            self._configured = False

    @property
    def available(self) -> bool:
        """True when a real Gemini model is ready to use."""
        return self._configured and self._model is not None

    def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int = 400,
    ) -> str:
        """Generate a single text reply. Retries once on transient failure."""
        if not self.available:
            raise RuntimeError("Gemini client not available")

        last_exc: Optional[Exception] = None
        for attempt in range(2):
            try:
                # Gemini combines system + user prompts in the user turn.
                combined = (
                    f"[SYSTEM INSTRUCTIONS]\n{system_prompt}\n\n"
                    f"[USER]\n{user_prompt}"
                )
                response = self._model.generate_content(
                    combined,
                    generation_config={
                        "max_output_tokens": max_output_tokens,
                        "temperature": 0.8,
                    },
                )
                text = (response.text or "").strip()
                if text:
                    return text
                raise RuntimeError("Empty response from Gemini")
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Gemini call failed (attempt %s): %s", attempt + 1, exc
                )
                time.sleep(2)
        raise last_exc or RuntimeError("Gemini call failed")


def follow_up_question(
    client: Optional[GeminiClient],
    scripted_questions: List[str],
    conversation_history: List[dict],
    question_index: int,
) -> str:
    """Decide the next interview question.

    Mirrors the old `InterviewerAgent.get_next_question` logic:
    - empty history → first scripted question
    - every 3rd turn → next scripted question
    - otherwise → ask Gemini for a warm follow-up
    """
    if not conversation_history:
        return scripted_questions[0]

    if question_index % 3 == 0:
        idx = min(question_index // 3, len(scripted_questions) - 1)
        return scripted_questions[idx]

    if client is None or not client.available:
        idx = min(question_index, len(scripted_questions) - 1)
        return scripted_questions[idx]

    try:
        lines: List[str] = []
        for m in conversation_history[-6:]:
            role = "Subject" if m.get("role") == "user" else "Interviewer"
            lines.append(f"{role}: {m.get('content', '').strip()}")
        transcript = "\n".join(lines)
        prompt = (
            "Based on the subject's last answer, ask ONE short, warm, "
            "specific follow-up question that gently goes deeper. "
            "Reference something concrete the subject just said. "
            "Never repeat a question already asked. Do not greet or explain.\n\n"
            f"Recent conversation:\n{transcript}\n\n"
            "Your follow-up question:"
        )
        text = client.generate_text(
            system_prompt=(
                "You are a compassionate, skilled oral historian conducting a "
                "life-story interview. Ask one question at a time. Never rush."
            ),
            user_prompt=prompt,
            max_output_tokens=160,
        )
        question = text.strip().strip('"').strip()
        if not question:
            raise RuntimeError("Empty follow-up from Gemini")
        return question
    except Exception as exc:
        logger.warning("Gemini follow-up failed: %s — using scripted", exc)
        idx = min(question_index, len(scripted_questions) - 1)
        return scripted_questions[idx]
