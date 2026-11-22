"""Mock of the Financial Data Engine's MCP server, for testing the integration before the real one is ready.

Serves the synthetic families in backend/data as Contract A payloads.

    stdio:  .venv/bin/python tools/mock_financial_mcp.py
    HTTP:   .venv/bin/python tools/mock_financial_mcp.py --http 9200   (endpoint: http://127.0.0.1:9200/mcp)
"""
import json
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer

DATA = Path(__file__).resolve().parent.parent / "data"
server = MCPServer("mock-financial-data-engine", instructions="Synthetic family financial data in FamilyOS Contract A format.")


@server.tool(description="List the families this engine has data for.")
def list_families() -> list[dict]:
    out = []
    for p in sorted(DATA.glob("*.financial.json")):
        d = json.loads(p.read_text())
        out.append({"family_id": d["family_id"], "members": len(d["members"]), "records": len(d["financial_records"])})
    return out


@server.tool(description="Full financial snapshot of one family (Contract A v1.0: members + financial_records).")
def get_family_financial_data(family_id: str) -> dict:
    p = DATA / f"{family_id}.financial.json"
    if not p.exists():
        raise ValueError(f"unknown family {family_id}")
    return json.loads(p.read_text())


if __name__ == "__main__":
    if "--http" in sys.argv:
        port = int(sys.argv[sys.argv.index("--http") + 1])
        server.run(transport="streamable-http", host="127.0.0.1", port=port)
    else:
        server.run()
