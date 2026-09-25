import ast, copy, re, pathlib
import pandas as pd
from quantgraph.collectors.common import *
from quantgraph.normalize.formula import *

def qlib(c):
    key='qlib:qlib/contrib/data/loader.py'; tree=ast.parse(c.text(key))
    for cls in [n for n in tree.body if isinstance(n,ast.ClassDef)]:
        fn=next((x for x in cls.body if isinstance(x,ast.FunctionDef) and x.name=='get_feature_config'),None)
        if fn is None:continue
        # Reviewed, pinned, data-only generator. Entire modules and imports never run.
        for n in ast.walk(fn):
            if isinstance(n,(ast.Import,ast.ImportFrom,ast.Global,ast.Nonlocal,ast.With,ast.Try,ast.While)):raise ValueError('unsafe generator node')
            if isinstance(n,ast.Call):
                if isinstance(n.func,ast.Name) and n.func.id not in {'range','str','use'}:raise ValueError('unsafe generator call')
                if isinstance(n.func,ast.Attribute) and n.func.attr not in {'get','lower','upper'}:raise ValueError('unsafe generator method')
        f=copy.deepcopy(fn);f.decorator_list=[]
        g={'__builtins__':{'range':range,'str':str}};exec(compile(ast.fix_missing_locations(ast.Module(body=[f],type_ignores=[])),'<qlib-config>','exec'),g)
        fields,names=g[fn.name]();collection=cls.name.removesuffix('DL')
        assert len(fields)==len(names)==int(collection[5:])
        for expression,name in zip(fields,names):
            prefix=re.sub(r'\d+$','',name);family='lag_close_ratio' if prefix in {'ROC','CLOSE'} else prefix
            if collection=='Alpha158' and name in {'KMID2','KUP2','KLOW2','KSFT2'}:family=name
            window=re.search(r'(\d+)$',name)
            r=c.add('qlib',collection+':'+name,name,'qlib:'+family,source_key=key,source_name='Microsoft Qlib',collection=collection,formula=expression,raw_definition=expression,definition_kind='formula',dialect='qlib',frequency='daily',universe='configurable equity universe; no fixed market assumed',license='MIT',terms='Retain Microsoft copyright and MIT license. Market data have separate rights.',terms_url=c.url('qlib:LICENSE'),commercial_use_flag='permitted_with_attribution',source_locator=f'{cls.name}.get_feature_config; feature={name}',formula_origin='official_source_generated_configuration',quality_tier='primary_definition',high_quality_eligible=name not in {'CLOSE0','VOLUME0'},parameters={'window_or_lag':int(window[1]) if window else None,'unit':'trading_bars','generator_default_config':True},notes=['特征不指定持仓或调仓规则；完整字段调整和数据供应商语义需在回测合约中固定。'])
            if name in {'CLOSE0','VOLUME0'}:
                r['notes'].append('CLOSE0为有效非零输入下的常数；VOLUME0为带epsilon的近常数。保留原始特征，不计高质量非退化信号。');c.issue(r['record_id'],'DEGENERATE_FEATURE','Default current-close/current-volume normalization is constant or near-constant.')
            r['canonical_factor_id']=uid('factor','qlib:daily:equity:'+r['formula_hash'])
            c.implementation(r,key,fn.lineno,fn.end_lineno,'qlib-expression',implementation_status='configuration_extracted',normalized_formula=r['normalized_formula'],formula_ast=r['formula_ast'],parse_status=r['parse_status'])
