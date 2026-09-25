"""Versioned contracts. Unknown facts stay null; entity types never share a table."""
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Permission(str, Enum):
    ALLOWED = "ALLOWED"
    CONDITIONAL = "CONDITIONAL"
    PROHIBITED = "PROHIBITED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class Rights(Model):
    license: str
    license_id: str
    commercial_use: Permission
    redistribution_allowed: Permission
    derivative_allowed: Permission
    attribution_required: bool | None
    raw_data_allowed: Permission = Permission.REVIEW_REQUIRED
    rights_status: str
    rights_scope: str
    terms_url: str


class FactorConcept(Model):
    canonical_factor_id: str
    canonical_name: str
    short_id: str
    aliases: list[str]
    description: str | None
    economic_logic: str | None
    category: str
    scope: str
    created_at: str
    updated_at: str


class FactorVariant(Rights):
    canonical_factor_id: str
    canonical_name: str
    factor_concept: str
    factor_variant_id: str
    variant_name: str
    aliases: list[str]
    description: str
    economic_logic: str | None
    category: str
    raw_formula: str | None
    normalized_formula: str | None
    formula_ast: dict | None
    formula_id: str | None
    dialect: str | None
    parameters: dict
    required_fields: list[str]
    required_fields_status: str
    lookback: dict | None
    frequency: str | None
    asset_class: str
    universe: str | None
    holding_period: dict | None
    rebalance: str | None
    source_id: str
    source_name: str
    source_url: str
    source_record_ids: list[str]
    source_native_ids: list[str]
    source_sha256: str
    source_revision: str | None
    source_locator: str
    paper_title: str | None
    paper_year: int | None
    authors: list[str]
    paper_ids: list[str]
    code_url: str | None
    quality_status: Literal["CURATED_DEFINITION"]
    semantic_status: Literal["NOT_VERIFIED"] = "NOT_VERIFIED"
    backtest_ready: Literal[False] = False
    issue_codes: list[str]
    created_at: str
    updated_at: str


class Formula(Model):
    formula_id: str
    raw_formula: str
    normalized_formula: str
    formula_ast: dict
    dialect: str
    semantic_status: str
    source_record_ids: list[str]


class Paper(Model):
    paper_id: str
    title: str | None
    year: int | None
    authors: list[str]
    author_ids: list[str]
    url: str | None
    citation_label: str
    metadata_status: Literal["TITLE_PRESENT", "PARTIAL_CITATION", "COLLECTION_REFERENCE"]
    provenance: list[dict]


class Author(Model):
    author_id: str
    name: str
    identity_status: Literal["UNRESOLVED_CITATION_NAME"]
    namespace: str


class Source(Model):
    source_id: str
    source_name: str
    url: str
    license_id: str
    revisions: list[str]
    collected_at: str
    storage_policy: str


class License(Rights):
    evidence_urls: list[str]
    reviewed_at: str
    notes: str


class Dataset(Model):
    dataset_id: str
    name: str
    source_id: str
    content_type: str
    revision: str | None
    license_id: str
    source_url: str
    observations_ingested: Literal[False] = False


class Implementation(Model):
    implementation_id: str
    factor_variant_id: str
    source_record_id: str
    code_url: str
    revision: str | None
    sha256: str
    source_locator: str
    language: str
    status: str
    license: str
    terms_url: str
    commercial_use: Permission
    executed: Literal[False] = False


class Strategy(Model):
    strategy_id: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    description: str
    entry_rules: list[dict] = Field(default_factory=list)
    exit_rules: list[dict] = Field(default_factory=list)
    position_sizing: dict | None = None
    risk_management: dict | None = None
    asset_class: list[str] = Field(default_factory=list)
    universe: str | None = None
    frequency: str | None = None
    rebalance: str | None = None
    factor_ids: list[str] = Field(default_factory=list)
    source: list[dict]
    paper: list[str] = Field(default_factory=list)
    code: list[dict] = Field(default_factory=list)
    original_backtest: list[str] = Field(default_factory=list)
    reproduced_backtest: list[str] = Field(default_factory=list)
    external_namespace: str
    external_id: str
    spec_sha256: str
    status: str
    created_at: str
    updated_at: str


class StrategyFactor(Model):
    strategy_id: str
    factor_id: str
    variant_id: str
    role: Literal["signal", "entry", "exit", "filter", "weight", "risk", "exposure"]
    confidence: float = Field(ge=0, le=1)
    evidence: str = Field(min_length=1)
    source: str = Field(min_length=1)
    attribution_status: Literal["RULE_LINK_ONLY", "EMPIRICALLY_TESTED"] = "RULE_LINK_ONLY"
    backtest_result_id: str | None = None

    @model_validator(mode="after")
    def attribution_requires_result(self):
        if self.attribution_status == "EMPIRICALLY_TESTED" and not self.backtest_result_id:
            raise ValueError("Empirical attribution requires a BacktestResult reference")
        return self


class BacktestResult(Model):
    backtest_result_id: str
    strategy_id: str
    result_kind: Literal["ORIGINAL_REPORTED", "LAB_REPRODUCED"]
    research_project: str
    artifact_uri: str
    artifact_sha256: str
    contract_uri: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    validation_status: str
    created_at: str


class Relationship(Model):
    relationship_id: str
    relation: Literal["SAME_AS", "ALIAS_OF", "VARIANT_OF", "DERIVED_FROM", "RELATED_TO", "IMPLEMENTATION_OF", "USES_FACTOR", "DESCRIBED_BY", "IMPLEMENTED_BY", "TESTED_ON", "SOURCED_FROM", "AUTHORED_BY"]
    from_id: str
    from_type: str
    to_id: str
    to_type: str
    confidence: float = Field(ge=0, le=1)
    evidence: str
    source: str
    status: Literal["CONFIRMED", "REVIEW_REQUIRED"]


ENTITY_MODELS = {
    "factor_concepts": FactorConcept, "factor_variants": FactorVariant,
    "formulas": Formula, "papers": Paper, "authors": Author,
    "sources": Source, "licenses": License, "datasets": Dataset,
    "implementations": Implementation, "strategies": Strategy,
    "strategy_factor": StrategyFactor, "backtest_results": BacktestResult,
    "relationships": Relationship,
}
