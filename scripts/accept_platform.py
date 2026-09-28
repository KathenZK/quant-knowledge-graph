"""Repeatable HTTP acceptance against real Catalog/Lab on an isolated runtime copy.

Unconfigured real research paths are BLOCKED, never substituted with fixtures.
The ingestion fixture is explicitly labelled and excluded from real counts.
"""
import argparse
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import time
from urllib.parse import quote
from uuid import uuid4

import requests


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--url',default='http://127.0.0.1:8761')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    cfg=json.loads(args.config.read_text())
    if cfg.get('acceptance_copy') is not True or Path(cfg['catalog_db']).parent != args.config.resolve().parent:
        raise ValueError('Acceptance mutations require an explicitly isolated local runtime copy')
    public=requests.Session();public.trust_env=False
    admin=requests.Session();admin.trust_env=False
    admin.headers['X-QuantGraph-Request']='1'
    report={'created_at':datetime.now(timezone.utc).isoformat(),'url':args.url,'scenarios':{},
            'preview':'NOT_DEPLOYED','public_production':'NOT_DEPLOYED','network':[]}

    def call(method,path,*,session=public,expected=200,**kwargs):
        response=session.request(method,args.url+path,timeout=30,**kwargs)
        report['network'].append({'method':method,'path':path.split('?')[0],'status':response.status_code})
        assert response.status_code==expected, f'{method} {path}: HTTP {response.status_code}'
        return response.json()

    def check(name,fn):
        try:report['scenarios'][name]={'status':'PASSED','evidence':fn()}
        except Exception as exc:report['scenarios'][name]={'status':'BLOCKED' if isinstance(exc,KeyError) else 'FAILED','reason':str(exc)}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')

    call('POST','/v1/admin/session',session=admin,
         json={'password':Path(cfg['admin_password_file']).read_text().strip()})
    with sqlite3.connect(cfg['catalog_db']) as con:
        con.row_factory=sqlite3.Row
        items=[json.loads(r['payload']) for r in con.execute("SELECT payload FROM catalog_items WHERE active=1 AND visibility='PUBLIC' AND kind='strategy'")]
        structured=next(v for v in items if v.get('record_level')=='variant' and not v.get('test_record'))

    def exploration():
        hit=call('GET','/v1/web/search',params={'kind':'strategy','q':structured['name'],'page_size':50})
        assert any(v['entity_id']==structured['entity_id'] for v in hit['items'])
        detail=call('GET','/v1/web/entities/strategy/'+quote(structured['entity_id'],safe=''))
        evidence={'strategy':detail['entity_id'],'name':detail['name'],'relationship_paths':{}}
        # Select real, existing endpoints from this copy, then verify HTTP traversal.
        with sqlite3.connect(cfg['catalog_db']) as con:
            for name,kinds in [('factor_factor',('variant','variant')),('strategy_strategy',('strategy','strategy')),('strategy_factor',('strategy','variant'))]:
                row=con.execute('''SELECT e.from_id,e.to_id,e.payload FROM catalog_edges e
                    JOIN catalog_items a ON a.entity_id=e.from_id JOIN catalog_items b ON b.entity_id=e.to_id
                    WHERE a.kind=? AND b.kind=? AND a.active=1 AND b.active=1
                    AND a.visibility='PUBLIC' AND b.visibility='PUBLIC' AND e.visibility='PUBLIC' LIMIT 1''',kinds).fetchone()
                if row is None:raise KeyError('Missing real relationship class: '+name)
                edge=json.loads(row[2]);response=call('GET','/v1/web/relations/'+quote(row[0],safe=''),params={'relation':edge['relation'],'limit':100})
                assert any(e['relationship_id']==edge['relationship_id'] for e in response['items'])
                for eid,kind in zip(row[:2],kinds):call('GET','/v1/web/entities/'+kind+'/'+quote(eid,safe=''))
                if name=='strategy_strategy':
                    compare=call('GET','/v1/web/compare',params=[('ref','strategy/'+eid) for eid in row[:2]])
                    assert len(compare['items'])==2
                if name=='strategy_factor':
                    reverse=call('GET','/v1/web/relations/'+quote(row[1],safe=''),params={'relation':edge['relation'],'limit':100})
                    assert any(e['relationship_id']==edge['relationship_id'] for e in reverse['items'])
                evidence['relationship_paths'][name]={'from':row[0],'to':row[1],'relation':edge['relation']}
        return evidence

    def research(case_name):
        case=cfg.get('acceptance_cases',{})[case_name]
        ref=case['entity_ref'];profile=cfg['profiles'][case['profile_id']]
        rid='acceptance-'+case_name+'-'+uuid4().hex
        body=dict(schema_version='research-request/v1',request_id=rid,idempotency_key=rid,
                  entity_refs=[ref],study_type=profile['study_type'],requested_settings={'profile_id':case['profile_id']})
        call('POST','/v1/research/jobs',json=body,headers={'X-QuantGraph-Request':'1'},expected=401)
        job=call('POST','/v1/research/jobs',session=admin,json=body,expected=202)
        retry=call('POST','/v1/research/jobs',session=admin,json=body,expected=202)
        assert retry['job_id']==job['job_id'] and retry['duplicate']
        deadline=time.monotonic()+profile['max_seconds']+40
        while job['status'] in {'QUEUED','RUNNING'} and time.monotonic()<deadline:
            time.sleep(.5)
            job=call('GET','/v1/research/jobs/'+job['job_id'],session=admin)
        assert job['status']=='SUCCEEDED',f"{job['status']}: {job.get('error')}"
        result=call('GET',job['result_url'])
        assert result['items'],'No publicly displayable real research result'
        assert any(r['sample'].get('real_market_data') is True for r in result['items'])
        kind='variant' if ref['entity_type']=='FactorVariant' else 'strategy'
        detail=call('GET','/v1/web/entities/'+kind+'/'+quote(ref['entity_id'],safe=''))
        assert any(r['job_id']==job['job_id'] for r in detail['results']['items'])
        if case_name=='evolution':assert any(r['lineage'] for r in result['items'])
        return {'job':job,'results':result['items']}

    def visibility():
        eid=structured['entity_id'];escaped=quote(eid,safe='')
        ref={k:structured[k] for k in ('entity_type','entity_id','definition_revision')}
        call('PATCH','/v1/admin/catalog',session=admin,json={'ids':[eid],'patch':{'visibility':'HIDDEN'}})
        try:
            for path in ['/v1/web/entities/strategy/'+escaped,'/v1/web/relations/'+escaped,'/v1/web/export/strategy/'+escaped]:
                call('GET',path,expected=404)
            call('GET','/v1/web/results',params={'kind':'strategy','eid':eid},expected=404)
            call('GET','/v1/research/results',params=ref,expected=404)
            assert not any(v['entity_id']==eid for v in call('GET','/v1/web/search',params={'kind':'strategy','q':structured['name'],'page_size':50})['items'])
            call('POST','/v1/web/references/resolve',json={'refs':[ref]},expected=409)
        finally:call('PATCH','/v1/admin/catalog',session=admin,json={'ids':[eid],'patch':{'visibility':'PUBLIC'}})
        call('GET','/v1/web/entities/strategy/'+escaped)
        return {'entity_id':eid,'restored':True,'server_surfaces':['detail','search','relations','export','results','references']}

    def ingestion():
        rid='C-ACCEPTANCE-TEST-'+uuid4().hex
        batch={'batch_id':rid+'-v1','collector_version':'platform-acceptance-test-only',
               'records':[dict(record_id=rid,name=rid,source_url='https://example.org/explicit-test-only',raw_market='美股ETF',
                               raw_rule='日频：若 RSI(7)>53 → 满仓 QQQ，否则 SHV。',
                               collected_at='2026-09-28T00:00:00Z',metadata={'fixture':True})]}
        first=call('POST','/v1/admin/imports/grokbot',session=admin,json=batch)
        again=call('POST','/v1/admin/imports/grokbot',session=admin,json=batch)
        assert again['replayed']
        one=call('GET','/v1/web/search',params={'kind':'strategy','q':rid})
        assert one['total']==1 and one['items'][0]['test_record']
        old=one['items'][0]
        batch['batch_id']=rid+'-v2';batch['records'][0]['raw_rule']='日频：若 RSI(7)>54 → 满仓 QQQ，否则 SHV。'
        call('POST','/v1/admin/imports/grokbot',session=admin,json=batch)
        new=call('GET','/v1/web/search',params={'kind':'strategy','q':rid})
        assert new['total']==1 and new['items'][0]['definition_revision']!=old['definition_revision']
        with sqlite3.connect(cfg['catalog_db']) as con:
            assert con.execute('SELECT count(*) FROM catalog_versions WHERE entity_id=? AND revision=?',(old['entity_id'],old['definition_revision'])).fetchone()[0]==1
        call('PATCH','/v1/admin/catalog',session=admin,json={'ids':[new['items'][0]['entity_id']],'patch':{'visibility':'HIDDEN'}})
        return {'record_id':rid,'first_receipt':first,'replay_idempotent':True,'history_retained':True,'test_only':True,'hidden_after_test':True}

    def retained_learning():
        from quantgraph.graph.research_import import import_manifest
        spec=cfg['retained_import']
        registry=Path(cfg['registry_path'])
        before=hashlib.sha256(registry.read_bytes()).hexdigest()
        receipt=import_manifest(cfg,spec['manifest'],spec['sha256'],spec['artifact_root'])
        assert all(v['duplicate'] for v in receipt['imported']) and receipt['new_trials']==0
        assert hashlib.sha256(registry.read_bytes()).hexdigest()==before
        collection=call('GET','/v1/research/collections')['items']
        one=next(v for v in collection if v['manifest_sha256']==spec['sha256'])
        assert one['imported_results']==len(receipt['imported'])
        path='/v1/research/collections/'+one['collection_id']+'/report'
        call('GET',path,expected=401)
        internal=call('GET',path,session=admin)
        assert internal['visibility']=='AUTHENTICATED_INTERNAL_RESEARCH' and internal['content']
        details={};failures=0;lineage=0
        for entry in receipt['imported']:
            job=call('GET','/v1/research/jobs/'+entry['job_id'],session=admin)
            assert job['attempts']==0 and job['stage']=='IMPORTED_COMPLETED_RESEARCH'
            if job['status']=='FAILED':
                failures+=1;assert job['error']
            for ref in job['entity_refs']:
                eid=ref['entity_id']
                if eid not in details:
                    kind='variant' if ref['entity_type']=='FactorVariant' else 'strategy'
                    details[eid]=call('GET','/v1/web/entities/'+kind+'/'+quote(eid,safe=''))
                result=next(r for r in details[eid]['results']['items'] if r['job_id']==job['job_id'])
                assert result['run_id']==entry['run_id'] and ref in result['entity_refs']
                for parent in result['lineage']:
                    kind='variant' if parent['entity_type']=='FactorVariant' else 'strategy'
                    item=call('GET','/v1/web/entities/'+kind+'/'+quote(parent['entity_id'],safe=''))
                    assert item['definition_revision']==parent['definition_revision'];lineage+=1
        return {'collection_id':one['collection_id'],'manifest_sha256':spec['sha256'],
                'retained_results':len(receipt['imported']),'retained_failures':failures,
                'lineage_references_resolved':lineage,'replay_duplicates':len(receipt['imported']),
                'new_trials':0,'registry_unchanged':True,'internal_report_verified':True}

    def recovery():
        if not cfg.get('allow_worker_interruption_test'):
            raise KeyError('Explicit isolated worker interruption test not configured')
        case=cfg['acceptance_cases']['factor'];profile=cfg['profiles'][case['profile_id']]
        rid='acceptance-recovery-'+uuid4().hex
        body=dict(request_id=rid,idempotency_key=rid,entity_refs=[case['entity_ref']],
                  study_type='FACTOR_DIAGNOSTIC',requested_settings={'profile_id':case['profile_id']})
        job=call('POST','/v1/research/jobs',session=admin,json=body,expected=202)
        registration=Path(cfg['output_root'])/job['job_id']/'research/study/trial-registration.json'
        deadline=time.monotonic()+30
        while not registration.exists() and time.monotonic()<deadline:time.sleep(.01)
        assert registration.exists(),'Worker did not register a real experiment before the fault test'
        pidfile=Path(cfg['job_db']).parent/'worker.pid';pid=int(pidfile.read_text())
        command=subprocess.check_output(['ps','-p',str(pid),'-o','command='],text=True)
        assert 'strategy_lab.platform_worker --config ' in command and str(args.config) in command
        # Only this supervised, isolated test worker is interrupted. The API and
        # original data stay available; the parent command restarts the worker.
        os.kill(pid,signal.SIGSTOP)
        try:
            before=call('GET','/v1/research/jobs/'+job['job_id'],session=admin)
            assert before['status']=='RUNNING','Computation already finished before the requested fault'
        finally:
            os.kill(pid,signal.SIGKILL)
        duplicate=call('POST','/v1/research/jobs',session=admin,json=body,expected=202)
        assert duplicate['job_id']==job['job_id'] and duplicate['duplicate']
        deadline=time.monotonic()+profile['max_seconds']+40
        while time.monotonic()<deadline:
            job=call('GET','/v1/research/jobs/'+job['job_id'],session=admin)
            if job['status'] not in {'QUEUED','RUNNING'}:break
            time.sleep(.5)
        assert job['status']=='SUCCEEDED' and job['attempts']==2, str(job)
        records=[json.loads(line)['data'] for line in Path(cfg['registry_path']).read_text().splitlines()]
        attempts=[r for r in records if r['kind']=='trial_attempt' and r['spec']['selection_campaign_id']=='factor-study-'+job['job_id']]
        assert len(attempts)==profile['trials_per_entity']
        assert len({r['attempt_id'] for r in attempts})==len(attempts)
        assert call('GET',job['result_url'])['items']
        return {'job':job,'registered_attempts':len(attempts),'duplicate_submission':True,
                'worker_restarted':int(pidfile.read_text())!=pid,'no_duplicate_statistical_trials':True}

    check('1_strategy_exploration',exploration)
    for name in ('factor','replication','evolution'):check(name,lambda name=name:research(name))
    check('4_retained_learning',retained_learning)
    check('5_visibility',visibility)
    check('6_ingestion',ingestion)
    check('7_worker_recovery',recovery)
    report['counts']=call('GET','/v1/web/meta')['counts']
    report['public_numerical_research']='AVAILABLE' if all(p.get('numeric_display') for p in cfg['profiles'].values()) else 'RESTRICTED_BY_DATA_RIGHTS'
    report['overall']='BRIDGE_PATHS_PASSED' if all(v['status']=='PASSED' for v in report['scenarios'].values()) else 'INCOMPLETE'
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'overall':report['overall'],'scenarios':{k:v['status'] for k,v in report['scenarios'].items()},'report':str(args.output)},ensure_ascii=False))
    raise SystemExit(0 if report['overall']=='BRIDGE_PATHS_PASSED' else 1)


if __name__=='__main__':main()
