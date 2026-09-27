"""Additional explicit rule families; no inferred universe or indicator defaults."""
import re
from .expressions import full_condition
from .parser import SYMBOL


def parse_explicit(expr, atom, schedule):
    # Asset-qualified input is distinct from the allocated asset (e.g. SPY -> HYG).
    m=re.fullmatch(rf'(?:若)?(.+?)(?:→|则)(次月|下月)?满仓({SYMBOL})[,;]?否则(满仓)?({SYMBOL}|现金(?:/T-bill)?)',expr)
    if m:
        text,timing,risk,full,safe=m.groups()
        signal_asset=None
        a=re.match(rf'^({SYMBOL})(?:之|的)?(?=收盘|SMA|EMA|ROC)',text)
        if a:signal_asset=a[1];text=text[a.end():]
        text=text.replace('收盘高于','收盘>').replace('收盘低于','收盘<').replace('自身','').replace('其','')
        text=re.sub(r'(\d+)日简单均线',r'SMA(\1)',text)
        conditions=full_condition(text,atom)
        if conditions:
            if signal_asset:
                def bind(node):
                    if isinstance(node,dict):
                        if 'asset' in node and node['asset'] is None:node['asset']=signal_asset
                        for v in node.values():bind(v)
                    elif isinstance(node,list):
                        for v in node:bind(v)
                bind(conditions)
            cash=safe.startswith('现金')
            return {'type':'threshold_switch' if len(conditions)==1 else 'conjunctive_switch',
                **({'condition':conditions[0]} if len(conditions)==1 else {'conditions':conditions,'operator':'AND'}),
                'then':{'asset':risk,'allocation':'full'},'else':{'asset':None if cash else safe,'allocation':'full' if full or cash else None},
                'safe_asset_description':safe if cash else None,'reported_execution_period':'following_month' if timing else None}
    # Explicit total-return comparison, including cross-asset condition and cash.
    m=re.fullmatch(rf'若({SYMBOL})(?:过去|近)(\d+)(?:个)?(交易日|日|个月|月)(总分收益|总收益|收益)(>=|<=|>|<)(-?\d+(?:\.\d+)?)(?:→|则)(?:次月|下月)?满仓({SYMBOL})[,;]?否则(满仓)?({SYMBOL}|现金(?:/T-bill)?)',expr)
    if m and int(m[2])>0:
        cash=m[9].startswith('现金')
        return {'type':'return_threshold_allocation','condition':{'operator':m[5],
           'left':{'type':'indicator','name':'reported_return','asset':m[1],'parameters':[int(m[2])],
                   'sampling_unit':'months' if '月' in m[3] else 'days','return_basis':m[4]},
           'right':{'type':'number','value':float(m[6])}},
          'then':{'asset':m[7],'allocation':'full'},'else':{'asset':None if cash else m[9],'allocation':'full' if m[8] or cash else None},
          'safe_asset_description':m[9] if cash else None}
    m=re.fullmatch(rf'若({SYMBOL})(?:月收盘|收盘)>(?:自身)?(?:SMA\((\d+)个?月\)|(?:过去)?(\d+)月简单均线)(?:→|则)(?:次月|下月)?满仓\1[,;]?否则(现金(?:/T-bill)?|{SYMBOL})',expr)
    if m and schedule=='month_end' and int(m[2] or m[3])>0:
        return {'type':'monthly_price_ma','assets':[m[1],None if m[4].startswith('现金') else m[4]],
           'parameters':[int(m[2] or m[3])],'indicator':'SMA','input':'month_end_close','comparison':'>','allocation':'full',
           'safe_asset_description':m[4] if m[4].startswith('现金') else None}
    m=re.fullmatch(rf'若({SYMBOL})收盘>=(?:过去)(\d+)个?交易日最高收盘→次月满仓\1;否则现金',expr)
    if m and schedule=='month_end' and int(m[2])>0:
        return {'type':'rolling_high_allocation','assets':[m[1],None],'parameters':[int(m[2])],
           'field':'close','comparison':'>=','window_excludes_current':None,'allocation':'full',
           'safe_asset_description':'现金','reported_execution_period':'following_month'}
    return None
