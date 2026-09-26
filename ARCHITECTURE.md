# Architecture

`quant-knowledge-graph → quant-research-lab → quant-runner`

This repository owns definitions, citations, relationships and research artifact references. The research project owns reproduction, data/cost contracts, statistical validation and promotion decisions. The runner owns execution and risk controls. The knowledge graph has no runner publishing interface and imports no research engine.

## Existing factor pipeline

Pinned source files → collectors → normalized source records → definition admission → immutable curated graph. The public Qlib cohort and default commercial API remain isolated from mixed-license research inputs. Existing IDs, SDK queries and old SQLite releases remain readable.

## GrokBot Strategy Corpus V1

```text
user-supplied tar.gz
  → raw/sources/grokbot/<archive SHA-256>/input.tar.gz (original bytes)
  → normalized/grokbot/<archive SHA-256>/<importer hash>/
      records.jsonl          # every CSV record + untouched rule text + typed variant
      source_groups.json     # shared citations; NOT strategy equivalence
      legacy_screens.jsonl   # all matched legacy results, including review candidates
      unmatched_screens.json / review_queue.json
  → curated/grokbot/releases/<release ID>/
      strategies + strategy_concepts + strategy_templates + strategy_variants
      sources + licenses + rule-reference factors + strategy_factor
      backtest_results + typed relationships
      JSONL / CSV / Parquet / SQLite + manifests
      commercial/            # empty: no corpus rights have been cleared
  → curated/grokbot/CURRENT  # switches only after verification
```

The separate corpus pointer does not replace `curated/current` or `public/CURRENT`. Consumers must explicitly open the private corpus database. Default SDK/API access continues to use the existing factor release. All normalized records are retained; only supported syntax with usable source and market metadata enters the private definition graph. Unknown syntax stays in normalized with `REVIEW`, `rule_ast=null` and an explicit reason.

A family groups a reported method. A template retains signal/operator/schedule while replacing numeric parameters and asset choices with slots. A variant retains the actual rule, native ID and specification hash. `Strategy` is the backward-compatible projection used by existing SDK queries. `StrategyVariant → VARIANT_OF → StrategyTemplate → VARIANT_OF → StrategyConcept` is distinct from source citation and derivation edges. RSI/Absolute Momentum citations can establish a reported family bucket even when their particular rule cannot be parsed. None of these groupings establishes economic independence or formula equivalence.

## Separate evidence gates

- Provenance distinguishes `SOURCE_NATIVE`, `SOURCE_IMPLEMENTATION`, `SOURCE_DERIVED`, `BOT_DERIVED`, `PARAMETER_VARIANT`, `MARKET_VARIANT`, `ASSET_VARIANT`, and `UNKNOWN`. A URL to code is an **unverified implementation reference**, not proof of original authorship. Unknown source relationships stay unknown. Parameter/asset/market variation axes supplement primary provenance and never erase `BOT_DERIVED`.
- StockCharts/Fidelity indicator definitions applied to generated ETF switching rules are `BOT_DERIVED`; Antonacci framework-based asset variants receive the same conservative treatment. The cited author is not credited with inventing those generated trading variants.
- `concept_origin_date`, `source_publication_date`, and `variant_created_at` remain null without independent evidence. The input's `提出日期` is preserved separately as `raw_proposed_date`. Import time is never substituted for historical creation time.
- The closed parser supports explicit daily/month-end threshold switches, RSI and a bounded indicator set, price versus SMA/EMA/WMA, moving-average comparisons, absolute momentum versus a named safe asset, and two-ETF relative-momentum rotation. It requires complete supported syntax or a recognized narrative envelope. Compound conditions, crossovers, unknown operators, additional exits and ambiguous rules require review. No uploaded code is executed.
- `PARSED` means syntax only. Missing indicator smoothing, signal asset, price adjustment, execution time, tie/missing-data handling, allocation or costs remain null. Every variant has `executable=false`; research must supply and validate a complete execution contract.
- StrategyFactor points to **new GrokBot rule-reference signal entities**, not speculative equivalence to Qlib features. All links are `RULE_LINK_ONLY`, with no attribution backtest reference. Ordinary performance numbers do not establish factor attribution.
- All 30 supplied legacy screens are retained in normalized, with their original proxy rules, cost/data notes and reported metrics. Only screens whose parent strategy passes definition admission enter curated. `LEGACY_GROKBOT_SCREEN` cannot support empirical attribution; no test is reproduced here. The legacy safe-asset zero-return caveat is retained.
- Rights default to `REVIEW_REQUIRED` across all corpus records. Private definition curation is not a commercial-use or redistribution grant. Complete raw/normalized/curated data stays ignored by Git. Public output consists only of implementation, synthetic tests and allowlisted aggregate reports.

## Verification and repeatability

Native IDs are checked for uniqueness. Archive members are size-bounded; links, traversal and duplicate members are rejected. The complete original archive is content-addressed, never rewritten and never executed. A separate import lock prevents concurrent publications. Release manifests cover all graph exports; normalized manifests pin the input-to-output projection. `verify-grokbot` replays normalization and curation, checks every record and typed graph row, foreign keys, export agreement, raw checksums and an empty commercial subgraph.

The public-tree check only permits the exact JSON aggregate schema and its generated Markdown projection. Free-form corpus text and source lists cannot be added to these report exceptions. Full private factor `validate-release` and public Qlib rebuild tests remain independent of corpus import.

## Incremental ingestion boundary

`api/ingestion.py` → `IngestionRepository` → private append-only submissions/revisions/observations/projections。
SQLite 是默认 adapter；normalized projection 复用原严格 parser 与 provenance，
rights 一律独立待审。HTTP SDK 位于 `sdk/quantgraph/client.py`。
研究层通过 scope 受控接口读取候选、提交不可变 ResearchEvidence；证据写回不修改
StrategyFactor 归因状态、不触发晋级。公共 profile 与私有 journal 没有自动合并路径。
详见 [接口和部署](docs/INGESTION.md)。
