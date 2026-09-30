"""Versioned, reversible factor assessments; never edit archived definitions."""
import hashlib
import json
from collections import Counter
from copy import deepcopy

from quantgraph.graph.corpus_research import _read_file, _loads, _finite, _identifier, _sha

GROUPS = {
    'research_cards': '研究资料卡',
    'basic_features': '基础价量特征',
    'definition_references': '待补定义的指标引用',
    'signal_components': '策略信号组件',
    'pending': '待核资料',
    'archived': '已归档',
}
CATEGORIES = {
    'BASIC_FEATURE': 'basic_features', 'DEFINITION_REFERENCE': 'definition_references',
    'STRATEGY_RULE_REFERENCE': 'definition_references',
    'STRATEGY_SIGNAL_COMPONENT': 'signal_components',
    'SOURCE_BACKED_RESEARCH_CANDIDATE': 'research_cards',
    'OFFICIAL_DEFINITION_IMPLEMENTATION_CANDIDATE': 'research_cards',
}
REVIEW_LABELS = {
    'SOURCE_FORMULA_AND_STATIC_PARAMETERS_VERIFIED': '原式与静态参数已逐条对照固定源码；算子运行语义待核',
    'SOURCE_FORMULA_VERIFIED_METADATA_FIX_REQUIRED': '原式已对照源码；窗口元数据错误已有单独修正记录',
    'REFERENCE_REVIEWED_FULL_IMPLEMENTATION_PENDING': '指标引用和参数角色已审读；完整实现合同待补',
    'REFERENCE_VARIANT_BINDING_REQUIRED_NOT_CONFIRMED_ERROR': '同名方法存在不同规格；本条尚需绑定确切版本',
    'REFERENCE_SOURCE_BODY_PENDING': '原始来源正文尚未恢复；相关定义仅作阅读参考',
    'PREVIOUS_REVIEW_VERIFIED_CARD_INHERITED': '沿用先前逐项来源审阅；本轮复核资料卡身份与哈希',
    'FIXED_SOURCE_COMPONENT_VERIFIED_EXECUTION_CONTRACT_PENDING': '固定版本组件源码已复核；完整执行合同待补',
}
PAPER_LABELS = {
    'COLLECTION_REFERENCE_ONLY_NOT_PER_FEATURE_ALPHA_PROOF': '论文介绍 Qlib 平台/特征集合，没有逐条证明这些特征能赚钱',
    'INDICATOR_OR_METHOD_DEFINITION_NOT_FACTOR_SPECIFIC_ALPHA_PROOF': '支持指标或方法定义，不构成本参数版本的 alpha 证据',
    'INHERITED_REVIEW_WITH_EXPLICIT_IMPLEMENTATION_DIFFERENCES': '具体论文支持范围见资料卡；保留实现差异，未新做收益验证',
    'SOURCE_COMPONENT_NOT_INDEPENDENT_ALPHA_VALIDATION': '支持源码组件定义，不是独立策略或 alpha 验证',
    'RELATED_BACKGROUND_NOT_CRYPTO_VERSION_VALIDATION': '论文只支持相关机制背景，未验证这条加密市场实现',
}
BODY_LABELS = {
    'CONTENT_CAPTURED_SCOPE_AS_LABELLED':'已捕获来源内容；仅按本条注明的支持范围使用',
    'ACCESS_FAILED_UNVERIFIED_NOT_FABRICATED':'原来源访问失败，尚未核实；不据此认定内容虚构',
    'NAMED_BODY_NOT_RECOVERED_LEARNING_CENTER_REDIRECT':'原链接跳到学习中心，尚未取得指定正文',
}
DEFINITION_LABELS = {
    'PRIMARY_PUBLISHER_BASE_DEFINITION_READ':'已读发布者基础定义；本条参数与执行细节仍需绑定',
    'SECONDARY_RESEARCH_SUMMARY_BASE_RULE_ONLY':'只读到二手研究摘要的基础规则',
    'SECONDARY_SUMMARY_ONLY_ORIGINAL_PAPER_BINDING_PENDING':'仅二手摘要；原论文绑定待补',
    'PER_RECORD_STRUCTURED_CONDITION_READ_ORIGINAL_SOURCE_PENDING':'本条结构化条件已审读；原来源待补',
    'REFERENCE_RULE_STRUCTURE_READ_SOURCE_VARIANT_BINDING_REQUIRED':'规则结构已审读；具体来源版本待绑定',
    'PRIMARY_PAPER_VARIANTS_READ_CURRENT_IMPLEMENTATION_EXPLICITLY_DISTINCT':'已读原论文不同规格；当前实现的差异单列',
    'REFERENCE_PARAMETERS_ONLY_SOURCE_SPECIFICATION_PENDING':'当前只取得引用参数；完整规格待补',
    'SOURCE_BODY_NOT_RECOVERED_DO_NOT_INVENT_FORMULA':'正文尚未恢复；不补造公式',
    'PRIMARY_PAPER_PREVIOUS_REVIEW_INHERITED':'沿用此前原论文审阅，本轮未重新阅读全文',
}
KBAR_NORMALIZATIONS = {
    'KMID2':'($close-$open)/($high-$low+1e-12)',
    'KUP2':'($high-Greater($open, $close))/($high-$low+1e-12)',
    'KLOW2':'(Less($open, $close)-$low)/($high-$low+1e-12)',
    'KSFT2':'(2*$close-$high-$low)/($high-$low+1e-12)',
}


def import_assessments(catalog, path, expected_sha256):
    content = _read_file(path, limit=8*1024*1024)
    _sha(expected_sha256)
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise ValueError('Factor assessment digest mismatch')
    body = _loads(content); _finite(body)
    if not isinstance(body, dict) or not isinstance(body.get('records'), list) or len(body['records']) > 10000:
        raise ValueError('Expected bounded assessment records')
    version = body.get('audit_version'); _identifier(version)
    prepared=[]; seen=set()
    with catalog.connect() as con:
        current={r['entity_id']:r for r in con.execute('SELECT entity_id,definition_revision,kind,private_payload FROM catalog_items WHERE active=1')}
        for row in body['records']:
            if not isinstance(row, dict):
                raise ValueError('Invalid assessment row')
            eid=row.get('entity_id'); revision=row.get('definition_revision')
            _identifier(eid); _identifier(revision)
            if eid in seen:
                raise ValueError('Duplicate assessment entity')
            seen.add(eid)
            old=current.get(eid)
            if old is None or old['definition_revision'] != revision or old['kind'] not in {'variant','source'}:
                raise ValueError('Assessment must bind an existing factor definition revision')
            if row.get('archive_candidate'):
                # A recommendation alone is not an authorized destructive action.
                raise ValueError('Archival requires a separate confirmed decision')
            if row.get('category') not in CATEGORIES:
                raise ValueError('Unknown factor assessment category')
            if not isinstance(row.get('missing_facts', []), list) or not all(isinstance(x,str) for x in row.get('missing_facts', [])):
                raise ValueError('Invalid assessment missing facts')
            prepared.append((eid,revision,version,expected_sha256,json.dumps(row,sort_keys=True,ensure_ascii=False)))
    inserted=0
    with catalog.lock, catalog.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        con.execute('''CREATE TABLE IF NOT EXISTS factor_quality_assessments (
            sequence INTEGER PRIMARY KEY, entity_id TEXT NOT NULL, definition_revision TEXT NOT NULL,
            assessment_version TEXT NOT NULL, input_sha256 TEXT NOT NULL, payload TEXT NOT NULL,
            UNIQUE(entity_id,definition_revision,assessment_version))''')
        for operation in ['UPDATE','DELETE']:
            con.execute(f'''CREATE TRIGGER IF NOT EXISTS factor_assessment_no_{operation.lower()}
                BEFORE {operation} ON factor_quality_assessments BEGIN
                SELECT RAISE(ABORT, 'factor assessment history is immutable'); END''')
        for values in prepared:
            current_revision=con.execute('SELECT definition_revision FROM catalog_items WHERE entity_id=? AND active=1',(values[0],)).fetchone()
            if not current_revision or current_revision[0] != values[1]:
                raise ValueError('Definition changed during assessment import')
            old=con.execute('SELECT input_sha256,payload FROM factor_quality_assessments WHERE entity_id=? AND definition_revision=? AND assessment_version=?',values[:3]).fetchone()
            if old:
                if tuple(old) != values[3:]:
                    raise ValueError('Assessment revision is immutable')
                continue
            con.execute('INSERT INTO factor_quality_assessments(entity_id,definition_revision,assessment_version,input_sha256,payload) VALUES(?,?,?,?,?)',values)
            inserted+=1
    return {'assessment_version':version,'input_sha256':expected_sha256,'records':len(prepared),'inserted':inserted,'unchanged':len(prepared)-inserted,'archived':0,'source_definitions_modified':0}


def apply_factor_quality(value, raw):
    if value['kind'] != 'variant' and not (value['kind']=='source' and value.get('source_type')=='factor_source_record'):
        return value
    card=raw.get('intake_card') or {}
    assessment=raw.get('_factor_quality_review') or {}
    if assessment.get('category') in CATEGORIES:
        group=CATEGORIES[assessment['category']]
    elif card.get('entity_type') == 'signal_component':
        group='signal_components'
    elif card:
        group='research_cards'
    elif raw.get('source_id') == 'qlib' or value.get('source_name') == 'Microsoft Qlib':
        group='basic_features'
    else:
        group='pending'
    quality={
        'group':group, 'label':GROUPS[group],
        'assessment_version':raw.get('_factor_quality_version'),
        'assessment_sha256':raw.get('_factor_quality_sha256'),
        'source_status':assessment.get('source_formula_match_status','NOT_REVIEWED_IN_THIS_AUDIT'),
        'paper_scope':assessment.get('paper_claim_scope','按逐条论文支持范围核对'),
        'empirical_status':assessment.get('current_empirical_status','NOT_ESTABLISHED_BY_COLLECTION'),
        'scope':assessment.get('source_check_scope','资料分组；不代表已完成逐条来源或收益验证'),
        'review_status':assessment.get('review_status','PENDING_INDIVIDUAL_REVIEW'),
        'review_label':REVIEW_LABELS.get(assessment.get('review_status'),'本轮逐条核验尚未登记；已有资料卡证据范围如下'),
        'paper_scope_label':PAPER_LABELS.get(assessment.get('paper_claim_scope'),'按下方每项论文与直接来源支持范围核对'),
        'source_body_status':assessment.get('source_body_status'),
        'source_body_label':BODY_LABELS.get(assessment.get('source_body_status')),
        'base_definition_status':assessment.get('base_definition_source_status'),
        'base_definition_label':DEFINITION_LABELS.get(assessment.get('base_definition_source_status')),
        'calculation_explanation':assessment.get('calculation_explanation'),
        'numeric_meaning':assessment.get('numeric_meaning_zh'),
        'strategy_use':assessment.get('strategy_use_zh'),
        'failure_modes':assessment.get('failure_modes_zh'),
        'data_timing':assessment.get('data_PIT_assessment_zh'),
        'reference_template':{k:v for k,v in (assessment.get('reference_template') or {}).items() if k in
            {'what_zh','definition_source_url','source_locator','common_boundary_zh'}} or None,
        'source_comparisons':[{k:r.get(k) for k in ['native_id','source_url','source_lines','matches_static_source_expression']} for r in assessment.get('source_comparisons',[])],
        'missing_facts':deepcopy(assessment.get('missing_facts',[])),
        'archived':False,
        'notice':'资料层次、定义核对、算子语义和收益检验分别记录；未删除原式、笔记或研究引用。',
    }
    brief=value.get('knowledge',{}).get('reader_brief')
    if brief and assessment.get('calculation_explanation') and group=='basic_features':
        brief['purpose']=assessment['calculation_explanation']
        brief['purpose_basis']='按本条固定源码表达式整理；具体参数见原式，计算说明不等于收益验证。'
    elif brief and group=='definition_references' and (assessment.get('reference_template') or {}).get('what_zh'):
        brief['purpose']=assessment['reference_template']['what_zh']
        brief['purpose_basis']='相关指标定义的阅读说明；原引用的输入、规格与完整实现仍待逐项绑定。'
    expected=KBAR_NORMALIZATIONS.get(value.get('name'))
    if (expected and value.get('source_name')=='Microsoft Qlib'
        and value.get('source_sha256')=='814b7f7ab3d418ae3c87ce352220080b239eba2670eac9e38376b794be4075cb'
        and value.get('formula')==expected and value.get('parameters',{}).get('window_or_lag')==2):
        value['parameters']=dict(value['parameters'],window_or_lag=None)
        for p in value['knowledge']['parameters']:
            if p.get('name')=='window_or_lag':
                p['value']=None
                p['meaning']='当前bar归一化变体；名称后缀2不是窗口或滞后'
        quality['metadata_corrections']=[dict(version='qlib-current-bar-window/v1',field='parameters.window_or_lag',previous=2,current=None,
            basis='固定源码原式仅使用当前bar；当前观测需求1不表示滞后1。原式、定义版本和来源ID保持不变。',
            source_url=value.get('source_url'))]
    value['factor_quality']=quality
    return value


def quality_summary(items):
    factors=[i['factor_quality'] for i in items if i.get('factor_quality')]
    counts=Counter(i['group'] for i in factors)
    return dict(total=len(factors), groups=[dict(value=k,label=v,count=counts[k]) for k,v in GROUPS.items()],
                assessed=sum(bool(i.get('assessment_version')) for i in factors),
                source_statuses=dict(Counter(i['source_status'] for i in factors)),
                review_statuses=dict(Counter(i['review_status'] for i in factors)),
                archived=0, notice='逐ID登记不等于逐项实证验证；来源核实的具体范围见每条详情。')
