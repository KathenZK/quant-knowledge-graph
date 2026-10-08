"""Synthetic-only contract/security tests; never read retained private artifacts."""
import csv
from datetime import date, timedelta
import gzip
import hashlib
import io
import json
import sqlite3

from fastapi.testclient import TestClient
import pytest

from quantgraph.api.personal_app import create_personal_app
from quantgraph.api.web import create_web_app
from quantgraph.graph.catalog import CatalogRepository
from quantgraph.graph.corpus_research import (
    ARTIFACTS, DATABASE, MAX_CURVE_POINTS, CorpusResearch, build_manifest, import_manifest,
)
from scripts.personal_runtime import initialize


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def write_csv(rows, fieldnames):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


@pytest.fixture
def collection(tmp_path):
    results, audit = tmp_path / 'results', tmp_path / 'audit'
    results.mkdir()
    audit.mkdir()
    identity = 'synthetic-screen-v1'
    rows = [dict(run_id=identity, id='R1', name='PRIVATE_SYNTHETIC_SCREEN', status='tested', reason='', tested_variants='2', source_url='https://example.org/one'),
            dict(run_id=identity, id='R2', name='Unimplemented', status='not_implemented', reason='unsupported rule', tested_variants='0', source_url='https://example.org/two'),
            dict(run_id=identity, id='R3', name='Failed', status='failed', reason='synthetic calculation failed', tested_variants='0', source_url='https://example.org/three'),
            dict(run_id=identity, id='R4', name='Unavailable', status='market_data_unavailable', reason='missing required series', tested_variants='0', source_url='https://example.org/four')]
    specs = [dict(id='R1', variant_id='R1@A', family='family_a', assets=['S'], cash_asset='CASH', assumptions=['Synthetic assumptions'], source_authorship_verified=False),
             dict(id='R1', variant_id='R1@B', family='family_b', assets=['S'], cash_asset='CASH', assumptions=['Synthetic assumptions']),
             dict(id='R4', family='unavailable_family', assets=['MISSING'], cash_asset='CASH', assumptions=[])]
    specs_blob = encoded(specs)
    run = dict(run_id=identity, created_at_utc='2026-01-01T00:00:00+00:00', corpus_sha256='1'*64,
        protocol_sha256='2'*64, protocol_amendments_sha256='3'*64, implementation_specs_sha256=digest(specs_blob),
        market_data_manifest_sha256='4'*64, data_acquisition_status_sha256='5'*64,
        engine_code_sha256={'synthetic.py':'6'*64}, normalized_data_sha256={'S.csv':'7'*64},
        corpus_records=4, main_end='2024-01-02', descriptive_2026_end='2024-01-03')
    summary = dict(run_id=identity, corpus_records=4, tested_records=1, tested_variants=2,
        spec_variants=3, families=2, used_data_series=1, data_files=1, deep_selected=1,
        coverage_counts={'tested':1,'not_implemented':1,'failed':1,'market_data_unavailable':1})
    metrics = []
    for spec, total, latest in [(specs[0], 0.045, 0.02), (specs[1], -0.1, 0.0)]:
        metrics.append(dict(id='R1', variant_id=spec['variant_id'], name=rows[0]['name'], family=spec['family'],
            assets=['S'], cash_asset='CASH', run_id=identity, protocol_sha256=run['protocol_sha256'],
            implementation_specs_sha256=run['implementation_specs_sha256'], supplemental_defaults_flag=latest > 0,
            implementation_fidelity='Synthetic standardized implementation, not source-exact',
            spy_benchmark={'full':{'total_return':0.1}},
            periods={'full':{'start':'2024-01-01','end':'2024-01-02','observations':2,'total_return':total,'sharpe':None},
                     'latest_2026':{'start':'2024-01-03','end':'2024-01-03','observations':1,'total_return':latest}}))
    artifacts = {'run_manifest.json':encoded(run), 'run_summary.json':encoded(summary),
        'implemented_specs.json':specs_blob, 'strategy_metrics.json':encoded(metrics),
        'all_record_coverage.csv':write_csv(rows,list(rows[0])),
        'daily_returns.csv.gz':gzip.compress(b'date,R1@A,R1@B\n2024-01-01,0.1,-0.1\n2024-01-02,-0.05,0\n2024-01-03,0.02,0\n'),
        'deep_validation.json':encoded([{'variant_id':'R1@A','selection':'synthetic_only','additional_day_lag':{'total_return':0.01}}]),
        'record_audit.jsonl':b'\n'.join(encoded({'id':r['id'],'名称':r['name'],'source_url':r['source_url'],
            'source_verification_status':'readable' if r['id']=='R1' else 'not_individually_checked',
            'source_rule_attribution_status':'unverified','source_check_detail_file':'/private/never-expose'}) for r in rows),
        'source_verification.json':encoded({'input':{'sha256':run['corpus_sha256'],'row_count':4},
            'sample_summary':{'sample_size':1},'records':[{'checked_id':'R1','verdict':'partial_support',
                'source_access':{'status':'readable'},'source_supported':['Synthetic indicator context only'],
                'private_path':'/private/never-expose'}]})}
    for name, content in artifacts.items():
        ((results if ARTIFACTS[name]=='results' else audit)/name).write_bytes(content)
    return dict(root=tmp_path, results=results, audit=audit, runtime=tmp_path/'runtime', serial=0)


def pin(fixture):
    fixture['serial'] += 1
    path = fixture['root'] / f"manifest-{fixture['serial']}.json"
    receipt = build_manifest(fixture['results'], fixture['audit'], path)
    return path, receipt['manifest_sha256']


def ingest(fixture, pinned=None):
    path, expected = pinned or pin(fixture)
    return import_manifest(fixture['runtime'], path, expected, fixture['results'], fixture['audit'])


def mutate(fixture, name, change):
    path = (fixture['results'] if ARTIFACTS[name]=='results' else fixture['audit']) / name
    value = json.loads(path.read_bytes())
    change(value)
    path.write_bytes(encoded(value))


def test_import_replay_curves_and_retained_detail(collection):
    pinned = pin(collection)
    receipt = ingest(collection,pinned)
    assert receipt['new_trials']==0 and not receipt['duplicate']
    reader = CorpusResearch(collection['runtime'])
    summary = reader.summary()
    assert summary['counts']==dict(corpus_records=4,tested_records=1,tested_variants=2,used_data_series=1,data_files=1,
                                  standardized_implementations=2,supplemental_defaults_implementations=1)
    assert summary['coverage_counts']['failed']==1
    records = reader.records(status='tested',page_size=1)
    assert records['total']==1 and records['items'][0]['id']=='R1'
    assert records['items'][0]['tested_variants']==2
    assert 'catalog_refs' not in records['items'][0]  # No invented definition binding.
    assert set(records['items'][0]['audit'])=={'source_verification_status','source_rule_attribution_status'}
    result = reader.implementation('R1@A')
    assert result['metrics']['spy_benchmark']['full']['total_return']==0.1
    assert result['curve'][-1]['equity']==pytest.approx(1.1*0.95*1.02)
    assert result['curve'][1]['drawdown']==pytest.approx(-0.05)
    assert result['lineage']['definition_revision_bound'] is False
    assert result['audit']['source_verification']['verdict']=='partial_support'
    assert '/private/never-expose' not in json.dumps(result)
    assert result['curve_meta']['benchmark_curve_available'] is False
    assert reader.implementation('R1@B')['deep_validation'] is None
    before = (collection['runtime']/DATABASE).read_bytes()
    assert ingest(collection,pinned)['duplicate'] is True
    assert (collection['runtime']/DATABASE).read_bytes()==before
    with sqlite3.connect(collection['runtime']/DATABASE) as con:
        assert con.execute('SELECT COUNT(*) FROM corpus_artifacts').fetchone()[0]==len(ARTIFACTS)
        assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert (collection['runtime']/DATABASE).stat().st_mode & 0o777 == 0o600


def test_filters_pagination_and_unavailable_records(collection):
    ingest(collection)
    reader = CorpusResearch(collection['runtime'])
    assert reader.records(family='family_b')['items'][0]['id']=='R1'
    assert reader.records(q='synthetic_screen')['total']==1
    assert reader.records(q="' OR 1=1 --")['total']==0
    assert reader.records(page=2,page_size=2)['items'][0]['id']=='R3'
    for status in ['failed','market_data_unavailable','not_implemented']:
        item=reader.records(status=status)['items'][0]
        assert item['reason'] and not item['implementations'] and item['tested_variants']==0
    with pytest.raises(KeyError):
        reader.implementation('R4')
    with pytest.raises(KeyError):
        reader.summary('missing-run')


@pytest.mark.parametrize('artifact',list(ARTIFACTS))
def test_tampered_artifact_fails_before_any_runtime_write(collection,artifact):
    pinned=pin(collection)
    target=(collection['results'] if ARTIFACTS[artifact]=='results' else collection['audit'])/artifact
    target.write_bytes(target.read_bytes()+b' ')
    with pytest.raises(ValueError,match='digest or byte count mismatch'):
        ingest(collection,pinned)
    assert not collection['runtime'].exists()


def test_manifest_pin_and_extra_paths_cannot_select_files(collection):
    pinned=pin(collection)
    with pytest.raises(ValueError,match='Manifest digest mismatch'):
        ingest(collection,(pinned[0],'0'*64))
    body=json.loads(pinned[0].read_bytes())
    body['artifacts']['../../outside.json']={'sha256':'0'*64,'bytes':0}
    pinned[0].write_bytes(encoded(body))
    with pytest.raises(ValueError,match='every fixed-name artifact'):
        ingest(collection,(pinned[0],digest(pinned[0].read_bytes())))
    assert not collection['runtime'].exists()


def test_symlink_artifact_rejected(collection):
    target=collection['results']/'run_summary.json'
    real=collection['root']/'outside.json'
    target.rename(real)
    target.symlink_to(real)
    with pytest.raises(ValueError,match='non-symlink'):
        pin(collection)


@pytest.mark.parametrize(('filename','change','message'),[
    ('run_summary.json',lambda x:x.update(tested_records=2),'counts'),
    ('run_summary.json',lambda x:x['coverage_counts'].update(failed=0),'coverage counts'),
    ('strategy_metrics.json',lambda x:x[0].update(id='R2'),'identity'),
    ('strategy_metrics.json',lambda x:x.append(x[0]),'Duplicate'),
    ('strategy_metrics.json',lambda x:x[0].update(run_id='different'),'identity'),
    ('strategy_metrics.json',lambda x:x[0]['periods']['full'].update(observations=3),'observations'),
    ('strategy_metrics.json',lambda x:x[0]['periods']['full'].update(total_return=.5),'total return'),
    ('strategy_metrics.json',lambda x:x[0]['periods']['full'].update(start='invalid'),'date'),
    ('deep_validation.json',lambda x:x[0].update(variant_id='unknown'),'IDs'),
    ('source_verification.json',lambda x:x['input'].update(sha256='9'*64),'corpus digest'),
    ('source_verification.json',lambda x:x['records'][0].update(checked_id='UNKNOWN'),'IDs'),
])
def test_reconciliation_rejects_inconsistent_pinned_artifacts(collection,filename,change,message):
    mutate(collection,filename,change)
    with pytest.raises(ValueError,match=message):
        ingest(collection)
    assert not collection['runtime'].exists()


@pytest.mark.parametrize('csv_bytes',[
    b'date,R1@A,R1@B\n2024-01-01,nan,0\n',
    b'date,R1@A,R1@B\n2024-01-01,inf,0\n',
    b'date,R1@A,R1@B\n2024-01-01,-1.1,0\n',
    b'date,R1@A,R1@A\n2024-01-01,0,0\n',
    b'date,R1@A,R1@B\n2024-01-01,0,0\n2024-01-01,0,0\n',
    b'date,R1@A,R1@B\n2024-02-31,0,0\n',
    b'date,R1@A,R1@B\n2024-01-04,0,0\n',
    b'date,R1@A,R1@B\n2024-01-01,,0\n',
])
def test_invalid_returns_fail_without_writes(collection,csv_bytes):
    (collection['results']/'daily_returns.csv.gz').write_bytes(gzip.compress(csv_bytes))
    with pytest.raises(ValueError):
        ingest(collection)
    assert not collection['runtime'].exists()


def test_nonfinite_json_rejected(collection):
    path=collection['results']/'strategy_metrics.json'
    path.write_bytes(path.read_bytes().replace(b'0.045',b'NaN'))
    with pytest.raises(ValueError,match='Non-finite'):
        ingest(collection)


def test_coverage_count_and_missing_audit_rejected(collection):
    path=collection['results']/'all_record_coverage.csv'
    path.write_bytes(path.read_bytes().replace(b'tested,,2,',b'tested,,1,'))
    with pytest.raises(ValueError,match='Coverage tested'):
        ingest(collection)
    path.write_bytes(path.read_bytes().replace(b'tested,,1,',b'tested,,2,'))
    path=collection['audit']/'record_audit.jsonl'
    path.write_bytes(b'\n'.join(path.read_bytes().splitlines()[:-1]))
    with pytest.raises(ValueError,match='Audit and source IDs'):
        ingest(collection)


def test_conflicting_run_cannot_replace_retained_bytes(collection):
    ingest(collection)
    before=(collection['runtime']/DATABASE).read_bytes()
    mutate(collection,'deep_validation.json',lambda x:x[0].update(selection='different selection'))
    with pytest.raises(ValueError,match='Conflicting retained run ID'):
        ingest(collection)
    assert (collection['runtime']/DATABASE).read_bytes()==before
    assert CorpusResearch(collection['runtime']).implementation('R1@A')['deep_validation']['selection']=='synthetic_only'


def test_atomic_rollback_for_insertion_failure(collection):
    ingest(collection)
    database=collection['runtime']/DATABASE
    with sqlite3.connect(database) as con:
        con.execute("CREATE TRIGGER reject_import BEFORE INSERT ON corpus_records BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
    # Rename every run identity consistently; same source lineage may have another run.
    for name in ['run_manifest.json','run_summary.json']:
        mutate(collection,name,lambda x:x.update(run_id='synthetic-screen-v2'))
    mutate(collection,'strategy_metrics.json',lambda x:[v.update(run_id='synthetic-screen-v2') for v in x])
    coverage=collection['results']/'all_record_coverage.csv'
    coverage.write_bytes(coverage.read_bytes().replace(b'synthetic-screen-v1',b'synthetic-screen-v2'))
    with pytest.raises(sqlite3.IntegrityError,match='synthetic failure'):
        ingest(collection)
    assert [r['run_id'] for r in CorpusResearch(collection['runtime']).summary()['runs']]==['synthetic-screen-v1']
    with sqlite3.connect(database) as con:
        assert con.execute('SELECT COUNT(*) FROM corpus_artifacts').fetchone()[0]==len(ARTIFACTS)


def test_api_missing_private_only_and_read_only(collection):
    runtime=collection['runtime']
    missing=TestClient(create_personal_app(runtime=runtime))
    assert missing.get('/v1/personal/corpus-research').json()['available'] is False
    assert not (runtime/DATABASE).exists()
    ingest(collection)
    app=create_personal_app(runtime=runtime)
    client=TestClient(app)
    base='/v1/personal/corpus-research'
    assert client.get(base).json()['counts']['tested_variants']==2
    assert client.get(base+'/records',params={'status':'failed'}).json()['items'][0]['id']=='R3'
    assert client.get(base+'/implementations/R1@A').json()['variant_id']=='R1@A'
    assert client.get(base+'/implementations/R2').status_code==404
    assert client.get(base,params={'run_id':'missing'}).status_code==404
    assert client.get(base+'/records?page_size=101').status_code==422
    assert client.get(base+'/records?page=0').status_code==422
    assert client.get(base+'/records',params={'q':'x'*2001}).status_code==422
    portfolios='/v1/personal/source-portfolios'
    assert client.get(portfolios).json()==[]
    assert client.post(portfolios,json={}).status_code==405
    assert client.get(portfolios,headers={'Origin':'https://example.org'}).status_code==403
    assert client.post(base,json={}).status_code==405
    assert client.put(base+'/implementations/R1@A',json={}).status_code==405
    assert client.get(base,headers={'Origin':'https://example.org'}).status_code==403
    assert client.get(base,headers={'Sec-Fetch-Site':'cross-site'}).status_code==403
    assert client.get(base,headers={'Host':'example.org'}).status_code==400
    remote=TestClient(app,client=('192.0.2.1',9999))
    assert remote.get(base).status_code==403
    assert remote.get(portfolios).status_code==403
    public=TestClient(create_web_app(catalog=CatalogRepository(collection['root']/'public.sqlite')))
    for path in [base,base+'/records',base+'/implementations/R1@A',portfolios]:
        response=public.get(path)
        assert response.status_code==404
        assert 'PRIVATE_SYNTHETIC_SCREEN' not in response.text
    assert 'PRIVATE_SYNTHETIC_SCREEN' not in public.get('/v1/web/search?kind=strategy').text


def test_backup_retains_collection_database(collection):
    ingest(collection)
    with sqlite3.connect(collection['runtime']/'catalog.sqlite') as con:
        con.execute('CREATE TABLE synthetic(id TEXT)')
    initialize(collection['runtime'],collection['root']/'copy')
    copy=CorpusResearch(collection['root']/'copy')
    assert copy.summary()['run_id']=='synthetic-screen-v1'
    assert copy.implementation('R1@A')['curve'][-1]['equity']==pytest.approx(1.0659)


def test_curve_bounds_preserve_endpoints_and_daily_drawdown(collection):
    ingest(collection)
    import zlib
    observations=[[(date(2010,1,1)+timedelta(days=i)).isoformat(),-.001 if i%10==0 else .001] for i in range(2501)]
    observations[1333][1] = -.8
    observations[1777][1] = 10.0
    with sqlite3.connect(collection['runtime']/DATABASE) as con:
        # This unit test injects curve data only after removing the SQL safeguard.
        con.execute('DROP TRIGGER corpus_implementations_no_update')
        con.execute('UPDATE corpus_implementations SET returns=? WHERE variant_id=?',(zlib.compress(encoded(observations)),'R1@A'))
    result=CorpusResearch(collection['runtime']).implementation('R1@A')
    assert len(result['curve'])==MAX_CURVE_POINTS
    assert result['curve'][0]['date']==observations[0][0]
    assert result['curve'][-1]['date']==observations[-1][0]
    assert result['curve'][0]['drawdown']==pytest.approx(-.001)
    assert result['curve_meta']['total_observations']==2501
    assert observations[1333][0] in {point['date'] for point in result['curve']}
    equity=peak=1.0
    worst=0.0
    for _, number in observations:
        equity *= 1+number
        peak=max(peak,equity)
        worst=min(worst,equity/peak-1)
    assert min(point['drawdown'] for point in result['curve'])==pytest.approx(worst)


def test_append_only_tables_reject_update_and_delete(collection):
    ingest(collection)
    with sqlite3.connect(collection['runtime']/DATABASE) as con:
        for table in ['corpus_runs','corpus_records','corpus_artifacts','corpus_implementations']:
            with pytest.raises(sqlite3.IntegrityError,match='append-only'):
                con.execute(f'DELETE FROM {table}')
            with pytest.raises(sqlite3.IntegrityError,match='append-only'):
                con.execute(f'UPDATE {table} SET run_id=run_id')


def test_second_run_is_appended_and_selectable_without_rewriting_first(collection):
    first=ingest(collection)
    for name in ['run_manifest.json','run_summary.json']:
        mutate(collection,name,lambda x:x.update(run_id='synthetic-screen-v2'))
    mutate(collection,'run_manifest.json',lambda x:x.update(created_at_utc='2026-02-01T00:00:00Z'))
    mutate(collection,'strategy_metrics.json',lambda x:[v.update(run_id='synthetic-screen-v2') for v in x])
    path=collection['results']/'all_record_coverage.csv'
    path.write_bytes(path.read_bytes().replace(b'synthetic-screen-v1',b'synthetic-screen-v2'))
    second=ingest(collection)
    reader=CorpusResearch(collection['runtime'])
    assert first['manifest_sha256']!=second['manifest_sha256']
    assert reader.summary()['run_id']=='synthetic-screen-v2'
    assert [r['run_id'] for r in reader.summary()['runs']]==['synthetic-screen-v2','synthetic-screen-v1']
    assert reader.summary('synthetic-screen-v1')['manifest_sha256']==first['manifest_sha256']
    assert reader.implementation('R1@A',run_id='synthetic-screen-v1')['run_id']=='synthetic-screen-v1'
    with sqlite3.connect(collection['runtime']/DATABASE) as con:
        assert con.execute('SELECT COUNT(*) FROM corpus_artifacts').fetchone()[0]==2*len(ARTIFACTS)


def test_original_asset_and_weight_order_is_preserved(collection):
    # Result ordering may follow a sorted price frame; spec order binds params.
    specs_path=collection['results']/'implemented_specs.json'
    specs=json.loads(specs_path.read_bytes())
    for spec in specs[:2]:
        spec['assets']=['Z','S']
        spec['params']={'weights':[0.75,0.25],'asset_order':['Z','S']}
    specs_path.write_bytes(encoded(specs))
    spec_digest=digest(specs_path.read_bytes())
    mutate(collection,'run_manifest.json',lambda x:(x.update(implementation_specs_sha256=spec_digest),x['normalized_data_sha256'].update({'Z.csv':'8'*64})))
    mutate(collection,'strategy_metrics.json',lambda x:[m.update(assets=['S','Z'],implementation_specs_sha256=spec_digest) for m in x])
    mutate(collection,'run_summary.json',lambda x:x.update(used_data_series=2,data_files=2))
    ingest(collection)
    detail=CorpusResearch(collection['runtime']).implementation('R1@A')
    assert detail['metrics']['assets']==['S','Z']
    assert detail['spec']['assets']==['Z','S']
    assert detail['spec']['params']=={'weights':[.75,.25],'asset_order':['Z','S']}
    assert detail['lineage']['definition_revision_bound'] is False


def test_api_redacts_credentials_in_nested_retained_metadata(collection):
    mutate(collection,'strategy_metrics.json',lambda x:x[0].update(api_key='SECRET_VALUE',
        notes='https://example.org/report?access_token=SECRET_VALUE&id=42',
        nested={'authorization':'SECRET_VALUE','public':'visible','local_path':'/private/forbidden'},
        message='Unavailable /workspace/secret/data.csv and C:\\Users\\name\\secret.txt'))
    ingest(collection)
    client=TestClient(create_personal_app(runtime=collection['runtime']))
    response=client.get('/v1/personal/corpus-research/implementations/R1@A')
    assert response.status_code==200 and 'SECRET_VALUE' not in response.text
    assert '/private/forbidden' not in response.text and '/workspace/secret' not in response.text
    assert 'secret.txt' not in response.text
    assert response.json()['metrics']['nested']['public']=='visible'
    assert 'id=42' in response.json()['metrics']['notes']


def test_untested_record_has_complete_bounded_private_audit(collection):
    path=collection['audit']/'record_audit.jsonl'
    rows=[json.loads(line) for line in path.read_bytes().splitlines()]
    rows[1].update({'规则':'Unimplemented synthetic rule requiring missing data',
                    '作者或机构':'Synthetic source',
                    'mechanical_flags':{'has_entry':True,'api_key':'SECRET_VALUE'},
                    'source_check_detail_file':'/private/never-expose'})
    path.write_bytes(b'\n'.join(encoded(row) for row in rows))
    ingest(collection)
    client=TestClient(create_personal_app(runtime=collection['runtime']))
    base='/v1/personal/corpus-research/records/'
    response=client.get(base+'R2',params={'run_id':'synthetic-screen-v1'})
    assert response.status_code==200
    record=response.json()
    assert record['id']=='R2' and record['status']=='not_implemented'
    assert not record['implementations'] and record['tested_variants']==0
    assert record['audit']['规则']=='Unimplemented synthetic rule requiring missing data'
    assert record['audit']['作者或机构']=='Synthetic source'
    assert record['source_url']=='https://example.org/two'
    assert record['lineage']['definition_revision_bound'] is False
    assert 'SECRET_VALUE' not in response.text and '/private/never-expose' not in response.text
    assert 'PRIVATE_SYNTHETIC_SCREEN' not in response.text  # No unrelated record payload.
    assert client.get(base+'missing').status_code==404
    assert client.post(base+'R2',json={}).status_code==405
    public=TestClient(create_web_app(catalog=CatalogRepository(collection['root']/'public.sqlite')))
    assert public.get(base+'R2').status_code==404


def set_fidelity(fixture, category, variant='R1@A', reason='Explicit synthetic deviation'):
    for filename in ['implemented_specs.json', 'strategy_metrics.json']:
        def change(values):
            for value in values:
                if value.get('variant_id', value['id']) == variant:
                    value.update(fidelity_class=category, fidelity_reason=reason)
        mutate(fixture, filename, change)
    specs_digest=digest((fixture['results']/'implemented_specs.json').read_bytes())
    mutate(fixture,'run_manifest.json',lambda x:x.update(implementation_specs_sha256=specs_digest))
    mutate(fixture,'strategy_metrics.json',lambda x:[v.update(implementation_specs_sha256=specs_digest) for v in x])
    # R1 has another standardized variant, so a nonstandard addition is mixed.
    rows=list(csv.DictReader(io.StringIO((fixture['results']/'all_record_coverage.csv').read_text())))
    rows[0]['status']='tested' if category=='STANDARDIZED' else 'tested_mixed'
    (fixture['results']/'all_record_coverage.csv').write_bytes(write_csv(rows,list(rows[0])))
    mutate(fixture,'run_summary.json',lambda x:x['coverage_counts'].update({rows[0]['status']:x['coverage_counts'].pop('tested')}))


@pytest.mark.parametrize('category',['PROXY','HYPOTHESIS','PROXY_HYPOTHESIS'])
def test_explicit_fidelity_categories_preserve_origin_and_count_overlap(collection,category):
    set_fidelity(collection,category)
    ingest(collection)
    reader=CorpusResearch(collection['runtime'])
    summary=reader.summary()
    assert summary['fidelity_counts'][category]==dict(records=1,implementations=1)
    assert summary['fidelity_counts']['STANDARDIZED']==dict(records=1,implementations=1)
    assert summary['aggregate']['tested_records']==1  # Never sum overlapping record classes.
    detail=reader.implementation('R1@A')
    assert detail['fidelity_class']==category and detail['fidelity_reason']
    assert detail['origin_run_id']=='synthetic-screen-v1'
    assert reader.record('R1')['related_results'][0]['protocol_sha256']=='2'*64
    assert detail['lineage']['definition_revision_bound'] is False


@pytest.mark.parametrize('change,message',[
    (lambda x:x[0].update(origin_run_id='different-origin'),'origin_run_id'),
    (lambda x:x[0].update(origin_protocol_sha256='8'*64),'origin protocol'),
    (lambda x:x.clear(),'nonempty'),
    (lambda x:x[0].update(fidelity_class='SOURCE_EXACT'),'fidelity classes'),
])
def test_origin_and_empty_execution_rejected(collection,change,message):
    mutate(collection,'strategy_metrics.json',change)
    with pytest.raises(ValueError,match=message):
        ingest(collection)
    assert not collection['runtime'].exists()


def test_proxy_cannot_hide_reason_or_claim_plain_tested(collection):
    set_fidelity(collection,'PROXY')
    mutate(collection,'strategy_metrics.json',lambda x:x[0].update(fidelity_reason=''))
    with pytest.raises(ValueError,match='fidelity reasons'):
        ingest(collection)
    mutate(collection,'strategy_metrics.json',lambda x:x[0].update(fidelity_reason='Explicit synthetic deviation'))
    p=collection['results']/'all_record_coverage.csv'
    p.write_bytes(p.read_bytes().replace(b'tested_mixed',b'tested'))
    with pytest.raises(ValueError,match='status/count/fidelity'):
        ingest(collection)


def test_separate_run_protocols_aggregate_without_rewriting_prior(collection):
    first=ingest(collection)
    reader=CorpusResearch(collection['runtime'])
    prior=reader.implementation('R1@A',run_id='synthetic-screen-v1')
    set_fidelity(collection,'HYPOTHESIS')
    for name in ['run_manifest.json','run_summary.json']:
        mutate(collection,name,lambda x:x.update(run_id='synthetic-screen-v2'))
    mutate(collection,'run_manifest.json',lambda x:x.update(protocol_sha256='8'*64,created_at_utc='2026-02-01T00:00:00Z',observation_end='2024-01-03'))
    mutate(collection,'strategy_metrics.json',lambda x:[v.update(run_id='synthetic-screen-v2',origin_run_id='synthetic-screen-v2',protocol_sha256='8'*64) for v in x])
    p=collection['results']/'all_record_coverage.csv';p.write_bytes(p.read_bytes().replace(b'synthetic-screen-v1',b'synthetic-screen-v2'))
    ingest(collection)
    aggregate=reader.summary()['aggregate']
    assert aggregate['run_count']==2 and aggregate['tested_records']==1
    related=reader.record('R1')['related_results']
    assert len(related)==4 and {r['protocol_sha256'] for r in related}=={'2'*64,'8'*64}
    assert reader.implementation('R1@A',run_id=first['run_id'])==prior
    assert all(r['origin_run_id'] in aggregate['run_ids'] for r in related)


def test_distinct_corpus_hashes_never_aggregate(collection):
    ingest(collection)
    for name in ['run_manifest.json','run_summary.json']:
        mutate(collection,name,lambda x:x.update(run_id='other-corpus-run'))
    mutate(collection,'run_manifest.json',lambda x:x.update(corpus_sha256='a'*64,created_at_utc='2026-02-01T00:00:00Z'))
    mutate(collection,'source_verification.json',lambda x:x['input'].update(sha256='a'*64))
    mutate(collection,'strategy_metrics.json',lambda x:[v.update(run_id='other-corpus-run') for v in x])
    p=collection['results']/'all_record_coverage.csv';p.write_bytes(p.read_bytes().replace(b'synthetic-screen-v1',b'other-corpus-run'))
    ingest(collection)
    aggregate=CorpusResearch(collection['runtime']).summary()['aggregate']
    assert aggregate['run_ids']==['other-corpus-run'] and aggregate['run_count']==1


@pytest.mark.parametrize('category,status',[
    ('PROXY','tested_proxy_only'),('HYPOTHESIS','tested_hypothesis_only'),('PROXY_HYPOTHESIS','tested_mixed')])
def test_pure_nonstandard_record_never_claims_standardized_completion(collection,category,status):
    set_fidelity(collection,category)
    for filename in ['implemented_specs.json','strategy_metrics.json']:
        mutate(collection,filename,lambda values:[v.update(fidelity_class=category,fidelity_reason='Explicit synthetic deviation') for v in values if v.get('variant_id')=='R1@B'])
    specs_digest=digest((collection['results']/'implemented_specs.json').read_bytes())
    mutate(collection,'run_manifest.json',lambda x:x.update(implementation_specs_sha256=specs_digest))
    mutate(collection,'strategy_metrics.json',lambda x:[v.update(implementation_specs_sha256=specs_digest) for v in x])
    p=collection['results']/'all_record_coverage.csv';p.write_bytes(p.read_bytes().replace(b'tested_mixed',status.encode()))
    mutate(collection,'run_summary.json',lambda x:x['coverage_counts'].update({status:x['coverage_counts'].pop('tested_mixed')}))
    ingest(collection)
    reader=CorpusResearch(collection['runtime'])
    assert reader.record('R1')['status']==status
    assert reader.summary()['fidelity_counts']['STANDARDIZED']['records']==0
    assert reader.summary()['fidelity_counts'][category]['implementations']==2


def test_same_corpus_digest_with_changed_native_ids_is_rejected(collection):
    ingest(collection)
    before=(collection['runtime']/DATABASE).read_bytes()
    for name in ['run_manifest.json','run_summary.json']:
        mutate(collection,name,lambda x:x.update(run_id='contradictory-ids'))
    mutate(collection,'strategy_metrics.json',lambda x:[v.update(run_id='contradictory-ids') for v in x])
    p=collection['results']/'all_record_coverage.csv'
    p.write_bytes(p.read_bytes().replace(b'synthetic-screen-v1',b'contradictory-ids').replace(b',R2,',b',R2-new,'))
    p=collection['audit']/'record_audit.jsonl';rows=[json.loads(line) for line in p.read_bytes().splitlines()]
    rows[1]['id']='R2-new';p.write_bytes(b'\n'.join(encoded(r) for r in rows))
    with pytest.raises(ValueError,match='Same-corpus run record identities'):
        ingest(collection)
    assert (collection['runtime']/DATABASE).read_bytes()==before
