# FamilyOS integration contracts (v1.0)

The Financial Data Engine (Builder A) and the Family Context Engine (Builder B) are coupled **only** through
Contract A. Neither side depends on the other's internals or database.

```
Documents ─▶ Financial Data Engine ──(Contract A JSON)──▶ Context Engine ──(Contract B)──▶ LangGraph agent ──(Contract C)──▶ UI
```

## Contract A: Financial Data Engine → Context Engine

- **Schema:** `financial-data-v1.schema.json` (full family snapshot) and `record-batch-v1.schema.json` (incremental push).
- **Golden sample:** `F001.sample.json`. Both builders test against this exact file.
- **Extended samples:** `samples/F002–F004.sample.json` cover a 3-generation joint family, a single-parent business owner and a
  young couple. Together they exercise AIS/TDS, pensions, locked investments, floaters, moratorium loans, CAD/USD amounts and unknown values.

### Delivery: either option works

| Option | Who calls whom | How |
|---|---|---|
| **Pull** | Context engine calls the data engine | Expose `GET {FINANCIAL_ENGINE_URL}/families/{family_id}/financial-data` and return a full Contract A payload. Start the context engine with `FINANCIAL_ENGINE_URL=http://host:port`. |
| **Push** | Data engine calls the context engine | `POST http://<context-engine>:8000/api/family/{family_id}/records` with a `RecordBatch` body: `{"schema_version":"1.0","family_id":"F001","financial_records":[...]}`. The response lists the memory changes, such as which older fact was superseded. |

| **MCP** | Context engine calls the data engine's MCP server | Expose a tool `get_family_financial_data(family_id)` that returns a full Contract A payload, as structured output or JSON text. Optionally also expose `list_families()`. Start the context engine with `FINANCIAL_ENGINE_MCP_URL=http://host:port/mcp` (streamable HTTP) or `FINANCIAL_ENGINE_MCP_COMMAND="python server.py"` (stdio). Different tool or argument names can be set with `FINANCIAL_ENGINE_MCP_TOOL` and `FINANCIAL_ENGINE_MCP_FAMILY_ARG`. A bearer token goes in `FINANCIAL_ENGINE_MCP_TOKEN`. |

If the MCP output is not Contract A, the only file to change is `backend/app/mcp_mapping.py`.
`GET /api/integrations/mcp` lists the server's tools. `POST /api/integrations/mcp/test?family_id=F001` fetches, maps and
validates one family without loading it. A reference server is in `backend/tools/mock_financial_mcp.py`.

Until the data engine is live, the context engine reads `backend/data/F001.financial.json`, which conforms to this contract.
Swapping in the live engine needs no code change. If the live engine is unreachable or returns an invalid payload, the
context engine falls back to the mock file automatically. `GET /api/health` shows the current `data_source`.

**Dry-run validation:** `POST http://<context-engine>:8000/api/contract/validate` with a full snapshot or a record batch.
Nothing is stored. The response lists every error with its JSON path, plus warnings such as a loan without an EMI.

### Member fields (optional additions in v1.0)
`spouse_id`, `parent_ids` and `other_relations` (`[{"type": "grandparent_of", "member_id": "M304"}]`) describe family links
explicitly. Use them whenever a role word like "daughter_in_law" isn't enough. The engine derives siblings and grandparents itself.

### Record fields

| Field | Required | Notes |
|---|---|---|
| `record_id` | ✔ | Stable and unique. **Records are immutable.** To correct or update a value, send a *new* record; the context engine supersedes the old one. |
| `member_id` | ✔ | The primary owner. Must exist in `members`. |
| `co_owner_ids` | | For joint assets, loans and expenses. |
| `type` | ✔ | `income · expense · bank_balance · investment · insurance · loan · asset · liability · transaction · tax` |
| `category` | ✔ | Free text, snake_case, e.g. `salary`, `professional_fees`, `savings_account`, `mutual_funds`, `home_loan`, `term_life`, `household`. |
| `amount` | ✔ | **Decimal string** (`"250000"`), never a float. `null` means *unknown*; it is never treated as zero. |
| `currency` | ✔ | ISO-4217 code (`INR`). |
| `frequency` | | `monthly · quarterly · annual · one_time`, or null for balances and stocks. |
| `entity` | | `{entity_id?, entity_type, name, institution?}`. `entity_type` is one of `employer · bank_account · loan_account · investment_portfolio · property · insurance_policy`. Send `entity_id` (e.g. a masked account number) where you can; otherwise the context engine resolves the entity by name. |
| `attributes` | | String map. **Loans:** `emi` (`"0"` during a moratorium), `emi_after_moratorium`, `moratorium_until`, `interest_rate_pct`, `remaining_tenure_months`, `secured_against_entity_id`. **Insurance:** `premium`, `premium_frequency`, `nominee_member_id`, `insured_member_ids` (comma-separated, for floaters), `copay_pct`, `cover_until`, `paid_by_member_id`. **Investments:** `liquidity` (`"locked"` for EPF/PPF/NPS/SCSS/ESOP-style holdings; inferred from the category if absent), `lock_in_until`, `guardian_member_id`. **Income:** `gross_or_net`. **Tax:** `financial_year`. |
| `source` | ✔ | `{document_id, filename, document_type?, page?}`. This is the provenance shown to users. |
| `valid_from` | ✔ | ISO date from which the fact holds. |
| `valid_until` | | ISO date or null (open-ended). |
| `as_of` | | Snapshot date for balances and valuations. |
| `confidence` | ✔ | Extraction confidence, from 0 to 1. |
| `supersedes` | | Optional explicit hint, e.g. `"R001"`. |

### Amount semantics by type
- **income / expense:** the amount per `frequency`.
- **bank_balance / investment / asset:** the value at `as_of`.
- **loan / liability:** the outstanding principal at `as_of`. The EMI goes in `attributes.emi`.
- **insurance:** the sum assured. The premium goes in `attributes`.
- **transaction:** a single event. These are always appended and never supersede anything.

### How the context engine applies temporal memory
- **income:** one current fact per `(member, type, category)`. A new employer's salary supersedes the old salary.
- **Balances, investments, loans and other state facts:** one current fact per `(member, type, category, entity)`.
- **transaction:** append-only.
- Superseded facts are kept and labelled `superseded`. Facts whose `valid_until` has passed are marked `ended`.

## Contract B: Context Engine → Agent and UI
`GET /api/family/{id}/context?member_id=M00x` returns:
`{family_id, members, entities, relationships, financial_context, memory_timeline, goals, withheld_record_count, context_version}`.
The response is filtered by the viewer's consent policy (`backend/data/F001.access.json`).

## Contract C: Question answering
`POST /api/family/{id}/ask` with body `{"question": "...", "member_id": "M003", "history": []}` returns:
`{answer, key_findings, context_insights, supporting_records, calculations, assumptions, missing_information, confidence, verification, trace, ...}`.
