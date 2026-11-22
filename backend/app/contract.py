"""Contract A — Financial Data Engine -> Context Engine (schema_version 1.0).

This is the ONLY coupling point with the Financial Data Engine. The context engine never
reads the extractor's database; it consumes payloads that validate against these models.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RecordType = Literal[
    "income", "expense", "bank_balance", "investment", "insurance",
    "loan", "asset", "liability", "transaction", "tax",
]
Frequency = Literal["monthly", "quarterly", "annual", "one_time"]


class MemberRelation(BaseModel):
    type: str          # e.g. grandparent_of, guardian_of, sibling_of
    member_id: str


class Member(BaseModel):
    model_config = ConfigDict(extra="allow")
    member_id: str
    name: str
    relationship: str  # role label: father | mother | son | daughter_in_law | grandfather | ...
    date_of_birth: Optional[date] = None
    # Optional explicit links (additive in v1.0). When any member has them, they replace role-word inference.
    spouse_id: Optional[str] = None
    parent_ids: list[str] = Field(default_factory=list)
    other_relations: list[MemberRelation] = Field(default_factory=list)


class Source(BaseModel):
    model_config = ConfigDict(extra="allow")
    document_id: str
    filename: str
    document_type: Optional[str] = None
    page: Optional[int] = None


class EntityRef(BaseModel):
    model_config = ConfigDict(extra="allow")
    entity_id: Optional[str] = None
    entity_type: str  # employer | bank_account | loan_account | investment_portfolio | property | insurance_policy
    name: str
    institution: Optional[str] = None


class FinancialRecord(BaseModel):
    model_config = ConfigDict(extra="allow")
    record_id: str
    member_id: str
    co_owner_ids: list[str] = Field(default_factory=list)
    type: RecordType
    category: str
    description: Optional[str] = None
    # Decimal-safe: the wire format is a string. None means UNKNOWN, never zero.
    amount: Optional[str]
    currency: str
    frequency: Optional[Frequency] = None
    entity: Optional[EntityRef] = None
    attributes: dict[str, str] = Field(default_factory=dict)
    source: Source
    valid_from: date
    valid_until: Optional[date] = None
    as_of: Optional[date] = None
    confidence: float = Field(ge=0, le=1)
    supersedes: Optional[str] = None  # optional explicit hint from the extractor

    @field_validator("amount")
    @classmethod
    def _decimal_string(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        try:
            Decimal(v)
        except InvalidOperation as e:
            raise ValueError(f"amount must be a decimal string, got {v!r}") from e
        return v

    @field_validator("currency")
    @classmethod
    def _iso_currency(cls, v: str) -> str:
        if len(v) != 3 or not v.isupper():
            raise ValueError("currency must be an ISO-4217 code, e.g. INR")
        return v

    @property
    def value(self) -> Optional[Decimal]:
        return Decimal(self.amount) if self.amount is not None else None

    def attr_decimal(self, key: str) -> Optional[Decimal]:
        raw = self.attributes.get(key)
        return Decimal(raw) if raw not in (None, "") else None


class FamilyFinancialData(BaseModel):
    model_config = ConfigDict(extra="allow")
    schema_version: Literal["1.0"]
    family_id: str
    members: list[Member]
    financial_records: list[FinancialRecord]

    @model_validator(mode="after")
    def _referential_integrity(self) -> "FamilyFinancialData":
        ids = {m.member_id for m in self.members}
        for m in self.members:
            linked = ([m.spouse_id] if m.spouse_id else []) + m.parent_ids + [x.member_id for x in m.other_relations]
            bad = [x for x in linked if x not in ids or x == m.member_id]
            if bad:
                raise ValueError(f"member {m.member_id} links to unknown or self member(s) {bad}")
        seen: set[str] = set()
        for r in self.financial_records:
            if r.record_id in seen:
                raise ValueError(f"duplicate record_id {r.record_id}")
            seen.add(r.record_id)
            for owner in [r.member_id, *r.co_owner_ids]:
                if owner not in ids:
                    raise ValueError(f"record {r.record_id} references unknown member {owner}")
        return self


class RecordBatch(BaseModel):
    """Incremental push from the Financial Data Engine (e.g. a newly processed document)."""
    schema_version: Literal["1.0"]
    family_id: str
    financial_records: list[FinancialRecord]
