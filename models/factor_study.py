"""Factor research contracts. These confer neither execution nor publication rights."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class EntityRef(Strict):
    entity_type: Literal['FactorDefinition', 'FactorVariant', 'StrategyVariant']
    entity_id: str = Field(min_length=1)
    definition_revision: str = Field(min_length=1)


class ResearchRequest(Strict):
    schema_version: Literal['research-request/v1'] = 'research-request/v1'
    request_id: str = Field(min_length=1, max_length=200)
    entity_refs: list[EntityRef] = Field(min_length=1, max_length=1000)
    study_type: Literal['FACTOR_DIAGNOSTIC', 'STRATEGY_REPLICATION']
    requested_settings: dict
    status: Literal['DRAFT'] = 'DRAFT'


class HashRef(Strict):
    uri: str = Field(min_length=1)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class Permission(Strict):
    internal_use: Literal['ALLOWED', 'DENIED', 'REVIEW_REQUIRED']
    public_display: Literal['ALLOWED', 'DENIED', 'REVIEW_REQUIRED']
    evidence: str = Field(min_length=1)


class Artifact(HashRef):
    kind: str = Field(min_length=1)
    permissions: Permission


class Identity(Strict):
    factor_concept_id: str = Field(min_length=1)
    factor_variant_id: str = Field(min_length=1)
    definition_revision: str = Field(pattern=r'^[a-f0-9]{64}$')
    source_revision: str = Field(min_length=1)
    source_snapshot: HashRef
    source_native_ids: list[str] = Field(min_length=1)
    formula_id: str = Field(min_length=1)
    formula: str = Field(min_length=1)
    formula_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class Implementation(Strict):
    implementation_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    code: HashRef
    semantic_version: str = Field(min_length=1)
    parameters: dict
    required_fields: list[str] = Field(min_length=1)
    axis: Literal['TIME_SERIES', 'CROSS_SECTIONAL']
    semantics: dict[str, str]


class SemanticTest(Strict):
    name: str = Field(min_length=1)
    status: Literal['PASS', 'FAIL', 'UNKNOWN']
    evidence: HashRef


class Mapping(Strict):
    identity: Identity
    implementation: Implementation
    mapping_status: Literal['VERIFIED', 'FAILED', 'UNVERIFIED']
    semantic_tests: list[SemanticTest]

    @model_validator(mode='after')
    def verified_requires_tests(self):
        needed = {'hand_calculated', 'reference_parity', 'real_market_boundaries'}
        if self.mapping_status == 'VERIFIED' and not needed <= {
            t.name for t in self.semantic_tests if t.status == 'PASS'
        }:
            raise ValueError('VERIFIED requires both semantic layers and reference parity')
        fields = {'missing_values', 'warmup', 'ties', 'window', 'adjustment',
                  'available_at', 'delay', 'volume_unit', 'universe', 'ddof', 'rsi'}
        if not fields <= self.implementation.semantics.keys():
            raise ValueError('Incomplete computation semantics')
        return self


class Permissions(Strict):
    definition: Permission
    implementation: Permission
    market_data: Permission
    derived_result: Permission


class Integrity(Strict):
    status: Literal['UNKNOWN', 'INTERNAL_CHECKED', 'FAILED']
    evidence: list[HashRef]
    independent_verification: Literal[False] = False


class FactorStudyResult(Strict):
    schema_version: Literal['factor-study-result/v1'] = 'factor-study-result/v1'
    run_id: str = Field(min_length=1, max_length=200)
    request_id: str = Field(min_length=1)
    study_type: Literal['COMPUTATION_CHECK', 'FACTOR_DIAGNOSTIC', 'PORTFOLIO_BACKTEST', 'CONFIRMATORY_VALIDATION']
    mapping: Mapping
    dataset: HashRef
    contract: HashRef
    code: HashRef
    sample: dict
    labels: list[dict]
    methods: dict
    results: dict
    status: Literal['SUCCESS', 'FAILED', 'INVALID']
    limitations: list[str] = Field(min_length=1)
    integrity_assessment: Integrity
    permissions: Permissions
    artifacts: list[Artifact]
    trial_registry: dict
    research_status: Literal['EXPLORATORY_RETROSPECTIVE'] = 'EXPLORATORY_RETROSPECTIVE'
    promotion_allowed: Literal[False] = False

    @model_validator(mode='after')
    def diagnostic_only(self):
        # Other study types are vocabulary, not an implementation of their gates.
        if self.study_type not in {'COMPUTATION_CHECK', 'FACTOR_DIAGNOSTIC'}:
            raise ValueError('Use the existing strategy/confirmation admission for this study type')
        if self.status == 'SUCCESS' and self.mapping.mapping_status != 'VERIFIED':
            raise ValueError('Successful study requires verified computation mapping')
        if self.study_type == 'FACTOR_DIAGNOSTIC' and self.status == 'SUCCESS':
            if self.sample.get('real_market_data') is not True or not self.labels or not self.results:
                raise ValueError('Factor diagnostic requires real data, labels and results')
        return self
