"""Exact input history for supported Qlib ASTs, never inferred from feature-name suffixes."""
from decimal import Decimal

ROLLING={'mean','std','sum','ts_rank','ts_max','ts_min','ts_argmax','ts_argmin','quantile','corr','slope','rsquare','resi'}
ELEMENTWISE={'abs','log','elementwise_max','elementwise_min'}


def lookback(ast, dialect):
    if not ast or dialect!='qlib':return None
    def span(n):
        t=n['type']
        if t=='number':return 0
        if t=='field':return 1
        args=n.get('args',[])
        if t!='call':
            lengths=[span(a) for a in args]
            return None if None in lengths else max(lengths,default=0)
        op=n['op'].split(':',1)[-1]
        if op in ELEMENTWISE:
            lengths=[span(a) for a in args]
            return None if None in lengths else max(lengths,default=0)
        if op=='delay' or op in ROLLING:
            # Qlib Quantile(x, n, q) uses its second argument for n.
            window=args[1] if op=='quantile' else args[-1]
            if window['type']!='number':return None
            number=Decimal(window['value'])
            if number!=number.to_integral_value() or number<0:return None
            if op!='delay' and number==0:return None  # expanding, not fixed history
            inputs=args[:1] if op=='quantile' else args[:-1]
            lengths=[span(a) for a in inputs]
            if None in lengths:return None
            return max(lengths,default=1)+int(number)-(0 if op=='delay' else 1)
        return None
    bars=span(ast)
    return None if bars is None else {'value':bars,'unit':'observations','scope':'minimum structural input span; includes current observation','status':'AST_DERIVED_NOT_RUNTIME_VERIFIED'}
