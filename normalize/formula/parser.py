"""Lossless structural normalization. Never infer mathematical equivalence.

Operators remain dialect-qualified: Qlib Rank is a time-series rank whereas
WorldQuant rank is cross-sectional. Floating lookbacks are never rounded.
"""
import ast
import hashlib
import json
import re
from decimal import Decimal
from lark import Lark, Transformer

GRAMMAR = r'''
?start: cond
?cond: logic_or "?" cond ":" cond -> conditional
     | logic_or
?logic_or: logic_or OR logic_and -> binary
         | logic_and
?logic_and: logic_and AND compare -> binary
          | compare
?compare: sum (COMP sum)+ -> compare
        | sum
?sum: sum ADD product -> binary
    | product
?product: product MUL unary -> binary
        | unary
?unary: UNARY unary -> unary
      | power
?power: atom POW unary -> binary
      | atom
?atom: NUMBER -> number
     | NAME "(" [args] ")" -> call
     | NAME -> field
     | "(" cond ")"
args: cond ("," cond)*
OR: "||" | "|"
AND: "&&" | "&"
COMP: "==" | "!=" | "<=" | ">=" | "<" | ">"
ADD: "+" | "-"
MUL: "*" | "/" | "%"
POW: "**" | "^"
UNARY: "+" | "-" | "!" | "~"
NAME: /\$?[a-zA-Z_][a-zA-Z_0-9.]*/
NUMBER: /(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?/
%import common.WS
%ignore WS
'''

ALIASES = {
 'qlib': {'ref':'delay','mean':'mean','std':'std','rank':'ts_rank','greater':'elementwise_max','less':'elementwise_min','max':'ts_max','min':'ts_min','idxmax':'ts_argmax','idxmin':'ts_argmin'},
 'wq101': {'ts_rank':'ts_rank','ts_argmax':'ts_argmax','ts_argmin':'ts_argmin','rank':'cs_rank','correlation':'corr','covariance':'cov','stddev':'std','signedpower':'signed_power','indneutralize':'industry_neutralize'},
 'gtja191': {'rank':'cs_rank','tsrank':'ts_rank','tsmax':'ts_max','tsmin':'ts_min','std':'std','corr':'corr','sma':'sma_cn','decaylinear':'decay_linear','max':'elementwise_max','min':'elementwise_min'}
}

def dumps(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(v): return hashlib.sha256(dumps(v).encode()).hexdigest()

class ToAST(Transformer):
    def __init__(self,dialect):super().__init__();self.dialect=dialect
    def number(self,x):
        val=format(Decimal(str(x[0])).normalize(),'f')
        return {'type':'number','value':val}
    def field(self,x):return {'type':'field','name':str(x[0]).lstrip('$').lower()}
    def args(self,x):return list(x)
    def call(self,x):
        name=str(x[0]).lower(); name=ALIASES.get(self.dialect,{}).get(name,name)
        return {'type':'call','op':self.dialect+':'+name,'args':x[1] if len(x)>1 and x[1] is not None else []}
    def binary(self,x):return {'type':'binary','op':{'**':'pow','^':'pow','||':'or','|':'or','&&':'and','&':'and'}.get(str(x[1]),str(x[1])),'args':[x[0],x[2]]}
    def unary(self,x):return {'type':'unary','op':str(x[0]),'args':[x[1]]}
    def compare(self,x):return {'type':'compare','ops':[str(v) for v in x[1::2]],'args':x[::2]}
    def conditional(self,x):return {'type':'if','args':list(x)}

PARSER=Lark(GRAMMAR,parser='lalr',maybe_placeholders=False)
def parse(raw,dialect):
    return ToAST(dialect).transform(PARSER.parse(raw))

def dsl(n):
    t=n['type']
    if t=='number':return n['value']
    if t=='field':return '$'+n['name']
    if t=='compare':return 'compare['+','.join(n['ops'])+']('+','.join(dsl(x) for x in n['args'])+')'
    op=n.get('op',t)
    return op+'('+','.join(dsl(x) for x in n.get('args',[]))+')'

def walk(n):
    yield n
    for v in n.get('args',[]):yield from walk(v)

def details(n):
    nodes=list(walk(n))
    return {'required_fields':sorted({x['name'] for x in nodes if x['type']=='field'}),'operators':sorted({x['op'] for x in nodes if x['type']=='call'}),'numeric_literals':sorted({x['value'] for x in nodes if x['type']=='number'},key=Decimal)}

def normalize(raw,dialect):
    try:
        n=parse(raw,dialect)
        return dict(ast=n,normalized_formula=dsl(n),formula_hash=digest({'dialect':dialect,'ast':n}),parse_status='parsed',parse_error=None,**details(n))
    except Exception as e:
        return dict(ast=None,normalized_formula=None,formula_hash=None,parse_status='parse_error',parse_error=str(e).splitlines()[0][:300],required_fields=sorted({x.lower().lstrip('$') for x in re.findall(r'\$?[A-Za-z_][A-Za-z_0-9.]*',raw) if x.lower().lstrip('$') in {'open','high','low','close','volume','vwap','returns','ret','cap','mkt','smb','hml','dtm','dbm','ld','hd','tr','banchmarkindexclose','banchmarkindexopen'}}),operators=[],numeric_literals=[])

def python_ast_json(node):
    """Serialize implementation syntax without running source code."""
    if isinstance(node,ast.AST):
        return {'node':type(node).__name__,**{k:python_ast_json(v) for k,v in ast.iter_fields(node) if k not in {'ctx','type_comment'}}}
    if isinstance(node,list):return [python_ast_json(x) for x in node]
    return node

def expression_from_function(fn):
    """Inline straight-line temporary assignments; reject complex control flow."""
    env={}
    class Substitute(ast.NodeTransformer):
        def visit_Name(self,node):return env.get(node.id,node)
    for stmt in fn.body:
        if isinstance(stmt,ast.Expr) and isinstance(stmt.value,ast.Constant):continue
        if isinstance(stmt,ast.Assign) and len(stmt.targets)==1 and isinstance(stmt.targets[0],ast.Name):
            env[stmt.targets[0].id]=Substitute().visit(stmt.value)
        elif isinstance(stmt,ast.Return) and stmt.value is not None:
            return ast.unparse(Substitute().visit(stmt.value))
        else:return None
    return None
