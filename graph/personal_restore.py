"""Previewed personal-layer restores. Source definitions are never rewritten.

Plans are durable local workflow records, deliberately excluded from backups to
avoid recursively embedding uploaded backups. Applied choices remain in audit.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
import re
from uuid import uuid4

from quantgraph.graph.grokbot import content_hash, stable_json
from quantgraph.graph.ingestion_store import now
from quantgraph.graph.personal_store import BACKUP_VERSION, DECISIONS, PERSONAL_FIELDS, blank, _identity, _patch, _text

MAX_BACKUP_BYTES = 8 * 1024 * 1024
V1 = 'quantgraph-personal-backup/v1'
TABLES = {'items': ('personal_items', 'entity_id'), 'duplicates': ('personal_duplicates', 'suggestion_id'),
          'redirects': ('personal_redirects', 'old_id'), 'migrations': ('personal_migrations', 'migration_id'),
          'audit': ('personal_audit', 'event_id')}


class RestoreConflict(ValueError):
    def __init__(self, message, code='RESTORE_CONFLICT'):
        super().__init__(message)
        self.code = code


def snapshot(con):
    values = {}
    for section, (table, key) in TABLES.items():
        if section in {'redirects', 'migrations'}:
            values[section] = [dict(r) for r in con.execute(f'SELECT * FROM {table} ORDER BY {key}')]
        else:
            values[section] = [json.loads(r[0]) for r in con.execute(f'SELECT payload FROM {table} ORDER BY {key}')]
    for item in values['items']:
        item.setdefault('record_revision', 0)
    return values


def envelope(payload):
    return dict(schema_version=BACKUP_VERSION, scope='LOCAL_PERSONAL_ONLY', created_at=now(),
                payload=payload, sha256=content_hash(payload))


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def validate(backup):
    """Validate all rows and report errors; a single invalid row blocks the batch."""
    errors = []
    def invalid(section, index, reason):
        errors.append(dict(section=section, index=index, reason=reason))
    try:
        if len(_json(backup).encode()) > MAX_BACKUP_BYTES:
            raise ValueError('备份超过 8 MiB 限制')
        if not isinstance(backup, dict) or backup.get('schema_version') not in {V1, BACKUP_VERSION}:
            raise ValueError('不支持的备份版本；仅接受个人备份 v1 或 v2')
        if backup.get('scope') != 'LOCAL_PERSONAL_ONLY':
            raise ValueError('不是个人工作台备份')
        raw = backup.get('payload')
        if not isinstance(raw, dict) or set(raw) != set(TABLES):
            raise ValueError('备份表结构不正确')
        if backup.get('sha256') != content_hash(raw):
            raise ValueError('备份摘要校验失败；原个人记录未改变')
        if any(not isinstance(v, list) or len(v) > 100000 for v in raw.values()):
            raise ValueError('备份记录数量或格式不正确')
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        # No source data is interpolated into this message.
        invalid('backup', None, str(exc))
        return None, errors
    payload = deepcopy(raw)
    for section, rows in payload.items():
        seen = set()
        for index, value in enumerate(rows):
            try:
                if not isinstance(value, dict):
                    raise ValueError('记录必须是对象')
                key = TABLES[section][1]
                identifier = _text(value.get(key), 500, required=True)
                if identifier in seen:
                    raise ValueError('备份内部存在重复主键；不能自行选择其中一条')
                seen.add(identifier)
                if section == 'items':
                    _identity(value)
                    expected = set(blank(value))
                    if backup['schema_version'] == V1:
                        expected.remove('record_revision')
                    # Old exports may lack timestamps; absence is retained, not invented.
                    if set(value) - expected or expected - set(value) - {'created_at', 'updated_at'}:
                        raise ValueError('个人记录字段与备份版本不符')
                    value.setdefault('record_revision', 0)
                    if type(value['record_revision']) is not int or value['record_revision'] < 0:
                        raise ValueError('个人记录版本不正确')
                    _patch({k: value[k] for k in PERSONAL_FIELDS})
                    for field in ['stable_id', 'stable_knowledge_id']:
                        _text(value[field], 500, required=True)
                    if value['stable_id'] != blank(value)['stable_id']:
                        raise ValueError('稳定实体身份不匹配')
                    for field in ['created_at', 'updated_at']:
                        value.setdefault(field, None)
                        if value[field] is not None:
                            _text(value[field], 200)
                    if not isinstance(value['revisions'], list) or not value['revisions']:
                        raise ValueError('定义版本引用缺失')
                    for revision in value['revisions']:
                        _text(revision, 500, required=True)
                    if value['definition_revision'] not in value['revisions']:
                        raise ValueError('固定定义版本不在记录引用中')
                elif section == 'duplicates':
                    if set(value) != {'suggestion_id', 'left', 'right', 'classification', 'evidence', 'status', 'canonical_id', 'exact', 'created_at', 'updated_at'}:
                        raise ValueError('重复关系字段不正确')
                    if value['status'] not in DECISIONS or type(value['exact']) is not bool:
                        raise ValueError('重复关系状态不正确')
                    for field in ['classification', 'evidence', 'created_at', 'updated_at']:
                        _text(value[field], 5000, required=True)
                    if value['canonical_id'] is not None:
                        _text(value['canonical_id'], 500, required=True)
                    for side in ['left', 'right']:
                        if not isinstance(value[side], dict) or set(value[side]) != {'entity_id', 'name', 'kind', 'definition_revision'}:
                            raise ValueError('重复关系定义引用不正确')
                        for field in value[side]:
                            _text(value[side][field], 500, required=True)
                    if value['left']['entity_id'] == value['right']['entity_id']:
                        raise ValueError('重复关系不能指向自己')
                elif section == 'redirects':
                    if set(value) != {'old_id', 'canonical_id', 'suggestion_id'}:
                        raise ValueError('重定向字段不正确')
                    for field in value.values():
                        _text(field, 500, required=True)
                elif section == 'migrations':
                    if set(value) != {'migration_id', 'digest', 'payload'}:
                        raise ValueError('迁移记录字段不正确')
                    _text(value['digest'], 64, required=True)
                    if not isinstance(json.loads(value['payload']), dict):
                        raise ValueError('迁移记录内容不正确')
                else:
                    if set(value) != {'event_id', 'action', 'at', 'detail'} or not isinstance(value['detail'], dict):
                        raise ValueError('审核记录字段不正确')
                    for field in ['event_id', 'action', 'at']:
                        _text(value[field], 200, required=True)
            except (ValueError, TypeError, KeyError) as exc:
                invalid(section, index, str(exc))
    if not errors:
        try:
            _validate_relations(payload)
        except ValueError as exc:
            invalid('relationships', None, str(exc))
    return payload, errors


def _validate_relations(payload):
    suggestions = {v['suggestion_id']: v for v in payload['duplicates']}
    redirects = {v['old_id']: v for v in payload['redirects']}
    referenced = {v['entity_id'] for v in payload['items']}
    for decision in suggestions.values():
        referenced.update(decision[side]['entity_id'] for side in ['left', 'right'])
    for value in redirects.values():
        decision = suggestions.get(value['suggestion_id'])
        if not decision or decision['status'] not in {'CONFIRMED', 'AUTO_MERGED'}:
            raise ValueError('重定向缺少已确认关系依据')
        if value['old_id'] not in {decision['left']['entity_id'], decision['right']['entity_id']} or value['canonical_id'] != decision['canonical_id']:
            raise ValueError('重定向与已确认关系不一致')
        # A chain may resolve outside this decision's pair, but its destination
        # still needs a retained item or an endpoint from another decision.
        if value['canonical_id'] not in referenced:
            raise ValueError('合并目标没有保留的实体或关系端点依据，不能恢复悬空重定向')
    for eid in redirects:
        seen = set()
        while eid in redirects:
            if eid in seen:
                raise ValueError('备份存在循环合并')
            seen.add(eid)
            eid = redirects[eid]['canonical_id']


def _time(value):
    created = value.get('created_at') or value.get('at')
    updated = value.get('updated_at') or value.get('at')
    result = dict(created_at=created, updated_at=updated, status='MISSING', normalized_updated_at=None)
    if updated:
        try:
            stamp = datetime.fromisoformat(updated.replace('Z', '+00:00'))
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                raise ValueError()
            result.update(status='VALID', normalized_updated_at=stamp.astimezone(timezone.utc).isoformat())
        except (ValueError, TypeError, AttributeError):
            result['status'] = 'INVALID'
    return result


def _version(value):
    return {key: value.get(key) for key in ['entity_id', 'definition_revision', 'record_revision']}


def _same(a, b, section):
    if section == 'items':
        # Clock/version counters are metadata, not note contents or definition identity.
        strip = lambda values: [{k: v for k, v in row.items() if k not in {'created_at', 'updated_at', 'record_revision'}} for row in values]
        return strip(a) == strip(b)
    return a == b


def _units(local, incoming):
    """Connected relation groups are indivisible, so decisions cannot orphan redirects."""
    units = []
    lineage, entity_lineage = {}, {}
    def lineage_root(key):
        lineage.setdefault(key, key)
        while lineage[key] != key:
            key = lineage[key]
        return key
    for item in local['items'] + incoming['items']:
        key = item['stable_id']
        root = lineage_root(key)
        prior = entity_lineage.setdefault(item['entity_id'], key)
        lineage[root] = lineage_root(prior)
    for section in ['items', 'migrations', 'audit']:
        key = 'stable_id' if section == 'items' else TABLES[section][1]
        left, right = {}, {}
        for value in local[section]:
            identity = lineage_root(value[key]) if section == 'items' else value[key]
            left.setdefault(identity, []).append(value)
        for value in incoming[section]:
            identity = lineage_root(value[key]) if section == 'items' else value[key]
            right.setdefault(identity, []).append(value)
        for identity, rows in right.items():
            matched = left.get(identity, [])
            units.append(dict(section=section, key=identity, local=sorted(matched, key=lambda v:v[TABLES[section][1]]),
                              backup=sorted(rows, key=lambda v:v[TABLES[section][1]])))
    parents = {}
    def find(eid):
        parents.setdefault(eid, eid)
        while parents[eid] != eid:
            eid = parents[eid]
        return eid
    for data in [local, incoming]:
        for decision in data['duplicates']:
            a, b = find(decision['left']['entity_id']), find(decision['right']['entity_id'])
            parents[b] = a
        for redirect in data['redirects']:
            a, b = find(redirect['old_id']), find(redirect['canonical_id'])
            parents[b] = a
    groups = {}
    for eid in parents:
        groups.setdefault(find(eid), []).append(eid)
    for members in groups.values():
        sides = []
        for data in [local, incoming]:
            ds = [v for v in data['duplicates'] if v['left']['entity_id'] in members]
            rs = [v for v in data['redirects'] if v['old_id'] in members]
            sides.append([dict(duplicates=ds, redirects=rs)] if ds or rs else [])
        if sides[1]:
            units.append(dict(section='relationships', key=content_hash(sorted(members)), local=sides[0], backup=sides[1]))
    return units


def _prepare(local, incoming, backup_version):
    conflicts, counts, sections = [], dict(added=0, identical=0, conflicts=0, invalid=0), {}
    units = _units(local, incoming)
    for unit in units:
        section = unit['section']
        unit['id'] = 'restore:' + content_hash([section, unit['key']])
        unit['state'] = 'added' if not unit['local'] else 'identical' if _same(unit['local'], unit['backup'], section) else 'conflicts'
        counts[unit['state']] += 1
        sections.setdefault(section, dict(added=0, identical=0, conflicts=0, invalid=0))[unit['state']] += 1
        if unit['state'] == 'conflicts':
            a, b = unit['local'][0], unit['backup'][0]
            identity = {k: b.get(k) for k in ['kind', 'entity_id', 'stable_id', 'stable_knowledge_id', 'name']}
            if section != 'items':
                identity = dict(id=unit['key'], name={'relationships': '重复关系及其重定向组', 'audit': '审核记录', 'migrations': '浏览器迁移记录'}[section])
            conflicts.append(dict(id=unit['id'], section=section, identity=identity, local=a, backup=b,
                local_records=unit['local'], backup_records=unit['backup'],
                versions={'local': _version(a), 'backup': _version(b), 'backup_schema_version': backup_version},
                timestamps={'local': _time(a), 'backup': _time(b)},
                reason='同一稳定身份的内容或定义引用不同；时间仅供核对，必须明确选择，双方原件会保留'))
    return units, conflicts, counts, sections


def preview(store, backup):
    incoming, invalid = validate(backup)
    token = uuid4().hex
    with store.lock, store.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        local = snapshot(con)
        if invalid:
            units, conflicts, counts, sections = [], [], dict(added=0, identical=0, conflicts=0, invalid=len(invalid)), {}
        else:
            units, conflicts, counts, sections = _prepare(local, incoming, backup['schema_version'])
        digest = backup.get('sha256') if isinstance(backup, dict) else None
        if not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest):
            digest = None
        value = dict(preview_token=token, backup_digest=digest,
            status='PREVIEW', can_apply=not invalid, counts=counts, sections=sections, conflicts=conflicts,
            invalid=invalid, decisions={}, result=None, applied_at=None,
            count_unit='stable_identity_or_connected_relationship_group',
            counts_complete=not invalid,
            summary=(f"备份无效 {counts['invalid']} 项；新增、相同和冲突数量尚未计算，不能执行恢复。" if invalid else
                     f"新增 {counts['added']} 组，相同 {counts['identical']} 组，冲突 {counts['conflicts']} 组，无效 0 项。不会按时间自动选择。"))
        plan = dict(preview=value, backup=backup if not invalid else None, units=units, base_digest=content_hash(local), created_at=now())
        con.execute('INSERT INTO personal_restore_plans VALUES(?,?)', (token, stable_json(plan)))
    return value


def _plan(con, token):
    if not isinstance(token, str) or not re.fullmatch(r'[a-f0-9]{32}', token):
        raise KeyError(token)
    row = con.execute('SELECT payload FROM personal_restore_plans WHERE preview_token=?', (token,)).fetchone()
    if not row:
        raise KeyError(token)
    return json.loads(row[0])


def report(store, token):
    with store.connect() as con:
        return _plan(con, token)['preview']


def _write_payload(con, payload):
    # Only a validated, previewed per-conflict selection can reach this transaction.
    for section, (table, _) in TABLES.items():
        con.execute(f'DELETE FROM {table}')
        for value in payload[section]:
            if section == 'redirects':
                con.execute(f'INSERT INTO {table} VALUES(?,?,?)', (value['old_id'], value['canonical_id'], value['suggestion_id']))
            elif section == 'migrations':
                con.execute(f'INSERT INTO {table} VALUES(?,?,?)', (value['migration_id'], value['digest'], value['payload']))
            else:
                con.execute(f'INSERT INTO {table} VALUES(?,?)', (value[TABLES[section][1]], stable_json(value)))


def _selected(local, units, choices):
    selected = deepcopy(local)
    for unit in units:
        if unit['state'] == 'identical' or (unit['state'] == 'conflicts' and choices[unit['id']] == 'KEEP_LOCAL'):
            continue
        section = unit['section']
        if section == 'relationships':
            for part in ['duplicates', 'redirects']:
                key = TABLES[part][1]
                existing = {v[key] for group in unit['local'] for v in group[part]}
                selected[part] = [v for v in selected[part] if v[key] not in existing]
                selected[part].extend(unit['backup'][0][part])
        else:
            key = TABLES[section][1]
            existing = {v[key] for v in unit['local']}
            selected[section] = [v for v in selected[section] if v[key] not in existing] + deepcopy(unit['backup'])
    for section in selected:
        selected[section].sort(key=lambda value: value[TABLES[section][1]])
    return selected


def _save_point(store, payload):
    directory = store.path.parent / 'restore-backups'
    directory.mkdir(mode=0o700, exist_ok=True)
    identity = uuid4().hex
    path = directory / (identity + '.json')
    data = _json(envelope(payload)).encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    return dict(id=identity, download_url=f'/v1/personal/restore/backups/{identity}')


def saved_backup(store, identity):
    if not isinstance(identity, str) or not re.fullmatch(r'[a-f0-9]{32}', identity):
        raise KeyError(identity)
    path = store.path.parent / 'restore-backups' / (identity + '.json')
    if not path.is_file():
        raise KeyError(identity)
    return json.loads(path.read_text())


def apply_restore(store, token, decisions, *, backup=None):
    if not isinstance(decisions, dict) or any(v not in {'KEEP_LOCAL', 'USE_BACKUP'} for v in decisions.values()):
        raise ValueError('每项冲突必须选择 KEEP_LOCAL 或 USE_BACKUP')
    with store.lock, store.connect() as con:
        con.execute('BEGIN IMMEDIATE')
        plan = _plan(con, token)
        view = plan['preview']
        if backup is not None and content_hash(backup) != content_hash(plan['backup']):
            raise RestoreConflict('备份文件与预览不一致，请重新预览', 'BACKUP_CHANGED')
        if view['status'] == 'APPLIED':
            if decisions != view['decisions']:
                raise RestoreConflict('此预览已按另一组选择执行；请重新预览', 'ALREADY_APPLIED')
            return view['result'] | {'replayed': True}
        if not view['can_apply']:
            raise ValueError('备份含无效记录，不能执行；请查看预览报告')
        expected = {c['id'] for c in view['conflicts']}
        if set(decisions) != expected:
            raise RestoreConflict('还有冲突未明确选择，或选择不属于此预览；双方内容已保留', 'UNRESOLVED_CONFLICTS')
        local = snapshot(con)
        if content_hash(local) != plan['base_digest']:
            raise RestoreConflict('预览后个人记录已有变化；请重新预览，当前资料未被覆盖', 'STALE_PREVIEW')
        selected = _selected(local, plan['units'], decisions)
        _, invalid = validate(envelope(selected))
        if invalid:
            raise ValueError('选定内容无法构成一致备份；个人记录未改变：' + invalid[0]['reason'])
        point = _save_point(store, local)
        changed = content_hash(selected) != content_hash(local)
        if changed:
            _write_payload(con, selected)
        result = dict(status='APPLIED', verified=True, counts=view['counts'],
            result=dict(added=view['counts']['added'], identical=view['counts']['identical'],
                        kept_local=sum(v == 'KEEP_LOCAL' for v in decisions.values()),
                        used_backup=sum(v == 'USE_BACKUP' for v in decisions.values())),
            pre_restore_backup=point, replayed=False,
            summary='恢复已完成；冲突按明确选择处理，双方原件与执行前备份保留。' if changed else '内容未变化；没有重复创建个人记录，执行前备份已保留。')
        if changed or decisions:
            store._audit(con, 'RESTORE_REVIEWED', {'preview_token': token, 'backup_digest': view['backup_digest'],
                'decisions': decisions, 'pre_restore_backup': point, 'changed': changed})
        view.update(status='APPLIED', can_apply=False, decisions=decisions, result=result, applied_at=now())
        con.execute('UPDATE personal_restore_plans SET payload=? WHERE preview_token=?', (stable_json(plan), token))
        if con.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('恢复事务检查失败；个人记录未改变')
    return result
