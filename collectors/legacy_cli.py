import argparse,hashlib,json,pathlib,sqlite3,sys
import pandas as pd
import requests
import jsonschema

DEFAULT_ROOT=pathlib.Path(__file__).resolve().parents[1]
def check_sources(root):
    lock=json.loads((root/'datasets/raw/source_lock.json').read_text());errors=[]
    for x in lock:
        p=root/x['path']
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=x['sha256']:errors.append(x['path'])
    if errors:raise ValueError('Frozen source checksum mismatch: '+', '.join(errors))
    return len(lock)

def fetch(root):
    """Restore only licensed pinned source files; never fetch financial observations."""
    lock=json.loads((root/'datasets/raw/source_lock.json').read_text())
    for x in lock:
        p=root/x['path']
        if p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==x['sha256']:continue
        if x['storage_policy']=='metadata_only':raise ValueError('Metadata snapshot missing; restore from bundle or review/reharvest website metadata: '+x['key'])
        r=requests.get(x['url'],timeout=60,headers={'User-Agent':'GlobalFactorLibrary/0.1 (public source reconstruction)'});r.raise_for_status()
        if hashlib.sha256(r.content).hexdigest()!=x['sha256']:raise ValueError('Remote content drift: '+x['url'])
        p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(r.content)
    print(json.dumps({'source_files_verified':check_sources(root)}))

def verify(root):
    count=check_sources(root);data=root/'datasets/normalized'
    records=[json.loads(x) for x in (data/'records.jsonl').read_text().splitlines()]
    schema=json.loads((root/'models/schemas/legacy/factor_record.schema.json').read_text());validator=jsonschema.Draft202012Validator(schema)
    for r in records:validator.validate(r)
    assert len({r['record_id'] for r in records})==len(records)
    con=sqlite3.connect(data/'factors.sqlite');assert not con.execute('PRAGMA foreign_key_check').fetchall();assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    manifest=json.loads((root/'reports/legacy/export_manifest.json').read_text())
    for path,h in manifest.items():assert hashlib.sha256((root/path).read_bytes()).hexdigest()==h,path
    tables={}
    for path in sorted(data.glob('*.jsonl')):
        if not (data/(path.stem+'.parquet')).exists():continue
        name=path.stem;rr=[json.loads(x) for x in path.read_text().splitlines()];par=pd.read_parquet(data/(name+'.parquet'));csv=pd.read_csv(data/(name+'.csv'),dtype=str,keep_default_na=False);n=con.execute('SELECT count(*) FROM "'+name+'"').fetchone()[0]
        assert len(rr)==len(par)==len(csv)==n,(name,len(rr),len(par),len(csv),n)
        # CSV exact text checks retain null-vs-empty distinction in JSONL/SQLite.
        from quantgraph.normalize.export import flatten
        flat=flatten(rr)
        for key in [k for k in par.columns if k.endswith('_id') or k in {'formula','normalized_formula','raw_definition'}]:
            expected=[r.get(key) for r in flat]
            assert [None if pd.isna(v) else v for v in par[key].tolist()]==expected,(name,key,'parquet')
            assert csv[key].tolist()==['' if v is None else str(v) for v in expected],(name,key,'csv')
            actual=con.execute('SELECT "'+key+'" FROM "'+name+'" ORDER BY rowid').fetchall()
            assert [x[0] for x in actual]==expected,(name,key,'sqlite')
        tables[name]=n
    con.close()
    return {'status':'PASS','frozen_source_files':count,'tables':tables,'schema':'PASS','unique_ids':'PASS','foreign_keys':'PASS','sqlite_integrity':'PASS','export_checksums':'PASS','csv_parquet_sqlite_key_and_formula_equality':'PASS'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=pathlib.Path,default=DEFAULT_ROOT);sp=p.add_subparsers(dest='cmd',required=True)
    sp.add_parser('build');sp.add_parser('fetch');sp.add_parser('verify');sp.add_parser('stats')
    q=sp.add_parser('search');q.add_argument('query');q.add_argument('--limit',type=int,default=12)
    args=p.parse_args();root=args.root.resolve()
    if args.cmd=='fetch':fetch(root)
    elif args.cmd=='build':
        check_sources(root)
        from quantgraph.collectors.pipeline import all_collectors
        from quantgraph.normalize.dedup.legacy import graph
        from quantgraph.normalize.export import export
        from quantgraph.normalize.quality import assess
        c=all_collectors(root);assess(c);tables=graph(c);tables['operators']=c.operator_registry;r=export(c,tables);print(json.dumps({k:v for k,v in r.items() if k not in {'field_missingness','issues'}},ensure_ascii=False,indent=2))
    elif args.cmd=='verify':print(json.dumps(verify(root),ensure_ascii=False,indent=2))
    elif args.cmd=='stats':print((root/'reports/legacy/quality.json').read_text())
    elif args.cmd=='search':
        con=sqlite3.connect(root/'datasets/normalized/factors.sqlite');con.row_factory=sqlite3.Row
        rows=con.execute('SELECT DISTINCT r.source_id,r.source_native_id,r.signal_name,r.canonical_factor_id,r.quality_tier,r.commercial_use_flag FROM records r LEFT JOIN aliases a ON a.canonical_factor_id=r.canonical_factor_id WHERE r.signal_name LIKE ? OR a.alias LIKE ? LIMIT ?',('%'+args.query+'%','%'+args.query+'%',args.limit)).fetchall();print(json.dumps([dict(r) for r in rows],ensure_ascii=False,indent=2))

if __name__=='__main__':main()
