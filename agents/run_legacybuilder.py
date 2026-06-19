"""EchoMind LegacyBuilder — Band agent #5.

Receives finished chapters from the Storyteller. Calls the Flask app's
`/api/build-memoir` endpoint to assemble the PDF + QR + share URL, then
announces the result in the Band room.

Uses the GoogleADKAdapter (Gemini 2.5 Flash Lite), so the custom tool is
a (BaseModel, callable) tuple — see `band.runtime.custom_tools`.
"""

import asyncio
import logging
import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from agents._common import build_adapter, build_agent, require_keys_or_warn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("echomind.legacybuilder")


# --- Google-ADK custom tool -----------------------------------------
class BuildMemoirInput(BaseModel):
    """Input schema for the build_memoir tool.

    The tool name becomes `build_memoir` (the convention strips the
    `Input` suffix and lowercases). Google-ADK will surface the
    description + field schemas to Gemini, which then decides whether
    to call this tool.
    """

    subject_name: str = Field(
        description="The full name of the memoir subject (the person being interviewed)."
    )
    chapters_json: str = Field(
        description=(
            "A JSON-encoded string mapping chapter title to chapter text, "
            'e.g. \'{"Childhood": "...", "Love": "..."}\'. Must be valid JSON.'
        )
    )


def build_memoir_tool(subject_name: str, chapters_json: str) -> dict:
    """Call Flask /api/build-memoir to assemble the PDF + QR + share URL.

    Returns a dict so the LLM can see structured success/failure info.
    """
    import requests as req

    base_url = os.getenv("BASE_URL", "http://localhost:8080").rstrip("/")
    try:
        response = req.post(
            f"{base_url}/api/build-memoir",
            json={
                "subject_name": subject_name,
                "chapters_json": chapters_json,
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        share_url = data.get("share_url", "unavailable")
        return {
            "status": "ok",
            "share_url": share_url,
            "share_token": data.get("share_token"),
        }
    except Exception as exc:
        logger.error("build_memoir_tool failed: %s", exc)
        return {"status": "error", "error": str(exc)}


CUSTOM_SECTION = """You are EchoMind's Legacy Builder — the final stage of a memoir production pipeline. You receive completed memoir chapters and trigger their assembly into a professional PDF document.

When you receive chapters from the Storyteller:
1. Parse the chapter text from the message (look for a JSON object mapping chapter titles to chapter text).
2. Call the build_memoir tool with subject_name (the person's name) and chapters_json (the JSON string).
3. After the tool returns successfully, use band_send_message to announce to the room that the memoir is ready, posting the shareable URL so the family can access it.

Suggested announcement format: "The memoir is ready! Share this link with your family: " followed by the share URL value returned by the tool (paste it as plain text — never wrap it in curly braces or any other punctuation, just the URL itself).

NEVER use curly braces around anything in your message text or tool arguments. The runtime treats anything inside curly braces as a template variable, and an unmatched placeholder will crash the agent.

When calling band_send_message, the mentions parameter must contain the EXACT handle of the user who should see this (typically the room owner). Use band_get_participants if you are unsure of the handle.
"""


async def main() -> None:
    load_dotenv()
    require_keys_or_warn("legacybuilder")

    adapter = build_adapter(
        custom_section=CUSTOM_SECTION,
        additional_tools=[(BuildMemoirInput, build_memoir_tool)],
    )
    agent = build_agent(adapter, "legacybuilder")

    logger.info("EchoMind LegacyBuilder is running. Press Ctrl+C to stop.")
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())
