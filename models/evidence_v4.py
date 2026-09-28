"""Current formal admission; legacy V3 reviews remain readable, not eligible."""
from typing import Literal, Any
from pydantic import model_validator, Field
from .evidence import EvidenceEnrichment, MarketResearchEvidence, ResearchCandidateAssessment
from .market import DatasetBinding, DerivedDataRequirement, ResearchContract


class EvidenceEnrichmentV4(EvidenceEnrichment):
    schema_version: Literal['evidence-enrichment-v4']
    derived_data_requirement: DerivedDataRequirement
    dataset_binding: DatasetBinding

    @model_validator(mode='after')
    def explicit_assumptions(self):
        facts=self.execution.model_dump(mode='json')
        for name,value in facts.items():
            if isinstance(value,dict) and value.get('basis')=='RESEARCH_ASSUMPTION':
                if not value.get('assumption_version') or not value.get('assumption_reason'):
                    raise ValueError('Version and reason required for research assumption: '+name)
        contract=ResearchContract.model_validate_json(self.dataset_binding.contract_json)
        if contract.execution_contract!=self.execution.model_dump(mode='json') or contract.data_requirements!=self.derived_data_requirement:
            raise ValueError('Review differs from frozen research contract')
        d=self.data_requirement;r=self.derived_data_requirement
        if set(d.required_fields)!=set(r.required_fields) or d.symbols!=r.symbols or d.frequency!=r.frequency:
            raise ValueError('Declared and derived data requirements differ')
        if (d.adjustment_method,d.timezone,d.calendar)!=(r.adjustment,r.timezone,r.calendar):
            raise ValueError('Data convention mismatch')
        return self


class MarketResearchEvidenceV4(MarketResearchEvidence):
    schema_version: Literal['3.0']
    parameter_grid: list[list[Any]] = Field(min_length=1)
    strategy_variant_id: str = Field(min_length=1)
    dataset_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    dataset_manifest_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    rights_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    rights_id: str = Field(min_length=1)
    exposure_definition: Literal['POST_OPEN_POSITION_PROXY_WITH_INTRABAR_BOUNDS']

    @model_validator(mode='after')
    def dataset_pins(self):
        if self.source_strategy_ids!=[self.strategy_variant_id]:
            raise ValueError('One frozen source variant per template experiment')
        if self.dataset_sha256!=self.data_provenance.dataset_hash:
            raise ValueError('Dataset digest mismatch')
        return self


class ResearchCandidateAssessmentV4(ResearchCandidateAssessment):
    gate_version: Literal['research-candidate-gate-v4']
    source_support_status: str
    data_requirement_status: str
    data_availability_status: str
