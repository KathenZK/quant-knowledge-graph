# 已采集因子目录

这是统一知识目录中的因子条目，按已有 `factor_variant_id` 登记，不按来源权限另建两套主目录。来源、准入与许可均是条目字段。`index.json` 是当前索引；`records/` 每个 JSON 对应一个既有变体，所有旧来源记录和原生 ID 保留。

`signal` 表示信号条目；`placebo` 为安慰剂/未确认预测记录；`withdrawn` 为已撤回记录；`parameter_template` 为参数模板；`factor_portfolio` 为因子组合。后三类及 placebo 不得统称为已准入正式单因子。参数不同、实现不同和经济概念不同不是一回事。目录不新增经济等价关系，不把语法已解析改写为语义已验证。

## 内容与归属

- Microsoft Qlib：保留官方配置展开公式、输入与参数，按 MIT 归属；完整声明已经随 `datasets/public` 的当前发布保存。518 个来源记录折叠为 510 个既有变体，其中 508 属于历史准入，另外 2 个仍有准入问题。
- Open Source Asset Pricing（Chen、Zimmermann 与贡献者）：保存已有短定义摘录、输入和结构化参数，原仓库 GPL-2.0 条件及署名随记录保留。超过 400 字符的定义仅取完整开头短句，明确标记截断，不能按摘录回测。源码许可不替代原论文或 CRSP/Compustat/IBES 授权。
- JKP（Jensen、Kelly、Pedersen 与贡献者）：保存已有短定义和字段，文档参考内容保守保留 CC BY-NC 4.0 限制及 DATA_LICENSE，不用代码 MIT 消除非商业限制。LaTeX 定义没有伪装成可执行公式。
- Kenneth French Data Library：仅保留项目原有独立数学摘要与来源书目，不复制网站正文或收益数据；市场数据商业权利仍待核。
- WorldQuant Alpha101 / GTJA Alpha191：保留社区转录的来源身份、输入、算子、数值参数及自撰结构摘要，不复制完整公式；原公式摘要和定位用于追溯。社区 MIT 不代表原论文/研报已授权。
- AQR：原采集仅有书目和数据集入口，没有取得定义；本目录明确缺失，不补造公式或收益数据。

许可附件：[OSAP GPL-2.0](licenses/OSAP-GPL-2.0.txt)、[JKP DATA_LICENSE](licenses/JKP-DATA-LICENSE.txt)。它们保持锁定来源的原始字节，仅用于交付必要许可声明，不计作因子或定义。JKP 引用：Jensen, Kelly and Pedersen (2023), “Is There a Replication Crisis in Finance?”, Journal of Finance, DOI 10.1111/jofi.13249。OSAP 引用：Chen and Zimmermann (2022), “Open Source Cross-Sectional Asset Pricing”, Critical Finance Review 11(2), 207–264。

本次对来源做了字段选择、JSON 格式转换、短句摘录和自撰结构摘要；`content_origin` 区分引用摘录与自撰内容，`truncated` 标记未展示后续条件。400 字符仅是本批展示摘录上限，不是准入门槛或规则完整性的证明；原有准入状态不由该上限决定。

所有许可状态直接保留采集时结论，不因进入统一目录而获得新的商业、行情或论文权限。本目录没有源代码、完整来源正文、市场观测、账户数据、执行接口或新回测结果。

## 完整性与再生成

`index.json` 保存输入文件摘要和当前条目摘要。各条 `provenance.source_lines` 保留原始 JSONL 行号、字节数及 SHA-256（不含换行符），`sources` 保留原来源文件的摘要和版本。机器绝对路径不进入条目。

```sh
python scripts/export_factor_metadata.py --validate
python scripts/export_factor_metadata.py --normalized-records /authorized/factor_records.jsonl --curated-release /authorized/curated/release --public-release /authorized/public/release --source-lock /authorized/project/datasets/raw/source_lock.json --check
```

省略 `--check` 才会写目标目录；输入必须显式提供，工具不搜索私有目录、不采集新数据、不修改原文件。缺少授权源文件时仍可对已提交目录运行 `--validate`，但这不等于重建原始采集或验证计算语义。
