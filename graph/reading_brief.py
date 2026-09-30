"""Plain-language reading layer; never upgrades evidence or execution status."""
import re


def reading_brief(value, knowledge, method_guide, card=None):
    strategy = value.get('kind') == 'strategy'
    rows = {r['key']: r for r in knowledge.get('reading', [])}
    method = knowledge.get('method_family', {})
    source = knowledge.get('source', {})
    formula = knowledge.get('formula') or ''
    facts = []
    fields = [('scope', '交易什么'), ('entry', '什么情况下买入或开仓'),
              ('exit', '什么情况下退出或换仓'), ('position', '投入多少资金'),
              ('observation', '什么时候观察'), ('execution', '什么时候成交')]
    if not strategy:
        fields = [('definition', '计算什么'), ('universe', '适用市场'),
                  ('frequency', '计算频率'), ('direction', '数值方向')]
    for key, label in fields:
        row = rows.get(key, {})
        known = row.get('status') not in {None, 'UNKNOWN'}
        facts.append(dict(key=key, label=label,
            text=row.get('text') if known else '现有资料没有明确说明，需核对原文。',
            status=row.get('status', 'UNKNOWN'), evidence=row.get('evidence')))
    purpose = knowledge.get('summary')
    if strategy:
        def known_text(key):
            row=rows.get(key,{})
            return re.sub(r'[*`]+','',row.get('text','')).strip('；。 ') if row.get('status') not in {None,'UNKNOWN'} else ''
        entry,exit_rule=known_text('entry'),known_text('exit')
        assets=knowledge.get('asset_scope',{}).get('assets',[])
        subject='、'.join(assets) if assets else known_text('scope')
        explicit_asset=re.search(r'(?:回测标的(?:为|是)|投资标的[：:]|币安现货)([^。；\n]{1,70})',knowledge.get('original_rule') or '')
        if not assets and explicit_asset:
            subject=explicit_asset[1]
            next(f for f in facts if f['key']=='scope').update(text=subject,status='EXTRACTED',evidence=source.get('url'))
        actions=list(dict.fromkeys(x for x in [entry,exit_rule] if x))
        if actions:
            purpose=(f'针对{subject}，' if subject else '')+'；'.join(actions)+'。'
            if len(purpose)>360:
                purpose=purpose[:360]+'…完整条件见下一节。'
        else:
            purpose='已有资料尚不足以概括明确的交易动作。下方保留原文和待补条件。'
    interpretation = None
    # Exact formula structures, never a name-only economic claim.
    clean = re.sub(r'\s+', '', formula)
    patterns = [
        (r'Ref\(\$close,(\d+)\)/\$close', '比较过去价格和现在价格；价格上涨时这个比值下降。可作为趋势或反转模型输入，收益方向需要另行检验。'),
        (r'Mean\(\$close,(\d+)\)/\$close', '衡量现价相对近期均价的位置。小于 1 表示现价高于均价；持续上涨或回到均值都只是待检验假设。'),
        (r'Std\(\$close,(\d+)\)/\$close', '衡量价格水平的相对离散程度，不是收益率波动率。适合描述价格形态或风险状态，不能直接推出买卖方向。'),
        (r'Slope\(\$close,(\d+)\)/\$close', '衡量价格随时间变化的趋势斜率，不是股票对市场的 CAPM beta。可作趋势特征，不能据此直接计算市场风险敞口。'),
    ]
    if knowledge.get('dialect') == 'qlib':
        for pattern, text in patterns:
            match = re.fullmatch(pattern, clean)
            if match:
                interpretation = text + f' 当前窗口或滞后为 {match[1]} 个交易观测，不是持仓期。'
                break
    if interpretation:
        purpose = interpretation
    evidence=[]
    for paper in value.get('papers', []):
        status=paper.get('metadata_status') or 'UNVERIFIED_CITATION'
        collection=status=='COLLECTION_REFERENCE'
        evidence.append(dict(paper_id=paper.get('paper_id'),title=paper.get('title') or '论文题目未记录',
            url=paper.get('url'),year=paper.get('year'),authors=paper.get('authors',[]),
            relationship='平台或集合引用' if collection else '论文书目关联',
            status=status,locator=paper.get('source_locator') or paper.get('locator'),
            claim='说明工具或资料集合的出处，不证明这个具体因子有超额收益。' if collection else '书目关系已保留；具体支持哪条定义或实证结论，需要核对原文位置。'))
    rationale = value.get('economic_logic')
    result = dict(version='reader-brief/v1',purpose=purpose or '现有资料不足以说明用途。',
        purpose_basis='按公式结构整理，不是论文收益结论' if interpretation else ('按已有规则概括，尚未逐条核验原作者归属；不是盈利证明' if strategy else '按原始公式整理'),
        trading=facts,source_url=source.get('url') or value.get('source_url'),
        economic_rationale=dict(text=rationale or '现有资料未收录可核对的盈利机制说明，暂不能回答为什么应当赚钱。',
            status='SOURCE_REPORTED_UNVERIFIED' if rationale else 'UNKNOWN',
            notice='价格、指标和买卖条件描述的是操作；收益是否来自风险补偿、行为偏差或样本偶然性，需要独立证据。'),
        papers=evidence,empirical_status='NOT_ESTABLISHED_BY_CITATION',
        empirical_notice='有论文或代码链接，不等于该版本已获实证支持。原文报告与本地验证分别列示。')
    if isinstance(card,dict):
        result['intake_status']=card.get('admission_status') or card.get('validation',{}).get('definition_status') or 'PENDING_REVIEW'
        result['blocked_reasons']=card.get('blocked_reasons',[])
        result['validation']=card.get('validation',{})
        result['novelty']=card.get('novelty',{})
        result['entry_type']=card.get('entity_type') or ('strategy' if strategy else 'factor')
        relation=card.get('relation') or {}
        result['existing_record_overlay']=relation.get('type')=='source_curation_overlay_for' and relation.get('also_in_frozen_5813') is True
        if strategy and isinstance(card.get('field_evidence'),dict):
            evidence_fields=card['field_evidence']
            def content(value):
                if isinstance(value,str):return value
                if isinstance(value,list):return '、'.join(map(str,value))
                if isinstance(value,dict):return '；'.join(f'{k}：{content(v)}' for k,v in value.items())
                return str(value)
            for fact in result['trading']:
                key={'scope':'asset','observation':'timeframe','execution':'fill_timing'}.get(fact['key'],fact['key'])
                evidence=evidence_fields.get(key,{})
                if evidence.get('value') is not None:
                    fact.update(text=content(evidence['value']),status=evidence.get('verification_status') or 'UNVERIFIED',origin=evidence.get('origin') or 'unknown',evidence=content(evidence.get('source_evidence_refs',[])))
            result['review_notice']='补证资料挂回原记录；未改写原始规则，也未将来源核对升级为回测通过。' if result['existing_record_overlay'] else '本次采集资料保留原始准入状态；来源内容与研究假设分开判断。'
        if card.get('one_line'):
            if result['existing_record_overlay']:
                result['source_review_summary']=card['one_line']
            else:
                result['purpose']=card['one_line']
                result['purpose_basis']=card.get('usage_authority') or '根据本次采集资料整理，验证状态单独保留'
        if not strategy:
            timing=card.get('timing',{})
            result['trading']=[dict(key=k,label=label,text=text or '现有资料没有明确说明。',status='CARD_REPORTED' if text else 'UNKNOWN',origin='RESEARCH_DESIGN_SUGGESTION' if k=='use' else 'CARD_EXPLANATION',verification_status=card.get('validation',{}).get('definition_status','UNVERIFIED')) for k,label,text in [
                ('definition','怎么算',card.get('formula_plain_zh')),('direction','数值高低代表什么',card.get('sign_interpretation')),
                ('use','研究用途','；'.join(card.get('strategy_uses_zh',[]))),('data','需要什么数据','、'.join(card.get('required_data',[]))),
                ('time','数据什么时候可用',timing.get('available_at_rule'))]]
            paper=card.get('primary_paper')
            if paper:
                result['papers']=[dict(paper_id=paper.get('doi'),title=paper.get('title'),url=paper.get('url'),year=paper.get('year'),authors=paper.get('authors',[]),
                    relationship='原论文核对记录',status=card.get('validation',{}).get('definition_status','PENDING_REVIEW'),
                    locator='；'.join(paper.get('verified_locations',[])),claim='；'.join(paper.get('supports',[])),
                    version_read=paper.get('version_read'),does_not_support=paper.get('does_not_support',[]))]
            example=card.get('worked_example',{})
            if example and example.get('synthetic') is True:
                result['worked_example']=dict(text=str(example.get('calculation',''))+'。'+str(example.get('interpretation','')),basis='教学假设数据，不是回测')
        rationale=card.get('economic_rationale')
        if isinstance(rationale,str) and rationale:
            result['economic_rationale']['text']=rationale
            result['economic_rationale']['status']='SOURCE_REVIEW_REPORTED'
        elif isinstance(rationale,dict) and isinstance(rationale.get('summary_zh'),str):
            result['economic_rationale'].update(text=rationale['summary_zh'],status=rationale.get('evidence_type','UNVERIFIED'),
                causal_status=rationale.get('causal_status'),source_url=rationale.get('source_url'),source_locator=rationale.get('source_locator'))
        if isinstance(card.get('empirical_scope'),dict):
            result['empirical_scope']=card['empirical_scope']
    return result
