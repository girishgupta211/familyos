"""Deterministic family-finance calculations. The LLM never does arithmetic.

Every step is logged as a Calc (label, formula, result, record_ids) so answers are auditable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .context_engine import FamilyContext, Fact
from .money import inr, inr_short, pct, q

ZERO = Decimal(0)
MONTHLY = {"monthly": Decimal(1), "quarterly": Decimal(1) / 3, "annual": Decimal(1) / 12}
LIQUID_TYPES = {"bank_balance", "investment"}
# Investments that cannot be drawn on for near-term goals without penalty or until maturity.
LOCKED_CATEGORIES = {"epf", "ppf", "nps", "senior_citizen_savings_scheme", "sukanya_samriddhi", "esop",
                     "startup_equity", "gratuity", "superannuation"}
BASE_CURRENCY = "INR"


def is_locked(f) -> bool:
    r = f.record
    liq = r.attributes.get("liquidity")
    return liq == "locked" if liq else r.category in LOCKED_CATEGORIES

# Planning assumptions — surfaced to the user verbatim, never hidden.
DEFAULTS = {
    "down_payment_pct": Decimal("20"),
    "closing_cost_pct": Decimal("7"),        # stamp duty + registration + misc (Maharashtra)
    "loan_rate_pct": Decimal("8.5"),
    "loan_tenure_years": Decimal("20"),
    "emergency_months": Decimal("6"),
    "investment_haircut_pct": Decimal("10"),  # market risk + tax on liquidation
    "savings_realisation_pct": Decimal("50"), # share of monthly surplus actually saved
    "comfortable_emi_ratio_pct": Decimal("40"),
    "max_emi_ratio_pct": Decimal("50"),
}


@dataclass
class Calc:
    label: str
    formula: str
    result: str
    value: Decimal
    record_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"label": self.label, "formula": self.formula, "result": self.result,
                "value": str(q(self.value, "0.01")), "record_ids": self.record_ids}


@dataclass
class Snapshot:
    income_by_member: dict[str, Decimal]
    income_records: dict[str, list[str]]
    monthly_income: Decimal
    emis: list[tuple[str, Decimal]]           # (record_id, monthly emi)
    expenses: list[tuple[str, Decimal]]
    premiums: list[tuple[str, Decimal]]       # insurance premiums, monthly equivalent
    monthly_outflow: Optional[Decimal]        # None if expenses are unknown
    surplus: Optional[Decimal]
    bank: list[tuple[str, Decimal]]
    investments: list[tuple[str, Decimal]]   # liquid investments only
    locked: list[tuple[str, Decimal]]        # EPF/PPF/NPS/SCSS/ESOP… not available for near-term goals
    property_value: Decimal
    property_ids: list[str]
    loan_outstanding: Decimal
    loan_ids: list[str]
    missing: list[str]
    calcs: list[Calc]
    foreign: list[dict] = field(default_factory=list)  # non-INR records, reported but not converted

    @property
    def liquid(self) -> Decimal:
        return sum((v for _, v in self.bank + self.investments), ZERO)

    @property
    def locked_total(self) -> Decimal:
        return sum((v for _, v in self.locked), ZERO)

    @property
    def net_worth(self) -> Decimal:
        return self.liquid + self.locked_total + self.property_value - self.loan_outstanding

    def summary(self, ctx: FamilyContext) -> dict:
        r2 = lambda d: str(q(d, "0.01"))
        return {
            "monthly_income": r2(self.monthly_income),
            "income_by_member": {ctx.members[m].name: r2(v) for m, v in self.income_by_member.items()},
            "monthly_emi": str(sum((v for _, v in self.emis), ZERO)),
            "monthly_expenses": str(sum((v for _, v in self.expenses), ZERO)) if self.expenses else None,
            "monthly_insurance_premiums": str(q(sum((v for _, v in self.premiums), ZERO), "1")),
            "monthly_surplus": r2(self.surplus) if self.surplus is not None else None,
            "bank_balances": str(sum((v for _, v in self.bank), ZERO)),
            "investments": str(sum((v for _, v in self.investments), ZERO)),
            "liquid_assets": str(self.liquid),
            "locked_investments": str(self.locked_total),
            "property_assets": str(self.property_value),
            "total_assets": str(self.liquid + self.locked_total + self.property_value),
            "total_liabilities": str(self.loan_outstanding),
            "net_worth": str(self.net_worth),
            "foreign_currency_holdings_not_converted": self.foreign,
            "missing": self.missing,
        }


def monthly(f: Fact) -> Optional[Decimal]:
    r = f.record
    if r.value is None or r.frequency not in MONTHLY:
        return None
    return r.value * MONTHLY[r.frequency]


def snapshot(ctx: FamilyContext, facts: list[Fact], income_overrides: dict[str, Decimal] | None = None) -> Snapshot:
    income_overrides = income_overrides or {}
    inc: dict[str, Decimal] = {m: ZERO for m in ctx.members}
    inc_recs: dict[str, list[str]] = {m: [] for m in ctx.members}
    emis, exps, prems, bank, inv, locked, missing, foreign = [], [], [], [], [], [], [], []
    prop, prop_ids, loan, loan_ids = ZERO, [], ZERO, []
    for f in facts:
        r = f.record
        if r.value is None:
            missing.append(f"{r.record_id}: amount unknown ({r.description}) — excluded, not treated as zero")
            continue
        if r.currency != BASE_CURRENCY:
            foreign.append({"record_id": r.record_id, "member": ctx.members[r.member_id].name, "type": r.type,
                            "description": r.description, "amount": r.amount, "currency": r.currency})
            missing.append(f"{r.record_id}: {r.amount} {r.currency} ({r.description}) — no FX rate on file, not converted to INR")
            continue
        if r.type == "insurance":
            prem = r.attr_decimal("premium")
            if prem:
                prems.append((r.record_id, prem * MONTHLY.get(r.attributes.get("premium_frequency", "annual"), MONTHLY["annual"])))
            continue
        if r.type == "income":
            m = monthly(f)
            if m is not None:
                inc[r.member_id] += m
                inc_recs[r.member_id].append(r.record_id)
        elif r.type == "expense":
            m = monthly(f)
            if m is not None:
                exps.append((r.record_id, m))
        elif r.type in ("loan", "liability"):
            loan += r.value
            loan_ids.append(r.record_id)
            emi = r.attr_decimal("emi")
            if emi is not None:
                emis.append((r.record_id, emi))
            elif r.type == "loan":
                missing.append(f"{r.record_id}: EMI not available for {r.description}")
        elif r.type == "bank_balance":
            bank.append((r.record_id, r.value))
        elif r.type == "investment":
            (locked if is_locked(f) else inv).append((r.record_id, r.value))
        elif r.type == "asset":
            prop += r.value
            prop_ids.append(r.record_id)
    for m, v in income_overrides.items():
        inc[m] = v
    total_inc = sum(inc.values(), ZERO)
    emi_total = sum((v for _, v in emis), ZERO)
    prem_total = sum((v for _, v in prems), ZERO)
    if not exps:
        missing.append("No household expense records — monthly surplus cannot be computed")
    outflow = emi_total + prem_total + sum((v for _, v in exps), ZERO) if exps else None
    surplus = total_inc - outflow if outflow is not None else None

    all_inc_ids = [r for m in inc for r in inc_recs[m] if m not in income_overrides]
    calcs = [
        Calc("Household monthly income", " + ".join(f"{ctx.members[m].name.split()[0]} {inr(v)}" for m, v in inc.items()),
             inr(total_inc), total_inc, all_inc_ids),
        Calc("Monthly outflows (EMIs + expenses + premiums)",
             " + ".join([f"EMIs {inr(emi_total)}", f"expenses {inr(sum((v for _, v in exps), ZERO))}", f"premiums {inr(prem_total)}"]),
             inr(outflow), outflow or ZERO, [i for i, _ in emis + exps + prems]),
    ]
    if surplus is not None:
        calcs.append(Calc("Monthly surplus", f"{inr(total_inc)} − {inr(outflow)}", inr(surplus), surplus))
    calcs.append(Calc("Liquid assets (bank + investments)",
                      " + ".join(inr(v) for _, v in bank + inv), inr(sum((v for _, v in bank + inv), ZERO)),
                      sum((v for _, v in bank + inv), ZERO), [i for i, _ in bank + inv]))
    if locked:
        lt = sum((v for _, v in locked), ZERO)
        calcs.append(Calc("Locked / retirement investments (excluded from liquid)", " + ".join(inr(v) for _, v in locked),
                          inr(lt), lt, [i for i, _ in locked]))
    return Snapshot(inc, inc_recs, total_inc, emis, exps, prems, outflow, surplus, bank, inv, locked,
                    prop, prop_ids, loan, loan_ids, missing, calcs, foreign)


def emi(principal: Decimal, annual_rate_pct: Decimal, years: Decimal) -> Decimal:
    r = annual_rate_pct / 100 / 12
    n = int(years * 12)
    if r == 0:
        return principal / n
    f = (1 + r) ** n
    return principal * r * f / (f - 1)


def affordability(s: Snapshot, price: Decimal, horizon_months: int, p: dict | None = None) -> dict:
    p = {**DEFAULTS, **(p or {})}
    calcs: list[Calc] = []
    bank = sum((v for _, v in s.bank), ZERO)
    inv = sum((v for _, v in s.investments), ZERO)
    inv_usable = inv * (1 - p["investment_haircut_pct"] / 100)
    calcs.append(Calc("Investments usable after haircut",
                      f"{inr(inv)} × (1 − {pct(p['investment_haircut_pct'])})", inr(inv_usable), inv_usable,
                      [i for i, _ in s.investments]))
    monthly_need = s.monthly_outflow or ZERO
    emergency = monthly_need * p["emergency_months"]
    calcs.append(Calc("Emergency reserve kept aside",
                      f"{p['emergency_months']} months × {inr(monthly_need)}", inr(emergency), emergency))
    surplus = s.surplus if s.surplus is not None else ZERO
    accumulate = max(surplus, ZERO) * horizon_months * p["savings_realisation_pct"] / 100
    calcs.append(Calc(f"Savings accumulated over {horizon_months} months",
                      f"{inr(max(surplus, ZERO))} × {horizon_months} × {pct(p['savings_realisation_pct'])}",
                      inr(accumulate), accumulate))
    corpus = bank + inv_usable + accumulate - emergency
    calcs.append(Calc("Funds available at purchase",
                      f"{inr(bank)} + {inr(inv_usable)} + {inr(accumulate)} − {inr(emergency)}", inr(corpus), corpus,
                      [i for i, _ in s.bank]))
    down = price * p["down_payment_pct"] / 100
    closing = price * p["closing_cost_pct"] / 100
    upfront = down + closing
    calcs.append(Calc("Upfront cash needed",
                      f"{pct(p['down_payment_pct'])} down {inr(down)} + {pct(p['closing_cost_pct'])} costs {inr(closing)}",
                      inr(upfront), upfront))
    gap = upfront - corpus
    calcs.append(Calc("Funding gap (negative = surplus)", f"{inr(upfront)} − {inr(corpus)}", inr(gap), gap))
    loan = price - down
    new_emi = emi(loan, p["loan_rate_pct"], p["loan_tenure_years"])
    calcs.append(Calc("New home-loan EMI",
                      f"{inr(loan)} @ {pct(p['loan_rate_pct'])} for {p['loan_tenure_years']} yrs", inr(new_emi), new_emi))
    existing_emi = sum((v for _, v in s.emis), ZERO)
    total_emi = existing_emi + new_emi
    ratio = total_emi / s.monthly_income * 100 if s.monthly_income else None
    calcs.append(Calc("EMI-to-income ratio after purchase",
                      f"({inr(existing_emi)} + {inr(new_emi)}) ÷ {inr(s.monthly_income)}",
                      pct(ratio), ratio or ZERO, [i for i, _ in s.emis]))
    post_surplus = surplus - new_emi if s.surplus is not None else None
    if post_surplus is not None:
        calcs.append(Calc("Monthly surplus after new EMI", f"{inr(surplus)} − {inr(new_emi)}",
                          inr(post_surplus), post_surplus))
    if ratio is None:
        verdict = "insufficient_data"
    elif gap <= 0 and ratio <= p["comfortable_emi_ratio_pct"] and (post_surplus or ZERO) > 0:
        verdict = "affordable"
    elif gap <= upfront * Decimal("0.15") and ratio <= p["max_emi_ratio_pct"] and (post_surplus or ZERO) > 0:
        verdict = "stretch"
    else:
        verdict = "not_affordable"
    return {
        "verdict": verdict, "price": price, "upfront": upfront, "corpus": corpus, "gap": gap,
        "loan": loan, "new_emi": new_emi, "total_emi": total_emi, "emi_ratio": ratio,
        "post_surplus": post_surplus, "calcs": calcs, "params": p,
    }


def contributions(ctx: FamilyContext, s: Snapshot) -> list[dict]:
    rows = []
    for m, v in sorted(s.income_by_member.items(), key=lambda kv: kv[1], reverse=True):
        share = v / s.monthly_income * 100 if s.monthly_income else ZERO
        rows.append({"member_id": m, "name": ctx.members[m].name, "monthly_income": v, "share_pct": share,
                     "record_ids": s.income_records[m]})
    return rows


def assumption_text(p: dict, horizon_months: int) -> list[str]:
    return [
        f"Income figures are taken as reported on source documents and treated as monthly cash available (gross vs. take-home not verified).",
        f"Down payment {pct(p['down_payment_pct'])}; stamp duty, registration & costs {pct(p['closing_cost_pct'])} of price.",
        f"New home loan at {pct(p['loan_rate_pct'])} for {p['loan_tenure_years']} years (illustrative rate, not a lender quote).",
        f"Only {pct(p['savings_realisation_pct'])} of the monthly surplus is assumed to be saved over the next {horizon_months} months.",
        f"Investments valued with a {pct(p['investment_haircut_pct'])} haircut for market movement and exit taxes.",
        f"{p['emergency_months']} months of outflows kept aside as an emergency reserve.",
        "Property, gold, vehicles and locked investments (EPF, PPF, NPS, SCSS, ESOPs) are not counted as available funds.",
    ]
