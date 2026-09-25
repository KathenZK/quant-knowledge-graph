# 本体实现位置

实体：`models/entities.py`。独立表与外键：`graph/store.py`。

知识图谱的概念与关系规则见 `docs/DATA_MODEL.md`。持久化采用 SQLite + JSONL，可在不改变 ID 的情况下投影到图数据库；当前无需额外运维 Neo4j。

尚未核验的全局概念合并不进入 SAME_AS。当前 605 个 curated 概念分组不是全球因子本体已经整理完成的声明。
