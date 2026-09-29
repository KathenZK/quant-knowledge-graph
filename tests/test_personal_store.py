"""Personal persistence uses synthetic definitions; source/artifact isolation is explicit."""
from copy import deepcopy
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from quantgraph.api.personal import install_personal, refresh_duplicates, export_notebook, markdown_export
from quantgraph.graph.catalog import CatalogRepository
from quantgraph.graph.catalog_projection import item
from quantgraph.graph.grokbot import content_hash
from quantgraph.graph.personal_store import PersonalStore
from quantgraph.models.factor_study import ResearchRequest


def definition(eid='test:a', *, name='测试均线', rule='收盘价超过 20 日均线则买入', rev='revision-1', native=None):
    return item('strategy', eid, name, 'StrategyVariant', rev,
        source_name='测试来源', source_url='https://example.org/paper?id=12#rule',
        source_native_ids=native or [eid], source_sha256='a'*64,
        strategy={'original_rule': rule, 'template_id': 'template:test', 'unknowns': ['执行时间未说明']},
        parameters={'window': 20}, required_fields=['close'])


class Catalog:
    def __init__(self, values):
        self.items = {i['entity_id']: i for i in values}

    def get(self, eid):
        return deepcopy(self.items[eid])

    def all_items(self):
        return list(self.items.values())

    def detail(self, kind, eid):
        return self.get(eid)


@pytest.fixture
def store(tmp_path):
    return PersonalStore(tmp_path / 'personal.sqlite')


def reviewed_restore(store, backup, choice=None):
    preview = store.preview_restore(backup)
    assert preview['counts']['invalid'] == 0
    assert not preview['conflicts'] or choice in {'KEEP_LOCAL', 'USE_BACKUP'}
    return store.restore(preview_token=preview['preview_token'],
                         decisions={v['id']: choice for v in preview['conflicts']})


def test_restart_version_pin_and_personal_layer_independence(store):
    source = definition()
    original = deepcopy(source)
    saved = store.update(source, {'note': '我的判断', 'starred': True, 'status': '值得研究', 'tags': ['趋势'], 'group': '价格信号', 'summary': '个人整理'})
    restarted = PersonalStore(store.path)
    assert restarted.get(source)['note'] == '我的判断'
    assert restarted.list(group='价格信号', status='值得研究', starred=True)['total'] == 1
    source['definition_revision'] = 'revision-2'
    saved2 = restarted.update(source, {'questions': '新版本是否改变执行时点？'})
    assert saved2['stable_id'] == saved['stable_id']
    assert saved2['definition_revision'] == 'revision-1'
    assert saved2['current_definition_revision'] == 'revision-2'
    assert saved2['version_changed']
    assert saved2['note'] == '我的判断'
    assert original['strategy'] == source['strategy']
    with pytest.raises(ValueError):
        restarted.update(source, {'note': '不能覆盖'}, definition_revision='not-an-observed-version')
    assert restarted.get(source)['note'] == '我的判断'


def test_legacy_migration_once_preserves_new_notes_and_old_refs(store):
    source = definition()
    store.update(source, {'note': '服务器的新笔记', 'starred': False})
    second = definition('test:b')
    legacy = [{k: row[k] for k in ['kind', 'entity_id', 'entity_type', 'definition_revision', 'name']} |
              {'note': '旧浏览器备注', 'group': '旧分组'} for row in [source, second]]
    first = store.migrate('localStorage-v1', legacy)
    assert first['imported'] == 1 and first['preserved'] == 1
    assert store.migrate('localStorage-v1', legacy)['replayed']
    assert store.list()['total'] == 2
    assert store.get(source)['note'] == '服务器的新笔记'
    assert not store.get(source)['starred']
    assert store.get(second)['starred']
    with pytest.raises(ValueError):
        store.migrate('localStorage-v1', legacy[:1])


def test_reversible_merge_keeps_notes_research_ids_and_manual_decisions(store):
    left, right = definition(), definition('test:b', name='另外名字')
    left['results'] = {'items': [{'run_id': 'historical', 'entity_refs': [{'entity_id': left['entity_id']}]}]}
    immutable = json.dumps(left, sort_keys=True)
    store.update(left, {'note': '左边笔记', 'starred': True})
    store.update(right, {'note': '右边笔记', 'group': '研究组'})
    suggested = store.suggest(left, right, 'SAME_CONTENT_CANDIDATE', '相同规则，仅候选')
    sid = suggested['suggestion_id']
    merged = store.decide(sid, 'confirm', canonical_id=left['entity_id'])
    assert merged['status'] == 'CONFIRMED'
    assert store.resolve(right['entity_id']) == left['entity_id']
    assert store.get(left)['linked_notes'][0]['note'] == '右边笔记'
    assert store.get(right)['note'] == '右边笔记'
    assert json.dumps(left, sort_keys=True) == immutable
    store.suggest(left, right, 'SAME_CONTENT_CANDIDATE', '重新自动扫描')
    assert store.duplicates()['items'][0]['status'] == 'CONFIRMED'
    store.decide(sid, 'undo')
    assert store.resolve(right['entity_id']) == right['entity_id']
    assert store.get(left)['note'] == '左边笔记'
    store.decide(sid, 'reject')
    store.suggest(left, right, 'SAME_CONTENT_CANDIDATE', '再次扫描')
    assert store.duplicates()['items'][0]['status'] == 'REJECTED'


def test_duplicates_only_exact_provenance_auto_merges(store):
    a = definition(native=['same-source-record'])
    b = definition('test:b', name='同原始记录新名字', native=['same-source-record'])
    c = definition('test:c', name='另一来源同内容', native=['different-source-record'])
    c['source_name'] = '另一来源'
    d = definition('test:d', name=a['name'], rule='收盘价低于 10 日均线买入', rev='different')
    d['strategy']['template_id'] = 'different-template'
    catalog = Catalog([a, b, c, d])
    result = refresh_duplicates(catalog, store)
    statuses = {r['classification']: r['status'] for r in result['items']}
    assert statuses['SAME_ORIGINAL_RECORD'] == 'AUTO_MERGED'
    assert statuses['SAME_CONTENT_CANDIDATE'] == 'PENDING'
    assert statuses['NAME_COLLISION'] == 'PENDING'
    assert store.resolve(c['entity_id']) == c['entity_id']
    assert len(catalog.all_items()) == 4
    exact = next(r for r in result['items'] if r['classification'] == 'SAME_ORIGINAL_RECORD')
    store.decide(exact['suggestion_id'], 'undo')
    refresh_duplicates(catalog, store)
    assert store.resolve(b['entity_id']) == b['entity_id']


@pytest.mark.parametrize('classification', ['TEMPLATE_VARIANT', 'NAME_COLLISION'])
def test_confirming_variant_or_collision_keeps_separate_identities(store, tmp_path, classification):
    a = definition()
    b = definition('test:b', rule='收盘低于 10 日均线买入', rev='different-definition')
    catalog = Catalog([a, b])
    original = deepcopy(catalog.items)
    store.update(a, {'note': '20 日原笔记'})
    store.update(b, {'note': '10 日原笔记', 'starred': True})
    sid = store.suggest(a, b, classification, '不同定义，确认其关系不代表同一身份')['suggestion_id']
    app = FastAPI()
    install_personal(app, catalog, store)
    client = TestClient(app)
    result = client.post(f'/v1/personal/duplicates/{sid}/decision', json={'action': 'confirm'}).json()
    assert result['status'] == 'CONFIRMED' and result['relation_only']
    assert result['canonical_id'] is None
    assert store.resolve(a['entity_id']) == a['entity_id']
    assert store.resolve(b['entity_id']) == b['entity_id']
    assert catalog.items == original and len(catalog.all_items()) == 2
    assert store.get(a)['note'] == '20 日原笔记'
    assert store.get(b)['note'] == '10 日原笔记'
    restored = PersonalStore(tmp_path / 'relation-restored.sqlite')
    assert reviewed_restore(restored, store.backup())['verified']
    assert restored.duplicates()['items'][0]['relation_only']
    assert restored.resolve(b['entity_id']) == b['entity_id']
    # An explicitly requested identity override remains separate from relation review.
    merged = client.post(f'/v1/personal/duplicates/{sid}/decision', json={'action': 'merge', 'canonical_id': a['entity_id']}).json()
    assert not merged['relation_only']
    assert store.resolve(b['entity_id']) == a['entity_id']
    assert store.get(b)['note'] == '10 日原笔记'
    store.decide(sid, 'undo')
    assert store.resolve(b['entity_id']) == b['entity_id']
    assert catalog.items == original


def test_backup_isolated_roundtrip_atomic_corruption_and_merge_protection(store, tmp_path):
    a, b = definition(), definition('test:b')
    store.update(a, {'note': '原始笔记'})
    store.update(b, {'note': '合并笔记'})
    candidate = store.suggest(a, b, 'SAME_CONTENT_CANDIDATE', '测试候选')
    store.decide(candidate['suggestion_id'], 'confirm', canonical_id=a['entity_id'])
    backup = store.backup()
    isolated = PersonalStore(tmp_path / 'isolated' / 'restored.sqlite')
    assert reviewed_restore(isolated, backup)['verified']
    assert isolated.get(a)['note'] == '原始笔记'
    assert isolated.resolve(b['entity_id']) == a['entity_id']
    store.update(a, {'note': '备份后的新笔记'})
    reviewed_restore(store, backup, 'KEEP_LOCAL')
    assert store.get(a)['note'] == '备份后的新笔记'
    corrupted = deepcopy(backup)
    corrupted['payload']['items'][0]['note'] = '篡改'
    before = store.backup()['sha256']
    preview = store.preview_restore(corrupted)
    assert preview['counts']['invalid'] > 0 and not preview['can_apply']
    with pytest.raises(ValueError):
        store.restore(preview_token=preview['preview_token'])
    assert before == store.backup()['sha256']
    cyclic = deepcopy(backup)
    cyclic['payload']['redirects'][0]['canonical_id'] = b['entity_id']
    cyclic['sha256'] = content_hash(cyclic['payload'])
    preview = store.preview_restore(cyclic)
    assert preview['counts']['invalid'] > 0 and not preview['can_apply']
    with pytest.raises(ValueError):
        store.restore(preview_token=preview['preview_token'])
    assert before == store.backup()['sha256']
    assert reviewed_restore(store, backup, 'USE_BACKUP')['verified']
    assert store.get(a)['note'] == '原始笔记'


def test_export_complete_compatible_drafts_and_version_mismatch(store):
    value = definition()
    value['relations'] = [{'from_id': value['entity_id'], 'to_id': 'factor:rsi', 'relation': 'USES_FACTOR', 'evidence': '规则明确引用'}]
    value['results'] = {'items': [{'run_id': 'historical-run'}]}
    catalog = Catalog([value])
    store.update(value, {'note': '备注', 'summary': '我的整理', 'reason': '研究理由', 'questions': '可证伪问题', 'problem': '执行时间缺失'})
    exported = export_notebook(catalog, store)
    entry = exported['items'][0]
    for key in ['rule', 'sources', 'parameters', 'required_fields', 'known_issues', 'related_methods', 'research_references', 'questions']:
        assert entry[key]
    assert ResearchRequest.model_validate(exported['research_requests'][0]).status == 'DRAFT'
    markdown = markdown_export(exported)
    assert '我的整理' in markdown and 'historical-run' in markdown and value['definition_revision'] in markdown
    catalog.items[value['entity_id']]['definition_revision'] = 'revision-2'
    catalog.items[value['entity_id']]['strategy']['original_rule'] = '全新规则'
    stale = export_notebook(catalog, store)
    assert stale['research_requests'] == []
    assert stale['items'][0]['rule'] is None
    assert stale['items'][0]['definition_revision'] == 'revision-1'
    assert stale['items'][0]['current_definition_snapshot']['strategy']['original_rule'] == '全新规则'
    assert stale['items'][0]['availability'] == 'PINNED_DEFINITION_UNAVAILABLE'


def test_api_browser_independence_restore_validation_and_selected_export(store):
    value = definition()
    app = FastAPI()
    install_personal(app, Catalog([value]), store)
    first, other = TestClient(app), TestClient(app)
    path = '/v1/personal/items/strategy/' + value['entity_id']
    assert first.put(path, json={'starred': True, 'note': '跨浏览器保留', 'status': '值得研究'}).status_code == 200
    assert other.get(path).json()['note'] == '跨浏览器保留'
    assert other.get('/v1/personal/items?status=值得研究').json()['total'] == 1
    assert first.put(path, json={'status': '未知状态'}).status_code == 422
    assert first.put(path, json={'visibility': 'PUBLIC'}).status_code == 422
    assert first.put(path, json={'entity_id': 'wrong'}).status_code == 422
    assert first.get('/v1/personal/items/variant/' + value['entity_id']).status_code == 404
    invalid = first.post('/v1/personal/restore/preview', json={'backup': {'scope': 'PUBLIC'}}).json()
    assert invalid['counts']['invalid'] == 1
    assert first.post('/v1/personal/restore', json={'preview_token': invalid['preview_token']}).status_code == 422
    response = first.post('/v1/personal/export', json={'ids': [value['entity_id']], 'format': 'markdown'})
    assert response.status_code == 200 and '跨浏览器保留' in response.text
    assert first.get('/v1/personal/export?format=bad').status_code == 422


@pytest.mark.parametrize('selected_id', ['test:historical', 'test:current'])
def test_missing_pinned_definition_current_snapshot_matches_current_reference(store, selected_id):
    pinned = definition('test:historical', rev='revision-missing', rule='缺失版本的原规则')
    historical = definition('test:historical', rev='revision-historical', rule='可读历史版本规则')
    current = definition('test:current', rev='revision-current', rule='真实当前版本规则')
    for value in [pinned, historical, current]:
        value['stable_knowledge_id'] = 'test:lineage'
    historical['current_entity_id'] = current['entity_id']
    current['prior_version_ids'] = [historical['entity_id']]
    store.update(pinned, {'note': '必须保留缺失版本的笔记'})

    class MissingVersionCatalog(Catalog):
        def detail_version(self, kind, eid, revision):
            raise KeyError(revision)

        def detail(self, kind, eid):
            return super().detail(kind, eid) | {'detail_marker': 'detail:' + eid}

    exported = export_notebook(MissingVersionCatalog([historical, current]), store, ids=[selected_id])
    record = exported['items'][0]
    assert record['availability'] == 'PINNED_DEFINITION_UNAVAILABLE'
    assert record['original_note_ref']['entity_id'] == pinned['entity_id']
    assert record['original_note_ref']['definition_revision'] == 'revision-missing'
    assert record['note'] == '必须保留缺失版本的笔记'
    assert record['rule'] is None and record['formula'] is None
    assert exported['research_requests'] == []
    snapshot = record['current_definition_snapshot']
    assert {key: snapshot[key] for key in ['entity_type', 'entity_id', 'definition_revision']} == record['current_definition_ref']
    assert snapshot['entity_id'] == current['entity_id']
    assert snapshot['strategy']['original_rule'] == '真实当前版本规则'
    assert snapshot['detail_marker'] == 'detail:test:current'
    assert '- 资料状态：PINNED_DEFINITION_UNAVAILABLE' in markdown_export(exported).splitlines()
    assert '固定定义缺失，仅保留原引用，未生成对应研究请求；未用新规则代替旧定义。' in markdown_export(exported)


def test_removed_catalog_source_export_keeps_reference_and_explains_missing_definition(store):
    pinned = definition()
    store.update(pinned, {'note': '来源移除也须保留'})
    exported = export_notebook(Catalog([]), store)
    record = exported['items'][0]
    assert record['availability'] == 'SOURCE_NO_LONGER_IN_CURRENT_CATALOG'
    assert record['original_note_ref']['definition_revision'] == pinned['definition_revision']
    assert record['note'] == '来源移除也须保留'
    assert record['rule'] is None and record['formula'] is None
    assert record['current_definition_ref'] is None and record['current_definition_snapshot'] is None
    assert exported['research_requests'] == []
    assert '- 资料状态：SOURCE_NO_LONGER_IN_CURRENT_CATALOG' in markdown_export(exported).splitlines()
    assert '固定定义缺失，仅保留原引用，未生成对应研究请求；未用新规则代替旧定义。' in markdown_export(exported)


def test_catalog_incremental_updates_cannot_overwrite_notes_or_merge(store, tmp_path):
    catalog = CatalogRepository(tmp_path / 'catalog.sqlite')
    a, b = definition(), definition('test:b')
    with catalog.connect() as con:
        catalog._put(con, a, 'synthetic-source', {'raw': '原始规则'})
        catalog._put(con, b, 'synthetic-source', {'raw': '另一原始规则'})
    store.update(a, {'note': '必须保留', 'aliases': ['个人别名']})
    suggestion = store.suggest(a, b, 'SAME_CONTENT_CANDIDATE', '人工确认')
    store.decide(suggestion['suggestion_id'], 'confirm', canonical_id=a['entity_id'])
    changed = deepcopy(a)
    changed['definition_revision'] = 'revision-2'
    changed['name'] = '来源修订名称'
    with catalog.connect() as con:
        catalog._put(con, changed, 'synthetic-source', {'raw': '修订规则'})
        catalog._put(con, changed, 'synthetic-source', {'raw': '修订规则'})
        assert con.execute('SELECT count(*) FROM catalog_versions WHERE entity_id=?', (a['entity_id'],)).fetchone()[0] == 2
    assert store.get(catalog.get(a['entity_id']))['note'] == '必须保留'
    assert store.get(catalog.get(a['entity_id']))['version_changed']
    assert store.resolve(b['entity_id']) == a['entity_id']
    assert catalog.search(q='来源修订名称')['total'] == 1


def test_real_ingestion_id_revision_retains_note_pinned_export_and_history(store, tmp_path):
    """Exercise the real parser and import pipeline, not direct projection edits."""
    from quantgraph.graph.ingestion_store import SQLiteIngestionRepository
    from quantgraph.graph.personal_catalog import PersonalCatalogRepository
    from quantgraph.models.ingestion import IngestBatch

    ingestion = SQLiteIngestionRepository(tmp_path / 'ingestion.sqlite')
    catalog = PersonalCatalogRepository(tmp_path / 'catalog.sqlite', ingestion=ingestion)
    catalog.personal_store = store
    def ingest(threshold):
        body = {'batch_id': f'revision-{threshold}', 'collector_version': 'test-pipeline-v1', 'records': [
            {'record_id': 'PERSONAL-REVISION-TEST', 'name': 'RSI 修订保护测试', 'source_url': 'https://example.org/rule?id=1#rsi',
             'raw_market': '美股 ETF', 'raw_rule': f'日频：若 RSI(7)>{threshold} → 满仓 QQQ，否则 SHV。',
             'collected_at': '2026-09-28T00:00:00Z'}]}
        result = ingestion.ingest(IngestBatch.model_validate(body), json.dumps(body).encode(), 'test')
        catalog.sync_ingestion()
        return result

    ingest(53)
    original = catalog.search(kind='strategy')['items'][0]
    store.update(original, {'note': '原始阈值笔记', 'starred': True, 'status': '值得研究', 'group': 'RSI 主题', 'aliases': ['个人检索名']})
    assert catalog.search(q='个人检索名', kind='strategy')['total'] == 1
    ingest(55)
    changed = catalog.search(kind='strategy')['items'][0]
    assert changed['entity_id'] != original['entity_id']
    assert changed['stable_knowledge_id'] == original['stable_knowledge_id']
    preserved = store.get(changed)
    assert preserved['entity_id'] == original['entity_id']
    assert preserved['note'] == '原始阈值笔记' and preserved['version_changed']
    assert preserved['definition_revision'] == original['definition_revision']
    store.update(changed, {'questions': '新阈值会怎样？'})
    assert store.list()['total'] == 1
    assert store.get(changed)['note'] == '原始阈值笔记'
    assert ingest(55)['replayed']
    assert catalog.search(kind='strategy')['total'] == 1
    assert catalog.get(original['entity_id'])['is_historical']
    assert catalog.search(q='个人检索名', kind='strategy')['total'] == 1
    exported = export_notebook(catalog, store, ids=[changed['entity_id']])
    entry = exported['items'][0]
    assert entry['definition_revision'] == original['definition_revision']
    assert entry['entity_id'] == original['entity_id']
    assert '53' in entry['rule'] and '55' not in entry['rule']
    assert entry['current_definition_ref']['entity_id'] == changed['entity_id']
    assert ResearchRequest.model_validate(exported['research_requests'][0]).entity_refs[0].entity_id == original['entity_id']
    default_export = export_notebook(catalog, store)['items'][0]
    assert default_export['current_definition_ref']['entity_id'] == changed['entity_id']
    assert default_export['version_changed']
    assert '53' in default_export['rule']
    # A separate process/browser view still follows lineage, without duplicating notes.
    restarted = PersonalStore(store.path)
    assert restarted.get(changed)['note'] == '原始阈值笔记'


def test_incremental_exact_duplicate_keeps_established_canonical(store):
    a = definition('b-established', native=['original-record'])
    b = definition('c-duplicate', native=['original-record'])
    catalog = Catalog([a, b])
    refresh_duplicates(catalog, store)
    assert store.resolve(b['entity_id']) == a['entity_id']
    new = definition('a-new-sort-first', native=['original-record'])
    catalog.items[new['entity_id']] = new
    refresh_duplicates(catalog, store)
    assert store.resolve(new['entity_id']) == a['entity_id']
    assert store.resolve(b['entity_id']) == a['entity_id']
    assert store.resolve(a['entity_id']) == a['entity_id']


def test_restore_conflicting_merges_preserves_current_and_audits_backup(store, tmp_path):
    a, b, c = definition('a'), definition('b'), definition('c')
    local = store.suggest(a, c, 'LOCAL_CHOICE', '本机确认 a 为主')
    store.decide(local['suggestion_id'], 'confirm', canonical_id='a')
    other = PersonalStore(tmp_path / 'other.sqlite')
    remote = other.suggest(b, c, 'BACKUP_CHOICE', '备份确认 b 为主')
    other.decide(remote['suggestion_id'], 'confirm', canonical_id='b')
    preview = store.preview_restore(other.backup())
    conflict = next(v for v in preview['conflicts'] if v['section'] == 'relationships')
    assert conflict['local']['redirects'][0]['canonical_id'] == 'a'
    assert conflict['backup']['redirects'][0]['canonical_id'] == 'b'
    store.restore(preview_token=preview['preview_token'], decisions={conflict['id']: 'KEEP_LOCAL'})
    assert store.resolve('c') == 'a'
    retained = store.restore_report(preview['preview_token'])['conflicts'][0]['backup']['duplicates'][0]
    assert retained['status'] == 'CONFIRMED' and retained['canonical_id'] == 'b'
    audit = store.backup()['payload']['audit']
    assert any(row['action'] == 'RESTORE_REVIEWED' and row['detail']['decisions'][conflict['id']] == 'KEEP_LOCAL' for row in audit)
    reviewed_restore(store, other.backup(), 'USE_BACKUP')
    assert store.resolve('c') == 'b'
