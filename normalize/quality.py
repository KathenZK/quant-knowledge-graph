"""Conservative structural checks. Parsing is not a backtest certification."""
import ast,collections,re
from quantgraph.normalize.formula import walk

ARITY={
 'qlib':{'abs':[1],'corr':[3],'delay':[2],'elementwise_max':[2],'elementwise_min':[2],'log':[1],'mean':[2],'quantile':[3],'resi':[2],'rsquare':[2],'slope':[2],'std':[2],'sum':[2],'ts_argmax':[2],'ts_argmin':[2],'ts_max':[2],'ts_min':[2],'ts_rank':[2]},
 'wq101':{'abs':[1],'corr':[3],'cov':[3],'cs_rank':[1],'decay_linear':[2],'delay':[2],'delta':[2],'industry_neutralize':[2],'log':[1],'max':[2],'min':[2],'product':[2],'scale':[1,2],'sign':[1],'signed_power':[2],'std':[2],'sum':[2],'ts_argmax':[2],'ts_argmin':[2],'ts_max':[2],'ts_min':[2],'ts_rank':[2]},
 'gtja191':{'abs':[1],'corr':[3],'count':[2],'coviance':[3],'cs_rank':[1],'decay_linear':[2],'delay':[2],'delta':[2],'elementwise_max':[2],'elementwise_min':[2],'filter':[2],'highday':[2],'log':[1],'lowday':[2],'ma':[2],'mean':[2],'prod':[2],'regbeta':[2,3],'sequence':[1],'sign':[1],'sma_cn':[3],'std':[2],'sum':[2],'sumac':[1],'sumif':[3],'ts_max':[2],'ts_min':[2],'ts_rank':[2],'wma':[2]}}

def assess(c):
    operators=collections.defaultdict(lambda:{'record_ids':set(),'arities':set()})
    for r in c.records:
        r['semantic_status']='not_verified'
        r['backtest_ready']=False
        if r['formula_ast']:
            for node in walk(r['formula_ast']):
                if node['type']!='call':continue
                dialect,name=node['op'].split(':',1);nargs=len(node['args']);entry=operators[node['op']];entry['record_ids'].add(r['record_id']);entry['arities'].add(nargs)
                expected=ARITY.get(dialect,{}).get(name)
                if expected is not None and nargs not in expected:
                    c.issue(r['record_id'],'OPERATOR_ARITY_REVIEW',f'{node["op"]} has {nargs} arguments; preliminary explicit-argument contract expects {expected}. Check upstream defaults/overloads; no repair applied.','formula')
                if expected is None:c.issue(r['record_id'],'OPERATOR_SIGNATURE_UNRESOLVED',node['op']+' requires explicit operator contract.','formula')
                if name=='delay' and node['args'] and node['args'][-1]['type']=='unary' and node['args'][-1]['op']=='-':
                    c.issue(r['record_id'],'FUTURE_REFERENCE','Negative lag references future data.','formula')
        if r['source_id']=='jkp' and r['raw_definition']:
            raw=r['raw_definition']
            if raw.count('{')!=raw.count('}'):
                r['high_quality_eligible']=False;c.issue(r['record_id'],'LATEX_UNBALANCED','LaTeX brace mismatch; extraction or original definition requires review.','raw_definition')
    c.operator_registry=[dict(operator=op,observed_arities=sorted(v['arities']),expected_arities=ARITY.get(op.split(':')[0],{}).get(op.split(':')[1]),record_count=len(v['record_ids']),execution_semantics='not_implemented',notes='Dialect is part of identity. Rank tie, NaN, minimum-observation, ddof, window rounding and alignment rules must be specified before executing.') for op,v in sorted(operators.items())]
