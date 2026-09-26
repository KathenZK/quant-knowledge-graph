# 规则与跨源本体的证据边界

本轮真实语料为 5813 条。严格解析从 75 条升至 170 条（1.29% → 2.92%）；
定义待审从 5738 降至 5643。按支持的规则结构得到 23 个方法族、32 个模板；
不能把这 23 个方法族称为统计独立、已验证的盈利假设。

[规则覆盖报告](ingestion-coverage.json) 包含按优先匹配分配的互斥 archetype 统计，
这些关键词类别只用于排期，绝不用于生成 AST。剩余大类包括均线、横截面排序和振荡器；
代码片段、缺失的变量定义、交易时序、资金分配和含糊叙述仍须核对来源。

解析器为全串匹配，支持明确的振荡器/波动阈值、SMA/EMA 持有态和交叉事件、
绝对/相对动量、通道突破、ZScore 回归、排名等权、配对价差等有限语法。
存在语法支持但当前语料没有严格匹配的类别，覆盖报告不会虚增这些类别的成功数。
完整原始规则和英文源码不改写；不使用 LLM 补全 AST。

StrategyConcept/Family → Template → Variant 延用原 ID 命名方式。
参数/资产不同的同一结构共用模板；同 URL 不直接合并，来源原生身份、来源证据、
params/market/assets 分别保留。source-native/source-implementation/source-derived/bot-derived
等分类继续按证据表示，无法确认的保持 UNKNOWN。新批次不按全量聚类序号重排 ID。
版本升级追加投影、重新计算当前视图；旧投影可通过 lineage 保留追踪。

170 条规则可建立信号因子候选关系，均为 RULE_LINK_ONLY；HTTP projection 保存 source、
confidence、evidence、link_reason、parser_version，可反向 factor → strategies 查询。
与某个技术信号有关，不代表其收益来自该经济因子。低置信或未解析记录不创建确定关系。

跨源经济分类运行于 Qlib / OSAP / JKP / Fama-French / AQR / Alpha101 / Alpha191 共 1578 条。
[聚合结果](factor-mapping-coverage.json)：105 条已有证据支持的类别联系，1473 条未决，
1 组跨源公式相似冲突，0 次 SAME_AS 合并。10 个 canonical 经济概念是稳定分类节点；
本轮关系为 RELATED_TO，不把因子信号、组合构造和经济概念错误合并。
Alpha101/191 的合成表达式没有足够经济等价证据，全部留待审。

完整映射、未决队列和冲突列表可由 `graph.ontology.canonical.map_records` 在私有 normalized
记录上重建。映射引用源记录和定义 hash，源公式、论文、股票池、组合构造继续留在原数据层。
`relation_decision` 区分 SAME_AS / ALIAS_OF / VARIANT_OF / DERIVED_FROM / RELATED_TO /
IMPLEMENTATION_OF；除经过人审且全部语义与组合字段一致的 SAME_AS 判定外，候选均待审。
该函数不执行合并。商业许可仍由原 rights gate 独立判断。
