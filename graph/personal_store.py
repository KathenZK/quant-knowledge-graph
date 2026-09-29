"""Private local notebook and reversible identity decisions.

This database is an overlay: it never writes source bytes, catalog definitions,
research artifacts, or public permissions. Merges retain every original record.
"""
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
from uuid import uuid4

from quantgraph.graph.grokbot import stable_json, content_hash
from quantgraph.graph.ingestion_store import now

STATUSES = ['待读', '已理解', '值得研究', '重复方法', '暂不研究']
KINDS = {'strategy', 'variant', 'concept', 'family', 'template', 'source'}
PERSONAL_FIELDS = {'starred', 'status', 'tags', 'group', 'note', 'summary', 'questions', 'reason', 'aliases', 'problem'}
IDENTITY_FIELDS = {'kind', 'entity_id', 'entity_type', 'definition_revision', 'name'}
DECISIONS = {'PENDING', 'CONFIRMED', 'REJECTED', 'UNDONE', 'AUTO_MERGED'}
BACKUP_VERSION = 'quantgraph-personal-backup/v1'


def _text(value, limit=20000, *, required=False):
    if not isinstance(value, str) or len(value) > limit or (required and not value):
        raise ValueError('文本字段格式不正确')
    return value


def _patch(patch):
    if not isinstance(patch, dict) or set(patch) - PERSONAL_FIELDS:
        raise ValueError('个人字段不正确')
    for key, value in patch.items():
        if key == 'starred':
            if not isinstance(value, bool):
                raise ValueError('收藏状态格式不正确')
        elif key in {'tags', 'aliases'}:
            if not isinstance(value, list) or len(value) > 100:
                raise ValueError('标签列表格式不正确')
            for entry in value:
                _text(entry, 200, required=True)
        else:
            _text(value, 200 if key in {'group', 'status'} else 20000)
    if patch.get('status', '待读') not in STATUSES:
        raise ValueError('阅读状态不正确')
    return deepcopy(patch)


def _identity(value):
    for key in IDENTITY_FIELDS:
        _text(value.get(key), 500, required=True)
    if value['kind'] not in KINDS:
        raise ValueError('条目类型不正确')


def blank(item):
    identity = {key: item[key] for key in IDENTITY_FIELDS}
    _identity(identity)
    return identity | dict(stable_id='personal:' + content_hash([identity['kind'], item.get('stable_knowledge_id') or identity['entity_id']]),
        stable_knowledge_id=item.get('stable_knowledge_id') or identity['entity_id'],
        starred=False, status='待读', tags=[], group='', note='', summary='', questions='', reason='', aliases=[],
        problem='', revisions=[identity['definition_revision']], created_at=None, updated_at=None)


class PersonalStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.connect() as con:
            version = con.execute('PRAGMA user_version').fetchone()[0]
            if version not in {0, 1}:
                raise ValueError('个人数据库需要迁移')
            con.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS personal_items(entity_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS personal_duplicates(suggestion_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS personal_redirects(old_id TEXT PRIMARY KEY, canonical_id TEXT NOT NULL, suggestion_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS personal_migrations(migration_id TEXT PRIMARY KEY, digest TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS personal_audit(event_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                PRAGMA user_version=1;
            ''')
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=30)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    @staticmethod
    def _audit(con, action, detail):
        eid = uuid4().hex
        con.execute('INSERT INTO personal_audit VALUES(?,?)', (eid, stable_json(dict(event_id=eid, action=action, at=now(), detail=detail))))

    @staticmethod
    def _resolve(con, eid):
        visited = set()
        while True:
            if eid in visited:
                raise ValueError('合并重定向形成循环')
            visited.add(eid)
            row = con.execute('SELECT canonical_id FROM personal_redirects WHERE old_id=?', (eid,)).fetchone()
            if not row:
                return eid
            eid = row[0]

    def resolve(self, eid):
        with self.connect() as con:
            return self._resolve(con, eid)

    @staticmethod
    def _note(con, item):
        row = con.execute('SELECT payload FROM personal_items WHERE entity_id=?', (item['entity_id'],)).fetchone()
        if not row and item.get('stable_knowledge_id'):
            row = con.execute("SELECT payload FROM personal_items WHERE json_extract(payload,'$.stable_knowledge_id')=? ORDER BY json_extract(payload,'$.created_at') LIMIT 1",
                              (item['stable_knowledge_id'],)).fetchone()
        if not row:
            for eid in item.get('prior_version_ids', []):
                row = con.execute('SELECT payload FROM personal_items WHERE entity_id=?', (eid,)).fetchone()
                if row:
                    break
        return row

    def get(self, item):
        with self.connect() as con:
            row = self._note(con, item)
            value = json.loads(row[0]) if row else blank(item)
            value['canonical_id'] = self._resolve(con, item['entity_id'])
            value['requested_entity_id'] = item['entity_id']
            value['current_entity_id'] = item.get('current_entity_id') or item['entity_id']
            value['current_definition_revision'] = item.get('current_definition_revision') or item['definition_revision']
            value['version_changed'] = value['definition_revision'] != value['current_definition_revision'] or value['entity_id'] != value['current_entity_id']
            ids = [r[0] for r in con.execute('SELECT old_id FROM personal_redirects')
                   if self._resolve(con, r[0]) == value['canonical_id']]
            value['merged_from'] = sorted(ids)
            # Every note remains separately attributed; never concatenate then overwrite.
            linked = ids + [value['canonical_id']]
            value['linked_notes'] = [json.loads(r[0]) for eid in linked if eid != item['entity_id']
                for r in con.execute('SELECT payload FROM personal_items WHERE entity_id=?', (eid,))]
            return value

    def update(self, item, patch, *, definition_revision=None):
        patch = _patch(patch)
        _identity(item)
        with self.lock, self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = self._note(con, item)
            value = json.loads(row[0]) if row else blank(item)
            if definition_revision is not None and definition_revision not in {item['definition_revision'], value['definition_revision']}:
                raise ValueError('定义版本已变化，请刷新后保存')
            # Saving a note does not silently move its reference to a new definition.
            value.update(patch)
            value['updated_at'] = now()
            value['created_at'] = value['created_at'] or value['updated_at']
            con.execute('INSERT OR REPLACE INTO personal_items VALUES(?,?)', (value['entity_id'], stable_json(value)))
            self._audit(con, 'UPDATE_NOTE', {'entity_id': item['entity_id'], 'fields': sorted(patch)})
        return self.get(item)

    def list(self, *, group='', status='', starred=None):
        with self.connect() as con:
            items = [json.loads(r[0]) for r in con.execute('SELECT payload FROM personal_items ORDER BY entity_id')]
            for item in items:
                item['canonical_id'] = self._resolve(con, item['entity_id'])
        items = [i for i in items if (not group or i['group'] == group) and (not status or i['status'] == status)
                 and (starred is None or i['starred'] == starred)]
        items.sort(key=lambda i: (i['updated_at'] or '', i['entity_id']), reverse=True)
        return dict(items=items, total=len(items), statuses=STATUSES)

    def migrate(self, migration_id, items):
        _text(migration_id, 200, required=True)
        if not isinstance(items, list) or len(items) > 5000:
            raise ValueError('迁移清单过大或格式不正确')
        prepared = []
        for item in items:
            _identity(item)
            value = blank(item)
            value.update(_patch({k: v for k, v in item.items() if k in PERSONAL_FIELDS}))
            value['starred'] = item.get('starred', True)
            value['created_at'] = value['updated_at'] = now()
            prepared.append(value)
        digest = content_hash(items)
        with self.lock, self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            prior = con.execute('SELECT digest,payload FROM personal_migrations WHERE migration_id=?', (migration_id,)).fetchone()
            if prior:
                if prior['digest'] != digest:
                    raise ValueError('同一迁移标识已有不同内容；请保留原清单并换用独立迁移标识')
                return json.loads(prior['payload']) | {'replayed': True}
            imported = 0
            for value in prepared:
                cur = con.execute('INSERT OR IGNORE INTO personal_items VALUES(?,?)', (value['entity_id'], stable_json(value)))
                imported += cur.rowcount
            result = dict(imported=imported, preserved=len(prepared)-imported, replayed=False, migration_id=migration_id)
            con.execute('INSERT INTO personal_migrations VALUES(?,?,?)', (migration_id, digest, stable_json(result)))
            self._audit(con, 'MIGRATE_BROWSER', result)
            return result

    def suggest(self, left, right, classification, evidence, *, exact=False):
        if left['entity_id'] == right['entity_id']:
            raise ValueError('需要两个不同条目')
        pair = sorted([left['entity_id'], right['entity_id']])
        sid = 'duplicate:' + content_hash(pair + [classification])
        snapshots = [{k: i.get(k) for k in ['entity_id', 'name', 'kind', 'definition_revision']} for i in [left, right]]
        value = dict(suggestion_id=sid, left=snapshots[0], right=snapshots[1], classification=classification,
                     evidence=evidence, status='PENDING', canonical_id=None, exact=exact, created_at=now(), updated_at=now())
        with self.lock, self.connect() as con:
            con.execute('INSERT OR IGNORE INTO personal_duplicates VALUES(?,?)', (sid, stable_json(value)))
            row = con.execute('SELECT payload FROM personal_duplicates WHERE suggestion_id=?', (sid,)).fetchone()
            value = json.loads(row[0])
        # An explicit rejection/undo survives incremental scans.
        if exact and value['status'] == 'PENDING':
            with self.connect() as con:
                established = {r[0] for r in con.execute('SELECT canonical_id FROM personal_redirects')}
                canonical = next((eid for eid in pair if eid in established or self._resolve(con, eid) != eid), pair[0])
            return self.decide(sid, 'confirm', canonical_id=canonical, automatic=True)
        return value

    def duplicates(self, entity_id='', status=''):
        with self.connect() as con:
            items = [json.loads(r[0]) for r in con.execute('SELECT payload FROM personal_duplicates ORDER BY suggestion_id')]
        items = [v for v in items if (not entity_id or entity_id in {v['left']['entity_id'], v['right']['entity_id']})
                 and (not status or v['status'] == status)]
        return {'items': [self._decision_view(v) for v in items], 'total': len(items)}

    @staticmethod
    def _decision_view(value):
        # This is a presentation field; older backups retain their exact schema.
        return {**value, 'relation_only': value['classification'] in {'TEMPLATE_VARIANT', 'NAME_COLLISION'}
                and value.get('canonical_id') is None}

    def decide(self, sid, action, *, canonical_id=None, automatic=False):
        if action not in {'confirm', 'merge', 'reject', 'undo'}:
            raise ValueError('重复审核操作无效')
        with self.lock, self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT payload FROM personal_duplicates WHERE suggestion_id=?', (sid,)).fetchone()
            if not row:
                raise KeyError(sid)
            value = json.loads(row[0])
            pair = [value['left']['entity_id'], value['right']['entity_id']]
            before = value['status']
            if action == 'confirm' and value['classification'] in {'TEMPLATE_VARIANT', 'NAME_COLLISION'}:
                # A confirmed variant/collision is a relation, not identity evidence.
                # Only the explicit manual "merge" action may override that distinction.
                con.execute('DELETE FROM personal_redirects WHERE suggestion_id=?', (sid,))
                value.update(status='CONFIRMED', canonical_id=None)
            elif action in {'confirm', 'merge'}:
                canonical_id = canonical_id or value.get('canonical_id') or pair[0]
                if canonical_id not in pair:
                    raise ValueError('主条目必须属于此重复建议')
                other = next(e for e in pair if e != canonical_id)
                target = self._resolve(con, canonical_id)
                existing = con.execute('SELECT canonical_id,suggestion_id FROM personal_redirects WHERE old_id=?', (other,)).fetchone()
                if target == other or (existing and existing['suggestion_id'] != sid):
                    raise ValueError('已有合并冲突；请先撤销相关合并')
                con.execute('INSERT OR REPLACE INTO personal_redirects VALUES(?,?,?)', (other, target, sid))
                value.update(status='AUTO_MERGED' if automatic else 'CONFIRMED', canonical_id=target)
            else:
                con.execute('DELETE FROM personal_redirects WHERE suggestion_id=?', (sid,))
                value.update(status='REJECTED' if action == 'reject' else 'UNDONE', canonical_id=None)
            value['updated_at'] = now()
            con.execute('UPDATE personal_duplicates SET payload=? WHERE suggestion_id=?', (stable_json(value), sid))
            self._audit(con, 'DUPLICATE_' + action.upper(), {'suggestion_id': sid, 'before': before, 'after': value['status']})
            return self._decision_view(value)

    def backup(self):
        with self.lock, self.connect() as con:
            payload = {
                'items': [json.loads(r[0]) for r in con.execute('SELECT payload FROM personal_items ORDER BY entity_id')],
                'duplicates': [json.loads(r[0]) for r in con.execute('SELECT payload FROM personal_duplicates ORDER BY suggestion_id')],
                'redirects': [dict(r) for r in con.execute('SELECT * FROM personal_redirects ORDER BY old_id')],
                'migrations': [dict(r) for r in con.execute('SELECT * FROM personal_migrations ORDER BY migration_id')],
                'audit': [json.loads(r[0]) for r in con.execute('SELECT payload FROM personal_audit ORDER BY event_id')],
            }
        return dict(schema_version=BACKUP_VERSION, scope='LOCAL_PERSONAL_ONLY', created_at=now(), payload=payload, sha256=content_hash(payload))

    @staticmethod
    def validate_backup(backup):
        if not isinstance(backup, dict) or backup.get('schema_version') != BACKUP_VERSION or backup.get('scope') != 'LOCAL_PERSONAL_ONLY':
            raise ValueError('不是个人工作台备份')
        payload = backup.get('payload')
        if not isinstance(payload, dict) or set(payload) != {'items', 'duplicates', 'redirects', 'migrations', 'audit'}:
            raise ValueError('备份表结构不正确')
        if backup.get('sha256') != content_hash(payload):
            raise ValueError('备份校验失败，原数据未改变')
        for values in payload.values():
            if not isinstance(values, list) or len(values) > 100000:
                raise ValueError('备份大小或内容格式不正确')
        seen = set()
        for value in payload['items']:
            if not isinstance(value, dict):
                raise ValueError('备份个人字段不正确')
            _identity(value)
            if set(value) != set(blank(value)):
                raise ValueError('备份个人字段不正确')
            _patch({k: value[k] for k in PERSONAL_FIELDS})
            for key in ['stable_id', 'stable_knowledge_id', 'created_at', 'updated_at']:
                _text(value[key], 200, required=True)
            if value['stable_id'] != blank(value)['stable_id'] or not isinstance(value['revisions'], list) or not value['revisions']:
                raise ValueError('备份稳定身份不正确')
            for revision in value['revisions']:
                _text(revision, 500, required=True)
            if value['entity_id'] in seen:
                raise ValueError('备份条目 ID 重复')
            seen.add(value['entity_id'])
        suggestions = {}
        for value in payload['duplicates']:
            expected = {'suggestion_id', 'left', 'right', 'classification', 'evidence', 'status', 'canonical_id', 'exact', 'created_at', 'updated_at'}
            if not isinstance(value, dict) or set(value) != expected or value.get('status') not in DECISIONS:
                raise ValueError('备份重复建议不正确')
            for key in ['classification', 'evidence', 'created_at', 'updated_at']:
                _text(value[key], 5000, required=True)
            if not isinstance(value['exact'], bool):
                raise ValueError('备份重复依据不正确')
            sid = _text(value.get('suggestion_id'), 200, required=True)
            if sid in suggestions:
                raise ValueError('备份重复建议 ID 重复')
            for side in ['left', 'right']:
                if not isinstance(value[side], dict) or set(value[side]) != {'entity_id', 'name', 'kind', 'definition_revision'}:
                    raise ValueError('备份重复建议条目不正确')
                for key in ['entity_id', 'name', 'kind', 'definition_revision']:
                    _text(value[side].get(key), 500, required=True)
            if value['left']['entity_id'] == value['right']['entity_id']:
                raise ValueError('备份重复建议指向自己')
            suggestions[sid] = value
        redirects = {}
        for value in payload['redirects']:
            if set(value) != {'old_id', 'canonical_id', 'suggestion_id'}:
                raise ValueError('备份重定向字段不正确')
            for val in value.values():
                _text(val, 500, required=True)
            sid = value['suggestion_id']
            if value['old_id'] in redirects or sid not in suggestions or suggestions[sid]['status'] not in {'CONFIRMED', 'AUTO_MERGED'}:
                raise ValueError('备份重定向依据不正确')
            if value['old_id'] not in {suggestions[sid]['left']['entity_id'], suggestions[sid]['right']['entity_id']}:
                raise ValueError('备份重定向与条目不一致')
            redirects[value['old_id']] = value['canonical_id']
        for eid in redirects:
            chain = set()
            while eid in redirects:
                if eid in chain:
                    raise ValueError('备份存在循环合并')
                chain.add(eid)
                eid = redirects[eid]
        migration_ids = set()
        for value in payload['migrations']:
            if not isinstance(value, dict) or set(value) != {'migration_id', 'digest', 'payload'}:
                raise ValueError('备份迁移字段不正确')
            _text(value['migration_id'], 200, required=True)
            if value['migration_id'] in migration_ids:
                raise ValueError('备份迁移标识重复')
            migration_ids.add(value['migration_id'])
            _text(value['digest'], 64, required=True)
            if not isinstance(json.loads(value['payload']), dict):
                raise ValueError('迁移记录格式不正确')
        audit_ids = set()
        for value in payload['audit']:
            if not isinstance(value, dict) or set(value) != {'event_id', 'action', 'at', 'detail'} or not isinstance(value['detail'], dict):
                raise ValueError('备份审核记录不正确')
            if value['event_id'] in audit_ids:
                raise ValueError('备份审核记录重复')
            audit_ids.add(value['event_id'])
            for key in ['event_id', 'action', 'at']:
                _text(value.get(key), 200, required=True)
        return deepcopy(payload)

    @staticmethod
    def _load(con, payload, *, mode):
        if mode == 'replace':
            for table in ['personal_items', 'personal_duplicates', 'personal_redirects', 'personal_migrations', 'personal_audit']:
                con.execute('DELETE FROM ' + table)
        before = con.execute('SELECT count(*) FROM personal_items').fetchone()[0]
        for value in payload['items']:
            con.execute('INSERT OR IGNORE INTO personal_items VALUES(?,?)', (value['entity_id'], stable_json(value)))
        new_decisions = set()
        for value in payload['duplicates']:
            changed = con.execute('INSERT OR IGNORE INTO personal_duplicates VALUES(?,?)', (value['suggestion_id'], stable_json(value)))
            if changed.rowcount:
                new_decisions.add(value['suggestion_id'])
        conflicts = []
        for value in payload['redirects']:
            # Preserve this machine's later decision during a merge restore.
            decision = json.loads(con.execute('SELECT payload FROM personal_duplicates WHERE suggestion_id=?', (value['suggestion_id'],)).fetchone()[0])
            if decision['status'] in {'CONFIRMED', 'AUTO_MERGED'} and decision['canonical_id'] == value['canonical_id']:
                current = con.execute('SELECT canonical_id,suggestion_id FROM personal_redirects WHERE old_id=?', (value['old_id'],)).fetchone()
                if current and (current['canonical_id'] != value['canonical_id'] or current['suggestion_id'] != value['suggestion_id']):
                    conflicts.append({'suggestion_id': value['suggestion_id'], 'old_id': value['old_id'], 'kept_canonical_id': current['canonical_id'], 'backup_canonical_id': value['canonical_id']})
                    if value['suggestion_id'] in new_decisions:
                        prior = deepcopy(decision)
                        decision.update(status='PENDING', canonical_id=None, evidence='备份合并遇到本机已确认的重定向，保留为待核对建议。' + decision['evidence'])
                        con.execute('UPDATE personal_duplicates SET payload=? WHERE suggestion_id=?', (stable_json(decision), value['suggestion_id']))
                        PersonalStore._audit(con, 'RESTORE_MERGE_CONFLICT', {'retained_backup_decision': prior, 'kept_redirect': dict(current)})
                else:
                    con.execute('INSERT OR IGNORE INTO personal_redirects VALUES(?,?,?)', (value['old_id'], value['canonical_id'], value['suggestion_id']))
        for value in payload['migrations']:
            con.execute('INSERT OR IGNORE INTO personal_migrations VALUES(?,?,?)', (value['migration_id'], value['digest'], value['payload']))
        for value in payload['audit']:
            con.execute('INSERT OR IGNORE INTO personal_audit VALUES(?,?)', (value['event_id'], stable_json(value)))
        for r in con.execute('SELECT old_id FROM personal_redirects'):
            PersonalStore._resolve(con, r[0])
        added = con.execute('SELECT count(*) FROM personal_items').fetchone()[0] - before
        return {'imported': added, 'preserved': len(payload['items'])-added, 'conflicts': conflicts}

    def restore(self, backup, *, mode='merge'):
        if mode not in {'merge', 'replace'}:
            raise ValueError('恢复方式不正确')
        payload = self.validate_backup(backup)
        # Build and check a separate temporary database before touching this one.
        with tempfile.TemporaryDirectory(prefix='quantgraph-personal-restore-') as directory:
            isolated = PersonalStore(Path(directory) / 'personal.sqlite')
            with isolated.connect() as con:
                self._load(con, payload, mode='replace')
                if con.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise ValueError('隔离恢复校验失败')
            if isolated.backup()['sha256'] != backup['sha256']:
                raise ValueError('隔离恢复内容不一致')
        with self.lock, self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            result = self._load(con, payload, mode=mode)
            self._audit(con, 'RESTORE', result | {'mode': mode, 'sha256': backup['sha256']})
        return result | {'mode': mode, 'verified': True}
