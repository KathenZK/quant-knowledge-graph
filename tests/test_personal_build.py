"""Build identity and daily launch fail closed before serving a stale page."""
import hashlib
import json
import socket

import pytest
from fastapi.testclient import TestClient
from quantgraph.api.personal_app import create_personal_app
from quantgraph.graph.personal_build_info import VERSION, build_info, source_fingerprint
from scripts.start_personal import check_port, node_environment


def test_build_missing_valid_stale_tampered_and_no_private_paths(tmp_path):
    web = tmp_path / 'web'
    (web / 'src').mkdir(parents=True)
    (web / 'src/app.ts').write_text('const a=1')
    assert build_info(tmp_path)['status'] == 'MISSING'
    dist = web / 'dist'
    (dist / 'assets').mkdir(parents=True)
    (dist / 'index.html').write_text('page')
    info = dict(schema_version=VERSION, build_id='test-id', source_fingerprint=source_fingerprint(web),
                built_at='2026-09-29T00:00:00Z', app_version='test', outputs={'index.html':hashlib.sha256(b'page').hexdigest()})
    (dist / 'build-info.json').write_text(json.dumps(info))
    assert build_info(tmp_path)['status'] == 'CURRENT'
    client = TestClient(create_personal_app(root=tmp_path, runtime=tmp_path/'runtime'))
    meta = client.get('/v1/web/meta').json()
    assert meta['build']['build_id'] == 'test-id' and meta['application_version']
    assert str(tmp_path) not in json.dumps(meta)
    (web / 'src/app.ts').write_text('const a=2')
    assert build_info(tmp_path)['status'] == 'STALE'
    (dist / 'index.html').write_text('tampered')
    assert build_info(tmp_path)['status'] == 'INVALID'


def test_fingerprint_add_delete_lock_config_and_generated_inputs(tmp_path):
    (tmp_path / 'src').mkdir()
    first = source_fingerprint(tmp_path)
    for filename in ['src/new.ts', 'package.json', 'package-lock.json', 'vite.config.ts', '.env.production']:
        item = tmp_path / filename
        item.write_text('input')
        assert source_fingerprint(tmp_path) != first
        item.unlink()
        assert source_fingerprint(tmp_path) == first
    (tmp_path / 'generated').mkdir()
    (tmp_path / 'generated/api.json').write_text('{}')
    assert source_fingerprint(tmp_path) != first


def test_occupied_port_is_preserved():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        port = listener.getsockname()[1]
        with pytest.raises(ValueError, match='没有终止任何进程'):
            check_port(port)
        assert listener.fileno() >= 0
        with socket.create_connection(('127.0.0.1', port), timeout=1):
            pass
    check_port(port)


def test_missing_supported_node_is_explicit(tmp_path, monkeypatch):
    monkeypatch.delenv('QUANTGRAPH_NODE_BIN', raising=False)
    monkeypatch.setattr('scripts.start_personal.shutil.which', lambda _: None)
    with pytest.raises(ValueError, match='Node.js 22'):
        node_environment(tmp_path)
