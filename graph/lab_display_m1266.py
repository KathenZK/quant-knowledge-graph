"""Exact public-light M1266 contract; no private C0, execution or source discovery."""
import calendar
from copy import deepcopy
import math

from quantgraph.graph.corpus_research import _finite, _loads
from quantgraph.graph.metadata_pilot import digest, encoded, read_below

ID = 'M1266'
PIN = 'd15ce516b56c4bc6e57ac8c6eb4dd474defef451'
ORIGINAL_PIN = '18abce049b3b260bee9e594354f5c8ddb10155b8'
CONTRACT = 'M1266_CORRECTED_SOURCE_FIXED_QTY_ACCEPTED_LIGHT_V1'
PROFILE = 'M1266_ACCEPTED_LIGHT_DAILY_SAMPLED_V1'
KIND = 'PUBLIC_DERIVED_DISPLAY_MANIFEST'
LOCK_KIND = 'SELECTED_APPROVED_PUBLIC_LIGHT_SOURCE_LOCK_NOT_PUBLICATION_OR_C0'
MANIFEST_SCHEMA = 'M1266-public-derived-display-manifest/v1'
RULE_KIND = 'PUBLIC_SELF_AUTHORED_OPERATIONAL_RULES_NOT_ORIGINAL_C0_PROTOCOL'
FIDELITY = 'ADAPTED_SOURCE_CORRECTED_VARIANT'
EXECUTION = 'HYPOTHESIS_EXECUTION_PROXY'
RUN = 'M1266-catalog-batch019-20261003-v1'
VARIANT = RUN+'-base'
ACCEPTED = 'ACCEPTED_INDEPENDENTLY_VALIDATED_ADAPTED_DIAGNOSTIC'
PENDING = 'HISTORICAL_VERIFIED_COORDINATOR_ACCEPTANCE_PENDING'
C0_SHA = 'adcf2862aaa7af28b19ced8432c62c23e314fd4ba6e3ec1e687cfd679c08a0f7'
RELEASE_SHA = 'debb6431803fc180c5fa31e7572b4c248d37c62be01b1886c30145885efd5225'
COSTS = [dict(name=n,fee_bps_each_side=f,slippage_bps_each_side=2,delay_bars=l)
         for n,f,l in [('base',8,1),('fee0',0,1),('fee20',20,1),('delay2',8,2)]]
RULE_KEYS = ['identity','indicators','entry','exit','execution','benchmark','cases','statistics']
# Independently reviewed public role lock. This is not a historical publication/C0 inventory.
SOURCE_LOCK = {'acceptance_note': {'bytes': 1695,
                     'path': 'research/public-strategies/M1266/README-results-v1.md',
                     'sha256': 'd3771dbe7c06a9cce79c04594eac089a4d61c88f480ecd42832a62d124b5d298',
                     'url': 'https://github.com/KathenZK/quant-research-lab/blob/d15ce516b56c4bc6e57ac8c6eb4dd474defef451/research/public-strategies/M1266/README-results-v1.md'},
 'approved_report': {'bytes': 16996,
                     'path': 'research/public-strategies/M1266/M1266.md',
                     'sha256': '65de7aca1c33151e51de311868266c177c4484d9700e0b735cf03cc3e6b971a1',
                     'url': 'https://github.com/KathenZK/quant-research-lab/blob/d15ce516b56c4bc6e57ac8c6eb4dd474defef451/research/public-strategies/M1266/M1266.md'},
 'coordinator_acceptance': {'bytes': 4384,
                            'path': 'research/public-strategies/M1266/recovery/coordinator-acceptance-20261003/acceptance.safe.json',
                            'sha256': '05d0d1511fad0793e5582a7a4166c74f45e9f754a7799b3e52ce2cf33d019a0d',
                            'url': 'https://github.com/KathenZK/quant-research-lab/blob/d15ce516b56c4bc6e57ac8c6eb4dd474defef451/research/public-strategies/M1266/recovery/coordinator-acceptance-20261003/acceptance.safe.json'},
 'metrics': {'bytes': 6983,
             'path': 'research/public-strategies/M1266/artifacts/20261003-batch019-v1/metrics.json',
             'sha256': 'aad07b6283b87b537fefccaa6f63b866f17b64c0bc0ddfefc3d132bcdef398b2',
             'url': 'https://github.com/KathenZK/quant-research-lab/blob/d15ce516b56c4bc6e57ac8c6eb4dd474defef451/research/public-strategies/M1266/artifacts/20261003-batch019-v1/metrics.json'},
 'operational_rules': {'bytes': 8747,
                       'path': 'research/public-strategies/M1266/specs/operational-rules-v1.json',
                       'sha256': 'b5def845de7f4ca03f2cacc86b19ef879a3e8ffbb771960dc3caec2a000931ec',
                       'url': 'https://github.com/KathenZK/quant-research-lab/blob/d15ce516b56c4bc6e57ac8c6eb4dd474defef451/research/public-strategies/M1266/specs/operational-rules-v1.json'},
 'original_detail': {'bytes': 14927,
                     'path': 'research/public-strategies/M1266/artifacts/20261003-batch019-v1/graph-detail.json',
                     'sha256': '699f2e228532ab738aa0967214e1f7c147d4ed14632bafe841808df1783ef0ac',
                     'url': 'https://github.com/KathenZK/quant-research-lab/blob/d15ce516b56c4bc6e57ac8c6eb4dd474defef451/research/public-strategies/M1266/artifacts/20261003-batch019-v1/graph-detail.json'},
 'original_record': {'bytes': 1801,
                     'path': 'research/public-strategies/M1266/artifacts/20261003-batch019-v1/graph-record.json',
                     'sha256': '017d2f2b8fbb2b7062812674af9d3f555eb2a249b322a6f15c6f9e79a040f6e7',
                     'url': 'https://github.com/KathenZK/quant-research-lab/blob/d15ce516b56c4bc6e57ac8c6eb4dd474defef451/research/public-strategies/M1266/artifacts/20261003-batch019-v1/graph-record.json'},
 'public_scope_review': {'bytes': 9767,
                         'path': 'research/public-strategies/M1266/recovery/coordinator-acceptance-20261003/publication-review.safe.json',
                         'sha256': '6a5e98783fd015ed4a417e77c470b29fbcd702a6e5dd5cede7ddf4e59ef347f2',
                         'url': 'https://github.com/KathenZK/quant-research-lab/blob/d15ce516b56c4bc6e57ac8c6eb4dd474defef451/research/public-strategies/M1266/recovery/coordinator-acceptance-20261003/publication-review.safe.json'},
 'receipt_evidence_review': {'bytes': 7906,
                             'path': 'research/public-strategies/M1266/recovery/coordinator-acceptance-20261003/receipt-evidence-review.safe.json',
                             'sha256': '1f8f53adcc6afa459b934964829e15b9c33e5e8a8a63b467b55c16b9bde18ec9',
                             'url': 'https://github.com/KathenZK/quant-research-lab/blob/d15ce516b56c4bc6e57ac8c6eb4dd474defef451/research/public-strategies/M1266/recovery/coordinator-acceptance-20261003/receipt-evidence-review.safe.json'}}


def require(ok, reason):
    if not ok:
        raise ValueError('M1266: '+reason)


def same(value, expected, reason):
    require(encoded(value)==encoded(expected), reason)


def number(value, reason, nullable=False):
    if nullable and value is None:
        return
    try:
        valid=type(value) in [int,float] and math.isfinite(value)
    except OverflowError:
        valid=False
    require(valid, reason)


def selected(entry):
    return entry.get('id')==ID or entry.get('source_contract')==CONTRACT or entry.get('projection_profile')==PROFILE


def check_entry(entry):
    require(entry.get('id')==ID and entry.get('lab_commit')==PIN and entry.get('source_contract')==CONTRACT
            and entry.get('projection_profile')==PROFILE and entry.get('manifest_kind')==KIND
            and entry.get('source_inventory_kind')==LOCK_KIND and entry.get('fidelity_class')=='ADAPTED'
            and entry.get('run_id')==RUN and entry.get('variant_id')==VARIANT,
            'Exact public-light identity/profile/type/pin required')
    same(entry['artifacts'],SOURCE_LOCK,'Only the exact nine approved source roles may be read')


def verified_source(root, entry):
    check_entry(entry)  # Before any path is opened; no extra private role permitted.
    blobs={}
    for role,ref in SOURCE_LOCK.items():
        body=read_below(root,ref['path'])
        require(len(body)==ref['bytes'] and digest(body)==ref['sha256'],'Frozen public source mismatch: '+role)
        blobs[role]=body
    return blobs


def metric(value):
    numeric=['total_return','cagr','max_drawdown','exposure','fees_paid','initial_equity','final_equity','sharpe','sharpe_zero_cash']
    ints=['observations','annualization','closed_roundtrips','fill_count','monthly_count','rejected_order_count']
    require(set(value)==set(numeric+ints+['start','end','end_exclusive','status']), 'Exact compact metric fields required; do not fill missing indicators')
    for key in numeric:
        number(value[key],'Finite numeric metric required: '+key,nullable=key in ['sharpe','sharpe_zero_cash'])
    for key in ints:
        require(type(value[key]) is int and value[key]>=0,'Integer metric count required: '+key)
    for key,n in [('observations',731),('annualization',365),('monthly_count',24)]:
        same(value[key],n,'Frozen metric observation count: '+key)
    same(value['initial_equity'],100000.0,'Initial capital representation must remain unchanged')
    same(value['sharpe'],value['sharpe_zero_cash'],'Sharpe alias/null conflict')
    require(value['start']=='2023-01-01' and value['end']=='2024-12-31' and value['end_exclusive']=='2025-01-01'
            and value['status']==PENDING,'Original metric window/publication status changed')
    require(value['total_return']>=-1 and value['cagr']>=-1 and -1<=value['max_drawdown']<=0
            and 0<=value['exposure']<=1 and value['fees_paid']>=0 and value['final_equity']>=0,
            'Metric outside the defined range')


def validate(entry, blobs):
    check_entry(entry)
    require(set(blobs)==set(SOURCE_LOCK),'Exact public source role set required')
    for role,ref in SOURCE_LOCK.items():
        require(digest(blobs[role])==ref['sha256'] and len(blobs[role])==ref['bytes'],'Pinned public source changed: '+role)
    v={k:_loads(b) for k,b in blobs.items() if SOURCE_LOCK[k]['path'].endswith('.json')}
    _finite(v)
    r,d,m,rules,acc,pub,ev=(v[k] for k in ['original_record','original_detail','metrics','operational_rules',
                                         'coordinator_acceptance','public_scope_review','receipt_evidence_review'])
    require(all(x.get('id')==ID for x in [r,d,m,rules,acc]) and d['run_id']==d['origin_run_id']==m['run_id']==rules['run_id']==RUN
            and d['variant_id']==VARIANT,'Immutable original execution identity mismatch')
    require(m['schema']=='M1266-lightweight-metrics/v1' and rules['schema']=='M1266-self-authored-operational-rules/v1'
            and acc['schema']=='coordinator-research-acceptance/v1','Source schema mismatch')
    require(not any(k in x for x in [r,d] for k in ['entity_id','definition_revision']), 'Native identity must not be invented')
    require(d['fidelity_class']==rules['classification']==m['classification']==acc['classification']==FIDELITY
            and d['execution_class']==rules['execution_class']==m['execution_class']==acc['execution_class']==EXECUTION,
            'Corrected-source classification/execution must not be relabeled')
    for audit in [r['audit'],m['audit'],rules['audit']]:
        same(audit,d['audit'],'Original publication audit must remain identical and pending')
    original_audit=d['audit']
    for key,val in dict(accepted=False,trusted=False,OOS=False,window_OOS=False,original_runtime_equivalence=False,
                        strict_reproductions=0,PIT='UNKNOWN',publication_review_status='PENDING_EXACT_ALLOWLIST_REVIEW').items():
        same(original_audit[key],val,'Original pending/quality boundary changed: '+key)
    for obj in [acc,rules]:
        for key,val in dict(trusted=False,OOS=False,strict_reproductions=0,PIT='UNKNOWN').items():
            same(obj[key],val,'Acceptance is not a quality upgrade: '+key)
    require(acc['status']==ACCEPTED and acc['C0_sha256']==pub['C0_sha256']==ev['C0_sha256']==C0_SHA
            and acc['root_release_sha256']==pub['release_sha256']==ev['root_release_sha256']==RELEASE_SHA,
            'Coordinator acceptance/C0/release hash-only binding conflict')
    require(acc['public_delivery']['public_review_sha256']==digest(blobs['public_scope_review'])
            and acc['receipt_cross_review']['sha256']==digest(blobs['receipt_evidence_review']),
            'Acceptance must bind both exact public reviews')
    require(pub['reviewed_commit']==ORIGINAL_PIN,'Static review is not an original publication manifest')
    same(pub['file_count'],12,'Original public file count');same(pub['file_bytes'],77633,'Original public byte count')
    allowed={x['path']:x for x in pub['files']};require(len(allowed)==12,'Exact unique original public review set')
    for role in ['original_record','original_detail','metrics','operational_rules','approved_report']:
        ref=entry['artifacts'][role]
        same({k:allowed[ref['path']][k] for k in ['bytes','sha256']},{k:ref[k] for k in ['bytes','sha256']},'Original public allowlist mismatch: '+role)
    for obj,key,n in [(m,'strategy_configurations',4),(m,'new_controls',1),(acc,'new_strategy_configurations',4),
                      (acc,'new_original_controls',1),(rules['benchmark'],'new_controls',1)]:
        same(obj[key],n,'Exact original experiment count: '+key)
    recovery=acc['recovery'];local=ev['local_review_scope']
    for key,val in dict(parent_actual_Library_saved_and_restored=True,archive_entries=292,
            root_full_archive_materialized_or_historical_replayed=False,later432entry_addendum_in_this_receipt_scope=False,
            new_trials_from_recovery=0).items():
        same(recovery[key],val,'Preserve the actual receipt/recovery scope: '+key)
    for key in ['historical_result_bytes_received','local_Library_materialization','local_original_runner_replay','market_input_bytes_read']:
        same(local[key],False,'Receipt review is not local history/full-archive execution')
    same(rules['cases'],COSTS,'Rule fee/day-lag configuration conflict');same(m['cases'],COSTS,'Metric fee/day-lag configuration conflict')
    require('q=0.9*100000/close' in rules['benchmark']['sizing'] and rules['benchmark']['name']=='buyhold-base',
            'Own fixed90-percent signal quantity control required; never M1258/fullcash')
    same(rules['indicators']['periods'],[20,50,100],'EMA periods changed')
    for key,val in dict(evaluation_rows=731,warmup_rows=100,initial_equity='100000',symbol='BTCUSDT',timeframe='UTC 1d').items():
        same(rules['identity'][key],val,'Frozen public execution identity: '+key)
    same(d['metrics'],m['metrics'],'Detail metrics differ from approved compact source')
    metrics=d['metrics']
    require(set(metrics)=={'periods','same_instrument_benchmark','additional_native_bar_lag','cost_sensitivity',
                          'execution_class','implementation_fidelity','fee_control_limitation'}
            and set(metrics['cost_sensitivity'])=={'0','20'},'Frozen metric container/cost labels changed')
    require(metrics['execution_class']==EXECUTION and metrics['implementation_fidelity']==FIDELITY,
            'Metric source/execution fidelity mismatch')
    require(metrics['fee_control_limitation']==m['fee_control_limitation']==rules['benchmark']['fee_control_limitation'],
            'Matched-cost control limitation must remain explicit')
    containers=[metrics[k] for k in ['periods','same_instrument_benchmark','additional_native_bar_lag']]+list(metrics['cost_sensitivity'].values())
    for periods in containers:
        require(set(periods)=={'full'},'Do not create unapproved annual or OOS statistics')
        metric(periods['full'])
    same(metrics['cost_sensitivity']['0']['full']['fees_paid'],0.0,'Zero fee must remain a present numeric zero')
    for role,name in [('base','periods'),('declared_control','same_instrument_benchmark')]:
        same(acc['quality'][role],{k:v for k,v in metrics[name]['full'].items() if k!='status'},'Accepted metric values conflict')
    dates=['2023-01-01']+[f'{y}-{mo:02d}-{calendar.monthrange(y,mo)[1]}' for y in [2023,2024] for mo in range(1,13)]
    for name,key in [('curve','periods'),('benchmark_curve','same_instrument_benchmark')]:
        points=d[name]
        require(len(points)==25 and [p['date'] for p in points]==dates,'Only original anchor plus24 sampled dates permitted')
        same(points[0],dict(date='2023-01-01',equity=1.0,drawdown=0.0),'Pre-open initial capital anchor changed')
        for point in points:
            require(set(point)=={'date','equity','drawdown'},'Unexpected curve field')
            number(point['equity'],'Curve equity must be numeric');number(point['drawdown'],'Curve drawdown must be numeric')
            require(point['equity']>=0 and -1<=point['drawdown']<=0,'Curve range invalid')
        require(math.isclose(points[-1]['equity'],metrics[key]['full']['final_equity']/100000,rel_tol=0,abs_tol=3e-15),
                'Approved units must not be renormalized or rebased')
    for key,val in dict(point_count=25,benchmark_point_count=25,source_observations=731,normalized_to_initial=100000,
                        initial_anchor_date='2023-01-01',initial_anchor_phase='before first evaluation open, not Jan1 close').items():
        same(d['curve_meta'][key],val,'Original sampled curve semantics changed: '+key)
    require(rules['source']['full_text_or_attachment_redistribution'] is False
            and r['selected_source_sha256']==rules['source']['selected_source_sha256']==d['spec']['selected_source_sha256']
            and r['source_url']==d['spec']['source_url']==rules['source']['url'],'Self-authored attribution/source hash conflict')
    same(d['data_attribution'],m['data_attribution'],'Derived-data attribution must be preserved')
    require(d['data_attribution']['derived_data_license']=='CC BY-NC-SA 4.0', 'Derived-data license scope cannot expand')
    return v


def display_manifest(entry):
    return dict(schema_version=MANIFEST_SCHEMA,manifest_kind=KIND,id=ID,origin_run_id=RUN,variant_id=VARIANT,
        lab_commit=PIN,source_contract=CONTRACT,projection_profile=PROFILE,source_inventory_kind=LOCK_KIND,
        source_artifacts=deepcopy(entry['artifacts']),original_private_result_manifest=False,
        historical_publication_manifest=False,original_results_modified=False,
        hash_scope='EXPLICIT_APPROVED_PUBLIC_SOURCE_BYTES_ONLY',self_or_output_hashes_included=False,
        original_counts=dict(strategy_configurations=4,new_control_configurations=1),
        projection_activity=dict(new_strategy_trials=0,new_controls=0))


def project(entry,blobs):
    try:
        v=validate(entry,blobs)
    except (KeyError,TypeError,IndexError) as exc:
        raise ValueError('M1266: Missing or malformed public-light source') from exc
    original=v['original_record'];d=deepcopy(v['original_detail']);rules=v['operational_rules'];acc=v['coordinator_acceptance']
    manifest=display_manifest(entry);manifest_sha=digest(encoded(manifest));refs=deepcopy(entry['artifacts'])
    acceptance=dict(accepted=True,status=acc['status'],scope='COORDINATOR_RESEARCH_ACCEPTANCE_ONLY_NOT_SOURCE_EQUIVALENCE_OR_SITE',
        accepted_at_utc=acc['accepted_at_utc'],receipt=refs['coordinator_acceptance'],
        public_scope_review=refs['public_scope_review'],receipt_evidence_review=refs['receipt_evidence_review'],
        C0_sha256_reference_only=acc['C0_sha256'],root_release_sha256_reference_only=acc['root_release_sha256'],
        private_C0_or_full_archive_read=False,root_full_archive_materialized_or_historical_replayed=False,
        later432entry_addendum_in_receipt_scope=False,strict_reproductions=0,trusted=False,OOS=False,PIT='UNKNOWN')
    ref=dict(origin_run_id=RUN,variant_id=VARIANT,manifest_sha256=manifest_sha,manifest_kind=KIND,
        protocol_sha256=digest(blobs['operational_rules']),protocol_kind=RULE_KIND,fidelity_class='ADAPTED',
        research_fidelity=FIDELITY,execution_class=EXECUTION)
    acceptance_note='原公开audit与指标pending字段保留发布时状态；固定公开回执已补充协调研究验收。这不表示严格复现、交易可信、原生实体绑定或Site部署。'
    control_note='M1266自身控制：2022-12-31信号收盘按q=0.9×100000/close冻结数量，2023-01-01开盘执行8bps费+2bps滑点；不是每次90%再平衡，也不是M1258满仓含费控制。'
    limits=deepcopy(d['limitations'])
    # Retain the exact original limitations separately; annotate the outdated
    # pending claim as a historical publication fact rather than erasing it.
    limits=[('原发布时限制（由当前协调验收回执补充）：'+x if '协调者验收和公开范围审查仍待完成' in x else x) for x in limits]
    limits += [acceptance_note,control_note,'原benchmark_curve保留25点，但当前UI不绘制该附加曲线；数值基准按full展示。']
    r=deepcopy(original)
    r.update(original_related_results=deepcopy(original['related_results']),original_publication_audit=deepcopy(original['audit']),
        coordinator_acceptance=acceptance,status='tested_proxy_only',reason=acc['quality']['interpretation'],
        tested_variants=1,families=[d['family']],related_results=[ref],implementations=[dict(ref,family=d['family'])],
        configuration_runs=4,new_control_runs=1,strategy_configurations=4,control_configurations=1,reused_control_configurations=0,
        rules={k:deepcopy(rules[k]) for k in RULE_KEYS},source_artifacts=refs,limitations=limits,
        economic_basis=dict(hypothesis='Corrected-source triple-EMA pullback and held-close peak exit; no causal economic attribution established.',
                            paper=None,paper_status='MISSING_NOT_INFERRED',selection_warning=rules['source']['author_selection_warning']),
        benchmark_reference=dict(id=ID,name=rules['benchmark']['name'],kind='OWN_ORIGINAL_FIXED_SIGNAL_QUANTITY_CONTROL',
            configuration=deepcopy(rules['benchmark']),result=deepcopy(d['metrics']['same_instrument_benchmark']['full']),
            original_controls=1,reused_control_configurations=0,matched_cost_or_delay_controls_available=False),
        public_display_manifest=manifest)
    for obj in [r,d]:
        obj.update(fidelity_class='ADAPTED',research_fidelity=FIDELITY,execution_class=EXECUTION,
                   projection_profile=PROFILE,source_contract=CONTRACT,manifest_kind=KIND,
                   source_inventory_kind=LOCK_KIND,projection_status='STAGED_NOT_IMPORTED',definition_revision_bound=False)
    d.update(original_publication_audit=deepcopy(d['audit']),coordinator_acceptance=deepcopy(acceptance),
        original_limitations=deepcopy(v['original_detail']['limitations']),limitations=limits,public_display_manifest=deepcopy(manifest),
        lab_counts=dict(strategy_ids=1,strategy_configurations=4,new_control_configurations=1,reused_control_configurations=0,strict_reproductions=0),
        projection_activity=dict(new_strategy_trials=0,new_controls=0))
    d['lineage']=dict(original_lab_lineage=deepcopy(d['lineage']),source_artifacts=refs,lab_commit=PIN,
        manifest_kind=KIND,manifest_sha256=manifest_sha,source_display_manifest_sha256=manifest_sha,
        source_contract=CONTRACT,projection_profile=PROFILE,source_inventory_kind=LOCK_KIND,
        protocol_sha256=digest(blobs['operational_rules']),protocol_kind=RULE_KIND,
        C0_sha256_reference_only=C0_SHA,coordinator_acceptance_sha256=digest(blobs['coordinator_acceptance']),definition_revision_bound=False)
    d['spec']['rule_excerpt']='自撰操作规则摘要：'+d['spec']['rule_summary']
    d['spec']['params']=deepcopy(r['rules']);d['spec']['economic_basis']=deepcopy(r['economic_basis'])
    d['spec']['assumptions']=[acceptance_note,'ADAPTED_SOURCE_CORRECTED_VARIANT / HYPOTHESIS_EXECUTION_PROXY；非严格复现。',
        'EMA20/50/100，100根完整日线预热；2023–2024共731评价日，旧曝光窗口非OOS。',
        rules['entry']['when'],rules['entry']['quantity'],rules['entry']['frozen'],rules['execution']['pending'],
        rules['execution']['rejection'],rules['exit']['predicate'],rules['exit']['high'],rules['exit']['reset'],control_note,
        rules['benchmark']['holding'],rules['benchmark']['fee_control_limitation'],
        'base为8bps费+2bps滑点；fee0/20只改变费用，delay2为两根原生日线延迟；不择优增设研究方案。',
        '首个展示点是首评价开盘前资金锚点，不是Jan1收盘；25样本点不重算731日指标。']
    d['metrics']['risk_match_note']=control_note+' '+rules['benchmark']['fee_control_limitation']+' '+acceptance_note
    d['metrics']['additional_lag_unit']='day'
    d['curve_meta'].update(observations=731,total_observations=731,returned_points=25,sampling=d['curve_meta']['resolution'],
        equity_unit='initial_capital_multiple',drawdown_unit='fraction',denominator=100000,first_point_rebased=False,
        full_daily_curve_published=False,private_daily_nav_used=False,public_curve_available=True,
        benchmark_curve_available=True,benchmark_curve_rendered_by_current_UI=False)
    return r,d


def check_output(record,detail):
    require(record.get('id')==detail.get('id')==ID and detail.get('run_id')==RUN and detail.get('variant_id')==VARIANT,
            'Output execution identity conflict')
    entry=dict(id=ID,lab_commit=PIN,run_id=RUN,variant_id=VARIANT,fidelity_class='ADAPTED',
        source_contract=CONTRACT,projection_profile=PROFILE,manifest_kind=KIND,source_inventory_kind=LOCK_KIND,artifacts=SOURCE_LOCK)
    expected=display_manifest(entry);h=digest(encoded(expected))
    for obj in [record,detail]:
        same(obj['public_display_manifest'],expected,'Output derived manifest conflict or self-reference')
        require(obj.get('manifest_kind')==KIND and obj.get('source_contract')==CONTRACT and obj.get('projection_profile')==PROFILE,
                'Output type/contract mismatch')
    require(detail['lineage']['manifest_sha256']==detail['lineage']['source_display_manifest_sha256']==h,
            'Output manifest hash conflict')
    require(len(record['related_results'])==len(record['implementations'])==1,'Only one immutable implementation identity')
    for ref in record['related_results']+record['implementations']:
        require(ref.get('origin_run_id')==RUN and ref.get('variant_id')==VARIANT and ref.get('manifest_kind')==KIND
                and ref.get('manifest_sha256')==h and ref.get('protocol_kind')==RULE_KIND
                and ref.get('protocol_sha256')==SOURCE_LOCK['operational_rules']['sha256'],'Output result binding mismatch')
