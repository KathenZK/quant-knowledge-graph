# 公式 AST / DSL v1

所有公式型来源同时保留：

- `formula`：采集文件的原始表达式，或 French 数学摘要的独立转录。
- `formula_ast`：JSON 语法树，用于机器读取。
- `normalized_formula`：语法树的前缀文本显示。
- `formula_hash`：方言与语法树的 SHA-256。
- `parameters.numeric_literals`：原式常数，不把所有数字错误地解释成窗口。
- `implementations.python_ast`：另一代码实现的完整函数语法树。

## 输入语法

支持字段、常数、函数、括号、算术、幂运算、比较、布尔及三元条件。解析器位于 `normalize/formula/parser.py`，不调用 eval 执行公式。字段大小写在同一方言内统一，空白和 `5`/`5.0` 合并，小数窗口原样保留。不会自动补参数、补括号、修改方向、展开任意窗口或假定缺失数据为零。

输入 `Ref($close, 5)/$close` 得到：

```json
{"type":"binary","op":"/","args":[{"type":"call","op":"qlib:delay","args":[{"type":"field","name":"close"},{"type":"number","value":"5"}]},{"type":"field","name":"close"}]}
```

显示 DSL 为 `/ (qlib:delay($close,5),$close)`（实际输出省略 `/` 后的空格）。JSON AST 是执行适配器应消费的结构。文本 DSL 是显示格式，当前 CLI 不提供该前缀格式的反向解析器。

## 算子方言不能混用

- Qlib `Rank(x,n)` 是窗口内时序秩。
- WQ/GTJA `rank(x)` / `RANK(x)` 是截面秩。
- Qlib `Greater/Less` 是逐元素最大/最小。
- GTJA `SMA(x,n,m)` 是递推平滑，不能等同于简单移动平均。
- WQ 的小数 lookback、行业中性化和 scale 的缺省参数均需后续明确约定。

这些差异保留在 op 前缀中。`datasets/normalized/operators.*` 收录实际使用的算子。参数数量检查属于保守候选检查，不能代替完整原始算子定义；尤其回归函数可能有不同签名。

## 解析成功仍可能不能计算

例如 `DELAY(CLOSE)` 可以组成合法语法树，但缺少明确滞后参数；`MAX(SUMAC(...))` 的实现语义有歧义。此类记录会产生 `OPERATOR_ARITY_REVIEW` 或待确认项，检查上游默认值/重载之后才能判定是否错误。两个 GTJA 实现函数只有空实现，已标记 `stub`。源码中注释掉的公式仍保留，带 `UPSTREAM_FORMULA_DISABLED`。

`backtest_ready` 当前全部为 false。后续引擎必须固定：时序/截面维度、NaN 和最小样本数、标准差自由度、rank 并列值处理、价格复权、单位、VWAP、行业分类时间、窗口取整、交易日历及信号可得时间。必须使用已收盘数据并明确执行延迟。

JKP 的 LaTeX 与 OSAP 的长文本定义保留原文；当前不把它们机械转成看似完整但无法复现的执行公式。

## QuantGraph 输入跨度

`normalize/formula/lookback.py` 对支持的 Qlib AST 计算最小输入观察数，例如 Ref(close,5)/close 需要包含当前值的 6 个观察，Mean(close,5) 需要 5 个。嵌套窗口累积跨度，不把所有数字或特征名后缀都当成窗口。未知算子、负滞后、小数窗口和 expanding window 返回 null。该结果不是持仓期，也未替代运行时数值验收。

公式 hash 保留原迁移身份。corr/std/cs_rank 等规范名可由后续 adapter 映射到 correlation/stddev/rank，但方言不得丢失；本版本不执行公式。
