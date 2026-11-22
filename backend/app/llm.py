"""Thin Claude wrapper. Claude does language (understanding + narration), never arithmetic.
If no credentials are configured or a call fails, callers fall back to deterministic logic."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

log = logging.getLogger("familyos.llm")
MODEL = os.environ.get("FAMILYOS_MODEL", "claude-opus-5-5")

_client = None
KEY_FILE = Path(os.environ.get("FAMILYOS_KEY_FILE", Path.home() / "Desktop" / "claude.env"))


def _key() -> Optional[str]:
    """ANTHROPIC_API_KEY from the environment, else from the key file (raw key or KEY=value lines)."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    try:
        for line in KEY_FILE.read_text().splitlines():
            line = line.strip().removeprefix("export ").strip()
            val = line.split("=", 1)[1] if "=" in line else line
            val = val.strip().strip('"').strip("'")
            if val.startswith("sk-ant-"):
                return val
    except OSError:
        pass
    return None


def enabled() -> bool:
    if os.environ.get("FAMILYOS_DISABLE_LLM") == "1":
        return False
    return bool(_key() or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def client():
    global _client
    if _client is None:
        import anthropic
        k = _key()
        _client = anthropic.Anthropic(api_key=k, timeout=90.0, max_retries=2) if k else anthropic.Anthropic(timeout=90.0, max_retries=2)
    return _client


def _create(**kw):
    """Opus 5.5 with server-side refusal fallback enabled; plain request if the beta is unavailable."""
    try:
        return client().beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kw)
    except TypeError:
        return client().messages.create(**kw)


def json_call(system: str, user: str, schema: dict, max_tokens: int = 2000) -> Optional[dict]:
    if not enabled():
        return None
    try:
        resp = _create(
            model=MODEL, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        )
        if resp.stop_reason in ("refusal", "max_tokens"):
            log.warning("LLM stop_reason=%s", resp.stop_reason)
            return None
        text = next(b.text for b in resp.content if b.type == "text")
        return json.loads(text)
    except Exception as e:  # demo resilience: never let the LLM take the app down
        log.warning("LLM call failed, using deterministic fallback: %s", e)
        return None
