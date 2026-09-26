"""Independent persisted-artifact verification; does not trust builder counters."""
import hashlib
import json
from pathlib import Path
import sqlite3
import pandas as pd
from quantgraph.models.entities import ENTITY_MODELS
from quantgraph.graph.store import encode, TYPES, PRIMARY_KEYS
from quantgraph.normalize.rights import commercial_allowed


def require(value,message):
    if not value:raise ValueError(message)


def verify_graph(path,commercial=False):
    path=Path(path)
    con=sqlite3.connect(path/'quantgraph.sqlite')
    require(con.execute('PRAGMA integrity_check').fetchone()[0]=='ok','SQLite integrity failure')
    require(not con.execute('PRAGMA foreign_key_check').fetchall(),'Foreign key failure')
    counts={}
    for file in sorted(path.glob('*.jsonl')):
        name=file.stem
        rows=[json.loads(line) for line in file.read_text().splitlines()]
        if name in ENTITY_MODELS:
            for row in rows:ENTITY_MODELS[name].model_validate(row)
        saved=[json.loads(r[0]) for r in con.execute(f'SELECT payload FROM "{name}" ORDER BY rowid')]
        require(rows==saved,name+' SQLite payload mismatch')
        columns=[r[1] for r in con.execute(f'PRAGMA table_info("{name}")') if r[1]!='payload']
        sql_rows=con.execute('SELECT '+','.join('"'+k+'"' for k in columns)+f' FROM "{name}" ORDER BY rowid').fetchall()
        expected=[tuple(encode(r.get(k)) for k in columns) for r in rows]
        require(sql_rows==expected,name+' SQLite columns mismatch')
        parquet=pd.read_parquet(path/(name+'.parquet'))
        require(len(parquet)==len(rows),name+' parquet count mismatch')
        csv=pd.read_csv(path/(name+'.csv'),dtype=str,keep_default_na=False)
        require(len(csv)==len(rows),name+' CSV count mismatch')
        # Full serialized field equality, including JSON arrays and formulas.
        for col in columns:
            def scalar(v):
                return None if v is None or (not isinstance(v,(list,dict)) and pd.isna(v)) else v
            exp=[encode(r.get(col)) for r in rows]
            require([scalar(v) for v in parquet[col].tolist()]==exp,name+':'+col+' parquet mismatch')
            require(csv[col].tolist()==['' if v is None else str(v) for v in exp],name+':'+col+' CSV mismatch')
        if name in TYPES:
            actual=con.execute('SELECT entity_id FROM entities WHERE entity_type=?',(TYPES[name],)).fetchall()
            require({v[0] for v in actual}=={r[PRIMARY_KEYS[name]] for r in rows},name+' registry mismatch')
        if name=='factor_variants':
            require(all(not r['backtest_ready'] for r in rows),'Unverified execution claim')
            if commercial:
                require(all(commercial_allowed(r) and r['source_id']=='qlib' for r in rows),'Commercial contamination')
        counts[name]=len(rows)
    for table, field, target, key in [('factor_variants','paper_ids','papers','paper_id'), ('factor_variants','source_record_ids','source_records','record_id'), ('papers','author_ids','authors','author_id'), ('strategies','factor_ids','factor_concepts','canonical_factor_id'), ('strategies','paper','papers','paper_id'), ('strategies','original_backtest','backtest_results','backtest_result_id'), ('strategies','reproduced_backtest','backtest_results','backtest_result_id')]:
        allowed={r[0] for r in con.execute(f'SELECT "{key}" FROM "{target}"')}
        for row in con.execute(f'SELECT "{field}" FROM "{table}"'):
            require(set(json.loads(row[0]))<=allowed,table+':'+field+' dangling JSON reference')
    wrong=con.execute('SELECT r.relationship_id FROM relationships r JOIN entities e ON r.from_id=e.entity_id WHERE r.from_type!=e.entity_type UNION SELECT r.relationship_id FROM relationships r JOIN entities e ON r.to_id=e.entity_id WHERE r.to_type!=e.entity_type').fetchall()
    require(not wrong,'Graph endpoint type mismatch')
    invalid_attribution=con.execute("SELECT sf.strategy_id FROM strategy_factor sf JOIN backtest_results b ON b.backtest_result_id=sf.backtest_result_id WHERE sf.attribution_status='EMPIRICALLY_TESTED' AND (b.result_kind='LEGACY_GROKBOT_SCREEN' OR b.strategy_id!=sf.strategy_id)").fetchall()
    require(not invalid_attribution,'Legacy screen or different strategy cannot support empirical attribution')
    if commercial:
        require({r[0] for r in con.execute('SELECT source_id FROM sources')} <= {'qlib'},'Restricted source in commercial graph')
        require(con.execute('SELECT count(*) FROM strategies').fetchone()[0]==0,'Unreviewed strategy in commercial graph')
    con.close()
    return counts


def verify(root):
    root=Path(root)
    from quantgraph.collectors.legacy_cli import check_sources
    source_count=check_sources(root)
    path=(root/'datasets/curated/current').resolve()
    manifest=json.loads((path/'manifest.json').read_text())
    actual={str(p.relative_to(path)) for p in path.rglob('*') if p.is_file() and p.name!='manifest.json'}
    require(set(manifest)==actual,'Missing or extra release artifact')
    for file,sha in manifest.items():
        require(hashlib.sha256((path/file).read_bytes()).hexdigest()==sha,'Release checksum: '+file)
    release = json.loads((path/'release.json').read_text())
    require(hashlib.sha256((root/'datasets/raw/source_lock.json').read_bytes()).hexdigest()==release['source_lock_sha256'], 'Source lock differs from release')
    require(hashlib.sha256((root/'models/id_registry.json').read_bytes()).hexdigest()==release['id_registry_sha256'], 'ID registry differs from release')
    for file,sha in json.loads((path/'code_manifest.json').read_text()).items():
        require(hashlib.sha256((root/file).read_bytes()).hexdigest()==sha,'Code changed since release: '+file)
    normalized=json.loads((root/'reports/normalized_manifest.json').read_text())
    for file,sha in normalized.items():
        require(hashlib.sha256((root/'datasets/normalized'/file).read_bytes()).hexdigest()==sha,'Normalized checksum: '+file)
    research=verify_graph(path);commercial=verify_graph(path/'commercial',commercial=True)
    require(research['factor_variants']>=500,'Phase-1 minimum not achieved')
    return dict(status='PASS',source_files=source_count,release=path.name,research=research,commercial=commercial)
