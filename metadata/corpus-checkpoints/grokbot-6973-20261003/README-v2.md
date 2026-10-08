# 旧6973条完整字段：v2独占输出合同

本合同替代旧hash-only执行路线；旧合同、旧计划和旧检查点保持原字节，只作审计。
唯一执行写者为dot，唯一全局进度与集成写者为root。

固定工具主分支提交为 `4576f6a3da08c45822cfc5cfcd5422aea5bbc970`，实现提交为 `f0b99c57cb959d989d0a52ac6c980589584ea5af`。
具体文件hash、唯一输出路径和公开边界见 [OUTPUT-CONTRACT-v2.json](OUTPUT-CONTRACT-v2.json)，命令见 [BATCH_IMPORT.md](../../BATCH_IMPORT.md)。

1. 对dot实际持有的原CSV核验6470637字节和既定SHA，创建新的plan-v2。6973个原ID、46缺口不得改动。
2. stage首批100条时带原CSV再次核对；每条来源记录完整保留11字段，未知类型仍UNREVIEWED，来源层不增加ID或运行数。
3. 私有Library保存完整批次压缩包及独立清单，读回后仅以该批次执行restore；逐11字段和原行hash验收，再验证无CSV重建的全部文件hash。
4. 首批远端恢复验收后才扩批。公开审查通过且无private-only条目的stage可原样保存到本分支的 `batches/batch-0001-v2/`；读回每个文件再报告。
5. 敏感条目保持完整私有值，混合批次不公开、不裁字段、不虚报公开完整。后续安全批次可按合同推进，单批/全库进度分别报告私有完整保存与公开验收。

本合同不证明真实CSV已在root执行；工具的679项测试和100条合成恢复通过。真实首批验收由dot执行。
禁止修改工具、顶层metadata索引/来源/策略/因子文件、其他ID、Site或全局进度。不得覆盖旧证据、force push或把Library引用写入公共Git。
