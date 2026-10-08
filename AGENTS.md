# 项目约束

- 因子、策略及待分类资料统一登记在 `metadata/catalog.json` 知识目录；来源、许可、审核与研究状态作为条目字段，不把公开/本机私有发布称作两套因子库。已有核心发布目录保留作技术兼容。
- 全部已采集因子通过 `metadata/factor-sources` 的逐版本元数据入仓库，保留原生 ID、定义、来源和缺项；不因登记而晋级准入或回测状态。必要许可证附件随元数据保存。

- QuantGraph 负责公开资料整理、定义/来源/关系、基础与筛选回测的编排和结果管理，以及个人标记。当前以单用户为主；未来 to C 是方向，不代表现在可以公开私有资料。
- quant-research-lab 承担对感兴趣策略的深入研究；quant-runner 用于实盘。基础筛选回测不要求先移入 Lab，不能自动把研究意向升级为实盘权限。
- quant-data 是助手云端共享数据湖，保留采集原件和研究结果，避免依赖用户本地电脑；不把机器路径写死为产品身份。
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
- 用户指定的 `metadata/strategies/`、`metadata/factors/` 保存经审查的逐编号元数据、来源链接和自撰规则；不复制来源全文、原始行情或历史私有材料。旧编号和实体类型分别保留；导入覆盖层须绑定现有实体的精确版本，不改原定义或个人批注。
- 公开发布先运行 build-public、verify-public 和 tests/test_public.py；完整私有数据仍运行 validate-release。
