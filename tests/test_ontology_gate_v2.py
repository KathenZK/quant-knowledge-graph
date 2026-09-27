import copy
import json

import pytest
from quantgraph.graph.ingestion_store import SQLiteIngestionRepository
from quantgraph.models.ingestion import IngestBatch
from quantgraph.normalize.strategy.parser import parse_rule
from test_ingestion_lifecycle import payload, ingest


def test_rsi_template_and_factor_identity_ignore_threshold_asset_and_order(tmp_path):
    repo = SQLiteIngestionRepository(tmp_path / 'journal.sqlite')
    first = payload()
    ingest(repo, first)
    original = repo.variants()[0]
    second = copy.deepcopy(first)
    second['records'][0].update(record_id='another', raw_rule='日频：若RSI(14)>60→满仓QQQ，否则满仓BIL。')
    ingest(repo, second)
    rows = repo.variants()
    assert len({r['variant']['strategy_concept_id'] for r in rows}) == 1
    assert len({r['variant']['strategy_template_id'] for r in rows}) == 1
    assert len({r['variant']['strategy_variant_id'] for r in rows}) == 2
    assert len({r['factor_links'][0]['factor_variant_id'] for r in rows}) == 1
    updated = next(r for r in rows if r['variant']['source_native_id'] == 'fixture-one')
    assert updated['variant']['strategy_variant_id'] == original['variant']['strategy_variant_id']
    assert original['variant']['variation_axes'] == []
    assert set(updated['variant']['variation_axes']) == {'PARAMETER_VARIANT', 'ASSET_VARIANT'}
    assert all(link['validation_status'] == 'RULE_LINK_ONLY' and link['link_id'] for r in rows for link in r['factor_links'])


def test_review_is_local_hash_bound_and_invalidated_by_revision(tmp_path):
    repo = SQLiteIngestionRepository(tmp_path / 'journal.sqlite')
    value = payload()
    value['records'][0].update(research_allowed=True, source_verification='VERIFIED', live_ready=True)
    ingest(repo, value)
    assert not repo.variants()[0]['candidate_gate']['eligible']
    with repo.connect() as con:
        digest = con.execute('SELECT semantic_record_hash FROM revision_semantics_v2').fetchone()[0]
    evidence = {'uri': 'fixture:reviewed-evidence', 'sha256': 'a' * 64}
    decision = dict(record_id='fixture-one', semantic_record_hash=digest, reviewed_by='fixture-reviewer',
                    source_evidence=evidence, provenance_type='BOT_DERIVED', rights_evidence=evidence,
                    research_use='ALLOWED', rights_scope='PRIVATE_RESEARCH', execution_evidence=evidence,
                    execution_contract={'timing': 'next_open', 'price_adjustment': 'split_and_dividend',
                                        'missing_data_policy': 'fail', 'indicator_semantics': 'fixture-exact-definition',
                                        'closed_bar_only': True, 'costs': {'fee_bps': 1, 'slippage_bps': 2}},
                    data_evidence=evidence, data_available=True, symbols=['SPY', 'BIL'], required_fields=['open', 'close'])
    repo.review_record(decision)
    assert not repo.variants()[0]['candidate_gate']['eligible']
    assert 'LEGACY_REVIEW_REQUIRES_V3' in repo.variants()[0]['candidate_gate']['blockers']
    assert repo.ingest_stats()['rights_status'] == {'REVIEW_REQUIRED': 1}
    assert repo.ingest_stats()['eligible_research_variants'] == 0
    assert repo.ingest_stats()['review_queue'] == 1
    assert not repo.variants()[0]['variant']['executable']
    assert repo.variants()[0]['variant']['rights_status'] == 'REVIEW_REQUIRED'  # no commercial permission
    value['records'][0]['raw_rule'] += ' 未定义额外规则'
    ingest(repo, value)
    assert not repo.variants()[0]['candidate_gate']['eligible']
    assert repo.ingest_stats()['rights_status'] == {'REVIEW_REQUIRED': 1}
    with pytest.raises(ValueError, match='current semantic'):
        repo.review_record(decision)


@pytest.mark.parametrize('rule', [
    '日频：若RSI(14)>55且收盘>SMA(180)→满仓QQQ，否则满仓BIL。',
    '日频：若AroonDown(25)<50→满仓SPY，否则满仓BIL。',
    '月末若QQQ近11月总分收益>0→次月满仓QQQ；否则现金。',
    '月末若QQQ月收>近9月收盘SMA→次月满仓QQQ；否则现金。',
])
def test_explicit_patterns_parse_without_inventing_execution(rule):
    result = parse_rule(rule)
    assert result['parse_status'] == 'PARSED'
    assert result['rule_ast']['costs'] is None and not result['executable']


@pytest.mark.parametrize('rule', [
    '日频：若RSI(14)>55且收盘>未知中轨→满仓QQQ，否则BIL。',
    '日频：若ADX(14)>20且+DI>-DI→满仓QQQ，否则BIL。',
    '日频：若MACD(12,26)>0→满仓QQQ，否则BIL。',
    '日频：若RSI(14)>55→满仓QQQ，否则BIL。另外触发止损时反转。',
])
def test_incomplete_indicators_or_additional_rules_remain_review(rule):
    assert parse_rule(rule)['rule_ast'] is None


def test_evidence_query_cannot_promote_factor_links(tmp_path):
    repo = SQLiteIngestionRepository(tmp_path / 'journal.sqlite')
    ingest(repo, payload())
    before = repo.variants()[0]
    vid = before['variant']['strategy_variant_id']
    evidence = {'research_run_id': 'fixture-result', 'source_strategy_ids': [vid],
                'results': {'oos': {'sharpe': 100}}, 'evidence_kind': 'LAB_REPRODUCED'}
    repo.put_evidence(evidence, 'fixture')
    assert repo.evidence_for(vid) == [evidence]
    assert repo.variants()[0]['factor_links'] == before['factor_links']


@pytest.mark.parametrize(('second_rule', 'axes'), [
    ('日频：若RSI(14)>45→满仓SPY，否则满仓BIL。', ['PARAMETER_VARIANT']),
    ('日频：若RSI(14)>55→满仓QQQ，否则满仓BIL。', ['ASSET_VARIANT']),
])
def test_axes_are_actual_sibling_differences_even_across_pages(tmp_path, second_rule, axes):
    repo = SQLiteIngestionRepository(tmp_path / 'journal.sqlite')
    value = payload()
    ingest(repo, value)
    assert repo.variants()[0]['variant']['variation_axes'] == []
    value['records'][0].update(record_id='sibling', raw_rule=second_rule)
    ingest(repo, value)
    assert repo.variants(limit=1)[0]['variant']['variation_axes'] == axes
    assert repo.variants(limit=1, offset=1)[0]['variant']['variation_axes'] == axes
