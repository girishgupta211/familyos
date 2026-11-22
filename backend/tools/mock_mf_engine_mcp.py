"""Tiny stand-in for MF Engine's /mcp/investor server, for testing FamilyOS plumbing only.

Mimics the documented behaviour: Bearer token check is skipped, but every tool requires an investor identity header
(access-token or x-agentic-user-id) and returns a JSON *string* in content[0].text, with {"error": true, ...} on failure.
The numbers are synthetic and shaped loosely — the real response shapes come from MF Engine.

    .venv/bin/python tools/mock_mf_engine_mcp.py 9300      → http://127.0.0.1:9300/mcp
"""
import json
import sys

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.context import Context

server = MCPServer("mf-investor-mcp-mock")

PORTFOLIOS = {  # keyed by identity value
    "demo-suresh": {"investor": "Suresh Iyer", "invested": 3150000, "current_value": 4200000, "xirr_pct": 14.2,
                    "holdings": [{"scheme_id": "SCH-101", "scheme": "Flexi Cap Fund – Direct Growth", "value": 1850000, "unrealised_gain": 520000, "holding_days": 1400},
                                 {"scheme_id": "SCH-205", "scheme": "Midcap Fund – Direct Growth", "value": 1250000, "unrealised_gain": 410000, "holding_days": 900},
                                 {"scheme_id": "SCH-318", "scheme": "Short Duration Debt Fund", "value": 1100000, "unrealised_gain": 120000, "holding_days": 200}]},
}


def _who(ctx: Context):
    h = {k.lower(): v for k, v in (ctx.headers or {}).items()}
    ident = h.get("access-token") or h.get("x-agentic-user-id")
    if h.get("x-mcp-take-action"):
        return None, json.dumps({"error": True, "code": "UNEXPECTED_HEADER", "message": "take-action header received"})
    if not ident or ident not in PORTFOLIOS:
        return None, json.dumps({"error": True, "code": "FORBIDDEN", "message": "Investor context required"})
    return PORTFOLIOS[ident], None


@server.tool(description="Portfolio health: 0-100 score, grade, top 3 actions.")
def getPortfolioHealthScore(ctx: Context) -> str:
    p, err = _who(ctx)
    return err or json.dumps({"score": 72, "grade": "B", "as_of": "2026-11-21",
                              "top_actions": ["Midcap allocation 30% vs 20% target", "No emergency debt bucket", "1 fund lagging its index"]})


@server.tool(description="Tax-aware plan to raise a target amount by redeeming funds.")
def getSmartRedemptionPlan(ctx: Context, target_amount: float, goal: str = "tax", source: str = "all") -> str:
    p, err = _who(ctx)
    if err:
        return err
    return json.dumps({"target_amount": target_amount, "as_of": "2026-11-21",
                       "plan": [{"scheme_id": "SCH-318", "scheme": "Short Duration Debt Fund", "redeem_amount": 500000,
                                 "estimated_tax": 9500, "reason": "lowest tax drag, least equity exposure"}],
                       "avoid_now": [{"scheme_id": "SCH-205", "reason": "units under 12 months would attract STCG"}],
                       "harvest_opportunity": [{"scheme_id": "SCH-101", "ltcg_within_exemption": 125000}],
                       "estimated_total_tax": 9500})


@server.tool(description="Family roll-up of linked members.")
def getFamilyPortfolioSummary(ctx: Context) -> str:
    p, err = _who(ctx)
    return err or json.dumps({"family_total_value": 4550000, "members": [
        {"name": "Suresh Iyer", "relation": "self", "current_value": 4200000},
        {"name": "Rohan Iyer", "relation": "son (minor)", "current_value": 350000}]})


@server.tool(description="MUTATION: saves risk profile (must never be exposed by FamilyOS).")
def submitRiskProfile(ctx: Context, answers: dict) -> str:
    return json.dumps({"dry_run": True})


if __name__ == "__main__":
    server.run(transport="streamable-http", host="127.0.0.1", port=int(sys.argv[1]) if len(sys.argv) > 1 else 9300)
