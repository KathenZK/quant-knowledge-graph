"""Versioned, scope-specific evidence. Collection is never a license grant."""
from datetime import datetime
import re
import math
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, str_strip_whitespace=True)

    @model_validator(mode='after')
    def timestamps_have_zones(self):
        for name in type(self).model_fields:
            value=getattr(self,name)
            if isinstance(value,datetime) and value.tzinfo is None:
                raise ValueError('Evidence timestamps require an explicit timezone')
        return self


class EvidenceArtifact(StrictModel):
    uri: str = Field(min_length=1)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class SourceEvidence(StrictModel):
    source_type: Literal['ACADEMIC_PAPER','AUTHOR_WEBSITE','OFFICIAL_DOCUMENTATION','BROKER_RESEARCH',
        'OPEN_SOURCE_IMPLEMENTATION','COMMUNITY_POST','SECONDARY_SUMMARY','INDICATOR_DOCUMENTATION','BOT_DERIVED','UNKNOWN']
    source_evidence_level: Literal['PRIMARY','SECONDARY','TERTIARY','UNKNOWN']
    source_support_type: Literal['EXACT_STRATEGY','STRATEGY_FRAMEWORK','INDICATOR_DEFINITION',
        'PARAMETER_GUIDANCE','IMPLEMENTATION_EXAMPLE','RELATED_RESEARCH','NO_DIRECT_SUPPORT','UNKNOWN']
    url: str = Field(pattern=r'^https?://')
    version: str = Field(min_length=1)
    artifact: EvidenceArtifact
    supported_rule_components: dict[str,str]
    unsupported_rule_components: dict[str,str]
    attributed_author: str | None
    indicator_author_is_strategy_author: bool = False
    checked_at: datetime


class RightsEvidence(StrictModel):
    scope: Literal['SOURCE_TEXT','IMPLEMENTATION_CODE','MARKET_DATA']
    research_use_allowed: bool | None
    research_use_scope: Literal['PRIVATE_INTERNAL_RESEARCH','PERSONAL_NONCOMMERCIAL','UNKNOWN']
    commercial_use_allowed: bool | None
    redistribution_allowed: bool | None
    derivative_allowed: bool | None
    attribution_required: bool | None
    attribution: str | None
    license_source: str = Field(min_length=1)
    license_checked_at: datetime
    license_confidence: Literal['HIGH','MEDIUM','LOW','UNKNOWN']
    artifact: EvidenceArtifact
    rationale: str = Field(min_length=1)


class ExecutionFact(StrictModel):
    value: Any
    basis: Literal['SOURCE_DEFINED','RESEARCH_ASSUMPTION','UNKNOWN']
    rationale: str = Field(min_length=1)
    evidence: EvidenceArtifact | None = None

    @model_validator(mode='after')
    def source_needs_evidence(self):
        if self.basis=='SOURCE_DEFINED' and self.evidence is None:
            raise ValueError('SOURCE_DEFINED facts require a pinned artifact')
        if self.basis!='UNKNOWN' and self.value in (None,''):
            raise ValueError('Known execution facts require a value')
        return self


class CostModel(StrictModel):
    fee_bps: float = Field(ge=0)
    slippage_bps: float = Field(ge=0)
    basis: Literal['SOURCE_DEFINED','RESEARCH_ASSUMPTION']
    description: str = Field(min_length=1)


class ExecutionContract(StrictModel):
    signal_timing: ExecutionFact
    execution_timing: ExecutionFact
    execution_price: ExecutionFact
    rebalance_frequency: ExecutionFact
    holding_period: ExecutionFact
    position_rule: ExecutionFact
    cash_rule: ExecutionFact
    fallback_rule: ExecutionFact
    long_short: ExecutionFact
    leverage: ExecutionFact
    transaction_cost_model: CostModel
    slippage_model: ExecutionFact
    price_adjustment: ExecutionFact
    missing_data_policy: ExecutionFact
    indicator_semantics: ExecutionFact
    closed_bar_only: bool
    accepted_research_assumptions: bool
    artifact: EvidenceArtifact


class DataRequirement(StrictModel):
    data_types: list[str] = Field(min_length=1)
    symbols: list[str] = Field(min_length=1)
    required_fields: list[str] = Field(min_length=1)
    frequency: str = Field(min_length=1)
    data_availability_status: Literal['VERIFIED_AVAILABLE','PENDING','UNAVAILABLE']
    data_source: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    dataset_version: str | None
    downloaded_at: datetime | None
    adjustment_method: str
    timezone: str
    calendar: str
    start_date: str | None
    end_date: str | None
    dataset_hash: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    raw_data_hashes: list[str] = Field(default_factory=list)
    real_market_data: bool
    quality_status: Literal['PASS','FAIL','UNVERIFIED']
    evidence: EvidenceArtifact

    @model_validator(mode='after')
    def available_is_pinned(self):
        if any(not re.fullmatch(r'[a-f0-9]{64}', h) for h in self.raw_data_hashes):
            raise ValueError('Invalid raw data hash')
        if self.start_date and self.end_date:
            start,end=datetime.fromisoformat(self.start_date),datetime.fromisoformat(self.end_date)
            if (start.tzinfo is None)!=(end.tzinfo is None) or start>=end:
                raise ValueError('Data period must have consistent zones and be ordered')
        if self.data_availability_status=='VERIFIED_AVAILABLE' and not all([
            self.dataset_version,self.downloaded_at,self.start_date,self.end_date,self.dataset_hash,self.raw_data_hashes]):
            raise ValueError('Verified available data requires version, period and byte hashes')
        return self


class EvidenceEnrichment(StrictModel):
    schema_version: Literal['evidence-enrichment-v3']
    record_id: str = Field(min_length=1)
    semantic_record_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    reviewed_by: str = Field(min_length=1)
    source: SourceEvidence
    provenance_type: Literal['SOURCE_NATIVE','SOURCE_IMPLEMENTATION','SOURCE_DERIVED','BOT_DERIVED',
        'PARAMETER_VARIANT','MARKET_VARIANT','ASSET_VARIANT','UNKNOWN']
    parent_record_ids: list[str]
    rights: list[RightsEvidence] = Field(min_length=1)
    use_context: Literal['PRIVATE_INTERNAL_RESEARCH','PERSONAL_NONCOMMERCIAL']
    execution: ExecutionContract
    data_requirement: DataRequirement
    rule_review_status: Literal['VERIFIED','INCOMPLETE','SOURCE_CONFLICT','UNVERIFIED']
    rule_evidence: EvidenceArtifact
    dedup_status: Literal['INDEPENDENT_TEMPLATE','SIBLING_VARIANT','UNRESOLVED']
    warnings: list[str]

    @model_validator(mode='after')
    def scopes_are_independent(self):
        scopes=[r.scope for r in self.rights]
        if len(scopes)!=len(set(scopes)):
            raise ValueError('Duplicate rights scopes')
        return self


class ResearchCandidateAssessment(StrictModel):
    gate_version: Literal['research-candidate-gate-v3']
    status: Literal['ELIGIBLE','CONDITIONALLY_ELIGIBLE','REVIEW_REQUIRED','BLOCKED']
    strategy_concept_id: str | None
    strategy_template_id: str | None
    source_status: str
    rights_status: str
    rule_status: str
    execution_status: str
    data_status: str
    dedup_status: str
    ontology_status: str
    research_readiness_score: int = Field(ge=0,le=100)
    blocking_reasons: list[str]
    warnings: list[str]


class MarketResearchEvidence(StrictModel):
    schema_version: Literal['2.0']
    research_run_id: str = Field(min_length=1,max_length=200)
    experiment_family_id: str = Field(min_length=1)
    source_strategy_ids: list[str] = Field(min_length=1,max_length=1000)
    strategy_concept_id: str = Field(min_length=1)
    strategy_template_id: str = Field(min_length=1)
    artifact_uri: str = Field(min_length=1)
    artifact_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    contract_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    code_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    config_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    candidate_snapshot_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    real_market_data: Literal[True]
    data_provenance: DataRequirement
    trial_count: int = Field(ge=1)
    parameter_grid: list[dict] = Field(min_length=1)
    results: dict
    evidence_kind: Literal['REAL_MARKET_BACKTEST']
    research_status: Literal['RESEARCH_PASSED','RESEARCH_FAILED','INCONCLUSIVE']
    limitations: list[str] = Field(min_length=1)
    validation_status: Literal['SUBMITTED_NOT_INDEPENDENTLY_VERIFIED']='SUBMITTED_NOT_INDEPENDENTLY_VERIFIED'
    promotion_allowed: Literal[False]=False

    @model_validator(mode='after')
    def not_a_fixture(self):
        data=self.data_provenance
        if len(self.parameter_grid)!=self.trial_count:
            raise ValueError('Every tested parameter setting must be declared')
        if not data.real_market_data or data.quality_status!='PASS' or data.data_availability_status!='VERIFIED_AVAILABLE':
            raise ValueError('Formal market research needs verified real data')
        for text in (self.artifact_uri,data.data_source,data.exchange,data.dataset_version,data.evidence.uri):
            if text and any(x in text.lower() for x in ('fixture','synthetic','example.org','test-only')):
                raise ValueError('Synthetic/fixture results are not market research')
        for section in ('in_sample','oos','costs','turnover','robustness','deflated_sharpe','pbo'):
            if section not in self.results:
                raise ValueError('Missing required research section: '+section)
        for section in ('in_sample','oos'):
            window=self.results[section]
            metrics={'total_return','cagr','sharpe','sortino','calmar','max_drawdown','volatility','turnover','win_rate','exposure'}
            if not isinstance(window,dict) or type(window.get('observations')) is not int or window['observations']<3 or not metrics<=window.keys():
                raise ValueError('Completed IS/OOS needs observations and all required metrics')
        def finite_values(node):
            if isinstance(node,float) and not math.isfinite(node):
                raise ValueError('Nonfinite result; use null with an explicit reason')
            if isinstance(node,dict):
                for value in node.values():finite_values(value)
            elif isinstance(node,list):
                for value in node:finite_values(value)
        finite_values(self.results)
        return self
