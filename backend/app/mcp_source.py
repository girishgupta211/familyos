"""MCP client for the Financial Data Engine.

The context engine calls the colleague's MCP server, turns the result into Contract A, validates it, and
feeds it through the normal pipeline (consent filtering, temporal memory, deterministic finance, Neo4j).
Claude never reads the MCP data directly, so every guarantee still holds for real data.

Configure with environment variables (one transport):
    FINANCIAL_ENGINE_MCP_URL       streamable-HTTP endpoint, e.g. http://10.0.0.5:9200/mcp
    FINANCIAL_ENGINE_MCP_COMMAND   stdio command, e.g. "python /path/to/server.py"
Optional:
    FINANCIAL_ENGINE_MCP_TOKEN        bearer token for HTTP
    FINANCIAL_ENGINE_MCP_TOOL         tool returning one family        (default get_family_financial_data)
    FINANCIAL_ENGINE_MCP_FAMILY_ARG   that tool's family-id argument  (default family_id)
    FINANCIAL_ENGINE_MCP_LIST_TOOL    tool listing families           (default list_families; optional)
"""
from __future__ import annotations

import asyncio
import json
import os
import shlex
from contextlib import asynccontextmanager
from typing import Any, Optional

from .mcp_mapping import to_contract_a  # noqa: F401  (re-exported for main)


def _cfg() -> dict:
    e = os.environ.get
    return {"url": e("FINANCIAL_ENGINE_MCP_URL"), "command": e("FINANCIAL_ENGINE_MCP_COMMAND"),
            "token": e("FINANCIAL_ENGINE_MCP_TOKEN"), "tool": e("FINANCIAL_ENGINE_MCP_TOOL", "get_family_financial_data"),
            "family_arg": e("FINANCIAL_ENGINE_MCP_FAMILY_ARG", "family_id"),
            "list_tool": e("FINANCIAL_ENGINE_MCP_LIST_TOOL", "list_families")}


def configured() -> bool:
    c = _cfg()
    return bool(c["url"] or c["command"])


def describe() -> dict:
    c = _cfg()
    return {"configured": configured(), "transport": "http" if c["url"] else "stdio" if c["command"] else None,
            "endpoint": c["url"] or c["command"], "tool": c["tool"], "family_arg": c["family_arg"], "list_tool": c["list_tool"]}


@asynccontextmanager
async def _session():
    from mcp import ClientSession, StdioServerParameters
    c = _cfg()
    if c["url"]:
        import httpx2
        from mcp.client.streamable_http import streamable_http_client
        headers = {"Authorization": f"Bearer {c['token']}"} if c["token"] else {}
        async with httpx2.AsyncClient(headers=headers, timeout=30) as http:
            async with streamable_http_client(c["url"], http_client=http) as (read, write):
                async with ClientSession(read, write) as s:
                    await s.initialize()
                    yield s
    elif c["command"]:
        from mcp.client.stdio import stdio_client
        parts = shlex.split(c["command"])
        params = StdioServerParameters(command=parts[0], args=parts[1:], env=dict(os.environ))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as s:
                await s.initialize()
                yield s
    else:
        raise RuntimeError("No MCP server configured (set FINANCIAL_ENGINE_MCP_URL or FINANCIAL_ENGINE_MCP_COMMAND)")


def _payload(result) -> Any:
    """Tool results arrive as structured content (preferred) or as JSON text blocks."""
    if getattr(result, "is_error", False):
        texts = [getattr(b, "text", "") for b in result.content or []]
        raise RuntimeError("MCP tool error: " + " ".join(texts)[:300])
    sc = getattr(result, "structured_content", None)
    if sc:
        # Servers that return a list or scalar wrap it as {"result": ...}
        return sc["result"] if set(sc) == {"result"} else sc
    for b in result.content or []:
        if getattr(b, "type", None) == "text":
            try:
                return json.loads(b.text)
            except json.JSONDecodeError:
                continue
    raise RuntimeError("MCP tool returned no JSON payload")


def _root_cause(e: BaseException) -> BaseException:
    """anyio/asyncio task groups wrap the real error (e.g. connection refused); surface it."""
    while isinstance(e, BaseExceptionGroup) and e.exceptions:
        e = e.exceptions[0]
    return e


def _run(coro):
    try:
        return _run_inner(coro)
    except BaseExceptionGroup as eg:
        root = _root_cause(eg)
        raise RuntimeError(f"{type(root).__name__}: {root}") from root


def _run_inner(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Called from inside an event loop: run in a fresh thread so we never block or nest loops.
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(1) as ex:
        return ex.submit(asyncio.run, coro).result()


async def _list_tools() -> list[dict]:
    async with _session() as s:
        res = await s.list_tools()
        return [{"name": t.name, "description": (t.description or "")[:200],
                 "input_schema": t.input_schema if hasattr(t, "input_schema") else getattr(t, "inputSchema", None)} for t in res.tools]


async def _call(tool: str, args: dict) -> Any:
    async with _session() as s:
        return _payload(await s.call_tool(tool, args))


def list_tools() -> list[dict]:
    return _run(_list_tools())


def raw_family(family_id: str) -> Any:
    c = _cfg()
    return _run(_call(c["tool"], {c["family_arg"]: family_id}))


def fetch_family(family_id: str) -> dict:
    """Fetch one family over MCP and return a Contract A dict (validated by the caller)."""
    return to_contract_a(raw_family(family_id), family_id)


def list_families() -> Optional[list[dict]]:
    c = _cfg()
    if not c["list_tool"]:
        return None
    try:
        out = _run(_call(c["list_tool"], {}))
    except Exception:
        return None
    if isinstance(out, dict):
        out = out.get("families") or out.get("result") or []
    return [f if isinstance(f, dict) else {"family_id": str(f)} for f in out]
