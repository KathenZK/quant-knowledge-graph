# 公开仓库与本地研究维护

## 公开仓库

公开仓库只带 Qlib 已筛选资料。运行 `quantgraph build-public` 和 `quantgraph verify-public`；GitHub CI 运行公开批次和公式测试。`quantgraph build` / `validate-release` 需要完整私有研究快照，不能在只有公开文件的 clone 中执行。

不要把 datasets/curated、normalized、非 Qlib 原始材料或本机日志加入 Git。原始来源索引中的 URL 和 hash 不代表相应资料已经随仓库分发。

下面保留完整本地研究工作流，供有相应合法来源的维护者使用。

## 完整本地研究工作流

## 日常入口

本仓库接替旧 Documents 目录中的 global-factor-library。旧目录只保留历史快照，不继续分叉维护。`reports/migration.json` 保存任务 ID、路径、原锁摘要以及 1,578 条记录逐字段相同的迁移核验。

```sh
uv sync --frozen --extra test
uv run quantgraph verify
uv run quantgraph validate-release
```

冻结来源只需离线重建。不要为“每天更新”重复下载同一版本，也不要把网站当前宣传数量当成采集数量。

## 恢复与重采冻结源

```sh
uv run quantgraph fetch
uv run python scripts/harvest_sources.py --source qlib --destination /tmp/new-qlib-snapshot
```

fetch 只恢复 source_lock 中授权且有固定 hash 的内容；metadata_only 来源缺失时拒绝重新下载正文。采集脚本写新目录并校验不可变版本摘要，失败非零退出；它不是自动 latest 更新器。

## 新版本审核

1. 选择一手来源的新 revision；检查许可证和内容范围是否变化。
2. 新增 raw 快照，记录 URL、retrieved_at、revision、sha256、字节数及 storage_policy。原始字节不修补。
3. 比较名称、原始公式、参数、代码、许可差异；记录原生 ID 的更名、撤回和替代。不得通过更新源数据消除历史问题。
4. 更新采集器/源码锁的引用；对新增算子、跨源合并、公式变更添加针对性验收。
5. 运行 build、verify、validate-release。检查 normalized 的准入决定、问题队列以及 curated 人工抽样。
6. 保存新发布；重启 API 读取新版本。下游研究记录 release ID、variant ID、公式与合约摘要。

`models/id_registry.json` 只追加，不能排序后重发编号。数据发布以内容摘要命名；current 通过原子 symlink 切换。构建锁避免同时写入。进程崩溃留下 `datasets/.publish.lock` 时，先确认没有构建进程，再移除空锁目录。

构建中 normalized 是工作层，可能反映尚未发布的候选。对外消费只读取已校验的 curated/current。发布目录不可修改；回退应切换 current 到已验证的旧 release，不覆写旧文件。

## 商业产品出口

`quantgraph export-commercial <新目录>` 先验收发布，再只复制 commercial 子图及归属声明。禁止直接打包 datasets/ 作为不受限商业数据产品。research profile 包含非商业及有条件素材，不能因为用途叫研究就忽略商业内部使用限制。

当前服务只监听 localhost，没有认证、计费、流量限制或公网托管。公网产品阶段应先确定授权内容、客户范围和认证机制，再部署；本次没有部署。

## 下一阶段门槛

- 优先核对 Alpha101/191 官方原式与实现差异，处理 163 组重复候选。
- 补足 OSAP 原始论文标题/DOI，以及 JKP 引文缺口；保留匹配证据。
- 明确算子的缺失值、rank 并列、样本最小数、窗口取整、披露滞后等计算语义。
- 将 Factor 层的准入/版本规则冻结后，导入策略描述和研究结果引用。历史研究代码留在研究项目。
