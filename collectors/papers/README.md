# 论文采集范围

当前只采集论文书目、引用和来源位置，不批量下载全文。

- JKP BibTeX 的严格键匹配由 `collectors/jkp/collector.py:bibliography` 执行。
- OSAP 只保留来源中实际存在的作者/年份；缺题目的引用作为 PARTIAL_CITATION，不按作者年份自动合并。
- `graph/curate.py` 将这些书目变成独立 Paper / Author 实体并记录 provenance。
- Qlib 平台论文与 JKP/OSAP 汇总论文用 COLLECTION_REFERENCE 标记，不冒充每个特征的原始论文。
- 下一批 DOI/论文元数据采集须保存查询、返回来源、匹配置信度和人工裁决；不能仅靠同名标题自动替换已有 ID。
