"""Readiness is evidence completeness, never expected profitability.

Decisions come from a local reviewed ledger, not collector/API extra fields.
Every decision is bound to a semantic hash and carries separate source, rights,
execution and market-data evidence. Unknown is not permission.
"""
from typing import Literal
import math
from pydantic import BaseModel, ConfigDict, Field

VERSION = 'research-candidate-gate-v2'


class Evidence(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    uri: str = Field(min_length=1)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, str_strip_whitespace=True)
    record_id: str = Field(min_length=1)
    semantic_record_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    reviewed_by: str = Field(min_length=1)
    source_evidence: Evidence
    provenance_type: Literal['SOURCE_NATIVE', 'SOURCE_IMPLEMENTATION', 'SOURCE_DERIVED', 'BOT_DERIVED']
    rights_evidence: Evidence
    research_use: Literal['ALLOWED', 'PROHIBITED', 'REVIEW_REQUIRED']
    rights_scope: Literal['PRIVATE_RESEARCH']
    execution_evidence: Evidence
    execution_contract: dict
    data_evidence: Evidence
    data_available: bool
    symbols: list[str] = Field(min_length=1)
    required_fields: list[str] = Field(min_length=1)


def evaluate(row, decision=None):
    v = row['variant']
    blockers = []
    scores = {}
    source_ok = bool(v.get('source_url')) and bool(decision)
    scores['source_evidence'] = 20 if source_ok else 0
    if not source_ok:
        blockers.append('SOURCE_EVIDENCE_UNVERIFIED')
    rights_ok = bool(decision and decision['research_use'] == 'ALLOWED')
    scores['rights_certainty'] = 20 if rights_ok else 0
    if not rights_ok:
        blockers.append('RIGHTS_REVIEW_REQUIRED')
    rule_ok = bool(v.get('rule_ast') and row.get('definition_admitted'))
    scores['rule_completeness'] = 20 if rule_ok else 0
    if not rule_ok:
        blockers.append('RULE_INCOMPLETE')
    contract = decision['execution_contract'] if decision else {}
    execution_ok = all(contract.get(k) for k in ('timing', 'price_adjustment', 'missing_data_policy', 'indicator_semantics'))
    costs = contract.get('costs') or {}
    execution_ok = execution_ok and all(type(costs.get(k)) in (int, float) and math.isfinite(costs[k]) and costs[k] >= 0 for k in ('fee_bps', 'slippage_bps'))
    execution_ok = execution_ok and contract.get('closed_bar_only') is True
    scores['execution_completeness'] = 20 if execution_ok else 0
    if not execution_ok:
        blockers.append('EXECUTION_CONTRACT_PENDING')
    symbols = set()
    unresolved_asset = False
    def assets(node):
        nonlocal unresolved_asset
        if isinstance(node, dict):
            for key, value in node.items():
                if key in {'risk_asset', 'safe_asset'} or (key == 'asset' and 'allocation' in node):
                    if value:
                        symbols.add(value)
                    else:
                        unresolved_asset = True
                elif key == 'assets':
                    symbols.update(s for s in value if s)
                    unresolved_asset |= any(s is None for s in value)
                else:
                    assets(value)
        elif isinstance(node, list):
            for value in node:
                assets(value)
    assets(v.get('rule_ast'))
    data_ok = bool(decision and decision['data_available'] and symbols and not unresolved_asset
                   and symbols <= set(decision['symbols'])
                   and 'close' in decision['required_fields']
                   and all(s.strip() for s in decision['symbols'] + decision['required_fields']))
    scores['data_availability'] = 20 if data_ok else 0
    if not data_ok:
        blockers.append('DATA_AVAILABILITY_UNCONFIRMED')
    return {'gate_version': VERSION, 'eligible': not blockers,
            'candidate_quality_score': sum(scores.values()), 'score_components': scores,
            'score_meaning': 'RESEARCH_READINESS_NOT_EXPECTED_RETURN', 'blockers': blockers,
            'hypothesis_id': v.get('strategy_template_id'), 'promotion_allowed': False}
