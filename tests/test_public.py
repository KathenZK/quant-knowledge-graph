import hashlib
import json
from pathlib import Path
import shutil
import pytest
from fastapi.testclient import TestClient
from quantgraph import FactorDB
from quantgraph.db import project_root
from quantgraph.api.app import create_app
from quantgraph.graph.public import public_sources, public_release, build_public, verify_public


@pytest.fixture(scope='module')
def clean_public_root(tmp_path_factory):
    source=project_root();root=tmp_path_factory.mktemp('public-clone')
    for rel in ['datasets/raw/source_lock.json','models/id_registry.json']:
        target=root/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source/rel,target)
    shutil.copytree(source/'datasets/raw/sources/qlib',root/'datasets/raw/sources/qlib')
    shutil.copytree(source/'datasets/public',root/'datasets/public')
    return root


def test_public_clone_integrity_and_dataset_scope(clean_public_root):
    result=verify_public(clean_public_root)
    assert result['counts']['factor_variants']==508
    db=FactorDB(clean_public_root)
    assert db.stats()['dataset_scope']=='public_qlib'
    assert db.stats()['profile']=='commercial'
    rows=db.search_factors(limit=1000)
    assert len(rows)==508 and {r['source_id'] for r in rows}=={'qlib'}
    assert all(r['commercial_use']=='ALLOWED' and not r['backtest_ready'] for r in rows)
    concept=db.get_factor(rows[0]['canonical_factor_id'])
    assert db.get_factor(concept['short_id'])==concept
    assert db.search_factors(asset_class='crypto')==[]
    assert db.find_strategies(factor='momentum')==[]


def test_public_rebuild_without_private_material(clean_public_root):
    before=public_release(clean_public_root)
    logical={p.name:p.read_bytes() for p in before.glob('*.jsonl')}
    result=build_public(clean_public_root)
    after=public_release(clean_public_root)
    assert {p.name:p.read_bytes() for p in after.glob('*.jsonl')}==logical
    assert build_public(clean_public_root)['release']==result['release']
    assert result['source_records']==518 and result['curated_variants']==508
    assert not (clean_public_root/'datasets/normalized').exists()
    assert not (clean_public_root/'datasets/curated').exists()
    assert not (clean_public_root/'datasets/raw/sources/jkp').exists()


def test_public_api_without_private_material(clean_public_root):
    client=TestClient(create_app(clean_public_root))
    assert client.get('/health').json()['dataset_scope']=='public_qlib'
    assert client.get('/v1/stats').json()['counts']['factor_variants']==508
    assert client.get('/v1/factors?source=jkp').json()['items']==[]
    assert client.get('/v1/strategies?factor=momentum').json()['items']==[]
    assert client.get('/v1/entities/Source/jkp').status_code==404
    assert client.post('/v1/factors',json={}).status_code==405
    assert client.get('/v1/factors?limit=0').status_code==422


def test_source_tampering_fails_closed(clean_public_root,tmp_path):
    lock=json.loads((clean_public_root/'datasets/raw/source_lock.json').read_text())
    (tmp_path/'datasets/raw').mkdir(parents=True)
    (tmp_path/'datasets/raw/source_lock.json').write_text(json.dumps(lock))
    with pytest.raises(ValueError,match='source mismatch'):public_sources(tmp_path)


def test_license_notice_present(clean_public_root):
    release=public_release(clean_public_root)
    assert (release/'NOTICE.md').is_file()
    upstream=clean_public_root/'datasets/raw/sources/qlib/LICENSE'
    assert (release/'THIRD_PARTY_LICENSE.txt').read_bytes()==upstream.read_bytes()
