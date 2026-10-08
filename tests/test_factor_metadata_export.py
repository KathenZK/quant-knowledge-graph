"""Identity, rights, provenance and completeness checks for factor metadata."""
import json
from pathlib import Path
from uuid import UUID

import pytest

from scripts.export_factor_metadata import (
    bounded_excerpt, digest, encode, generate, validate,
)

ROOT = Path(__file__).resolve().parents[1]


def source_row(source='qlib', number=1, **updates):
    row = {
        'record_id': 'qkg:record:' + str(UUID(int=number)),
        'factor_variant_id': 'qkg:factor:' + str(UUID(int=number)),
        'legacy_canonical_factor_id': 'legacy:' + str(number),
        'canonical_factor_id': 'concept:' + str(number), 'concept_id': 'concept:' + str(number),
        'source_id': source, 'source_name': source, 'source_native_id': 'native' + str(number),
        'signal_name': 'Example ' + str(number), 'record_kind': 'signal',
        'source_url': 'https://example.org/source', 'source_locator': 'definition:1',
        'source_file_sha256': 'a' * 64, 'source_response_sha256': None,
        'source_revision': 'b' * 40, 'retrieved_at': '2026-10-04T00:00:00Z',
        'authors': ['Example author'], 'primary_source': True,
        'formula': '$close', 'raw_formula': '$close', 'raw_definition': '$close',
        'dialect': source, 'parameters': {'operators': ['mean'], 'numeric_literals': ['20']},
        'required_fields': ['close'], 'required_fields_status': 'syntax_extracted_unexpanded',
        'curation_status': 'ADMITTED', 'curation_reasons': [], 'quality_tier': 'primary_definition',
        'parse_status': 'parsed', 'semantic_status': 'not_verified', 'backtest_ready': False,
        'license': 'TEST SOURCE LICENSE', 'license_id': 'license:1', 'rights_status': 'REVIEW_REQUIRED',
        'commercial_use': 'REVIEW_REQUIRED', 'redistribution_allowed': 'REVIEW_REQUIRED',
        'derivative_allowed': 'REVIEW_REQUIRED', 'raw_data_allowed': 'REVIEW_REQUIRED',
        'rights_scope': 'Example scope', 'terms_url': 'https://example.org/terms',
        'attribution_required': True,
    }
    row.update(updates)
    return row


def inputs(tmp_path, rows, admitted=None, public=None):
    raw = b''.join(json.dumps(row, ensure_ascii=False).encode() + b'\n' for row in rows)
    normalized = tmp_path / 'source.jsonl'
    normalized.write_bytes(raw)
    admitted = admitted if admitted is not None else {r['factor_variant_id'] for r in rows}
    public = public or set()
    release_paths = []
    for name, ids in [('curated', admitted), ('public', public)]:
        release = tmp_path / name
        release.mkdir()
        (release / 'factor_variants.jsonl').write_bytes(b''.join(encode({
            'factor_variant_id': key, 'canonical_factor_id': 'curated:' + key,
        }).replace(b'\n', b'') + b'\n' for key in sorted(ids)))
        (release / 'release.json').write_bytes(encode({'scope': name}))
        release_paths.append(release)
    project = tmp_path / 'input-project'
    lock = project / 'datasets/raw/source_lock.json'
    lock.parent.mkdir(parents=True)
    entries = []
    for source, native in [('osap', 'LICENSE'), ('jkp', 'DATA_LICENSE')]:
        relative = Path('datasets/raw/sources') / source / native
        body = f'{source} test license notice\n'.encode()
        path = project / relative
        path.parent.mkdir(parents=True)
        path.write_bytes(body)
        entries.append({'key': source + ':' + native, 'path': str(relative),
            'sha256': digest(body), 'bytes': len(body), 'url': 'https://example.org/' + source,
            'revision': 'b' * 40, 'retrieved_at': '2026-10-04T00:00:00Z'})
    lock.write_bytes(encode(entries))
    return normalized, *release_paths, lock


def materialize(tmp_path, files):
    out = tmp_path / 'output'
    for name, body in files.items():
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    return out


def exported_records(files):
    return [json.loads(body) for name, body in files.items() if name.startswith('records/')]


def test_current_catalogue_is_complete_and_internally_verified():
    counts = validate(ROOT / 'metadata/factor-sources')
    assert counts['variants'] == 1570
    assert counts['source_records'] == 1578
    assert counts['curated_members'] == 1085
    assert counts['historical_public_export_members'] == 508
    assert counts['source_variants'] == {
        'aqr': 6, 'french': 9, 'gtja191': 191, 'jkp': 422,
        'osap': 331, 'qlib': 510, 'wq101': 101,
    }
    assert counts['record_kind'] == {
        'signal': 1415, 'placebo': 114, 'withdrawn': 5,
        'parameter_template': 21, 'factor_portfolio': 15,
    }


def test_duplicate_variant_preserves_both_native_records_and_line_hashes(tmp_path):
    first = source_row()
    second = source_row(number=2, factor_variant_id=first['factor_variant_id'],
                        source_native_id='another_feature_name', parameters={'window_or_lag': 0})
    args = inputs(tmp_path, [first, second], public={first['factor_variant_id']})
    files = generate(*args)
    record, = exported_records(files)
    assert record['native_source_ids'] == ['another_feature_name', 'native1']
    assert len(record['sources']) == 2
    assert record['sources'][1]['parameters'] == {'window_or_lag': 0}
    source_lines = args[0].read_bytes().splitlines()
    assert [x['line_sha256'] for x in record['provenance']['source_lines']] == list(map(digest, source_lines))
    assert record['provenance']['source_snapshot_sha256'] == digest(args[0].read_bytes())
    assert generate(*args) == files
    assert validate(materialize(tmp_path, files))['variants'] == 1


def test_native_names_do_not_merge_sources_and_rights_do_not_expand(tmp_path):
    rows = [source_row('wq101', 1, source_native_id='alpha001',
                      raw_formula='FULL_PRIVATE_FORMULA_A', formula='FULL_PRIVATE_FORMULA_A',
                      raw_definition='FULL_PRIVATE_FORMULA_A', primary_source=False),
            source_row('gtja191', 2, source_native_id='alpha001',
                      raw_formula='FULL_PRIVATE_FORMULA_B', formula='FULL_PRIVATE_FORMULA_B',
                      raw_definition='FULL_PRIVATE_FORMULA_B', primary_source=False),
            source_row('jkp', 3, formula=None, raw_formula=None,
                      raw_definition=r'$\frac{XAD_t}{SALE_t}$', commercial_use='PROHIBITED',
                      redistribution_allowed='CONDITIONAL')]
    files = generate(*inputs(tmp_path, rows, admitted=set()))
    records = exported_records(files)
    assert len(records) == 3
    assert all('FULL_PRIVATE_FORMULA_' not in body.decode() for body in files.values())
    secondary = [r for r in records if r['sources'][0]['source_id'] != 'jkp']
    assert all(r['definition']['formula'] is None for r in secondary)
    assert all(r['definition']['required_fields'] == ['close'] for r in secondary)
    assert all('不保留完整运算顺序' in r['definition']['text'] for r in secondary)
    jkp = next(r for r in records if r['sources'][0]['source_id'] == 'jkp')
    assert jkp['rights']['commercial_use'] == ['PROHIBITED']
    assert jkp['definition']['text'] == rows[2]['raw_definition']
    assert not jkp['quality']['backtest_ready']
    assert jkp['sources'][0]['paper']['permission'] == 'REVIEW_REQUIRED'
    assert validate(materialize(tmp_path, files))['variants'] == 3


def test_excerpt_never_silently_becomes_full_definition_and_missing_stays_missing(tmp_path):
    long = 'First complete rule sentence. ' + 'Next rule must retain many qualifications ' * 30
    assert bounded_excerpt(long) == ('First complete rule sentence.', True)
    rows = [source_row('osap', 1, raw_definition=long, formula=None, raw_formula=None),
            source_row('aqr', 2, raw_definition=None, formula=None, raw_formula=None,
                       required_fields=[], parameters={}, record_kind='factor_portfolio')]
    records = exported_records(generate(*inputs(tmp_path, rows)))
    osap, aqr = records
    assert osap['definition']['truncated']
    assert any('后续条件' in value for value in osap['missing_information'])
    assert osap['definition']['definition_sha256'] == digest(long.encode())
    assert aqr['definition']['status'] == 'MISSING'
    assert aqr['definition']['text'] is None and aqr['definition']['formula'] is None
    assert any('factor_portfolio' in value for value in aqr['missing_information'])


def test_refuses_conflicting_variant_and_membership_outside_source(tmp_path):
    first = source_row()
    second = source_row(number=2, factor_variant_id=first['factor_variant_id'], formula='$volume')
    with pytest.raises(ValueError, match='Conflicting formula'):
        generate(*inputs(tmp_path, [first, second]))
    other = tmp_path / 'other'
    other.mkdir()
    with pytest.raises(ValueError, match='subsets'):
        generate(*inputs(other, [first], admitted={'qkg:factor:' + str(UUID(int=999))}))


@pytest.mark.parametrize('target', ['record', 'license', 'index', 'schema'])
def test_rejects_tampered_published_artifacts(tmp_path, target):
    files = generate(*inputs(tmp_path, [source_row()]))
    output = materialize(tmp_path, files)
    if target == 'record':
        path = next((output / 'records').glob('*.json'))
        path.write_bytes(path.read_bytes() + b' ')
    elif target == 'license':
        path = output / 'licenses/JKP-DATA-LICENSE.txt'
        path.write_bytes(path.read_bytes() + b' ')
    elif target == 'schema':
        path = output / 'schema.json'
        path.write_bytes(path.read_bytes() + b' ')
    else:
        path = output / 'index.json'
        value = json.loads(path.read_text())
        value['counts']['variants'] += 1
        path.write_bytes(encode(value))
    with pytest.raises(ValueError):
        validate(output)


def test_no_machine_paths_or_unindexed_original_documents_in_current_catalogue():
    root = ROOT / 'metadata/factor-sources'
    index = json.loads((root / 'index.json').read_text())
    assert len(index['license_notices']) == 2
    for ref in index['records']:
        assert ':' not in ref['path']
        body = (root / ref['path']).read_text()
        assert '/Users/' not in body and '/home/' not in body
        row = json.loads(body)
        assert row['rights']['source_fulltext_included'] is False
        assert row['rights']['market_observations_included'] is False
        assert row['quality']['economic_validity'] == 'NOT_EVALUATED'
        for source in row['sources']:
            assert source['sha256'] and source['locator'] and source['url']
    assert all(x['counted_as_factor'] is False for x in index['license_notices'])
