"""Analyze the frozen review universe BEFORE developing new grammar; private output."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3

# Routing labels only; these patterns NEVER create a trading rule.
TAXONOMY = [
 ('source_factor_portfolio', r'Signal Browser Definition|Documentation\.pdf', '完整信号公式、PIT股票池、分组和持仓规则', 'HIGH'),
 ('source_code_fragment', r'strategy\.(?:entry|exit)|input\(|Pine Script', '完整源码、依赖版本、配置、回测语义', 'HIGH'),
 ('pairs_spread_zscore', r'配对|配對|pairs|协整|協整|价差.*[Zz]|[Zz].*价差', '配对池、形成期、价差定义、入场退出、两腿权重', 'HIGH'),
 ('funding_carry', r'资金费率|基差|carry|funding', '合约、两腿价格、资金费率、展期和保证金', 'HIGH'),
 ('options_volatility', r'期权|期權|隐含波动|implied.vol', '期权链、到期日、行权价、希腊值、报价与成交', 'HIGH'),
 ('fundamental_value_quality', r'CAPE|盈利|市净率|账面|价值|质量|财务|ROE|EPS', 'PIT财务数据、发布日期、股票池、打分和换仓', 'HIGH'),
 ('event_calendar', r'新月|满月|财报|公告|季节|星期|周一|周五|节假|日历', '事件时点、日历、持仓窗口、退出和资产', 'HIGH'),
 ('machine_learning', r'机器学习|神经|LSTM|LightGBM|XGBoost|随机森林', '特征、标签、训练窗口、泄漏控制、模型及执行', 'HIGH'),
 ('dual_momentum', r'dual.momentum|双动量|双重动量', '绝对与相对动量窗口、资产池、现金门槛、换仓', 'MEDIUM'),
 ('absolute_momentum', r'absolute.momentum|绝对动量|Intrinsic.Momentum', '资产、收益口径、窗口、阈值、避险资产', 'LOW'),
 ('relative_momentum', r'relative.momentum|相对动量|满仓较高者', '比较资产、窗口、收益口径、平手政策', 'LOW'),
 ('volatility_targeting', r'目标.{0,4}波动|波动.{0,4}目标|volatility.target', '波动估计、目标、杠杆上下界、再平衡', 'MEDIUM'),
 ('trend_volatility_combination', r'(?:均线|\bSMA\b|\bEMA\b).*(?:波动|ATR)|(?:波动|ATR).*(?:\bSMA\b|\bEMA\b|均线)', '趋势条件、波动公式、AND/OR、仓位、退出', 'MEDIUM'),
 ('cross_sectional_rank_top_n', r'横截面|截面|排名|排序|\bTop\d|最高.{0,4}\d|最低.{0,4}\d', 'PIT池、打分公式、排序方向、N、权重、换仓', 'HIGH'),
 ('etf_rotation', r'轮动|輪動|配对切换|Paired.Switching', '完整资产池、相对排名、阈值、分配、平手政策', 'MEDIUM'),
 ('risk_on_off', r'风险开|风险关|risk.on|risk.off|金丝雀', '状态信号、阈值、风险与避险分配、退出', 'MEDIUM'),
 ('rsi', r'\bRSI\b|RSI\(', '周期、平滑方法、阈值、比较/穿越、资产、退出', 'LOW'),
 ('macd', r'MACD', '快慢信号周期、柱/线定义、条件、退出', 'MEDIUM'),
 ('roc', r'\bROC|RoC', '窗口、收益口径、阈值、分配、退出', 'LOW'),
 ('bollinger', r'Bollinger|布林|BBW', '窗口、标准差定义、倍数、上下轨、退出', 'MEDIUM'),
 ('ema_crossover', r'EMA.*(?:上穿|下穿|交叉|金叉|死叉)', '快慢窗口、穿越方向、仓位、反向/平仓', 'LOW'),
 ('sma_crossover', r'SMA.*(?:上穿|下穿|交叉|金叉|死叉)', '快慢窗口、穿越方向、仓位、反向/平仓', 'LOW'),
 ('price_vs_ma', r'\bSMA\b|\bEMA\b|SMA\(|EMA\(|均线|均線', '价格字段、MA类型和窗口、比较、分配、退出', 'LOW'),
 ('oscillator', r'Stoch|Williams|CCI|MFI|UO\(|CMO\(|STC\(|Aroon|RVI', '指标完整参数、阈值、比较、资产与退出', 'MEDIUM'),
 ('volatility_filter', r'波动|波動|ATR|VIX', '波动字段/公式、窗口、阈值、仓位与退出', 'MEDIUM'),
 ('breakout_donchian_rolling_extreme', r'突破|新高|Donchian|通道', '回看窗口、排除当前栏、比较、入场和退出', 'MEDIUM'),
 ('zscore', r'ZScore|Z-score|z.score', '窗口、均值/标准差定义、双阈值、退出', 'LOW'),
 ('mean_reversion', r'回归|回歸|reversion', '锚点、偏离度量、阈值、持仓和退出', 'MEDIUM'),
 ('momentum_other', r'动量|動量|Momentum|收益>', '收益定义、窗口、门槛、资产、退出', 'MEDIUM'),
 ('threshold_allocation', r'阈值|阈|满仓|否则', '完整条件、双方分配、资产与再平衡', 'MEDIUM'),
 ('other_or_ambiguous', r'.', '待逐条确认完整定义', 'HIGH'),
]

def classify(text):
    return next(name for name, pattern, _, _ in TAXONOMY if re.search(pattern, text, re.I))

def main():
    p=argparse.ArgumentParser(); p.add_argument('--journal', required=True); p.add_argument('--out', default='reports'); a=p.parse_args()
    con=sqlite3.connect(f'file:{Path(a.journal).resolve()}?mode=ro',uri=True)
    rows=[json.loads(r[0]) for r in con.execute("SELECT payload FROM projections WHERE parser_version='grok-rule-v3.1' ORDER BY record_id")]
    if len(rows)!=5813: raise ValueError('Expected the frozen v3.1 baseline universe')
    unresolved=[r for r in rows if not r['definition_admitted']]
    groups=defaultdict(list)
    from quantgraph.normalize.strategy.archetypes import review_reason
    for r in unresolved: groups[classify(r['variant']['original_rule_text'])].append(r)
    result=[]
    for name, _, fields, difficulty in TAXONOMY:
        g=groups[name]
        # Include first, middle and last, rather than overrepresenting early source IDs.
        ix=sorted({0,len(g)//2,len(g)-1}) if g else []
        result.append(dict(archetype=name,count=len(g),percentage=round(100*len(g)/len(unresolved),4),
          representative_examples=[{'record_id':g[i]['variant']['source_native_id'],'rule':g[i]['variant']['original_rule_text'],'source_url':g[i]['variant']['source_url']} for i in ix],
          current_parse_failure_reason=dict(Counter(review_reason(r['variant']['original_rule_text']) for r in g)),
          required_fields=fields,likely_parser_difficulty=difficulty))
    result.sort(key=lambda r:(-r['count'],r['archetype']))
    value=dict(generated_at=datetime.now(timezone.utc).isoformat(),baseline_parser='grok-rule-v3.1',
      total_records=len(rows),review_records=len(unresolved),routing_only=True,
      baseline_payload_sha256=hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),archetypes=result)
    out=Path(a.out);out.mkdir(exist_ok=True)
    (out/'rule-archetypes-v3.json').write_text(json.dumps(value,ensure_ascii=False,indent=2))
    md=['# Rule Archetypes V3','',f"冻结解析器 grok-rule-v3.1：{len(rows)} 条，待规则审核 {len(unresolved)} 条。以下是互斥的路由统计，不是 AST 或经济机制认定。先于新增语法生成。",'','| 类型 | 数量 | 队列比例 | 难度 | 必要字段 |','|---|---:|---:|---|---|']
    for r in result:md.append(f"| {r['archetype']} | {r['count']} | {r['percentage']:.2f}% | {r['likely_parser_difficulty']} | {r['required_fields']} |")
    for r in result[:30]:
      md += ['',f"## {r['archetype']}",'',f"当前失败：{r['current_parse_failure_reason']}",'']
      md += [f"- {e['record_id']}：{e['rule']}" for e in r['representative_examples']]
    (out/'rule-archetypes-v3.md').write_text('\n'.join(md)+'\n')
    print(json.dumps({r['archetype']:r['count'] for r in result},ensure_ascii=False))
if __name__=='__main__':main()
