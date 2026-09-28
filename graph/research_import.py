"""Operator-only import of pinned research artifacts; never launches computation."""
import argparse
import hashlib
import json
from pathlib import Path

from quantgraph.graph.catalog import CatalogRepository
from quantgraph.graph.ingestion_store import SQLiteIngestionRepository
from quantgraph.graph.research_jobs import ResearchJobRepository
from quantgraph.models.ingestion import IngestBatch


def import_manifest(config, manifest_path, expected_sha256, artifact_root):
    root = Path(artifact_root).resolve(strict=True)
    checked = {}

    def read_artifact(ref):
        path = Path(ref['uri']).resolve(strict=True)
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError('Artifact must remain inside the explicit input directory')
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != ref['sha256']:
            raise ValueError('Artifact digest mismatch: ' + path.name)
        checked[str(path)] = json.loads(content)
        return checked[str(path)]

    manifest = read_artifact({'uri': str(manifest_path), 'sha256': expected_sha256})
    if (manifest.get('schema_version') != 'B-discovery-delivery-manifest/v1'
            or manifest.get('import_mode') != 'IMPORTED_COMPLETED_RESEARCH'
            or manifest.get('execute_new_trials') is not False):
        raise ValueError('Only retained, completed research manifests are supported')

    def verify_refs(value):
        if isinstance(value, dict):
            if 'uri' in value and 'sha256' in value:
                read_artifact(value)
            else:
                for child in value.values():
                    verify_refs(child)
        elif isinstance(value, list):
            for child in value:
                verify_refs(child)

    # Verify every artifact before the first mutation. Paths in input data never
    # select an executable, output location, profile or arbitrary local read.
    verify_refs(manifest)
    entries = manifest['entries']
    prepared = []
    for entry in entries:
        envelope = checked[str(Path(entry['envelope']['uri']).resolve())]
        if envelope.get('run_id', envelope.get('research_run_id')) != entry['run_id']:
            raise ValueError('Original run identity mismatch')
        meta = envelope.get('study_metadata', {})
        if meta.get('entity_refs') != entry['entity_refs'] or meta.get('study_type') != entry['study_type']:
            raise ValueError('Manifest and result definition bindings differ')
        profiles = [key for key, profile in config['profiles'].items()
                    if profile['study_type'] == entry['study_type']
                    and profile.get('display_policy') == meta.get('display_policy')]
        if len(profiles) != 1:
            raise ValueError('Exactly one locally reviewed import profile is required')
        request = dict(request_id='retained-' + entry['run_id'], entity_refs=entry['entity_refs'],
                       study_type=entry['study_type'], requested_settings={'profile_id': profiles[0]})
        prepared.append((entry, envelope, request))

    ingestion = SQLiteIngestionRepository(config['ingestion_db'])
    catalog = CatalogRepository(config['catalog_db'], ingestion=ingestion)
    for ref in manifest.get('derived_record_batches', []):
        payload = checked[str(Path(ref['uri']).resolve())]
        batch = IngestBatch.model_validate(payload)
        ingestion.ingest(batch, json.dumps(payload, ensure_ascii=False).encode(), 'retained-research-import')
    sync = catalog.sync_ingestion()
    if sync['errors']:
        raise ValueError('Derived definitions failed Catalog projection; safe to retry import')
    jobs = ResearchJobRepository(config['job_db'], config['profiles'], **config.get('limits', {}))
    imported = []
    for entry, envelope, request in prepared:
        receipt = dict(manifest_sha256=expected_sha256, run_id=entry['run_id'],
                       original_result=entry['original_result'], original_envelope=entry['original_envelope'],
                       metadata_revision=entry['envelope'], registry_scope=entry['registry_scope'],
                       attempt_ids=entry['attempt_ids'])
        job, duplicate = jobs.import_completed(request, [envelope], source_receipt=receipt,
                                               owner='administrator', resolve_ref=catalog.resolve_ref)
        imported.append(dict(job_id=job['job_id'], run_id=entry['run_id'], status=job['status'], duplicate=duplicate))
    return dict(manifest_sha256=expected_sha256, imported=imported, new_trials=0,
                original_counts=manifest['counts'], artifact_count=len(checked))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--artifact-root', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    report = import_manifest(json.loads(args.config.read_text()), args.manifest, args.sha256, args.artifact_root)
    args.receipt.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'imported': len(report['imported']), 'new_trials': 0,
                      'duplicates': sum(r['duplicate'] for r in report['imported'])}))


if __name__ == '__main__':
    main()
