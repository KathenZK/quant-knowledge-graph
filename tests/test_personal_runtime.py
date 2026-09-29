"""The explicit runtime backup retains recovery points without copying unrelated files."""
import json
import sqlite3
import pytest
from scripts.personal_runtime import initialize


def test_backup_includes_committed_wal_and_recovery_point(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    with sqlite3.connect(source / 'catalog.sqlite') as con:
        con.execute('PRAGMA journal_mode=WAL')
        con.execute('CREATE TABLE original(value TEXT)')
        con.execute("INSERT INTO original VALUES('committed')")
        con.commit()
        points = source / 'restore-backups'
        points.mkdir()
        identifier = 'a' * 32 + '.json'
        (points / identifier).write_text('{"original":"backup"}')
        (source / 'config.json').write_text('{"private":"unrelated"}')
        result = initialize(source, tmp_path / 'copy')
    with sqlite3.connect(tmp_path / 'copy/catalog.sqlite') as copied:
        assert copied.execute('SELECT value FROM original').fetchone()[0] == 'committed'
    assert (tmp_path / 'copy/restore-backups' / identifier).read_bytes() == (points / identifier).read_bytes()
    assert result['recovery_points'][0]['name'] == identifier
    assert not (tmp_path / 'copy/config.json').exists()
    assert json.loads((tmp_path / 'copy/snapshot.json').read_text())['recovery_points']
    with pytest.raises(ValueError, match='existing personal data is never overwritten'):
        initialize(source, tmp_path / 'copy')
