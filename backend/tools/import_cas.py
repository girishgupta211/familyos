"""Import an NSDL CAS PDF as a PRIVATE FamilyOS family (never committed, never served through the public tunnel).

    .venv/bin/python tools/import_cas.py /path/to/nsdl_cas.pdf P001 "My family (live CAS)"
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.cas_nsdl import parse, to_contract_a          # noqa: E402
from app.contract import FamilyFinancialData            # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"

pdf, fid, label = sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None
assert fid.startswith("P"), "private family ids must start with P (git-ignored, local-only)"
cas = parse(pdf)
r = cas.reconciliation
if r["grand_total_parsed"] != r["grand_total_statement"]:
    sys.exit(f"Refusing to import: parsed total {r['grand_total_parsed']} != statement total {r['grand_total_statement']}")
payload = to_contract_a(cas, fid, f"{fid}-M1", Path(pdf).name)
FamilyFinancialData.model_validate(payload)
(DATA / f"{fid}.financial.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))
(DATA / f"{fid}.access.json").write_text(json.dumps({"family_id": fid, "policies": {f"{fid}-M1": {"share_with_family": True, "private_record_ids": []}}}, indent=2))
idx_path = DATA / "private_families.json"
idx = json.loads(idx_path.read_text()) if idx_path.exists() else []
idx = [f for f in idx if f["family_id"] != fid] + [{
    "family_id": fid, "name": label or f"{cas.holder_name} (live CAS)", "city": None, "default_member_id": f"{fid}-M1",
    "private": True,
    "summary": f"Real NSDL CAS as of {cas.as_of:%d %b %Y}: {len(cas.holdings)} holdings reconciled to the statement total. Local only.",
    "questions": ["How is my portfolio split across stocks, mutual funds and bonds?",
                  "Which of my holdings carry the most concentration or credit risk?",
                  "Where am I sitting on the biggest unrealised gains and losses?"]}]
idx_path.write_text(json.dumps(idx, indent=2, ensure_ascii=False))
print(f"Imported {fid}: {len(payload['financial_records'])} records, total ₹{r['grand_total_parsed']:,} (matches statement)")
