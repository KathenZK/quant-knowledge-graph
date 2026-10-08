# Research scope, executions and conclusions

QuantGraph organizes research inputs, screening results and owner annotations. The catalog definition, the worklist, an execution, a data-quality assessment and a human interpretation have separate versions. None alone certifies an investable strategy.

- `research_universe` imports a hash-pinned worklist and binds each row to a catalog entity and definition revision. Legacy record types can remain pending. Components and development fixtures stay visible and are counted separately from strategy families.
- `research_views` counts only executions with matching retained rule definitions. Historical run denominators are preserved. A newer full worklist does not rewrite an older run.
- `research_interpretations` pins authored conclusions to the declared historical worklist, original run manifest, original metrics/specification files, assessment revision and Graph import manifest. The original and import manifests are different hashes. Referenced period, cost, delay and window fields are compared with retained original metrics; this is not a new numerical backtest or a factual review of every sentence.
- `research_data_quality` accepts restrictive, version-bound flags. It verifies the original run, metric artifact and instrument input-series hash. Such an overlay cannot certify data or change returns. Unavailable annotations are shown as unavailable, not as a pass.

The existing strategy/component details contain the conclusions. The existing comparison page retains origin/run/variant/import-manifest identity. Fund-vehicle proxies remain distinct from point-in-time constituent-method reproductions. Native data windows are independent and do not interpolate gaps. Model capital extinction and end-of-sample forced closure remain distinct from exchange margin liquidation.

## Explicit private refresh

Use `scripts/export_research_site.py` with a verified runtime and ordered baseline asset roots. It refuses a pre-existing export destination and checks old implementation display bytes under their immutable identities. New catalog details are published in bounded preparatory batches; the last atomic activation updates the visible catalog and research indexes. Relationship and worklist assets are split at known record boundaries. An incomplete object upload never activates a batch.

`site_sync.py` uploads registered objects with bounded bulk requests or the existing single-object path. Both paths verify receipts. Authentication, owner-private deployment, immutable references and activation checks are unchanged. The script is an explicit operation; it does not create a background polling process or store a credential.

Owner feedback remains authoritative in Sites. Durable receiving, acknowledgement and versioned research interpretation are separate actions. Source material and feedback text are untrusted content and do not themselves authorize external actions.
