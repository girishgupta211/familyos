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


# USD per million tokens (Anthropic first-party list prices, Nov 2026). Cache writes use the 5-minute TTL (1.25× input).
# Fast mode on Claude Opus 5.5 bills 2× standard; cache prices are scaled the same way here, so treat fast-mode
# costs as an estimate. Models not listed get no cost estimate rather than a guessed one.
PRICES = {
    "claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_read": 0.20, "cache_write": 5.00},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_read": 0.10, "cache_write": 2.50},
}


def usage_of(resp, model: str, ms: float) -> dict:
    """One LLM call's token usage, from the API's own `usage` block."""
    u = getattr(resp, "usage", None)
    g = lambda k: int(getattr(u, k, 0) or 0) if u is not None else 0
    return {
        "model": getattr(resp, "model", None) or model,
        "speed": getattr(u, "speed", None) if u is not None else None,
        "input_tokens": g("input_tokens"),
        "output_tokens": g("output_tokens"),
        "cache_read_input_tokens": g("cache_read_input_tokens"),
        "cache_creation_input_tokens": g("cache_creation_input_tokens"),
        "stop_reason": getattr(resp, "stop_reason", None),
        "ms": round(ms),
    }


def cost_usd(call: dict) -> Optional[float]:
    """Estimated cost of one call; None when the model has no known price."""
    p = PRICES.get(str(call.get("model") or "").split("@")[0])
    if not p:
        return None
    mult = 2.0 if call.get("speed") == "fast" else 1.0
    c = (call["input_tokens"] * p["input"] + call["output_tokens"] * p["output"]
         + call["cache_read_input_tokens"] * p["cache_read"] + call["cache_creation_input_tokens"] * p["cache_write"]) / 1e6
    return round(c * mult, 6)


def summarize_usage(calls: list[dict]) -> dict:
    """Per-answer totals: what a question cost and how much of the prompt came from cache."""
    tot = lambda k: sum(c[k] for c in calls)
    prompt = tot("input_tokens") + tot("cache_read_input_tokens") + tot("cache_creation_input_tokens")
    costs = [cost_usd(c) for c in calls]
    return {
        "llm_calls": len(calls),
        "input_tokens": tot("input_tokens"),
        "output_tokens": tot("output_tokens"),
        "cache_read_input_tokens": tot("cache_read_input_tokens"),
        "cache_creation_input_tokens": tot("cache_creation_input_tokens"),
        "cache_hit_ratio": round(tot("cache_read_input_tokens") / prompt, 3) if prompt else 0.0,
        "est_cost_usd": round(sum(costs), 6) if calls and all(c is not None for c in costs) else None,
        "llm_ms": sum(c["ms"] for c in calls),
        "models": sorted({str(c["model"]) for c in calls}),
        "speeds": sorted({str(c["speed"]) for c in calls if c["speed"]}),
    }


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
