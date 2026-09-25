import json
from pathlib import Path
import sqlite3
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from quantgraph import FactorDB
from quantgraph.db import project_root
from quantgraph.api.app import create_app
from quantgraph.models.entities import Strategy, StrategyFactor, ENTITY_MODELS
from quantgraph.graph.verify import verify
from quantgraph.normalize.rights import commercial_allowed, rights_for
from quantgraph.normalize.dedup.policy import admission

ROOT=project_root()
pytestmark = pytest.mark.skipif(not (ROOT/'datasets/curated/current/quantgraph.sqlite').exists(), reason='Requires local mixed-license research snapshot, not distributed publicly')


def test_release_contract_and_profile_closure():
    r=verify(ROOT)
    assert r['research']['factor_variants']==1085
    assert r['commercial']['factor_variants']==508
    assert r['research']['strategies']==r['research']['backtest_results']==0
    public=FactorDB(profile='commercial')
    rows=public.search_factors(limit=1000)
    assert len(rows)==508 and all(commercial_allowed(v) for v in rows)
    assert {v['source_id'] for v in rows}=={'qlib'}


def test_concepts_and_variants_preserve_legacy_ids():
    db=FactorDB()
    momentum=db.search_factors('ret_12_1',source='jkp')[0]
    concept=db.get_factor(momentum['canonical_factor_id'])
    assert concept['canonical_factor_id']!=momentum['factor_variant_id']
    assert db.get_factor(concept['short_id'])['canonical_factor_id']==concept['canonical_factor_id']
    assert any(v['source_native_ids']==['Mom12m'] for v in concept['variants'])
    assert db.get_variant(momentum['factor_variant_id'])==momentum
    assert not any(v['backtest_ready'] for v in concept['variants'])


def test_filters_do_not_invent_crypto_coverage():
    db=FactorDB()
    assert db.search_factors(category='momentum',asset_class='crypto')==[]
    assert db.search_factors(category='momentum',asset_class='equity')
    assert db.search_factors("' OR 1=1 --")==[]
    with pytest.raises(ValueError):db.search_factors(limit=0)


def test_no_fabricated_strategy_links():
    db=FactorDB()
    assert db.find_strategies(factor='momentum')==[]
    assert db.get_strategy_factors('uncollected')==[]


def test_default_api_is_commercial_and_non_mutating():
    client=TestClient(create_app())
    assert client.get('/health').json()['profile']=='commercial'
    assert len(client.get('/v1/factors?limit=1000').json()['items'])==508
    assert client.get('/v1/factors?source=jkp').json()['items']==[]
    assert client.get('/v1/factors?asset_class=crypto').json()['items']==[]
    restricted=FactorDB().search_factors(source='jkp',limit=1)[0]
    vid=restricted['factor_variant_id']
    assert client.get('/v1/variants/'+vid).status_code==404
    assert client.get('/v1/entities/FactorVariant/'+vid).status_code==404
    assert client.get('/v1/relationships/'+vid).json()['items']==[]
    for pid in restricted['paper_ids']:
        assert client.get('/v1/entities/Paper/'+pid).status_code==404
    assert client.post('/v1/factors',json={}).status_code==405
    assert client.get('/v1/factors?limit=-1').status_code==422
    assert not any('runner' in p or 'publish' in p or 'execute' in p for p in client.get('/openapi.json').json()['paths'])


def test_api_research_profile_explicit_and_valid():
    client=TestClient(create_app(profile='research'))
    assert client.get('/health').json()['profile']=='research'
    records=client.get('/v1/factors?source=jkp&limit=2').json()['items']
    assert len(records)==2 and records[0]['commercial_use']=='PROHIBITED'
    vid=records[0]['factor_variant_id']
    assert client.get('/v1/variants/'+vid).json()==records[0]


def test_schema_requires_attribution_evidence():
    with pytest.raises(ValidationError):
        StrategyFactor(strategy_id='x',factor_id='f',variant_id='v',role='signal',confidence=1.01,evidence='source rule',source='file')
    with pytest.raises(ValidationError):
        StrategyFactor(strategy_id='x',factor_id='f',variant_id='v',role='signal',confidence=1,evidence='rule',source='file',attribution_status='EMPIRICALLY_TESTED')


def test_strategy_factor_foreign_keys_and_concept_consistency(tmp_path):
    source=sqlite3.connect(FactorDB().path);db=sqlite3.connect(tmp_path/'copy.sqlite');source.backup(db);source.close()
    db.execute('PRAGMA foreign_keys=ON')
    vid,cid=db.execute('SELECT factor_variant_id,canonical_factor_id FROM factor_variants LIMIT 1').fetchone()
    other=db.execute('SELECT canonical_factor_id FROM factor_concepts WHERE canonical_factor_id != ? LIMIT 1',(cid,)).fetchone()[0]
    strategy=Strategy(strategy_id='fixture:strategy',canonical_name='Fixture only',description='Test-only metadata',source=[{'uri':'fixture'}],external_namespace='test',external_id='1',spec_sha256='0'*64,status='TEST_ONLY',created_at='2026-09-25',updated_at='2026-09-25')
    # Insert fully typed payload and columns, not an invented production strategy.
    from quantgraph.graph.store import encode
    row=strategy.model_dump(mode='json');columns=list(row)
    db.execute('INSERT INTO strategies ('+','.join(columns)+',payload) VALUES ('+','.join('?' for _ in range(len(columns)+1))+')',[encode(v) for v in row.values()]+[encode(row)])
    def insert(c,variant=vid):
        data=StrategyFactor(strategy_id='fixture:strategy',factor_id=c,variant_id=variant,role='signal',confidence=1,evidence='fixture rule',source='fixture').model_dump(mode='json')
        db.execute('INSERT INTO strategy_factor ('+','.join(data)+',payload) VALUES ('+','.join('?' for _ in range(len(data)+1))+')',list(data.values())+[encode(data)])
    with pytest.raises(sqlite3.IntegrityError,match='does not belong'):insert(other)
    insert(cid);db.commit()
    copied=FactorDB(database=tmp_path/'copy.sqlite')
    assert copied.find_strategies(factor=cid)[0]['strategy_id']=='fixture:strategy'
    assert copied.get_strategy_factors('fixture:strategy')[0]['attribution_status']=='RULE_LINK_ONLY'
    with pytest.raises(sqlite3.IntegrityError):
        insert(cid,'missing-variant');db.commit()
    db.rollback();db.close()


def test_curation_rejects_unverified_or_broken_primary():
    row={'high_quality_eligible':True,'primary_source':True,'record_kind':'signal','raw_definition':'real definition'}
    assert admission(row,[])[0]
    assert not admission(row,['FUTURE_REFERENCE'])[0]
    assert not admission({**row,'primary_source':False},[])[0]
    assert not admission({**row,'record_kind':'placebo'},[])[0]


def test_source_file_tamper_blocks_release(tmp_path):
    from quantgraph.collectors.legacy_cli import check_sources
    lock=json.loads((ROOT/'datasets/raw/source_lock.json').read_text())[:1]
    p=tmp_path/'datasets/raw/source_lock.json';p.parent.mkdir(parents=True)
    p.write_text(json.dumps(lock))
    target=tmp_path/lock[0]['path'];target.parent.mkdir(parents=True);target.write_text('tampered')
    with pytest.raises(ValueError,match='checksum'):check_sources(tmp_path)


def test_unknown_rights_are_not_promoted():
    record=dict(commercial_use_flag='unknown',license='unknown',source_id='new',terms_url='https://example.org')
    rights=rights_for(record)
    assert rights['commercial_use']=='REVIEW_REQUIRED'
    assert not commercial_allowed(rights)


def test_all_required_entities_have_real_contracts():
    assert set(ENTITY_MODELS)=={'factor_concepts','factor_variants','formulas','papers','authors','sources','licenses','datasets','implementations','strategies','strategy_factor','backtest_results','relationships'}


def test_concept_aliases_resolve_without_merging_parameters():
    db=FactorDB()
    concept=db.get_factor('Price Momentum')
    assert concept['canonical_name']=='历史价格动量'
    variants=concept['variants']
    assert len(variants)>1
    assert len({v['factor_variant_id'] for v in variants})==len(variants)
    assert db.get_factor('MOM')['canonical_factor_id']==concept['canonical_factor_id']
