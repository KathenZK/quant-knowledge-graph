"""Personal restore acceptance: all databases here are isolated pytest copies."""
from copy import deepcopy
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from quantgraph.api.personal import install_personal, export_notebook
from quantgraph.graph.grokbot import content_hash
from quantgraph.graph.personal_restore import RestoreConflict, MAX_BACKUP_BYTES
from quantgraph.graph.personal_store import PersonalStore, blank
from test_personal_store import Catalog, definition


@pytest.fixture
def pair(tmp_path):
    return PersonalStore(tmp_path/'local.sqlite'), PersonalStore(tmp_path/'source.sqlite')


def rehash(backup):
    backup['sha256'] = content_hash(backup['payload'])
    return backup


def choose(preview, action):
    return {conflict['id']: action for conflict in preview['conflicts']}


def apply(store, backup, choice=None):
    preview = store.preview_restore(backup)
    assert preview['can_apply'], preview['invalid']
    assert not preview['conflicts'] or choice in {'KEEP_LOCAL', 'USE_BACKUP'}
    return store.restore(preview_token=preview['preview_token'], decisions=choose(preview, choice))


@pytest.mark.parametrize('local_time,backup_time', [
    ('2025-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'),
    ('2026-01-01T00:00:00+00:00', '2025-01-01T00:00:00+00:00'),
    ('2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'),
    ('2026-01-01T08:00:00+08:00', '2026-01-01T00:00:00Z'),
])
def test_newer_older_same_time_and_timezone_never_choose_implicitly(pair, local_time, backup_time):
    local, other = pair
    item = definition()
    local.update(item, {'note': '本机文本'})
    other.update(item, {'note': '备份文本'})
    with local.connect() as con:
        value = json.loads(con.execute('SELECT payload FROM personal_items').fetchone()[0])
        value['updated_at'] = local_time
        con.execute('UPDATE personal_items SET payload=?', (json.dumps(value),))
    backup = other.backup()
    backup['payload']['items'][0]['updated_at'] = backup_time
    rehash(backup)
    before = local.backup()['sha256']
    preview = local.preview_restore(backup)
    assert local.backup()['sha256'] == before
    assert preview['sections']['items'] == dict(added=0, identical=0, conflicts=1, invalid=0)
    conflict = next(v for v in preview['conflicts'] if v['section'] == 'items')
    assert conflict['local']['note'] == '本机文本' and conflict['backup']['note'] == '备份文本'
    assert conflict['timestamps']['local']['updated_at'] == local_time
    assert conflict['timestamps']['backup']['updated_at'] == backup_time
    with pytest.raises(RestoreConflict, match='还有冲突'):
        local.restore(preview_token=preview['preview_token'])
    assert local.backup()['sha256'] == before
    result = local.restore(preview_token=preview['preview_token'], decisions=choose(preview, 'KEEP_LOCAL'))
    assert result['verified'] and local.get(item)['note'] == '本机文本'
    assert local.restore_report(preview['preview_token'])['conflicts'][0]['backup']['note'] == '备份文本'
    apply(local, backup, 'USE_BACKUP')
    assert local.get(item)['note'] == '备份文本'


@pytest.mark.parametrize('stamp,expected', [(None, 'MISSING'), ('not-a-time', 'INVALID'), ('2026-01-01T00:00:00', 'INVALID')])
def test_missing_or_invalid_time_is_preserved_not_used_to_decide(pair, stamp, expected):
    local, other = pair
    item = definition()
    local.update(item, {'note': '本机'})
    other.update(item, {'note': '备份'})
    backup = other.backup()
    row = backup['payload']['items'][0]
    if stamp is None:
        row.pop('updated_at')
        row.pop('created_at')
    else:
        row['updated_at'] = stamp
    preview = local.preview_restore(rehash(backup))
    assert preview['can_apply'] and preview['counts']['conflicts'] == 1
    conflict = preview['conflicts'][0]
    assert conflict['timestamps']['backup']['status'] == expected
    apply(local, backup, 'USE_BACKUP')
    assert local.get(item)['note'] == '备份'
    assert local.get(item)['updated_at'] == stamp


def test_identical_content_and_repeated_restore_do_not_duplicate(pair):
    local, other = pair
    item = definition()
    other.update(item, {'note': '同一内容', 'starred': True})
    backup = other.backup()
    preview = local.preview_restore(backup)
    assert preview['sections']['items']['added'] == 1
    result = local.restore(preview_token=preview['preview_token'])
    before = local.backup()['sha256']
    replay = local.restore(preview_token=preview['preview_token'])
    assert replay == result | {'replayed': True}
    assert before == local.backup()['sha256']
    second = local.preview_restore(backup)
    assert second['sections']['items']['identical'] == 1 and not second['conflicts']
    local.restore(preview_token=second['preview_token'])
    assert local.list()['total'] == 1
    assert before == local.backup()['sha256']
    changed_time = deepcopy(backup)
    changed_time['payload']['items'][0]['updated_at'] = '2030-01-01T00:00:00+00:00'
    changed_time['payload']['items'][0]['record_revision'] = 100
    p = local.preview_restore(rehash(changed_time))
    assert p['sections']['items']['identical'] == 1 and not p['conflicts']


@pytest.mark.parametrize('different', [False, True])
def test_duplicate_backup_primary_keys_are_invalid_and_no_partial_restore(pair, different):
    local, other = pair
    other.update(definition(), {'note': '原件'})
    backup = other.backup()
    extra = deepcopy(backup['payload']['items'][0])
    if different:
        extra['note'] = '同键另一份'
    backup['payload']['items'].append(extra)
    before = local.backup()['sha256']
    preview = local.preview_restore(rehash(backup))
    assert not preview['can_apply'] and preview['counts']['invalid'] == 1
    assert '重复主键' in preview['invalid'][0]['reason']
    with pytest.raises(ValueError):
        local.restore(preview_token=preview['preview_token'])
    assert local.backup()['sha256'] == before


def test_v1_compatibility_and_explicit_future_or_unknown_rejection(pair):
    local, other = pair
    other.update(definition(), {'note': '旧格式'})
    old = other.backup()
    old['schema_version'] = 'quantgraph-personal-backup/v1'
    for row in old['payload']['items']:
        row.pop('record_revision')
    apply(local, rehash(old))
    assert local.get(definition())['record_revision'] == 0
    assert local.backup()['schema_version'] == 'quantgraph-personal-backup/v2'
    for version in ['quantgraph-personal-backup/v0', 'quantgraph-personal-backup/v3']:
        invalid = deepcopy(old)
        invalid['schema_version'] = version
        before = local.backup()['sha256']
        preview = local.preview_restore(invalid)
        assert not preview['can_apply'] and '不支持' in preview['invalid'][0]['reason']
        with pytest.raises(ValueError):
            local.restore(preview_token=preview['preview_token'])
        assert local.backup()['sha256'] == before


def test_corruption_invalid_record_and_size_limit_leave_database_unchanged(pair):
    local, other = pair
    local.update(definition('local'), {'note': '必须保留'})
    other.update(definition('new-a'), {'note': 'A'})
    other.update(definition('new-b'), {'note': 'B'})
    original = other.backup()
    cases = []
    corruption = deepcopy(original)
    corruption['payload']['items'][0]['note'] = '不更新摘要的篡改'
    cases.append(corruption)
    invalid = deepcopy(original)
    invalid['payload']['items'][1]['status'] = '无效状态'
    cases.append(rehash(invalid))
    oversized = deepcopy(original)
    oversized['payload']['audit'][0]['detail']['large'] = 'x' * MAX_BACKUP_BYTES
    cases.append(rehash(oversized))
    before = local.backup()['sha256']
    for backup in cases:
        preview = local.preview_restore(backup)
        assert preview['counts']['invalid'] and not preview['can_apply']
        with pytest.raises(ValueError):
            local.restore(preview_token=preview['preview_token'])
        assert local.backup()['sha256'] == before


def test_restored_definition_reference_favorites_groups_and_old_identity_stay_bound(pair):
    local, other = pair
    old = definition('source:old', rev='old-definition')
    old['stable_knowledge_id'] = 'source:native-1'
    new = definition('source:new', rev='new-definition', rule='另一版本规则')
    new['stable_knowledge_id'] = old['stable_knowledge_id']
    local.update(new, {'note': '当前版本备注'})
    other.update(old, {'note': '原版本备注', 'starred': True, 'group': '主题', 'tags': ['窗口'],
        'status': '值得研究', 'summary': '整理', 'reason': '理由', 'questions': '问题', 'aliases': ['别名'], 'problem': '出处待核对'})
    preview = local.preview_restore(other.backup())
    conflict = preview['conflicts'][0]
    assert conflict['versions']['local']['definition_revision'] == 'new-definition'
    assert conflict['versions']['backup']['definition_revision'] == 'old-definition'
    assert conflict['identity']['stable_id'] == blank(old)['stable_id']
    local.restore(preview_token=preview['preview_token'], decisions=choose(preview, 'USE_BACKUP'))
    value = local.get(new)
    assert value['entity_id'] == 'source:old' and value['definition_revision'] == 'old-definition'
    assert value['version_changed'] and value['starred'] and value['group'] == '主题'
    for field in ['note', 'tags', 'status', 'summary', 'reason', 'questions', 'aliases', 'problem']:
        assert value[field] == other.get(old)[field]
    assert local.list()['total'] == 1
    export = export_notebook(Catalog([new]), local, ids=[new['entity_id']])
    assert export['items'][0]['definition_revision'] == 'old-definition'
    assert export['items'][0]['availability'] == 'PINNED_DEFINITION_UNAVAILABLE'
    assert export['items'][0]['rule'] is None
    assert local.restore_report(preview['preview_token'])['conflicts'][0]['local']['note'] == '当前版本备注'


def test_before_restore_backup_survives_restart_and_failure_rolls_back(pair, monkeypatch):
    local, other = pair
    item = definition()
    local.update(item, {'note': '恢复前'})
    other.update(item, {'note': '恢复后'})
    preview = local.preview_restore(other.backup())
    before = local.backup()
    audit = local._audit
    def fail_after_write(con, action, detail):
        assert json.loads(con.execute('SELECT payload FROM personal_items').fetchone()[0])['note'] == '恢复后'
        raise RuntimeError('注入事务内失败')
    monkeypatch.setattr(local, '_audit', fail_after_write)
    with pytest.raises(RuntimeError, match='事务内失败'):
        local.restore(preview_token=preview['preview_token'], decisions=choose(preview, 'USE_BACKUP'))
    assert local.backup()['sha256'] == before['sha256']
    assert local.restore_report(preview['preview_token'])['status'] == 'PREVIEW'
    monkeypatch.setattr(local, '_audit', audit)
    result = local.restore(preview_token=preview['preview_token'], decisions=choose(preview, 'USE_BACKUP'))
    restarted = PersonalStore(local.path)
    assert restarted.restore_backup(result['pre_restore_backup']['id'])['sha256'] == before['sha256']
    assert restarted.restore_report(preview['preview_token'])['result']['verified']
    assert restarted.get(item)['note'] == '恢复后'


def test_preview_concurrent_writer_and_changed_upload_cannot_overwrite(pair):
    local, other = pair
    item = definition()
    local.update(item, {'note': '本机'})
    other.update(item, {'note': '备份'})
    backup = other.backup()
    preview = local.preview_restore(backup)
    PersonalStore(local.path).update(item, {'note': '预览后的更新'})
    before = local.backup()['sha256']
    with pytest.raises(RestoreConflict, match='已有变化'):
        local.restore(preview_token=preview['preview_token'], decisions=choose(preview, 'USE_BACKUP'))
    assert local.backup()['sha256'] == before
    fresh = local.preview_restore(backup)
    other.update(item, {'note': '另一个上传'})
    with pytest.raises(RestoreConflict, match='文件与预览不一致'):
        local.restore(other.backup(), preview_token=fresh['preview_token'], decisions=choose(fresh, 'USE_BACKUP'))
    assert local.get(item)['note'] == '预览后的更新'


def test_failure_to_create_restore_point_prevents_any_write(pair, monkeypatch):
    import quantgraph.graph.personal_restore as restore
    local, other = pair
    other.update(definition(), {'note': '不能先写入'})
    preview = local.preview_restore(other.backup())
    before = local.backup()['sha256']
    def fail(*args):
        raise OSError('备份目录不可写')
    monkeypatch.setattr(restore, '_save_point', fail)
    with pytest.raises(OSError):
        local.restore(preview_token=preview['preview_token'])
    assert local.backup()['sha256'] == before and local.list()['total'] == 0


def test_api_preview_report_choices_download_and_legacy_rejection(pair):
    local, other = pair
    item = definition()
    local.update(item, {'note': '本机'})
    other.update(item, {'note': '备份'})
    app = FastAPI()
    install_personal(app, Catalog([item]), local)
    client = TestClient(app)
    backup = other.backup()
    assert client.post('/v1/personal/restore', json={'backup': backup, 'mode': 'replace'}).status_code == 409
    preview = client.post('/v1/personal/restore/preview', json={'backup': backup}).json()
    token = preview['preview_token']
    assert client.get('/v1/personal/restore/reports/'+token).json() == preview
    assert client.post('/v1/personal/restore', json={'preview_token': token}).status_code == 409
    decisions = choose(preview, 'USE_BACKUP')
    response = client.post('/v1/personal/restore', json={'preview_token': token, 'decisions': decisions})
    assert response.status_code == 200
    result = response.json()
    restored_point = client.get(result['pre_restore_backup']['download_url'])
    assert restored_point.status_code == 200
    assert restored_point.json()['payload']['items'][0]['note'] == '本机'
    assert client.get('/v1/personal/restore/reports/'+token).json()['status'] == 'APPLIED'
    assert client.post('/v1/personal/restore', json={'preview_token': token, 'decisions': decisions}).json()['replayed']
    assert local.get(item)['note'] == '备份'
    assert client.get('/v1/personal/restore/backups/not-a-token').status_code == 404


def test_existing_database_v1_upgrades_without_rewriting_note(tmp_path):
    import sqlite3
    path = tmp_path/'legacy.sqlite'
    store = PersonalStore(path)
    item = definition()
    store.update(item, {'note': '旧数据库原文'})
    with store.connect() as con:
        value = json.loads(con.execute('SELECT payload FROM personal_items').fetchone()[0])
        value.pop('record_revision')
        original = json.dumps(value, ensure_ascii=False)
        con.execute('UPDATE personal_items SET payload=?', (original,))
        con.execute('DROP TABLE personal_restore_plans')
        con.execute('PRAGMA user_version=1')
    upgraded = PersonalStore(path)
    with sqlite3.connect(path) as con:
        assert con.execute('PRAGMA user_version').fetchone()[0] == 2
        assert con.execute('SELECT payload FROM personal_items').fetchone()[0] == original
    assert upgraded.get(item)['note'] == '旧数据库原文'
    assert upgraded.get(item)['record_revision'] == 0


def test_multiple_note_versions_in_a_lineage_are_retained_and_selected_together(pair):
    local, other = pair
    first, second = definition('old-a', rev='v1'), definition('old-b', rev='v2')
    first['stable_knowledge_id'] = second['stable_knowledge_id'] = 'shared-native'
    other.update(first, {'note': '旧版本第一份'})
    backup = other.backup()
    extra = blank(second) | {'note': '旧版本第二份', 'created_at': '2025-01-01T00:00:00Z', 'updated_at': None}
    backup['payload']['items'].append(extra)
    local.update(second, {'note': '本机版本'})
    preview = local.preview_restore(rehash(backup))
    assert preview['counts']['conflicts'] == 1
    assert len(preview['conflicts'][0]['backup_records']) == 2
    local.restore(preview_token=preview['preview_token'], decisions=choose(preview, 'USE_BACKUP'))
    rows = {row['entity_id']: row for row in local.list()['items']}
    assert rows[first['entity_id']]['note'] == '旧版本第一份'
    assert rows[second['entity_id']]['note'] == '旧版本第二份'
    assert rows[first['entity_id']]['definition_revision'] == 'v1'
    assert rows[second['entity_id']]['definition_revision'] == 'v2'
    kept = local.restore_report(preview['preview_token'])['conflicts'][0]['local_records']
    assert kept[0]['note'] == '本机版本'


def test_forged_canonical_target_rejected_even_when_digest_and_decision_agree(pair):
    local, other = pair
    a, b = definition('a'), definition('b')
    decision = other.suggest(a, b, 'SAME_CONTENT_CANDIDATE', '人工身份确认')
    other.decide(decision['suggestion_id'], 'confirm', canonical_id='a')
    backup = other.backup()
    backup['payload']['duplicates'][0]['canonical_id'] = 'missing-entity'
    backup['payload']['redirects'][0]['canonical_id'] = 'missing-entity'
    rehash(backup)
    before = local.backup()['sha256']
    with pytest.raises(ValueError, match='合并目标'):
        local.validate_backup(backup)
    preview = local.preview_restore(backup)
    assert not preview['can_apply'] and preview['counts']['invalid'] == 1
    with pytest.raises(ValueError):
        local.restore(preview_token=preview['preview_token'])
    assert local.backup()['sha256'] == before


def test_multi_step_canonical_outside_current_pair_remains_valid(pair):
    local, other = pair
    a, b, c = definition('a'), definition('b'), definition('c')
    first = other.suggest(a, b, 'SAME_CONTENT_CANDIDATE', '首个身份确认')
    other.decide(first['suggestion_id'], 'confirm', canonical_id='a')
    second = other.suggest(b, c, 'SAME_CONTENT_CANDIDATE', '后续身份确认')
    other.decide(second['suggestion_id'], 'confirm', canonical_id='b')
    backup = other.backup()
    second_record = next(v for v in backup['payload']['duplicates'] if v['suggestion_id'] == second['suggestion_id'])
    assert second_record['canonical_id'] == 'a'
    assert 'a' not in {second_record['left']['entity_id'], second_record['right']['entity_id']}
    local.validate_backup(backup)
    apply(local, backup)
    assert local.resolve('b') == 'a' and local.resolve('c') == 'a'
