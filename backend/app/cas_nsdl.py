"""NSDL Consolidated Account Statement (CAS) → Contract A investment records.

Extracts holdings only (equities in demat, MF units in demat, MF folios). Personal identifiers in the CAS —
address, date of birth, PAN, phone, email, bank and demat account numbers — are never copied into records.
Parsed totals are reconciled against the statement's own summary page.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

ISIN = re.compile(r"\b(IN[EF0-9][A-Z0-9]{9})\b")   # INE equity/bonds, INF funds, IN00… government (SGB)
NUM = re.compile(r"-?\d[\d,]*\.\d+|-?\d{1,3}(?:,\d{2,3})+(?:\.\d+)?")
MONTHS = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August",
                                      "September", "October", "November", "December"], 1)}
DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def _d(s: str) -> Decimal:
    return Decimal(s.replace(",", ""))


@dataclass
class Holding:
    kind: str            # equity | bond | sgb | mf_demat | mf_folio
    isin: str
    name: str
    units: Decimal | None
    price: Decimal | None
    value: Decimal
    cost: Decimal | None = None
    unrealised: Decimal | None = None
    account: str = ""


@dataclass
class CasParse:
    as_of: date
    holder_name: str
    holdings: list[Holding] = field(default_factory=list)
    summary: dict[str, Decimal] = field(default_factory=dict)
    reconciliation: dict = field(default_factory=dict)


def _clean_name(s: str) -> str:
    s = DEVANAGARI.sub("", s)
    s = re.sub(r"^\s*(?:MF[A-Z]{2,}\d+|NOT AVAILABLE|\d{5,6})\s+", "", s)   # registrar UCC codes before the scheme name
    s = re.sub(r"\s+", " ", s).strip(" -#")
    return s[:120]


def parse(path: str | Path) -> CasParse:
    from pypdf import PdfReader
    pages = [p.extract_text() or "" for p in PdfReader(str(path)).pages]
    text = "\n".join(pages)

    m = re.search(r"Consolidated Account Statement for the month of (\w+) (\d{4})", text)
    month, year = MONTHS[m.group(1)], int(m.group(2))
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    as_of = date.fromordinal(nxt.toordinal() - 1)

    holder = ""
    hm = re.search(r"In the (?:Single|Joint) Names? of\s*\n\s*([A-Z][A-Z .]+?)\s*\[", text)
    if hm:
        parts = hm.group(1).split()
        holder = " ".join(p.capitalize() for p in (parts[1:] + parts[:1] if len(parts) == 2 else parts))

    out = CasParse(as_of=as_of, holder_name=holder)
    for label, key in [("NSDL Demat Account", "nsdl_demat"), ("CDSL Demat Account", "cdsl_demat"),
                       ("Mutual Fund Folios", "mf_folios")]:
        sm = re.search(rf"{label}.*?([\d,]+\.\d{{2}})\s*$", text, re.M)
        if sm:
            out.summary[key] = _d(sm.group(1))
    gm = re.search(r"Grand Total\s+([\d,]+\.\d{2})", text)
    if gm:
        out.summary["grand_total"] = _d(gm.group(1))

    # --- split by section headers, not pages: one page can hold the end of demat and the start of MF folios
    start = text.find("Current Bal.")
    folio_hdr = re.search(r"ISIN\s+UCC\s+ISIN Description", text)
    folio_start = folio_hdr.start() if folio_hdr else len(text)
    ter = re.search(r"Period\s+ISIN\s+ISIN Description|Date\s+Transaction Details", text[folio_start:])
    folio_end = folio_start + ter.start() if ter else len(text)
    _parse_demat(text[max(start, 0):folio_start] if start >= 0 else "", out)
    _parse_folios(text[folio_start:folio_end], out)

    eq = sum((h.value for h in out.holdings if h.kind in ("equity", "mf_demat", "bond", "sgb")), Decimal(0))
    mf = sum((h.value for h in out.holdings if h.kind == "mf_folio"), Decimal(0))
    demat_summary = out.summary.get("nsdl_demat", Decimal(0)) + out.summary.get("cdsl_demat", Decimal(0))
    out.reconciliation = {
        "demat_parsed": eq, "demat_statement": demat_summary,
        "mf_folios_parsed": mf, "mf_folios_statement": out.summary.get("mf_folios"),
        "grand_total_parsed": eq + mf, "grand_total_statement": out.summary.get("grand_total"),
    }
    return out


def _segments(text: str):
    """Split text into (isin, body) segments, ending each at the next ISIN or a Sub Total line."""
    idx = [(m.start(), m.group(1)) for m in ISIN.finditer(text)]
    for i, (pos, isin) in enumerate(idx):
        end = idx[i + 1][0] if i + 1 < len(idx) else len(text)
        body = text[pos + len(isin):end]
        body = re.split(r"Sub Total|Total\s", body)[0]
        yield isin, body


def _parse_demat(text: str, out: CasParse) -> None:
    seen = set()
    for isin, body in _segments(text):
        nums = NUM.findall(body)
        if len(nums) < 3:
            continue
        flat = body.replace("\n", " ")
        # Row = name, 9 balance columns (current, free, lent, …), market price, value. Coupon rates inside names
        # (e.g. "2.5% SGB") are numbers too, so position from the right, not the left.
        units = _d(nums[-11]) if len(nums) >= 11 else _d(nums[0])
        cut = flat.find(nums[-11]) if len(nums) >= 11 else NUM.search(flat).start()
        name = _clean_name(flat[:cut])
        if not name or isin in seen:
            continue
        seen.add(isin)
        price, value = _d(nums[-2]), _d(nums[-1])
        kind = ("sgb" if isin.startswith("IN00") or "SGB" in name else "mf_demat" if isin.startswith("INF")
                else "bond" if re.search(r"BOND|NCD|DEBENTURE|SECURED", name, re.I) else "equity")
        out.holdings.append(Holding(kind, isin, name, units, price, value))


def _parse_folios(text: str, out: CasParse) -> None:
    for isin, body in _segments(text):
        nums = NUM.findall(body)
        if len(nums) < 6:
            continue
        units, avg, cost, nav, value, pnl = (_d(x) for x in nums[-6:])
        if not isin.startswith("INF") or units <= 0:
            continue
        head = body.split("\n")
        # first line after the ISIN is the UCC code; the description follows until the folio number
        desc_lines = []
        for ln in head[1:]:
            ln = ln.strip()
            if not ln or re.fullmatch(r"[A-Z0-9]{6,}|NOT AVAILABLE", ln):
                continue
            desc_lines.append(re.split(r"\s\d{6,}\s", ln)[0])
            if NUM.search(ln):
                break
        name = _clean_name(" ".join(desc_lines))
        name = NUM.split(name)[0].strip() if name else isin
        out.holdings.append(Holding("mf_folio", isin, name, units, nav, value, cost=cost, unrealised=pnl))


def to_contract_a(cas: CasParse, family_id: str, member_id: str, source_filename: str) -> dict:
    """Contract A payload: one member, one investment record per holding (no personal identifiers)."""
    asof = cas.as_of.isoformat()
    doc = f"CAS-NSDL-{cas.as_of:%Y%m}"
    recs = []
    occurrence: dict[str, int] = {}
    # Same ISIN can sit in several folios/accounts: each is its own holding (entity), keyed by ISIN + nth occurrence in
    # statement order, so next month's CAS supersedes the matching holding instead of collapsing two folios into one.
    keys = {}
    for h in cas.holdings:
        occurrence[h.isin] = occurrence.get(h.isin, 0) + 1
        keys[id(h)] = f"{family_id}-{h.isin}" + (f"-{occurrence[h.isin]}" if occurrence[h.isin] > 1 else "")
    for i, h in enumerate(sorted(cas.holdings, key=lambda h: -h.value), 1):
        cat = {"equity": "listed_equity", "mf_demat": "mutual_funds", "mf_folio": "mutual_funds", "bond": "bonds",
               "sgb": "sovereign_gold_bonds"}[h.kind]
        attrs = {"isin": h.isin, "holding_type": h.kind}
        if h.units is not None:
            attrs["units"] = str(h.units)
        if h.price is not None:
            attrs["price_or_nav"] = str(h.price)
        if h.cost is not None:
            attrs["cost_basis"] = str(h.cost)
        if h.unrealised is not None:
            attrs["unrealised_gain"] = str(h.unrealised)
        recs.append({
            "record_id": f"{family_id}-R{i:03d}", "member_id": member_id, "type": "investment", "category": cat,
            "description": h.name, "amount": str(h.value), "currency": "INR", "frequency": None,
            "entity": {"entity_id": keys[id(h)], "entity_type": "investment_portfolio", "name": h.name},
            "attributes": attrs,
            "source": {"document_id": doc, "filename": source_filename, "document_type": "nsdl_cas"},
            "valid_from": asof, "valid_until": None, "as_of": asof, "confidence": 0.95,
        })
    return {"schema_version": "1.0", "family_id": family_id,
            "members": [{"member_id": member_id, "name": cas.holder_name or "Investor", "relationship": "self"}],
            "financial_records": recs}
