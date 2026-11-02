# v48 中证500/中证1000指数增强专题（规则不全，待回测）

本批按用户要求，把规则缺口较小、缺项可以逐条列明的 5 条 A 股指数增强记录入库，**全部标为“规则不全”**，**不计入 1,000 + 1,000 目标**（manifest 计数：strategy 0 / factor 0 / records 5 / execution_trials 0）。没有放宽质量合同：`required_for_target` 中的 `core_rules_complete` 仍是计数前提；本批复核记录一律 `core_rules_complete: false`，并用合同已有的不计目标结论（`INCOMPLETE` 4 条；`EXISTING_DEFINITION` 1 条，即 M0968 的来源复核）记录。每条 review 另带 `rule_completeness: "规则不全"`、`missing_items`、`lookahead_notes`、`reported_performance.status = REPORTED_UNVERIFIED`、`backtest_status = NOT_BACKTESTED`。没有运行任何算法，没有回测，研报或作者自报的绩效均未验证。

本批**未登记到 `metadata/catalog.json`**：现有目录适配器 `_source_collection` 遇到非 `REVIEWED_DISTINCT_CONSTRUCTION` 结论会报错（"Only reviewed new definitions enter this collection adapter"），为不改代码、不放宽合同，本批只作为独立校验的集合目录存在。

本批承接 v47（f899f3e），`prior_checkpoint` 指向 v47 批次。来源为 HTML/Markdown 快照（`utf8` 提取，行段哈希），原始快照只存本地 `datasets/raw/sources/harvest2000-v48/`，不入 Git；不含任何研报 PDF。

| 记录 | 来源（机构/作者，日期） | 复核结论 | 主要缺项 |
|---|---|---|---|
| HT2024:CSI500-inclusion-R2-event-ew | 海通证券金融工程《事件驱动策略之指数成分股调整表现回顾》，2024-11-06（行研转载投资要点） | INCOMPLETE | 入场时点（公告日收盘或次日开盘）未写明，**回测须按公告次一交易日开盘入场**；交易成本；超额口径；仅摘要 |
| TF2018:adaptive-risk-control-index-enhancement-source-upgrade | 天风证券金工《基于自适应风险控制的指数增强策略》，2018-07-05（BigQuant转载摘要） | EXISTING_DEFINITION（= M0968，不新增行） | 因子清单与窗口；偏离网格/回看期/目标TE（前次Scribd读到的0.1%–0.5%、3个月、TE 4%本次未能固定，未核实）；调仓、费用；正文PDF链接404 |
| SWHY2025:CSI500-enhancement-differentiated-constraints | 申万宏源金工《量化策略演进手记系列之一》（原报告日期2025-12-29据前次采集，未复核；发现报告纪要页2026-08-20） | INCOMPLETE | 底层alpha因子表；超额波动率与行业权重分档阈值；宏观筛选方法；目标函数、调仓、费用；作者需原文复核 |
| BQ2025:CSI1000-6class-alpha-QP-enhancement | BigQuant社区《中证1000指数增强策略》，页面更新2025-12-18（未登录快照显示xiaoshao，登录态显示“大田”，待核） | INCOMPLETE | 6个具体因子在付费私享会源码中；换手1.5的期间单位；风格偏离0.5的单位；成交价格；优化失败时权重 |
| GH2026:yanjunlin828-csi500-multifactor-mainline | GitHub yanjunlin828-dotcom/csi500-multifactor README（提交0e25a33；仓库创建2026-05-28） | INCOMPLETE | 主线因子清单（configs/pipelines 主线文件未抓取）；Tushare→RQData；hk_hold 2024-08后披露变化；测试集结果未公布；**仓库无许可证，未复制代码** |

未入库：中金情景分析因子模型（N1）本次两个来源均抓取失败（慧博连接失败、转载页404），无法固定快照；民生DL元模型、国金Mamba等核心模型未公开的条目按要求排除；其余见 v48 拒收表。
