import ast, copy, re, pathlib
import pandas as pd
from quantgraph.collectors.common import *
from quantgraph.normalize.formula import *

def formula_alphas(c, sources=None):
    for family,total,dialect in [('alpha101',101,'wq101'),('alpha191',191,'gtja191')]:
        if sources is not None and dialect not in sources:continue
        rawkey=f'alpha_examples:transformer/{family}.txt';codekey=f'ta_cn:ta_cn/alphas/{family}.py'
        tree=ast.parse(c.text(codekey));functions={int(n.name.split('_')[1]):n for n in tree.body if isinstance(n,ast.FunctionDef) and re.fullmatch(r'alpha_\d+',n.name)}
        found={}
        for line,raw in enumerate(c.text(rawkey).splitlines(),1):
            m=re.match(r'\s*(#\s*)?Alpha#?(\d+)\s*:?\s*(.*)',raw)
            if m:found[int(m[2])]=(m[3].strip(),line,bool(m[1]))
        assert set(found)==set(range(1,total+1)),(family,len(found))
        for n,(raw,line,disabled) in sorted(found.items()):
            source='wq101' if family=='alpha101' else 'gtja191'
            r=c.add(source,f'alpha{n:03}',f'{"WorldQuant" if source=="wq101" else "GTJA"} Alpha{n:03}',source_key=rawkey,source_name='WorldQuant Alpha101 (MIT community transcription)' if source=='wq101' else 'GTJA Alpha191 (MIT community transcription)',collection=family,aliases=[f'{source}:alpha_{n:03}'],formula=raw,raw_definition=raw,dialect=dialect,definition_kind='formula',quality_tier='secondary_definition',primary_source=False,high_quality_eligible=False,formula_origin='alpha_examples transcription; NOT verified official original',frequency='daily',universe='requires caller-specified cross-sectional equity universe',paper_title='101 Formulaic Alphas' if source=='wq101' else '基于短周期价量特征的多因子选股体系',paper_year=2016 if source=='wq101' else 2017,authors=['Zura Kakushadze'] if source=='wq101' else [],paper_url='https://arxiv.org/abs/1601.00991v3' if source=='wq101' else None,license='MIT (community repository); upstream formula/paper rights not cleared',terms='Repository license applies to contributed source. It does not prove WorldQuant/GTJA upstream rights. Excluded from commercial export.',terms_url=c.url('alpha_examples:LICENSE'),commercial_use_flag='upstream_rights_review_required',source_locator=f'line {line}; Alpha{n}',parameters={'alpha_number':n,'source_commented_out':disabled},notes=['原始公式指所采集版本原文，未伪称官方论文逐字核验。','时序/截面算子保留方言；小数窗口、缺失值、行业中性化规则待回测引擎明确。'])
            if disabled:c.issue(r['record_id'],'UPSTREAM_FORMULA_DISABLED','Formula is commented out in the source transformer input.')
            c.implementation(r,rawkey,line,line,'formula-expression',implementation_status='transcription_only',normalized_formula=r['normalized_formula'],formula_ast=r['formula_ast'],parse_status=r['parse_status'])
            r['code_url']=None
            fn=functions.get(n)
            if fn is None:c.issue(r['record_id'],'IMPLEMENTATION_MISSING','No function in pinned implementation.');continue
            fn_copy=copy.deepcopy(fn);expr=expression_from_function(fn_copy);exnorm=normalize(expr,dialect) if expr else None
            status='source_only_not_executed'
            if not any(isinstance(v,ast.Return) for v in ast.walk(fn)):
                status='stub';c.issue(r['record_id'],'IMPLEMENTATION_STUB','Function contains no return. Not counted as usable implementation.')
            elif expr is None:status='program_ast_only'
            impl=c.implementation(r,codekey,fn.lineno,fn.end_lineno,'python',implementation_status=status,python_ast=python_ast_json(fn),normalized_formula=exnorm['normalized_formula'] if exnorm else None,formula_ast=exnorm['ast'] if exnorm else None,parse_status=exnorm['parse_status'] if exnorm else 'program_only',notes=['Python程序AST仅证明语法可保存；未运行且未做论文语义等价验收。'])
            if raw and expr and r['parse_status']=='parsed' and exnorm and exnorm['parse_status']=='parsed' and r['normalized_formula']!=exnorm['normalized_formula']:
                c.issue(r['record_id'],'SOURCE_IMPLEMENTATION_SYNTAX_DIFFERS','Transcription and implementation differ structurally. Could be equivalent rewriting or a substantive change; review required.','formula')
            # Function signature is useful even when original expression cannot parse.
            impl['required_fields']=[arg.arg for arg in fn.args.args]
