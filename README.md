# FamilyOS: Your family's financial life. Understood by AI.

FamilyOS treats a family as one connected financial system: who earns, who owns, who owes, and how one
member's decision affects everyone else.

## Run

```bash
./dev.sh                                   # API on :8000, dashboard on http://localhost:3000
export ANTHROPIC_API_KEY=...               # optional: enables Claude (claude-opus-5-5) for understanding and narration
export FINANCIAL_ENGINE_URL=http://...     # optional: pull live data from the Financial Data Engine
cd backend && .venv/bin/python -m pytest   # contract, temporal, access and end-to-end tests
```

Deep link for the demo: `http://localhost:3000/?q=Can%20our%20family%20afford%20to%20buy%20a%20₹1.5%20crore%20house%20next%20year%3F`

## Architecture

```
Financial Data Engine ──Contract A──▶ Context Engine ─────────────▶ LangGraph workflow ──Contract C──▶ Next.js UI
 (Builder A: OCR and extraction)       entity resolution             1 understand  (Claude or rules)
                                       relationship graph            2 retrieve    (consent-filtered)
                                       temporal memory               3 analyse     (Decimal maths only)
                                       consent and access policy     4 reason      (cross-member insights)
                                       remembered goals              5 verify      (recompute, provenance, gaps)
                                                                     6 respond     (Claude narrates; numbers checked)
```

- **No arithmetic by the LLM.** Every figure comes from `backend/app/finance.py`. The verify and respond steps
  reject any Claude narrative that quotes a number the engine did not compute, and fall back to a deterministic answer.
- **Provenance everywhere.** Each calculation lists its record IDs, and each record links to its source document.
- **Consent.** Arjun's crypto wallet (R018) is marked private. When you view as Rajesh or Priya, it is excluded and the UI says so.
- **Memory.** Asking about a house stores a family goal. A later "what if father retires?" re-evaluates that goal automatically.

## Demo script (3 minutes)
1. **Overview** (KPIs, context graph, Members tab). Hover over Rajesh in the graph to show the joint loan and the nominee link.
2. Viewing as **Arjun**, ask *"Can our family afford to buy a ₹1.5 crore house next year?"*. Walk through the pooled
   income, the Calculations tab, the Evidence tab and the cross-member insight that Rajesh turns 60 in March 2027.
3. Ask *"What happens if father retires next year?"*. The remembered goal is re-evaluated: the EMI ratio goes from 22.9% to 37.9%.
4. Ask *"Which family member contributes the most…?"*: Arjun, at 47.6%.
5. Optional: switch the viewer to **Rajesh** to show the 🔒 private-record notice. In the Memory timeline,
   click **Simulate new document** to show a job change superseding the old salary while keeping its history.
   Click **Reset demo** afterwards.

## Disclosures
All family data is synthetic. Until the Financial Data Engine is connected, data comes from a mock file that follows
Contract A (`backend/data/F001.financial.json`). Planning assumptions (rates, down payment, haircut) are shown with every
answer. Answers are estimates, not lending or investment advice.
