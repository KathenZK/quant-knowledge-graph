# Private corpus research evidence

The Personal Workbench now has a **研究证据** page at `/results`. It reuses the
existing loopback-only application and visual language. It is a read-only view
of retained strategy screens, not a research engine or a trading interface.
The public web app does not mount the new endpoints and receives no private
records, numerical derivatives, audit details or collection counts.

## What can be inspected

- Coverage across **all source records**, including missing-data, ambiguous and
  unimplemented cases. These statuses do not prove a strategy is ineffective.
- Separate source-record, tested-record and implementation counts. Method/family
  grouping is an implementation classification, not an independence claim.
- Every source record, including untested records, exposes its original rule,
  source link and selective audit through a separate read-only detail view.
- Each implementation's original rule excerpt, explicit parameters, standardized
  execution conventions, supplemental assumptions and selective source audit.
- Original development, validation, retrospective holdout and later descriptive
  metrics, three retained benchmark comparisons, and cost scenarios.
- Net-equity and drawdown curves derived from retained daily net returns. All
  curve calculations precede display sampling; endpoints are retained. Global equity extrema and the worst drawdown are also retained. Curves
  show the complete retained series and do not follow the metric-period selector.
  Missing benchmark daily returns are not reconstructed from summary metrics.
- Immutable run, corpus, protocol, implementation and market lineage. Imported
  artifact bytes are independently digest-checked; other source hashes remain
  producer declarations and are clearly distinguished.

Existing Catalog entries and old journal results remain in place. A source-native
ID can link a Catalog entry to a screen record. Such a link is **reference only**;
it does not claim the Catalog definition revision equals the tested implementation.
Absent or ambiguous matches remain explicit rather than guessing a definition.
The research page also works when only a research collection has been imported;
other knowledge pages still require the existing full Catalog.

## Private import contract

`private-strategy-screen-collection/v1` pins nine fixed-name files:

- Results directory: `run_manifest.json`, `run_summary.json`,
  `strategy_metrics.json`, `implemented_specs.json`, `all_record_coverage.csv`,
  `daily_returns.csv.gz`, `deep_validation.json`
- Audit directory: `record_audit.jsonl`, `source_verification.json`

These files are private inputs, never repository fixtures. Use synthetic examples
for tests. Do not put actual rules, source text, market data, derived results,
operator paths or credentials into a Git commit.

This contract intentionally does not submit `factor-study-result/v1` or fabricate
`LAB_REPRODUCED` evidence. Existing FactorStudy and B-discovery import workflows
keep their independent contracts and permissions.

### Prepare, review and import

After installing the existing project dependencies, run from the Graph checkout:

```sh
.venv/bin/python -m quantgraph.graph.corpus_research build-manifest \
  --results-dir /authorized/private/results \
  --audit-dir /authorized/private/audit \
  --output /authorized/private/import-manifest.json
```

Inspect the files and the returned SHA-256 digest. Preparation fixes byte hashes;
it does not approve source/data rights or independently certify a backtest.
Import only the expected private artifact set and supply the reviewed digest:

```sh
.venv/bin/python -m quantgraph.graph.corpus_research import \
  --runtime .artifacts/personal \
  --manifest /authorized/private/import-manifest.json \
  --sha256 REVIEWED_SHA256 \
  --results-dir /authorized/private/results \
  --audit-dir /authorized/private/audit
bash scripts/start_personal.sh .artifacts/personal
```

Open `http://127.0.0.1:8791/results`. Never reverse-proxy this personal port to the
public internet. Local access does not resolve any source or data licensing
uncertainty. Public display requires its own reviewed rights and projection.

The importer validates all input hashes before writes, reconciles record/run/
implementation identities and counts, and uses a single SQLite transaction.
Replaying the identical manifest is idempotent. A different payload for an
existing run is rejected; create a new run to retain corrected evidence. No
research jobs are created, and no compute budget is consumed. The new private
`corpus-research.sqlite` is included by the existing runtime-copy backup helper.
The raw source files and manifests still need their own immutable backups.

## API and UI boundaries

Only `api/personal_app.py` installs these GET endpoints:

- `/v1/personal/corpus-research?run_id=...`
- `/v1/personal/corpus-research/records?run_id=...&q=...&status=...&family=...&page=1&page_size=20`
- `/v1/personal/corpus-research/records/{record_id}?run_id=...`
- `/v1/personal/corpus-research/implementations/{variant_id}?run_id=...`

Lists are paginated; implementation metrics and curves are loaded on demand.
There are no HTTP import, file-path, artifact-download or execution endpoints.
The existing loopback, Host, Origin, cross-site and no-store protections apply.
Public mode never gains a switch to read these private files.

## Checks

```sh
.venv/bin/python -m pytest tests/test_corpus_research.py tests/test_personal_app.py tests/test_personal_research.py tests/test_public.py -q
npm --prefix web run typecheck
npm --prefix web run lint
npm --prefix web test
npm --prefix web run build
npm --prefix web run e2e
```

Browser verification should cover empty import, source-ID search, all coverage
statuses, family filtering, pagination, open/close and browser Back/Forward,
multiple implementations per source, missing metrics, period selection, cost
scenarios, net-equity/drawdown, narrow screens and public/private separation.
Full private `validate-release` remains dependent on the original locked inputs;
a public checkout must not report it passed without them.

## Independent delta runs and fidelity (v2)

An incremental run must contain only its own executed results. A cumulative
coverage spreadsheet is a producer statement, not permission to relabel earlier
experiments with the latest run ID or protocol hash. The v2 metadata-only adapter
builds a new private export from one frozen delta directory:

```sh
.venv/bin/python -m quantgraph.graph.corpus_export \
  --origin-dir /authorized/private/one-frozen-run \
  --protocol /authorized/private/the-original-protocol.json \
  --audit-dir /authorized/private/audit \
  --destination /authorized/private/new-graph-export
# Optional: --annotations /authorized/private/reviewed-annotations.json
```

It verifies the original manifest's declared output hashes and original protocol,
retains all nine producer files and that protocol byte-for-byte, and derives the
seven Graph result files without executing a strategy. The audit files are copied
unchanged. A separate operator-annotations file is also pinned (empty by default),
so `private-strategy-screen-collection/v2` contains twenty declared artifacts.
The returned manifest digest must still be reviewed before the existing import
command is used. Pass the export directory as both `--results-dir` and
`--audit-dir`; never overwrite an earlier export or run.

The importer deterministically re-derives v2 projections from the retained origin
bytes. Re-pinning an edited result does not let it diverge from its original
metrics. Original run ID, protocol hash, source manifest hash, source specification
hash and derivative specification hash remain separate. Metadata enrichment is
explicitly marked `recomputed: false`. Missing source amendment/acquisition
manifests are not invented. Producer market/code hashes remain declarations;
this adapter does not independently reproduce those upstream files.

Each result has a fidelity class and original run identity:

- `STANDARDIZED`: standardized source-rule implementation, without a declared
  asset proxy or parameter/sizing hypothesis; not source-exact certification
- `PROXY`: explicitly substituted asset/data representation
- `HYPOTHESIS`: explicitly changed or unresolved parameter, sizing or rule
- `PROXY_HYPOTHESIS`: both kinds of deviation, with both reasons retained

Coverage uses `tested`, `tested_proxy_only`, `tested_hypothesis_only` or
`tested_mixed` according to the actual result classes for that source record.
Unknown classifications, missing deviation reasons, empty completed runs and
mixed-origin results are rejected. Unexecuted source records retain this run's
actual data/error status, or `not_evaluated_in_this_run`. They do not inherit a
previous run's completion status.

The optional annotation format is `strategy-screen-annotations/v1`, with the
specific `run_id` and an `implementations` map keyed by original variant ID.
Allowed annotations are `additional_hypothesis_reason` and
`deep_validation_scope: FIXED_ORDER_PATH_DELAY`. They add reviewed limitations,
not new source facts or calculations. The latter explicitly warns that a saved
order path was delayed without rerunning price-dependent entry/exit decisions;
it must not be presented as a complete execution revalidation.

The workbench counts fidelity classes separately. Its aggregate coverage uses
only runs with the identical corpus digest and exact source-ID universe, counts
each covered source record once, and never adds class-specific record counts
(the sets may overlap). Record details link each related experiment to its own
run and protocol. Original artifacts and per-run statuses are unchanged. A
newer or larger corpus is a separate scope, even if many native IDs overlap.
Metric period choices and observation boundaries come from the retained run;
there are no fixed market or calendar-year assumptions in the new adapter.

After an origin run is imported, changing its annotations or projection is a
conflict, not a new execution. This version deliberately rejects such rewrites.
Do not invent a new run ID to bypass that guard. Corrections to an already
published/imported run need a separately designed, linked assessment-revision
contract; until then retain the original evidence and the correction separately.
