"""One read-only knowledge directory over versioned, attributed repository records.

The directory aggregates evidence, not economic identities. It never imports a
runtime Catalog, changes a source record, or promotes a definition for execution.
"""
from collections import Counter, defaultdict
from copy import deepcopy
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

from jsonschema import Draft202012Validator

from quantgraph.db import AmbiguousAliasError
from quantgraph.graph.metadata_pilot import digest, encoded, read_below, validate


REGISTRY = 'quantgraph-catalog-registry/v1'


def stable_id(namespace, native_id):
    # Classification and revision deliberately do not participate in identity.
    return 'knowledge:' + digest(encoded([namespace, native_id]))[:32]


def _github_path(url):
    parsed = urlsplit(url or '')
    if parsed.scheme != 'https' or parsed.hostname != 'github.com' or parsed.username or parsed.password:
        return None
    parts = unquote(parsed.path).strip('/').split('/', 4)
    return ('/'.join(parts[:2]), parts[4]) if len(parts) == 5 and parts[2] == 'blob' else None


class KnowledgeCatalog:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.registry = self._json('metadata/catalog.json')
        if self.registry.get('schema_version') != REGISTRY:
            raise ValueError('Unsupported knowledge registry')
        self.entries, self.aliases, self.csv_rows = {}, defaultdict(set), {}
        self.edges, self._versions, self._identity_targets = {}, {}, {}
        self._used_overlays = set()
        self._factor_entries, self._factor_source_rows = set(), set()
        self._source_review_versions = set()
        self._collection_review_versions = set()
        self._collection_definition_signatures = set()
        self._collection_source_owners = {}
        self.counts = Counter()
        self.source_rows = Counter()
        collections = self.registry['collections']
        ids = [c['id'] for c in collections]
        if len(set(ids)) != len(ids):
            raise ValueError('Duplicate collection ID')
        paths = [str(Path(c['path'])) for c in collections]
        if len(set(paths)) != len(paths):
            raise ValueError('Duplicate collection path')
        loaders = {'csv_corpus': self._csv, 'classification': self._classification,
                   'factor_records': self._factors, 'reviewed_metadata': self._reviewed,
                   'reviewed_batches': self._batches, 'classification_batch': self._classification_batch,
                   'source_followups': self._source_followups,
                   'source_collection': self._source_collection}
        # Dependency ordering is semantic, not the order of paths in the registry.
        for kind in loaders:
            for collection in collections:
                if collection['kind'] == kind:
                    loaders[kind](collection['path'])
        if any(c['kind'] not in loaders for c in collections):
            raise ValueError('Unknown collection adapter')
        if self._used_overlays != {digest(encoded(o)) for o in self.registry.get('overlays', [])}:
            raise ValueError('Unresolved reviewed overlay binding')
        for record in self.entries.values():
            choices = {c['kind'] for c in record['classifications'] if c['kind'] != 'unclassified'}
            record['kind'] = next(iter(choices)) if len(choices) == 1 else 'unclassified'
            record['classification_conflict'] = len(choices) > 1
            record['classifications'].sort(key=lambda c: (c['kind'], c['status'], c['evidence']))
            record['versions'].sort(key=lambda v: (v['namespace'], v['native_id'], v['revision']))
            for key in ['native_ids', 'source_names', 'markets', 'frequencies', 'missing_information',
                        'content_subtypes', 'classification_flags']:
                record[key] = sorted(set(record[key]))
            record['statuses'] = {k: sorted(set(v)) for k, v in record['statuses'].items()}
            record['record_kinds'] = sorted(set(record['record_kinds']))
        for relation in self.edges.values():
            if relation['from_id'] not in self.entries or relation['to_id'] not in self.entries:
                raise ValueError('Unresolved knowledge relationship')

    def _json(self, relative):
        return json.loads(read_below(self.root, relative))

    def _checked(self, relative, reference):
        return json.loads(self._checked_bytes(relative, reference))

    def _checked_bytes(self, relative, reference):
        raw = read_below(self.root, relative)
        if digest(raw) != reference['sha256'] or len(raw) != reference['bytes']:
            raise ValueError('Knowledge record digest mismatch: ' + relative)
        return raw

    def _entry(self, namespace, native_id, name):
        eid = stable_id(namespace, native_id)
        if eid not in self.entries:
            self.entries[eid] = dict(entity_id=eid, name=name, kind='unclassified',
                identity=dict(namespace=namespace, native_id=native_id), native_ids=[],
                classifications=[], record_kinds=[], source_names=[], markets=[], frequencies=[],
                statuses=defaultdict(list), versions=[], missing_information=[],
                content_subtypes=[], classification_flags=[],
                current_version=None, current_version_policy='NO_IMPLICIT_LATEST_SELECTION')
        self._alias(eid, namespace, native_id)
        return self.entries[eid]

    def _alias(self, eid, namespace, native_id):
        self.aliases[native_id].add(eid)
        self.aliases[namespace + ':' + native_id].add(eid)
        self.entries[eid]['native_ids'].append(native_id)

    def _version(self, entry, namespace, native_id, raw, path, representation, **extra):
        revision = digest(encoded(raw))
        key = (namespace, native_id, representation, revision)
        previous = self._versions.get(key)
        if previous:
            if previous != entry['entity_id']:
                raise ValueError('Same source version bound to multiple entries')
            return
        identity = (namespace, native_id, representation)
        target = self._identity_targets.setdefault(identity, entry['entity_id'])
        if target != entry['entity_id']:
            raise ValueError('Source identity changed knowledge target across versions')
        self._versions[key] = entry['entity_id']
        entry['versions'].append(dict(namespace=namespace, native_id=native_id,
            revision=revision, path=path, representation=representation, record=raw, **extra))
        self._alias(entry['entity_id'], namespace, native_id)

    def _classify(self, entry, kind, status, evidence, **details):
        if kind not in {'strategy', 'factor', 'reference', 'unclassified'}:
            raise ValueError('Unknown classification')
        entry['classifications'].append(dict(kind=kind, status=status, evidence=evidence, **details))
        entry['statuses']['classification'].append(status)

    def _csv(self, path):
        corpus = self._json(path)
        parent = Path(path).parent
        observed, seen_paths = set(), set()
        for batch in corpus['batches']:
            batch_path = parent / batch['path']
            if str(batch_path) in seen_paths:
                raise ValueError('Duplicate CSV batch')
            seen_paths.add(str(batch_path))
            manifest_raw = read_below(self.root, str(batch_path / 'manifest.json'))
            if digest(manifest_raw) != batch['manifest_sha256']:
                raise ValueError('CSV batch manifest digest mismatch')
            frozen = json.loads(manifest_raw)
            metadata_path = batch_path / 'metadata'
            # Bind schemas and index to the already frozen checkpoint manifest;
            # re-hashing an edited row/index cannot erase its source lineage.
            for name in ['metadata/index.json', 'metadata/schema.json', 'metadata/source-record.schema.json']:
                self._checked(str(batch_path / name), frozen['files'][name])
            records = [r for r in validate(self.root / metadata_path) if r['entity_type'] == 'source_record']
            index = self._json(str(metadata_path / 'index.json'))
            refs = {r['record_id']: r for r in index['records'] if r['entity_type'] == 'source_record'}
            if len(records) != batch['record_count']:
                raise ValueError('CSV batch count mismatch')
            for r in records:
                rid = r['record_id']
                if rid in self.csv_rows:
                    raise ValueError('Duplicate CSV native identity')
                observed.add(rid)
                record_path = str(metadata_path / refs[rid]['path'])
                if frozen['files']['metadata/' + refs[rid]['path']] != {
                        k: refs[rid][k] for k in ['sha256', 'bytes']}:
                    raise ValueError('CSV row no longer matches the frozen checkpoint')
                self.csv_rows[rid] = dict(record=r, path=record_path)
                values = {k: v['value'] for k, v in r['reported_fields'].items()}
                e = self._entry(r['identity_namespace'], rid, values['名称'] or values['标题'] or rid)
                self.csv_rows[rid]['entity_id'] = e['entity_id']
                e['source_names'].append('grokbot')
                e['markets'].extend([values['市场']] if values['市场'] else [])
                e['record_kinds'].append('source_candidate')
                e['statuses']['source_verification'].append('CATALOG_REPORTED_UNVERIFIED')
                e['statuses']['economic_validity'].append('NOT_ESTABLISHED_BY_COLLECTION')
                e['statuses']['commercial_rights'].append('REVIEW_REQUIRED')
                e['missing_information'].append('来源规则及执行条件尚未完整审核')
                self._classify(e, 'unclassified', 'UNREVIEWED', r['provenance']['row_sha256'])
                self._version(e, r['identity_namespace'], rid, r, record_path, 'SOURCE_RECORD',
                              row_sha256=r['provenance']['row_sha256'])
        if len(observed) != corpus['counts']['public_source_records']:
            raise ValueError('CSV corpus coverage mismatch')
        self.source_rows['csv'] += len(observed)

    def _classification(self, path):
        directory, parent = self._json(path), Path(path).parent
        seen = set()
        for view in directory['records']:
            rid, decision = view['record_id'], view['classification']
            if rid in seen:
                raise ValueError('Duplicate reading classification')
            seen.add(rid)
            original = self.csv_rows[rid]['record']
            for key in ['row_sha256', 'rule_sha256']:
                if decision[key] != original['provenance'][key]:
                    raise ValueError('Classification targets a different source version')
            source_path = str(parent / view['source']['path'])
            if source_path != self.csv_rows[rid]['path']:
                raise ValueError('Reading source path mismatch')
            self._checked(source_path, view['source'])
            raw = read_below(self.root, str(parent / view['view']['path']))
            if len(raw) != view['view']['bytes'] or digest(raw) != view['view']['sha256']:
                raise ValueError('Reading view digest mismatch')
            e = self.entries[self.csv_rows[rid]['entity_id']]
            self._classify(e, decision['entity_type'], 'CONTENT_INFERRED', decision['row_sha256'])
        self.counts['reading_views'] += len(seen)

    def _classification_batch(self, path):
        from quantgraph.graph.classification_batch import validate_batch
        _, decisions = validate_batch(self.root, path, self.csv_rows)
        for decision in decisions:
            e = self.entries[self.csv_rows[decision['record_id']]['entity_id']]
            self._classify(e, decision['kind'], 'CONTENT_INFERRED', decision['row_sha256'],
                reason=decision['reason'], evidence_quotes=decision['evidence'],
                subtype=decision['subtype'], confidence=decision['confidence'],
                rule_id=decision['rule_id'], batch_path=path,
                definition_status='UNVERIFIED', quality_flags=decision['quality_flags'])
            e['content_subtypes'].append(decision['subtype'])
            e['classification_flags'].extend(decision['quality_flags'])
            e['statuses']['definition_verification'].append(decision['definition_status'])
        self.counts['classification_decisions'] += len(decisions)

    def _factors(self, path):
        index, parent = self._json(path), Path(path).parent
        if index['schema_version'] != 'quantgraph-factor-metadata-index/v1':
            raise ValueError('Unsupported factor metadata index')
        schema_ref = index['schema_reference']
        schema = self._checked(str(parent / schema_ref['path']), schema_ref)
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        for license_ref in index['license_notices']:
            self._checked_bytes(str(parent / license_ref['path']), license_ref)
        listed, identities, source_ids, native_ids = set(), set(), set(), set()
        for ref in index['records']:
            relative = str(parent / ref['path'])
            r = self._checked(relative, ref)
            validator.validate(r)
            if r['record_id'] != ref['record_id'] or relative in listed or r['record_id'] in identities:
                raise ValueError('Factor metadata identity mismatch')
            listed.add(relative)
            identities.add(r['record_id'])
            local_sources = {s['record_id'] for s in r['sources']}
            local_natives = {(s['source_id'], s['native_id']) for s in r['sources']}
            if (len(local_sources) != len(r['sources']) or len(local_natives) != len(r['sources'])
                    or source_ids & local_sources or native_ids & local_natives):
                raise ValueError('Duplicate factor source identity in collection')
            source_ids |= local_sources
            native_ids |= local_natives
            lines = r['provenance']['source_lines']
            if (local_sources != set(r['identity']['source_record_ids'])
                    or local_sources != {line['record_id'] for line in lines}
                    or len(lines) != len(local_sources)
                    or set(r['native_source_ids']) != {s['native_id'] for s in r['sources']}):
                raise ValueError('Factor source identity mapping mismatch')
            snapshot = r['provenance']['source_snapshot_sha256']
            if snapshot != index['source_snapshot']['sha256']:
                raise ValueError('Factor source snapshot mismatch')
            e = self._entry(r['identity_namespace'], r['record_id'], r['name'])
            self._classify(e, 'factor', 'SOURCE_DEFINITION_REGISTERED', ref['sha256'])
            e['record_kinds'].append(r['record_kind'])
            e['source_names'].extend(s['source_id'] for s in r['sources'])
            domain = r['domain']
            for key, target in [('asset_class', 'markets'), ('frequency', 'frequencies')]:
                value = domain.get(key)
                if value:
                    e[target].extend(value if isinstance(value, list) else [str(value)])
            e['statuses']['definition'].append(str(r['admission'].get('status', 'REGISTERED')))
            e['statuses']['computation_semantics'].append('NOT_VERIFIED')
            e['statuses']['economic_validity'].append('NOT_ESTABLISHED_BY_COLLECTION')
            rights = r['rights'].get('commercial_use', ['REVIEW_REQUIRED'])
            e['statuses']['commercial_rights'].extend(rights if isinstance(rights, list) else [rights])
            e['missing_information'].extend(r['missing_information'])
            self._version(e, r['identity_namespace'], r['record_id'], r, relative, 'FACTOR_DEFINITION')
            for native in r['native_source_ids']:
                self._alias(e['entity_id'], r['identity_namespace'], native)
            for source in r['sources']:
                self._alias(e['entity_id'], source['source_id'], source['native_id'])
            self._factor_entries.add(e['entity_id'])
            self._factor_source_rows.update((snapshot, sid) for sid in local_sources)
        actual = {str(p.relative_to(self.root)) for p in (self.root / parent / 'records').rglob('*.json')}
        if actual != listed:
            raise ValueError('Factor index does not cover exactly its records')
        if len(listed) != index['counts']['variants']:
            raise ValueError('Factor variant count mismatch')
        if len(source_ids) != index['counts']['source_records']:
            raise ValueError('Factor source row count mismatch')
        self.source_rows['factor_sources'] = len(self._factor_source_rows)
        self.counts['factor_variants'] = len(self._factor_entries)

    def _source_followups(self, path):
        from quantgraph.graph.source_review import validate as validate_review
        index, records = validate_review(self.root, path, self.csv_rows)
        refs = {r['record_id']: r for r in index['records']}
        for record in records:
            rid = record['record_id']
            version = (rid, digest(encoded(record)))
            if version in self._source_review_versions:
                continue
            self._source_review_versions.add(version)
            entry = self.entries[self.csv_rows[rid]['entity_id']]
            classification = record['classification']
            relative = str(Path(path).parent / refs[rid]['path'])
            self._classify(entry, classification['kind'], record['outcome'], refs[rid]['sha256'],
                subtype=classification['subtype'], reason=classification['reason'],
                source_evidence=classification['evidence'], review_path=relative)
            entry['content_subtypes'].append(classification['subtype'])
            entry['statuses']['source_followup'].append(record['outcome'])
            entry['statuses']['computation_semantics'].append(record['computation_semantics'])
            entry['statuses']['economic_validity'].append(record['economic_validity'])
            entry['statuses']['commercial_rights'].append(record['commercial_use'])
            entry['missing_information'].extend(record['missing_information'])
            for source in record['sources']:
                if source['kind'] != 'license':
                    entry['source_names'].extend([source['attribution'], urlsplit(source['url']).hostname])
            timeframe = record['fields']['timeframe']
            if timeframe['status'] in {'SOURCE_CODE_REVIEWED', 'SOURCE_DESCRIPTION_REVIEWED'}:
                entry['frequencies'].append(timeframe['text'])
            self._version(entry, entry['identity']['namespace'], rid, record, relative, 'SOURCE_FOLLOWUP')
            self.counts['source_reviews'] += 1
            if record['outcome'] != 'SOURCE_UNAVAILABLE':
                entry['statuses']['source_verification'].append(record['outcome'])
                self.counts['reviewed_representations'] += 1
            if record['outcome'] == 'SOURCE_CODE_REVIEWED':
                entry['record_kinds'].append('source_implementation')

    def _batches(self, path):
        root = self.root / path
        read_below(self.root, path + '/README.md')  # reject traversal and symlink roots
        for directory in sorted(root.iterdir()):
            if not directory.is_dir():
                continue
            for required in ['index.json', 'manifest.json', 'source-lock.json', 'schema.json']:
                read_below(self.root, str((directory / required).relative_to(self.root)))
            self._reviewed(str((directory / 'index.json').relative_to(self.root)), batch=True)

    def _reviewed(self, path, batch=False):
        parent = Path(path).parent
        index = self._json(path)
        records = validate(self.root / parent)
        refs = {(r['identity_namespace'], r['record_id']): r for r in index['records']}
        if len(refs) != len(index['records']):
            raise ValueError('Ambiguous reviewed source identity in one batch')
        declarations = {}
        if batch:
            manifest = self._json(str(parent / 'manifest.json'))
            declarations = {(r['identity_namespace'], r['record_id']): r for r in manifest['records']}
            lock = self._json(str(parent / 'source-lock.json'))
            locked = {r['id']: r for r in lock['files']}
            if (len(locked) != len(lock['files']) or set(declarations) != set(refs)
                    or len(declarations) != len(manifest['records'])):
                raise ValueError('Reviewed batch membership mismatch')
            for frozen in locked.values():
                if (not re.fullmatch(r'[0-9a-f]{40}', frozen['revision'])
                        or not re.fullmatch(r'[0-9a-f]{64}', frozen['sha256'])
                        or frozen['url'] != f"https://github.com/{frozen['repository']}/blob/{frozen['revision']}/{frozen['path']}"
                        or frozen['fetch_url'] != f"https://raw.githubusercontent.com/{frozen['repository']}/{frozen['revision']}/{frozen['path']}"):
                    raise ValueError('Source lock must pin an immutable upstream commit')
        for r in records:
            ns, rid = r['identity_namespace'], r['record_id']
            ref = refs[(ns, rid)]
            matches = declarations.get((ns, rid), {}).get('catalog_matches', [])
            exact = [m for m in matches if m['match_type'] == 'SAME_SOURCE_PATH']
            if len(exact) > 1:
                raise ValueError('Ambiguous source-to-card binding')
            overlay = [o for o in self.registry.get('overlays', []) if o['namespace'] == ns and o['native_id'] == rid]
            if len(overlay) > 1:
                raise ValueError('Ambiguous reviewed overlay')
            if exact:
                target = self._match(exact[0], r)
                e = self.entries[target['entity_id']]
            elif overlay:
                binding = overlay[0]
                target = self.csv_rows[rid]
                if (binding['row_sha256'] != target['record']['provenance']['row_sha256']
                        or binding['metadata_sha256'] != ref['sha256']):
                    raise ValueError('Reviewed overlay version mismatch')
                self._used_overlays.add(digest(encoded(binding)))
                e = self.entries[target['entity_id']]
            else:
                if rid in self.csv_rows and self.csv_rows[rid]['record']['identity_namespace'] == ns:
                    raise ValueError('Reviewed CSV identity requires an explicit overlay binding')
                e = self._entry(ns, rid, r['name'])
            if batch:
                for source in r['sources']:
                    frozen = locked[source['id']]
                    if any(source[k] != frozen[k] for k in ['url', 'revision', 'sha256']):
                        raise ValueError('Reviewed source differs from immutable lock')
            self._classify(e, r['entity_type'], 'REVIEWED_TYPE', ref['sha256'])
            e['record_kinds'].append('source_implementation')
            e['source_names'].append(ns)
            e['statuses']['source_verification'].append('SOURCE_CODE_REVIEWED')
            e['statuses']['computation_semantics'].append('NOT_VERIFIED')
            e['statuses']['economic_validity'].append('NOT_ESTABLISHED_BY_COLLECTION')
            e['statuses']['commercial_rights'].append('REVIEW_REQUIRED')
            e['missing_information'].extend(r['missing_information'])
            e['markets'].extend(declarations.get((ns, rid), {}).get('markets', []))
            fields = r.get('strategy_fields') or r.get('factor_fields') or {}
            if fields.get('timeframe', {}).get('status') == 'SOURCE_CODE_REVIEWED':
                e['frequencies'].append(fields['timeframe']['text'])
            self._version(e, ns, rid, r, str(parent / ref['path']), 'REVIEWED_METADATA',
                          binding='SOURCE_EVIDENCE_AGGREGATION_NOT_EQUIVALENCE' if exact else 'EXPLICIT_IDENTITY')
            self.counts['reviewed_representations'] += 1
            for match in matches:
                target = self._match(match, r)
                relation = dict(from_id=e['entity_id'], to_id=target['entity_id'],
                    relation=match['match_type'], role=match['role'], confidence=match['confidence'],
                    evidence=match['evidence'], source=match['source'], row_sha256=match['row_sha256'],
                    implementation_identity=dict(namespace=ns, native_id=rid, revision=ref['sha256']),
                    equivalence_claimed=False)
                key = digest(encoded(relation))
                self.edges[key] = {'relationship_id': 'knowledge-edge:' + key, **relation}

    def _match(self, match, record):
        original = self.csv_rows[match['record_id']]
        if (match['row_sha256'] != original['record']['provenance']['row_sha256']
                or match['source_record_path'] != original['path']):
            raise ValueError('Catalog match targets another source version')
        if match['equivalence_claimed'] is not False:
            raise ValueError('Source locator match cannot assert economic equivalence')
        if match['match_type'] not in {'SAME_SOURCE_PATH', 'POSSIBLE_CONCEPT_OVERLAP'}:
            raise ValueError('Unsupported catalog match')
        evidence_ids = {s['id'] for s in record['sources']} | {f"catalog:{match['record_id']}:row_sha256"}
        if not match['evidence'] or not set(match['evidence']) <= evidence_ids:
            raise ValueError('Unresolved match evidence')
        if not all(match.get(k) for k in ['role', 'confidence', 'source']):
            raise ValueError('Incomplete relationship attribution')
        if match['match_type'] == 'SAME_SOURCE_PATH':
            old = original['record']['reported_fields']['source_url']['value']
            paths = {_github_path(s['url']) for s in record['sources']} - {None}
            if _github_path(old) not in paths:
                raise ValueError('Source path match is not supported by source URLs')
        return original

    def _source_collection(self, directory):
        from quantgraph.graph.collection_batch import validate_collection
        result = validate_collection(self.root, directory)
        refs = {(ref['identity_namespace'], ref['entity_type'], ref['record_id']): ref
                for ref in self._json(directory + '/index.json')['records']}
        for record in result['records']:
            ns, kind, rid = (record[key] for key in ('identity_namespace', 'entity_type', 'record_id'))
            review = result['reviews'][(ns, kind, rid)]
            if review['dedup']['outcome'] != 'REVIEWED_DISTINCT_CONSTRUCTION':
                raise ValueError('Only reviewed new definitions enter this collection adapter')
            combined = dict(metadata=record, review=review)
            revision = digest(encoded(combined))
            identity = (ns, rid, revision)
            if identity in self._collection_review_versions:
                continue
            signature = review['definition_signature']
            if signature in self._collection_definition_signatures:
                raise ValueError('Repeated collection definition across batches')
            source_keys = result['source_keys'][(ns, kind, rid)]
            for source_key in sorted(source_keys):
                if source_key in self._collection_source_owners:
                    raise ValueError(f'Repeated collection source definition across batches: {ns}:{rid} and '
                                     f'{self._collection_source_owners[source_key]} share {source_key}')
            eid = stable_id(ns, rid)
            if eid in self.entries:
                raise ValueError('New collection definition collides with an existing knowledge identity')
            self._collection_review_versions.add(identity)
            self._collection_definition_signatures.add(signature)
            self._collection_source_owners.update((source_key, ns + ':' + rid) for source_key in source_keys)
            entry = self._entry(ns, rid, record['name'])
            self._classify(entry, kind, 'SOURCE_DEFINITION_REVIEWED', revision)
            entry['record_kinds'].append('source_definition')
            entry['source_names'].append(ns)
            entry['source_names'].extend(source['attribution'] for source in record['sources'])
            entry['markets'].extend(review.get('markets', []))
            entry['frequencies'].extend(review.get('frequencies', []))
            entry['content_subtypes'].append(review['subtype'])
            entry['statuses']['collection_review'].append('REVIEWED_NEW_DEFINITION')
            entry['statuses']['definition_verification'].append('CORE_RULES_REVIEWED')
            fields = record.get('strategy_fields') or record['factor_fields']
            entry['statuses']['source_verification'].extend(field['status'] for field in fields.values()
                if field['status'] in {'SOURCE_CODE_REVIEWED', 'SOURCE_DESCRIPTION_REVIEWED'})
            for name, value in review['states'].items():
                entry['statuses']['commercial_rights' if name == 'commercial_use' else name].append(value)
            entry['statuses']['source_origin'].append(review.get('source_origin', 'PINNED_PUBLISHED_VERSION'))
            entry['missing_information'].extend(record['missing_information'])
            ref = refs[(ns, kind, rid)]
            self._version(entry, ns, rid, combined, directory + '/' + ref['path'],
                          'COLLECTION_REVIEWED_METADATA', collection_batch=result['manifest']['batch_id'])
            self.counts['source_collection_entries'] += 1
            self.counts['collected_' + kind] += 1

    def stats(self):
        return dict(schema_version='quantgraph-knowledge-stats/v1', unique_entries=len(self.entries),
            kinds=dict(sorted(Counter(r['kind'] for r in self.entries.values()).items())),
            record_kinds=dict(sorted(Counter(k for r in self.entries.values() for k in r['record_kinds']).items())),
            source_rows=dict(self.source_rows), versions=len(self._versions), relationships=len(self.edges),
            classification_conflicts=sum(r['classification_conflict'] for r in self.entries.values()),
            classified_csv=sum(self.entries[r['entity_id']]['kind'] != 'unclassified' for r in self.csv_rows.values()),
            **{k: self.counts[k] for k in ['reading_views', 'reviewed_representations', 'factor_variants', 'classification_decisions', 'source_reviews',
                                          'source_collection_entries', 'collected_strategy', 'collected_factor']},
            counting_rule='Unique knowledge entries; evidence versions and source rows are not added to this count. No global economic-equivalence claim.')

    def _resolve(self, identity):
        if identity in self.entries:
            return identity
        matches = self.aliases.get(identity, set())
        if len(matches) > 1:
            raise AmbiguousAliasError('Ambiguous native ID; specify source namespace or entity_id')
        if not matches:
            raise KeyError(identity)
        return next(iter(matches))

    def get(self, identity):
        return deepcopy(self.entries[self._resolve(identity)])

    def relations(self, identity):
        eid = self._resolve(identity)
        return deepcopy([r for r in self.edges.values() if eid in {r['from_id'], r['to_id']}])

    def search(self, query=None, *, kind=None, source=None, status=None, market=None,
               frequency=None, record_kind=None, subtype=None, limit=50, offset=0):
        if not 1 <= limit <= 1000 or offset < 0:
            raise ValueError('limit must be 1..1000 and offset nonnegative')
        if kind is not None and kind not in {'strategy', 'factor', 'reference', 'unclassified'}:
            raise ValueError('Unknown knowledge kind')
        rows = []
        for record in sorted(self.entries.values(), key=lambda r: r['entity_id']):
            if kind and record['kind'] != kind:
                continue
            filters = [(source, record['source_names']), (market, record['markets']),
                       (frequency, record['frequencies']), (record_kind, record['record_kinds']),
                       (subtype, record['content_subtypes'])]
            if any(value and not any(value.casefold() in s.casefold() for s in choices)
                   for value, choices in filters):
                continue
            if status and status.casefold() not in {
                    s.casefold() for values in record['statuses'].values() for s in values}:
                continue
            if query:
                haystack = json.dumps(record, ensure_ascii=False).casefold()
                if not all(word in haystack for word in query.casefold().split()):
                    continue
            rows.append({k: deepcopy(v) for k, v in record.items() if k != 'versions'})
        return dict(items=rows[offset:offset + limit], total=len(rows), limit=limit, offset=offset)
