"""Fixed real-corpus search audit. Reports are private; the source SQLite is read-only.

Run --phase before before changing search, then --phase after with the same output.
Semantic expectations below are independent of the query tokenizer; HTTP success
alone never passes a case. The frozen witnesses retain their original identities.
"""
import argparse
from collections import Counter
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import statistics
import tempfile
import time

from quantgraph.graph.personal_catalog import PersonalCatalogRepository

MA = r'均线|移动平均|moving[ _-]average|(?<![a-z_])(?:sma|ema)(?![a-z_])|Mean\(\s*\$close'
MOM = r'动量|(?<![a-z_])momentum(?![a-z_])'
RSI = r'相对强弱(?:指标|指数)|(?<![a-z_])rsi(?![a-z_])|relative strength index'
REV = r'均值回归|mean[ _-]reversion'
VOL = r'成交量|(?<![a-z_])volume(?![a-z_])'
BRK = r'突破|(?<![a-z_])breakout(?![a-z_])'
CASES = [
    ('均线动量','strategy',[MA,MOM],'同时含均线与动量证据'),
    ('均线 动量','strategy',[MA,MOM],'空格与无空格应同义'),
    ('RSI均值回归','strategy',[RSI,REV],'RSI 与均值回归均须有据'),
    ('RSI 均值回归','strategy',[RSI,REV],'混合缩写和独立中文概念'),
    ('低波动','strategy',[r'低波动|low[ _-]volatility'],'低波动完整短语，不泛化为所有波动'),
    ('只用日线','strategy',[],'严格日频且已知输入仅 OHLCV'),
    ('成交量突破','strategy',[VOL,BRK],'成交量和突破两个独立条件'),
    ('成交量 突破','strategy',[VOL,BRK],'分隔形式保持相同含义'),
    ('SMA crossover','strategy',[r'(?<![a-z_])sma(?![a-z_])|简单均线|简单移动平均|simple moving average',r'交叉|crossover|cross over|(?<![a-z_])cross(?![a-z_])'],'简单均线和交叉，不泛化为全部均线'),
    ('RSI14','strategy',[r'(?<![a-z0-9_])rsi\s*(?:\(\s*14\s*\)|14(?!\d))(?![a-z_])'],'保留 RSI 的 14 参数'),
    ('MA200','strategy',[r'(?<![a-z0-9_])ma\s*(?:\(\s*200\s*\)|200(?!\d))(?![a-z_])'],'保留 MA200，不把 EMA200/SMA200 当同一标识'),
    ('12-1 Momentum','all',[r'12\s*[-−–]\s*1\s+momentum'],'保留数字区间与完整原名，不保证本机收录'),
    ('moving average momentum','strategy',[MA,MOM],'多词英文同义短语与动量组合'),
    ('布林带均值回归','strategy',[r'布林|bollinger',REV],'布林与均值回归均须有据'),
    ('日线RSI','strategy',[RSI],'日线指数据频率，不是仅提到过去若干日'),
    ('日频成交量','strategy',[VOL],'已知日频与成交量组合'),
    ('资金费率动量','strategy',[r'资金费率|funding[ _]rate',MOM],'费率和动量两个条件'),
    ('配对交易','strategy',[r'配对|pairs? trading'],'配对交易中英同义'),
    ('动量','strategy',[MOM],'不能仅凭“动量与趋势”分类标签命中趋势条目'),
    ('RSI','strategy',[RSI],'不把 StochRSI 名字子串当 RSI'),
    ('均线神秘词XYZ','strategy',[MA,r'神秘词xyz'],'未知词保留，不静默退化为均线查询'),
    ('均线','variant',[MA],'明确均线公式或名称仍可通过中文检索'),
    ('MA5','variant',[r'(?<![a-z0-9_])ma5(?![a-z0-9_])'],'完整名称应优先于在规则/公式中提到的条目'),
    ('Alpha101','variant',[r'(?<![a-z0-9_])alpha101(?![a-z0-9_])'],'保留来源原生编号'),
    ('Mean($close, 5)/$close','variant',[r'Mean\(\s*\$close\s*,\s*5\s*\)\s*/\s*\$close'],'完整原式检索并保持窗口5'),
    ('WorldQuant 成交量','variant',[r'worldquant',VOL],'来源与数据字段两个条件，包含未准入来源记录'),
    ('简单均线交叉','strategy',[r'简单均线|简单移动平均|(?<![a-z_])sma(?![a-z_])|simple moving average',r'交叉|crossover|cross over|(?<![a-z_])cross(?![a-z_])'],'多字术语使用最长已知词，不拆成无意义单字'),
    ('均值回归','strategy',[REV],'固定多字概念不被拆开'),
    ('成交量动量','strategy',[VOL,MOM],'输入字段和方法同时出现'),
    ('资金费率','strategy',[r'资金费率|funding[ _]rate'],'固定金融短语中英映射'),
]


def source_text(value):
    k=value['knowledge']
    return '\n'.join(str(v or '') for v in (value['name'],value.get('aliases'),value.get('source_native_ids'),
        value.get('source_name'),value.get('source_type'),value.get('required_fields'),value.get('parameters'),
        value.get('family'),k.get('formula'),k.get('original_rule'),k.get('original_definition')))


def in_scope(value,kind):
    return not value.get('test_record') and (kind=='all' or value['kind']==kind or
        kind=='variant' and value['kind']=='source' and value.get('source_type')=='factor_source_record')


def semantic_ok(value,query,patterns):
    text=source_text(value)
    if not all(re.search(pattern,text,re.I) for pattern in patterns):
        return False
    if query=='只用日线':
        return value['knowledge']['filters']['daily_ohlcv']
    if query in {'日线RSI','日频成交量'}:
        return value.get('frequency') in {'daily','daily_eod'}
    return True


@contextmanager
def copied_catalog(source):
    # CatalogRepository initialization migrates its schema; never run it against
    # the original operational database during acceptance.
    with tempfile.TemporaryDirectory(prefix='quantgraph-search-audit-') as directory:
        copy=Path(directory)/'catalog.sqlite'
        with sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True) as original, sqlite3.connect(copy) as target:
            original.backup(target)
        yield PersonalCatalogRepository(copy)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--phase',choices=['before','after'],required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    baseline=args.output/'search-before.json'
    if args.phase=='before' and baseline.exists():
        raise SystemExit('Refusing to replace the frozen pre-change baseline')
    old=json.loads(baseline.read_text()) if args.phase=='after' else None
    reports=[];failures=[]
    with copied_catalog(args.runtime/'catalog.sqlite') as catalog:
        started=time.perf_counter();data=catalog._load();cold=time.perf_counter()-started
        original_match=catalog._match;captured=set()
        def traced(eid,groups,extra_documents=(),**kwargs):
            found=original_match(eid,groups,extra_documents,**kwargs)
            if found is not None:
                captured.add(eid)
            return found
        catalog._match=traced
        for index,(query,kind,patterns,intent) in enumerate(CASES):
            expected=sorted(eid for eid,v in data.items() if in_scope(v,kind) and semantic_ok(v,query,patterns))
            witnesses=(old['queries'][index]['witnesses'] if old else expected[:3])
            captured.clear();started=time.perf_counter()
            result=catalog.search(q=query,kind=kind,page_size=20,collapse_duplicates=False)
            elapsed=time.perf_counter()-started
            unexpected=sorted(eid for eid in captured if not semantic_ok(data[eid],query,patterns))
            missing=sorted(set(witnesses)-captured)
            exact=sorted(eid for eid,v in data.items() if in_scope(v,kind) and query.casefold() in
                [str(name).casefold() for name in [v['name'],*v.get('aliases',[])]])
            exact_lost=sorted(set(exact)-captured)
            candidate_gaps=sorted(set(expected)-captured)
            exact_priority=not exact or not result['items'] or result['items'][0]['entity_id'] in exact
            passed=not unexpected and not missing and not exact_lost and exact_priority
            if not passed:
                failures.append(query)
            reports.append(dict(query=query,kind=kind,intent=intent,semantic_patterns=patterns,
                actual_source_candidates=len(expected),witnesses=witnesses,expected_absent=not expected,
                total=result['total'],elapsed_seconds=elapsed,matched_ids=sorted(captured),
                query_plan=result.get('query'),missing_witnesses=missing,overexpanded_ids=unexpected,
                unmatched_loose_candidates=[dict(entity_id=eid,name=data[eid]['name']) for eid in candidate_gaps],
                exact_name_alias_lost=exact_lost,exact_name_alias_priority=exact_priority,status='PASS' if passed else 'FAIL',
                top=[dict(entity_id=v['entity_id'],name=v['name'],matches=v.get('matches')) for v in result['items'][:5]]))
        # A fresh warm round prevents cold index construction from masquerading
        # as query latency; instrument real projection work to verify reuse.
        import quantgraph.graph.personal_catalog as module
        readable_calls=[];real_readable=module.readable_item
        def counted(*a,**kw):
            readable_calls.append(1);return real_readable(*a,**kw)
        module.readable_item=counted;warm=[]
        try:
            for query,kind,_,_ in CASES:
                started=time.perf_counter();catalog.search(q=query,kind=kind,page_size=20)
                warm.append(time.perf_counter()-started)
        finally:
            module.readable_item=real_readable
        report=dict(phase=args.phase,status='PASS' if not failures and not readable_calls else 'FAIL',
            catalog_counts=dict(Counter(v['kind'] for v in data.values() if not v.get('test_record'))),
            source_open_mode='read-only SQLite backup; all repository initialization occurs in a temporary copy',
            source_rows_sha256=hashlib.sha256(json.dumps(sorted((eid,v['definition_revision']) for eid,v in data.items())).encode()).hexdigest(),
            cold_seconds=cold,warm_seconds=dict(median=statistics.median(warm),max=max(warm),p95=sorted(warm)[int(len(warm)*.95)-1]),
            warm_readable_item_calls=len(readable_calls),queries=reports,failed_queries=failures,
            limitations='PASS 仅表示固定见证、全部返回项词汇证据与精确名保留通过；宽松候选未命中另列，不宣称穷尽语义召回。词汇共现提供检索证据；否定、对照方法和引用也可能命中。检索命中不等于来源证明方法等价或收益有效。')
        target=args.output/f'search-{args.phase}.json'
        target.write_text(json.dumps(report,ensure_ascii=False,indent=2))
        if old:
            lines=['# 固定真实中文检索验收','',f"状态：{report['status']}；固定 {len(CASES)} 条查询；暖搜中位 {statistics.median(warm):.3f}s，P95 {report['warm_seconds']['p95']:.3f}s，最大 {max(warm):.3f}s；重新生成阅读内容 {len(readable_calls)} 条。",'',
                '|查询|本意|原命中|现命中|宽松候选|未命中候选|漏固定证据|过宽|精确名丢失|结论|','|---|---|---:|---:|---:|---:|---:|---:|---:|---|']
            for before,after in zip(old['queries'],reports):
                lines.append(f"|{after['query']}|{after['intent']}|{before['total']}|{after['total']}|{after['actual_source_candidates']}|{len(after['unmatched_loose_candidates'])}|{len(after['missing_witnesses'])}|{len(after['overexpanded_ids'])}|{len(after['exact_name_alias_lost'])}|{after['status']}|")
            lines+=['',report['limitations'],'','每个查询的原始证据片段、固定见证 ID、全部命中 ID、未知词与展开条件在 search-before.json / search-after.json；资料缺失允许零命中。']
            (args.output/'search-acceptance.md').write_text('\n'.join(lines))
        print(json.dumps({k:v for k,v in report.items() if k not in {'queries'}},ensure_ascii=False))
        print(json.dumps([dict(query=r['query'],total=r['total'],candidates=r['actual_source_candidates'],missing=len(r['missing_witnesses']),overexpanded=len(r['overexpanded_ids']),top=[v['name'] for v in r['top'][:2]]) for r in reports],ensure_ascii=False))
    if args.phase=='after' and report['status']!='PASS':
        raise SystemExit(1)


if __name__=='__main__':
    main()
