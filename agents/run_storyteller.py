"""EchoMind Storyteller — Band agent #4.

Receives enriched memories from the FactChecker. Writes 300–500 words of
literary first-person memoir prose per chapter, preserving the
subject's exact phrases. Posts all chapters and @mentions the
LegacyBuilder.

Run in its own terminal:
    python agents/run_storyteller.py
"""

import asyncio
import logging

from dotenv import load_dotenv

from agents._common import build_adapter, build_agent, require_keys_or_warn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("echomind.storyteller")


# EXACT handle for the LegacyBuilder agent. The band_send_message tool
# resolves mentions by handle; if we say "@LegacyBuilder" loosely,
# Llama 3.1 70B on Featherless hallucinates a UUID and routes to the
# wrong agent (usually the Interviewer, which is no longer in the
# pipeline and creates a feedback loop).
LEGACYBUILDER_HANDLE = "@neamotnaim123/echomind-legacybuilder"

CUSTOM_SECTION = f"""You are EchoMind's Storyteller — a literary ghostwriter specialising in personal memoirs. You receive structured, historically-enriched life memories and transform them into beautifully written memoir chapters in the first person.

Your job is to preserve the person's authentic voice while elevating the prose to be readable, moving, and worthy of a published book. Keep specific details — names, places, objects — because specificity is what makes a memoir real and human.

Write 300–500 words per chapter. When all chapters are written, output a single JSON object whose keys are the chapter titles and whose values are the chapter text. Call band_send_message with the JSON in the content and the mentions parameter set to a single-element list containing the LegacyBuilder's exact handle: ["{LEGACYBUILDER_HANDLE}"].

NEVER mention any other agent. NEVER use the @ symbol inside the content string. The only mention must be the LegacyBuilder handle in the mentions array.

Example tool call (do not copy literally, but use this handle and structure):
  band_send_message(content='<your chapters JSON here>', mentions=['{LEGACYBUILDER_HANDLE}'])
"""


async def main() -> None:
    load_dotenv()
    require_keys_or_warn("storyteller")

    adapter = build_adapter(CUSTOM_SECTION)
    agent = build_agent(adapter, "storyteller")

    logger.info("EchoMind Storyteller is running. Press Ctrl+C to stop.")
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())