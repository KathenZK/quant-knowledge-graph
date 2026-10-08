# 原来源核查 · 20261004-v1

本批追索历史分类队列中的4条记录。M0115、M0196、M2122取得与原来源直接关联的公开源码，可补为策略；M0176的原仓库及README当前不可得，保留待分类。核查日为2026-10-04，本次没有执行源码、下载行情或运行回测。

[批次索引](index.json)绑定4份记录、原CSV行与规则摘要、来源版本、文件摘要及定位。原CSV和[历史分类批次](../../classifications/20261004-v1/README.md)保持原样；新证据以同卡的`SOURCE_FOLLOWUP`版本追加，集合适配器为`source_followups`。

| 原ID | 本次结果 | 补到的关键证据 |
|---|---|---|
| [M0115](records/M0115.json) | strategy / `SOURCE_CODE_REVIEWED` | 官方能源股一目教程、固定仓库文件及其嵌入算法形成定位链；取得选池、信号和组合代码 |
| [M0196](records/M0196.json) | strategy / `SOURCE_CODE_REVIEWED` | 原页直接绑定的公开Pine脚本版本1.0；取得SuperTrend计算、双向停止入场和仓位声明 |
| [M2122](records/M2122.json) | strategy / `SOURCE_CODE_REVIEWED` | 原页直接绑定的公开Pine脚本版本2.0；取得引擎切换、入场、退出、仓位与配置 |
| [M0176](records/M0176.json) | unclassified / `SOURCE_UNAVAILABLE` | 原仓库API及main/master README均返回404；没有取得可绑定该变体的原文或源码 |

当前统一目录为8,546张条目卡：6,423策略、2,039因子、83参考资料、1待分类；CSV已分类6,970/6,971条。新批次只增加4个证据版本，总版本数为8,556；已审说明为14份，来源核查记录为4份。历史`classification_decisions`仍为6,782，不能把核查记录再加进条目总数。

## 三条规则补证

**M0115：能源股一目均衡。** 原CSV只写“最大能源股上用一目均衡表交叉”。官方目录说明、QuantConnect/Tutorials中1028教程的固定文件，以及该文件引用的嵌入算法建立了对应关系。源码按月更新有基本面数据的能源股池，按市值降序取10只；日线信号比较Ichimoku的Chikou输出与云层上下沿，从非上方进入上方发多向信号，从非下方进入下方发空向信号。进入云内没有显式Flat信号，而是保留已有方向并续发一天期Insight；主程序调用等权组合和即时执行模型。

这些是已读代码的行为，不能替换成“当前收盘穿云即开平仓”。另取的当前Lean依赖版本只用于解释接口，未证明是原嵌入回测所用引擎；历史成交、费用、借券及缺失历史数据处理仍未复现。教程规则也不能直接等同其引用论文的固定股票池研究。

**M0196：SuperTrend停止入场。** 原CSV只有XBTUSD、1分钟、倍数2和周期14。原页面绑定的版本1.0为Pine v4；源码递归更新ATR轨道，每次计算都依次提交多向和空向两张停止入场单，两者价格均为当前`st_line`，默认数量按权益100%配置。交叉标记只用于绘图；源码没有独立`exit/close`、取消单或OCA互斥组。

反向入口具有Pine引擎的反转语义，但双向订单的实际成交先后尚未重放。页面场景为BitMEX XBTUSD的1分钟图，代码本身使用宿主图表；真实费用、资金费、合约单位和保证金对应关系仍缺。原页展示的收益数字仅保留为作者报告，不当作本次回测结果。

**M2122：双引擎与均值回归配置。** 原CSV只留下EMA/MACD等参数。原页当前公开版本2.0为Pine v6，包含实际`strategy.entry`及退出逻辑；自动模式在周期不超过900秒时选择均值回归，否则选择EMA-MACD引擎。均值回归默认以EMA40、RSI2和ATR偏离构造入场信号，再受趋势及交易窗口等条件约束；默认关闭做空。源码还给出ATR止损/目标、时间退出和仓位计算。

这是本次抓取的已发布版本，标题及代码包含预测显示等扩展，不能倒推原CSV采集时已包含全部相同功能。绘图、预测和提示标签也不能代替实际入口条件。代码内的费用、滑点与运行参数是脚本配置，不代表真实成交成本；没有运行源码或验证预测与收益。

## M0176：来源不可得

原来源为`visioneth/V33X-Pine-Scripts`。本次GitHub仓库API，以及原库main/master分支README请求均返回404。作者公开仓库列表未列出该库，含fork的仓库搜索未找到结果；这只能说明本次公开检索未取得原源，不能判断它过去不存在、已永久删除或是否转为私有。

同作者`crypto-kill-zones`的固定README仍引用原仓库，但它描述的是其他交易时段工具，未给出M0176的15分钟、RSI(9)、EMA(9)、75/25组合，不能拿来补规则。同URL的M0191、M0193参数也不同，不能移植其开平条件。指定本机范围内未找到对应旧快照；Internet Archive的CDX请求返回503、availability请求返回429，因此没有核验到历史快照，也不能宣称历史快照不存在。

M0176仍只有原CSV参数摘要。EMA作用于价格还是RSI、阈值属于状态还是穿越、趋势对齐含义、交易方向和离场均不明；缺项见[记录](records/M0176.json)。后续取得该变体的原README、源码或可核验快照后再追加证据，不使用相似策略代替。

## 当前查询与校验

```bash
uv run quantgraph catalog-search --kind unclassified
uv run quantgraph catalog-search --status SOURCE_UNAVAILABLE
uv run quantgraph catalog-show M0176
uv run quantgraph catalog-show M0196
uv run python -m quantgraph.graph.source_review --index metadata/source-reviews/20261004-v1/index.json
# 仅在本机保有原始快照时使用：
uv run python -m quantgraph.graph.source_review --index metadata/source-reviews/20261004-v1/index.json --verify-snapshots
```

`statuses.source_followup`保留核查结果。普通校验检查已提交记录、schema、摘要、原CSV绑定与来源定位；`--verify-snapshots`另检查本机原始快照的字节与摘要。源码和网页原文留在被Git忽略的快照目录，Git只保存自撰规则、定位、版本摘要、许可状态及缺项。

历史分类批次的`unclassified-queue.json`仍保存冻结时的4条；当前待分类集合以知识目录查询为准。`SOURCE_CODE_REVIEWED`只表示审过所列源码，不等于规则全部可执行、计算语义通过、正式准入、盈利或可商用。许可证范围按记录分别保留，不从社区源码授权推导论文、网页或行情授权。本批未修改活动Site、旧运行库或交易系统。
