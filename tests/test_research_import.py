"""Pinned operator import rejects changed/out-of-scope evidence before mutation."""
import hashlib
import json

import pytest
from quantgraph.graph.research_import import import_manifest


def write(path, value):
    path.write_text(json.dumps(value))
    return {'uri': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


@pytest.mark.parametrize('violation', ['outside', 'changed'])
def test_untrusted_artifacts_fail_before_creating_databases(tmp_path, violation):
    inputs = tmp_path / 'inputs'
    inputs.mkdir()
    artifact = write(tmp_path / 'outside.json' if violation == 'outside' else inputs / 'result.json', {})
    manifest = write(inputs / 'manifest.json', {
        'schema_version': 'B-discovery-delivery-manifest/v1',
        'import_mode': 'IMPORTED_COMPLETED_RESEARCH', 'execute_new_trials': False,
        'entries': [], 'registry_scope': artifact,
    })
    if violation == 'changed':
        (inputs / 'result.json').write_text('{"changed":true}')
    config = {k: str(tmp_path / (k + '.sqlite')) for k in ('ingestion_db', 'catalog_db', 'job_db')}
    with pytest.raises(ValueError, match='directory|digest'):
        import_manifest(config, manifest['uri'], manifest['sha256'], inputs)
    assert not list(tmp_path.glob('*.sqlite'))
