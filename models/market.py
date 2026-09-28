"""V4 immutable research/data contracts. Permissions are independent facts."""
from datetime import datetime
import hashlib
import json
from typing import Any, Literal, Annotated
from pydantic import Field, model_validator, StringConstraints
from .evidence import StrictModel


def canonical_sha256(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class ReviewedRightsEvidence(StrictModel):
    schema_version: Literal['reviewed-rights-v4']
    rights_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    source: str = Field(min_length=1)
    scope: Literal['MARKET_DATA', 'SOURCE_TEXT', 'IMPLEMENTATION_CODE']
    research_use_allowed: bool | None
    research_use_scope: Literal['PRIVATE_INTERNAL_RESEARCH', 'PERSONAL_NONCOMMERCIAL', 'UNKNOWN']
    commercial_use_allowed: bool | None
    redistribution_allowed: bool | None
    derivative_allowed: bool | None
    attribution_required: bool | None
    attribution: str | None
    license_source: str = Field(min_length=1)
    license_url: str = Field(pattern=r'^https://')
    reviewed_at: datetime
    reviewed_by: str = Field(min_length=1)
    confidence: Literal['HIGH', 'MEDIUM', 'LOW', 'UNKNOWN']
    status: Literal['VERIFIED', 'REVIEW_REQUIRED', 'PROHIBITED']
    evidence_path: str = Field(min_length=1)
    evidence_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    rationale: str = Field(min_length=1)


class DerivedDataRequirement(StrictModel):
    derivation_version: Literal['ast-execution-v4']
    required_fields: list[str] = Field(min_length=1)
    symbols: list[str] = Field(min_length=1)
    frequency: str = Field(min_length=1)
    adjustment: str = Field(min_length=1)
    timezone: Literal['UTC']
    calendar: str = Field(min_length=1)
    auxiliary_data: list[str]
    derivation_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    # Explicit acceptance profile is frozen separately from signal inputs.
    # AST derivation does not waive either profile's independent quality gates.
    dataset_profile: Literal['LAB_OHLCV_V1', 'TRUSTED_OHLCV_CORE_V1']


class ResearchContract(StrictModel):
    schema_version: Literal['research-contract-v4']
    frozen_at: datetime
    strategy_concept_id: str = Field(min_length=1)
    strategy_template_id: str = Field(min_length=1)
    strategy_variant_id: str = Field(min_length=1)
    experiment_family_id: str = Field(min_length=1)
    parameters: list[Any] = Field(min_length=1)
    parameter_grid: list[list[Any]] = Field(min_length=1)
    trial_count: int = Field(ge=1)
    symbols: list[str] = Field(min_length=1)
    universe: Literal['FIXED_SINGLE_ASSET']
    provider: str = Field(min_length=1)
    source: str = Field(min_length=1)
    market_type: Literal['spot']
    frequency: Literal['1d', '4h']
    requested_start: datetime
    requested_end: datetime
    is_start: datetime
    is_end: datetime
    oos_start: datetime
    oos_end: datetime
    signal_timing: str = Field(min_length=1)
    execution_timing: str = Field(min_length=1)
    execution_price: str = Field(min_length=1)
    rebalance: str = Field(min_length=1)
    holding_period: str = Field(min_length=1)
    fees_bps: float = Field(ge=0, lt=10000)
    slippage_bps: float = Field(ge=0, lt=10000)
    cost_model: str = Field(min_length=1)
    execution_contract: dict
    rule_ast: dict
    data_requirements: DerivedDataRequirement
    use_context: Literal['PRIVATE_INTERNAL_RESEARCH', 'PERSONAL_NONCOMMERCIAL']
    engine_config: dict
    prior_trial_count: int = Field(ge=0)
    holdout_status: Literal['RETROSPECTIVE_PREVIOUSLY_OBSERVED', 'UNOBSERVED_AT_FREEZE']
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode='after')
    def consistent(self):
        if len(self.symbols)!=1 or self.symbols!=self.data_requirements.symbols:
            raise ValueError('One fixed asset and matching data requirement required')
        if self.frequency!=self.data_requirements.frequency:
            raise ValueError('Frequency mismatch')
        if self.trial_count!=len(self.parameter_grid) or self.parameters not in self.parameter_grid:
            raise ValueError('Complete grid including the frozen baseline required')
        if len({json.dumps(p,sort_keys=True) for p in self.parameter_grid})!=self.trial_count:
            raise ValueError('Duplicate parameter trials')
        if not self.requested_start<=self.is_start<self.is_end==self.oos_start<self.oos_end==self.requested_end:
            raise ValueError('Nonoverlapping adjacent IS/OOS inside requested history required')
        from quantgraph.graph.data_requirements import derive
        expected=derive(self.rule_ast,self.execution_contract,calendar=self.data_requirements.calendar,
                        dataset_profile=self.data_requirements.dataset_profile)
        if expected!=self.data_requirements.model_dump(mode='json'):
            raise ValueError('Data requirement differs from AST/execution derivation')
        return self


class MarketCoverage(StrictModel):
    requested_start: str
    requested_end: str
    actual_start: str | None
    actual_end: str | None
    expected_count: int | None = Field(ge=0)
    actual_count: int = Field(ge=0)
    gap_count: int | None = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    unexpected_count: int = Field(ge=0)
    ordered: bool
    calendar: str
    calendar_version: str
    coverage_status: Literal['VERIFIED','PARTIAL','UNKNOWN','INVALID']
    coverage_reason: str

    @model_validator(mode='after')
    def verified_is_consistent(self):
        if self.coverage_status=='VERIFIED' and (not self.ordered or self.expected_count is None or self.expected_count<1
            or self.actual_count!=self.expected_count or self.gap_count!=0 or self.duplicate_count or self.unexpected_count
            or not self.actual_start or not self.actual_end or self.calendar_version=='UNKNOWN'):
            raise ValueError('Inconsistent VERIFIED coverage')
        return self


class MarketDatasetTrustAssessment(StrictModel):
    """A pinned Lab audit, not a permission grant or a hand-written gate override."""
    schema_version: Literal['market-dataset-trust-v1']
    dataset_profile: Literal['TRUSTED_OHLCV_CORE_V1']
    contract_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    dataset_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    rights_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    raw_dataset_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    source_identity: Literal['PASS', 'FAIL', 'UNKNOWN']
    rights: Literal['PASS', 'FAIL', 'UNKNOWN']
    coverage: Literal['PASS', 'FAIL', 'UNKNOWN']
    schema_status: Literal['PASS', 'FAIL', 'UNKNOWN']
    calendar: Literal['PASS', 'FAIL', 'UNKNOWN']
    integrity: Literal['PASS', 'FAIL', 'UNKNOWN']
    hashes: Literal['PASS', 'FAIL', 'UNKNOWN']
    finality: Literal['PASS', 'FAIL', 'UNKNOWN']
    provenance: Literal['PASS', 'FAIL', 'UNKNOWN']
    page_count: int = Field(ge=1)
    assessment_code_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    assessed_at: datetime
    status: Literal['TRUSTED', 'DIAGNOSTIC_ONLY', 'REJECTED']
    limitations: list[str]

    @model_validator(mode='after')
    def derived_status(self):
        checks=[getattr(self,k) for k in ('source_identity','rights','coverage','schema_status',
                'calendar','integrity','hashes','finality','provenance')]
        expected='REJECTED' if 'FAIL' in checks else 'TRUSTED' if set(checks)=={'PASS'} else 'DIAGNOSTIC_ONLY'
        if self.status!=expected:
            raise ValueError('Trust status must follow all independent checks')
        return self


class DatasetBinding(StrictModel):
    contract_json: Annotated[str, StringConstraints(strip_whitespace=False, min_length=1)]
    contract_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    dataset_manifest_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    rights_id: str = Field(min_length=1)
    rights_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    rights_evidence: ReviewedRightsEvidence
    coverage: MarketCoverage
    acceptance_status: Literal['TRUSTED', 'raw_unaccepted']
    missing_native_fields: list[str]
    trust_assessment: MarketDatasetTrustAssessment | None = None
    trust_assessment_sha256: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')

    @model_validator(mode='after')
    def rights_binding(self):
        if hashlib.sha256(self.contract_json.encode()).hexdigest()!=self.contract_sha256:
            raise ValueError('Frozen contract bytes digest mismatch')
        contract=ResearchContract.model_validate_json(self.contract_json)
        if contract.data_requirements.calendar!=self.coverage.calendar:
            raise ValueError('Contract and coverage calendar mismatch')
        if datetime.fromisoformat(self.coverage.requested_start)!=contract.requested_start or datetime.fromisoformat(self.coverage.requested_end)!=contract.requested_end:
            raise ValueError('Frozen requested history and coverage mismatch')
        if self.rights_id!=self.rights_evidence.rights_id:
            raise ValueError('Rights ID mismatch')
        if self.rights_sha256!=canonical_sha256(self.rights_evidence.model_dump(mode='json')):
            raise ValueError('Reviewed rights digest mismatch')
        if self.trust_assessment:
            t=self.trust_assessment
            if self.trust_assessment_sha256!=canonical_sha256(t.model_dump(mode='json')):
                raise ValueError('Trust assessment digest mismatch')
            if (t.contract_sha256,t.rights_sha256,t.dataset_profile)!=(self.contract_sha256,self.rights_sha256,contract.data_requirements.dataset_profile):
                raise ValueError('Trust assessment binding mismatch')
            if self.acceptance_status=='TRUSTED' and t.status!='TRUSTED':
                raise ValueError('Dataset trust is not established')
        elif self.trust_assessment_sha256:
            raise ValueError('Trust assessment missing')
        return self
