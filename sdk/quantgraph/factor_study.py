"""Definition snapshots shared by selection, mapping and writeback."""
import hashlib
import json


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def definition_identity(variant):
    value = dict(
        factor_concept_id=variant['canonical_factor_id'],
        factor_variant_id=variant['factor_variant_id'],
        source_revision=variant['source_revision'],
        source_snapshot={'uri': variant['source_url'], 'sha256': variant['source_sha256']},
        source_native_ids=variant['source_native_ids'],
        formula_id=variant['formula_id'], formula=variant['raw_formula'],
        formula_sha256=digest({'dialect': variant['dialect'], 'ast': variant['formula_ast']}),
    )
    value['definition_revision'] = digest({**value, 'parameters': variant['parameters'],
                                           'required_fields': variant['required_fields']})
    return value


def draft_request(db, names, request_id, settings):
    from quantgraph.models.factor_study import ResearchRequest
    rows = db.search_factors(source='qlib', limit=1000)
    selected = []
    for name in names:
        matches = [v for v in rows if 'Alpha158:' + name in v['source_native_ids']]
        if len(matches) != 1:
            raise ValueError('Missing or ambiguous collected definition: ' + name)
        selected.append(matches[0])
    if len(set(names)) != len(names):
        raise ValueError('Duplicate definitions')
    request = ResearchRequest(request_id=request_id, study_type='FACTOR_DIAGNOSTIC',
        entity_refs=[dict(entity_type='FactorVariant', entity_id=v['factor_variant_id'],
                          definition_revision=definition_identity(v)['definition_revision']) for v in selected],
        requested_settings=settings).model_dump(mode='json')
    return {'request': request, 'definitions': selected, 'graph_release': db.stats()['release']}
