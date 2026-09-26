"""Read a bounded tar/CSV snapshot without extraction or rewriting source bytes."""
import csv
import hashlib
import io
from pathlib import Path, PurePosixPath
import tarfile

REQUIRED = {'id', '名称', '市场', '规则', 'source_url', '提出日期'}
MAX_ARCHIVE = 100 * 1024 * 1024
MAX_MEMBER = 64 * 1024 * 1024


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def csv_rows(data):
    reader = csv.DictReader(io.StringIO(data.decode('utf-8-sig'), newline=''))
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise ValueError('Missing or duplicate CSV headers')
    rows = list(reader)
    if any(None in r or any(v is None for v in r.values()) for r in rows):
        raise ValueError('Malformed CSV row; no records silently dropped')
    return rows


def read_bundle(path):
    path = Path(path)
    if path.stat().st_size > MAX_ARCHIVE:
        raise ValueError('Archive exceeds size limit')
    data = path.read_bytes()
    members = {}
    total = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        for entry in archive:
            p = PurePosixPath(entry.name)
            if p.is_absolute() or '..' in p.parts or entry.issym() or entry.islnk():
                raise ValueError('Unsafe archive member')
            if entry.isdir():
                continue
            if not entry.isfile() or entry.size > MAX_MEMBER or entry.name in members:
                raise ValueError('Invalid, oversized or duplicate archive member')
            total += entry.size
            if total > 256 * 1024 * 1024:
                raise ValueError('Expanded archive exceeds size limit')
            members[entry.name] = archive.extractfile(entry).read()
    if 'quant-master-draft.csv' not in members:
        raise ValueError('Missing quant-master-draft.csv')
    rows = csv_rows(members['quant-master-draft.csv'])
    if not rows or not REQUIRED <= rows[0].keys():
        raise ValueError('Missing required corpus columns')
    ids = [r['id'].strip() for r in rows]
    if not all(ids) or len(ids) != len(set(ids)):
        raise ValueError('Missing or duplicate native ID; review before import')
    screens = []
    for name, content in sorted(members.items()):
        if name.startswith('validation/strategy-validation-batch') and name.endswith('.csv'):
            for row in csv_rows(content):
                if not {'id', 'proxy_and_rule', 'data_note'} <= row.keys():
                    raise ValueError('Missing legacy screen fields')
                screens.append({'member': name, 'sha256': sha256(content), 'row': row})
    return {'sha256': sha256(data), 'bytes': data, 'members': members, 'rows': rows, 'screens': screens}


def preserve_bundle(root, bundle):
    directory = Path(root) / 'datasets/raw/sources/grokbot' / bundle['sha256']
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / 'input.tar.gz'
    try:
        with target.open('xb') as stream:
            stream.write(bundle['bytes'])
    except FileExistsError:
        if sha256(target.read_bytes()) != bundle['sha256']:
            raise ValueError('Immutable raw snapshot was modified')
    return target
