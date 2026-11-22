"""Neo4j mirror of the family context graph.

The in-memory context engine stays the source of truth; Neo4j is a queryable mirror used for
multi-hop reasoning (by the agent) and for visual exploration (Neo4j Browser, :7474).

Privacy: only records every family member is allowed to see (consented for family sharing) are
written to the shared graph. A member's private records never reach Neo4j, so agent-written Cypher
cannot leak them. Owners still see their private records through the access-controlled tools.

If Neo4j is unreachable the app keeps working; graph tools report that the graph is unavailable.
"""
from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger("familyos.neo4j")

URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
USER = os.environ.get("NEO4J_USER", "neo4j")
PASSWORD = os.environ.get("NEO4J_PASSWORD", "familyos-demo")
ENABLED = os.environ.get("FAMILYOS_NEO4J", "1") != "0"

ENTITY_LABEL = {
    "employer": "Employer", "bank_account": "BankAccount", "loan_account": "LoanAccount",
    "investment_portfolio": "InvestmentPortfolio", "property": "Property", "insurance_policy": "InsurancePolicy",
    "income": "IncomeStream", "expense": "ExpenseStream", "tax": "TaxRecord", "liability": "Liability",
    "pension_source": "PensionSource", "business": "Business", "deposit": "Deposit", "retirement_account": "RetirementAccount",
    "vehicle": "Vehicle", "precious_metal": "Gold", "credit_card": "CreditCard", "transaction": "TransactionStream",
}

SCHEMA_DOC = """Graph schema (all nodes carry family_id):
(:Family {family_id, name})-[:HAS_MEMBER]->(:Member {member_id, name, relationship, age})
(:Member)-[:SPOUSE_OF|PARENT_OF|SIBLING_OF|GRANDPARENT_OF|SUPPORTS]->(:Member)
(:Member)-[:EARNS_FROM|EARNS|RUNS|OWNS|CO_OWNS|OWES|CO_OWES|INSURED_BY|COVERED_BY|NOMINEE_OF|PAYS_FOR|GUARDIAN_OF|SPENDS_ON|CO_SPENDS_ON|HAS]->(:Entity)
(:Entity) also has one label of: Employer, PensionSource, Business, BankAccount, Deposit, InvestmentPortfolio, RetirementAccount,
  LoanAccount, CreditCard, Property, Vehicle, Gold, InsurancePolicy, IncomeStream, ExpenseStream, TaxRecord
  props: entity_id, name, entity_type, institution, current_amount (float, INR), current_record_id
(:Entity:LoanAccount)-[:SECURED_AGAINST]->(:Entity)   (property, vehicle, gold, business)
(:Entity)-[:HAS_RECORD]->(:Record {record_id, type, category, description, amount (float INR), frequency, status (current|superseded|ended|event),
  effective_from, effective_until, emi (float, loans), source_document, confidence})
(:Record)-[:SUPERSEDED_BY]->(:Record)
(:Family)-[:HAS_GOAL]->(:Goal {kind, label, amount, target_date, set_by})
Only family-shared records are in the graph. Always filter with family_id: $family_id."""

_driver = None
_last_fail = 0.0
_status: dict[str, Any] = {"connected": False, "error": None, "last_sync": None, "nodes": 0, "relationships": 0}
_family_stats: dict[str, dict] = {}

_WRITE = re.compile(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV|FOREACH|CALL\s+(dbms|db\.create|apoc\.(create|merge|refactor|periodic)))\b", re.I)


def driver():
    """Lazy driver; after a failure, retries at most every 20s so a down Neo4j never slows requests."""
    global _driver, _last_fail
    if not ENABLED:
        return None
    if _driver is not None:
        return _driver
    if time.time() - _last_fail < 20:
        return None
    try:
        from neo4j import GraphDatabase
        d = GraphDatabase.driver(URI, auth=(USER, PASSWORD), connection_timeout=2, max_transaction_retry_time=2)
        d.verify_connectivity()
        _driver = d
        _status.update(connected=True, error=None)
        return d
    except Exception as e:
        _last_fail = time.time()
        _status.update(connected=False, error=str(e)[:200])
        log.warning("Neo4j unavailable: %s", e)
        return None


def status(family_id: Optional[str] = None) -> dict:
    driver()
    out = dict(_status, uri=URI, browser="http://localhost:7474", enabled=ENABLED)
    if family_id and family_id in _family_stats:
        out.update(_family_stats[family_id], family_id=family_id)
    return out


def _shared_facts(ctx) -> list:
    return [f for f in ctx.facts.values() if all(ctx.can_view(m, f) for m in ctx.members)]


def sync(ctx) -> Optional[dict]:
    """Rebuild this family's subgraph from the context engine (small graph → full rebuild is simplest and safe)."""
    global _driver
    d = driver()
    if d is None:
        return None
    from .context_engine import TODAY
    fam = ctx.family_id
    if fam.startswith("P"):  # real-person data never goes into the shared graph database
        with d.session() as s:
            s.run("MATCH (n {family_id: $f}) DETACH DELETE n", f=fam).consume()
        return None
    facts = _shared_facts(ctx)
    fact_ids = {f.record.record_id for f in facts}
    ent_ids = {f.entity_id for f in facts}
    members = []
    for m in ctx.members.values():
        age = None
        if m.date_of_birth:
            age = TODAY.year - m.date_of_birth.year - ((TODAY.month, TODAY.day) < (m.date_of_birth.month, m.date_of_birth.day))
        members.append({"member_id": m.member_id, "name": m.name, "relationship": m.relationship, "age": age})
    entities = []
    for eid in ent_ids:
        e = ctx.entities[eid]
        cur = [ctx.facts[r] for r in e.record_ids if r in fact_ids and ctx.facts[r].status == "current"]
        latest = cur[-1].record if cur else None
        entities.append({"entity_id": eid, "label": ENTITY_LABEL.get(e.entity_type, "Asset"), "name": e.name,
                         "entity_type": e.entity_type, "institution": e.institution,
                         "current_amount": float(latest.value) if latest and latest.value is not None else None,
                         "current_record_id": latest.record_id if latest else None})
    records = []
    for f in facts:
        r = f.record
        records.append({"record_id": r.record_id, "entity_id": f.entity_id, "type": r.type, "category": r.category,
                        "description": r.description, "amount": float(r.value) if r.value is not None else None,
                        "frequency": r.frequency, "status": f.status,
                        "effective_from": str(f.effective_from), "effective_until": str(f.effective_until) if f.effective_until else None,
                        "emi": float(r.attr_decimal("emi")) if r.attr_decimal("emi") is not None else None,
                        "source_document": r.source.filename, "confidence": r.confidence, "superseded_by": f.superseded_by})
    member_ids = set(ctx.members)
    rels = [{"from": x["from"], "to": x["to"], "type": x["type"].upper()} for x in ctx.relationships
            if x["type"] != "has_member" and (x["from"] in member_ids or x["from"] in ent_ids) and (x["to"] in member_ids or x["to"] in ent_ids)]
    try:
        with d.session() as s:
            s.run("MATCH (n {family_id: $f}) DETACH DELETE n", f=fam).consume()
            s.run("MERGE (fam:Family {family_id: $f}) SET fam.name = $name", f=fam,
                  name=f"{next(iter(ctx.members.values())).name.split()[-1]} family").consume()
            s.run("""UNWIND $ms AS m
                     MATCH (fam:Family {family_id: $f})
                     CREATE (x:Member {family_id: $f}) SET x += m
                     CREATE (fam)-[:HAS_MEMBER]->(x)""", ms=members, f=fam).consume()
            for label in {e["label"] for e in entities}:
                s.run(f"""UNWIND $es AS e
                          CREATE (x:Entity:{label} {{family_id: $f}})
                          SET x += {{entity_id: e.entity_id, name: e.name, entity_type: e.entity_type, institution: e.institution,
                                     current_amount: e.current_amount, current_record_id: e.current_record_id}}""",
                      es=[e for e in entities if e["label"] == label], f=fam).consume()
            s.run("""UNWIND $rs AS r
                     MATCH (e:Entity {family_id: $f, entity_id: r.entity_id})
                     CREATE (x:Record {family_id: $f})
                     SET x += {record_id: r.record_id, type: r.type, category: r.category, description: r.description,
                               amount: r.amount, frequency: r.frequency, status: r.status, effective_from: r.effective_from,
                               effective_until: r.effective_until, emi: r.emi, source_document: r.source_document,
                               confidence: r.confidence}
                     CREATE (e)-[:HAS_RECORD]->(x)""", rs=records, f=fam).consume()
            s.run("""UNWIND $rs AS r WITH r WHERE r.superseded_by IS NOT NULL
                     MATCH (a:Record {family_id: $f, record_id: r.record_id}), (b:Record {family_id: $f, record_id: r.superseded_by})
                     CREATE (a)-[:SUPERSEDED_BY]->(b)""", rs=records, f=fam).consume()
            s.run("""UNWIND $gs AS g
                     MATCH (fam:Family {family_id: $f})
                     CREATE (x:Goal {family_id: $f}) SET x += {kind: g.kind, label: g.label, amount: toFloat(g.amount),
                                                               target_date: g.target_date, set_by: g.set_by}
                     CREATE (fam)-[:HAS_GOAL]->(x)""", gs=ctx.goals, f=fam).consume()
            for t in {x["type"] for x in rels}:
                s.run(f"""UNWIND $rs AS r
                          MATCH (a {{family_id: $f}}) WHERE a.member_id = r.from OR a.entity_id = r.from
                          MATCH (b {{family_id: $f}}) WHERE b.member_id = r.to OR b.entity_id = r.to
                          CREATE (a)-[:{t}]->(b)""", rs=[x for x in rels if x["type"] == t], f=fam).consume()
            c = s.run("MATCH (n {family_id: $f}) OPTIONAL MATCH (n)-[r]->() RETURN count(DISTINCT n) AS n, count(r) AS r", f=fam).single()
        stats = {"last_sync": datetime.now(timezone.utc).isoformat(timespec="seconds"), "nodes": c["n"],
                 "relationships": c["r"], "private_records_excluded": len(ctx.facts) - len(facts)}
        _family_stats[fam] = stats
        _status.update(connected=True, error=None, **stats)
        return dict(_status)
    except Exception as e:
        log.warning("Neo4j sync failed: %s", e)
        _status.update(connected=False, error=str(e)[:200])
        try:
            d.close()
        except Exception:
            pass
        _driver = None
        return None


def read_query(cypher: str, family_id: str, params: dict | None = None, limit: int = 50) -> dict:
    """Run agent-written Cypher in a READ transaction. Writes are rejected twice: by keyword and by access mode."""
    if _WRITE.search(cypher):
        raise ValueError("Only read queries are allowed (MATCH/OPTIONAL MATCH/WITH/WHERE/RETURN/ORDER BY/LIMIT).")
    d = driver()
    if d is None:
        raise RuntimeError("Neo4j graph is unavailable right now; use the other tools.")
    from neo4j import READ_ACCESS, unit_of_work

    @unit_of_work(timeout=5)
    def work(tx):
        res = tx.run(cypher, family_id=family_id, **(params or {}))
        return [r.data() for r in res][:limit], res.keys()

    with d.session(default_access_mode=READ_ACCESS) as s:
        rows, keys = s.execute_read(work)
    return {"columns": list(keys), "rows": rows, "row_count": len(rows), "truncated_to": limit}


DEPENDENCY_QUERY = """
MATCH (m:Member {family_id: $family_id, member_id: $member_id})
OPTIONAL MATCH (m)-[r1]->(e:Entity)
OPTIONAL MATCH (other:Member)-[r2]->(e) WHERE other <> m
OPTIONAL MATCH (e)-[:SECURED_AGAINST]->(p:Entity)
OPTIONAL MATCH (e)-[:HAS_RECORD]->(rec:Record {status: 'current'})
WITH m, e, type(r1) AS link,
     collect(DISTINCT CASE WHEN other IS NOT NULL THEN {member: other.name, link: type(r2)} END) AS shared_with,
     collect(DISTINCT p.name) AS secured_against, collect(DISTINCT {record_id: rec.record_id, amount: rec.amount, emi: rec.emi, frequency: rec.frequency}) AS records
RETURN e.name AS entity, labels(e) AS kind, link, shared_with, secured_against, records
ORDER BY link
"""

FAMILY_LINKS_QUERY = """
MATCH (m:Member {family_id: $family_id, member_id: $member_id})
OPTIONAL MATCH (m)-[r]-(o:Member)
RETURN o.name AS member, o.relationship AS role, o.age AS age, type(r) AS link,
       CASE WHEN startNode(r) = m THEN 'outgoing' ELSE 'incoming' END AS direction
"""


def member_dependencies(family_id: str, member_id: str) -> dict:
    deps = read_query(DEPENDENCY_QUERY, family_id, {"member_id": member_id})
    fam = read_query(FAMILY_LINKS_QUERY, family_id, {"member_id": member_id})
    return {"member_id": member_id, "family_links": fam["rows"], "financial_links": deps["rows"],
            "cypher": DEPENDENCY_QUERY.strip()}
