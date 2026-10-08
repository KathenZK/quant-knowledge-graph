import os
import sqlite3

import pytest

from quantgraph.graph.corpus_export import export_delta
from quantgraph.graph.corpus_workspace import initialize,append_collection,snapshot_runtime
from test_corpus_export import origin
from test_corpus_research import collection


def test_append_is_transactional_without_snapshot_clone(origin):
    o=origin;r=export_delta(o['origin'],o['protocol'],o['audit'],o['export'])
    initialize(o['runtime'])
    args=(o['runtime'],o['export']/'import-manifest.json',r['manifest_sha256'],o['export'],o['export'])
    append_collection(*args,reserve_bytes=0)
    db=o['runtime']/'corpus-research.sqlite';inode=db.stat().st_ino
    first=db.read_bytes()
    with pytest.raises(ValueError,match='digest mismatch'):
        append_collection(args[0],args[1],'0'*64,args[3],args[4],reserve_bytes=0)
    assert db.read_bytes()==first
    assert append_collection(*args,reserve_bytes=0)['duplicate']
    assert db.stat().st_ino==inode and db.stat().st_nlink==1
    with pytest.raises(ValueError,match='outside the mutable'):
        snapshot_runtime(o['runtime'],o['runtime']/'corpus-research.sqlite-wal',reserve_bytes=0)
    with sqlite3.connect(db) as con:
        con.execute('PRAGMA journal_mode=WAL')
    snapshot=o['root']/'frozen.sqlite'
    result=snapshot_runtime(o['runtime'],snapshot,reserve_bytes=0)
    assert result['status']=='FROZEN' and snapshot.stat().st_ino!=inode
    assert snapshot.stat().st_mode&0o222==0
    with sqlite3.connect('file:'+str(snapshot)+'?mode=ro&immutable=1',uri=True) as con:
        assert con.execute('PRAGMA quick_check').fetchone()[0]=='ok'
    before=snapshot.read_bytes()
    with pytest.raises(FileExistsError):snapshot_runtime(o['runtime'],snapshot,reserve_bytes=0)
    assert snapshot.read_bytes()==before


def test_frozen_and_hardlinked_databases_rejected(origin):
    o=origin;o['runtime'].mkdir()
    with pytest.raises(ValueError,match='Frozen or unmarked'):
        append_collection(o['runtime'],None,None,None,None,reserve_bytes=0)
    with pytest.raises(FileExistsError):initialize(o['runtime'])
    other=o['root']/'active';initialize(other);db=other/'corpus-research.sqlite';db.write_bytes(b'placeholder')
    os.link(db,o['root']/'alias')
    with pytest.raises(ValueError,match='independently allocated'):
        append_collection(other,None,None,None,None,reserve_bytes=0)


def test_reserve_rejection_does_not_create_database(origin):
    o=origin;r=export_delta(o['origin'],o['protocol'],o['audit'],o['export']);initialize(o['runtime'])
    with pytest.raises(ValueError,match='reserve'):
        append_collection(o['runtime'],o['export']/'import-manifest.json',r['manifest_sha256'],o['export'],o['export'],reserve_bytes=10**30)
    assert not (o['runtime']/'corpus-research.sqlite').exists()
