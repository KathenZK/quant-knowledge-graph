# Readable knowledge and retained results

The personal strategy and factor detail pages are the reading entry point. Strategy explanations show purpose, assets and entry/exit conditions, then paper/economic evidence. Missing source information remains explicit. A paper bibliography link, a platform reference, a reviewed definition and an empirical result are distinct relationships.

The primary research navigation item is removed. Retained strategy experiments are selected inside their source record's detail and the existing comparison table. Selection is keyed by `(origin_run_id, variant_id)`. Old `/results` links resolve the native source ID and redirect to an existing strategy detail when possible; unresolved historical links retain a readable fallback. Source-native references do not establish Catalog definition equivalence. Factor results remain separately bound to factor definition versions.

## Private source-review cards

`python -m quantgraph.graph.private_intake --catalog PRIVATE_CATALOG --input CARD_FILE --sha256 REVIEWED_SHA256 --kind factor|strategy` imports an explicitly chosen private snapshot. It accepts a bounded strict JSON array, checks the digest and types before mutation, preserves supplied admission and evidence states, and reports inserted/updated/unchanged entries. It never executes downloaded code or creates a research result.

An old-corpus source review with an explicit native-record relationship is appended to `private_intake_reviews`; it does not replace the original rule, definition revision or stored raw record. New candidates remain private. Signal components, research models and development examples carry explicit type labels and must not be counted as confirmed independent trading strategies. Repeating a snapshot is idempotent.

Keep actual cards, private databases, research snapshots, logs and Site data out of the public repository. Tests use synthetic records. The static private Site exports the same reading projection and original page components; only the read-only API and browser-local note adapter differ from the local service.

## Verification boundaries

Component tests check navigation, old-link redirects, origin-scoped result selection and missing evidence. Python tests check strict imports, isolation, idempotence, unchanged source definitions and non-upgrading evidence states. These tests are not live browser visual verification and do not establish strategy profitability.

Public Qlib verification/build remain separate from full private `validate-release`, which requires the original mixed-source private bundle. A missing private bundle must be reported rather than replacing it with the public-only subset.
