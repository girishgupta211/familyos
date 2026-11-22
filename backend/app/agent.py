"""FamilyOS financial reasoning workflow (LangGraph).

understand -> retrieve -> analyse -> reason -> verify -> respond

Deterministic Python does every number. Claude (if configured) only parses the question and
writes the narrative, and the verify step rejects any narrative quoting numbers we did not compute.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date
from decimal import Decimal
from typing import Any, Optional, TypedDict

from langgraph.graph import END, StateGraph

from . import finance, llm, nlu
from .context_engine import TODAY, FamilyContext, Fact, store
from .money import CRORE, LAKH, inr, inr_short, pct, q


class State(TypedDict, total=False):
    family_id: str
    question: str
    member_id: Optional[str]
    history: list[dict]
    ctx: Any
    plan: dict
    facts: list
    withheld: int
    analysis: dict
    insights: list[str]
    verification: dict
    response: dict
    trace: list[dict]


def _trace(state: State, node: str, t0: float, detail: str) -> list[dict]:
    return state.get("trace", []) + [{"node": node, "ms": round((time.perf_counter() - t0) * 1000), "detail": detail}]


def first(ctx: FamilyContext, mid: str) -> str:
    return ctx.members[mid].name.split()[0]


# ------------------------------------------------------------------ 1. understand
UNDERSTAND_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["intent", "member_ids", "amount", "horizon_months", "scenario_member_id", "scenario_new_monthly_income"],
    "properties": {
        "intent": {"type": "string", "enum": nlu.INTENTS},
        "member_ids": {"type": "array", "items": {"type": "string"}},
        "amount": {"type": ["string", "null"], "description": "Purchase price in INR as a plain integer string, e.g. 15000000"},
        "horizon_months": {"type": "integer"},
        "scenario_member_id": {"type": ["string", "null"]},
        "scenario_new_monthly_income": {"type": ["string", "null"], "description": "INR/month after the change; '0' if retiring with no stated pension"},
    },
}


def understand(state: State) -> State:
    t0 = time.perf_counter()
    ctx = store.get(state["family_id"])
    asker = state.get("member_id")
    if asker and asker not in ctx.members:
        raise PermissionError(f"{asker} is not a member of {ctx.family_id}")
    rules = nlu.understand(ctx, state["question"], asker)
    plan = dict(rules)
    roster = "\n".join(f"{m.member_id}: {m.name} ({m.relationship})" for m in ctx.members.values())
    hist = "\n".join(f"{h['role']}: {h['content'][:300]}" for h in state.get("history", [])[-4:])
    out = llm.json_call(
        system=("You classify a family-finance question for FamilyOS. Intents: affordability (can we buy X), "
                "income_change (what if a member retires / loses job / income changes), contribution (who "
                "contributes most / income split), overview (anything else). Resolve relationship words to member "
                "ids relative to the asker. Convert lakh/crore to plain INR integers. Do not invent amounts."),
        user=f"Family members:\n{roster}\nAsker: {asker}\nToday: {TODAY}\nRecent conversation:\n{hist or '(none)'}\n\nQuestion: {state['question']}",
        schema=UNDERSTAND_SCHEMA, max_tokens=1500,
    )
    if out and out["intent"] in nlu.INTENTS and all(m in ctx.members for m in out["member_ids"]):
        plan.update({k: out[k] for k in ("intent", "horizon_months", "scenario_member_id", "scenario_new_monthly_income")})
        plan["member_ids"] = out["member_ids"] or list(ctx.members)
        plan["amount"] = out["amount"] if out["amount"] and re.fullmatch(r"\d+(\.\d+)?", out["amount"]) else rules["amount"]
        plan["parser"] = "claude"
        plan["required_data"] = nlu.understand(ctx, state["question"], asker)["required_data"] if plan["intent"] == rules["intent"] else \
            ["income", "expense", "loan", "bank_balance", "investment", "insurance", "asset"]
    if plan["intent"] == "income_change" and plan.get("scenario_member_id") not in ctx.members:
        plan["intent"] = "overview"
    detail = f"intent={plan['intent']} via {plan['parser']}; members={','.join(first(ctx, m) for m in plan['member_ids'])}"
    return {"ctx": ctx, "plan": plan, "trace": _trace(state, "Question understanding", t0, detail)}


# ------------------------------------------------------------------ 2. retrieve
def retrieve(state: State) -> State:
    t0 = time.perf_counter()
    ctx: FamilyContext = state["ctx"]
    vis, hidden = ctx.visible_facts(state.get("member_id"))  # access check happens here
    current = [f for f in vis if f.status == "current"]
    detail = (f"{len(current)} current facts across {len({f.record.member_id for f in current})} members; "
              f"{len([f for f in vis if f.status == 'superseded'])} historical; {hidden} withheld by consent policy")
    return {"facts": vis, "withheld": hidden, "trace": _trace(state, "Context retrieval", t0, detail)}


# ------------------------------------------------------------------ 3. analyse
def analyse(state: State) -> State:
    t0 = time.perf_counter()
    ctx: FamilyContext = state["ctx"]
    plan = state["plan"]
    current = [f for f in state["facts"] if f.status == "current"]
    base = finance.snapshot(ctx, current)
    a: dict = {"intent": plan["intent"], "base": base, "calcs": list(base.calcs), "assumptions": [], "findings": []}
    intent = plan["intent"]

    if intent == "affordability":
        price = Decimal(plan["amount"])
        h = int(plan.get("horizon_months") or 12)
        res = finance.affordability(base, price, h)
        a.update(afford=res, price=price, horizon=h)
        a["calcs"] += res["calcs"]
        a["assumptions"] += finance.assumption_text(res["params"], h)
        store.remember_goal(ctx.family_id, {
            "kind": "property_purchase", "label": f"Buy a {inr_short(price)} home",
            "amount": str(price), "target_date": _add_months(TODAY, h).isoformat(),
            "set_by": state.get("member_id"), "created_at": TODAY.isoformat(), "source": "conversation",
        })

    elif intent == "income_change":
        mid = plan["scenario_member_id"]
        new_inc = Decimal(plan.get("scenario_new_monthly_income") or 0)
        h = int(plan.get("horizon_months") or 12)
        scen = finance.snapshot(ctx, current, income_overrides={mid: new_inc})
        a.update(scenario_member=mid, new_income=new_inc, scen=scen, horizon=h)
        drop = base.monthly_income - scen.monthly_income
        a["calcs"].append(finance.Calc(f"Household income if {first(ctx, mid)}'s income → {inr(new_inc)}",
                                       f"{inr(base.monthly_income)} − {inr(drop)}", inr(scen.monthly_income),
                                       scen.monthly_income, base.income_records[mid]))
        a["calcs"].append(finance.Calc("Income reduction", f"{inr(drop)} ÷ {inr(base.monthly_income)}",
                                       pct(drop / base.monthly_income * 100), drop / base.monthly_income * 100))
        if scen.surplus is not None:
            a["calcs"].append(finance.Calc("Monthly surplus after change", f"{inr(scen.monthly_income)} − {inr(scen.monthly_outflow)}",
                                           inr(scen.surplus), scen.surplus))
            if scen.surplus < 0:
                runway = (scen.liquid / -scen.surplus)
                a["calcs"].append(finance.Calc("Months of runway from liquid assets", f"{inr(scen.liquid)} ÷ {inr(-scen.surplus)}",
                                               f"{q(runway)} months", runway))
        a["assumptions"].append(f"{first(ctx, mid)}'s income assumed to become {inr(new_inc)}/month (no pension or gratuity data on file)."
                                if new_inc == 0 else f"{first(ctx, mid)}'s income assumed to become {inr(new_inc)}/month.")
        a["assumptions"].append("All other incomes, expenses and EMIs stay at their latest known values.")
        goal = next((g for g in ctx.goals if g["kind"] == "property_purchase"), None)
        if goal:
            price = Decimal(goal["amount"])
            before = finance.affordability(base, price, h)
            after = finance.affordability(scen, price, h)
            a.update(goal=goal, goal_before=before, goal_after=after)
            a["calcs"].append(finance.Calc(f"Goal '{goal['label']}': EMI-to-income ratio",
                                           f"before {pct(before['emi_ratio'])} → after {pct(after['emi_ratio'])}",
                                           pct(after["emi_ratio"]), after["emi_ratio"] or Decimal(0)))
            a["calcs"].append(finance.Calc(f"Goal '{goal['label']}': surplus after new EMI",
                                           f"before {inr(before['post_surplus'])} → after {inr(after['post_surplus'])}",
                                           inr(after["post_surplus"]), after["post_surplus"] or Decimal(0)))
            a["assumptions"] += finance.assumption_text(after["params"], h)[1:4]

    elif intent == "contribution":
        rows = finance.contributions(ctx, base)
        a["contrib"] = rows
        a["calcs"] = [base.calcs[0]]
        for r in rows:
            a["calcs"].append(finance.Calc(f"{first(ctx, r['member_id'])}'s share of household income",
                                           f"{inr(r['monthly_income'])} ÷ {inr(base.monthly_income)}",
                                           pct(r["share_pct"]), r["share_pct"], r["record_ids"]))
        a["assumptions"].append("Contribution measured by current monthly income on record, not by spending responsibility.")

    else:
        a["assumptions"].append("Figures reflect the latest known value of each record.")

    detail = f"{len(a['calcs'])} deterministic calculations"
    return {"analysis": a, "trace": _trace(state, "Financial analysis", t0, detail)}


def _add_months(d: date, m: int) -> date:
    y, mo = divmod(d.month - 1 + m, 12)
    return date(d.year + y, mo + 1, min(d.day, 28))


# ------------------------------------------------------------------ 4. contextual reasoning
def reason(state: State) -> State:
    t0 = time.perf_counter()
    ctx: FamilyContext = state["ctx"]
    a = state["analysis"]
    base: finance.Snapshot = a["base"]
    facts: list[Fact] = state["facts"]
    cur = [f for f in facts if f.status == "current"]
    out: list[tuple[str, str]] = []
    add = lambda tag, text: out.append((tag, text))

    # Income concentration / dependency
    rows = finance.contributions(ctx, base)
    top = rows[0]
    if top["share_pct"] >= 40:
        add("concentration", f"{first(ctx, top['member_id'])} provides {pct(top['share_pct'])} of household income — the family's finances depend most on this income.")

    # Ages / life stage from DOB
    for m in ctx.members.values():
        if m.date_of_birth:
            age = TODAY.year - m.date_of_birth.year - ((TODAY.month, TODAY.day) < (m.date_of_birth.month, m.date_of_birth.day))
            if age >= 55:
                turns60 = date(m.date_of_birth.year + 60, m.date_of_birth.month, m.date_of_birth.day)
                if TODAY < turns60 <= _add_months(TODAY, 24):
                    add("age", f"{first(ctx, m.member_id)} is {age} and turns 60 in {turns60:%B %Y} — {first(ctx, m.member_id)}'s earning horizon is short.")

    # Liabilities whose obligors may change
    for f in cur:
        r = f.record
        if r.type == "loan":
            months = r.attr_decimal("remaining_tenure_months")
            end = _add_months(TODAY, int(months)) if months else None
            co = ", ".join(first(ctx, c) for c in r.co_owner_ids)
            add("loan", f"Existing {r.description.split(' —')[0]} ({inr_short(r.attr_decimal('emi'))}/month EMI) is in {first(ctx, r.member_id)}'s name"
                       + (f" with {co} as co-borrower" if co else "") + (f", running until ~{end:%b %Y}." if end else "."))
        if r.type == "insurance" and r.attributes.get("nominee_member_id"):
            add("insurance", f"{first(ctx, r.member_id)}'s {inr_short(r.value)} term cover names {first(ctx, r.attributes['nominee_member_id'])} as nominee"
                       + (f" and runs until {r.attributes['cover_until'][:4]}." if r.attributes.get("cover_until") else "."))

    # Temporal context — recent changes and short income histories
    for f in cur:
        r = f.record
        if r.type == "income" and f.supersedes:
            prev = ctx.facts[f.supersedes].record
            add("income_change", f"{first(ctx, r.member_id)}'s income changed from {inr_short(prev.value)} to {inr_short(r.value)} on {r.valid_from:%b %Y} (latest value used; history preserved).")
        if r.type == "income" and not f.supersedes and (TODAY - r.valid_from).days < 365:
            add("income_history", f"{first(ctx, r.member_id)}'s current income has only {max(1, (TODAY - r.valid_from).days // 30)} months of history — less proven for long-term commitments.")

    intent = a["intent"]
    if intent == "affordability":
        res = a["afford"]
        earners = [r for r in rows if r["monthly_income"] > 0]
        add("pooled", f"Affordability relies on pooled income of {len(earners)} earners; any new loan would need co-applicants' consent and documents.")
        old = [m for m in ctx.members.values() if m.date_of_birth and TODAY.year - m.date_of_birth.year >= 55]
        young = [r for r in earners if r["member_id"] not in {m.member_id for m in old}]
        if old and young:
            add("anchor", f"With {first(ctx, old[0].member_id)} close to retirement, a 20-year loan would more plausibly be anchored on {first(ctx, young[0]['member_id'])}'s income.")
    if intent == "income_change" and a.get("goal"):
        add("goal", f"FamilyOS remembered the goal '{a['goal']['label']}' (set {a['goal']['created_at']}) and re-evaluated it under this scenario.")
    if state.get("withheld"):
        add("withheld", f"{state['withheld']} record(s) owned by other members are private and were excluded from this analysis.")
    if intent == "income_change":
        mid = a["scenario_member"]
        if a["scen"].surplus is not None and a["scen"].surplus > 0:
            add("dependency", f"After {first(ctx, mid)} stops earning, the existing EMI and household costs are carried by "
                + " and ".join(first(ctx, m) for m, v in a["scen"].income_by_member.items() if v > 0) + ".")
    keep = RELEVANT.get(intent)
    texts = [t for tag, t in out if keep is None or tag in keep]
    return {"insights": texts, "trace": _trace(state, "Contextual reasoning", t0, f"{len(texts)} cross-member insights")}


RELEVANT = {
    "affordability": {"concentration", "age", "loan", "income_history", "pooled", "anchor", "withheld"},
    "income_change": {"age", "dependency", "loan", "insurance", "goal", "concentration", "withheld"},
    "contribution": {"concentration", "income_change", "income_history", "withheld"},
}


# ------------------------------------------------------------------ 5. verify (pre-narrative)
def verify(state: State) -> State:
    t0 = time.perf_counter()
    a = state["analysis"]
    ctx: FamilyContext = state["ctx"]
    vis_ids = {f.record.record_id for f in state["facts"]}
    cited = sorted({rid for c in a["calcs"] for rid in c.record_ids})
    problems = [rid for rid in cited if rid not in vis_ids]
    # Recompute key totals independently to catch drift
    base: finance.Snapshot = a["base"]
    recomputed = sum(base.income_by_member.values(), Decimal(0))
    checks = [{"check": "Household income recomputed", "ok": recomputed == base.monthly_income}]
    checks.append({"check": "All cited records visible to asker", "ok": not problems})
    if base.surplus is not None:
        checks.append({"check": "Surplus = income − outflows", "ok": base.surplus == base.monthly_income - base.monthly_outflow})
    lowconf = [f.record.record_id for f in state["facts"] if f.status == "current" and f.record.confidence < 0.9 and f.record.record_id in cited]
    missing = list(base.missing)
    if a["intent"] == "income_change" and a.get("new_income") == 0:
        missing.append(f"No pension, gratuity or retirement-corpus documents on file for {first(ctx, a['scenario_member'])}.")
    if a["intent"] == "affordability":
        missing.append("No target property details (location, carpet area, builder) — generic cost assumptions used.")
    v = {"checks": checks, "cited_record_ids": cited, "low_confidence_record_ids": lowconf, "missing": missing,
         "passed": all(c["ok"] for c in checks)}
    return {"verification": v, "trace": _trace(state, "Verification", t0, f"{sum(c['ok'] for c in checks)}/{len(checks)} checks passed; {len(missing)} gaps flagged")}


# ------------------------------------------------------------------ 6. respond
def _findings_and_template(state: State) -> tuple[list[str], str, str]:
    ctx: FamilyContext = state["ctx"]
    a = state["analysis"]
    base: finance.Snapshot = a["base"]
    who = " + ".join(f"{first(ctx, m)} {inr_short(v)}" for m, v in base.income_by_member.items() if v)
    f: list[str] = []
    if a["intent"] == "affordability":
        r = a["afford"]
        label = {"affordable": "looks affordable", "stretch": "is a stretch but possible", "not_affordable": "does not look affordable yet",
                 "insufficient_data": "cannot be assessed with the data on file"}[r["verdict"]]
        f = [f"Pooled household income: {inr_short(base.monthly_income)}/month ({who}).",
             f"Upfront need: {inr_short(r['upfront'])} vs. {inr_short(r['corpus'])} available at purchase → "
             + (f"surplus of {inr_short(-r['gap'])}." if r["gap"] <= 0 else f"shortfall of {inr_short(r['gap'])}."),
             f"New loan {inr_short(r['loan'])} → EMI ≈ {inr(q(r['new_emi'], '1'))}/month; total EMIs {pct(r['emi_ratio'])} of income.",
             f"Monthly surplus after the new EMI: {inr(q(r['post_surplus'], '1'))}."]
        text = (f"Under the stated assumptions, a {inr_short(a['price'])} home in {a['horizon']} months {label}. "
                f"Your family's combined income is {inr_short(base.monthly_income)}/month, and by then you'd have about "
                f"{inr_short(r['corpus'])} available against {inr_short(r['upfront'])} needed upfront. The new EMI of about "
                f"{inr(q(r['new_emi'], '1'))} would take total EMIs to {pct(r['emi_ratio'])} of household income.")
        conf = "medium"
    elif a["intent"] == "income_change":
        s: finance.Snapshot = a["scen"]
        mid = a["scenario_member"]
        drop = base.monthly_income - s.monthly_income
        f = [f"Household income falls {inr_short(base.monthly_income)} → {inr_short(s.monthly_income)}/month (−{pct(drop / base.monthly_income * 100)}).",
             f"Monthly surplus: {inr(base.surplus)} → {inr(s.surplus)}." if s.surplus is not None else "Surplus unknown (expenses missing).",
             f"Liquid assets of {inr_short(s.liquid)} remain untouched."]
        if a.get("goal"):
            b, af = a["goal_before"], a["goal_after"]
            f.append(f"'{a['goal']['label']}': EMI ratio {pct(b['emi_ratio'])} → {pct(af['emi_ratio'])}; surplus after EMI {inr(q(b['post_surplus'], '1'))} → {inr(q(af['post_surplus'], '1'))} ({af['verdict'].replace('_', ' ')}).")
        verb = "retires" if "retir" in state["question"].lower() else "stops earning"
        text = (f"If {first(ctx, mid)} {verb}, household income drops from {inr_short(base.monthly_income)} to "
                f"{inr_short(s.monthly_income)} a month. Expenses and the existing EMI stay, so the monthly surplus moves from "
                f"{inr(base.surplus)} to {inr(s.surplus)}.")
        if a.get("goal"):
            text += (f" For your goal to {a['goal']['label'].lower()}, total EMIs would rise to {pct(a['goal_after']['emi_ratio'])} of income "
                     f"(from {pct(a['goal_before']['emi_ratio'])}), leaving {inr(q(a['goal_after']['post_surplus'], '1'))} a month.")
        conf = "medium"
    elif a["intent"] == "contribution":
        rows = a["contrib"]
        f = [f"{r['name']}: {inr(r['monthly_income'])}/month — {pct(r['share_pct'])}" for r in rows]
        top = rows[0]
        text = (f"{top['name']} contributes the most — {inr_short(top['monthly_income'])} a month, {pct(top['share_pct'])} of the "
                f"household's {inr_short(base.monthly_income)}. " + ", ".join(f"{first(ctx, r['member_id'])} {pct(r['share_pct'])}" for r in rows[1:]) + ".")
        conf = "high"
    else:
        f = [f"Monthly income {inr_short(base.monthly_income)} ({who}).",
             f"Monthly outflows {inr_short(base.monthly_outflow)}; surplus {inr_short(base.surplus)}.",
             f"Liquid assets {inr_short(base.liquid)}; property {inr_short(base.property_value)}; loans {inr_short(base.loan_outstanding)}.",
             f"Net worth ≈ {inr_short(base.net_worth)}."]
        text = (f"Here's your family's position: {inr_short(base.monthly_income)} monthly income, {inr_short(base.surplus)} monthly surplus, "
                f"{inr_short(base.liquid)} in liquid assets and a net worth of about {inr_short(base.net_worth)}.")
        conf = "high"
    if state["verification"]["missing"] and conf == "high":
        conf = "medium"
    return f, text, conf


NARRATE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["answer"],
                  "properties": {"answer": {"type": "string"}}}

_NUM = re.compile(r"(?:₹\s?)?(\d[\d,]*(?:\.\d+)?)\s*(crore|lakh|%)?", re.I)


def _numbers(text: str) -> list[Decimal]:
    out = []
    for m in _NUM.finditer(text):
        raw, unit = m.group(1).replace(",", ""), (m.group(2) or "").lower()
        try:
            v = Decimal(raw)
        except Exception:
            continue
        out.append(v * (CRORE if unit == "crore" else LAKH if unit == "lakh" else 1))
    return out


def _grounded(narrative: str, allowed_text: str) -> tuple[bool, list[str]]:
    allowed = _numbers(allowed_text)
    bad = []
    for v in _numbers(narrative):
        if v <= 31 or v in (2026, 2027, 2028) or v == 60:  # small counts, months, years, ages
            continue
        if not any(abs(v - a) <= max(abs(a) * Decimal("0.02"), Decimal(1)) for a in allowed):
            bad.append(str(v))
    return not bad, bad


def respond(state: State) -> State:
    t0 = time.perf_counter()
    ctx: FamilyContext = state["ctx"]
    a = state["analysis"]
    v = state["verification"]
    findings, template, conf = _findings_and_template(state)
    calcs = [c.to_dict() for c in a["calcs"]]
    facts_by_id = {f.record.record_id: f for f in state["facts"]}
    supporting = []
    for rid in v["cited_record_ids"]:
        f = facts_by_id[rid]
        r = f.record
        supporting.append({"record_id": rid, "member": ctx.members[r.member_id].name, "type": r.type,
                           "category": r.category, "description": r.description, "amount": r.amount,
                           "currency": r.currency, "frequency": r.frequency, "status": f.status,
                           "valid_from": r.valid_from.isoformat(), "confidence": r.confidence,
                           "source": r.source.model_dump()})

    answer, narrator, rejected = template, "template", []
    facts_blob = json.dumps({"question": state["question"], "key_findings": findings, "calculations": calcs,
                             "context_insights": state["insights"], "assumptions": a["assumptions"],
                             "missing_information": v["missing"], "draft": template}, ensure_ascii=False, default=str)
    out = llm.json_call(
        system=("You are FamilyOS, a family financial intelligence assistant in India. Write the answer to the family's question "
                "in 3–5 warm, plain-English sentences, speaking to the family ('your family', names). Use ONLY numbers that appear "
                "verbatim in the provided findings/calculations — never compute, round differently, or introduce new numbers. "
                "Connect members (who carries what), mention the most important dependency or risk from context_insights, and note "
                "that this is an estimate under assumptions, not a lending or investment recommendation. No markdown headings or bullets."),
        user=facts_blob, schema=NARRATE_SCHEMA, max_tokens=2500,
    )
    if out and out.get("answer"):
        ok, bad = _grounded(out["answer"], facts_blob)
        if ok:
            answer, narrator = out["answer"], "claude"
        else:
            rejected = bad
    v = {**v, "narrative_grounded": narrator == "claude" or not rejected, "narrator": narrator, "ungrounded_numbers_rejected": rejected}
    trace = _trace(state, "Response generation", t0, f"narrative by {narrator}" + (f"; rejected LLM draft (ungrounded: {', '.join(rejected)})" if rejected else ""))
    resp = {
        "answer": answer,
        "key_findings": findings,
        "context_insights": state["insights"],
        "supporting_records": supporting,
        "calculations": calcs,
        "assumptions": a["assumptions"],
        "missing_information": v["missing"],
        "confidence": conf,
        "verification": v,
        "intent": a["intent"],
        "plan": {k: state["plan"].get(k) for k in ("intent", "member_ids", "amount", "horizon_months", "scenario_member_id", "parser")},
        "withheld_record_count": state.get("withheld", 0),
        "remembered_goals": store.get(ctx.family_id).goals,
        "trace": trace,
    }
    return {"response": resp, "verification": v, "trace": trace}


def build_graph():
    g = StateGraph(State)
    for name, fn in [("understand", understand), ("retrieve", retrieve), ("analyse", analyse),
                     ("reason", reason), ("verify", verify), ("respond", respond)]:
        g.add_node(name, fn)
    g.set_entry_point("understand")
    for a, b in [("understand", "retrieve"), ("retrieve", "analyse"), ("analyse", "reason"),
                 ("reason", "verify"), ("verify", "respond")]:
        g.add_edge(a, b)
    g.add_edge("respond", END)
    return g.compile()


GRAPH = build_graph()


def ask(family_id: str, question: str, member_id: Optional[str], history: list[dict] | None = None) -> dict:
    out = GRAPH.invoke({"family_id": family_id, "question": question, "member_id": member_id,
                        "history": history or [], "trace": []})
    return out["response"]
