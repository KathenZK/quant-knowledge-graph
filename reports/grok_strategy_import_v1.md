# GrokBot Strategy Corpus V1 import audit

Aggregate-only report. Complete rules, source lists and legacy results remain private.

| Measure | Count |
|---|---:|
| raw_records | 5813 |
| normalized_records | 5813 |
| candidate_variants | 5813 |
| strategy_concepts_families | 14 |
| templates | 20 |
| curated_variants | 75 |
| unclassified_records | 5722 |
| factor_linked | 75 |
| parse_success | 75 |
| parse_failure | 5738 |
| executable | 0 |
| execution_review_required | 5813 |
| rights_review_required | 5813 |
| exact_duplicate_groups | 0 |
| legacy_screens | 30 |
| legacy_screens_curated | 19 |
| legacy_screens_unmatched | 0 |
| public_corpus_records | 0 |

## provenance_distribution

```json
{
  "ASSET_VARIANT": 0,
  "BOT_DERIVED": 345,
  "MARKET_VARIANT": 0,
  "PARAMETER_VARIANT": 0,
  "SOURCE_DERIVED": 0,
  "SOURCE_IMPLEMENTATION": 744,
  "SOURCE_NATIVE": 0,
  "UNKNOWN": 4724
}
```

## variation_axes

```json
{
  "ASSET_VARIANT": 35,
  "PARAMETER_VARIANT": 47
}
```

## source_url_statistics

```json
{
  "invalid_records": 0,
  "normalized_unique": 4035,
  "raw_unique": 4035,
  "records_in_shared_sources": 2313,
  "shared_source_groups": 535,
  "source_buckets": 4035
}
```

## license_distribution

```json
{
  "UNKNOWN": 5813
}
```

## rights_distribution

```json
{
  "REVIEW_REQUIRED": 5813
}
```

## attribution_distribution

```json
{
  "RULE_LINK_ONLY": 75
}
```

## Scope and limitations

- Candidate records are not independent strategies.
- Families use supported parsed methods or explicit RSI/Absolute Momentum citation families; unresolved source buckets are not families.
- Shared URLs and exact-text candidates do not establish strategy equivalence.
- All three dates remain null until independent evidence distinguishes their meaning.
- Source pages and original authorship have not been independently verified.
- Parsed syntax is not executable: timing, adjustments, indicator semantics, costs and missing-data policies need review.
- All records require rights review; private curation does not grant use or redistribution rights.
- Legacy screens preserve reported proxy rules and data caveats, not lab reproduction or factor attribution.

## Reproduction

Input archive SHA-256: `c9d6e7de6e876fcd75678085aebe5c88e94a4d8932a39565a5cad96fa0418954`.
Raw CSV SHA-256: `d21bec27800cbd573382a45de5b0ad9f9f653041c51dd88c814e56cd32d486a8`.

`uv run quantgraph import-grokbot /private/path/input.tar.gz`
`uv run quantgraph verify-grokbot`

The importer checks record conservation, raw bytes, typed models, graph references and commercial isolation.
Only this Markdown and its aggregate JSON are public; neither file is evidence of strategy profitability.
