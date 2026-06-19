"""Shared helpers for the standalone EchoMind Band agents.

Each agent uses the `band-sdk` `GoogleADKAdapter` to wrap a Gemini model
and connect to Band over WebSocket. The `band-sdk` package requires
Python 3.11+.

If the `band` package is not installed, the scripts still parse and
exit with a helpful message — the Flask app keeps working.
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def load_agent_config(name: str) -> Tuple[Optional[str], Optional[str]]:
    """Load agent_id and api_key for the named agent.

    Priority order:
      1. environment variables `ECHOMIND_{NAME}_AGENT_ID` /
         `ECHOMIND_{NAME}_API_KEY` (useful for containers/CI)
      2. a local `agent_config.yaml` next to the repo root

    Returns (None, None) if the values cannot be found.
    """
    env_id = os.getenv(f"ECHOMIND_{name.upper()}_AGENT_ID")
    env_key = os.getenv(f"ECHOMIND_{name.upper()}_API_KEY")
    if env_id and env_key:
        return env_id.strip(), env_key.strip()

    try:
        import yaml  # type: ignore
    except ImportError:
        logger.warning(
            "PyYAML not installed — skipping agent_config.yaml. "
            "Install with: pip install pyyaml"
        )
        return None, None

    # Look for agent_config.yaml one level up from agents/
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(here)
    config_path = os.path.join(repo_root, "agent_config.yaml")
    if not os.path.exists(config_path):
        return None, None

    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        entry = data.get(name) or {}
        agent_id = (entry.get("agent_id") or "").strip()
        api_key = (entry.get("api_key") or "").strip()
        if agent_id and api_key:
            return agent_id, api_key
        return None, None
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to read %s: %s", config_path, exc)
        return None, None


def build_adapter(custom_section: str, additional_tools=None) -> object:
    """Build a GoogleADKAdapter pointed at Gemini.

    EchoMind uses Google's Gemini models directly through Band's
    GoogleADKAdapter. This is the "Band AI" path: Band orchestrates
    the agent room / WebSocket plumbing, and Gemini provides the
    actual language model under the hood.

    We deliberately use the gemini-2.5-flash-lite model (not Pro or
    standard Flash) because it has the highest free-tier daily quota
    in the gemini-2.5 family. The 20 RPD cap on the free tier is
    Google's hard limit — for higher quotas, enable billing in
    Google AI Studio.
    """
    try:
        from band.adapters import GoogleADKAdapter  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "The `band-sdk` package is not installed. "
            "Install with: pip install 'band-sdk[google_adk]' "
            "(requires Python 3.11+)"
        ) from exc

    api_key = os.getenv("GOOGLE_API_KEY", "").strip()
    model_name = os.getenv(
        "ECHOMIND_GEMINI_MODEL", "gemini-2.5-flash-lite"
    ).strip()

    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY is not set in .env. "
            "Get a key from https://aistudio.google.com/apikey and add "
            "it to .env."
        )

    kwargs = dict(
        model=model_name,
        custom_section=custom_section,
        enable_execution_reporting=True,
    )
    if additional_tools:
        kwargs["additional_tools"] = additional_tools
    return GoogleADKAdapter(**kwargs)


def build_agent(adapter, name: str) -> object:
    """Build a `band.Agent` connected to Band via WebSocket."""
    try:
        from band import Agent  # type: ignore
        from band.runtime.types import SessionConfig  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "The `band-sdk` package is not installed. "
            "Install with: pip install 'band-sdk[google_adk]' "
            "(requires Python 3.11+)"
        ) from exc

    agent_id, api_key = load_agent_config(name)
    if not agent_id or not api_key:
        raise RuntimeError(
            f"Missing Band credentials for {name!r}. "
            "Fill in agent_config.yaml or set ECHOMIND_{NAME}_AGENT_ID / "
            "ECHOMIND_{NAME}_API_KEY."
        )

    # Bump retries so transient Gemini 429s (free tier = 20 RPD) don't
    # permanently kill a handoff. The Band server keeps failed messages
    # re-routable as long as we keep retrying.
    session_config = SessionConfig(max_message_retries=5)

    return Agent.create(
        adapter=adapter,
        agent_id=agent_id,
        api_key=api_key,
        ws_url=os.getenv("BAND_WS_URL", "wss://app.band.ai/api/v1/socket/websocket"),
        rest_url=os.getenv("BAND_REST_URL", "https://app.band.ai/"),
        session_config=session_config,
    )


def require_keys_or_warn(name: str) -> None:
    """Log a clear warning if Band credentials are missing for `name`."""
    agent_id, api_key = load_agent_config(name)
    if not agent_id or not api_key:
        logger.warning(
            "Band credentials for %r are not configured. "
            "Copy agent_config.yaml.example to agent_config.yaml and fill "
            "in the agent_id and api_key, or set the ECHOMIND_%s_AGENT_ID "
            "and ECHOMIND_%s_API_KEY environment variables.",
            name, name.upper(), name.upper(),
        )
