"""Generates the synthetic demo families F002–F004 (Contract A v1.0) plus access policies and the family index.

Run:  .venv/bin/python data/seed/build_families.py
All people, employers and numbers are fictional.
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent


def member(mid, name, rel, dob, spouse=None, parents=None, other=None):
    m = {"member_id": mid, "name": name, "relationship": rel, "date_of_birth": dob}
    if spouse:
        m["spouse_id"] = spouse
    if parents:
        m["parent_ids"] = parents
    if other:
        m["other_relations"] = [{"type": t, "member_id": x} for t, x in other]
    return m


def ent(eid, etype, name, inst=None):
    e = {"entity_id": eid, "entity_type": etype, "name": name}
    if inst:
        e["institution"] = inst
    return e


def rec(rid, mid, typ, cat, desc, amount, *, freq=None, entity=None, attrs=None, doc, fname, dtype,
        vf, vu=None, as_of=None, conf=0.97, co=None, cur="INR"):
    r = {"record_id": rid, "member_id": mid, "type": typ, "category": cat, "description": desc,
         "amount": None if amount is None else str(amount), "currency": cur, "frequency": freq,
         "source": {"document_id": doc, "filename": fname, "document_type": dtype},
         "valid_from": vf, "valid_until": vu, "confidence": conf}
    if co:
        r["co_owner_ids"] = co
    if entity:
        r["entity"] = entity
    if attrs:
        r["attributes"] = {k: str(v) for k, v in attrs.items()}
    if as_of:
        r["as_of"] = as_of
    return r


def family(fid, members, records):
    return {"schema_version": "1.0", "family_id": fid, "generated_at": "2026-11-21T18:00:00Z",
            "members": members, "financial_records": records}


# ======================================================================= F002 — Iyer joint family
P = "F002"
iyer_m = [
    member("M201", "Venkatesh Iyer", "grandfather", "1954-06-03", spouse="M202"),
    member("M202", "Kamala Iyer", "grandmother", "1958-01-19", spouse="M201"),
    member("M203", "Suresh Iyer", "son", "1980-09-12", spouse="M204", parents=["M201", "M202"]),
    member("M204", "Meera Iyer", "daughter_in_law", "1983-02-27", spouse="M203"),
    member("M205", "Ananya Iyer", "granddaughter", "2007-05-08", parents=["M203", "M204"]),
    member("M206", "Rohan Iyer", "grandson", "2012-11-30", parents=["M203", "M204"]),
    member("M207", "Karthik Iyer", "son", "1988-03-22", parents=["M201", "M202"]),
]
FD_IOB = ent("DEP-FD-IOB-M201", "deposit", "IOB fixed deposits", "Indian Overseas Bank")
SCSS = ent("DEP-SCSS-M201", "deposit", "Senior Citizens Savings Scheme", "State Bank of India")
POMIS = ent("DEP-POMIS-M202", "deposit", "Post Office Monthly Income Scheme", "India Post")
MYL = ent("PROP-MYLAPORE", "property", "Ancestral house, Mylapore")
WF = ent("PROP-WHITEFIELD", "property", "Whitefield flat, Bengaluru (let out)")
CAR = ent("VEH-M203", "vehicle", "Toyota Innova Hycross")
CLINIC = ent("BIZ-CLINIC-M204", "business", "Meera's Paediatric Clinic")
KAVERI = ent("EMP-KAVERI", "employer", "Kaveri Bank Ltd")
iyer_r = [
    # Venkatesh — retired central-government officer
    rec("R201", "M201", "income", "pension", "Central government pension", 68000, freq="monthly",
        entity=ent("PEN-CPAO-M201", "pension_source", "Central Pension Accounting Office"),
        doc="D201", fname="venkatesh_pension_slip_oct2026.pdf", dtype="pension_slip", vf="2014-07-01"),
    rec("R202", "M201", "investment", "senior_citizen_savings_scheme", "SCSS deposit (8.2%, 5-year lock-in)", 3000000,
        entity=SCSS, attrs={"interest_rate_pct": "8.2", "liquidity": "locked", "lock_in_until": "2028-04-01"},
        doc="D202", fname="venkatesh_scss_passbook.pdf", dtype="passbook", vf="2023-04-01", as_of="2026-10-31"),
    rec("R203", "M201", "investment", "fixed_deposit", "IOB fixed deposits (laddered)", 1800000, entity=FD_IOB,
        attrs={"interest_rate_pct": "7.25"}, doc="D203", fname="venkatesh_iob_fd_receipts.pdf", dtype="fd_receipt",
        vf="2026-10-31", as_of="2026-10-31"),
    rec("R204", "M201", "income", "interest_income", "FD interest (reported in AIS)", 135000, freq="annual", entity=FD_IOB,
        doc="D204", fname="venkatesh_AIS_FY2025-26.pdf", dtype="ais", vf="2025-04-01"),
    rec("R205", "M201", "income", "interest_income", "SCSS interest (reported in AIS)", 246000, freq="annual", entity=SCSS,
        doc="D204", fname="venkatesh_AIS_FY2025-26.pdf", dtype="ais", vf="2025-04-01"),
    rec("R206", "M201", "asset", "residential_property", "Ancestral house, Mylapore (self-occupied, inherited)", 28000000,
        entity=MYL, co=["M207"], attrs={"self_occupied": "true", "valuation_basis": "guideline value × 1.6"},
        doc="D205", fname="mylapore_legal_heir_certificate_and_patta.pdf", dtype="property_document",
        vf="2009-11-02", as_of="2026-04-01", conf=0.75),
    rec("R207", "M201", "insurance", "health_senior_citizen", "Senior citizen health policy (30% co-pay)", 1000000,
        entity=ent("POL-SENIOR-M201", "insurance_policy", "Senior citizen health policy ••4471", "Star Health"),
        attrs={"premium": "62000", "premium_frequency": "annual", "insured_member_ids": "M201,M202",
               "copay_pct": "30", "cover_until": "2027-03-31"},
        doc="D206", fname="senior_health_policy_schedule.pdf", dtype="insurance_policy", vf="2026-04-01"),
    rec("R208", "M201", "tax", "tds_on_interest", "TDS on FD/SCSS interest, FY 2025-26 (AIS)", 38100, freq="annual",
        attrs={"financial_year": "2025-26"}, doc="D204", fname="venkatesh_AIS_FY2025-26.pdf", dtype="ais",
        vf="2025-04-01", vu="2026-03-31"),
    rec("R209", "M201", "expense", "medical", "Medicines & check-ups for both grandparents", 15000, freq="monthly", co=["M202"],
        doc="D207", fname="venkatesh_iob_statement_oct2026.pdf", dtype="bank_statement", vf="2026-01-01", conf=0.85),
    rec("R210", "M201", "bank_balance", "savings_account", "IOB savings account", 420000,
        entity=ent("ACC-IOB-1188", "bank_account", "IOB Savings ••1188", "Indian Overseas Bank"),
        doc="D207", fname="venkatesh_iob_statement_oct2026.pdf", dtype="bank_statement", vf="2026-10-31", as_of="2026-10-31"),
    # Kamala
    rec("R211", "M202", "asset", "gold_jewellery", "Gold jewellery, ~150 g (heirloom)", 2200000,
        entity=ent("GOLD-M202", "precious_metal", "Kamala's gold jewellery"), attrs={"weight_grams": "150"},
        doc="D208", fname="gold_valuation_certificate_2026.pdf", dtype="valuation_report", vf="2026-03-15", as_of="2026-03-15", conf=0.8),
    rec("R212", "M202", "investment", "post_office_mis", "Post Office MIS deposit", 900000, entity=POMIS,
        attrs={"interest_rate_pct": "7.4"}, doc="D209", fname="kamala_pomis_passbook.pdf", dtype="passbook",
        vf="2024-02-01", as_of="2026-10-31"),
    rec("R213", "M202", "income", "interest_income", "POMIS monthly payout", 5550, freq="monthly", entity=POMIS,
        doc="D209", fname="kamala_pomis_passbook.pdf", dtype="passbook", vf="2024-03-01"),
    # Suresh — bank VP
    rec("R214", "M203", "income", "salary", "Monthly salary — Kaveri Bank", 380000, freq="monthly", entity=KAVERI,
        attrs={"gross_or_net": "net"}, doc="D210", fname="suresh_payslip_mar2026.pdf", dtype="payslip", vf="2025-04-01"),
    rec("R215", "M203", "income", "salary", "Monthly salary — Kaveri Bank (promotion to VP)", 420000, freq="monthly", entity=KAVERI,
        attrs={"gross_or_net": "net"}, doc="D211", fname="suresh_payslip_oct2026.pdf", dtype="payslip", vf="2026-04-01"),
    rec("R216", "M203", "investment", "epf", "Employees' Provident Fund", 3800000,
        entity=ent("RET-EPF-M203", "retirement_account", "Suresh — EPF (UAN ••7710)"), attrs={"liquidity": "locked"},
        doc="D212", fname="suresh_epf_passbook.pdf", dtype="epf_passbook", vf="2026-10-31", as_of="2026-10-31"),
    rec("R217", "M203", "investment", "nps", "National Pension System (Tier I)", 1400000,
        entity=ent("RET-NPS-M203", "retirement_account", "Suresh — NPS Tier I"), attrs={"liquidity": "locked", "lock_in_until": "2040-09-12"},
        doc="D213", fname="suresh_nps_statement.pdf", dtype="nps_statement", vf="2026-10-31", as_of="2026-10-31"),
    rec("R218", "M203", "investment", "mutual_funds", "Mutual fund portfolio (CAS)", 3900000,
        entity=ent("INV-CAS-M203", "investment_portfolio", "Suresh — MF portfolio (CAS)"),
        doc="D214", fname="suresh_cas_jun2026.pdf", dtype="cas_statement", vf="2026-06-30", as_of="2026-06-30"),
    rec("R219", "M203", "investment", "mutual_funds", "Mutual fund portfolio (CAS)", 4200000,
        entity=ent("INV-CAS-M203", "investment_portfolio", "Suresh — MF portfolio (CAS)"),
        doc="D215", fname="suresh_cas_oct2026.pdf", dtype="cas_statement", vf="2026-10-31", as_of="2026-10-31"),
    rec("R220", "M203", "investment", "esop", "Employer ESOPs (unvested portion excluded)", 1600000,
        entity=ent("INV-ESOP-M203", "investment_portfolio", "Suresh — Kaveri Bank ESOPs"),
        attrs={"liquidity": "locked", "next_vesting": "2027-06-30"},
        doc="D216", fname="suresh_esop_grant_letter.pdf", dtype="esop_statement", vf="2026-06-30", as_of="2026-06-30", conf=0.85),
    rec("R221", "M203", "asset", "residential_property", "Whitefield flat, Bengaluru (let out)", 16500000, entity=WF, co=["M204"],
        attrs={"self_occupied": "false"}, doc="D217", fname="whitefield_sale_deed.pdf", dtype="property_document",
        vf="2019-08-20", as_of="2026-04-01", conf=0.8),
    rec("R222", "M203", "loan", "home_loan", "ICICI home loan — Whitefield flat", 6200000, co=["M204"],
        entity=ent("LOAN-ICICI-HL-M203", "loan_account", "ICICI Home Loan ••3302", "ICICI Bank"),
        attrs={"emi": "78000", "interest_rate_pct": "8.6", "remaining_tenure_months": "132", "secured_against_entity_id": "PROP-WHITEFIELD"},
        doc="D218", fname="icici_home_loan_statement_oct2026.pdf", dtype="loan_statement", vf="2026-10-31", as_of="2026-10-31"),
    rec("R223", "M203", "income", "rental_income", "Rent from Whitefield flat", 45000, freq="monthly", entity=WF, co=["M204"],
        doc="D219", fname="whitefield_rent_agreement_2026.pdf", dtype="rent_agreement", vf="2026-02-01"),
    rec("R224", "M203", "asset", "vehicle", "Toyota Innova Hycross (2024)", 1100000, entity=CAR,
        doc="D220", fname="innova_rc_and_insurance.pdf", dtype="vehicle_document", vf="2024-03-10", as_of="2026-10-31", conf=0.8),
    rec("R225", "M203", "loan", "car_loan", "Car loan — Innova", 650000,
        entity=ent("LOAN-CAR-M203", "loan_account", "Kaveri Bank Car Loan ••5521", "Kaveri Bank"),
        attrs={"emi": "21000", "interest_rate_pct": "9.1", "remaining_tenure_months": "34", "secured_against_entity_id": "VEH-M203"},
        doc="D221", fname="car_loan_statement_oct2026.pdf", dtype="loan_statement", vf="2026-10-31", as_of="2026-10-31"),
    rec("R226", "M203", "insurance", "term_life", "Term life cover", 20000000,
        entity=ent("POL-TERM-M203", "insurance_policy", "Term policy ••8840", "Max Life"),
        attrs={"premium": "32000", "premium_frequency": "annual", "nominee_member_id": "M204", "cover_until": "2045-09-12"},
        doc="D222", fname="suresh_term_policy.pdf", dtype="insurance_policy", vf="2021-09-12"),
    rec("R227", "M203", "insurance", "health_family_floater", "Family floater health cover", 2500000,
        entity=ent("POL-FLOATER-M203", "insurance_policy", "Family floater ••1290", "Niva Bupa"),
        attrs={"premium": "48000", "premium_frequency": "annual", "insured_member_ids": "M203,M204,M205,M206", "cover_until": "2027-05-31"},
        doc="D223", fname="family_floater_schedule.pdf", dtype="insurance_policy", vf="2026-06-01"),
    rec("R228", "M203", "liability", "credit_card", "Credit card outstanding (statement balance)", 120000,
        entity=ent("CC-M203", "credit_card", "Credit card ••9012", "Kaveri Bank"),
        doc="D224", fname="suresh_cc_statement_oct2026.pdf", dtype="card_statement", vf="2026-10-31", as_of="2026-10-31"),
    rec("R229", "M203", "tax", "tds_on_salary", "TDS on salary, FY 2025-26 (AIS / Form 16)", 1480000, freq="annual",
        attrs={"financial_year": "2025-26"}, doc="D225", fname="suresh_AIS_FY2025-26.pdf", dtype="ais", vf="2025-04-01", vu="2026-03-31"),
    rec("R230", "M203", "tax", "itr_filed", "ITR-2 filed, FY 2025-26 — total tax paid", 1720000, freq="annual",
        attrs={"financial_year": "2025-26", "rental_income_declared": "480000"},
        doc="D226", fname="suresh_ITR2_FY2025-26_ack.pdf", dtype="itr_acknowledgement", vf="2025-04-01", vu="2026-03-31"),
    rec("R231", "M203", "tax", "ais_rental_receipts", "Rent received as reported in AIS (TDS by tenant u/s 194-IB)", 540000, freq="annual",
        attrs={"financial_year": "2025-26", "mismatch_vs_itr": "60000"},
        doc="D225", fname="suresh_AIS_FY2025-26.pdf", dtype="ais", vf="2025-04-01", vu="2026-03-31"),
    rec("R232", "M203", "transaction", "sft_mutual_fund_purchase", "High-value MF purchase reported in AIS (SFT-018)", 600000,
        freq="one_time", entity=ent("INV-CAS-M203", "investment_portfolio", "Suresh — MF portfolio (CAS)"),
        doc="D225", fname="suresh_AIS_FY2025-26.pdf", dtype="ais", vf="2025-12-15"),
    rec("R233", "M203", "expense", "household", "Household running costs, Mylapore (joint family)", 180000, freq="monthly", co=["M201"],
        doc="D227", fname="suresh_kaveri_statement_oct2026.pdf", dtype="bank_statement", vf="2026-04-01", conf=0.85),
    rec("R234", "M203", "bank_balance", "savings_account", "Kaveri Bank salary account", 1250000,
        entity=ent("ACC-KAVERI-M203", "bank_account", "Kaveri Bank Savings ••6634", "Kaveri Bank"),
        doc="D227", fname="suresh_kaveri_statement_oct2026.pdf", dtype="bank_statement", vf="2026-10-31", as_of="2026-10-31"),
    # Meera — paediatrician
    rec("R235", "M204", "income", "professional_fees", "Clinic receipts (net of GST)", 210000, freq="monthly", entity=CLINIC,
        doc="D228", fname="meera_clinic_pnl_FY2025-26.pdf", dtype="profit_and_loss", vf="2025-04-01", conf=0.88),
    rec("R236", "M204", "income", "professional_fees", "Clinic receipts after expansion (net of GST)", 260000, freq="monthly", entity=CLINIC,
        doc="D229", fname="meera_clinic_bank_statement_oct2026.pdf", dtype="bank_statement", vf="2026-04-01", conf=0.86),
    rec("R237", "M204", "loan", "business_loan", "Equipment loan — clinic ultrasound & ICU cots", 1800000,
        entity=ent("LOAN-BIZ-M204", "loan_account", "SIDBI equipment loan ••0417", "SIDBI"),
        attrs={"emi": "42000", "interest_rate_pct": "10.5", "remaining_tenure_months": "48", "secured_against_entity_id": "BIZ-CLINIC-M204"},
        doc="D230", fname="meera_equipment_loan_sanction.pdf", dtype="loan_statement", vf="2026-10-31", as_of="2026-10-31"),
    rec("R238", "M204", "investment", "ppf", "Public Provident Fund", 2100000,
        entity=ent("RET-PPF-M204", "retirement_account", "Meera — PPF"), attrs={"liquidity": "locked", "lock_in_until": "2031-03-31"},
        doc="D231", fname="meera_ppf_passbook.pdf", dtype="passbook", vf="2026-03-31", as_of="2026-03-31"),
    rec("R239", "M204", "investment", "sovereign_gold_bonds", "Sovereign Gold Bonds (exchange-tradable)", 600000,
        entity=ent("INV-SGB-M204", "investment_portfolio", "Meera — SGB holdings"),
        doc="D232", fname="meera_demat_holdings_oct2026.pdf", dtype="demat_statement", vf="2026-10-31", as_of="2026-10-31"),
    rec("R240", "M204", "investment", "fixed_deposit", "Personal fixed deposit", 800000,
        entity=ent("DEP-FD-M204", "deposit", "Meera — personal FD"),
        doc="D233", fname="meera_fd_receipt.pdf", dtype="fd_receipt", vf="2026-07-01", as_of="2026-07-01"),
    rec("R241", "M204", "insurance", "professional_indemnity", "Professional indemnity cover", 10000000,
        entity=ent("POL-PI-M204", "insurance_policy", "Doctors' indemnity policy ••7731", "New India Assurance"),
        attrs={"premium": "15000", "premium_frequency": "annual"},
        doc="D234", fname="meera_indemnity_policy.pdf", dtype="insurance_policy", vf="2026-04-01"),
    rec("R242", "M204", "tax", "tds_on_professional_fees", "TDS u/s 194J on hospital consulting fees (AIS)", 312000, freq="annual",
        attrs={"financial_year": "2025-26"}, doc="D235", fname="meera_AIS_FY2025-26.pdf", dtype="ais", vf="2025-04-01", vu="2026-03-31"),
    rec("R243", "M204", "expense", "business_operating", "Clinic rent, nurse & receptionist salaries", 55000, freq="monthly", entity=CLINIC,
        doc="D229", fname="meera_clinic_bank_statement_oct2026.pdf", dtype="bank_statement", vf="2026-04-01", conf=0.85),
    # Ananya — undergraduate in Toronto
    rec("R244", "M205", "loan", "education_loan", "Education loan — University of Toronto (in moratorium)", 3500000, co=["M203"],
        entity=ent("LOAN-EDU-M205", "loan_account", "Education loan ••6012", "Kaveri Bank"),
        attrs={"emi": "0", "emi_after_moratorium": "46000", "moratorium_until": "2029-12-31", "interest_rate_pct": "9.5"},
        doc="D236", fname="ananya_education_loan_sanction.pdf", dtype="loan_statement", vf="2025-08-20", as_of="2026-10-31"),
    rec("R245", "M205", "expense", "education", "Tuition & living costs, Toronto (paid from Suresh's account)", 240000, freq="monthly",
        co=["M203"], attrs={"paid_by_member_id": "M203"},
        doc="D227", fname="suresh_kaveri_statement_oct2026.pdf", dtype="bank_statement", vf="2025-09-01", conf=0.9),
    rec("R246", "M205", "income", "part_time_job", "Campus library job (Canada)", 1400, freq="monthly", cur="CAD",
        entity=ent("EMP-UOFT-LIB", "employer", "University of Toronto Libraries"),
        doc="D237", fname="ananya_td_bank_statement_oct2026.pdf", dtype="bank_statement", vf="2026-01-10", conf=0.9),
    rec("R247", "M205", "bank_balance", "savings_account", "TD Bank chequing account (Canada)", 3200, cur="CAD",
        entity=ent("ACC-TD-M205", "bank_account", "TD Chequing ••2290", "TD Bank"),
        doc="D237", fname="ananya_td_bank_statement_oct2026.pdf", dtype="bank_statement", vf="2026-10-31", as_of="2026-10-31"),
    # Rohan — Class 9
    rec("R248", "M206", "expense", "school_fees", "School fees, Class 9", 320000, freq="annual", co=["M204"],
        doc="D238", fname="rohan_school_fee_receipt_2026-27.pdf", dtype="fee_receipt", vf="2026-06-01"),
    rec("R249", "M206", "investment", "mutual_funds", "Minor's MF folio (guardian: Suresh)", 350000,
        entity=ent("INV-MF-M206", "investment_portfolio", "Rohan — minor MF folio"), attrs={"guardian_member_id": "M203"},
        doc="D239", fname="rohan_minor_folio_statement.pdf", dtype="cas_statement", vf="2026-10-31", as_of="2026-10-31"),
    # Karthik — founder; does not share with the family (only the co-owned house is visible to others)
    rec("R250", "M207", "income", "founder_stipend", "Founder stipend — Kolam Labs", 150000, freq="monthly",
        entity=ent("BIZ-KOLAM-M207", "business", "Kolam Labs Pvt Ltd (founder)"),
        doc="D240", fname="karthik_bank_statement_oct2026.pdf", dtype="bank_statement", vf="2025-01-01", conf=0.85),
    rec("R251", "M207", "investment", "startup_equity", "Founder equity in Kolam Labs — no current valuation", None,
        entity=ent("BIZ-KOLAM-M207", "business", "Kolam Labs Pvt Ltd (founder)"), attrs={"liquidity": "locked"},
        doc="D241", fname="kolam_cap_table.pdf", dtype="cap_table", vf="2026-03-31", conf=0.6),
    rec("R252", "M207", "loan", "personal_loan", "Personal loan", 900000,
        entity=ent("LOAN-PL-M207", "loan_account", "Personal loan ••4410", "Bajaj Finance"),
        attrs={"emi": "24000", "interest_rate_pct": "13.5", "remaining_tenure_months": "44"},
        doc="D242", fname="karthik_pl_statement.pdf", dtype="loan_statement", vf="2026-10-31", as_of="2026-10-31"),
]

# ======================================================================= F003 — Khan family
khan_m = [
    member("M301", "Farah Khan", "mother", "1985-07-04"),
    member("M302", "Zubeida Khan", "grandmother", "1960-02-11", other=[("grandparent_of", "M303"), ("grandparent_of", "M304")]),
    member("M303", "Ayaan Khan", "son", "2009-04-15", parents=["M301"]),
    member("M304", "Sara Khan", "daughter", "2015-09-23", parents=["M301"]),
]
BOUT = ent("BIZ-BOUTIQUE-M301", "business", "Noor Boutique (proprietorship)")
FD_F = ent("DEP-FD-M301", "deposit", "FDs from insurance claim", "Canara Bank")
HYD = ent("PROP-HYD-M301", "property", "Flat in Tolichowki, Hyderabad")
LKO = ent("PROP-LKO-M302", "property", "House in Aminabad, Lucknow (let out)")
GOLD_F = ent("GOLD-M301", "precious_metal", "Farah's gold jewellery")
khan_r = [
    rec("R301", "M301", "income", "business_income", "Boutique profit drawn (avg)", 95000, freq="monthly", entity=BOUT,
        attrs={"income_volatility": "high"}, doc="D301", fname="farah_boutique_pnl_FY2025-26.pdf", dtype="profit_and_loss",
        vf="2025-04-01", conf=0.8),
    rec("R302", "M301", "income", "business_income", "Boutique profit drawn (avg, festive-season uplift)", 110000, freq="monthly",
        entity=BOUT, attrs={"income_volatility": "high", "gst_turnover_annual": "2640000"},
        doc="D302", fname="farah_gstr3b_and_bank_apr-oct2026.pdf", dtype="gst_return", vf="2026-04-01", conf=0.78),
    rec("R303", "M301", "expense", "business_operating", "Boutique shop rent & 2 tailors", 35000, freq="monthly", entity=BOUT,
        doc="D302", fname="farah_gstr3b_and_bank_apr-oct2026.pdf", dtype="bank_statement", vf="2025-04-01"),
    rec("R304", "M301", "investment", "fixed_deposit", "FDs created from late husband's term-insurance claim", 4500000, entity=FD_F,
        attrs={"interest_rate_pct": "7.0", "purpose": "children's education"},
        doc="D303", fname="farah_canara_fd_receipts.pdf", dtype="fd_receipt", vf="2026-10-31", as_of="2026-10-31"),
    rec("R305", "M301", "transaction", "insurance_claim_credit", "Term-insurance death claim settled (late husband)", 5000000,
        freq="one_time", entity=ent("ACC-CANARA-M301", "bank_account", "Canara Savings ••7702", "Canara Bank"),
        doc="D304", fname="claim_settlement_letter_2023.pdf", dtype="insurance_claim", vf="2023-08-14"),
    rec("R306", "M301", "income", "interest_income", "FD interest (reported in AIS)", 315000, freq="annual", entity=FD_F,
        doc="D305", fname="farah_AIS_FY2025-26.pdf", dtype="ais", vf="2025-04-01"),
    rec("R307", "M301", "loan", "home_loan", "Home loan — Tolichowki flat", 2800000,
        entity=ent("LOAN-HL-M301", "loan_account", "SBI Home Loan ••1185", "State Bank of India"),
        attrs={"emi": "31000", "interest_rate_pct": "8.5", "remaining_tenure_months": "140", "secured_against_entity_id": "PROP-HYD-M301"},
        doc="D306", fname="farah_home_loan_statement_oct2026.pdf", dtype="loan_statement", vf="2026-10-31", as_of="2026-10-31"),
    rec("R308", "M301", "asset", "residential_property", "Flat in Tolichowki, Hyderabad (self-occupied)", 7200000, entity=HYD,
        attrs={"self_occupied": "true"}, doc="D307", fname="tolichowki_sale_deed.pdf", dtype="property_document",
        vf="2018-02-10", as_of="2026-04-01", conf=0.8),
    rec("R309", "M301", "loan", "gold_loan", "Gold loan (bullet repayment, interest paid monthly)", 400000,
        entity=ent("LOAN-GOLD-M301", "loan_account", "Gold loan ••3390", "Muthoot Finance"),
        attrs={"emi": "3000", "repayment": "bullet", "principal_due": "2027-03-10", "interest_rate_pct": "9.0",
               "secured_against_entity_id": "GOLD-M301"},
        doc="D308", fname="farah_gold_loan_receipt.pdf", dtype="loan_statement", vf="2026-03-10", as_of="2026-10-31"),
    rec("R310", "M301", "asset", "gold_jewellery", "Gold jewellery (pledged for gold loan)", 900000, entity=GOLD_F,
        doc="D308", fname="farah_gold_loan_receipt.pdf", dtype="valuation_report", vf="2026-03-10", as_of="2026-03-10", conf=0.85),
    rec("R311", "M301", "insurance", "health_family_floater", "Family floater (Farah + children only)", 1000000,
        entity=ent("POL-FLOATER-M301", "insurance_policy", "Family floater ••5528", "Care Health"),
        attrs={"premium": "24000", "premium_frequency": "annual", "insured_member_ids": "M301,M303,M304", "cover_until": "2027-01-31"},
        doc="D309", fname="farah_health_policy.pdf", dtype="insurance_policy", vf="2026-02-01"),
    rec("R312", "M301", "insurance", "personal_accident", "Personal accident cover", 2000000,
        entity=ent("POL-PA-M301", "insurance_policy", "Personal accident policy ••0081", "Bajaj Allianz"),
        attrs={"premium": "1800", "premium_frequency": "annual"},
        doc="D310", fname="farah_pa_policy.pdf", dtype="insurance_policy", vf="2026-05-01"),
    rec("R313", "M301", "expense", "household", "Household running costs", 65000, freq="monthly",
        doc="D311", fname="farah_canara_statement_oct2026.pdf", dtype="bank_statement", vf="2026-01-01", conf=0.85),
    rec("R314", "M303", "expense", "coaching", "JEE coaching (Class 12)", 180000, freq="annual", co=["M301"],
        doc="D312", fname="ayaan_coaching_fee_receipt.pdf", dtype="fee_receipt", vf="2026-04-01"),
    rec("R315", "M304", "expense", "school_fees", "School fees, Class 6", 140000, freq="annual", co=["M301"],
        doc="D313", fname="sara_school_fee_receipt.pdf", dtype="fee_receipt", vf="2026-06-01"),
    rec("R316", "M301", "bank_balance", "savings_account", "Canara savings account", 380000,
        entity=ent("ACC-CANARA-M301", "bank_account", "Canara Savings ••7702", "Canara Bank"),
        doc="D311", fname="farah_canara_statement_oct2026.pdf", dtype="bank_statement", vf="2026-10-31", as_of="2026-10-31"),
    rec("R317", "M301", "tax", "tds_on_interest", "TDS on FD interest, FY 2025-26 (AIS)", 31500, freq="annual",
        attrs={"financial_year": "2025-26"}, doc="D305", fname="farah_AIS_FY2025-26.pdf", dtype="ais", vf="2025-04-01", vu="2026-03-31"),
    rec("R318", "M301", "tax", "advance_tax_paid", "Advance tax paid, FY 2026-27 (Q1–Q2)", 45000, freq="annual",
        attrs={"financial_year": "2026-27"}, doc="D314", fname="farah_challan_280.pdf", dtype="tax_challan", vf="2026-04-01"),
    rec("R319", "M302", "income", "family_pension", "Family pension (late husband, Railways)", 22000, freq="monthly",
        entity=ent("PEN-RLY-M302", "pension_source", "Railways family pension"),
        doc="D315", fname="zubeida_pension_slip.pdf", dtype="pension_slip", vf="2012-05-01"),
    rec("R320", "M302", "asset", "residential_property", "House in Aminabad, Lucknow (let out)", 7500000, entity=LKO,
        attrs={"self_occupied": "false"}, doc="D316", fname="aminabad_property_papers.pdf", dtype="property_document",
        vf="1994-01-01", as_of="2026-04-01", conf=0.7),
    rec("R321", "M302", "income", "rental_income", "Rent from Lucknow house", 18000, freq="monthly", entity=LKO,
        doc="D317", fname="aminabad_rent_agreement.pdf", dtype="rent_agreement", vf="2025-06-01"),
    rec("R322", "M302", "bank_balance", "savings_account", "PNB savings account", 260000,
        entity=ent("ACC-PNB-M302", "bank_account", "PNB Savings ••4419", "Punjab National Bank"),
        doc="D318", fname="zubeida_pnb_passbook.pdf", dtype="passbook", vf="2026-10-31", as_of="2026-10-31"),
    rec("R323", "M302", "expense", "medical", "Diabetes & BP medicines, check-ups (uninsured)", 9000, freq="monthly",
        doc="D318", fname="zubeida_pnb_passbook.pdf", dtype="passbook", vf="2026-01-01", conf=0.8),
    rec("R324", "M304", "investment", "sukanya_samriddhi", "Sukanya Samriddhi Account", 420000,
        entity=ent("RET-SSY-M304", "retirement_account", "Sara — Sukanya Samriddhi"),
        attrs={"liquidity": "locked", "lock_in_until": "2036-09-23", "guardian_member_id": "M301"},
        doc="D319", fname="sara_ssy_passbook.pdf", dtype="passbook", vf="2026-03-31", as_of="2026-03-31"),
    rec("R325", "M303", "bank_balance", "savings_account", "Minor savings account", 35000,
        entity=ent("ACC-MINOR-M303", "bank_account", "Ayaan — minor account ••0912", "Canara Bank"),
        doc="D320", fname="ayaan_minor_passbook.pdf", dtype="passbook", vf="2026-10-31", as_of="2026-10-31"),
]

# ======================================================================= F004 — Kapoor–Reddy household
kr_m = [
    member("M401", "Neha Kapoor", "wife", "1995-01-17", spouse="M402"),
    member("M402", "Vikram Reddy", "husband", "1993-06-30", spouse="M401", parents=["M404"]),
    member("M403", "Kabir Reddy", "son", "2026-08-10", parents=["M401", "M402"]),
    member("M404", "Lakshmi Reddy", "mother_in_law", "1965-12-02"),
]
kr_r = [
    rec("R401", "M401", "income", "salary", "Monthly salary — Orbital Commerce (on paid maternity leave to Feb 2027)", 290000,
        freq="monthly", entity=ent("EMP-ORBITAL", "employer", "Orbital Commerce Pvt Ltd"),
        attrs={"gross_or_net": "net", "maternity_leave_until": "2027-02-09"},
        doc="D401", fname="neha_payslip_oct2026.pdf", dtype="payslip", vf="2025-07-01"),
    rec("R402", "M401", "investment", "us_equity_rsu", "Vested RSUs (NASDAQ-listed parent)", 26500, cur="USD",
        entity=ent("INV-RSU-M401", "investment_portfolio", "Neha — vested RSUs (US broker)"), attrs={"next_vesting": "2027-02-15"},
        doc="D402", fname="neha_us_broker_statement_oct2026.pdf", dtype="brokerage_statement", vf="2026-10-31", as_of="2026-10-31"),
    rec("R403", "M401", "investment", "epf", "Employees' Provident Fund", 900000,
        entity=ent("RET-EPF-M401", "retirement_account", "Neha — EPF"), attrs={"liquidity": "locked"},
        doc="D403", fname="neha_epf_passbook.pdf", dtype="epf_passbook", vf="2026-10-31", as_of="2026-10-31"),
    rec("R404", "M401", "investment", "mutual_funds", "Mutual fund portfolio (CAS)", 1150000,
        entity=ent("INV-CAS-M401", "investment_portfolio", "Neha — MF portfolio (CAS)"),
        doc="D404", fname="neha_cas_oct2026.pdf", dtype="cas_statement", vf="2026-10-31", as_of="2026-10-31"),
    rec("R405", "M401", "tax", "tds_on_salary", "TDS on salary, FY 2025-26 (AIS)", 820000, freq="annual",
        attrs={"financial_year": "2025-26", "schedule_fa_required": "true"},
        doc="D405", fname="neha_AIS_FY2025-26.pdf", dtype="ais", vf="2025-04-01", vu="2026-03-31"),
    rec("R406", "M401", "bank_balance", "savings_account", "HDFC salary account", 1450000,
        entity=ent("ACC-HDFC-M401", "bank_account", "HDFC Savings ••3318", "HDFC Bank"),
        doc="D406", fname="neha_hdfc_statement_oct2026.pdf", dtype="bank_statement", vf="2026-10-31", as_of="2026-10-31"),
    rec("R407", "M402", "income", "salary", "Monthly salary — Paygrid Technologies", 240000, freq="monthly",
        entity=ent("EMP-PAYGRID", "employer", "Paygrid Technologies"), attrs={"gross_or_net": "net"},
        doc="D407", fname="vikram_payslip_aug2026_paygrid.pdf", dtype="payslip", vf="2024-10-01"),
    rec("R408", "M402", "income", "salary", "Monthly salary — Lumen Fintech (new job)", 310000, freq="monthly",
        entity=ent("EMP-LUMEN", "employer", "Lumen Fintech Pvt Ltd"), attrs={"gross_or_net": "net"},
        doc="D408", fname="vikram_offer_and_payslip_oct2026_lumen.pdf", dtype="payslip", vf="2026-09-01"),
    rec("R409", "M402", "investment", "crypto", "Crypto holdings (exchange wallet)", 300000,
        entity=ent("INV-CRYPTO-M402", "investment_portfolio", "Vikram — crypto wallet"),
        doc="D409", fname="vikram_exchange_statement.pdf", dtype="exchange_statement", vf="2026-10-31", as_of="2026-10-31", conf=0.9),
    rec("R410", "M402", "loan", "personal_loan", "Personal loan taken for the wedding", 600000,
        entity=ent("LOAN-PL-M402", "loan_account", "Personal loan ••2201", "Axis Bank"),
        attrs={"emi": "19500", "interest_rate_pct": "12.5", "remaining_tenure_months": "30"},
        doc="D410", fname="vikram_pl_statement_oct2026.pdf", dtype="loan_statement", vf="2026-10-31", as_of="2026-10-31"),
    rec("R411", "M402", "liability", "credit_card", "Credit card outstanding (statement balance)", 85000,
        entity=ent("CC-M402", "credit_card", "Credit card ••7765", "Axis Bank"),
        doc="D411", fname="vikram_cc_statement_oct2026.pdf", dtype="card_statement", vf="2026-10-31", as_of="2026-10-31"),
    rec("R412", "M402", "investment", "mutual_funds", "Mutual fund portfolio (CAS)", 640000,
        entity=ent("INV-CAS-M402", "investment_portfolio", "Vikram — MF portfolio (CAS)"),
        doc="D412", fname="vikram_cas_oct2026.pdf", dtype="cas_statement", vf="2026-10-31", as_of="2026-10-31"),
    rec("R413", "M402", "insurance", "term_life", "Term life cover", 15000000,
        entity=ent("POL-TERM-M402", "insurance_policy", "Term policy ••4410", "HDFC Life"),
        attrs={"premium": "21000", "premium_frequency": "annual", "nominee_member_id": "M401", "cover_until": "2053-06-30"},
        doc="D413", fname="vikram_term_policy.pdf", dtype="insurance_policy", vf="2025-03-01"),
    rec("R414", "M402", "insurance", "group_health", "Employer group health cover — Paygrid", 500000,
        entity=ent("POL-GRP-PAYGRID", "insurance_policy", "Paygrid group health"),
        attrs={"premium": "0", "premium_frequency": "annual", "insured_member_ids": "M402,M401", "employer_provided": "true"},
        doc="D414", fname="paygrid_group_health_ecard.pdf", dtype="insurance_policy", vf="2024-10-01", vu="2026-08-31"),
    rec("R415", "M402", "insurance", "group_health", "Employer group health cover — Lumen (incl. newborn)", 1000000,
        entity=ent("POL-GRP-LUMEN", "insurance_policy", "Lumen group health"),
        attrs={"premium": "0", "premium_frequency": "annual", "insured_member_ids": "M402,M401,M403", "employer_provided": "true"},
        doc="D415", fname="lumen_group_health_ecard.pdf", dtype="insurance_policy", vf="2026-09-01"),
    rec("R416", "M402", "expense", "parent_support", "Monthly support to mother (medicines & help)", 12000, freq="monthly",
        attrs={"beneficiary_member_id": "M404"},
        doc="D416", fname="vikram_icici_statement_oct2026.pdf", dtype="bank_statement", vf="2025-01-01", conf=0.88),
    rec("R417", "M402", "expense", "rent", "Rent, HSR Layout flat", 55000, freq="monthly", co=["M401"],
        doc="D417", fname="hsr_rent_agreement_2026.pdf", dtype="rent_agreement", vf="2026-03-01"),
    rec("R418", "M401", "expense", "household", "Household running costs", 70000, freq="monthly", co=["M402"],
        doc="D406", fname="neha_hdfc_statement_oct2026.pdf", dtype="bank_statement", vf="2026-01-01", conf=0.85),
    rec("R419", "M403", "expense", "childcare", "Nanny & paediatric visits for Kabir", 35000, freq="monthly", co=["M401", "M402"],
        doc="D406", fname="neha_hdfc_statement_oct2026.pdf", dtype="bank_statement", vf="2026-09-01", conf=0.85),
    rec("R420", "M402", "bank_balance", "savings_account", "ICICI salary account", 380000,
        entity=ent("ACC-ICICI-M402", "bank_account", "ICICI Savings ••5130", "ICICI Bank"),
        doc="D416", fname="vikram_icici_statement_oct2026.pdf", dtype="bank_statement", vf="2026-10-31", as_of="2026-10-31"),
    rec("R421", "M403", "investment", "mutual_funds", "Kabir's first SIP (minor folio)", 50000,
        entity=ent("INV-MF-M403", "investment_portfolio", "Kabir — minor MF folio"), attrs={"guardian_member_id": "M401"},
        doc="D418", fname="kabir_minor_folio.pdf", dtype="cas_statement", vf="2026-10-31", as_of="2026-10-31"),
    rec("R422", "M404", "asset", "residential_property", "Flat in Kukatpally, Hyderabad (self-occupied)", 6000000,
        entity=ent("PROP-KUKATPALLY", "property", "Kukatpally flat, Hyderabad"), attrs={"self_occupied": "true"},
        doc="D419", fname="kukatpally_sale_deed.pdf", dtype="property_document", vf="2004-06-15", as_of="2026-04-01", conf=0.75),
    rec("R423", "M404", "insurance", "health_individual", "Individual health policy (premium paid by Vikram)", 500000,
        entity=ent("POL-HEALTH-M404", "insurance_policy", "Health policy ••6620", "Star Health"),
        attrs={"premium": "28000", "premium_frequency": "annual", "insured_member_ids": "M404", "paid_by_member_id": "M402",
               "pre_existing_waiting_until": "2027-04-01"},
        doc="D420", fname="lakshmi_health_policy.pdf", dtype="insurance_policy", vf="2024-04-01"),
    rec("R424", "M404", "investment", "fixed_deposit", "Bank FD", 700000,
        entity=ent("DEP-FD-M404", "deposit", "Lakshmi — SBI FD", "State Bank of India"),
        doc="D421", fname="lakshmi_fd_receipt.pdf", dtype="fd_receipt", vf="2026-10-31", as_of="2026-10-31"),
    rec("R425", "M404", "income", "interest_income", "FD interest (AIS)", 49000, freq="annual",
        entity=ent("DEP-FD-M404", "deposit", "Lakshmi — SBI FD", "State Bank of India"),
        doc="D422", fname="lakshmi_AIS_FY2025-26.pdf", dtype="ais", vf="2025-04-01"),
    rec("R426", "M404", "expense", "medical", "Knee pain treatment & physiotherapy", 6000, freq="monthly",
        doc="D423", fname="lakshmi_sbi_passbook.pdf", dtype="passbook", vf="2026-06-01", conf=0.8),
]

FAMILIES = {
    "F002": (family("F002", iyer_m, iyer_r), {
        "M201": {"share_with_family": True, "private_record_ids": []},
        "M202": {"share_with_family": True, "private_record_ids": []},
        "M203": {"share_with_family": True, "private_record_ids": []},
        "M204": {"share_with_family": True, "private_record_ids": ["R240"]},
        "M205": {"share_with_family": True, "private_record_ids": []},
        "M206": {"share_with_family": True, "private_record_ids": []},
        "M207": {"share_with_family": False, "private_record_ids": []},
    }),
    "F003": (family("F003", khan_m, khan_r), {m["member_id"]: {"share_with_family": True, "private_record_ids": []} for m in khan_m}),
    "F004": (family("F004", kr_m, kr_r), {
        "M401": {"share_with_family": True, "private_record_ids": []},
        "M402": {"share_with_family": True, "private_record_ids": ["R409"]},
        "M403": {"share_with_family": True, "private_record_ids": []},
        "M404": {"share_with_family": True, "private_record_ids": []},
    }),
}

INDEX = [
    {"family_id": "F001", "name": "Mehta family", "city": "Pune", "default_member_id": "M003",
     "summary": "Three earners, one home loan, father close to retirement. The golden sample for Contract A.",
     "questions": ["Can our family afford to buy a ₹1.5 crore house next year?",
                   "What happens if father retires next year?",
                   "Which family member contributes the most to our current household income?"]},
    {"family_id": "F002", "name": "Iyer joint family", "city": "Chennai", "default_member_id": "M203",
     "summary": "Three generations, seven members: pensions, a let-out flat, a daughter studying in Toronto and an uncle who keeps his finances private.",
     "questions": ["If Appa needs a ₹15 lakh heart surgery, how should we pay for it?",
                   "Can we fund Rohan's engineering abroad in 4 years while Ananya's education loan is still running?",
                   "Who in our family is under-insured?",
                   "Does anything in our AIS look inconsistent with what we filed?"]},
    {"family_id": "F003", "name": "Khan family", "city": "Hyderabad", "default_member_id": "M301",
     "summary": "A widowed single parent with a boutique business, her mother-in-law and two school-going children.",
     "questions": ["Can I afford Ayaan's engineering college fees of ₹18 lakh over 4 years?",
                   "Am I adequately insured as the only earning parent?",
                   "What happens if boutique income drops by 30%?"]},
    {"family_id": "F004", "name": "Kapoor–Reddy household", "city": "Bengaluru", "default_member_id": "M401",
     "summary": "A young two-income couple with a newborn, a recent job change and a dependent mother in another city.",
     "questions": ["Should we buy a ₹1.2 crore flat in 2 years or keep renting?",
                   "How have our finances changed since Kabir was born and Vikram switched jobs?",
                   "Can we support Vikram's mother's ₹4 lakh knee surgery?"]},
]

if __name__ == "__main__":
    for fid, (data, policies) in FAMILIES.items():
        (OUT / f"{fid}.financial.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))
        (OUT / f"{fid}.access.json").write_text(json.dumps(
            {"_comment": "Owned by the Context Engine. Consent each member has given for sharing with the family.",
             "family_id": fid, "policies": policies}, indent=2))
        print(fid, len(data["members"]), "members,", len(data["financial_records"]), "records")
    (OUT / "families.json").write_text(json.dumps(INDEX, indent=2, ensure_ascii=False))
    print("families.json:", [f["family_id"] for f in INDEX])
