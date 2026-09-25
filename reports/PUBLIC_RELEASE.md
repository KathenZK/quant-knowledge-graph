# 公开发布范围

公开内容：项目代码、文档、实体 schema、稳定 ID 注册表、来源 URL/版本/摘要索引，以及固定 Qlib 版本的三个 MIT 文件和 508 个信号变体。

Qlib 固定 revision：`be725493eb1a6bbb42bf11b37aa7669f59610ff1`。原始 518 个输入列，合并 8 条完全相同表达式来源，排除 2 个常数/近常数特征，得到 508 个具体变体、43 个特征族。

未公开：完整混合许可研究数据、非 Qlib 来源原文、本机迁移记录、任务标识、本机路径日志和个人环境。原始私有文件仍保留在维护者本地，不被公开构建改写。

## 可重复验证

```sh
uv sync --frozen --extra test
uv run quantgraph verify-public
uv run quantgraph build-public
uv run pytest tests/test_formula.py tests/test_public.py -q
```

`verify-public` 检查来源摘要、所有公开导出摘要、发布身份、SQLite 完整性/外键/实体类型、CSV/Parquet/SQLite 逐字段一致性，以及商业许可隔离。

公开测试从只包含允许公开文件的临时目录启动 SDK/API，并验证重建保持相同逻辑记录、同一环境内重复构建得到相同发布摘要。CI 不需要私有研究资料或账号凭据。

源码公开不代表所有内容采用同一开放许可，见根 LICENSE 和公开发布中的 THIRD_PARTY_LICENSE.txt。
