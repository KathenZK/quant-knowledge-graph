"""Small full-consumption expression grammar. Unspecified indicators stay unknown."""
import re


def expression(text, atom, depth=0):
    if depth > 12:
        return None
    # Strip only a balanced pair covering the complete expression.
    if text.startswith('(') and text.endswith(')'):
        level=0
        for i,c in enumerate(text):
            level += (c=='(')-(c==')')
            if level==0:
                if i==len(text)-1:return expression(text[1:-1],atom,depth+1)
                break
    # Split top-level arithmetic, preserving precedence and associativity.
    for operators in ('+-', '×*·/'):
        level=0
        for i in range(len(text)-1,-1,-1):
            c=text[i];level+=(c==')')-(c=='(')
            if level==0 and c in operators and i>0 and text[i-1] not in '+-*/×·':
                left=expression(text[:i],atom,depth+1);right=expression(text[i+1:],atom,depth+1)
                if left is not None and right is not None:
                    return {'type':'arithmetic','operator':'*' if c in '×·' else c,'left':left,'right':right}
    direct=atom(text)
    if direct is not None:return direct
    fields={'Open':'open','High':'high','Low':'low','Close':'close','开盘':'open','最高':'high','最低':'low','成交量':'volume','Volume':'volume'}
    if text in fields:return {'type':'price','field':fields[text],'asset':None}
    m=re.fullmatch(r'Prior(Open|High|Low|Close)',text)
    if m:return {'type':'lag','periods':1,'input':{'type':'price','field':m[1].lower(),'asset':None}}
    m=re.fullmatch(r'(.+?)(?:_t|_\{t\})',text)
    if m:return expression(m[1],atom,depth+1)
    m=re.fullmatch(r'(.+?)_\{t-(\d+)\}',text)
    if m and int(m[2])>0:
        inner=expression(m[1],atom,depth+1)
        if inner:return {'type':'lag','periods':int(m[2]),'input':inner}
    m=re.fullmatch(r'(?:自身)?(SMA|EMA|WMA|DEMA|TEMA)(\d+)',text)
    if m and int(m[2])>0:return {'type':'indicator','name':m[1],'parameters':[int(m[2])],'asset':None,'smoothing':None}
    m=re.fullmatch(r'(SMA|EMA|WMA)\((\d+)of(.+)\)',text)
    if m and int(m[2])>0:
        inner=expression(m[3],atom,depth+1)
        if inner:return {'type':'indicator','name':m[1],'parameters':[int(m[2])],'input':inner,'asset':None}
    m=re.fullmatch(r'(SMA|EMA|WMA)(\d+)\((.+)\)',text)
    if m and int(m[2])>0:
        inner=expression(m[3],atom,depth+1)
        if inner:return {'type':'indicator','name':m[1],'parameters':[int(m[2])],'input':inner,'asset':None}
    m=re.fullmatch(r'(Highest|Lowest)\((High|Low|Close),(\d+)\)',text)
    if m and int(m[3])>0:
        return {'type':'rolling_extreme','operation':'max' if m[1]=='Highest' else 'min','field':m[2].lower(),
                'parameters':[int(m[3])],'asset':None,'window_excludes_current':None}
    # Explicit periods only. BBW and %B include n and sigma; no inference from title.
    m=re.fullmatch(r'(DEMA|TEMA|ZScore|MassIndex|\+DI|-DI)\((\d+)\)',text)
    if m and int(m[2])>0:return {'type':'indicator','name':m[1],'parameters':[int(m[2])],'asset':None}
    m=re.fullmatch(r'(BBW|%B)\((\d+),(\d+(?:\.\d+)?)\)',text)
    if m and int(m[2])>1 and float(m[3])>0:
        return {'type':'indicator','name':m[1],'parameters':[int(m[2]),float(m[3])],'asset':None,'standard_deviation_ddof':None}
    return None


def full_condition(text, atom):
    conditions=[]
    for clause in re.split('且|∧',text):
        parts=re.split(r'(>=|<=|>|<)',clause)
        if len(parts)<3 or len(parts)%2==0:return None
        operands=[expression(v,atom) for v in parts[::2]]
        if any(v is None for v in operands):return None
        for i,operator in enumerate(parts[1::2]):
            if operands[i]['type']=='number':return None
            conditions.append({'operator':operator,'left':operands[i],'right':operands[i+1]})
    if not 1<=len(conditions)<=5:return None
    return conditions
