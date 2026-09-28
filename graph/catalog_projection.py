"""Field-limited website views. Business visibility is not a license grant.

Original bytes stay in the ingestion journal. Public knowledge contains factual
metadata and parser-supported rule facts, never unrestricted source attachments.
"""
from copy import deepcopy
import re
from urllib.parse import urlsplit, urlunsplit

from quantgraph.api.web_read_model import safe_url, revision
from quantgraph.graph.grokbot import content_hash

VERSION = 'catalog-projection/v1'
FAMILIES = {
    'moving_average': '均线趋势', 'mean_reversion': '均值回归',
    'absolute_momentum': '绝对动量', 'absolute_momentum_zero': '绝对动量（零阈值）',
    'relative_momentum_rotation': '相对动量轮动', 'monthly_price_ma': '月度均线',
    'rolling_high_allocation': '滚动高点配置', 'indicator:rsi': 'RSI 强弱指标',
    'indicator:realized_volatility': '已实现波动率', 'indicator:atr': 'ATR 波幅',
}


def public_text(value):
    if value is None:
        return None
    text = str(value)
    text = re.sub(r'(?i)(?:api[_ -]?key|secret|password|token)\s*[:=]\s*[^\s,;]+', '[敏感字段已移除]', text)
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', '[个人联系信息已移除]', text)
    text = re.sub(r'(?i)\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{12,}\b', '[凭证已移除]', text)
    return text[:3000]


def public_url(value):
    value = safe_url(value)
    if not value:
        return None
    parts = urlsplit(value)
    # Citation links do not need user-supplied query credentials or fragments.
    return urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))


def empty_results():
    return dict(items=[], total=0, status='尚未研究', reason='尚无经许可可展示的研究结果。研究请求不代表研究已经运行。',
                contract='factor-study-result/v1', contract_status='CONNECTED',
                levels=['computational_test', 'exploratory', 'retrospective', 'confirmatory'])


def item(kind, eid, name, entity_type, definition_revision, **fields):
    return dict(kind=kind, entity_id=eid, entity_type=entity_type, name=(public_text(name) or '')[:500],
        definition_revision=definition_revision, aliases=[], description=None, economic_logic=None,
        category=None, category_label='待分类', family=None, family_label=None, formula=None,
        parameters={}, required_fields=[], markets=[], frequency=None, axis='未补充',
        source_name=None, source_url=None, source_revision=None, source_sha256=None, source_native_ids=[],
        statuses=dict(catalog='已收录', implementation='未验证', readiness='研究准备待补充',
                      result='尚未研究', display='PUBLIC · 知识元信息公开，附件权限另行检查'),
        result_status='unresearched', variant_count=0, implementations=[], papers=[], authors=[],
        concept=None, related=[], relations=[], related_strategies=[], source_locator=None,
        lookback=None, required_fields_status='REPORTED_NOT_VERIFIED', license='REVIEW_REQUIRED', terms_url=None,
        rights=dict(definition='可展示知识元信息与独立结构化事实；不授予全文再分发权',
                    code='代码附件未获展示授权', market_data='不包含行情授权', results='结果单独审查'),
        results=empty_results(), visibility='PUBLIC', source_type='knowledge', record_level=kind) | fields


def operand(node):
    if not isinstance(node, dict):
        return '待补充'
    if node.get('type') == 'number':
        return str(node.get('value'))
    if node.get('type') == 'price':
        return f"{node.get('asset') or '未指定资产'} 收盘价"
    if node.get('type') == 'indicator':
        return f"{node.get('asset') or ''} {node.get('name')}({', '.join(map(str,node.get('parameters', [])))})".strip()
    return str(node.get('type', '待补充'))


def rule_facts(ast):
    """Only describe facts the closed parser actually emitted; no inferred exits."""
    if not ast:
        return dict(entry=None, exit=None, position=None, rebalance=None, cash=None, execution=None,
                    costs=None, unknowns=['规则尚未完全结构化', '执行、成本与数据授权待确认'])
    then, otherwise = ast.get('then', {}), ast.get('else', {})
    condition = ast.get('condition')
    entry = (f"{operand(condition.get('left'))} {condition.get('operator')} {operand(condition.get('right'))}"
             if condition else None)
    if ast.get('type') == 'relative_momentum_rotation':
        entry = f"比较 {', '.join(ast.get('assets', []))} 的 {ast.get('lookback', {}).get('value')} 个月报告总收益，选择较高者"
    elif ast.get('type') == 'absolute_momentum':
        entry = f"{ast.get('risk_asset')} 的 {ast.get('lookback', {}).get('value')} 个月报告总收益高于 {ast.get('safe_asset')}"
    return dict(entry=entry, exit=(f"条件不满足时切换到 {otherwise.get('asset')}" if otherwise.get('asset') else None),
        position=(f"{then.get('asset')}：{then.get('allocation') or '比例待补充'}" if then else ast.get('allocation')),
        rebalance=ast.get('schedule'), cash=ast.get('cash_policy'), execution=ast.get('execution_timing'), costs=ast.get('costs'),
        unknowns=[k for k in ['execution_timing', 'price_adjustment', 'missing_data_policy', 'costs'] if ast.get(k) is None])


def edge(left, right, relation, evidence, source=None, **fields):
    return dict(relationship_id='catalog-edge:' + content_hash([left, right, relation]), from_id=left, to_id=right,
                relation=relation, evidence=public_text(evidence), source=public_url(source), source_label=public_url(source),
                confidence=1.0, status='SOURCE_REPORTED', review_status='SOURCE_REPORTED', version=VERSION,
                semantics='知识关系，不代表数学等价、实证相关性或收益归因', visibility='PUBLIC') | fields


def strategy_projection(row):
    v, raw = row['variant'], row['raw_record']
    ast = v.get('rule_ast')
    # Never treat reported source author as the creator of the collected variant.
    source_url = public_url(v.get('source_url'))
    family = next((c['canonical_name'] for c in row.get('concepts', []) if c['strategy_concept_id'] == v.get('strategy_concept_id')), None)
    facts = rule_facts(ast)
    definition = v['spec_sha256']
    vid = v['strategy_variant_id']
    name = raw.get('名称') or v['source_native_id']
    s = item('strategy', vid, name, 'StrategyVariant', definition,
        source_native_ids=[v['source_native_id']], family=family, family_label=FAMILIES.get(family, family),
        category=family, category_label=FAMILIES.get(family, family) or '待分类',
        description=(f"在{v.get('raw_market') or '待确认市场'}，{facts['entry']}。" if facts['entry'] else
                     f"收录的{FAMILIES.get(family, family) or '策略'}资料；已知市场为{v.get('raw_market') or '待补充'}，交易规则仍需核对来源。"),
        parameters={'reported': ast or {}}, required_fields=['close'] if ast else [],
        markets=v.get('market_taxonomy', {}).get('asset_class', []), market_description=public_text(v.get('raw_market')),
        frequency=ast.get('schedule') if ast else None, axis='时序规则（执行假设未验证）' if ast else '待补充',
        source_name='GrokBot 采集记录', source_type=v.get('provenance_type', 'UNKNOWN'), source_url=source_url,
        source_revision=str(v.get('ingestion_lineage', {}).get('revision', 1)), source_sha256=v.get('source_sha256'),
        source_locator=v.get('source_locator'), record_level='variant' if ast else 'source_record',
        strategy=dict(facts=facts, structured_rule=ast, original_rule=None,
            original_rule_notice='原始规则全文保存在本机来源快照；展示授权未核实，公开页提供结构化事实与来源链接。',
            source_author=public_text(raw.get('作者或机构')), variant_author=None,
            source_support=v.get('source_support'), provenance_type=v.get('provenance_type'),
            provenance_evidence=public_text(v.get('provenance_evidence')), variation_axes=v.get('variation_axes', []),
            parse_status=v.get('parse_status'), parse_reason=v.get('parse_reason'),
            family_id=v.get('strategy_concept_id'), template_id=v.get('strategy_template_id'),
            legacy_strategy_id=v['strategy_id'], research_hypotheses=[], unknowns=facts['unknowns']),
        test_record=bool(v.get('auditable_metadata', {}).get('metadata', {}).get('fixture')),
    )
    s['statuses'].update(implementation='规则已结构化 · 计算语义未验证' if ast else '规则待补充',
                         readiness='需 Lab 核对数据、权限及执行假设')
    nodes, edges = [s], []
    sid = 'catalog-source:' + content_hash([v['source_native_id'], v.get('ingestion_lineage', {}).get('revision', 1)])
    nodes.append(item('source', sid, f"{v['source_native_id']} · 来源记录", 'SourceRecord', v['source_sha256'],
                      source_url=source_url, source_native_ids=[v['source_native_id']], source_name='GrokBot',
                      description='原始输入已保留；此页只展示来源和版本，不分发受限全文。'))
    edges.append(edge(sid, vid, 'DESCRIBES', '来源记录与其规范化投影', source_url))
    for c in row.get('concepts', []):
        cid = c['strategy_concept_id']
        nodes.append(item('family', cid, FAMILIES.get(c['canonical_name'], c['canonical_name']), 'StrategyConcept', content_hash(c),
                          description='由来源与已解析方法归类；同族不代表同一策略或相同收益。', source_url=source_url))
    for t in row.get('templates', []):
        tid = t['strategy_template_id']
        nodes.append(item('template', tid, f"{FAMILIES.get(family, family) or '策略'}模板 · {tid[-8:]}", 'StrategyTemplate', content_hash(t),
                          parameters={'template': t.get('template_ast')}, description='保留规则结构，将参数与资产作为独立槽位。', source_url=source_url))
        edges.append(edge(vid, tid, 'VARIANT_OF', '明确的模板槽位；参数与资产分别保留', source_url))
        if t.get('strategy_concept_id'):
            edges.append(edge(tid, t['strategy_concept_id'], 'VARIANT_OF', '模板所属的报告方法族', source_url))
    if v.get('strategy_concept_id'):
        edges.append(edge(vid, v['strategy_concept_id'], 'IN_FAMILY', '来源/解析支持的方法归类；不是等价声明', source_url))
    for link in row.get('factor_links', []):
        fid, cid = link['factor_variant_id'], link['factor_id']
        signal = link.get('evidence') if isinstance(link.get('evidence'), dict) else {}
        fname = signal.get('name') or signal.get('type') or '规则引用信号'
        params = signal.get('parameters', [])
        fr = item('variant', fid, f"{fname}({', '.join(map(str, params))}) · 规则引用", 'FactorVariant', content_hash(signal),
                  family=fname, family_label=FAMILIES.get('indicator:' + fname.lower(), fname), aliases=[fname],
                  parameters=signal, source_name='GrokBot 规则引用', source_type='RULE_LINK_ONLY', source_url=source_url,
                  axis='待核对实现语义', description='来源规则明确使用此信号。平滑、窗口和实现细节未补充时，不与其他同名因子声明等价。',
                  required_fields=['close'], record_level='rule_reference')
        nodes.extend([fr, item('concept', cid, fname, 'FactorConcept', content_hash({'name': fname}),
                              description='规则引用中的指标概念；并非已验证的计算实现。', source_url=source_url)])
        edges.extend([edge(vid, fid, 'USES_FACTOR', '已解析规则中的显式信号引用', source_url, role=link.get('role'),
                           review_status='RULE_LINK_ONLY', attribution_status='RULE_LINK_ONLY'),
                      edge(fid, cid, 'VARIANT_OF', '保留参数的规则引用；不声明与 Qlib 等价', source_url)])
    return nodes, edges


def safe_factor(model, kind, eid, record, *, licensed=False):
    projected = model.project(kind, eid, record)
    projected = item(kind, eid, projected['name'], projected['entity_type'], projected['definition_revision']) | projected
    projected['source_url'] = public_url(projected['source_url'])
    projected['name'] = public_text(projected['name'])
    projected['aliases'] = [public_text(a) for a in projected['aliases']]
    projected['source_type'] = record.get('source_name') or 'factor_reference'
    projected['license'] = record.get('license', 'REVIEW_REQUIRED')
    projected['authors'] = [public_text(a) for a in record.get('authors', [])]
    if licensed:
        full = model.detail(kind, eid)
        for key in ['implementations', 'papers', 'authors', 'lookback', 'source_locator', 'required_fields_status', 'terms_url']:
            projected[key] = full.get(key)
        # A verified Qlib release, not an incoming producer license claim.
        projected['rights']['definition'] = '已核验 Qlib MIT 定义；保留归属和许可声明'
    else:
        for key in ['formula', 'description', 'economic_logic']:
            projected[key] = None
        projected['parameters'] = {}
        projected['description'] = '已收录来源定义。此来源的公式/正文展示权限待复核，可通过原始链接查阅。'
        projected['statuses']['display'] = 'PUBLIC · 来源元信息；公式与正文权限待复核'
    return deepcopy(projected)
