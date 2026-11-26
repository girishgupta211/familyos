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
    # F001 (Mehta family) members, for the family fan-out demo
    "demo-rajesh": {"investor": "Rajesh Mehta", "pan": "ABCPM1234K", "email": "rajesh@example.com", "invested": 2400000, "current_value": 3350000, "xirr_pct": 12.8,
                    "holdings": [{"scheme_id": "SCH-101", "scheme": "Flexi Cap Fund – Direct Growth", "folio": "4455667/12", "value": 2100000, "unrealised_gain": 700000, "holding_days": 1800},
                                 {"scheme_id": "SCH-401", "scheme": "Liquid Fund – Direct Growth", "folio": "8899001/03", "value": 1250000, "unrealised_gain": 60000, "holding_days": 400}]},
    "demo-arjun": {"investor": "Arjun Mehta", "pan": "BCDPM5678L", "email": "arjun@example.com", "invested": 900000, "current_value": 1150000, "xirr_pct": 16.1,
                   "holdings": [{"scheme_id": "SCH-205", "scheme": "Midcap Fund – Direct Growth", "folio": "1122334/55", "value": 700000, "unrealised_gain": 180000, "holding_days": 500},
                                {"scheme_id": "SCH-512", "scheme": "ELSS Tax Saver – Direct Growth", "folio": "5566778/90", "value": 450000, "unrealised_gain": 70000, "holding_days": 600}]},
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


@server.tool(description="Portfolio summary for the asking investor.")
def getPortfolioSummary(ctx: Context) -> str:
    p, err = _who(ctx)
    return err or json.dumps({**{k: p[k] for k in ("investor", "invested", "current_value", "xirr_pct")},
                              **({"pan": p["pan"], "email": p["email"]} if "pan" in p else {}), "holdings": p["holdings"]})


@server.tool(description="Cash raisable by a date, cheapest first, after exit load and tax (synthetic: 1% load-free, 12.5% on gains).")
def getLiquidityLadder(ctx: Context, target_amount: float | None = None, needed_by: str | None = None, slab_rate_pct: float | None = None) -> str:
    p, err = _who(ctx)
    if err:
        return err
    order = []
    for h in sorted(p["holdings"], key=lambda h: h["unrealised_gain"] / h["value"]):
        locked = "ELSS" in h["scheme"] and h["holding_days"] < 1095
        if locked:
            continue
        tax = round(h["unrealised_gain"] * 0.125)
        order.append({"scheme_id": h["scheme_id"], "scheme_name": h["scheme"], "folio": h["folio"] if "folio" in h else None,
                      "redeem_gross": h["value"], "exit_load": 0, "estimated_tax": tax, "net_proceeds": h["value"] - tax, "full_exit": True})
    net = sum(o["net_proceeds"] for o in order)
    return json.dumps({"as_of": needed_by or "2026-11-26", "target_amount": target_amount,
                       "target_met": None if target_amount is None else net >= target_amount,
                       "totals": {"planned_net": net, "locked_elss_value": sum(h["value"] for h in p["holdings"] if "ELSS" in h["scheme"] and h["holding_days"] < 1095)},
                       "redemption_order": order})


@server.tool(description="MUTATION: saves risk profile (must never be exposed by FamilyOS).")
def submitRiskProfile(ctx: Context, answers: dict) -> str:
    return json.dumps({"dry_run": True})


if __name__ == "__main__":
    server.run(transport="streamable-http", host="127.0.0.1", port=int(sys.argv[1]) if len(sys.argv) > 1 else 9300)
