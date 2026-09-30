# QuantGraph hosted deployment

This directory is the Sites target of the same QuantGraph application. React page components remain in `web/src`. Python remains the collector, normalization, research, and local API implementation. The Worker implements only immutable research-snapshot delivery/sync and a persistent feedback overlay. It neither runs Python backtests nor submits trades.

Native Sites owns D1 (`DB`), R2 (`BUCKET`), user authentication and owner-private access. The hosting manifest belongs only to the private deployment checkout. Never commit Site identity, credentials, private snapshots, generated reference indexes, or deployment output to public Git.

`sites/build.mjs` builds the original React app with its hosted transport and emits `dist/server/index.js`, `dist/client`, and D1 migrations. A private staging operation copies this repository's exact tracked application source, package lock, and a pinned public-assets snapshot to the existing Site checkout. `seed.generated.json` is a generated immutable reference index over that bundled baseline, not a separate app implementation.

Browser notes require trusted `oai-authenticated-user-id`, exact same-origin writes, a request header and JSON. The principal is never accepted in client payloads. Service sync endpoints rely on Sites dispatch service access and are valid only while the Site is confirmed owner-private; they reject browser user context. Do not send a service token to another host or put it in browser code. MCP tools are read-only and require user identity for feedback.

Batch manifests and objects are immutable. The current pointer changes only after each declared byte length and SHA256 matches uploaded objects and entity/result references match the retained details. Compare-and-swap activation prevents one uploader replacing a concurrent batch. Old batches, objects and notes remain accessible. Notes use a fixed entity+definition reference, optional origin+variant+manifest, optimistic revisions and actor-scoped idempotency keys. They do not change source facts or research results.

Data completion and feedback consumption are explicit operations, not an unverified continuous background service. Refreshing the page reads the latest activated batch. Saving a note persists to D1 immediately. The research-side consumer commits an append-only SQLite ledger before acknowledging its cursor. Acknowledgement means received, not researched.

Run `node --test sites/tests/*.test.mjs`. Schema lives in `sites/db/schema.ts`; generate and inspect migrations with `sites/node_modules/.bin/drizzle-kit generate --config sites/drizzle.config.ts`. Applied migrations and their metadata are immutable. Never rewrite them to retry a failed deploy without establishing the applied boundary.

The page pins one active snapshot for all manifest/index/detail requests. It does not mix different activation states while loading. Old-note export uses the note's original snapshot and definition revision; unavailable pinned definitions remain explicitly unavailable rather than substituted. Browser migration recognizes all three historical storage keys, is opt-in, retains originals, and never overwrites an existing cloud note. Unsaved editor drafts are temporary session state, not the authoritative notebook.

Owner-private hosting is a security precondition for service routes. `X-QuantGraph-Sync` is a request discriminator, not a credential. Dispatch validates the platform service credential before invocation. Public sharing would require a separate service authorization design and is not enabled by this implementation.

A rollback is a new successor manifest, explicitly referencing the retained old objects and the current parent. It passes the same hash/reference checks and activation compare-and-swap. The implementation does not silently move the current pointer back to an old batch or rewrite historical activation evidence. Each JSON object is bounded to 8 MB after decompression; larger indexes must be split at known record boundaries before import.
