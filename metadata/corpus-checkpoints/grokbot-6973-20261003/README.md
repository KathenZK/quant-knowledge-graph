# 旧6973条：dot独占批次输出

唯一写者是 `dot persist_grok_metadata_records`。分支 `dot/grok6973-checkpoints-20261003`，原始基底 `68d1d584b7e50b13f8118460b1f75737844091b3`；工具固定 `a063616399acc298e334bd8e07cf4820d24e3d95`，见[运行说明](../../BATCH_IMPORT.md)和[输出合同](OUTPUT-CONTRACT.json)。本分支初始内容只是任务合同，未计任何真实接收记录。

私有执行：先对已核主表执行plan，再stage首批100条并重建比较所有文件hash；私有Library保存压缩包及独立清单，恢复验证后扩批。字段审查后的stage目录原样复制到 `batches/batch-0001-v1/`，其后逐批追加；原stage内manifest和metadata相对路径不变。任何不安全字段使该批保留私有并报告，不能改字节冒充工具输出。

先提交首批、核验远端读回并通知协调者；后续最多提前准备2批，不把未启动/未保存算完成。禁止改工具、顶层metadata索引/策略因子文件、Site或任何其他目录，禁止force push、删除或覆盖旧检查点。规划和完成回执只写合同允许的新文件。全局计数与PR合并由root负责。

所有6973原ID必须留存，46缺口不补号。无权威类型者为UNREVIEWED库存记录；此种保存不等于strategies/factors已分类覆盖。规则、日期、可回测性和来源链接保留未核状态，绝不据此生成新回测或晋级。
