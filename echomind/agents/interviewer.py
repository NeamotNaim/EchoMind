"""@interviewer agent — runs the warm, conversational interview."""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


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


class InterviewerAgent:
    """Conducts the life-story interview with the subject."""

    MIN_EXCHANGES = 6  # minimum number of back-and-forth rounds
    TARGET_EXCHANGES = 15  # when to mark the interview complete

    SYSTEM_PROMPT = (
        "You are a compassionate, skilled oral historian conducting a "
        "life-story interview. Your job is to help elderly or dying people "
        "tell the stories that matter most to them before it is too late. "
        "Ask one question at a time. Never rush. When someone mentions a "
        "person, place, or event, follow up with warmth and curiosity. "
        "Use simple, direct language. Never sound clinical or cold. "
        "After completing a session, summarise the transcript and post it "
        "to Band tagged @organiser."
    )

    def __init__(self, anthropic_client, band_manager):
        self.client = anthropic_client
        self.band = band_manager
        self.system_prompt = self.SYSTEM_PROMPT
        self.questions = INTERVIEW_QUESTIONS

    # ------------------------------------------------------------------
    # Question generation
    # ------------------------------------------------------------------
    def get_next_question(
        self,
        conversation_history: List[Dict[str, str]],
        question_index: int,
    ) -> str:
        """Decide what to ask next.

        Strategy:
        - Empty history → return the first scripted question.
        - Every 3rd turn → return the next scripted question to ensure
          we cover all life topics.
        - Otherwise → ask Claude to generate a warm, contextual follow-up
          based on the subject's last answer. If Claude fails, fall back
          to the next scripted question.
        """
        if not conversation_history:
            return self.questions[0]

        # Use a scripted question every third turn to drive coverage
        if question_index % 3 == 0:
            scripted_idx = min(question_index // 3, len(self.questions) - 1)
            return self.questions[scripted_idx]

        try:
            return self._claude_follow_up(conversation_history)
        except Exception as exc:
            logger.warning("Claude follow-up failed: %s — using scripted", exc)
            idx = min(question_index, len(self.questions) - 1)
            return self.questions[idx]

    def _claude_follow_up(self, conversation_history: List[Dict[str, str]]) -> str:
        """Ask Claude for a warm, contextual follow-up question."""
        if not self.client:
            raise RuntimeError("No Anthropic client available")

        # Build a compact transcript for the prompt
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

        text = self._call_claude(prompt, max_tokens=160)
        question = text.strip().strip('"').strip()
        if not question:
            raise RuntimeError("Empty follow-up from Claude")
        return question

    def _call_claude(self, user_prompt: str, max_tokens: int = 400) -> str:
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
                # Extract text from response
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

    # ------------------------------------------------------------------
    # Answer processing
    # ------------------------------------------------------------------
    def process_answer(
        self,
        answer: str,
        conversation_history: List[Dict[str, str]],
        session_id: str,
    ) -> Dict:
        """Process the subject's answer and decide what's next.

        Returns a dict with:
            question: next question (or final message)
            complete: bool, whether the interview is finished
            session_complete: bool, whether the pipeline should fire
        """
        # Append the subject's answer
        conversation_history.append({"role": "user", "content": answer})
        exchanges = sum(1 for m in conversation_history if m.get("role") == "user")
        question_index = exchanges  # 0-based count of questions asked

        # Check for completion
        if exchanges >= self.TARGET_EXCHANGES:
            closing = (
                "Thank you for sharing all of this with me. Your stories are "
                "going to be preserved beautifully for your family."
            )
            conversation_history.append({"role": "assistant", "content": closing})
            return {
                "question": closing,
                "complete": True,
                "session_complete": True,
            }

        if exchanges >= self.MIN_EXCHANGES and self._subject_signals_finish(answer):
            closing = (
                "That sounds like a beautiful place to pause. Let me go and "
                "put your stories together now."
            )
            conversation_history.append({"role": "assistant", "content": closing})
            return {
                "question": closing,
                "complete": True,
                "session_complete": True,
            }

        # Otherwise, ask the next question
        next_q = self.get_next_question(conversation_history, question_index)
        conversation_history.append({"role": "assistant", "content": next_q})
        return {
            "question": next_q,
            "complete": False,
            "session_complete": False,
        }

    @staticmethod
    def _subject_signals_finish(answer: str) -> bool:
        """Heuristic: if the subject seems to be wrapping up, finish early."""
        if not answer:
            return False
        text = answer.lower().strip()
        triggers = [
            "that's all",
            "i think that's it",
            "i'm done",
            "no more",
            "that's everything",
            "i've told you everything",
            "i'm finished",
        ]
        return any(t in text for t in triggers)

    # ------------------------------------------------------------------
    # Transcript
    # ------------------------------------------------------------------
    def compile_transcript(
        self,
        conversation_history: List[Dict[str, str]],
        subject_name: str,
    ) -> str:
        """Format the conversation as a readable transcript string."""
        lines: List[str] = [
            f"Life Story Interview — {subject_name}",
            "=" * 50,
            "",
        ]
        for m in conversation_history:
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

    def post_to_band(self, transcript: str, session_id: str) -> Optional[str]:
        """Post the transcript to Band and @mention @organiser."""
        try:
            msg = (
                f"Interview complete. Transcript follows:\n\n{transcript}\n\n"
                "@organiser please organise these memories into chapters."
            )
            return self.band.mention_agent("interviewer", "organiser", msg)
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to post transcript to Band: %s", exc)
            return None
