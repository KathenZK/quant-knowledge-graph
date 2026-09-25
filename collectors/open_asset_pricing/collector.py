import ast, copy, re, pathlib
import pandas as pd
from quantgraph.collectors.common import *
from quantgraph.normalize.formula import *

def osap(c):
    key='osap:SignalDoc.csv';df=pd.read_csv(c.path(key)).where(pd.notna(pd.read_csv(c.path(key))),None)
    code_files=[x for x in c.lock if x['key'].startswith('osap:Signals/pyCode/')]
    for i,x in df.iterrows():
        a=x['Acronym']; category=x['Cat.Signal'];definition=clean(x['Detailed Definition']);alias=clean(x['Acronym2'])
        r=c.add('osap',a,clean(x['LongDescription']) or a,source_key=key,source_name='Open Source Asset Pricing',aliases=[a]+([alias] if alias and alias!=a else []),raw_definition=definition,definition_kind='prose' if definition else 'metadata',quality_tier='primary_definition' if definition and category=='Predictor' else 'reference_only',high_quality_eligible=bool(definition and category=='Predictor'),record_kind={'Predictor':'signal','Placebo':'placebo','Drop':'withdrawn'}[category],frequency='monthly',universe='US equities; original-paper filters and licensed inputs vary by signal',holding_period={'value':float(x['Portfolio Period']),'unit':'months','scope':'OSAP original-paper portfolio configuration'} if clean(x['Portfolio Period']) else None,rebalance=None,authors=[clean(x['Authors'])] if clean(x['Authors']) else [],paper_year=int(x['Year']) if clean(x['Year']) else None,license='GPL-2.0',terms='Repository GPL-2.0; source notice required, derivative code distribution subject to GPL. Underlying financial data rights are separate.',terms_url=c.url('osap:LICENSE'),commercial_use_flag='conditional_copyleft',source_locator='CSV record '+str(i+1)+'; Acronym='+a,parameters={'sign':float(x['Sign']) if clean(x['Sign']) else None,'portfolio_period_months':float(x['Portfolio Period']) if clean(x['Portfolio Period']) else None,'start_month':float(x['Start Month']) if clean(x['Start Month']) else None,'stock_weight':clean(x['Stock Weight']),'long_short_quantile':clean(x['LS Quantile']),'filter':clean(x['Filter'])},notes=[s for s in [clean(x['Notes']),f"Source classification: {category}; replication quality: {x['Signal Rep Quality']}; data category: {x['Cat.Data']}",'主账定义与具体代码分别保留；论文复现评级不等于净收益或未来有效性。'] if s])
        r['required_fields']=sorted(set(re.findall(r'\(([a-z][a-z0-9_]{1,25})\)',definition or '')));r['required_fields_status']='partial_definition_extraction'
        # Prefer exact filename, otherwise verify literal output symbol in source.
        candidates=[v for v in code_files if pathlib.Path(v['path']).stem==a]
        if not candidates:
            candidates=[v for v in code_files if re.search(r"['\"]"+re.escape(a)+r"['\"]",c.text(v['key']))]
        for v in candidates[:3]:
            code=c.text(v['key']);lines=code.splitlines();c.implementation(r,v['key'],1,len(lines),'python')
            try:doc=ast.get_docstring(ast.parse(code)) or ''
            except SyntaxError:doc=''
            title=re.search(r'(?im)^(?:Paper(?: Title)?|Title)\s*:\s*(.+)$',doc)
            if title:r['paper_title']=title[1].strip()
        if not candidates:c.issue(r['record_id'],'CODE_LINK_UNRESOLVED','No exact output or matching filename in pinned Python code.','code_url')
        if not r['paper_title']:c.issue(r['record_id'],'PAPER_TITLE_NOT_IN_CATALOG','Author/year retained; exact original paper title not filled without evidence.','paper_title')
