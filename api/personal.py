"""Notebook endpoints for the explicitly local personal application only."""
from collections import defaultdict
import json
import re
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from quantgraph.graph.grokbot import content_hash
from quantgraph.graph.personal_store import IDENTITY_FIELDS, PERSONAL_FIELDS, STATUSES
from quantgraph.graph.personal_restore import RestoreConflict
from quantgraph.models.factor_study import ResearchRequest


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Restore(Strict):
    backup: dict | None = None
    preview_token: str | None = None
    decisions: dict[str, str] = Field(default_factory=dict)
    mode: str | None = None


class RestorePreview(Strict):
    backup: dict


class Migration(Strict):
    migration_id: str = Field(min_length=1, max_length=200)
    items: list[dict] = Field(max_length=5000)


class Decision(Strict):
    action: str
    canonical_id: str | None = None


class Export(Strict):
    ids: list[str] = Field(default_factory=list, max_length=1000)
    format: str = 'json'
    group: str = ''


def _rule(item):
    strategy = item.get('strategy') or {}
    knowledge = item.get('knowledge') or {}
    return strategy.get('original_rule') or knowledge.get('original_rule') or strategy.get('structured_rule')


def _definition(item):
    formula = item.get('formula')
    knowledge = item.get('knowledge') or {}
    formula = formula or knowledge.get('original_formula') or item.get('original_formula')
    value = {'rule': _rule(item), 'formula': formula, 'parameters': item.get('parameters'),
             'fields': item.get('required_fields'), 'axis': item.get('axis'), 'frequency': item.get('frequency'),
             'markets': item.get('markets'), 'semantics': item.get('semantics')}
    return value if value['rule'] or value['formula'] else None


def refresh_duplicates(catalog, store):
    """Linear grouping; suggestions link each group to its first stable member.

    Content equality alone is never execution equivalence. Only same source
    identity + same source bytes + matching definition can be automatically folded.
    """
    groups = defaultdict(list)
    for item in catalog.all_items():
        if item.get('kind') not in {'strategy', 'variant', 'concept', 'source'}:
            continue
        definition = _definition(item)
        name = re.sub(r'\s+', '', item.get('name', '')).casefold()
        if name:
            groups[('name', item['kind'], name)].append(item)
        if definition:
            groups[('content', item['kind'], content_hash(definition))].append(item)
        strategy = item.get('strategy') or {}
        template = strategy.get('template_id')
        if template:
            groups[('template', item['kind'], template)].append(item)
        if item.get('source_sha256') and item.get('source_native_ids') and item.get('source_name'):
            signature = [item['source_name'], sorted(item['source_native_ids']), item['source_sha256'], definition]
            groups[('original', item['kind'], content_hash(signature))].append(item)
    encountered = set()
    new_count = 0
    # Strongest evidence wins per pair; names are used only for collision review.
    order = {'original': 0, 'content': 1, 'template': 2, 'name': 3}
    for key, group in sorted(groups.items(), key=lambda pair: (order[pair[0][0]], pair[0])):
        if len(group) < 2:
            continue
        # Prefer an already established root over a newly imported lexicographically smaller ID.
        existing_roots = {store.resolve(i['entity_id']) for i in group if store.resolve(i['entity_id']) != i['entity_id']} if key[0] == 'original' else set()
        group.sort(key=lambda i: (i['entity_id'] not in existing_roots, i['entity_id']))
        first = group[0]
        for item in group[1:]:
            pair = tuple(sorted([first['entity_id'], item['entity_id']]))
            if pair in encountered:
                continue
            encountered.add(pair)
            category = key[0]
            if category == 'original':
                classification = 'SAME_ORIGINAL_RECORD'
                evidence = '同一来源名称、原生 ID、原始字节摘要和已知定义完全一致；仅归并本机浏览身份，原始条目保留。'
            elif category == 'content':
                classification = 'SAME_CONTENT_CANDIDATE'
                evidence = '已知规则或公式、参数、数据、频率及市场字段一致；来源和完整计算语义仍需核对，不自动认定同一方法。'
            elif category == 'template':
                if content_hash(first.get('parameters')) == content_hash(item.get('parameters')) and _definition(first) == _definition(item):
                    continue
                classification = 'TEMPLATE_VARIANT'
                evidence = '已有规则解析指向同一模板；保留参数、资产和实现差异，只作变体分组建议。'
            else:
                if first['definition_revision'] == item['definition_revision']:
                    continue
                classification = 'NAME_COLLISION'
                evidence = '名称相同但定义版本不同；名称不构成等价证据，可能是不同定义或实现。'
            store.suggest(first, item, classification, evidence, exact=category == 'original')
            new_count += 1
    return {'examined_pairs': new_count, **store.duplicates()}


def export_notebook(catalog, store, *, ids=None, group=''):
    saved = {item['entity_id']: item for item in store.list(group=group)['items']}
    selected = list(dict.fromkeys(ids)) if ids else list(saved)
    items = []
    requests = defaultdict(list)
    for eid in selected:
        try:
            row = catalog.get(eid)
            value = catalog.detail(row['kind'], eid)
            personal = store.get(row)
            availability = 'AVAILABLE'
            current_item = value
            if value.get('current_entity_id') and value['current_entity_id'] != value['entity_id']:
                current_item = catalog.get(value['current_entity_id'])
                availability = 'PINNED_HISTORICAL_DEFINITION'
            current_revision = current_item['definition_revision']
            current_ref = {key: current_item[key] for key in ['entity_type', 'entity_id', 'definition_revision']}
            current_definition = None
            if personal['definition_revision'] != value['definition_revision'] or personal['entity_id'] != value['entity_id']:
                try:
                    value = catalog.detail_version(personal['kind'], personal['entity_id'], personal['definition_revision'])
                    availability = 'PINNED_HISTORICAL_DEFINITION'
                except (AttributeError, KeyError):
                    current_definition = catalog.detail(current_item['kind'], current_item['entity_id'])
                    value = {key: personal[key] for key in IDENTITY_FIELDS}
                    availability = 'PINNED_DEFINITION_UNAVAILABLE'
        except KeyError:
            if eid not in saved:
                raise
            personal = saved[eid]
            value = dict(personal)
            availability = 'SOURCE_NO_LONGER_IN_CURRENT_CATALOG'
            current_revision = None
            current_ref = None
            current_definition = None
        knowledge = value.get('knowledge') or {}
        strategy = value.get('strategy') or {}
        record = {key: personal[key] for key in IDENTITY_FIELDS}
        record.update({key: personal[key] for key in PERSONAL_FIELDS})
        record.update(stable_id=personal['stable_id'], canonical_id=store.resolve(eid), availability=availability,
            current_definition_revision=current_revision,
            original_note_ref={key: personal[key] for key in ['entity_type', 'entity_id', 'definition_revision']},
            current_definition_ref=current_ref, current_definition_snapshot=current_definition,
            version_changed=(current_revision is not None and personal['definition_revision'] != current_revision) or (current_ref is not None and personal['entity_id'] != current_ref['entity_id']),
            sources={key: value.get(key) for key in ['source_name', 'source_url', 'source_revision', 'source_sha256', 'source_native_ids', 'source_locator', 'license', 'rights']},
            rule=_rule(value), formula=value.get('formula') or knowledge.get('original_formula'),
            original_formula=value.get('original_formula') or knowledge.get('original_formula'),
            parameters=value.get('parameters', {}), required_fields=value.get('required_fields', []),
            calculation_semantics=value.get('semantics') or knowledge.get('calculation_semantics'),
            known_issues=strategy.get('unknowns', []) or knowledge.get('unknowns', []),
            related_methods=value.get('relations', []), research_references=value.get('results', {}).get('items', []),
            knowledge=knowledge, linked_notes=personal.get('linked_notes', []))
        items.append(record)
        if availability in {'AVAILABLE', 'PINNED_HISTORICAL_DEFINITION'} and record['entity_type'] in {'FactorDefinition', 'FactorVariant', 'StrategyVariant'}:
            study_type = 'STRATEGY_REPLICATION' if record['entity_type'] == 'StrategyVariant' else 'FACTOR_DIAGNOSTIC'
            requests[study_type].append(record)
    drafts = []
    for study_type, records in requests.items():
        drafts.append(ResearchRequest(request_id='personal-' + uuid4().hex,
            entity_refs=[{key: r[key] for key in ['entity_type', 'entity_id', 'definition_revision']} for r in records],
            study_type=study_type, requested_settings={'personal_research_brief': records,
                'notice': '用户选题资料；未调度研究，版本和权限需由研究流程独立核对。'}).model_dump(mode='json'))
    return dict(schema_version='quantgraph-list/v1', mode='PRIVATE', items=items, research_requests=drafts,
                export_contract='quantgraph-personal-brief/v1', notice='个人参考资料；不构成商用、公开分发或执行授权。')


def markdown_export(value):
    lines = ['# 我的研究清单', '', '用户自己的判断和研究问题；尚未调度研究。', '']
    for item in value['items']:
        availability = item['availability']
        if availability in {'PINNED_DEFINITION_UNAVAILABLE', 'SOURCE_NO_LONGER_IN_CURRENT_CATALOG'}:
            availability += '\n\n固定定义缺失，仅保留原引用，未生成对应研究请求；未用新规则代替旧定义。'
        lines.extend(['## ' + item['name'], '', f"- 条目：`{item['entity_id']}`", f"- 定义版本：`{item['definition_revision']}`",
            f"- 状态：{item['status']}；分组：{item['group'] or '未分组'}", f"- 来源：{item['sources'].get('source_name') or '来源未说明'}",
            f"- 来源定位：{item['sources'].get('source_url') or item['sources'].get('source_locator') or '来源未说明'}", '',
            '### 版本核对', '', ('笔记固定的旧版本与当前版本不同；未确认前不会把新规则当成旧版本导出。' if item['version_changed'] else '笔记与当前定义版本一致。'), '',
            f"- 资料状态：{availability}", '', '### 我的判断', '', item['note'] or '未填写', '', '### 我的整理', '', item['summary'] or '未填写', '',
            '### 研究理由与问题', '', item['reason'] or '未填写研究理由', '', item['questions'] or '未填写问题', '',
            '### 规则或公式', '', _markdown_value(item['rule'] or item['formula'] or '来源未说明'), '',
            '### 参数', '', _markdown_value(item['parameters']), '', '### 所需数据与计算语义', '',
            _markdown_value(item['required_fields']), '', _markdown_value(item['calculation_semantics']), '',
            '### 已知疑点', '', item['problem'] or '未添加个人问题标记', '', _markdown_value(item['known_issues']), '',
            '### 相关方法', '', _markdown_value(item['related_methods']), '', '### 已有研究引用', '',
            _markdown_value(item['research_references']), '', '### 来源与版本', '', _markdown_value(item['sources']), ''])
        if item['current_definition_snapshot']:
            lines += ['### 当前版本（独立参考，不属于上述旧版本）', '', _markdown_value(item['current_definition_ref']), '', _markdown_value(item['current_definition_snapshot']), '']
        if item['linked_notes']:
            lines += ['### 合并条目的原笔记（保留原 ID）', '', _markdown_value(item['linked_notes']), '']
    return '\n'.join(lines)


def _markdown_value(value):
    if not value:
        return '来源未说明或尚未收录'
    if isinstance(value, str):
        return value
    # Four-space blocks cannot be escaped by an embedded closing fence.
    return '\n'.join('    ' + line for line in json.dumps(value, ensure_ascii=False, indent=2).splitlines())


def install_personal(app, catalog, store):
    """Caller must install loopback/same-origin and body-size security boundaries."""
    app.state.personal_store = store
    router = APIRouter(prefix='/v1/personal')

    def entity(kind, eid):
        try:
            value = catalog.get(eid)
            if value['kind'] != kind:
                raise KeyError(eid)
            return value
        except KeyError:
            raise HTTPException(404, '当前本机资料中没有此条目')

    def perform(fn):
        try:
            return fn()
        except KeyError:
            raise HTTPException(404, '条目或重复建议不存在')
        except (ValueError, TypeError, IndexError):
            raise HTTPException(422, '数据校验失败；原个人资料未被替换，请核对字段、定义版本或备份完整性')

    @router.get('/items')
    def items(group: str = '', status: str = '', starred: bool | None = None):
        if status and status not in STATUSES:
            raise HTTPException(422, '阅读状态不正确')
        return store.list(group=group, status=status, starred=starred)

    @router.get('/items/{kind}/{eid}')
    def read(kind: str, eid: str):
        return store.get(entity(kind, eid))

    @router.put('/items/{kind}/{eid}')
    def update(kind: str, eid: str, body: dict):
        unknown = set(body) - PERSONAL_FIELDS - IDENTITY_FIELDS
        if unknown:
            raise HTTPException(422, '不支持的个人字段')
        item = entity(kind, eid)
        if any(key in body and body[key] != item[key] for key in ['kind', 'entity_id', 'entity_type']):
            raise HTTPException(422, '个人记录身份不匹配')
        return perform(lambda: store.update(item, {k: v for k, v in body.items() if k in PERSONAL_FIELDS},
                                            definition_revision=body.get('definition_revision')))

    @router.get('/backup')
    def backup():
        return store.backup()

    @router.post('/restore/preview')
    def restore_preview(body: RestorePreview):
        return perform(lambda: store.preview_restore(body.backup))

    @router.get('/restore/reports/{preview_token}')
    def restore_report(preview_token: str):
        return perform(lambda: store.restore_report(preview_token))

    @router.get('/restore/backups/{backup_id}')
    def restore_backup(backup_id: str):
        return JSONResponse(perform(lambda: store.restore_backup(backup_id)), headers={
            'Content-Disposition': f'attachment; filename="quantgraph-before-restore-{backup_id}.json"'})

    @router.post('/restore')
    def restore(body: Restore):
        try:
            return store.restore(body.backup, preview_token=body.preview_token, decisions=body.decisions, mode=body.mode)
        except RestoreConflict as exc:
            raise HTTPException(409, detail={'code': exc.code, 'message': str(exc)})
        except KeyError:
            raise HTTPException(404, '恢复预览不存在，请重新上传备份')
        except (ValueError, TypeError):
            raise HTTPException(422, '恢复内容校验失败；个人记录未改变，请查看预览报告')

    @router.post('/migrate')
    def migrate(body: Migration):
        def run():
            values = []
            for value in body.items:
                try:
                    item = catalog.get(value['entity_id'])
                    value = value | {'stable_knowledge_id': item.get('stable_knowledge_id') or value['entity_id']}
                except KeyError:
                    pass
                values.append(value)
            return store.migrate(body.migration_id, values)
        return perform(run)

    @router.get('/duplicates')
    def duplicates(entity_id: str = '', status: str = ''):
        return store.duplicates(entity_id, status)

    @router.post('/duplicates/refresh')
    def refresh():
        return perform(lambda: refresh_duplicates(catalog, store))

    @router.post('/duplicates/{sid}/decision')
    def decision(sid: str, body: Decision):
        return perform(lambda: store.decide(sid, body.action, canonical_id=body.canonical_id))

    def export_result(format, group, ids=None):
        if format not in {'json', 'markdown'}:
            raise HTTPException(422, '请选择 JSON 或 Markdown')
        value = perform(lambda: export_notebook(catalog, store, ids=ids, group=group))
        if format == 'markdown':
            return PlainTextResponse(markdown_export(value), media_type='text/markdown; charset=utf-8',
                                     headers={'Content-Disposition': 'attachment; filename="quantgraph-research-list.md"'})
        return value

    @router.get('/export')
    def export(format: str = 'json', group: str = ''):
        return export_result(format, group)

    @router.post('/export')
    def export_selected(body: Export):
        return export_result(body.format, body.group, body.ids)

    app.include_router(router)
