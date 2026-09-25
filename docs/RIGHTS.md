# 内容、许可与商业边界

审阅日期：2026-09-25。以下是本项目对实际采集内容的权限分类与使用范围，不扩张上游授权。记录级字段比统一包名称更重要。

| 来源 | 已保存的内容 | 许可依据 | 商业导出状态 |
|---|---|---|---|
| Microsoft Qlib | MIT 源文件、展开的表达式与语法树 | 官方仓库 LICENSE | 可在保留声明等条件下使用；市场数据权利另行解决 |
| Open Source Asset Pricing | SignalDoc、Python 源码、来源元数据 | 仓库 GPL-2.0 | 有条件；分发衍生代码需遵守 GPL，不能用本项目 MIT 声明覆盖 |
| JKP | 定义文档、参考对照、引文；MIT 代码单独保存 | MIT 与 DATA_LICENSE 分离；参考内容保守按 CC BY-NC 4.0 | 排除商用导出；商业用途需另行授权 |
| WorldQuant Alpha101 | MIT 社区转录版本及 ta_cn 函数 | 两个社区仓库 LICENSE；论文 arXiv 许可另列 | 上游公式权利待核，不纳入商用白名单 |
| GTJA Alpha191 | MIT 社区转录版本及 ta_cn 函数 | 社区仓库 LICENSE；未核实官方原研报授权 | 上游权利待核，不纳入商用白名单 |
| Kenneth French | 书目信息、检索链接和独立数学摘要 | 官网页脚版权声明，无明确开放再分发许可确认 | 排除自动商用导出；未下载收益序列 |
| AQR | 数据集名称、引用与链接 | Terms of Use 的 Copyright and Trademarks | 仅元数据，不复制正文、公式或收益数据 |

## 核验链接

- [Qlib LICENSE](https://github.com/microsoft/qlib/blob/be725493eb1a6bbb42bf11b37aa7669f59610ff1/LICENSE)
- [OSAP LICENSE](https://github.com/OpenSourceAP/CrossSection/blob/8db892442c2c3a3779b0f1eac4370d3655be15a1/LICENSE)
- [JKP DATA_LICENSE](https://github.com/bkelly-lab/jkp-data/blob/666e8960ed81a664f1e9f189f92925ab2eeffcd5/DATA_LICENSE)
- [JKP 数据页面](https://jkpfactors.com/data)
- [AQR Terms of Use](https://www.aqr.com/Terms-of-Use)
- [Kenneth French Data Library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html)
- [WorldQuant 论文及 arXiv 许可入口](https://arxiv.org/abs/1601.00991v3)
- [alpha_examples LICENSE](https://github.com/wukan1986/alpha_examples/blob/0cd963d8780a3ad816dd5940fc4bc3f5e78ed09e/LICENSE)
- [ta_cn LICENSE](https://github.com/wukan1986/ta_cn/blob/a569a618109daa804541c5d67fa4c0407f03fd49/LICENSE)

## 保存范围

没有取得 WRDS、CRSP、Compustat、IBES 的观测数据；代码中的字段名和公式不代表取得底层数据许可。没有复制 AQR 和 French 收益序列，也没有把 WorldQuant PDF 或 GTJA 研报全文装入数据包。

网站只保留元数据快照、HTTP 状态、原响应摘要和访问时间，不随包传播完整 HTML。GitHub 只取公开、固定版本、附有许可的目标文件，source_lock 可逐一追踪。

研究参考数据包保留 JKP 的非商业限制，不能因为这些记录进入统一 schema、被去重或转换为 Parquet 就消除限制。商业 API 应从记录级许可白名单导出；不得把整个 research 包作为无条件可售的数据产品。

## 归属声明与修改

第三方原始文件位于 `datasets/raw/sources/<source>/`，保持原字节并附 LICENSE。生成的数据做了字段选择、格式转换、别名归一化、公式语法解析、关系标注和质量标注。第三方作者及原始引用保留在记录和源文件中。无任何上游作者背书的含义。

JKP 引用：Jensen, Theis Ingerslev; Kelly, Bryan T.; Pedersen, Lasse Heje (2023), “Is There a Replication Crisis in Finance?”, Journal of Finance, DOI 10.1111/jofi.13249。

OSAP 引用：Chen, Andrew Y.; Zimmermann, Tom (2022), “Open Source Cross-Sectional Asset Pricing”, Critical Finance Review 11(2), 207–264。源项目也保留 2021 工作论文标识。

## QuantGraph v0.2 出口

新项目不默认开源或授权销售整个仓库，见根 LICENSE。迁入的 MIT 自写采集组件保留原声明。

记录使用 ALLOWED / CONDITIONAL / PROHIBITED / REVIEW_REQUIRED 四态；OSAP 条件许可仍要求商业方案复核，JKP 已知禁止商业用途。raw_data_allowed 针对底层市场观测始终未获授权，不用代码许可证推定数据许可。

commercial 子图目前仅保留 508 个通过定义准入的 Qlib 变体，连来源、论文、别名、实现和关系都单独过滤；导出附完整 MIT 声明。
