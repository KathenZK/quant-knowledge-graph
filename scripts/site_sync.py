#!/usr/bin/env python3
"""Explicit owner-private Sites research upload and durable feedback pull.

The caller obtains this Site's platform service credential via Sites get_site,
confirms owner-only access, and supplies it through hidden stdin. Never persist
the credential, reuse it at another destination, or impersonate a browser user.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from itertools import islice
import base64
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys
import termios
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

from quantgraph.graph.site_feedback import FeedbackLedger, canonical, read_envelope

BATCH_MAX_OBJECTS = 32
BATCH_MAX_BYTES = 4 * 1024 * 1024
UPLOAD_CONCURRENCY = 4


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Refusing to forward a Site credential through a redirect')


class SiteClient:
    def __init__(self, origin, token):
        self.origin = FeedbackLedger.source(origin)
        if not urlsplit(self.origin).hostname.endswith('.chatgpt.site'):
            raise ValueError('Expected the verified native Sites origin')
        if not isinstance(token, str) or not token or len(token) > 10000:
            raise ValueError('Missing platform service credential')
        self.token = token
        self.opener = build_opener(NoRedirect())

    def request(self, path, method='GET', value=None, raw=None):
        if not path.startswith('/v1/sync/') or '://' in path or '..' in path:
            raise ValueError('Unsupported synchronization path')
        data = raw if raw is not None else canonical(value).encode() if value is not None else None
        req = Request(self.origin + path, data=data, method=method, headers={
            'OAI-Sites-Authorization': 'Bearer ' + self.token,
            'X-QuantGraph-Sync': '1',
            'Content-Type': 'application/octet-stream' if raw is not None else 'application/json',
        })
        try:
            with self.opener.open(req, timeout=90) as response:
                if response.length and response.length > 8 * 1024 * 1024:
                    raise ValueError('Unexpectedly large synchronization response')
                body = response.read(8 * 1024 * 1024 + 1)
                if len(body) > 8 * 1024 * 1024:
                    raise ValueError('Response exceeds limit')
                return json.loads(body)
        except HTTPError as error:
            # No headers or credential-bearing request representation in logs.
            raise RuntimeError(f'Site operation failed with HTTP {error.code}') from None


def object_upload_requests(objects):
    """Pack exact wire/decoded/expanded bounds; larger objects retain single PUT."""
    empty_bytes = len(canonical({'objects': []}).encode())
    pending = []
    wire_bytes, decoded_bytes, expanded_bytes = empty_bytes, 0, 0
    seen = set()
    for row, data in objects:
        if row['sha256'] in seen:
            continue
        seen.add(row['sha256'])
        expanded_size = len(data)
        if data.startswith(b'\x1f\x8b'):
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
                expanded_size = len(stream.read(BATCH_MAX_BYTES + 1))
        entry = {
            'sha256': row['sha256'], 'bytes': len(data),
            'data_base64': '',
        }
        entry_bytes = len(canonical(entry).encode()) + 4 * ((len(data) + 2) // 3)
        if pending and (
            len(pending) == BATCH_MAX_OBJECTS
            or wire_bytes + 1 + entry_bytes > BATCH_MAX_BYTES
            or decoded_bytes + len(data) > BATCH_MAX_BYTES
            or expanded_bytes + expanded_size > BATCH_MAX_BYTES
        ):
            yield '/v1/sync/objects-batch', {'objects': pending}, None
            pending = []
            wire_bytes, decoded_bytes, expanded_bytes = empty_bytes, 0, 0
        if empty_bytes + entry_bytes > BATCH_MAX_BYTES or expanded_size > BATCH_MAX_BYTES:
            yield '/v1/sync/objects/' + row['sha256'], None, data
            continue
        wire_bytes += entry_bytes + bool(pending)
        decoded_bytes += len(data)
        expanded_bytes += expanded_size
        entry['data_base64'] = base64.b64encode(data).decode('ascii')
        pending.append(entry)
    if pending:
        yield '/v1/sync/objects-batch', {'objects': pending}, None


def verify_object_receipt(result, expected):
    if not isinstance(result, dict) or result.get('complete') is not True:
        raise RuntimeError('Object batch upload was incomplete; activation not attempted')
    receipts = result.get('objects')
    if not isinstance(receipts, list) or len(receipts) != len(expected):
        raise RuntimeError('Object batch receipt is incomplete; activation not attempted')
    received = set()
    for row in receipts:
        if (
            not isinstance(row, dict) or not isinstance(row.get('sha256'), str)
            or row['sha256'] not in expected
            or row['sha256'] in received or row.get('stored') is not True
            or type(row.get('replayed')) is not bool
        ):
            raise RuntimeError('Object batch receipt does not match; activation not attempted')
        received.add(row['sha256'])


def upload(client, manifest_path, object_root, expected_sha):
    manifest_path, root = Path(manifest_path), Path(object_root).resolve()
    raw = manifest_path.read_bytes()
    if len(raw) > 1500000 or hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError('Manifest pin does not match')
    manifest = read_envelope(manifest_path)
    objects = []
    for row in manifest['files']:
        path = row['path']
        if not path.startswith(('/catalog/', '/data/')) or '..' in path or '\\' in path:
            raise ValueError('Unsafe object path')
        file = root / path.lstrip('/')
        if file.is_symlink() or root not in file.resolve().parents:
            raise ValueError('Object escaped reviewed input root')
        if file.stat().st_size != row['bytes'] or row['bytes'] > 16000000:
            raise ValueError('Object size differs')
        data = file.read_bytes()
        if hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('Object bytes differ')
        objects.append((row, data))
    receipt = client.request('/v1/sync/batches', 'POST', manifest)
    def send_object(request):
        path, value, raw = request
        try:
            result = client.request(path, 'PUT' if raw is not None else 'POST', value, raw=raw)
        except RuntimeError as error:
            raise RuntimeError(f'{error}; object upload incomplete, activation not attempted') from None
        if value is not None:
            verify_object_receipt(result, {row['sha256'] for row in value['objects']})
        elif not isinstance(result, dict) or result.get('sha256') != path.rsplit('/', 1)[1] or type(result.get('replayed')) is not bool:
            raise RuntimeError('Single object receipt does not match; activation not attempted')

    # Independent immutable objects may upload concurrently. Keep both queued
    # requests and in-flight payloads bounded; activation follows every receipt.
    requests = iter(object_upload_requests(objects))
    with ThreadPoolExecutor(max_workers=UPLOAD_CONCURRENCY) as pool:
        while group := list(islice(requests, UPLOAD_CONCURRENCY)):
            list(pool.map(send_object, group))
    active = client.request('/v1/sync/activate/' + receipt['batch_id'], 'POST', {})
    return {'batch': receipt, 'activation': active, 'objects': len(objects)}


def pull_feedback(client, ledger_path):
    ledger = FeedbackLedger(ledger_path)
    receipts = []
    while True:
        cursor = ledger.cursor(client.origin)
        envelope = client.request('/v1/sync/feedback?after_cursor=' + str(cursor))
        receipt = ledger.ingest(client.origin, envelope)
        # This acknowledgement follows the committed local transaction.
        ack = client.request('/v1/sync/ack', 'POST', {'cursor': receipt['durable_cursor']})
        receipts.append({**receipt, 'acknowledged_cursor': ack['received_cursor']})
        if not envelope['has_more']:
            return {'pages': receipts, 'status': 'received_not_yet_researched'}


def secret_stdin():
    state = None
    if sys.stdin.isatty():
        state = termios.tcgetattr(sys.stdin)
        hidden = list(state)
        hidden[3] &= ~termios.ECHO
        termios.tcsetattr(sys.stdin, termios.TCSANOW, hidden)
    print('Ready for platform Site credential JSON on stdin (input hidden).', flush=True)
    try:
        value = json.loads(sys.stdin.readline(12000))
        return value['token']
    finally:
        if state is not None:
            termios.tcsetattr(sys.stdin, termios.TCSANOW, state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['status', 'upload', 'feedback'])
    parser.add_argument('--site-url', required=True)
    parser.add_argument('--confirmed-owner-private', action='store_true', required=True)
    parser.add_argument('--manifest')
    parser.add_argument('--object-root')
    parser.add_argument('--sha256')
    parser.add_argument('--ledger')
    parser.add_argument('--receipt', required=True)
    args = parser.parse_args()
    client = SiteClient(args.site_url, secret_stdin())
    if args.operation == 'upload':
        result = upload(client, args.manifest, args.object_root, args.sha256)
    elif args.operation == 'feedback':
        result = pull_feedback(client, args.ledger)
    else:
        result = client.request('/v1/sync/status')
    Path(args.receipt).write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
