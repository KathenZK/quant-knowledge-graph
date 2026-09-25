# 关系构建

`graph/curate.py` 构建带证据的关系；`models.entities.Relationship` 限制关系类型；`graph/store.py` 和 `graph/verify.py` 验证引用及端点类型。SQL 索引支持正反向查询。

第二阶段的策略关联独立保存在 strategy_factor。规则使用与经验收益归因必须分开。
