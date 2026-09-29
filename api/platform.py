"""Deployment glue for Catalog, durable research jobs and the registered Lab worker."""
import argparse
import json
from pathlib import Path

from quantgraph.api.admin import require_admin
from quantgraph.api.research_jobs import install_research_jobs, public_results
from quantgraph.api.web import create_web_app
from quantgraph.graph.catalog import CatalogRepository
from quantgraph.graph.catalog_projection import empty_results
from quantgraph.graph.ingestion_store import SQLiteIngestionRepository
from quantgraph.graph.research_jobs import ResearchJobRepository


def create_platform_app(config, *, admin_password=None):
    catalog = CatalogRepository(config['catalog_db'],
                                ingestion=SQLiteIngestionRepository(config['ingestion_db']))
    jobs = ResearchJobRepository(config['job_db'],config['profiles'],**config.get('limits',{}))

    def reader(kind=None,eid=None):
        values = [catalog.get(eid)] if eid else [catalog.get(ref['entity_id']) for ref in jobs.result_refs()
                                                if catalog.visible(ref['entity_id'])]
        items=[]
        for value in values:
            if kind and value['kind']!=kind:
                continue
            ref={k:value[k] for k in ('entity_type','entity_id','definition_revision')}
            items.extend(public_results(jobs,ref,catalog.visible))
        return {**empty_results(),'items':items,'total':len(items),
                'status':'已有研究结果' if items else '尚无可展示结果',
                'reason':'研究执行与结论级别分别记录；受限附件不在公开接口中。'}

    catalog.result_reader=reader

    def install(app,cat):
        install_research_jobs(app,jobs,resolve_ref=cat.resolve_ref,can_view=cat.visible,
                              auth_dependency=require_admin,collections=config.get('research_collections',{}))

    app=create_web_app(config['graph_root'],catalog=catalog,admin_password=admin_password,
                       research_installer=install)
    return app


def main():
    parser=argparse.ArgumentParser(description='Catalog and controlled research API; loopback by default')
    parser.add_argument('--config',required=True,type=Path)
    parser.add_argument('--port',type=int,default=8761)
    args=parser.parse_args()
    import uvicorn
    config=json.loads(args.config.read_text())
    password=Path(config['admin_password_file']).read_text().strip() if config.get('admin_password_file') else None
    uvicorn.run(create_platform_app(config,admin_password=password),
                host='127.0.0.1',port=args.port,access_log=False)


if __name__=='__main__':
    main()
