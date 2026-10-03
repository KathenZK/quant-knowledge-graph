"""Hash-pinned, resumable CSV metadata staging. No download, Git, DB or Site writes.

Every original ID retains all eleven CSV values in an independent source record.
Unknown entity types stay unreviewed; sensitive records remain private-only.
Checkpoints are immutable and tied to CSV bytes, schema, review decisions and base
metadata. Only the coordinator merges reviewed checkpoints into the repository.
"""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import json
from pathlib import Path
import re
import shutil
from jsonschema import Draft202012Validator

from quantgraph.collectors.grokbot.collector import csv_rows
from quantgraph.graph.corpus_research import _loads, _read_file, _sha
from quantgraph.graph.metadata_pilot import encoded, digest, read_below, validate, publication_screen, RESERVE
from quantgraph.graph.personal_catalog import personal_url
from quantgraph.normalize.strategy.parser import parse_rule

HEADERS = {'id', '名称', '市场', '规则', '作者或机构', '标题', 'source_url', '页码或文件', '可回测', '别名来源', '提出日期'}
SOURCE = dict(sha256='15cc0ecbcb23261e3cd7f2fb0851815daed59951090d9ce3e759ef224ea6f415',
              bytes=6470637, rows=6973, min_id=1, max_id=7019, gaps=46)
FORMAT = 'quantgraph-csv-metadata-plan/v2'
BATCH = 'quantgraph-csv-metadata-checkpoint/v2'


def canonical_hash(value):
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode())


def load_csv(path, contract):
    """Exact bytes first; CSV row ordinals are not physical lines with quoted newlines."""
    _sha(contract['sha256'])
    raw = _read_file(path, 64 * 1024**2)
    if digest(raw) != contract['sha256'] or len(raw) != contract['bytes']:
        raise ValueError('CSV source hash or byte count differs from declared contract')
    rows = csv_rows(raw)
    if len(rows) != contract['rows'] or not rows or set(rows[0]) != HEADERS:
        raise ValueError('CSV row count or exact eleven-column contract differs')
    ids = [r['id'] for r in rows]
    if any(not re.fullmatch(r'M\d{4}', rid) for rid in ids) or len(set(ids)) != len(ids):
        raise ValueError('CSV original IDs must be unique Mdddd values; never trim or renumber')
    numbers = sorted(int(rid[1:]) for rid in ids)
    id_set = set(ids)
    gaps = [f'M{n:04d}' for n in range(numbers[0], numbers[-1] + 1) if f'M{n:04d}' not in id_set]
    if (numbers[0], numbers[-1], len(gaps)) != (contract['min_id'], contract['max_id'], contract['gaps']):
        raise ValueError('CSV stable-ID extent/gaps differ from declared contract')
    return rows, gaps


def load_decisions(path=None, expected=None):
    if bool(path) != bool(expected):
        raise ValueError('Review decision file and its hash must be paired')
    if not path:
        return {}, None
    raw = _read_file(path, 8 * 1024**2)
    _sha(expected)
    if digest(raw) != expected:
        raise ValueError('Review decision digest mismatch')
    data = _loads(raw)
    if data.get('schema_version') != 'quantgraph-csv-type-decisions/v1' or not isinstance(data.get('records'), list):
        raise ValueError('Unsupported explicit type review format')
    result = {}
    for row in data['records']:
        if (set(row) != {'record_id', 'row_sha256', 'entity_type', 'reason', 'evidence'}
                or not re.fullmatch(r'M\d{4}', row['record_id']) or row['record_id'] in result
                or row['entity_type'] not in {'strategy', 'factor'}
                or not isinstance(row['reason'], str) or not row['reason']
                or not isinstance(row['evidence'], list) or not row['evidence']
                or not all(isinstance(x, str) and x for x in row['evidence'])):
            raise ValueError('Type review needs unique original ID, row hash, explicit type, reason and evidence')
        _sha(row['row_sha256']); result[row['record_id']] = row
    return result, raw


def safe_label(value, limit=240):
    if not value:
        return None
    # Long prose and obvious credential-like labels require manual review.
    if len(value) > limit or re.search(r'(?i)(token|password|api[_-]?key|secret)\s*[:=]', value):
        return None
    return value


def analyze(row, ordinal, contract, existing, decisions):
    rid = row['id']; row_hash = canonical_hash(row)
    prior = existing.get(rid, [])
    decision = decisions.get(rid)
    if decision and decision['row_sha256'] != row_hash:
        raise ValueError('Type decision is bound to a different CSV row: ' + rid)
    if len(prior) > 1:
        raise ValueError('Existing metadata has ambiguous original ID: ' + rid)
    prior_type = prior[0]['entity_type'] if prior else None
    if decision and prior_type and prior_type != decision['entity_type']:
        raise ValueError('Type review conflicts with preserved metadata; explicit migration required: ' + rid)
    kind = decision['entity_type'] if decision else prior_type
    status = ('REVIEWED_EXPLICIT_DECISION' if decision else 'EXISTING_REVIEWED_METADATA') if kind else 'UNREVIEWED'
    reason = decision['reason'] if decision else ('Existing reviewed metadata fixes the entity type; CSV itself has no type column.' if kind else 'CSV_HAS_NO_AUTHORITATIVE_TYPE_COLUMN')
    evidence = decision['evidence'] if decision else ([prior[0]['path'] + '#sha256=' + prior[0]['sha256']] if prior else [])
    source = personal_url(row['source_url'])
    parsed = parse_rule(row['规则'])
    ast = parsed['rule_ast']
    return dict(record_id=rid, native_source_id=rid, csv_row_ordinal=ordinal, row_sha256=row_hash,
        rule_sha256=digest(row['规则'].encode()), source_url_sha256=digest(row['source_url'].encode()),
        definition_fingerprint=canonical_hash({k:row[k] for k in ['规则','市场','source_url']}),
        source_url=source, source_link_status=('UNVERIFIED_REFERENCE' if source == row['source_url'] else 'SANITIZED_UNVERIFIED_REFERENCE') if source else 'MISSING_OR_UNSAFE',
        name=safe_label(row['名称']) or ('目录记录 ' + rid),
        original_classification=None, entity_type=kind, type_status=status, classification_reason=reason,
        classification_evidence=evidence, source_column_labels=dict(backtestability=safe_label(row['可回测']), proposed_date=safe_label(row['提出日期'])),
        parser=dict(version=parsed['parser_version'], status=parsed['parse_status'], rule_type=ast.get('type') if ast else None),
        record_path=(('strategies/' if kind == 'strategy' else 'factors/') + rid + '.json') if kind else None,
        preserved_metadata=prior[0] if prior else None,
        knowledge_values_complete=True, catalog_rule_value_retained=True, new_execution_trials=0)


def source_record(row, entry, contract):
    """Preserve all eleven catalog values, including empty strings and newlines."""
    screened = publication_screen({**row, 'classification_reason': entry['classification_reason'],
        'classification_evidence': json.dumps(entry['classification_evidence'], ensure_ascii=False)})
    return dict(schema_version='quantgraph-catalog-source-record/v1', identity_namespace='grokbot',
        record_id=row['id'], native_source_id=row['id'], entity_type='source_record',
        reported_fields={k:dict(value=v,status='CATALOG_REPORTED_UNVERIFIED') for k,v in row.items()},
        classification=dict(entity_type=entry['entity_type'], type_status=entry['type_status'],
            original_classification=None, reason=entry['classification_reason'], evidence=entry['classification_evidence']),
        provenance=dict(csv_sha256=contract['sha256'], csv_row_ordinal=entry['csv_row_ordinal'],
            row_sha256=entry['row_sha256'], rule_sha256=entry['rule_sha256']), publication=screened,
        knowledge_values_complete=True, source_webpage_fulltext_fetched=False,
        new_execution_trials=0, execution_permission_granted=False)


def _index_ref(path, raw, rid, kind):
    return dict(path=path,sha256=digest(raw),bytes=len(raw),record_id=rid,
                identity_namespace='grokbot',entity_type=kind)


def _batch_counts(entries, records):
    return dict(inventory_ids=len(entries), knowledge_records=len(entries),
        metadata_records=len(records), classified_records=sum(r['entity_type'] in {'strategy','factor'} for r in records),
        source_records=sum(r['entity_type']=='source_record' for r in records),
        private_only_records=sum(r['publication']['status']=='PRIVATE_ONLY_BLOCKED' for r in entries),
        strategies=sum(r['entity_type']=='strategy' for r in records), factors=sum(r['entity_type']=='factor' for r in records),
        unresolved=sum(r['entity_type'] is None for r in entries),
        preserved_existing=sum(r['preserved_metadata'] is not None and r['publication']['status']!='PRIVATE_ONLY_BLOCKED' for r in entries))


def _immutable_write(output, files):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError('Checkpoint destination exists; use a fresh immutable directory')
    if not output.parent.is_dir() or output.parent.is_symlink():
        raise ValueError('Checkpoint parent must be an existing non-symlink directory')
    if shutil.disk_usage(output.parent).free < RESERVE + sum(len(v) for v in files.values()) * 2:
        raise ValueError('Five GiB disk reserve required')
    output.mkdir(mode=0o700)
    for name, raw in files.items():
        if name.startswith('/') or any(p in {'', '.', '..'} for p in name.split('/')):
            raise ValueError('Unsafe checkpoint member')
        p = output/name; p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with p.open('xb') as stream:
            stream.write(raw)
    # manifest.json is always written last; an interrupted directory is never complete.


def create_plan(csv_path, metadata_root, output, *, contract=None, batch_size=100, decisions_path=None, decisions_sha256=None):
    contract = dict(SOURCE if contract is None else contract)
    if type(batch_size) is not int or not 1 <= batch_size <= 250:
        raise ValueError('Use bounded batches of 1..250 original IDs')
    rows, gaps = load_csv(csv_path, contract)
    base_records = validate(metadata_root)
    base_index = _loads(read_below(metadata_root, 'index.json'))
    existing = defaultdict(list)
    for ref in base_index['records']:
        if ref['identity_namespace'] == 'grokbot' and ref['entity_type'] in {'strategy','factor'}: existing[ref['record_id']].append(ref)
    decisions, raw_decisions = load_decisions(decisions_path, decisions_sha256)
    if not decisions.keys() <= {r['id'] for r in rows}:
        raise ValueError('Type decisions include new IDs outside the pinned original CSV')
    inventory = [analyze(row, i + 1, contract, existing, decisions) for i, row in enumerate(rows)]
    groups = defaultdict(list)
    for row in inventory: groups[row['definition_fingerprint']].append(row['record_id'])
    duplicates = [dict(definition_fingerprint=k, record_ids=v, status='CANDIDATE_ONLY_IDS_RETAINED') for k,v in sorted(groups.items()) if len(v)>1]
    schema = read_below(metadata_root, 'schema.json')
    source_schema = read_below(metadata_root, 'source-record.schema.json')
    source_validator = Draft202012Validator(_loads(source_schema))
    files = {'metadata-schema.json':schema, 'metadata/schema.json':schema,
             'metadata/source-record.schema.json':source_schema,
             'base-index.json':read_below(metadata_root, 'index.json')}
    if raw_decisions: files['private-only/type-decisions.json'] = raw_decisions
    source_refs=[]
    for row, entry in zip(rows, inventory):
        record=source_record(row,entry,contract);source_validator.validate(record);raw=encoded(record)
        blocked=record['publication']['status']=='PRIVATE_ONLY_BLOCKED'
        path=('private-only/' if blocked else 'metadata/')+'source-records/'+entry['record_id']+'.json'
        files[path]=raw
        entry['knowledge_record']=dict(path=path,sha256=digest(raw),bytes=len(raw))
        entry['publication']=record['publication']
        if blocked:
            # Recovery values remain exact in the private source record. Never leak
            # fragments through inventory labels, links, summaries or type evidence.
            entry.update(name='目录记录 '+entry['record_id'],source_url=None,source_link_status='PRIVATE_ONLY_BLOCKED',
                source_column_labels=dict(backtestability=None,proposed_date=None),
                classification_reason='PRIVATE_ONLY_EVIDENCE_RETAINED_IN_SOURCE_RECORD',classification_evidence=[])
        else:
            source_refs.append(_index_ref(path.removeprefix('metadata/'),raw,entry['record_id'],'source_record'))
    files['inventory.json']=encoded(inventory)
    files['metadata/index.json']=encoded(dict(schema_version='quantgraph-metadata-index/v1',records=source_refs))
    # Preserve existing reviewed record bytes only when IDs occur in this CSV.
    for row in inventory:
        ref = row['preserved_metadata']
        if ref: files['preserved/' + ref['path']] = read_below(metadata_root, ref['path'])
    batches = [dict(batch_id=f'batch-{n//batch_size+1:04d}', row_start=n+1, row_end=min(n+batch_size,len(rows)),
                    record_ids=[r['record_id'] for r in inventory[n:n+batch_size]]) for n in range(0,len(rows),batch_size)]
    report = dict(schema_version=FORMAT, source=contract, csv_columns_have_authoritative_type=False,
        base_metadata_record_count=len(base_records), base_index_sha256=digest(files['base-index.json']),
        decisions_sha256=decisions_sha256, stable_id_gaps=gaps, batch_size=batch_size, batches=batches,
        counts=dict(input_rows=len(rows), unique_original_ids=len(inventory),
            strategies=sum(r['entity_type']=='strategy' for r in inventory), factors=sum(r['entity_type']=='factor' for r in inventory),
            unresolved=sum(r['entity_type'] is None for r in inventory), duplicate_definition_candidate_groups=len(duplicates)),
        duplicate_definition_candidates=duplicates, duplicates_merged=0, new_ids=0, new_execution_trials=0,
        catalog_rule_values_retained=True, all_knowledge_values_retained=True, original_csv_bytes_retained=False,
        private_only_record_ids=[r['record_id'] for r in inventory if r['publication']['status']=='PRIVATE_ONLY_BLOCKED'],
        public_sync_ready=False, source_record_layer_is_not_new_strategy_ids=True,
        limitations=['Every catalog value is retained exactly in per-ID source records, including private-only records. CSV byte formatting is not retained.',
            'UNREVIEWED rows are retained in inventory and must not be counted as strategies/factors-folder coverage.',
            'Reported dates/backtestability are original labels, not verified dates, execution clearance or license grants.',
            'Every field still requires publication review; private-only records must never enter public Git or Site.',
            'No publication/remote persistence is performed; coordinator must save and read back each reviewed checkpoint.'],
        files={n:dict(sha256=digest(b),bytes=len(b)) for n,b in sorted(files.items())})
    files['manifest.json'] = encoded(report)
    _immutable_write(output, files)
    return dict(plan_sha256=digest(files['manifest.json']), **{k:report[k] for k in ['schema_version','source','counts','new_ids','new_execution_trials']})


def read_checkpoint(root, pin, expected_format):
    raw = read_below(root, 'manifest.json'); _sha(pin)
    if digest(raw) != pin: raise ValueError('Checkpoint manifest digest mismatch')
    manifest = _loads(raw)
    if manifest.get('schema_version') != expected_format: raise ValueError('Checkpoint format mismatch')
    for name, ref in manifest['files'].items():
        content = read_below(root, name, 64 * 1024**2 if name == 'inventory.json' else 8 * 1024**2)
        if dict(sha256=digest(content),bytes=len(content)) != ref: raise ValueError('Checkpoint member digest mismatch')
    actual = {str(p.relative_to(root)) for p in Path(root).rglob('*') if p.is_file() or p.is_symlink()}
    if actual != set(manifest['files']) | {'manifest.json'}: raise ValueError('Checkpoint contains unlisted files')
    return manifest


def _read_knowledge(root, entry, contract, validator):
    ref=entry['knowledge_record'];raw=read_below(root,ref['path'])
    if dict(sha256=digest(raw),bytes=len(raw))!={k:ref[k] for k in ['sha256','bytes']}:
        raise ValueError('Full knowledge record digest mismatch')
    record=_loads(raw);validator.validate(record)
    values={k:v['value'] for k,v in record['reported_fields'].items()}
    if (set(values)!=HEADERS or values['id']!=entry['record_id']
            or record['record_id']!=entry['record_id'] or record['native_source_id']!=entry['record_id']
            or canonical_hash(values)!=entry['row_sha256']
            or record['provenance']!=dict(csv_sha256=contract['sha256'],csv_row_ordinal=entry['csv_row_ordinal'],
                row_sha256=entry['row_sha256'],rule_sha256=digest(values['规则'].encode()))):
        raise ValueError('Full knowledge values differ from the original CSV row identity')
    screened=publication_screen({**values,'classification_reason':record['classification']['reason'],
        'classification_evidence':json.dumps(record['classification']['evidence'],ensure_ascii=False)})
    if record['publication']!=screened or entry['publication']!=screened:
        raise ValueError('Knowledge privacy review flags differ from retained values')
    expected=('private-only/' if screened['status']=='PRIVATE_ONLY_BLOCKED' else 'metadata/')+'source-records/'+entry['record_id']+'.json'
    if ref['path']!=expected:raise ValueError('Sensitive knowledge must remain in its private-only path')
    return values,raw


def recover_rows(root, expected_sha256, *, checkpoint_format=FORMAT):
    """Recover exact eleven-column values without requiring the original CSV file."""
    manifest=read_checkpoint(root,expected_sha256,checkpoint_format)
    validator=Draft202012Validator(_loads(read_below(root,'metadata/source-record.schema.json')))
    inventory=_loads(read_below(root,'inventory.json',64*1024**2))
    return [_read_knowledge(root,entry,manifest['source'],validator)[0] for entry in inventory]


def _operand(value):
    if value['type']=='number': return str(value['value'])
    if value['type']=='price': return '收盘价'
    if value['type']=='indicator':
        return (value.get('smoothing') or '') + value['name'] + '(' + ', '.join(map(str,value.get('parameters',[]))) + ')'
    raise ValueError('Unsupported closed grammar operand')


def _plain_operand(value):
    # A compact indicator label cannot represent nested inputs or volatility
    # annualization/return-basis semantics. Leave those rules for review.
    return (value.get('type') in {'number','price','indicator'}
            and set(value) <= {'type','value','field','name','parameters','smoothing','asset'}
            and value.get('asset') is None)


def metadata_record(row, entry, contract):
    """Controlled paraphrase only for three closed grammar families, otherwise missing."""
    kind = entry['entity_type']
    keys = ['assets','universe','signal','entry','exit','position','risk','cost','execution_time','timeframe'] if kind=='strategy' else ['formula','inputs','calculation','economic_meaning','use_cases','availability']
    fields = {k:dict(text='目录信息尚未核实或不足以明确本字段。',status='MISSING',evidence=[]) for k in keys}
    def put(key,text): fields[key]=dict(text=text,status='CATALOG_REPORTED_UNVERIFIED',evidence=['catalog-row'])
    parsed=parse_rule(row['规则']); ast=parsed['rule_ast']
    supported=False
    safe_operands = bool(ast) and (ast['type'] != 'threshold_switch' or all(
        _plain_operand(ast['condition'][side]) for side in ['left','right']))
    if kind=='strategy' and ast and safe_operands and ast['type'] in {'threshold_switch','absolute_momentum','relative_momentum_rotation'}:
        supported=True
        put('timeframe',{'daily_eod':'每日收盘观察条件。','month_end':'每月末观察条件。'}[ast['schedule']])
        if ast['type']=='threshold_switch':
            left,right=ast['condition']['left'],ast['condition']['right']
            cond=_operand(left)+' '+ast['condition']['operator']+' '+_operand(right)
            risk,safe=ast['then']['asset'],ast['else']['asset']
            put('assets',f'目录规则明确涉及 {risk}、{safe}；不代表历史可交易性已核实。')
            put('signal','比较：'+cond+'。')
            put('entry',f'条件满足时以 {risk} 为目标持仓。')
            put('exit',f'条件不满足时以 {safe} 为目标持仓；具体成交时刻未给出。')
            a,b=ast['then']['allocation'],ast['else']['allocation']
            if a or b:put('position',f'条件满足时：{"满仓" if a=="full" else "比例未给"}；否则：{"满仓" if b=="full" else "比例未给"}。')
        elif ast['type']=='absolute_momentum':
            risk,safe=ast['risk_asset'],ast['safe_asset'];window=ast['lookback']['value']
            put('assets',f'目录规则涉及 {risk} 与 {safe}。')
            put('signal',f'比较两者过去 {window} 个月的目录所称总回报；回报口径还需核实。')
            put('entry',f'{risk} 同期回报严格高于 {safe} 时，目标为 {risk}。')
            put('exit',f'条件不满足时，目标切换为 {safe}。')
            if ast['allocation']=='full':put('position','条件满足时满仓；其他仓位细节仍需复查。')
        else:
            a,b=ast['assets'];window=ast['lookback']['value']
            put('assets',f'目录规则涉及 {a} 与 {b}。')
            put('signal',f'比较过去 {window} 个月的目录所称总回报；回报口径还需核实。')
            put('entry','在列明的两个标的中，持有回报较高者。')
            put('exit','排名变化时目标切换；相等情形和成交时刻未明确。')
            if ast['allocation']=='full':put('position','目标标的满仓；相等回报的处理未明确。')
    missing=[f'{k}: MISSING' for k,v in fields.items() if v['status']=='MISSING']
    missing += ['仅整理原目录陈述，尚未读取并核对来源支持；不代表严格复现或作者归属已证明。','未生成回测、净值、交易记录、成本检验或样本外结果。']
    if not supported:missing.append('原规则未由本转换器支持的三类封闭语法作无损释义；完整采集规则已保存于同ID来源记录，结构化释义待人工补证。')
    origin={k:deepcopy(entry[k]) for k in ['csv_row_ordinal','row_sha256','rule_sha256','source_url_sha256','original_classification','type_status','classification_reason','classification_evidence','source_column_labels','parser']}
    origin['csv_sha256']=contract['sha256']; origin['rule_content_copied']=False
    return dict(schema_version='quantgraph-knowledge-metadata/v1', identity_namespace='grokbot', record_id=row['id'],native_source_id=row['id'],entity_type=kind,
        name=entry['name'],one_line=('目录条件释义：'+fields['entry']['text'] if supported else '目录元数据已登记；规则字段待人工核实补齐。'), relations=[],
        sources=[dict(id='catalog-source-link',url=entry['source_url'],revision=None,sha256=None,
            locator=f"CSV record ordinal {entry['csv_row_ordinal']}; complete collected rule retained in the same-ID source record",
            supports=['仅保留目录所列来源链接；未读取来源，不能证明其支持此规则。'],license='UNKNOWN_REVIEW_REQUIRED',
            attribution='原目录的作者归属尚未核实。', verification='NOT_FETCHED_REFERENCE_ONLY' if entry['source_url'] else 'MISSING_SOURCE_LINK')],
        **{('strategy_fields' if kind=='strategy' else 'factor_fields'):fields},
        economic_basis=dict(hypothesis='尚未核实理论、论文或经济机制，不能从规则推断收益来源。',status='MISSING',paper_support=[],missing=['论文支持和经济假设待核实。']),
        missing_information=missing, lab=None, catalog_origin=origin,
        rights=dict(metadata='仅目录来源链接、审阅分类和受限语法的自撰事实释义；完整采集规则在同ID来源层保存；没有采集来源网页全文。',derived_results='没有生成研究结果；来源许可待逐项审阅。',terms_url=entry['source_url'] or 'UNKNOWN_REVIEW_REQUIRED',raw_data_included=False,source_fulltext_included=False))


def stage_batch(plan_root, plan_sha256, csv_path, batch_id, output):
    plan=read_checkpoint(plan_root,plan_sha256,FORMAT)
    rows=load_csv(csv_path,plan['source'])[0] if csv_path else None
    batches=[b for b in plan['batches'] if b['batch_id']==batch_id]
    if len(batches)!=1:raise ValueError('Unknown planned batch; cannot expand the source scope')
    batch=batches[0];inventory=_loads(read_below(plan_root,'inventory.json',64 * 1024**2))
    selected=inventory[batch['row_start']-1:batch['row_end']]
    if [r['record_id'] for r in selected]!=batch['record_ids']:raise ValueError('Batch IDs differ from fixed inventory')
    source_schema=read_below(plan_root,'metadata/source-record.schema.json')
    validator=Draft202012Validator(_loads(source_schema))
    files={'metadata/schema.json':read_below(plan_root,'metadata-schema.json'),
           'metadata/source-record.schema.json':source_schema};refs=[]
    for entry in selected:
        row,knowledge_raw=_read_knowledge(plan_root,entry,plan['source'],validator)
        if rows is not None and rows[entry['csv_row_ordinal']-1]!=row:raise ValueError('Restored full values differ from verified CSV')
        files[entry['knowledge_record']['path']]=knowledge_raw
        if entry['publication']['status']=='PRIVATE_ONLY_BLOCKED':continue
        refs.append(_index_ref(entry['knowledge_record']['path'].removeprefix('metadata/'),knowledge_raw,entry['record_id'],'source_record'))
        if entry['entity_type'] is None:continue
        if entry['preserved_metadata']:
            raw=read_below(plan_root,'preserved/'+entry['record_path'])
        else:raw=encoded(metadata_record(row,entry,plan['source']))
        files['metadata/'+entry['record_path']]=raw
        refs.append(_index_ref(entry['record_path'],raw,entry['record_id'],entry['entity_type']))
    files['metadata/index.json']=encoded(dict(schema_version='quantgraph-metadata-index/v1',records=refs))
    files['inventory.json']=encoded(selected)
    manifest=dict(schema_version=BATCH,plan_sha256=plan_sha256,source=plan['source'],batch_id=batch_id,record_ids=batch['record_ids'],
        counts=_batch_counts(selected,refs),
        publication_status='PRIVATE_ONLY_BLOCKED' if any(r['publication']['status']=='PRIVATE_ONLY_BLOCKED' for r in selected) else 'STAGED_REQUIRES_ALL_FIELD_REVIEW_AND_REMOTE_READBACK',
        private_only_record_ids=[r['record_id'] for r in selected if r['publication']['status']=='PRIVATE_ONLY_BLOCKED'],
        knowledge_values_complete=True, public_sync_ready=False, new_ids=0,new_execution_trials=0,
        files={n:dict(sha256=digest(b),bytes=len(b)) for n,b in sorted(files.items())})
    _immutable_write(output,files)
    validate(Path(output)/'metadata')
    with (Path(output)/'manifest.json').open('xb') as stream:
        stream.write(encoded(manifest))
    return dict(checkpoint_sha256=digest(encoded(manifest)),**{k:manifest[k] for k in ['batch_id','counts','publication_status','new_ids','new_execution_trials']})


def resume_report(plan_root,plan_sha256,checkpoints):
    """Read-only progress from verified completed batches; no global progress write."""
    plan=read_checkpoint(plan_root,plan_sha256,FORMAT);expected={b['batch_id']:b for b in plan['batches']};seen={};counts=Counter()
    inventory=_loads(read_below(plan_root,'inventory.json',64 * 1024**2))
    for root,pin in checkpoints:
        m=read_checkpoint(root,pin,BATCH)
        if m['plan_sha256']!=plan_sha256 or m['source']!=plan['source']:raise ValueError('Checkpoint belongs to another source/plan')
        bid=m['batch_id']
        if bid not in expected or m['record_ids']!=expected[bid]['record_ids']:raise ValueError('Checkpoint IDs are outside planned batch')
        if bid in seen:raise ValueError('Duplicate checkpoint batch; do not count an identical rebuild twice')
        selected=inventory[expected[bid]['row_start']-1:expected[bid]['row_end']]
        if _loads(read_below(root,'inventory.json'))!=selected:raise ValueError('Checkpoint inventory differs from fixed plan')
        records=validate(Path(root)/'metadata')
        validator=Draft202012Validator(_loads(read_below(root,'metadata/source-record.schema.json')))
        for entry in selected:_read_knowledge(root,entry,plan['source'],validator)
        eligible=[r for r in selected if r['publication']['status']!='PRIVATE_ONLY_BLOCKED']
        identities={(r['record_id'],'source_record') for r in eligible}
        identities|={(r['record_id'],r['entity_type']) for r in eligible if r['entity_type']}
        if ({(r['record_id'],r['entity_type']) for r in records}
                != identities):
            raise ValueError('Checkpoint metadata identity differs from classified inventory')
        actual_counts=_batch_counts(selected,records)
        if m['counts']!=actual_counts:raise ValueError('Checkpoint counts differ from retained records')
        seen[bid]=pin;counts.update(m['counts'])
    return dict(plan_sha256=plan_sha256,completed_batches=seen,remaining_batches=[b for b in expected if b not in seen],
        completed_counts=dict(counts),source_rows=plan['source']['rows'],inventory_complete=counts['inventory_ids']==plan['source']['rows'],
        knowledge_values_complete=counts['knowledge_records']==plan['source']['rows'],
        classified_folders_complete=counts['classified_records']==plan['source']['rows'],
        public_review_candidate_coverage_complete=counts['source_records']==plan['source']['rows'],
        public_publication_complete=False,remote_persistence_verified=False,new_execution_trials=0)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    init=sub.add_parser('plan');init.add_argument('--csv',required=True,type=Path);init.add_argument('--metadata',required=True,type=Path);init.add_argument('--output',required=True,type=Path)
    init.add_argument('--batch-size',type=int,default=100);init.add_argument('--decisions',type=Path);init.add_argument('--decisions-sha256')
    # Non-default contracts are explicit files, useful for synthetic verification or separately reviewed revisions.
    init.add_argument('--contract',type=Path)
    stage=sub.add_parser('stage');stage.add_argument('--plan',required=True,type=Path);stage.add_argument('--plan-sha256',required=True);stage.add_argument('--csv',type=Path);stage.add_argument('--batch-id',required=True);stage.add_argument('--output',required=True,type=Path)
    resume=sub.add_parser('resume');resume.add_argument('--plan',required=True,type=Path);resume.add_argument('--plan-sha256',required=True)
    resume.add_argument('--checkpoint',action='append',nargs=2,metavar=('DIRECTORY','SHA256'),default=[])
    restore=sub.add_parser('restore');restore.add_argument('--checkpoint',required=True,type=Path);restore.add_argument('--sha256',required=True);restore.add_argument('--kind',choices=['plan','batch'],default='plan');restore.add_argument('--output',required=True,type=Path)
    for name in ['public-subset', 'check-public-subset', 'restore-public-subset']:
        command=sub.add_parser(name);command.add_argument('--checkpoint',required=True,type=Path);command.add_argument('--sha256',required=True)
        if name!='check-public-subset':command.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    if a.command=='plan':result=create_plan(a.csv,a.metadata,a.output,contract=_loads(_read_file(a.contract)) if a.contract else None,batch_size=a.batch_size,decisions_path=a.decisions,decisions_sha256=a.decisions_sha256)
    elif a.command=='stage':result=stage_batch(a.plan,a.plan_sha256,a.csv,a.batch_id,a.output)
    elif a.command=='resume':result=resume_report(a.plan,a.plan_sha256,a.checkpoint)
    elif a.command in {'public-subset', 'check-public-subset', 'restore-public-subset'}:
        from quantgraph.graph.metadata_public_subset import create_public_subset, check_public_subset, restore_public_subset
        if a.command=='public-subset':result=create_public_subset(a.checkpoint,a.sha256,a.output)
        elif a.command=='check-public-subset':result=check_public_subset(a.checkpoint,a.sha256)
        else:result=restore_public_subset(a.checkpoint,a.sha256,a.output)
    else:
        rows=recover_rows(a.checkpoint,a.sha256,checkpoint_format=FORMAT if a.kind=='plan' else BATCH)
        raw=b''.join((json.dumps(r,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode() for r in rows)
        result=dict(status='RESTORED_PRIVATE_ONLY',records=len(rows),all_eleven_field_values_preserved=True,
                    exact_original_csv_byte_format=False,sha256=digest(raw),bytes=len(raw),new_execution_trials=0)
        _immutable_write(a.output,{'private-only/restored-records.jsonl':raw,'restore-receipt.json':encoded(result)})
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))


if __name__=='__main__':main()
