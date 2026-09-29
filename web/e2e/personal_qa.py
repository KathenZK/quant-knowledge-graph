"""Explicit QA-only test record visibility; never imported by the application.

Only this fixed disposable runtime and loopback port are supported. Ordinary
searches/counts retain production test isolation. TEST_POLISH queries opt in to
the single marked test lineage so the actual browser can inspect its revision.
"""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sqlite3
import sys

from quantgraph.graph.ingestion_store import SQLiteIngestionRepository
from quantgraph.graph.personal_catalog import PersonalCatalogRepository
from quantgraph.models.ingestion import IngestBatch

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / '.artifacts/polish-v1/update-runtime'
SOURCE = ROOT / '.artifacts/personal'
RECORD_ID = 'TEST_POLISH_M4018'


def catalog():
    journal = SQLiteIngestionRepository(RUNTIME / 'ingestion.sqlite')
    return journal, PersonalCatalogRepository(RUNTIME / 'catalog.sqlite', ingestion=journal)


def ingest(journal, record, suffix):
    batch = IngestBatch.model_validate(dict(batch_id='TEST_POLISH_' + suffix, collector_version='test-polish/v1', records=[record]))
    return journal.ingest(batch, batch.model_dump_json().encode(), 'TEST_POLISH_BROWSER')


def seed():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    for name in ['catalog.sqlite', 'ingestion.sqlite']:
        with sqlite3.connect(f'file:{SOURCE / name}?mode=ro', uri=True) as src, sqlite3.connect(RUNTIME / name) as dst:
            src.backup(dst)
    for suffix in ['', '-wal', '-shm']:
        (RUNTIME / ('personal.sqlite' + suffix)).unlink(missing_ok=True)
    shutil.copyfile(SOURCE / 'snapshot.json', RUNTIME / 'snapshot.json')
    journal, model = catalog()
    before = model.metadata()['counts']
    with journal.connect() as con:
        raw = json.loads(con.execute('SELECT raw_payload FROM revisions WHERE record_id=? ORDER BY revision DESC LIMIT 1', ('M4018',)).fetchone()[0])
    raw.pop('auditable_unknown_fields', None)
    row = deepcopy(raw)
    row.update(record_id=RECORD_ID, name='TEST_POLISH_ORIGINAL 隔离测试原版：' + raw['name'])
    row['metadata'] = {**row.get('metadata', {}), 'fixture': True, 'acceptance_scope': 'TEST_ONLY_SIMULATED_REVISION_NOT_SOURCE_FACT'}
    accepted = ingest(journal, row, 'ADD')
    model.sync_ingestion()
    item = next(v for v in model.search(q='TEST_POLISH_ORIGINAL', include_tests=True)['items'] if RECORD_ID in v['source_native_ids'])
    assert item['test_record'] and model.metadata()['counts'] == before
    result = dict(before=before, original=item, accepted=accepted, raw=row)
    (RUNTIME / 'test-lineage.json').write_text(json.dumps(result, ensure_ascii=False))
    print(json.dumps({'entity_id': item['entity_id'], 'definition_revision': item['definition_revision'], 'before': before, 'test_record': True}))


def revise():
    state = json.loads((RUNTIME / 'test-lineage.json').read_text())
    journal, model = catalog()
    row = state['raw']
    row['name'] = row['name'].replace('TEST_POLISH_ORIGINAL', 'TEST_POLISH_UPDATED')
    assert '**20** 日' in row['raw_rule']
    row['raw_rule'] = row['raw_rule'].replace('**20** 日', '**21** 日')
    result = ingest(journal, row, 'REVISION')
    replay = ingest(journal, row, 'REVISION')
    model.sync_ingestion()
    item = next(v for v in model.search(q='TEST_POLISH_UPDATED', include_tests=True)['items'] if RECORD_ID in v['source_native_ids'])
    assert result['revision'] == 1 and replay['replayed']
    assert item['test_record'] and model.metadata()['counts'] == state['before']
    assert model.search(q='TEST_POLISH_UPDATED')['total'] == 0
    print(json.dumps({'entity_id': item['entity_id'], 'definition_revision': item['definition_revision'], 'counts':model.metadata()['counts'], 'test_record':True, 'replayed':True}))


def missing_definition():
    from quantgraph.graph.personal_store import PersonalStore
    from quantgraph.graph.grokbot import stable_json
    store = PersonalStore(RUNTIME / 'personal.sqlite')
    backup = store.backup()
    (RUNTIME / 'before-missing-definition-test.json').write_text(json.dumps(backup, ensure_ascii=False))
    records = backup['payload']['items']
    assert len(records) == 1 and records[0]['note'].startswith('TEST ')
    value = records[0]
    value['definition_revision'] = 'TEST_MISSING_OLD_DEFINITION'
    value['revisions'].append(value['definition_revision'])
    value['record_revision'] += 1
    # Simulate a portable note whose exact old snapshot is absent in this copy.
    # Identity/source definitions stay intact; this is a test-only personal row.
    with store.connect() as con:
        con.execute('UPDATE personal_items SET payload=? WHERE entity_id=?', (stable_json(value), value['entity_id']))
    print(json.dumps({'entity_id':value['entity_id'], 'definition_revision':value['definition_revision'], 'backup_saved':True}))


class QACatalog(PersonalCatalogRepository):
    def get(self, entity_id, *, admin=False, include_tests=False):
        try:
            return super().get(entity_id, admin=admin, include_tests=include_tests)
        except KeyError:
            value = super().get(entity_id, include_tests=True)
            if value.get('test_record') and RECORD_ID in value.get('source_native_ids', []):
                return value
            raise

    def search(self, **kwargs):
        if str(kwargs.get('q', '')).startswith('TEST_POLISH_'):
            kwargs['include_tests'] = True
        return super().search(**kwargs)


def serve():
    import uvicorn
    from quantgraph.api.personal_app import create_personal_app
    if not (RUNTIME / 'test-lineage.json').is_file():
        raise SystemExit('Seed the disposable TEST_POLISH runtime first.')
    journal = SQLiteIngestionRepository(RUNTIME / 'ingestion.sqlite')
    model = QACatalog(RUNTIME / 'catalog.sqlite', ingestion=journal)
    app = create_personal_app(ROOT, runtime=RUNTIME, catalog=model)
    uvicorn.run(app, host='127.0.0.1', port=8793)


if __name__ == '__main__':
    command = sys.argv[1] if len(sys.argv) == 2 else ''
    {'seed': seed, 'revise': revise, 'missing': missing_definition, 'serve': serve}[command]()
