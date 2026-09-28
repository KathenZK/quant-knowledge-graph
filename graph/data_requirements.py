"""Deterministic field dependency analysis; unknown nodes fail closed."""
from quantgraph.models.market import canonical_sha256


def derive(ast, execution, *, calendar):
    fields=set(); symbols=set(); aux=set(); unknown=[]
    close_indicators={'SMA','EMA','WMA','DEMA','TEMA','RSI','ZScore','BBW','%B','ROC','MOM','MACD','RealizedVolatility'}
    hlc_indicators={'ATR','ADX','+DI','-DI','CCI','Stochastic','WilliamsR','MassIndex'}
    def visit(node):
        if isinstance(node,list):
            for value in node:visit(value)
        elif isinstance(node,dict):
            for k in ('asset','risk_asset','safe_asset'):
                if node.get(k):symbols.add(node[k])
            symbols.update(x for x in node.get('assets',[]) if x)
            kind=node.get('type')
            if kind=='long_only_signal':
                if node.get('signal') not in {'PRICE_SMA','ZSCORE_REVERSION','EMA_CROSSOVER'}:unknown.append('signal')
                fields.add('close')
                if node.get('signal')=='EMA_CROSSOVER':fields.add('volume')
                if node.get('stop_loss_fraction') is not None or node.get('take_profit_fraction') is not None:
                    fields.update({'open','high','low'})
            elif kind in {'price','rolling_extreme'}:
                if node.get('field') not in {'open','high','low','close','volume'}:unknown.append('field')
                else:fields.add(node['field'])
            elif kind=='indicator':
                name=node.get('name')
                if name in close_indicators:
                    if not node.get('input'):fields.add('close')
                elif name in hlc_indicators:fields.update({'high','low','close'})
                elif name in {'OBV','MFI','VWAP'}:
                    fields.update({'close','volume'})
                    if name=='MFI':fields.update({'high','low'})
                    if name=='VWAP':fields.add('vwap')
                else:unknown.append('indicator:'+str(name))
            elif kind=='fundamental':
                if not node.get('field') or not node.get('availability_lag'):unknown.append('fundamental availability')
                else:
                    fields.add(node['field']);aux.update({'point_in_time_fundamentals','availability_timestamp',str(node['availability_lag'])})
            elif kind and kind not in {'number','arithmetic','lag','conditional_allocation','threshold_rotation','cross','comparison','and'}:
                unknown.append('node:'+kind)
            for value in node.values():
                if isinstance(value,(list,dict)):visit(value)
    visit(ast)
    def fact(key):
        value=execution.get(key,{})
        return value.get('value') if isinstance(value,dict) else value
    price=fact('execution_price')
    # Accept reviewed normalized price tokens, never guess from prose.
    if price=='OPEN':fields.add('open')
    elif price=='CLOSE':fields.add('close')
    else:unknown.append('execution_price')
    frequency={'daily_eod':'1d','4h_close':'4h'}.get(ast.get('schedule'))
    adjustment=fact('price_adjustment')
    if not fields or not symbols or unknown or not frequency or not adjustment or not calendar:
        raise ValueError('Unresolved data dependencies: '+','.join(unknown or ['asset/frequency/adjustment/calendar']))
    return dict(derivation_version='ast-execution-v4',required_fields=sorted(fields),symbols=sorted(symbols),
        frequency=frequency,adjustment=adjustment,timezone='UTC',calendar=calendar,auxiliary_data=sorted(aux),
        derivation_sha256=canonical_sha256({'ast':ast,'execution':execution,'calendar':calendar}),dataset_profile='LAB_OHLCV_V1')
