"""Read all retained journals without executing or inventing pinned definitions."""
import json
import sqlite3

from quantgraph.graph.personal_research import RetainedResearch, safe_metadata


def journal(path, table, values):
    with sqlite3.connect(path) as con:
        con.execute(f'CREATE TABLE {table}(payload TEXT)')
        con.executemany(f'INSERT INTO {table} VALUES(?)', [(json.dumps(v),) for v in values])


def test_metadata_credentials_are_redacted_recursively():
    result = safe_metadata({'metrics': {'IC': 0.1}, 'nested': [
        {key: 'DO_NOT_DISPLAY' for key in ['access_token', 'refresh-token', 'api-key', 'apiKey',
         'clientSecret', 'private_key', 'Authorization', 'sessionCookie']}],
        'source': 'https://example.org/paper?id=7&token=DO_NOT_DISPLAY#section'})
    assert 'DO_NOT_DISPLAY' not in json.dumps(result)
    assert result['metrics'] == {'IC': 0.1}
    assert 'id=7' in result['source'] and '#section' in result['source']


def test_standalone_journals_are_read_without_jobs_or_false_versions(tmp_path):
    journal(tmp_path / 'factor-studies.sqlite', 'studies', [dict(run_id='factor-run',
        mapping={'identity': {'factor_variant_id': 'factor-1', 'definition_revision': 'v1'}},
        results={'IC': 0.1, 'nested': {'api_key': 'DO_NOT_DISPLAY'}}, limitations=['small sample'])])
    journal(tmp_path / 'ingestion.sqlite', 'evidence', [dict(run_id='legacy-run',
        source_strategy_ids=['strategy-1'], results={'return': 0.2})])
    reader = RetainedResearch(tmp_path)
    result = reader()
    assert result['total'] == 2
    assert 'DO_NOT_DISPLAY' not in json.dumps(result)
    factor = reader(eid='factor-1')['items'][0]
    assert factor['entity_refs'][0]['definition_revision'] == 'v1'
    legacy = reader(eid='strategy-1')['items'][0]
    assert legacy['entity_refs'][0]['definition_revision'] == 'NOT_PINNED_IN_EVIDENCE'
    assert legacy['promotion_allowed'] is False and legacy['job_id'] is None
    assert any('未固定定义版本' in text for text in legacy['limitations'])


def test_duplicate_run_references_preserve_extra_entities_and_refresh_wal(tmp_path):
    con = sqlite3.connect(tmp_path / 'jobs.sqlite')
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA wal_autocheckpoint=0')
    con.execute('CREATE TABLE research_jobs(job_id TEXT,status TEXT,results TEXT,created INTEGER)')
    value = dict(run_id='same-run', study_metadata={'entity_refs': [dict(entity_type='StrategyVariant',
        entity_id='strategy-1', definition_revision='v1')], 'public_summary': {'metrics': {'return': 0.1}}})
    con.execute('INSERT INTO research_jobs VALUES(?,?,?,?)', ('job-1', 'completed', json.dumps([value]), 1))
    con.commit()
    journal(tmp_path / 'factor-studies.sqlite', 'studies', [
        dict(run_id='same-run', mapping={'identity': {'factor_variant_id': 'factor-1', 'definition_revision': 'v1'}}),
        dict(run_id='same-run', mapping={'identity': {'factor_variant_id': 'factor-1', 'definition_revision': 'v2'}}),
    ])
    # Same ID with an unpinned original journal is also retained, not labelled v1.
    journal(tmp_path / 'ingestion.sqlite', 'evidence', [
        dict(run_id='same-run', source_strategy_ids=['strategy-1']),
    ])
    reader = RetainedResearch(tmp_path)
    assert reader()['total'] == 4
    assert reader()['input_counts']['duplicate_run_references'] == 0
    assert reader(eid='factor-1')['total'] == 2
    assert {x['entity_refs'][0]['definition_revision'] for x in reader(eid='factor-1')['items']} == {'v1', 'v2'}
    assert reader(eid='strategy-1')['total'] == 2
    value['run_id'] = 'next-run'
    con.execute('INSERT INTO research_jobs VALUES(?,?,?,?)', ('job-2', 'completed', json.dumps([value]), 2))
    con.commit()
    assert reader()['total'] == 5
    assert reader()['input_counts']['distinct_run_ids'] == 2
    con.close()
