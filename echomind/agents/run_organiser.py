"""EchoMind Organiser — Band agent #2.

Listens for transcripts from the Interviewer. Classifies each memory
into one of the canonical chapters, posts the JSON, and @mentions the
FactChecker.

Run in its own terminal:
    python agents/run_organiser.py
"""

import asyncio
import logging

from dotenv import load_dotenv

from agents._common import build_adapter, build_agent, require_keys_or_warn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("echomind.organiser")


# IMPORTANT: The handle below is the EXACT Band handle for the
# FactChecker agent. The band_send_message tool resolves mentions
# by handle (or by agent UUID), and Llama 3.1 70B on Featherless
# will hallucinate UUIDs if we say "the FactChecker" generically.
# Always pass the exact handle as a literal string.
FACTCHECKER_HANDLE = "@neamotnaim123/echomind-factchecker"

CUSTOM_SECTION = f"""You are EchoMind's Memory Organiser — a skilled archivist who receives raw interview transcripts and organises the stories within them into meaningful thematic chapters for a life memoir.

Classify each memory or story into one of these chapters:
- Childhood & Family Origins
- School & Growing Up
- Love & Relationships
- Career & Life's Work
- Adventures & Travel
- Proudest Moments
- Hardest Times & Lessons Learned
- Wisdom & Advice for the Future

Output a structured JSON object with chapter names as keys and arrays of memory text as values. Be faithful to the person's voice — do not paraphrase.

Then, when you have the JSON ready, call band_send_message with the JSON in the content and the mentions parameter set to a single-element list containing the FactChecker's exact handle: ["{FACTCHECKER_HANDLE}"].

NEVER mention any other agent. NEVER use the @ symbol inside the content string. The only mention must be the FactChecker handle in the mentions array.

Example tool call (do not copy literally, but use this handle and structure):
  band_send_message(content='<your JSON here>', mentions=['{FACTCHECKER_HANDLE}'])
"""


async def main() -> None:
    load_dotenv()
    require_keys_or_warn("organiser")

    adapter = build_adapter(CUSTOM_SECTION)
    agent = build_agent(adapter, "organiser")

    logger.info("EchoMind Organiser is running. Press Ctrl+C to stop.")
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
