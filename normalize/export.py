import collections,csv,datetime,hashlib,json,pathlib,sqlite3
import pandas as pd
import jsonschema
from quantgraph.normalize.formula import dumps
from quantgraph.collectors.common import uid

def sources(c):
    result=[]
    for sid in sorted({r['source_id'] for r in c.records}):
        r=next(x for x in c.records if x['source_id']==sid)
        result.append(dict(source_id=sid,source_name=r['source_name'],license=r['license'],terms=r['terms'],terms_url=r['terms_url'],commercial_use_flag=r['commercial_use_flag'],primary_source=r['primary_source'],retrieved_at=r['retrieved_at'],upstream_data_ingested=False))
    return result

JSON_FIELDS={'aliases','formula_ast','parameters','required_fields','holding_period','authors','notes'}
def schema_for_records(sample):
    required=list(sample)
    props={}
    for k in required:
        if k in {'high_quality_eligible','primary_source','backtest_ready'}:props[k]={'type':'boolean'}
        elif k=='paper_year':props[k]={'type':['integer','null']}
        elif k in {'aliases','required_fields','authors','notes'}:props[k]={'type':'array'}
        elif k=='parameters':props[k]={'type':'object'}
        elif k in {'formula_ast','holding_period'}:props[k]={'type':['object','null']}
        else:props[k]={'type':['string','null']}
    for k in ['record_id','canonical_factor_id','concept_id']:
        props[k]={'type':'string','pattern':r'^qkg:[a-z]+:[0-9a-f-]{36}$'}
    props['commercial_use_flag']={'enum':['unknown','permitted_with_attribution','conditional_copyleft','noncommercial_only','permission_required','upstream_rights_review_required']}
    return {'$schema':'https://json-schema.org/draft/2020-12/schema','$id':'https://example.invalid/qkg/factor-record-v1.schema.json','title':'QKG Factor Record v1','type':'object','required':required,'properties':props,'additionalProperties':False}

def flatten(rows):
    return [{k:dumps(v) if isinstance(v,(list,dict)) else v for k,v in row.items()} for row in rows]

def write_tables(root,tables):
    data=root/'datasets/normalized';data.mkdir(parents=True,exist_ok=True)
    for name,rows in tables.items():
        if not rows:continue
        p=data/(name+'.jsonl');p.write_text(''.join(json.dumps(x,ensure_ascii=False,sort_keys=True,allow_nan=False)+'\n' for x in rows))
        df=pd.DataFrame(flatten(rows));df.to_csv(data/(name+'.csv'),index=False);df.to_parquet(data/(name+'.parquet'),index=False)

def database(root,tables):
    path=root/'datasets/normalized/factors.sqlite';path.unlink(missing_ok=True)
    con=sqlite3.connect(path);con.execute('PRAGMA foreign_keys=ON')
    keys={'sources':'source_id','concepts':'concept_id','factors':'canonical_factor_id','records':'record_id','implementations':'implementation_id','aliases':'alias_id','relationships':'relation_id','duplicate_candidates':'candidate_id','operators':'operator'}
    refs={'factors':{'concept_id':('concepts','concept_id')},'records':{'canonical_factor_id':('factors','canonical_factor_id'),'concept_id':('concepts','concept_id'),'source_id':('sources','source_id')},'implementations':{'canonical_factor_id':('factors','canonical_factor_id'),'record_id':('records','record_id')},'aliases':{'canonical_factor_id':('factors','canonical_factor_id'),'record_id':('records','record_id')}}
    for name in ['sources','concepts','factors','records','implementations','aliases','relationships','duplicate_candidates','issues','operators']:
        rows=flatten(tables[name]);columns=list(dict.fromkeys(k for r in rows for k in r))
        if not columns:continue
        types={k:'INTEGER' if k in {'paper_year','high_quality_eligible','primary_source','backtest_ready','upstream_data_ingested'} else 'TEXT' for k in columns}
        defs=[f'"{k}" {types[k]}'+(' PRIMARY KEY' if k==keys.get(name) else '') for k in columns]
        for k,(to,key) in refs.get(name,{}).items():defs.append(f'FOREIGN KEY ("{k}") REFERENCES "{to}"("{key}")')
        con.execute('CREATE TABLE "'+name+'" ('+','.join(defs)+')')
        con.executemany('INSERT INTO "'+name+'" ('+','.join('"'+k+'"' for k in columns)+') VALUES ('+','.join('?' for k in columns)+')',[[r.get(k) for k in columns] for r in rows])
    con.executescript('''
    CREATE TABLE strategies (strategy_id TEXT PRIMARY KEY, external_namespace TEXT NOT NULL, external_id TEXT NOT NULL, name TEXT, spec_url TEXT, spec_sha256 TEXT, status TEXT NOT NULL, UNIQUE(external_namespace, external_id));
    CREATE TABLE strategy_implementations (strategy_id TEXT REFERENCES strategies(strategy_id), implementation_id TEXT REFERENCES implementations(implementation_id), role TEXT NOT NULL CHECK(role IN ('signal','filter','weight','risk','exit')), parameters_json TEXT, PRIMARY KEY(strategy_id, implementation_id, role));
    CREATE INDEX idx_records_source ON records(source_id,source_native_id);
    CREATE INDEX idx_records_factor ON records(canonical_factor_id);
    CREATE INDEX idx_records_concept ON records(concept_id);
    CREATE INDEX idx_alias_lookup ON aliases(normalized_alias,namespace);
    CREATE INDEX idx_impl_factor ON implementations(canonical_factor_id);
    CREATE VIEW commercial_permissive AS SELECT * FROM records WHERE commercial_use_flag='permitted_with_attribution';
    CREATE VIEW primary_defined_signals AS SELECT * FROM records WHERE high_quality_eligible=1;
    CREATE VIEW factor_implementation_strategy AS
      SELECT f.canonical_factor_id, i.implementation_id, si.strategy_id, si.role
      FROM factors f LEFT JOIN implementations i ON f.canonical_factor_id=i.canonical_factor_id
      LEFT JOIN strategy_implementations si ON i.implementation_id=si.implementation_id;
    ''')
    con.commit();assert not con.execute('PRAGMA foreign_key_check').fetchall();assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    ddl=[r[0]+';' for r in con.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY rowid")]
    (root/'models/schemas/legacy/relational.sql').write_text('PRAGMA foreign_keys=ON;\n\n'+'\n\n'.join(ddl)+'\n')
    con.close()

def report(c,tables):
    rows=tables['records'];factors=tables['factors'];issue_counts=collections.Counter(x['code'] for x in tables['issues'])
    group=[]
    for source in sorted({r['source_id'] for r in rows}):
        rr=[r for r in rows if r['source_id']==source]
        group.append(dict(source=source,records=len(rr),canonical_factors=len({r['canonical_factor_id'] for r in rr}),high_quality_unique=len({r['canonical_factor_id'] for r in rr if r['high_quality_eligible']}),raw_formulas=sum(r['formula'] is not None for r in rr),parsed_formulas=sum(r['parse_status']=='parsed' for r in rr),metadata_only=sum(r['definition_kind']=='metadata' for r in rr)))
    summary=dict(record_count=len(rows),canonical_factor_count=len(factors),concept_count=len(tables['concepts']),exact_duplicate_records=len(rows)-len(factors),high_quality_primary_unique=sum(f['high_quality_eligible'] for f in factors),implementation_count=len(tables['implementations']),alias_count=len(tables['aliases']),relation_count=len(tables['relationships']),duplicate_candidate_count=len(tables['duplicate_candidates']),raw_formula_count=sum(r['formula'] is not None for r in rows),raw_formula_parse_success=sum(r['parse_status']=='parsed' for r in rows),raw_formula_parse_errors=sum(r['parse_status']=='parse_error' for r in rows),implementation_stub_count=sum(x['implementation_status']=='stub' for x in tables['implementations']),source_coverage=group,issues=dict(issue_counts),field_missingness={k:sum(r[k] is None or r[k]==[] for r in rows) for k in rows[0]},strategy_count=0,backtests_run=0,licensed_market_data_rows=0)
    return summary

def export(c,tables):
    root=c.root;tables={'sources':sources(c),**tables}
    schema=schema_for_records(tables['records'][0]);(root/'models/schemas/legacy').mkdir(parents=True,exist_ok=True);(root/'models/schemas/legacy/factor_record.schema.json').write_text(json.dumps(schema,ensure_ascii=False,indent=2))
    validator=jsonschema.Draft202012Validator(schema)
    for r in tables['records']:validator.validate(r)
    write_tables(root,tables);database(root,tables)
    safe=[r for r in tables['records'] if r['commercial_use_flag']=='permitted_with_attribution']
    pd.DataFrame(flatten(safe)).to_csv(root/'datasets/normalized/commercial_permissive.csv',index=False)
    summary=report(c,tables);(root/'reports/legacy').mkdir(parents=True,exist_ok=True);(root/'reports/legacy/quality.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False))
    text=['# 数据质量报告','', '本报告评估来源、定义和结构化质量，不评估盈利能力。数字由本次冻结输入重建。','',f"- 来源记录：{summary['record_count']}；保守去重后信号/因子条目：{summary['canonical_factor_count']}。",f"- 其中具备一手具体定义、排除 Placebo/Drop/模板/歧义编号/退化特征的唯一条目：{summary['high_quality_primary_unique']}。",f"- 概念/族群：{summary['concept_count']}。多数是尚未跨来源合并的来源局部概念，不能解释为独立经济机制数。",f"- 完全重复记录：{summary['exact_duplicate_records']}；待人工判断的重复候选：{summary['duplicate_candidate_count']}。",f"- 原始公式 {summary['raw_formula_count']} 条；成功解析 {summary['raw_formula_parse_success']} 条；原文解析失败 {summary['raw_formula_parse_errors']} 条。",f"- 实现记录 {summary['implementation_count']}；空实现 {summary['implementation_stub_count']}。未执行上游交易/数据下载代码，未做收益回测。",'', '| 来源 | 原始记录 | 去重条目 | 一手具体定义 | 公式解析成功/原式 |','|---|---:|---:|---:|---:|']
    for x in summary['source_coverage']:text.append(f"| {x['source']} | {x['records']} | {x['canonical_factors']} | {x['high_quality_unique']} | {x['parsed_formulas']}/{x['raw_formulas']} |")
    text+=['','## 数量口径','', 'Qlib 的窗口和滞后特征是真实来源中的输入列，会计入信号条目；不会宣传为独立盈利因子。JKP 只提取实际文档行和 153 核心对照，不按 93 个国家重复计数，不凭网页总数补齐不存在的记录。OSAP Placebo 和 Drop 另作标记。AQR 只收元数据，不计一手具体定义。','', '## 完整性问题','']
    for k,v in summary['issues'].items():text.append(f'- {k}: {v}。逐条定位见 `data/issues.csv`。')
    text+=['','## 缺失字段','', '没有证据的 paper_title、holding_period、rebalance、universe 保持空值；不把因子观察频率自动当作策略调仓频率。公式中的字段抽取不等于数据可用性验收，所需字段还可能有复权、报告披露时点、行业分类和供应商依赖。','', '| 字段 | 缺失条数 |','|---|---:|']
    for k in ['paper_title','paper_year','authors','code_url','holding_period','rebalance','universe','required_fields']:text.append(f"| {k} | {summary['field_missingness'][k]} |")
    text+=['','## 商业边界','', '许可按照内容单独保留。`commercial_permissive.csv` 当前仅含明确宽松许可的 Qlib 表达式，使用时仍需保留 MIT 版权声明。OSAP 代码/定义受 GPL 条件约束；JKP 参考提取按 CC BY-NC 处理；WorldQuant/GTJA 的社区 MIT 许可不证明原始公式权利链已清理；AQR/French 收益数据没有进入本库。','', '## 可复现性','', '所有冻结文件有 SHA-256；离线重建不访问网络。`factorlib verify` 检查输入摘要、schema、唯一键、表间外键、记录数以及导出一致性。代码修复/单元测试结果见 `reports/validation.json`。原文语法树解析与经济语义验收是两件事。']
    (root/'reports/legacy/DATA_QUALITY.md').write_text('\n'.join(text)+'\n')
    manifest={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ['datasets/normalized','models/schemas/legacy'] for p in sorted((root/folder).glob('*')) if p.is_file()}
    (root/'reports/legacy/export_manifest.json').write_text(json.dumps(manifest,indent=2))
    return summary
