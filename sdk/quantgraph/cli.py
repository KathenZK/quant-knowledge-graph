import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from .db import FactorDB, project_root


def main():
    p=argparse.ArgumentParser(description='Quant Knowledge Graph, upstream of research only')
    p.add_argument('--root',type=Path)
    sp=p.add_subparsers(dest='command',required=True)
    s=sp.add_parser('factor-study-select');s.add_argument('--names',nargs='+',required=True);s.add_argument('--request-id',required=True);s.add_argument('--settings',type=Path,required=True);s.add_argument('--output',type=Path,required=True)
    s=sp.add_parser('factor-study-import');s.add_argument('file',type=Path);s.add_argument('--journal',type=Path,required=True)
    s=sp.add_parser('factor-study-query');s.add_argument('entity_id');s.add_argument('--journal',type=Path,required=True);s.add_argument('--profile',choices=['research','commercial'],default='commercial')
    for cmd in ('build','verify','stats','fetch','validate-release','build-public','verify-public'):sp.add_parser(cmd)
    for cmd in ('catalog-stats', 'catalog-validate'):sp.add_parser(cmd)
    s=sp.add_parser('catalog-show');s.add_argument('identity')
    s=sp.add_parser('catalog-search');s.add_argument('query',nargs='?',default=None)
    for field in ('kind','source','status','market','frequency','record-kind','subtype'):s.add_argument('--'+field)
    s.add_argument('--limit',type=int,default=50);s.add_argument('--offset',type=int,default=0)
    s=sp.add_parser('search');s.add_argument('query');s.add_argument('--profile',choices=['research','commercial'],default='research');s.add_argument('--limit',type=int,default=10)
    s=sp.add_parser('serve');s.add_argument('--profile',choices=['research','commercial'],default='commercial');s.add_argument('--port',type=int,default=8000)
    s=sp.add_parser('export-commercial');s.add_argument('destination',type=Path)
    s=sp.add_parser('import-grokbot');s.add_argument('archive',type=Path)
    sp.add_parser('verify-grokbot')
    s=sp.add_parser('ingest-batch');s.add_argument('file',type=Path);s.add_argument('--url',required=True);s.add_argument('--batch-id');s.add_argument('--collector-version');s.add_argument('--gzip',action='store_true')
    for cmd in ('projection-status', 'reproject', 'ingest-stats', 'review-record'):
        s=sp.add_parser(cmd);s.add_argument('--db',type=Path,default=os.getenv('QUANTGRAPH_INGEST_DB'))
        if cmd=='review-record':s.add_argument('file',type=Path)
    args=p.parse_args()
    if args.command in {'projection-status', 'reproject', 'ingest-stats', 'review-record'}:
        if not args.db or not Path(args.db).is_file():
            p.error('An existing private journal is required: --db or QUANTGRAPH_INGEST_DB')
        from quantgraph.graph.ingestion_store import SQLiteIngestionRepository
        repo=SQLiteIngestionRepository(args.db)
        method=getattr(repo,args.command.replace('-','_'))
        result=method(json.loads(args.file.read_text())) if args.command=='review-record' else method()
        print(json.dumps(result,ensure_ascii=False,indent=2));return
    if args.command=='ingest-batch':
        from .client import QuantGraphClient, load_batch
        result=QuantGraphClient(args.url).ingest_batch(load_batch(args.file,batch_id=args.batch_id,collector_version=args.collector_version),compress=args.gzip)
        print(json.dumps(result,ensure_ascii=False,indent=2));return
    root=project_root(args.root)
    if args.command.startswith('catalog-'):
        from quantgraph.graph.knowledge_catalog import KnowledgeCatalog
        catalog=KnowledgeCatalog(root)
        if args.command in {'catalog-stats','catalog-validate'}:result=catalog.stats()
        elif args.command=='catalog-show':result=catalog.get(args.identity)
        else:result=catalog.search(args.query,**{k:getattr(args,k) for k in
            ['kind','source','status','market','frequency','record_kind','subtype','limit','offset']})
        print(json.dumps(result,ensure_ascii=False,indent=2));return
    if args.command.startswith('factor-study-'):
        from .factor_study import draft_request
        from quantgraph.graph.factor_study_store import FactorStudyRepository
        db=FactorDB(root,profile='commercial')
        if args.command=='factor-study-select':
            result=draft_request(db,args.names,args.request_id,json.loads(args.settings.read_text()))
            with args.output.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
        elif args.command=='factor-study-import':
            result=FactorStudyRepository(args.journal,db).put(json.loads(args.file.read_text()))
        else:result=db.factor_studies(args.entity_id,journal=args.journal,profile=args.profile)
        print(json.dumps(result,ensure_ascii=False,indent=2));return
    if args.command in {'import-grokbot','verify-grokbot'}:
        from quantgraph.graph.grokbot import import_grokbot, verify_grokbot
        result=import_grokbot(root,args.archive) if args.command=='import-grokbot' else verify_grokbot(root)
        print(json.dumps(result,ensure_ascii=False,indent=2));return
    if args.command=='build-public':
        from quantgraph.graph.public import build_public
        result=build_public(root)
    elif args.command=='verify-public':
        from quantgraph.graph.public import verify_public
        result=verify_public(root)
    elif args.command=='build':
        from quantgraph.graph.build import build
        result=build(root)
    elif args.command=='verify':
        from quantgraph.graph.verify import verify
        result=verify(root)
    elif args.command=='fetch':
        from quantgraph.collectors.legacy_cli import fetch
        fetch(root);return
    elif args.command=='stats':result=FactorDB(root).stats()
    elif args.command=='search':result=FactorDB(root,profile=args.profile).search_factors(args.query,limit=args.limit)
    elif args.command=='serve':
        import uvicorn
        from quantgraph.api.app import create_app
        uvicorn.run(create_app(root,profile=args.profile),host='127.0.0.1',port=args.port);return
    elif args.command=='export-commercial':
        from quantgraph.graph.verify import verify
        verify(root)
        destination=args.destination.resolve()
        if destination.exists():raise ValueError('Destination exists; choose a new export directory')
        source=(root/'datasets/curated/current').resolve()/'commercial'
        shutil.copytree(source,destination)
        from quantgraph.graph.build import write_json, manifest
        write_json(destination/'manifest.json',manifest(destination))
        result={'status':'PASS','path':str(destination),'profile':'commercial','variants':FactorDB(root,profile='commercial').stats()['counts']['factor_variants']}
    elif args.command=='validate-release':
        from quantgraph.graph.build import build, write_json
        from quantgraph.graph.verify import verify
        before=(root/'datasets/curated/current').resolve().name
        result_build=build(root)
        env=os.environ.copy();env['PYTHONPATH']=str(root)+os.pathsep+str(root/'sdk')
        tests=subprocess.run([sys.executable,'-m','pytest','-q'],cwd=root,env=env,text=True,capture_output=True)
        checks=verify(root)
        result={'status':'PASS' if tests.returncode==0 and before==result_build['release_id'] else 'FAIL',
            'checked_at':datetime.now(timezone.utc).isoformat(),'deterministic_rebuild':before==result_build['release_id'],
            'release':result_build['release_id'],'tests_exit_code':tests.returncode,'tests_output':tests.stdout+tests.stderr,
            'verification':checks,'python':sys.version,'research_code_imported':False,'runner_endpoints':0}
        write_json(root/'reports/validation.json',result)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        raise SystemExit(result['status']!='PASS')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
