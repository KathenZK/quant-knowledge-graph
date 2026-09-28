# Integrated local platform delivery

The delivery consists of two independent Git repositories. Merge the Lab integration PR #17 first, then Graph #12; the Graph cross-repository CI pins the exact Lab commit. These integration PRs include the A/B implementation commits. Do not merge duplicate A/B branches separately. No main branch, runner or trading deployment is changed.

## Start and acceptance

With a reviewed operator config, the existing editable Graph/Lab virtual environments and `web/dist` built:

```sh
bash scripts/start_platform.sh /absolute/path/to/operator-config.json
```

This command supervises the local API and the registered Lab worker together. The default address is `http://127.0.0.1:8761`. It restarts an interrupted worker up to three times. Ctrl-C stops the services. It does not deploy a public service or promise execution after the supervising process ends. Production reverse proxy, TLS, authentication deployment and lifecycle supervision require a separate explicit deployment.

Run the bounded real-data HTTP and browser acceptance against an isolated runtime copy:

```sh
QUANTGRAPH_NODE_BIN=/path/to/node22-or-newer/bin bash scripts/accept_platform_all.sh /absolute/path/to/operator-config.json
```

The config must declare `acceptance_copy: true` and `allow_worker_interruption_test: true`. This performs real computation, including an intentional worker termination after experiment registration. It creates 36 bounded statistical trial registrations across HTTP and browser flows, not an optimization search. Acceptance fixtures are labelled and excluded from real Catalog counts. Reports remain beside the private config; screenshots contain no credentials. The API must already be running. Existing pytest, public release verification and mocked transport tests are separate from this real acceptance.

## Configuration and contracts

`api/platform.py` composes the existing Catalog, ingestion journal, authenticated admin session and `ResearchJobRepository`. The JSON operator config contains `graph_root`, `lab_python`, `catalog_db`, `ingestion_db`, `job_db`, `registry_path`, `output_root`, `admin_password_file`, `port`, registered `profiles`, and optional `limits`, `acceptance_cases`, `research_collections`. Password files remain private, outside Git and the handoff. Use separate DBs and output directories for each runtime.

Each profile fixes `capability: discovery-v1`, one `study_type`, allowed `entity_types`, `max_entities`, `max_trials`, `trials_per_entity`, `max_seconds`, trusted `server_config`, and independently reviewed `display_policy`, `public_display`, `numeric_display`. The server config pins the actual data manifest, contract, source catalog and source roots. Requests only choose a registered profile ID. They cannot choose shell commands, Python, paths, market inputs or public-display permissions. Anonymous requests cannot start computation; queue, global concurrency, time and rolling trial budget limits apply. SQLite WAL/transactions, idempotency hashes and fenced leases preserve run identity on recovery. Cancellation stops the subprocess and retains partial artifacts.

The compatible versions remain `research-request/v1`, `factor-study-result/v1`, and the existing strategy evidence 1.0/3.0 envelopes. Optional `study_metadata` adds exact entity revisions, provenance, limitations, lineage, study kind and conclusion strength. Absent optional metadata does not alter old artifact serialization. Job lifecycle is QUEUED/RUNNING/SUCCEEDED/PARTIAL/BLOCKED/FAILED/CANCELLED. Computational success does not grant ELIGIBLE, independent confirmation or trading rights.

Public research summaries are available at `/v1/research/results` and on the original Catalog detail, with exact definition revision and current server visibility. Authenticated `/v1/research/jobs/{job_id}/evidence` returns permitted internal research, without an arbitrary file/download endpoint. Hidden ancestors also suppress dependent public summaries. Already downloaded content cannot be recalled.

## Import retained research without new trials

```sh
.venv/bin/python -m quantgraph.graph.research_import \
  --config /absolute/path/to/operator-config.json \
  --manifest /authorized/artifacts/import-manifest.json \
  --sha256 REVIEWED_MANIFEST_SHA256 \
  --artifact-root /authorized/artifacts \
  --receipt /private/output/import-receipt.json
```

This operator-only command verifies every declared artifact hash and rejects paths outside the explicit directory before any mutation. It imports derived definitions through the existing ingestion journal, binds evidence to exact Catalog revisions, and records original result/envelope hashes, attempt IDs and registry scope. Imported jobs are terminal, use zero compute budget and cannot be claimed by a worker. A replay returns the same job IDs. An interrupted import may be retried; successfully imported evidence is retained, never overwritten. There is no HTTP import route.

Optional `research_collections` maps stable collection IDs to `title`, `manifest_sha256`, operational `trial_counts`/`triage_counts`, `limitations`, and a fixed `report: {path, sha256}`. Public `/v1/research/collections` exposes no local path; its counts must come from the reviewed manifest. The authenticated report endpoint verifies the pinned digest on every read. Changed reports require an explicit new reviewed digest; request data cannot select report paths. A hidden linked entity suppresses the collection.

## Current evidence and limits

The reviewed B manifest has 98 Catalog-associated result revisions: 78 strategy results (60 baseline, six original failures, six repairs, six development-only component studies) plus 20 factor results covering 40 labels. Three buy-and-hold control configurations remain internal. The original registry holds 121 attempts: 81 strategy configurations (75 completed, six failed) and 40 factor labels; the initial two smoke labels are separate. Metadata import adds zero attempts. B's two derived strategies retain their parent and factor references. Failure and negative results are kept.

The calculations use real BTC/EUR daily bars and explicit costs. They are cross-market independent research implementations of 20 source templates, not complete reproductions of original authors' equity/cash settings. Historical samples were observed, prior search completeness is UNKNOWN, and neither DSR nor diagnostic PBO grants independent confirmation. The two turnover-oriented modifications do not establish general profitability improvement. No fabricated improvement is used for acceptance.

The reviewed Bit2Me source permits the configured internal research but restricts public numerical derivatives. Catalog entities and operational research metadata are PUBLIC; numerical evidence and the full learning report require authentication. This is a source-rights limitation, not an alpha-secrecy setting. Public numerical research and public production deployment are not claimed complete. An independently approved source or additional rights review is needed before changing `numeric_display`.

`build-public`, `verify-public` and public tests run from the public checkout. Full `validate-release` additionally needs all locked private raw snapshots; a public-only worktree must report missing inputs, not fabricate a PASS or download replacements into frozen data. Local operational data, research artifacts, logs and reports remain outside public Git.
