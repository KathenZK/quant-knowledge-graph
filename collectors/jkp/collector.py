import ast, copy, re, pathlib
import pandas as pd
from quantgraph.collectors.common import *
from quantgraph.normalize.formula import *

def bibliography(text):
    out={}
    for m in re.finditer(r'@\w+\{([^,]+),([\s\S]*?)(?=\n@|\Z)',text):
        values={}
        for field in ['title','author','year','url','doi']:
            x=re.search(r'(?im)^\s*'+field+r'\s*=\s*[{\"](.+?)[}\"]\s*,?\s*$',m[2]);values[field]=latex_text(x[1]) if x else None
        out[m[1]]=values
    return out

def jkp(c):
    key='jkp:documentation/documentation.tex';text=c.text(key);bib=bibliography(c.text('jkp:documentation/documentation.bib'))
    metadata={}
    for line in text.splitlines():
        parts=re.split(r'(?<!\\)&',line)
        if len(parts)==6 and '\\citeA{' in parts[2]:
            native=parts[1].strip().replace('\\_','_');ck=re.search(r'\\citeA\{([^}]+)\}',parts[2]);metadata[native]={'name':parts[0].strip(),'cite':ck[1],'sign':parts[4].strip()}
    frame=pd.read_excel(c.path('jkp:src/jkp/data/resources/factor_details.xlsx'));core={str(x['abr_jkp']):x for _,x in frame.iterrows() if pd.notna(x['abr_jkp'])};assert len(core)==153
    clusters=pd.read_csv(c.path('jkp:src/jkp/data/resources/cluster_labels.csv'));cluster_map=dict(zip(clusters.characteristic,clusters.cluster))
    parsed={}
    for label in ['accounting_char','market_char']:
        start=text.index('\\label{'+label+'}');end=text.index('\\end{longtable}',start);block=text[start:end]
        for m in re.finditer(r'(?m)^\s*(.*?)\s*(?<!\\)&\s*([a-z][a-z0-9_\\]*)\s*(?<!\\)&\s*([\s\S]*?)(?=\\\\)',block):
            name,native,definition=m.groups();native=native.replace('\\_','_')
            if native=='Abbreviation':continue
            name=latex_text(name);definition=definition.strip();line=text[:start+m.start()].count('\n')+1
            if native in parsed:
                c.issue(uid('record','jkp:'+native),'DUPLICATE_SOURCE_ABBREVIATION',f'Documentation repeats {native} at line {line}; all source occurrences retained in notes.','source_native_id')
                parsed[native]['duplicates'].append({'line':line,'name':name,'definition':definition});continue
            parsed[native]={'name':name,'definition':definition,'line':line,'duplicates':[]}
    for native in sorted(set(parsed)|set(core)):
        info=parsed.get(native);meta=metadata.get(native,{});ref=bib.get(meta.get('cite'),{});core_row=core.get(native)
        name=info['name'] if info else str(core_row['name_new']);definition=info['definition'] if info else None
        template=bool(re.search(r'_z(?:d|m)?$|_x$|_n$',native))
        if not definition and native in meta:definition='Definition reference: '+name+'. See linked characteristic-construction documentation.'
        detailed=bool(info and 'Outlined in detail' not in definition)
        flags=[]
        if info and info['duplicates']:flags.append('原始文档编号重复；对应定义见 source_occurrences，待核对，不能自动挑选。')
        if not detailed:flags.append('当前记录为方法引用；不能直接当成完整可执行公式。')
        if template:flags.append('原文中的窗口模板，未自动扩成任意参数，排除独立信号计数。')
        r=c.add('jkp',native,name,source_key=key,source_name='JKP Global Factor Data',aliases=[native]+([str(core_row['abr_hxz'])] if core_row is not None and pd.notna(core_row['abr_hxz']) else []),raw_definition=definition,definition_kind='latex' if info else 'metadata',quality_tier='primary_definition' if detailed else 'reference_only',record_kind='parameter_template' if template else 'signal',high_quality_eligible=detailed and not template and not info['duplicates'],frequency='monthly',universe='global equities; source covers 93 countries; country-specific data availability',holding_period={'value':1,'unit':'month','scope':'default JKP monthly factor portfolio'},rebalance='monthly for default monthly JKP portfolios',paper_title=ref.get('title'),paper_year=int(ref['year']) if ref.get('year','') and ref['year'].isdigit() else None,authors=ref['author'].split(' and ') if ref.get('author') else [],paper_url=ref.get('url') or (('https://doi.org/'+ref['doi'].removeprefix('https://doi.org/')) if ref.get('doi') else None),license='CC-BY-NC-4.0 (reference metadata; conservative scope); MIT (code)',terms='Research reference extraction is attributed and modified. Excluded from commercial export. No WRDS/CRSP/Compustat values collected.',terms_url=c.url('jkp:DATA_LICENSE'),commercial_use_flag='noncommercial_only',source_locator=f"documentation.tex:L{info['line']}" if info else 'factor_details.xlsx: abr_jkp='+native,parameters={'core_153':native in core,'theme':cluster_map.get(native),'original_sign':meta.get('sign'),'source_occurrences':info['duplicates'] if info else [],'accounting_availability_lag_months':4},notes=flags+['LaTeX保持原式；未转换为可执行AST。end-of-month特征预测下个月收益，禁止同月错配。'])
        r['required_fields']=sorted(set(re.findall(r'(?<![a-zA-Z])([A-Z][A-Z0-9]*(?:\\_[A-Z0-9]+)*)',definition or '')));r['required_fields_status']='partial_latex_token_extraction'
        if not info:c.issue(r['record_id'],'DEFINITION_SECTION_JOIN_MISSING','Core 153 row found, but no exact characteristic-table abbreviation match.','raw_definition')
        if detailed:
            r['code_url']=c.url('jkp:src/jkp/data/aux_functions.py')
        if not ref:c.issue(r['record_id'],'ORIGINAL_PAPER_METADATA_MISSING','No exact original-paper bibliography join; JKP 2023 is collection provenance only.','paper_title')
