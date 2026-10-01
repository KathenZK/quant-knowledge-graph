# Private export storage and mutable import workspaces

Exports preserve the existing fixed artifact names and byte-pinned import manifest.
They share exact artifact bytes through read-only regular hardlinks. The original
source/audit/run files remain independent. SQLite files never enter this store.

## Export once, reuse across batches

Pass the same `--object-store` to `python -m quantgraph.graph.corpus_export` for
all batches. Without it, sibling exports share `.corpus-export-objects` in their
parent. The store must share the destination filesystem. Existing objects are
verified before reuse; corrupt, writable, symlink or special objects fail closed.
The exporter validates source and derived bytes before materialization, creates a
fresh staging directory, fsyncs it, and publishes atomically under a cooperating
exporter lock. No uncoordinated writer may edit the frozen export namespace.

Objects are created from validated bytes, never linked from mutable sources.
Frozen artifacts must not be chmod'ed and rewritten in place: intentionally
changed artifacts require a new version or an independent file replacement.
Read-only bits prevent accidents; they cannot prevent an owner/root deliberately
altering a shared inode. Original manifest hashes remain the integrity check.

Export receipts may still be appended to the run directory. Object-store contents
must not be removed without auditing all surviving hardlink/reference consumers.
A failed export can retain a valid unused object; this is not permission for
automatic garbage collection. Old exports and their manifests are not rewritten.

## Stop cloning the cumulative database for each batch

Use a newly created mutable workspace, separate from all historical runtimes:

- `python -m quantgraph.graph.corpus_workspace init PATH`
- `python -m quantgraph.graph.corpus_workspace append PATH --manifest FILE --sha256 HASH --results-dir DIR --audit-dir DIR`
- Only when a frozen publication/rollback checkpoint is needed:
  `python -m quantgraph.graph.corpus_workspace snapshot PATH NEW_SQLITE_FILE`

Initialization refuses every existing directory. Append refuses unmarked frozen
runtimes, symlink databases and multiply linked databases. It delegates each run
to the existing validated `BEGIN IMMEDIATE` transaction; a failed transaction
retains the previously committed runs. There is no full database copy per append.
A multi-run batch is resumable per run, not one all-or-nothing transaction.

Snapshot is an explicit independent SQLite backup. It includes committed WAL
content, closes its database handles, verifies a self-contained DELETE-journal
file, and uses create-only atomic publication. The output must be outside the
mutable workspace. Existing frozen snapshots are never overwritten; callers
retain their current successful publication and required rollback checkpoints.
Neither operation changes a global/current pointer or deploys a Site.

The CLI preflights a 5 GiB free-space reserve. Snapshot budgets the logical page
count including committed WAL growth. Append's four-times-artifact-byte estimate
is a conservative preflight, not a filesystem quota or absolute allocation bound:
compressed returns, indexes, journals and unrelated writers can require more.
Budget peak space for the actual workload and coordinate writers before large
imports. No existing production runtime is automatically adopted or migrated.

Before running, verify the loaded `quantgraph.graph.corpus_export.__file__`.
Editable installations or scripts prepending older worktrees can select old code;
changing a canonical tree alone does not update those scripts. Historical,
hash-pinned scripts should remain frozen; use an explicit new entry point.
