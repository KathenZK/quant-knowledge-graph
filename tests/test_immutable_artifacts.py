import hashlib
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path

import pytest

from quantgraph.graph.immutable_artifacts import materialize_immutable
from quantgraph.graph.corpus_export import export_delta
from quantgraph.graph.corpus_research import build_manifest, import_manifest
from test_corpus_export import origin
from test_corpus_research import collection


def test_reuse_exact_bytes_without_linking_source(tmp_path):
    store=tmp_path/'objects';a=tmp_path/'a';b=tmp_path/'b';c=tmp_path/'c'
    source=tmp_path/'source';source.write_bytes(b'content')
    materialize_immutable(source.read_bytes(),a,store)
    materialize_immutable(source.read_bytes(),b,store)
    materialize_immutable(b'different',c,store)
    assert a.stat().st_ino==b.stat().st_ino!=source.stat().st_ino
    assert c.stat().st_ino!=a.stat().st_ino
    assert a.stat().st_mode&0o222==0
    source.write_bytes(b'changed')
    assert a.read_bytes()==b'content'
    # Intentional copy-on-write preserves every other reference.
    a.unlink();a.write_bytes(b'new')
    assert b.read_bytes()==b'content'


@pytest.mark.parametrize('kind',['writable','corrupt','symlink','directory','fifo'])
def test_bad_existing_objects_fail_without_mutation(tmp_path,kind):
    data=b'hello';digest=hashlib.sha256(data).hexdigest();store=tmp_path/'store';shard=store/digest[:2];shard.mkdir(parents=True);obj=shard/digest
    if kind=='symlink':
        target=tmp_path/'target';target.write_bytes(data);obj.symlink_to(target)
    elif kind=='directory':obj.mkdir()
    elif kind=='fifo':os.mkfifo(obj)
    else:
        obj.write_bytes(b'wrong' if kind=='corrupt' else data)
        if kind=='corrupt':obj.chmod(0o400)
    before=obj.lstat()
    with pytest.raises((ValueError,OSError)):
        materialize_immutable(data,tmp_path/'destination',store)
    assert obj.lstat().st_ino==before.st_ino
    assert not (tmp_path/'destination').exists()


def test_store_symlink_and_sqlite_rejected(tmp_path):
    real=tmp_path/'real';real.mkdir();store=tmp_path/'link';store.symlink_to(real,target_is_directory=True)
    with pytest.raises(ValueError,match='non-symlink'):
        materialize_immutable(b'ok',tmp_path/'a',store)
    with pytest.raises(ValueError,match='SQLite'):
        materialize_immutable(b'SQLite format 3\x00extra',tmp_path/'b',real)


def test_concurrent_create_only_objects(tmp_path):
    def one(n):return materialize_immutable(b'concurrent',tmp_path/str(n),tmp_path/'store')
    with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(one,range(16)))
    assert len({(tmp_path/str(n)).stat().st_ino for n in range(16)})==1
    assert not list((tmp_path/'store').rglob('.object-*'))


def test_export_preserves_contract_and_imports_shared_objects(origin):
    o=origin;store=o['root']/'objects';second=o['root']/'second'
    r1=export_delta(o['origin'],o['protocol'],o['audit'],o['export'],object_store=store)
    r2=export_delta(o['origin'],o['protocol'],o['audit'],second,object_store=store)
    assert r1['manifest_sha256']==r2['manifest_sha256']
    for p in o['export'].iterdir():
        assert p.read_bytes()==(second/p.name).read_bytes()
        if p.name!='import-manifest.json':
            assert p.stat().st_ino==(second/p.name).stat().st_ino
            assert not p.is_symlink()
    assert (o['audit']/'record_audit.jsonl').stat().st_ino!=(second/'record_audit.jsonl').stat().st_ino
    r=import_manifest(o['runtime'],second/'import-manifest.json',r2['manifest_sha256'],second,second)
    assert not r.get('duplicate')
    db=o['runtime']/'corpus-research.sqlite'
    assert db.stat().st_nlink==1


def test_manifest_matches_legacy_independent_materialization(origin):
    o=origin;r=export_delta(o['origin'],o['protocol'],o['audit'],o['export'])
    old=o['root']/'old-style';old.mkdir()
    for p in o['export'].iterdir():
        if p.name!='import-manifest.json':(old/p.name).write_bytes(p.read_bytes())
    prior=build_manifest(old,old,old/'import-manifest.json')
    assert prior['manifest_sha256']==r['manifest_sha256']
    assert (old/'import-manifest.json').read_bytes()==(o['export']/'import-manifest.json').read_bytes()


def test_object_store_traversal_cannot_create_destination(origin):
    o=origin;store=o['root']/'elsewhere'/'..'/'export'/'store'
    with pytest.raises(ValueError,match='outside the new export'):
        export_delta(o['origin'],o['protocol'],o['audit'],o['export'],object_store=store)
    assert not o['export'].exists()


def test_corrupt_store_does_not_publish_partial_export(origin):
    o=origin;store=o['root']/'store';data=(o['audit']/'record_audit.jsonl').read_bytes()
    digest=hashlib.sha256(data).hexdigest();shard=store/digest[:2];shard.mkdir(parents=True)
    obj=shard/digest;obj.write_bytes(b'X'*len(data));obj.chmod(0o400)
    with pytest.raises(ValueError,match='digest mismatch'):
        export_delta(o['origin'],o['protocol'],o['audit'],o['export'],object_store=store)
    assert not o['export'].exists()
    assert not list(o['root'].glob('.corpus-export-*'))
