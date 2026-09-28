# 研究仓库命名迁移（2026-09-28）

`quant-knowledge-graph → quant-research-lab → quant-runner`

研究仓库从 `KathenZK/quant-strategy-lab` 原地更名为 [KathenZK/quant-research-lab](https://github.com/KathenZK/quant-research-lab)。旧 URL 用作历史兼容入口，现有 commit、PR 和证据 hash 不改写。知识仓库名称不变，研究代码仍在独立研究仓库；本轮不修改运行仓库。

Repository / distribution 为 `quant-research-lab`；Python package/import 仍为 `strategy_lab`。新 ResearchEvidence、Implementation 和外部 metadata 的 repository identity / URI 使用新名，历史 evidence 内容和 hash 原样保留，不把历史证据重新发布成新证据。

以下审核记录使用当时的旧仓库名称和链接，作为历史 provenance 原字节保留：

- `docs/audits/quant-platform-audit-2026-09-26.md`
- `docs/audits/quant-platform-v4-baseline.md`

研究端 v2 制品 schema 接受新 producer 和旧名兼容别名；知识层的证据 API 不通过仓库改名改变准入、许可、执行合同或审批结果。运行端未在本轮修改或验证，不宣称其接受新 producer。

本机正式研究路径为 `~/OpenCode/quant-research-lab`；旧 `~/OpenCode/quant-strategy-lab` 暂留为兼容符号链接。Git linked worktree 指向已修复。并行任务应使用新目录，已有旧路径仍可访问。

打开仓库根部的 [quant-platform.code-workspace](../quant-platform.code-workspace) 可使用同级的三个仓库；本机另有 `~/OpenCode/Quant Platform.code-workspace`。该文件只列出 folder，不读取或修改运行配置。

Codex 原生项目注册未更新：工具没有 folder registration 修改接口，Computer Use 明确禁止操作 Codex 自身界面。这里按本任务允许的降级方式交付 workspace 和文档，没有修改内部数据库。可在“编辑项目”中将旧研究 folder 替换为新目录；已有聊天记录不重写。官方操作入口见 [Projects and chats](https://learn.chatgpt.com/docs/projects)。
