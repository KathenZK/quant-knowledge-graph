"""Reproducible public Qlib release, isolated from locally held research data."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from quantgraph.collectors.common import Catalog
from quantgraph.collectors.qlib.collector import qlib
from quantgraph.normalize.dedup.legacy import graph
from quantgraph.normalize.quality import assess
from quantgraph.graph.curate import curate, commercial_subset
from quantgraph.graph.store import write_graph
from quantgraph.graph.verify import verify_graph, require
from quantgraph.graph.build import digest, manifest, write_json


def public_sources(root):
    root=Path(root)
    lock=json.loads((root/'datasets/raw/source_lock.json').read_text())
    selected=[r for r in lock if r['key'].startswith('qlib:')]
    require(len(selected)==3,'Expected three pinned Qlib source files')
    for row in selected:
        path=root/row['path']
        require(path.is_file() and digest(path)==row['sha256'],'Pinned Qlib source mismatch: '+row['path'])
    return selected


def build_public(root):
    root=Path(root).resolve()
    selected=public_sources(root)
    lock=root/'datasets/.publish.lock'
    try:lock.mkdir()
    except FileExistsError:raise RuntimeError('Another build holds the publication lock')
    staging=None
    try:
        catalog=Catalog(root);qlib(catalog);assess(catalog)
        legacy=graph(catalog)
        tables,decisions=curate(root,legacy)
        tables=commercial_subset(tables)
        parent=root/'datasets/public';parent.mkdir(parents=True,exist_ok=True)
        staging=Path(tempfile.mkdtemp(prefix='.build-',dir=parent))
        write_graph(staging,tables)
        shutil.copy2(root/'datasets/raw/sources/qlib/LICENSE',staging/'THIRD_PARTY_LICENSE.txt')
        (staging/'NOTICE.md').write_text('Qlib-derived expressions: Copyright Microsoft Corporation. MIT terms apply; see THIRD_PARTY_LICENSE.txt. QuantGraph modifies representation and grouping. Market data rights are excluded. No profitability or execution certification.\n')
        summary={'scope':'public_qlib','source_records':len(catalog.records),'curated_variants':len(tables['factor_variants']),
                 'concepts':len(tables['factor_concepts']),'formula_count':len(tables['formulas']),
                 'rejected_source_records':sum(not d['admitted'] for d in decisions),'source_files':3,
                 'id_registry_sha256':digest(root/'models/id_registry.json')}
        write_json(staging/'release.json',summary)
        write_json(staging/'source_lock.json',selected)
        verify_graph(staging,commercial=True)
        hashes=manifest(staging)
        release_id=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()[:20]
        write_json(staging/'manifest.json',hashes)
        releases=parent/'releases';releases.mkdir(exist_ok=True)
        target=releases/release_id
        if target.exists():
            require(manifest(target)==hashes,'Existing public release corrupted')
            shutil.rmtree(staging);staging=None
        else:
            staging.rename(target);staging=None
        next_pointer=parent/'.CURRENT-next'
        next_pointer.write_text(release_id+'\n')
        os.replace(next_pointer,parent/'CURRENT')
        return {'status':'PASS','release':release_id,**summary}
    finally:
        if staging and staging.exists():shutil.rmtree(staging)
        lock.rmdir()


def public_release(root):
    parent=Path(root)/'datasets/public'
    release_id=(parent/'CURRENT').read_text().strip()
    require(len(release_id)==20 and all(c in '0123456789abcdef' for c in release_id),'Invalid public release pointer')
    return parent/'releases'/release_id


def verify_public(root):
    root=Path(root)
    selected=public_sources(root)
    release=public_release(root)
    hashes=json.loads((release/'manifest.json').read_text())
    require(manifest(release)==hashes,'Public release checksums changed')
    require(hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()[:20]==release.name,'Public release ID mismatch')
    require(json.loads((release/'source_lock.json').read_text())==selected,'Public source lock mismatch')
    summary=json.loads((release/'release.json').read_text())
    require(summary['id_registry_sha256']==digest(root/'models/id_registry.json'),'ID registry changed')
    counts=verify_graph(release,commercial=True)
    require(counts['factor_variants']==508,'Unexpected public cohort size')
    return {'status':'PASS','release':release.name,'counts':counts}
