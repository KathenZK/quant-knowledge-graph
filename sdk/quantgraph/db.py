"""Read-only SDK for curated releases. No research engine or runner dependency."""
import json
import os
from pathlib import Path
import sqlite3
from quantgraph.normalize.aliases import key as alias_key


def project_root(root=None):
    if root is not None:
        return Path(root).expanduser().resolve()
    if os.getenv('QUANTGRAPH_ROOT'):
        return Path(os.environ['QUANTGRAPH_ROOT']).expanduser().resolve()
    candidate=Path(__file__).resolve().parents[2]
    if (candidate/'datasets/raw/source_lock.json').exists():
        return candidate
    raise FileNotFoundError('Set QUANTGRAPH_ROOT or FactorDB(root=...) to the knowledge graph repository')


class AmbiguousAliasError(ValueError):
    pass


class FactorDB:
    def __init__(self, root=None, *, profile='research', database=None):
        if profile not in {'research','commercial'}:
            raise ValueError('profile must be research or commercial')
        if database is not None and profile=='commercial':
            raise ValueError('commercial mode requires a verified curated commercial release')
        self.profile=profile
        self.dataset_scope='research'
        if database is None:
            release=project_root(root)/'datasets/curated/current'
            if not (release/'quantgraph.sqlite').is_file():
                from quantgraph.graph.public import public_release
                self.release_path=public_release(project_root(root)).resolve()
                db_path=self.release_path/'quantgraph.sqlite'
                self.profile='commercial'
                self.dataset_scope='public_qlib'
            else:
                self.release_path=release.resolve()
                db_path=self.release_path/('commercial/quantgraph.sqlite' if profile=='commercial' else 'quantgraph.sqlite')
        else:
            db_path=Path(database).resolve();self.release_path=db_path.parent
        if not db_path.is_file():
            raise FileNotFoundError(f'Curated database missing: {db_path}; run quantgraph build')
        self.path=db_path.resolve()

    def _query(self, sql, params=()):
        with sqlite3.connect(self.path.as_uri()+'?mode=ro&immutable=1',uri=True) as con:
            return con.execute(sql,params).fetchall()

    def _objects(self, sql, params=()):
        return [json.loads(row[0]) for row in self._query(sql,params)]

    def search_factors(self, query=None, *, category=None, asset_class=None, source=None, limit=100, offset=0):
        if not 1<=limit<=1000 or offset<0:
            raise ValueError('limit must be 1..1000 and offset must be nonnegative')
        clauses=[];params=[]
        for field,value in [('v.category',category),('v.asset_class',asset_class),('v.source_id',source)]:
            if value is not None:
                clauses.append(field+'=?');params.append(value)
        if query:
            clauses.append('(v.variant_name LIKE ? OR v.canonical_name LIKE ? OR v.aliases LIKE ? OR c.aliases LIKE ? OR v.category LIKE ? OR v.source_native_ids LIKE ?)')
            params.extend(['%'+query+'%']*6)
        where=' WHERE '+' AND '.join(clauses) if clauses else ''
        return self._objects('SELECT v.payload FROM factor_variants v JOIN factor_concepts c USING(canonical_factor_id)'+where+' ORDER BY v.factor_variant_id LIMIT ? OFFSET ?',params+[limit,offset])

    def get_variant(self, variant_id):
        rows=self._objects('SELECT payload FROM factor_variants WHERE factor_variant_id=?',(variant_id,))
        if not rows:
            raise KeyError(variant_id)
        return rows[0]

    def get_factor(self, factor_id, *, namespace=None):
        rows=self._objects('SELECT payload FROM factor_concepts WHERE canonical_factor_id=? OR short_id=?',(factor_id,factor_id))
        if not rows:
            variant=self._query('SELECT canonical_factor_id FROM factor_variants WHERE factor_variant_id=?',(factor_id,))
            if variant:
                return self.get_factor(variant[0][0])
            params=[alias_key(factor_id)]
            where='normalized_alias=?'
            if namespace is not None:
                where+=' AND namespace=?';params.append(namespace)
            matches={r[0] for r in self._query('SELECT DISTINCT canonical_factor_id FROM aliases WHERE '+where,params)}
            if namespace is None:
                for cid, name, aliases in self._query('SELECT canonical_factor_id,canonical_name,aliases FROM factor_concepts'):
                    if alias_key(factor_id) in {alias_key(a) for a in [name]+json.loads(aliases)}:
                        matches.add(cid)
            if len(matches)>1:
                raise AmbiguousAliasError(f'Alias {factor_id!r} matches {len(matches)} concepts; use a canonical ID and source namespace')
            if not matches:
                raise KeyError(factor_id)
            return self.get_factor(next(iter(matches)))
        concept=rows[0]
        concept['variants']=self._objects('SELECT payload FROM factor_variants WHERE canonical_factor_id=? ORDER BY factor_variant_id',(concept['canonical_factor_id'],))
        return concept

    def find_related_factors(self, factor_id):
        concept=self.get_factor(factor_id)
        return dict(concept=concept['canonical_factor_id'], relation='VARIANT_OF', variants=concept['variants'],
                    interpretation='Shared family; not mathematical equivalence or proven return attribution')

    def find_strategies(self, *, factor=None, limit=100, offset=0):
        if not 1<=limit<=1000 or offset<0:
            raise ValueError('invalid pagination')
        if not factor:
            return self._objects('SELECT payload FROM strategies ORDER BY strategy_id LIMIT ? OFFSET ?',(limit,offset))
        try:
            cid=self.get_factor(factor)['canonical_factor_id'];ids=[cid]
        except KeyError:
            ids=sorted({v['canonical_factor_id'] for v in self.search_factors(factor,limit=1000)})
        if not ids:
            return []
        placeholders=','.join('?' for _ in ids)
        return self._objects('SELECT DISTINCT s.payload FROM strategies s JOIN strategy_factor sf USING(strategy_id) WHERE sf.factor_id IN ('+placeholders+') ORDER BY s.strategy_id LIMIT ? OFFSET ?',ids+[limit,offset])

    def get_strategy_factors(self, strategy_id):
        return self._objects('SELECT payload FROM strategy_factor WHERE strategy_id=? ORDER BY variant_id,role',(strategy_id,))

    def get_entity(self, entity_type, entity_id):
        from quantgraph.graph.store import PRIMARY_KEYS, TYPES
        mapping={kind:(table,PRIMARY_KEYS[table]) for table,kind in TYPES.items()}
        if entity_type not in mapping:
            raise KeyError(entity_type)
        table,key=mapping[entity_type]
        result=self._objects(f'SELECT payload FROM "{table}" WHERE "{key}"=?',(entity_id,))
        if not result:
            raise KeyError(entity_id)
        return result[0]

    def relationships(self, entity_id, *, limit=100, offset=0):
        if not 1<=limit<=1000 or offset<0:
            raise ValueError('invalid pagination')
        return self._objects('SELECT payload FROM relationships WHERE from_id=? OR to_id=? ORDER BY relationship_id LIMIT ? OFFSET ?',(entity_id,entity_id,limit,offset))

    def stats(self):
        from quantgraph.graph.store import PRIMARY_KEYS
        return dict(profile=self.profile, dataset_scope=self.dataset_scope, release=self.release_path.name,
                    counts={table:self._query(f'SELECT count(*) FROM "{table}"')[0][0] for table in [*PRIMARY_KEYS,'strategy_factor']})
