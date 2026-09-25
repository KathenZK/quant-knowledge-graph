"""Collectors for frozen, attributed source files. Online retrieval lives in cli."""
import ast, copy, csv, json, re, pathlib, uuid
import pandas as pd
from quantgraph.normalize.formula import normalize, digest, python_ast_json, expression_from_function

NS=uuid.UUID('b14f8d5f-7202-5b66-a5b0-4506247f18df')
def uid(kind,key):return 'qkg:'+kind+':'+str(uuid.uuid5(NS,kind+':'+key))
def clean(v):
    if v is None or (isinstance(v,float) and pd.isna(v)):return None
    return str(v).strip() or None
def latex_text(s):
    s=s.replace('\\_','_').replace('\\&','&')
    s=re.sub(r'\\(?:hyperlink|hypertarget|href)\{[^{}]*\}\{([^{}]*)\}',r'\1',s)
    s=re.sub(r'\\[a-zA-Z]+\{([^{}]*)\}',r'\1',s)
    return re.sub(r'\s+',' ',s.replace('{','').replace('}','')).strip()

CONCEPTS={
 'price_momentum':'历史价格动量', 'time_series_momentum':'时间序列动量',
 'book_to_market':'账面市值比', 'asset_growth':'资产增长', 'accruals':'应计项目',
 'gross_profitability':'毛利润能力', 'market_beta':'市场贝塔', 'size':'规模',
 'idiosyncratic_volatility':'特质波动率','short_term_reversal':'短期反转',
 'long_term_reversal':'长期反转','quality':'质量', 'earnings_surprise':'盈余意外',
 'dividend_yield':'股息率','net_equity_issuance':'净股权发行',
 'betting_against_beta':'低贝塔对冲高贝塔', 'market_excess_return':'市场超额收益',
 'operating_profitability':'营业利润能力','investment':'投资强度',
 'hml_portfolio':'价值多空组合', 'smb_portfolio':'小盘减大盘组合',
 'momentum_portfolio':'动量多空组合', 'qmj_portfolio':'优质减劣质组合',
}
CURATED={
 'osap':{'BM':'book_to_market','AssetGrowth':'asset_growth','Accruals':'accruals','GP':'gross_profitability','Beta':'market_beta','Size':'size','IdioVol3F':'idiosyncratic_volatility','Mom12m':'price_momentum','Mom6m':'price_momentum','MomRev':'price_momentum','STreversal':'short_term_reversal','LongTermReversal':'long_term_reversal','PriceDelayRsq':'price_delay','EarningsSurprise':'earnings_surprise','DivYieldST':'dividend_yield','ShareIss1Y':'net_equity_issuance'},
 'jkp':{'be_me':'book_to_market','at_gr1':'asset_growth','oaccruals_at':'accruals','gp_at':'gross_profitability','beta_60m':'market_beta','market_equity':'size','me':'size','ivol_ff3_21d':'idiosyncratic_volatility','ret_12_1':'price_momentum','ret_6_1':'price_momentum','ret_1_0':'short_term_reversal','ret_60_12':'long_term_reversal','niq_su':'earnings_surprise','div12m_me':'dividend_yield','chcsho_12m':'net_equity_issuance','qmj':'qmj_portfolio','betabab_1260d':'market_beta'},
}

class Catalog:
    def __init__(self,root):
        self.root=pathlib.Path(root);self.lock=json.loads((self.root/'datasets/raw/source_lock.json').read_text());self.bykey={x['key']:x for x in self.lock}
        self.records=[];self.implementations=[];self.issues=[];self.source_summary=[]
    def path(self,key):return self.root/self.bykey[key]['path']
    def text(self,key):return self.path(key).read_text(encoding='utf-8-sig')
    def url(self,key,line=None):
        x=self.bykey[key]
        if x['repository']:
            tail=x['url'].split('/'+x['revision']+'/',1)[1]
            return f'https://github.com/{x["repository"]}/blob/{x["revision"]}/{tail}'+(f'#L{line}' if line else '')
        return x['url']
    def issue(self,rid,code,message,field=None):self.issues.append({'record_id':rid,'code':code,'message':message,'field':field})
    def add(self,source,native,name,concept=None,**kw):
        rid=uid('record',source+':'+native);key=kw.pop('source_key')
        row=dict(record_id=rid,canonical_factor_id=uid('factor',source+':'+native),source_native_id=native,concept_id=None,factor_concept=concept or name,signal_name=name,aliases=[],formula=None,raw_definition=None,normalized_formula=None,formula_ast=None,formula_hash=None,parameters={},required_fields=[],required_fields_status='not_extracted',frequency=None,asset_class='equity',universe=None,holding_period=None,rebalance=None,source_id=source,source_name=source,source_url=self.url(key),paper_title=None,paper_year=None,authors=[],paper_url=None,code_url=None,license=None,terms=None,terms_url=None,commercial_use_flag='unknown',notes=[],source_revision=self.bykey[key]['revision'],retrieved_at=self.bykey[key]['retrieved_at'],source_file_sha256=self.bykey[key]['sha256'],source_locator=None,definition_kind='metadata',record_kind='signal',primary_source=True,quality_tier='metadata_only',parse_status='not_applicable',parse_error=None,dialect=None,high_quality_eligible=False,formula_origin=None,collection=None)
        row.update(kw)
        row['source_response_sha256']=(json.loads(self.text(key)).get('response_sha256') if self.bykey[key]['storage_policy']=='metadata_only' else self.bykey[key]['sha256'])
        if concept is None:concept=CURATED.get(source,{}).get(native,source+':'+native)
        row['concept_id']=uid('concept',concept);row['factor_concept']=CONCEPTS.get(concept,concept)
        if row['formula']:
            v=normalize(row['formula'],row['dialect']);row.update({k:v[k] for k in ['normalized_formula','formula_hash','parse_status','parse_error','required_fields']});row['formula_ast']=v['ast']
            row['parameters']={**row['parameters'],'numeric_literals':v['numeric_literals'],'operators':v['operators']};row['required_fields_status']='syntax_extracted_unexpanded'
            if v['parse_error']:self.issue(rid,'RAW_FORMULA_PARSE_ERROR',v['parse_error'],'formula')
        self.records.append(row);return row
    def implementation(self,row,key,line,end,language,**kw):
        loc=f'{line}:{end}';raw='\n'.join(self.text(key).splitlines()[line-1:end]);h=digest(raw)
        impl=dict(implementation_id=uid('impl',row['canonical_factor_id']+':'+key+':'+loc+':'+h),record_id=row['record_id'],canonical_factor_id=row['canonical_factor_id'],code_url=self.url(key,line),source_file_sha256=self.bykey[key]['sha256'],source_revision=self.bykey[key]['revision'],source_locator=loc,language=language,implementation_hash=h,implementation_status='source_only_not_executed',python_ast=None,normalized_formula=None,formula_ast=None,parse_status='not_applicable',notes=[])
        impl.update(kw);self.implementations.append(impl)
        source_prefix=key.split(':',1)[0]
        impl['source_repository']=self.bykey[key]['repository']
        impl['source_license']='GPL-2.0' if source_prefix=='osap' else 'MIT'
        impl['source_terms_url']=self.url(source_prefix+':LICENSE')
        impl['commercial_use_flag']=row['commercial_use_flag']
        if row['code_url'] is None:row['code_url']=impl['code_url']
        return impl
