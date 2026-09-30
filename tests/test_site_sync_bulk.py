"""Synthetic-only checks for explicit owner-private Site upload transport."""
import base64
import gzip
import hashlib
import io
import json
from urllib.error import HTTPError

import pytest

from scripts import site_sync


def object_row(data, index=0):
    return {
        'path': f'/catalog/details/synthetic-{index}.json',
        'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
    }, data


def write_inputs(tmp_path, data):
    objects = [object_row(value, index) for index, value in enumerate(data)]
    for row, value in objects:
        path = tmp_path / row['path'].lstrip('/')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    manifest = {
        'schema_version': 'quantgraph-site-sync/v1',
        'parent_batch_id': 'bundled-test',
        'files': [row for row, _ in objects], 'entities': [], 'results': [],
    }
    path = tmp_path / 'manifest.json'
    raw = site_sync.canonical(manifest).encode()
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


class SyntheticClient:
    def __init__(self, receipt_transform=None, fail_upload=False):
        self.calls = []
        self.receipt_transform = receipt_transform
        self.fail_upload = fail_upload

    def request(self, path, method='GET', value=None, raw=None):
        self.calls.append((path, method, value, raw))
        if path == '/v1/sync/batches':
            return {'batch_id': 'synthetic-batch'}
        if path == '/v1/sync/objects-batch':
            if self.fail_upload:
                raise RuntimeError('Site operation failed with HTTP 503')
            receipt = {
                'complete': True,
                'objects': [dict(sha256=row['sha256'], stored=True, replayed=False)
                            for row in value['objects']],
            }
            return self.receipt_transform(receipt) if self.receipt_transform else receipt
        if path.startswith('/v1/sync/objects/'):
            return {'sha256': path.rsplit('/', 1)[1], 'replayed': False}
        if path.startswith('/v1/sync/activate/'):
            return {'batch_id': 'synthetic-batch', 'active': True}
        raise AssertionError('Unexpected synthetic route')


def assert_bounded(requests):
    for path, value, raw in requests:
        if raw is not None:
            assert path == '/v1/sync/objects/' + hashlib.sha256(raw).hexdigest()
            assert value is None
            continue
        assert path == '/v1/sync/objects-batch'
        assert 1 <= len(value['objects']) <= 32
        assert len(site_sync.canonical(value).encode()) <= site_sync.BATCH_MAX_BYTES
        decoded_total = expanded_total = 0
        for row in value['objects']:
            data = base64.b64decode(row['data_base64'], validate=True)
            assert len(data) == row['bytes']
            assert hashlib.sha256(data).hexdigest() == row['sha256']
            decoded_total += len(data)
            expanded_total += len(gzip.decompress(data)) if data.startswith(b'\x1f\x8b') else len(data)
        assert decoded_total <= site_sync.BATCH_MAX_BYTES
        assert expanded_total <= site_sync.BATCH_MAX_BYTES


def test_654_small_objects_use_21_requests_and_activate_once(tmp_path):
    manifest, digest = write_inputs(tmp_path, [json.dumps({'synthetic': i}).encode() for i in range(654)])
    client = SyntheticClient()
    result = site_sync.upload(client, manifest, tmp_path, digest)
    uploads = [(path, value, raw) for path, _, value, raw in client.calls if path == '/v1/sync/objects-batch']
    assert len(uploads) == 21
    assert [len(value['objects']) for _, value, _ in uploads] == [32] * 20 + [14]
    assert len(client.calls) == 23
    assert result['objects'] == 654 and result['activation']['active'] is True
    assert client.calls[-1][0] == '/v1/sync/activate/synthetic-batch'
    assert_bounded(uploads)


def test_packing_uses_actual_wire_size_and_preserves_large_single_put():
    data = [json.dumps(char * size).encode() for char, size in [
        ('a', 1600000), ('b', 1600000), ('c', site_sync.BATCH_MAX_BYTES), ('d', 10),
    ]]
    requests = list(site_sync.object_upload_requests([object_row(value, i) for i, value in enumerate(data)]))
    assert len(requests) == 4
    assert [raw is not None for _, _, raw in requests] == [False, False, True, False]
    assert_bounded(requests)


def test_exact_wire_boundary_is_allowed_and_one_byte_less_splits(monkeypatch):
    objects = [object_row(b'{}'), object_row(b'[]')]
    initial = list(site_sync.object_upload_requests(objects))
    wire = len(site_sync.canonical(initial[0][1]).encode())
    monkeypatch.setattr(site_sync, 'BATCH_MAX_BYTES', wire)
    assert len(list(site_sync.object_upload_requests(objects))) == 1
    monkeypatch.setattr(site_sync, 'BATCH_MAX_BYTES', wire - 1)
    split = list(site_sync.object_upload_requests(objects))
    assert len(split) == 2 and all(raw is None for _, _, raw in split)


def test_compressed_expansion_splits_and_large_expansion_uses_single_put():
    data = [gzip.compress(json.dumps(char * size).encode()) for char, size in [
        ('a', 3 * 1024 * 1024), ('b', 3 * 1024 * 1024), ('c', site_sync.BATCH_MAX_BYTES),
    ]]
    requests = list(site_sync.object_upload_requests([object_row(value, i) for i, value in enumerate(data)]))
    assert len(requests) == 3
    assert [raw is not None for _, _, raw in requests] == [False, False, True]
    assert_bounded(requests)


def test_repeated_content_across_paths_is_uploaded_once(tmp_path):
    manifest, digest = write_inputs(tmp_path, [b'{}', b'{}', b'[]'])
    client = SyntheticClient()
    site_sync.upload(client, manifest, tmp_path, digest)
    assert len(client.calls[1][2]['objects']) == 2


@pytest.mark.parametrize('transform', [
    lambda receipt: {**receipt, 'complete': False},
    lambda receipt: {**receipt, 'complete': 1},
    lambda receipt: {**receipt, 'objects': []},
    lambda receipt: {**receipt, 'objects': receipt['objects'][:1] * 2},
    lambda receipt: {**receipt, 'objects': [{**row, 'stored': False} for row in receipt['objects']]},
    lambda receipt: {**receipt, 'objects': [{**row, 'sha256': 'a' * 64} for row in receipt['objects']]},
    lambda receipt: {**receipt, 'objects': [{**row, 'sha256': []} for row in receipt['objects']]},
    lambda receipt: {**receipt, 'objects': [{**row, 'replayed': 1} for row in receipt['objects']]},
    lambda receipt: None,
])
def test_incomplete_or_mismatched_success_receipt_never_activates(tmp_path, transform):
    manifest, digest = write_inputs(tmp_path, [b'{}', b'[]'])
    client = SyntheticClient(receipt_transform=transform)
    with pytest.raises(RuntimeError, match='activation not attempted'):
        site_sync.upload(client, manifest, tmp_path, digest)
    assert not any('/activate/' in path for path, *_ in client.calls)


def test_http_partial_failure_never_activates_and_same_input_is_retryable(tmp_path):
    manifest, digest = write_inputs(tmp_path, [b'{}', b'[]'])
    client = SyntheticClient(fail_upload=True)
    with pytest.raises(RuntimeError, match='HTTP 503; object upload incomplete, activation not attempted'):
        site_sync.upload(client, manifest, tmp_path, digest)
    assert not any('/activate/' in path for path, *_ in client.calls)
    failed_request = client.calls[-1]
    client.fail_upload = False
    site_sync.upload(client, manifest, tmp_path, digest)
    assert client.calls[-2] == failed_request
    assert client.calls[-1][0].startswith('/v1/sync/activate/')


def test_changed_local_pin_or_bytes_fail_before_network(tmp_path):
    manifest, digest = write_inputs(tmp_path, [b'{}'])
    client = SyntheticClient()
    with pytest.raises(ValueError, match='Manifest pin'):
        site_sync.upload(client, manifest, tmp_path, 'a' * 64)
    (tmp_path / 'catalog/details/synthetic-0.json').write_bytes(b'[]')
    with pytest.raises(ValueError, match='Object bytes'):
        site_sync.upload(client, manifest, tmp_path, digest)
    assert client.calls == []


def test_transport_keeps_credential_in_memory_and_rejects_redirects(capsys):
    token = 'synthetic-test-only-credential'
    client = site_sync.SiteClient('https://synthetic.chatgpt.site', token)
    captured = []

    class Opener:
        def open(self, request, timeout):
            captured.append(request)
            error = HTTPError(request.full_url, 503, token, {'Secret': token}, io.BytesIO(token.encode()))
            raise error

    client.opener = Opener()
    with pytest.raises(RuntimeError, match='^Site operation failed with HTTP 503$') as raised:
        client.request('/v1/sync/objects-batch', 'POST', {'objects': []})
    assert token not in str(raised.value)
    request = captured[0]
    assert token not in request.full_url and token.encode() not in request.data
    assert request.get_header('Oai-sites-authorization') == 'Bearer ' + token
    assert request.get_header('X-quantgraph-sync') == '1'
    assert not request.has_header('oai-authenticated-user-id')
    with pytest.raises(ValueError, match='redirect'):
        site_sync.NoRedirect().redirect_request(request, None, 307, '', {}, 'https://elsewhere.example/')
    captured_output = capsys.readouterr()
    assert captured_output.out == '' and captured_output.err == ''


def test_only_verified_native_site_origin_and_sync_paths_are_accepted():
    for origin in ['https://example.com', 'https://chatgpt.site.attacker.example', 'https://synthetic.chatgpt.site?token=x']:
        with pytest.raises(ValueError):
            site_sync.SiteClient(origin, 'synthetic-credential')
    client = site_sync.SiteClient('https://synthetic.chatgpt.site', 'synthetic-credential')
    for path in ['https://elsewhere.example/v1/sync/objects-batch', '/v1/personal/items', '/v1/sync/../outside']:
        with pytest.raises(ValueError, match='path'):
            client.request(path)


def test_single_put_receipt_mismatch_never_activates(tmp_path):
    raw = json.dumps('a' * (site_sync.BATCH_MAX_BYTES + 1)).encode()
    manifest, pin = write_inputs(tmp_path, [raw])

    class WrongReceipt(SyntheticClient):
        def request(self, path, method='GET', value=None, raw=None):
            result = super().request(path, method, value, raw)
            return {'sha256': 'f' * 64, 'replayed': False} if path.startswith('/v1/sync/objects/') else result

    client = WrongReceipt()
    with pytest.raises(RuntimeError, match='Single object receipt does not match'):
        site_sync.upload(client, manifest, tmp_path, pin)
    assert not any('/activate/' in path for path, *_ in client.calls)
