"""EchoMind FactChecker — Band agent #3.

Receives structured chapter JSON from the Organiser. Adds 1–2 sentences
of historical context per memory where a year or place is mentioned,
using Wikipedia. Never edits the memory text itself. Then @mentions the
Storyteller.

Run in its own terminal:
    python agents/run_factchecker.py
"""

import asyncio
import logging

from dotenv import load_dotenv

from agents._common import build_adapter, build_agent, require_keys_or_warn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("echomind.factchecker")


# EXACT handle for the Storyteller agent. The band_send_message tool
# resolves mentions by handle; passing a literal like "@Storyteller"
# will cause Llama 3.1 70B on Featherless to hallucinate a UUID and
# route the message to the wrong agent (typically the Interviewer,
# which causes an infinite loop).
STORYTELLER_HANDLE = "@neamotnaim123/echomind-storyteller"

CUSTOM_SECTION = f"""You are EchoMind's Fact Checker — a historical contextualiser for a life memoir project. You receive structured memory data and enrich each memory with accurate historical context from the time period described.

For each memory that mentions a year or historical event, use your knowledge to add 1-2 sentences of historical context that helps readers understand the world the person lived in. Never edit or contradict the person's memory — only add surrounding context.

When you have enriched the JSON, call band_send_message with the enriched JSON in the content and the mentions parameter set to a single-element list containing the Storyteller's exact handle: ["{STORYTELLER_HANDLE}"].

NEVER mention any other agent. NEVER use the @ symbol inside the content string. The only mention must be the Storyteller handle in the mentions array.

Example tool call (do not copy literally, but use this handle and structure):
  band_send_message(content='<your enriched JSON here>', mentions=['{STORYTELLER_HANDLE}'])
"""


async def main() -> None:
    load_dotenv()
    require_keys_or_warn("factchecker")

    adapter = build_adapter(CUSTOM_SECTION)
    agent = build_agent(adapter, "factchecker")

    logger.info("EchoMind FactChecker is running. Press Ctrl+C to stop.")
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())