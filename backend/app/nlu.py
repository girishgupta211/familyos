"""Deterministic question understanding — used as fallback and as a validator for the LLM parse."""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Optional

from .context_engine import FamilyContext

INTENTS = ["affordability", "income_change", "contribution", "overview"]

ROLE_WORDS = {
    "father": ["father", "dad", "papa", "daddy", "pitaji"],
    "mother": ["mother", "mom", "mum", "mummy", "maa", "mama"],
    "son": ["son", "brother"],
    "daughter": ["daughter", "sister"],
    "grandfather": ["grandfather", "grandpa", "appa", "thatha", "dadaji", "nanaji"],
    "grandmother": ["grandmother", "grandma", "amma", "paati", "dadi", "nani"],
    "husband": ["husband"],
    "wife": ["wife"],
    "mother_in_law": ["mother-in-law", "mother in law", "saasu"],
}
UNIT = {"crore": Decimal(10_000_000), "cr": Decimal(10_000_000), "lakh": Decimal(100_000),
        "lakhs": Decimal(100_000), "lac": Decimal(100_000), "l": Decimal(100_000), "k": Decimal(1000)}

_AMT = re.compile(r"(?:₹|rs\.?|inr)?\s*(\d+(?:[.,]\d+)?)\s*(crore|cr|lakhs?|lac|l|k)\b", re.I)


def parse_amount(text: str) -> Optional[Decimal]:
    m = _AMT.search(text)
    if m:
        return Decimal(m.group(1).replace(",", "")) * UNIT[m.group(2).lower()]
    m = re.search(r"₹\s*([\d,]{4,})", text)
    return Decimal(m.group(1).replace(",", "")) if m else None


def parse_horizon(text: str) -> int:
    t = text.lower()
    if "next year" in t:
        return 12
    m = re.search(r"in\s+(\d+)\s+years?", t)
    if m:
        return int(m.group(1)) * 12
    m = re.search(r"in\s+(\d+)\s+months?", t)
    return int(m.group(1)) if m else 12


def resolve_members(ctx: FamilyContext, text: str, asker: Optional[str]) -> list[str]:
    t = text.lower()
    found = []
    for mid, m in ctx.members.items():
        if m.name.split()[0].lower() in t:
            found.append(mid)
        elif any(re.search(rf"\b{w}\b", t) for w in ROLE_WORDS.get(m.relationship, [])):
            found.append(mid)
    if asker and re.search(r"\b(i|me|my)\b", t) and asker not in found and not re.search(r"\b(our|we|us)\b", t):
        found.append(asker)
    return found


def understand(ctx: FamilyContext, question: str, asker: Optional[str]) -> dict:
    t = question.lower()
    members = resolve_members(ctx, question, asker)
    if re.search(r"retire|quit|lose (his|her|my) job|loses? (his|her|my)? ?job|stops? working|laid off|sabbatical", t):
        intent = "income_change"
    elif re.search(r"contribut|earns? the most|biggest earner|highest income|who earns|share of (household )?income", t):
        intent = "contribution"
    elif re.search(r"afford|buy|purchase|house|home|flat|apartment|property|car", t) and parse_amount(question):
        intent = "affordability"
    else:
        intent = "overview"
    new_income = None
    if intent == "income_change":
        new_income = Decimal(0)
        m = re.search(r"pension of\s*(.+)", t)
        if m and parse_amount(m.group(1)):
            new_income = parse_amount(m.group(1))
    return {
        "intent": intent,
        "member_ids": members or list(ctx.members),
        "scope": "member" if members and intent != "affordability" else "family",
        "amount": str(parse_amount(question)) if intent == "affordability" and parse_amount(question) else None,
        "horizon_months": parse_horizon(question),
        "scenario_member_id": members[0] if intent == "income_change" and members else None,
        "scenario_new_monthly_income": str(new_income) if new_income is not None else None,
        "required_data": {
            "affordability": ["income", "expense", "loan", "bank_balance", "investment"],
            "income_change": ["income", "expense", "loan", "bank_balance", "investment", "insurance"],
            "contribution": ["income"],
            "overview": ["income", "expense", "loan", "bank_balance", "investment", "asset"],
        }[intent],
        "parser": "rules",
    }
