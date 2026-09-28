# 项目约束

- 本项目负责知识、定义、来源和关系。数据流只能是 quant-knowledge-graph → quant-research-lab → quant-runner。
- 研究项目正式名称及同级目录为 `quant-research-lab` / `../quant-research-lab`；Python 包 `strategy_lab` 兼容保留，不迁入其研究/回测代码。
- 不添加实盘执行、下单、策略发布或 runner 集成接口。
- 原始来源保留字节、版本、摘要和许可。不可直接改写 raw；新版本须采集新快照、审核变更后更新锁文件。
- normalized 收全部可追溯记录；curated 必须通过准入门槛。元数据质量、公式语法、计算语义、经济有效性、商用许可分别判断。
- 同名不是等价证据。参数变体、组合构造、实现和经济概念分别建模。保留旧 ID 和来源原生 ID。
- 不把社区源码的许可证当作原始论文、研报、市场数据的授权；不确定的商业使用为 REVIEW_REQUIRED。
- API 默认 commercial profile；research profile 是显式的私有参考模式，不代表取得商业内部研究许可。
- 不将归因猜测写成收益驱动证据；策略与因子关联须有 role、confidence、evidence、source。
- 变更后运行相关测试；发布前运行 `quantgraph validate-release` 检查离线重建、schema、外键、隔离和导出一致性。
- 公开 Git 仓库只包含已审查的 Qlib 原始文件和 datasets/public；完整 normalized/curated、其他来源原文、本机验收日志不得加入 Git。
- 公开发布先运行 build-public、verify-public 和 tests/test_public.py；完整私有数据仍运行 validate-release。
