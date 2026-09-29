"""Persistent, rebuildable website read model over the existing graph and journal.

This is a SQLite projection, not a second ontology or research queue. All public
queries filter visibility on the server. Restricted source payloads never form
part of the search index, export or public response.
"""
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import threading

from quantgraph.api.web_read_model import normalize, FIELD_LABELS
from quantgraph.graph.catalog_projection import VERSION, edge, empty_results, safe_factor, strategy_projection, public_text, public_url, item
from quantgraph.graph.grokbot import content_hash, stable_json
from quantgraph.graph.ingestion_store import now
from quantgraph.normalize.strategy.parser import VERSION as PARSER_VERSION


class CatalogRepository:
    def __init__(self, path, *, ingestion=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ingestion = ingestion
        self.lock = threading.RLock()
        self.result_reader = None
        with self.connect() as con:
            if con.execute('PRAGMA user_version').fetchone()[0] > 1:
                raise ValueError('Catalog migration required')
            con.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS catalog_items (
                    entity_id TEXT PRIMARY KEY, kind TEXT NOT NULL, entity_type TEXT NOT NULL,
                    definition_revision TEXT NOT NULL, payload TEXT NOT NULL, private_payload TEXT NOT NULL,
                    visibility TEXT NOT NULL DEFAULT 'PUBLIC', patch TEXT NOT NULL DEFAULT '{}',
                    search_text TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, is_test INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS catalog_versions (
                    entity_id TEXT, revision TEXT, payload TEXT, private_payload TEXT,
                    created_at TEXT, PRIMARY KEY(entity_id,revision));
                CREATE TABLE IF NOT EXISTS catalog_origins (
                    owner TEXT, entity_id TEXT, active INTEGER NOT NULL DEFAULT 1, PRIMARY KEY(owner,entity_id));
                CREATE TABLE IF NOT EXISTS catalog_edges (
                    relationship_id TEXT PRIMARY KEY, from_id TEXT, to_id TEXT, payload TEXT,
                    visibility TEXT NOT NULL DEFAULT 'PUBLIC', patch TEXT NOT NULL DEFAULT '{}');
                CREATE INDEX IF NOT EXISTS catalog_edges_from ON catalog_edges(from_id);
                CREATE INDEX IF NOT EXISTS catalog_edges_to ON catalog_edges(to_id);
                CREATE TABLE IF NOT EXISTS catalog_edge_origins (
                    owner TEXT, relationship_id TEXT, active INTEGER NOT NULL DEFAULT 1, PRIMARY KEY(owner,relationship_id));
                CREATE INDEX IF NOT EXISTS catalog_origin_entity ON catalog_origins(entity_id,active);
                CREATE INDEX IF NOT EXISTS catalog_edge_origin_edge ON catalog_edge_origins(relationship_id,active);
                CREATE TABLE IF NOT EXISTS catalog_inputs (
                    source TEXT, record_id TEXT, revision TEXT, entity_id TEXT,
                    disposition TEXT, reason TEXT, is_test INTEGER, PRIMARY KEY(source,record_id));
                CREATE TABLE IF NOT EXISTS catalog_checkpoints (source TEXT PRIMARY KEY, cursor TEXT);
                CREATE TABLE IF NOT EXISTS catalog_imports (
                    import_id INTEGER PRIMARY KEY, created_at TEXT, status TEXT, processed INTEGER,
                    errors INTEGER, reason TEXT);
                CREATE TABLE IF NOT EXISTS catalog_audit (
                    audit_id INTEGER PRIMARY KEY, created_at TEXT, actor TEXT, action TEXT,
                    entity_id TEXT, before_json TEXT, after_json TEXT);
                CREATE TABLE IF NOT EXISTS catalog_suggestions (
                    suggestion_id TEXT PRIMARY KEY, payload TEXT, status TEXT, created_at TEXT);
                CREATE VIEW IF NOT EXISTS catalog_visible_items AS SELECT i.* FROM catalog_items i
                    WHERE i.active=1 AND i.visibility='PUBLIC' AND NOT(i.kind='source' AND EXISTS(
                        SELECT 1 FROM catalog_edges e JOIN catalog_items parent ON parent.entity_id=e.to_id
                        WHERE e.from_id=i.entity_id AND json_extract(e.payload,'$.relation')='DESCRIBES'
                        AND (parent.active=0 OR parent.visibility='HIDDEN')));
                PRAGMA user_version=1;
            ''')
            if 'is_test' not in {r[1] for r in con.execute('PRAGMA table_info(catalog_items)')}:
                con.execute('ALTER TABLE catalog_items ADD COLUMN is_test INTEGER NOT NULL DEFAULT 0')
            self._classify_test_origins(con)
            con.execute('DROP VIEW IF EXISTS catalog_visible_items')
            con.execute("""CREATE VIEW catalog_visible_items AS SELECT i.* FROM catalog_items i
                WHERE i.active=1 AND i.visibility='PUBLIC'
                AND NOT(i.kind='source' AND EXISTS(SELECT 1 FROM catalog_edges e
                    JOIN catalog_items parent ON parent.entity_id=e.to_id WHERE e.from_id=i.entity_id
                    AND json_extract(e.payload,'$.relation')='DESCRIBES'
                    AND (parent.active=0 OR parent.visibility='HIDDEN')))
                AND (i.is_test=0 OR EXISTS(SELECT 1 FROM catalog_origins o
                    JOIN catalog_inputs x ON x.source='grokbot' AND x.record_id=substr(o.owner,8)
                    JOIN catalog_items parent ON parent.entity_id=x.entity_id
                    WHERE o.entity_id=i.entity_id AND o.active=1 AND parent.active=1 AND parent.visibility='PUBLIC'))""")
        self.path.chmod(0o600)

    @staticmethod
    def _classify_test_origins(con):
        con.execute("""UPDATE catalog_items SET is_test=NOT EXISTS(
            SELECT 1 FROM catalog_origins o LEFT JOIN catalog_inputs x
            ON x.source='grokbot' AND x.record_id=substr(o.owner,8)
            WHERE o.entity_id=catalog_items.entity_id AND o.active=1
            AND (o.owner NOT LIKE 'ingest:%' OR COALESCE(x.is_test,0)=0))""")

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
    def index(payload):
        # Exactly the public display projection; never raw/private text.
        return normalize(' '.join(str(payload.get(k) or '') for k in (
            'name', 'aliases', 'description', 'family', 'family_label', 'source_native_ids',
            'formula', 'parameters', 'market_description', 'source_type')))

    def _put(self, con, value, owner, private=None):
        value = deepcopy(value)
        raw = private if private is not None else {}
        eid, rev = value['entity_id'], value['definition_revision']
        old = con.execute('SELECT patch FROM catalog_items WHERE entity_id=?',(eid,)).fetchone()
        indexed = value | (json.loads(old['patch']) if old else {})
        con.execute('INSERT OR IGNORE INTO catalog_versions VALUES (?,?,?,?,?)',
                    (eid, rev, stable_json(value), stable_json(raw), now()))
        con.execute('''INSERT INTO catalog_items(entity_id,kind,entity_type,definition_revision,payload,private_payload,search_text)
            VALUES (?,?,?,?,?,?,?) ON CONFLICT(entity_id) DO UPDATE SET definition_revision=excluded.definition_revision,
            payload=excluded.payload, private_payload=excluded.private_payload, search_text=excluded.search_text,active=1''',
            (eid, value['kind'], value['entity_type'], rev, stable_json(value), stable_json(raw), self.index(indexed)))
        con.execute('INSERT INTO catalog_origins VALUES (?,?,1) ON CONFLICT(owner,entity_id) DO UPDATE SET active=1', (owner,eid))

    def _edge(self, con, value, owner):
        con.execute('''INSERT INTO catalog_edges(relationship_id,from_id,to_id,payload) VALUES (?,?,?,?)
            ON CONFLICT(relationship_id) DO UPDATE SET payload=excluded.payload''',
            (value['relationship_id'], value['from_id'], value['to_id'], stable_json(value)))
        con.execute('INSERT INTO catalog_edge_origins VALUES (?,?,1) ON CONFLICT(owner,relationship_id) DO UPDATE SET active=1',
                    (owner, value['relationship_id']))

    def import_factors(self, public_model, extra_db=None, normalized=None):
        """Verified Qlib definitions plus metadata-only mixed-license inputs."""
        models = [(public_model, True)]
        if extra_db is not None:
            # Reuse the existing projector, without relaxing its public constructor.
            from quantgraph.api.web_read_model import WebReadModel
            m = object.__new__(WebReadModel)
            m.records = {}
            for row in extra_db._objects('SELECT payload FROM factor_variants'):
                m.records[('variant', row['factor_variant_id'])] = row
            for row in extra_db._objects('SELECT payload FROM factor_concepts'):
                m.records[('concept', row['canonical_factor_id'])] = row
            models.insert(0, (m, False))  # Verified public rows win duplicate IDs.
        record_map = {rid: eid for m, _ in models for (kind, eid), value in m.records.items() if kind == 'variant' for rid in value.get('source_record_ids', [])}
        with self.lock, self.connect() as con:
            for model, licensed in models:
                for (kind, eid), row in model.records.items():
                    if kind not in {'variant', 'concept'}:
                        continue
                    owner = 'factor:' + eid
                    value = safe_factor(model, kind, eid, row, licensed=licensed)
                    self._put(con, value, owner, row)
                    if kind == 'variant':
                        self._edge(con, edge(eid, row['canonical_factor_id'], 'VARIANT_OF',
                                   '来源定义所属概念；保留参数与实现差异', value['source_url']), owner)
                    con.execute('INSERT OR REPLACE INTO catalog_inputs VALUES (?,?,?,?,?,?,0)',
                        ('factors', eid, value['definition_revision'], eid, 'DISPLAYABLE_DEFINITION' if licensed else 'METADATA_ONLY',
                         '' if licensed else 'SOURCE_TEXT_RIGHTS_REVIEW_REQUIRED'))
            # Concrete factor-to-factor navigation follows an existing source
            # concept; it deliberately asserts only a category link.
            groups = {}
            for (kind, eid), row in public_model.records.items():
                if kind == 'variant':
                    groups.setdefault(row['canonical_factor_id'], []).append(row)
            for group in groups.values():
                group.sort(key=lambda r:r['variant_name'])
                for row in group[1:]:
                    first = group[0]
                    self._edge(con, edge(first['factor_variant_id'], row['factor_variant_id'], 'CATEGORY_LINK_ONLY',
                        '同一来源概念内的具体定义；公式与参数须逐项比较，无等价或实证相关性结论',
                        row.get('source_url')), 'public-release')
            # Keep real public factor relationships with provenance, not name guesses.
            ids = {r[0] for r in con.execute('SELECT entity_id FROM catalog_items')}
            for raw in public_model.db._objects('SELECT payload FROM relationships'):
                if raw['from_id'] in ids and raw['to_id'] in ids:
                    value = edge(raw['from_id'], raw['to_id'], raw['relation'], raw.get('evidence'), raw.get('source'),
                                 confidence=raw.get('confidence', 1), status=raw.get('status', 'SOURCE_REPORTED'))
                    self._edge(con, value, 'public-release')
            if normalized:
                # Every collected factor record is accounted for, even if curation
                # merged it or rejected it. No restricted text leaves this journal.
                records = Path(normalized)
                if records.is_file():
                    for line in records.read_text().splitlines():
                        row = json.loads(line)
                        rid = row.get('record_id') or row.get('source_record_id') or content_hash(row)
                        source = row.get('source_name') or row.get('source_id') or 'normalized'
                        match = record_map.get(rid)
                        if not match:
                            knowledge = item('source', rid, row.get('signal_name') or row.get('source_native_id') or rid,
                                'SourceRecord', content_hash(row), source_name=source, source_type='factor_source_record',
                                source_native_ids=[row.get('source_native_id')] if row.get('source_native_id') else [],
                                source_url=public_url(row.get('source_url')),
                                description='因子原始资料已收录，定义仍待补充或合并核对。受限公式、正文与代码未分发。')
                            self._put(con, knowledge, 'normalized:' + rid, row)
                        con.execute('INSERT OR REPLACE INTO catalog_inputs VALUES (?,?,?,?,?,?,0)',
                            ('normalized:' + source, rid, content_hash(row), match, 'MERGED_REFERENCE' if match else 'RAW_REFERENCE',
                             '' if match else '原始资料已保存；未通过定义准入或尚未建立精确映射'))
            con.execute('INSERT INTO catalog_imports(created_at,status,processed,errors,reason) VALUES (?,?,?,?,?)',
                        (now(), 'COMPLETED', sum(len(m.records) for m, _ in models), 0, 'Factor definitions and metadata'))

    def sync_ingestion(self, *, retry=False):
        if self.ingestion is None:
            return {'processed': 0, 'errors': 0}
        with self.lock, self.connect() as con, self.ingestion.connect() as source:
            checkpoint = con.execute('SELECT cursor FROM catalog_checkpoints WHERE source=?', ('ingestion:' + PARSER_VERSION,)).fetchone()
            cursor = 0 if retry or not checkpoint else int(checkpoint[0])
            rows = source.execute('''SELECT p.rowid AS cursor,p.* FROM projections p WHERE p.rowid>? AND parser_version=?
                AND revision=(SELECT MAX(revision) FROM revisions r WHERE r.record_id=p.record_id) ORDER BY p.rowid''',
                (cursor, PARSER_VERSION)).fetchall()
            errors = 0
            for r in rows:
                owner = 'ingest:' + r['record_id']
                try:
                    value = json.loads(r['payload'])
                    nodes, edges = strategy_projection(value)
                    con.execute('SAVEPOINT project_record')
                    con.execute('UPDATE catalog_origins SET active=0 WHERE owner=?', (owner,))
                    con.execute('UPDATE catalog_edge_origins SET active=0 WHERE owner=?', (owner,))
                    for node in nodes:
                        self._put(con, node, owner, value if node['kind'] == 'strategy' else {})
                    for e in edges:
                        self._edge(con, e, owner)
                    primary = nodes[0]
                    con.execute('INSERT OR REPLACE INTO catalog_inputs VALUES (?,?,?,?,?,?,?)',
                        ('grokbot', r['record_id'], str(r['revision']), primary['entity_id'],
                         'DISPLAYABLE_VARIANT' if primary['record_level'] == 'variant' else 'RAW_REFERENCE',
                         value['variant'].get('parse_reason'), int(primary['test_record'])))
                    con.execute('RELEASE project_record')
                except (ValueError, KeyError, TypeError):
                    # Explicit recoverable failure; never disclose raw exception text.
                    try:
                        con.execute('ROLLBACK TO project_record')
                        con.execute('RELEASE project_record')
                    except sqlite3.OperationalError:
                        pass
                    errors += 1
                    con.execute('INSERT OR REPLACE INTO catalog_inputs VALUES (?,?,?,?,?,?,0)',
                        ('grokbot', r['record_id'], str(r['revision']), None, 'FAILED', 'PROJECTION_FAILED_RETRY_AVAILABLE'))
            if rows:
                con.execute('UPDATE catalog_items SET active=EXISTS(SELECT 1 FROM catalog_origins o WHERE o.entity_id=catalog_items.entity_id AND o.active=1)')
                # Failed rows keep the cursor back for automatic retry.
                if not errors:
                    con.execute('INSERT OR REPLACE INTO catalog_checkpoints VALUES (?,?)', ('ingestion:' + PARSER_VERSION, str(rows[-1]['cursor'])))
                con.execute('INSERT INTO catalog_imports(created_at,status,processed,errors,reason) VALUES (?,?,?,?,?)',
                    (now(), 'PARTIAL' if errors else 'COMPLETED', len(rows)-errors, errors, 'Ingestion projection'))
                self._refresh_lineage(con)
                self._classify_test_origins(con)
            return {'processed': len(rows)-errors, 'errors': errors}

    def _refresh_lineage(self, con):
        from quantgraph.graph.variation import apply_observed_axes, components, signature
        projections = [json.loads(r[0]) for r in con.execute("SELECT private_payload FROM catalog_items WHERE kind='strategy' AND active=1")]
        apply_observed_axes(projections)
        ids = {p['variant']['source_native_id']:p['variant']['strategy_variant_id'] for p in projections}
        groups = {}
        con.execute("UPDATE catalog_edge_origins SET active=0 WHERE owner='observed-lineage'")
        for p in projections:
            v = p['variant']; eid = v['strategy_variant_id']
            current = con.execute('SELECT payload FROM catalog_items WHERE entity_id=?',(eid,)).fetchone()
            value = json.loads(current[0]); value['strategy']['variation_axes'] = v['variation_axes']
            con.execute('UPDATE catalog_items SET payload=? WHERE entity_id=?',(stable_json(value),eid))
            meta = v.get('auditable_metadata',{}).get('metadata',{})
            parent = meta.get('parent_record_id')
            if parent in ids:
                self._edge(con,edge(eid, ids[parent], 'DERIVED_FROM', '采集元数据明确保留父记录；改造有效性未验证',v.get('source_url'), review_status='CANDIDATE'), 'observed-lineage')
            if v.get('strategy_template_id'):
                groups.setdefault(v['strategy_template_id'],[]).append(v)
        for group in groups.values():
            first = group[0]
            for v in group[1:]:
                for relation, keys in [('PARAMETER_VARIANT',{'parameters','value','threshold','exit_threshold'}),('ASSET_VARIANT',{'asset','assets','risk_asset','safe_asset'})]:
                    if signature(components(v['rule_ast'],keys)) != signature(components(first['rule_ast'],keys)):
                        self._edge(con,edge(first['strategy_variant_id'],v['strategy_variant_id'],relation,
                            '相同解析模板中的已观察槽位差异；其他变化轴须同时比较',v.get('source_url')), 'observed-lineage')

    @staticmethod
    def _value(row):
        value = json.loads(row['payload']) | json.loads(row['patch'])
        value['visibility'] = row['visibility']
        value['test_record'] = bool(row['is_test'])
        value['statuses'] = value['statuses'] | {'display': row['visibility'] + ' · 字段与附件权限独立'}
        return value

    def get(self, entity_id, *, admin=False):
        with self.connect() as con:
            table = 'catalog_items' if admin else 'catalog_visible_items'
            row = con.execute(f'SELECT entity_id,payload,patch,visibility,is_test FROM {table} WHERE entity_id=?', (entity_id,)).fetchone()
            if not row:
                raise KeyError(entity_id)
            return self._value(row)

    def visible(self, entity_id):
        try:
            self.get(entity_id)
            return True
        except KeyError:
            return False

    def resolve_ref(self, entity_type, entity_id, definition_revision):
        """Server-only definition snapshot for C; no raw payload public endpoint."""
        item = self.get(entity_id)
        if item['entity_type'] != entity_type or item['definition_revision'] != definition_revision:
            raise KeyError('Definition reference is not current')
        with self.connect() as con:
            row = con.execute('SELECT private_payload FROM catalog_items WHERE entity_id=?', (entity_id,)).fetchone()
        return {'entity_ref': {k: item[k] for k in ['entity_type','entity_id','definition_revision']},
                'catalog': item, 'definition': json.loads(row[0])}

    @property
    def by_key(self):
        return {(r['kind'], r['entity_id']):r for r in self.all_items()}

    def all_items(self, *, admin=False):
        with self.connect() as con:
            table = 'catalog_items' if admin else 'catalog_visible_items'
            rows = con.execute(f'SELECT entity_id,payload,patch,visibility,is_test FROM {table} WHERE active=1')
            return [self._value(r) for r in rows]

    def search(self, *, q='', kind='strategy', category='', family='', field='', market='', frequency='', source_type='', result_status='', page=1, page_size=20, admin=False):
        needle = normalize(q)
        researched = {ref['entity_id'] for r in self.results().get('items', []) for ref in r.get('entity_refs', [])}
        with self.connect() as con:
            table = 'catalog_items' if admin else 'catalog_visible_items'
            rows = con.execute(f'SELECT entity_id,payload,patch,visibility,is_test FROM {table} WHERE active=1 AND kind=?', (kind,))
            matched = []
            for row in rows:
                value = self._value(row)
                if value['entity_id'] in researched:
                    value['result_status'] = 'researched'
                    value['statuses']['result'] = '已有研究记录 · 结论级别独立判断'
                if needle and needle not in self.index(value):
                    continue
                if any(wanted and value.get(key) != wanted for key, wanted in [('family', family), ('category', category), ('frequency', frequency), ('source_type', source_type), ('result_status',result_status)]):
                    continue
                if field and field not in value['required_fields'] or market and market not in value['markets']:
                    continue
                score = (0 if needle == normalize(value['name']) else 1 if normalize(value['name']).startswith(needle) else 2)
                matched.append((score, value))
        matched.sort(key=lambda x:(x[0], x[1]['name'],x[1]['entity_id']))
        offset = (page-1)*page_size
        return dict(items=[v for _,v in matched[offset:offset+page_size]],total=len(matched),page=page,page_size=page_size,
                    sort='name_alias_relevance_then_name',scope='PUBLIC')

    def relations(self, entity_id, *, hops=1, relation='', limit=40, offset=0, admin=False):
        root = self.get(entity_id, admin=admin)
        with self.connect() as con:
            restriction = '' if admin else " AND a.visibility='PUBLIC' AND b.visibility='PUBLIC' AND e.visibility='PUBLIC'"
            table = 'catalog_items' if admin else 'catalog_visible_items'
            candidates = con.execute(f"""SELECT e.payload,e.patch FROM catalog_edges e
                JOIN {table} a ON a.entity_id=e.from_id JOIN {table} b ON b.entity_id=e.to_id
                WHERE a.active=1 AND b.active=1 AND EXISTS(SELECT 1 FROM catalog_edge_origins o
                WHERE o.relationship_id=e.relationship_id AND o.active=1)""" + restriction).fetchall()
        # A filtered two-hop exploration walks only selected edge types.
        values = [json.loads(r['payload']) | json.loads(r['patch']) for r in candidates]
        if relation:
            values = [r for r in values if r['relation'] == relation]
        frontier, found, visited = {entity_id}, {}, {entity_id}
        for _ in range(min(hops,2)):
            next_frontier = set()
            for r in values:
                if r['from_id'] in frontier or r['to_id'] in frontier:
                    found[r['relationship_id']] = r
                    next_frontier.update([r['from_id'],r['to_id']])
            frontier = next_frontier - visited
            visited.update(next_frontier)
        ordered = sorted(found.values(),key=lambda r:(r['relation'],r['relationship_id']))
        rows = ordered[offset:offset+limit]
        nodes = {entity_id: root}
        for r in rows:
            a,b = self.get(r['from_id'],admin=admin),self.get(r['to_id'],admin=admin)
            nodes[a['entity_id']],nodes[b['entity_id']] = a,b
            r.update(from_name=a['name'],to_name=b['name'],from_type=a['entity_type'],to_type=b['entity_type'],
                     from_kind=a['kind'],to_kind=b['kind'])
        # Never send all node definitions just to render a bounded diagram.
        return dict(items=rows, total=len(ordered), offset=offset, limit=limit,
                    nodes=[{k:n[k] for k in ['entity_id','name','kind','entity_type']} for n in nodes.values()],
                    types=sorted({r['relation'] for r in found.values()}))

    def detail(self, kind, eid):
        value = self.get(eid)
        if value['kind'] != kind:
            raise KeyError(eid)
        value['relations'] = self.relations(eid)['items']
        relatives = []
        for r in value['relations']:
            other = r['to_id'] if r['from_id'] == eid else r['from_id']
            node = self.get(other)
            if node['kind'] in {'strategy','variant','concept','family','template'}:
                relatives.append(node)
        value['related'] = relatives
        value['related_strategies'] = [dict(strategy_id=n['entity_id'], canonical_name=n['name']) for n in relatives if n['kind']=='strategy']
        value['results'] = self.results(kind, eid)
        if value['results']['items']:
            value['statuses']['result'] = '已有研究记录 · 见各自结论级别'
        return value

    def results(self, kind=None, eid=None):
        if eid:
            value = self.get(eid)
            if kind != value['kind']:
                raise KeyError(eid)
        return self.result_reader(kind,eid) if self.result_reader else empty_results()

    def metadata(self):
        items = self.all_items()
        visible_counts = Counter(i['kind'] for i in items)
        counts = Counter(i['kind'] for i in items if not i.get('test_record'))
        def facet(key, multiple=False):
            values = {v for i in items for v in (i.get(key, []) if multiple else [i.get(key)]) if v}
            return [dict(value=v,label=FIELD_LABELS.get(v,v)) for v in sorted(values)]
        return dict(mode='PUBLIC', release='runtime-catalog', graph_api='v1', graph_version='0.2.0', adapter_version='catalog/v1',
            counts={k:counts[k] for k in ['strategy','variant','concept','family','template','source']}, result_count=self.results()['total'], legacy_result_count=0,
            facets=dict(categories=facet('category'),families=facet('family'),fields=facet('required_fields',True),markets=facet('markets',True),
                        frequencies=facet('frequency'),source_types=facet('source_type')),
            contracts=dict(request='research-request/v1',result='factor-study-result/v1',status='CONNECTED',export_enabled=True),
            visible_counts=dict(visible_counts),
            test_counts=dict(Counter(i['kind'] for i in items if i.get('test_record'))),
            knowledge_counts=dict(collected_strategy_records=sum(i['kind']=='strategy' and not i.get('test_record') for i in items),structured_strategy_variants=sum(i['kind']=='strategy' and i['record_level']=='variant' and not i.get('test_record') for i in items),
                strategy_families=counts['family'],independent_strategies=None,
                explanation='采集记录、策略族与参数变体分别计数；独立策略数未经验证。'))

    def reconcile(self):
        with self.connect() as con:
            dispositions = [dict(r) for r in con.execute('SELECT source,disposition,is_test,count(*) AS count FROM catalog_inputs GROUP BY source,disposition,is_test')]
            failed = [dict(r) for r in con.execute("SELECT * FROM catalog_inputs WHERE disposition='FAILED'")]
            imports = [dict(r) for r in con.execute('SELECT * FROM catalog_imports ORDER BY import_id DESC LIMIT 30')]
        return dict(dispositions=dispositions,failed=failed,imports=imports,projection_version=VERSION,parser_version=PARSER_VERSION)

    def edit(self, ids, patch, actor):
        allowed = {'visibility','name','aliases','description','family','family_label','source_url','source_type','frequency','markets'}
        if not ids or len(ids)>100 or set(patch)-allowed or patch.get('visibility','PUBLIC') not in {'PUBLIC','HIDDEN'}:
            raise ValueError('Invalid catalog edit')
        for key, value in patch.items():
            if key in {'aliases','markets'}:
                if not isinstance(value,list) or len(value)>100 or any(not isinstance(v,str) or len(v)>500 for v in value):
                    raise ValueError('Invalid list field')
            elif value is not None and (not isinstance(value,str) or len(value)>3000):
                raise ValueError('Invalid text field')
        patch = deepcopy(patch)
        if 'source_url' in patch:
            patch['source_url'] = public_url(patch['source_url'])
        for key in ['name','description','family','family_label','source_type','frequency']:
            if key in patch:
                patch[key] = public_text(patch[key])
        if 'aliases' in patch:
            patch['aliases'] = [public_text(v) for v in patch['aliases']]
        with self.lock, self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            for eid in ids:
                row = con.execute('SELECT entity_id,payload,patch,visibility,is_test FROM catalog_items WHERE entity_id=?', (eid,)).fetchone()
                if not row:
                    raise KeyError(eid)
                before = self._value(row)
                updates = json.loads(row['patch']) | {k:v for k,v in patch.items() if k!='visibility'}
                after = before | updates
                visibility = patch.get('visibility',row['visibility'])
                con.execute('UPDATE catalog_items SET visibility=?,patch=?,search_text=? WHERE entity_id=?',
                            (visibility,stable_json(updates),self.index(after),eid))
                con.execute('INSERT INTO catalog_audit(created_at,actor,action,entity_id,before_json,after_json) VALUES (?,?,?,?,?,?)',
                            (now(),actor,'EDIT',eid,stable_json({k:before.get(k) for k in patch}),stable_json(patch)))
        return {'updated':len(ids),'notice':'历史已下载内容无法撤回。可见性不会改写历史研究 artifact。'}

    def edit_relation(self, rid, patch, actor):
        if set(patch)-{'visibility','review_status','evidence','confidence'} or patch.get('visibility','PUBLIC') not in {'PUBLIC','HIDDEN'}:
            raise ValueError('Invalid relation review')
        if 'confidence' in patch and (type(patch['confidence']) not in (int,float) or not 0<=patch['confidence']<=1):
            raise ValueError('Invalid confidence')
        if 'review_status' in patch and patch['review_status'] not in {'CANDIDATE','REVIEWED','REJECTED'}:
            raise ValueError('Invalid review status')
        if 'evidence' in patch:
            if not isinstance(patch['evidence'],str):raise ValueError('Invalid evidence')
            patch=patch | {'evidence':public_text(patch['evidence'])}
        with self.connect() as con:
            row = con.execute('SELECT * FROM catalog_edges WHERE relationship_id=?',(rid,)).fetchone()
            if not row:
                raise KeyError(rid)
            updates = json.loads(row['patch']) | {k:v for k,v in patch.items() if k!='visibility'}
            con.execute('UPDATE catalog_edges SET visibility=?,patch=? WHERE relationship_id=?',
                        (patch.get('visibility',row['visibility']),stable_json(updates),rid))
            con.execute('INSERT INTO catalog_audit(created_at,actor,action,entity_id,before_json,after_json) VALUES (?,?,?,?,?,?)',
                        (now(),actor,'REVIEW_RELATION',rid,row['patch'],stable_json(patch)))
        return {'updated':1}

    def audit(self, limit=100):
        with self.connect() as con:
            return [dict(r) for r in con.execute('SELECT * FROM catalog_audit ORDER BY audit_id DESC LIMIT ?', (limit,))]
