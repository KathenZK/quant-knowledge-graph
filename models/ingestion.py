"""GrokBot wire contracts. Extra fields are retained, never interpreted as grants."""
from datetime import datetime
from typing import Any
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator
from quantgraph.normalize.strategy.metadata import canonical_url


class AuditableModel(BaseModel):
    model_config = ConfigDict(extra='allow', allow_inf_nan=False)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def audit_payload(self):
        payload = self.model_dump(mode='json')
        # Keep the original top-level extras as well as an explicit audit index.
        payload['auditable_unknown_fields'] = dict(self.model_extra or {})
        return payload


class IngestRecord(AuditableModel):
    record_id: str = Field(min_length=1, max_length=200, validation_alias=AliasChoices('record_id', 'external_id'))
    source_url: str = Field(max_length=4000)
    name: str = Field(min_length=1, max_length=2000, validation_alias=AliasChoices('name', 'title'))
    author: str | None = Field(default=None, validation_alias=AliasChoices('author', 'org'))
    source_publication_date: str | None = None
    raw_market: str = Field(min_length=1, max_length=2000)
    raw_rule: str = Field(min_length=1, max_length=100000)
    backtestability: str | None = None
    collected_at: datetime

    def semantic_payload(self, version='strategy-record-semantics-v2'):
        """Versioned source semantics, excluding declared observation-only fields.

        Unknown fields remain in audit_payload; they cannot grant rights or affect
        strategy identity. Collectors put source facts in metadata/source_metadata
        and parameters in strategy_parameters. Reserved assessment keys in metadata
        are observation-only, including legacy collector aliases.
        """
        if version not in {'strategy-record-semantics-v1', 'strategy-record-semantics-v2'}:
            raise ValueError('Unsupported semantic hash version')
        fields = ('source_url', 'name', 'author', 'source_publication_date', 'raw_market', 'raw_rule')
        operational = {'collected_at', 'ingested_at', 'ingestion_timestamp',
                       'request_time', 'request_timestamp', 'api_request_timestamp',
                       'batch_id', 'batch_runtime_metadata', 'observation_metadata',
                       'collected_at_basis', 'legacy_archive_sha256'}
        if version == 'strategy-record-semantics-v1':
            fields += ('backtestability',)
        else:
            operational |= {'backtestability', 'bot_assessment', 'parser_output',
                            'candidate_score', 'candidate_quality_score', 'research_readiness',
                            'research_readiness_score', 'rights_enrichment_result'}
        def source_facts(value):
            if version == 'strategy-record-semantics-v1':
                return value
            if isinstance(value, dict):
                return {k: source_facts(v) for k, v in value.items() if k not in operational | {'可回测'}}
            if isinstance(value, list):
                return [source_facts(v) for v in value]
            return value
        payload = self.model_dump(mode='json')
        return {**{key: payload[key] for key in fields},
                'metadata': source_facts({k: v for k, v in self.metadata.items() if k not in operational}),
                'source_metadata': source_facts(payload.get('source_metadata', {})),
                'strategy_parameters': payload.get('strategy_parameters', {})}

    @field_validator('record_id', 'name', 'raw_market', 'raw_rule')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Blank fields are not valid records')
        return value

    @field_validator('source_url')
    @classmethod
    def valid_url(cls, value):
        if not canonical_url(value):
            raise ValueError('A valid HTTP(S) source URL without credentials is required')
        return value

    @field_validator('collected_at')
    @classmethod
    def zoned_time(cls, value):
        if value.tzinfo is None:
            raise ValueError('collected_at requires a timezone')
        return value

    @model_validator(mode='after')
    def aliases_agree(self):
        for alias, primary in [('external_id', self.record_id), ('title', self.name), ('org', self.author)]:
            if alias in (self.model_extra or {}) and self.model_extra[alias] != primary:
                raise ValueError(f'Conflicting alias: {alias}')
        return self


class IngestBatch(AuditableModel):
    batch_id: str = Field(min_length=1, max_length=200, pattern=r'^[A-Za-z0-9_.:-]+$')
    collector_version: str = Field(min_length=1, max_length=200)
    records: list[IngestRecord] = Field(min_length=1, max_length=1000)

    @model_validator(mode='after')
    def distinct_ids(self):
        ids = [r.record_id for r in self.records]
        if len(set(ids)) != len(ids):
            raise ValueError('Duplicate record_id within one request')
        return self
