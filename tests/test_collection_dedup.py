"""Source identity and conservative candidate retrieval, without source execution."""
from copy import deepcopy

import pytest

from quantgraph.graph.collection_dedup import (
    STATUS,
    baseline_candidates,
    code_fingerprints,
    collection_source_keys,
    fingerprint_clusters,
    normalize_source_url,
    source_key,
)


@pytest.mark.parametrize('url', [
    'https://www.tradingview.com/script/aB12Cd34-Original-title/',
    'https://cn.tradingview.com/script/aB12Cd34-另一个标题/',
    'https://ru.tradingview.com/script/aB12Cd34-New-Slug/?utm_source=x',
    'https://www.tradingview.com/zh-cn/script/aB12Cd34/',
])
def test_tradingview_locales_and_slugs_keep_case_sensitive_script_id(url):
    assert normalize_source_url(url) == 'tradingview:aB12Cd34'
    assert normalize_source_url(url) != normalize_source_url(url.replace('aB12Cd34', 'ab12cd34'))


def test_tradingview_facade_native_id_is_a_source_location_not_a_version_or_title():
    url = 'https://pine-facade.tradingview.com/pine-facade/get/PUB%3B' + 'a' * 32 + '/1'
    expected = 'tradingview-pub:PUB;' + 'a' * 32
    assert normalize_source_url(url) == expected
    assert normalize_source_url(url + '.0?utm_source=ignored') == expected
    assert normalize_source_url(url.replace('/1', '/2')) == expected
    for invalid in [url.replace('/1', '/-1.0'), url.replace('PUB%3B', 'USER%3B'),
                    url.replace('a' * 32, 'a' * 31)]:
        assert normalize_source_url(invalid) is None


def test_legacy_tradingview_native_tokens_are_opaque_and_case_sensitive():
    token = 'AuVCpaVo2YGf4cxsVqp0LxAeJTWNB3yx'
    url = 'https://pine-facade.tradingview.com/pine-facade/get/PUB%3B' + token + '/1'
    assert normalize_source_url(url) == 'tradingview-pub:PUB;' + token
    assert normalize_source_url(url) != normalize_source_url(url.replace(token, token.lower()))
    row, review, sources = code_review()
    sources['code']['url'] = row['sources'][0]['url'] = url
    assert 'tradingview-native:PUB;' + token + '@1' in collection_source_keys(row, review, sources)


def code_review(*, native='9KcWvaBf', namespace='TradingView', publication=True):
    url = ('https://pine-facade.tradingview.com/pine-facade/get/PUB%3B' + 'a' * 32 + '/1'
           if publication else 'https://github.com/example/library/blob/' + 'b' * 40 + '/algorithms.py')
    sources = {'code': dict(role='source_code', url=url, sha256='c' * 64, extraction='json.source' if publication else 'utf8')}
    record = dict(entity_type='factor', identity_namespace=namespace, record_id=native, native_source_id=native,
                  sources=[dict(id='code', url=url)], factor_fields={field: dict(evidence=['code'])
                  for field in ('formula', 'inputs', 'calculation')},
                  rights=dict(terms_url='https://www.tradingview.com/script/9KcWvaBf-Original-title/'))
    review = dict(definition_signature='editorial signature', field_spans={field: [dict(source_id='code',
                  first_line=1, last_line=5, sha256='d' * 64)] for field in record['factor_fields']})
    return record, review, sources


@pytest.mark.parametrize('match', ['native_version', 'publication_version', 'exact_script_bytes'])
def test_whole_script_repeats_survive_namespace_names_and_editorial_span_changes(match):
    old, before, old_sources = code_review()
    new, after, new_sources = deepcopy((old, before, old_sources))
    new.update(identity_namespace='another namespace', name='Renamed summary')
    after['definition_signature'] = 'unrelated signature'
    for spans in after['field_spans'].values():
        spans[0].update(first_line=2, last_line=6, sha256='e' * 64)
    if match == 'native_version':
        new.update(record_id='aB12Cd34', native_source_id='aB12Cd34')
        new['rights']['terms_url'] = 'https://cn.tradingview.com/script/aB12Cd34-Other-name/'
        # Different response-container bytes cannot disguise the same PUB@1.
        new_sources['code'].update(url=new_sources['code']['url'] + '.0', sha256='f' * 64)
    elif match == 'publication_version':
        new_sources['code'].update(url=new_sources['code']['url'].replace('a' * 32, 'f' * 32), sha256='f' * 64)
        new['rights']['terms_url'] = 'https://cn.tradingview.com/script/9KcWvaBf-Renamed/'
    else:
        new.update(record_id='aB12Cd34', native_source_id='aB12Cd34')
        new['rights']['terms_url'] = 'https://cn.tradingview.com/script/aB12Cd34/'
        new_sources['code']['url'] = new_sources['code']['url'].replace('a' * 32, 'f' * 32)
    new['sources'][0]['url'] = new_sources['code']['url']
    assert collection_source_keys(old, before, old_sources) & collection_source_keys(new, after, new_sources)


def test_a_new_script_version_is_not_automatically_the_same_definition():
    old, before, old_sources = code_review()
    new, after, new_sources = deepcopy((old, before, old_sources))
    new_sources['code'].update(url=new_sources['code']['url'].removesuffix('/1') + '/2', sha256='e' * 64)
    new['sources'][0]['url'] = new_sources['code']['url']
    assert not collection_source_keys(old, before, old_sources) & collection_source_keys(new, after, new_sources)


def test_same_library_file_different_core_spans_are_not_a_duplicate():
    first, review, sources = code_review(native='algorithm_one', publication=False)
    second, other_review = deepcopy((first, review))
    second.update(record_id='algorithm_two', native_source_id='algorithm_two')
    # The shared input line remains; the algorithm definitions occupy different
    # parts of the very same file. Its byte hash alone cannot merge them.
    for field in ('formula', 'calculation'):
        other_review['field_spans'][field][0].update(first_line=20, last_line=30, sha256='e' * 64)
    assert not collection_source_keys(first, review, sources) & collection_source_keys(second, other_review, sources)
    second['identity_namespace'] = 'mirror'
    assert collection_source_keys(first, review, sources) == collection_source_keys(second, review, sources)


def test_a_shared_helper_or_published_script_reference_is_not_a_whole_definition():
    first, review, sources = code_review(native='algorithm_one', publication=False)
    sources['helper'] = dict(role='source_code', url='https://example.org/helper.py', sha256='e' * 64, extraction='utf8')
    first['sources'].append(dict(id='helper', url=sources['helper']['url']))
    for field in first['factor_fields']:
        first['factor_fields'][field]['evidence'].append('helper')
        review['field_spans'][field].append(dict(source_id='helper', first_line=1, last_line=10, sha256='f' * 64))
    second, second_sources = deepcopy((first, sources))
    second_sources['code']['sha256'] = '0' * 64
    assert not collection_source_keys(first, review, sources) & collection_source_keys(second, review, second_sources)
    # A TV library function is not the whole publication: its native algorithm
    # ID must not inherit a page-only record's whole-script identity shortcut.
    function, function_review, function_sources = code_review(native='algorithm_one')
    assert all(key.startswith('scoped-code:') for key in collection_source_keys(function, function_review, function_sources))


@pytest.mark.parametrize('role', ['license', 'attribution', 'source_index', 'published_definition'])
def test_noncode_snapshots_do_not_create_code_duplicate_keys(role):
    row, review, sources = code_review()
    sources['code']['role'] = role
    assert collection_source_keys(row, review, sources) == frozenset()


@pytest.mark.parametrize('url', [
    'https://www.fmz.com/strategy/123456',
    'https://www.fmz.com/lang/en/strategy/123456/',
    'https://fmz.com/lang/zh-cn/strategy/123456?utm_source=feed',
])
def test_fmz_locales_resolve_to_native_strategy_id(url):
    assert normalize_source_url(url) == 'fmz:123456'


@pytest.mark.parametrize('url', [
    'https://github.com/Example/Signals/blob/main/factors/Value.py#L10-L20',
    'https://raw.githubusercontent.com/example/signals/main/factors/Value.py',
    'https://github.com/example/signals/raw/refs/heads/main/factors/Value.py',
    f'https://github.com/example/signals/blob/{"a" * 40}/factors/Value.py',
])
def test_git_ref_and_transport_do_not_create_new_source_identity(url):
    assert normalize_source_url(url) == 'github:example/signals/factors/Value.py'


def test_git_slash_branches_have_explicit_ref_boundary_and_paths_keep_case():
    url = 'https://github.com/example/signals/blob/feature/review/factors/Value.py'
    assert normalize_source_url(url, ref='feature/review') == 'github:example/signals/factors/Value.py'
    assert normalize_source_url(url, ref='another') is None
    assert normalize_source_url(url, ref='feature/review') != normalize_source_url(url.replace('Value.py', 'value.py'), ref='feature/review')


def test_github_file_is_not_a_definition_and_callers_can_preserve_symbols():
    url = 'https://github.com/example/signals/blob/main/factors.py#L20'
    assert source_key(url, symbol='momentum') != source_key(url, symbol='value')
    assert source_key(url, locator='function momentum') != source_key(url, locator='function value')
    assert source_key(url, symbol='momentum') == ('github:example/signals/factors.py', 'momentum', None)
    with pytest.raises(ValueError, match='nonempty strings'):
        source_key(url, symbol='')


@pytest.mark.parametrize('value', ['10.1234/AbC.56', 'doi:10.1234/AbC.56',
                                  'https://doi.org/10.1234/AbC.56', 'http://dx.doi.org/10.1234/abc.56'])
def test_complete_doi_values_match_without_network(value):
    assert normalize_source_url(value) == 'doi:10.1234/abc.56'


@pytest.mark.parametrize('value', ['doi:10.1234', 'doi:10.1234/', '10.12/example',
                                  'https://doi.org/10.1234/', 'https://doi.org/not-a-doi',
                                  'doi:10.1234/part with whitespace'])
def test_incomplete_or_invalid_doi_is_not_an_identity(value):
    assert normalize_source_url(value) is None


def test_generic_urls_remove_tracking_without_erasing_business_query_ids():
    first = 'https://example.org/view?id=42&edition=1&utm_source=news#section'
    assert normalize_source_url(first) == 'url:https://example.org/view?id=42&edition=1'
    assert normalize_source_url(first) != normalize_source_url(first.replace('id=42', 'id=43'))
    assert normalize_source_url(first) != normalize_source_url(first.replace('edition=1', 'edition=2'))
    assert normalize_source_url('https://example.org/?id=42&fbclid=x') == 'url:https://example.org/?id=42'
    assert normalize_source_url('https://example.org/?strategyId=42') == 'url:https://example.org/?strategyId=42'
    # ref/source can be application identifiers; they are not guessed as tracking.
    assert 'ref=alpha&source=paper' in normalize_source_url('https://example.org/view?ref=alpha&source=paper')


def test_business_query_multiplicity_and_reserved_path_bytes_are_preserved():
    url = 'https://example.org/view?id=1&id=2&empty='
    assert normalize_source_url(url).endswith('?id=1&id=2&empty=')
    assert normalize_source_url(url) != normalize_source_url(url.replace('id=1&id=2', 'id=2&id=1'))
    assert normalize_source_url('https://example.org/a%2Fb') != normalize_source_url('https://example.org/a/b')


@pytest.mark.parametrize('url', [
    'https://github.com/owner/repo', 'https://github.com/owner/repo/tree/main/factors',
    'https://github.com/owner/repo/blob/main', 'https://tradingview.com/scripts/',
    'https://tradingview.com/script/not-an-id-example/', 'https://fmz.com/strategy',
    'https://example.org/', 'https://example.org/strategy-library?utm_source=x',
    'https://example.org/strategies?page=2', 'file:///tmp/example.py',
    'https://user:password@example.org/example.py', 'https://example.org:bad/example.py',
    'https://exa mple.org/example.py', 'https://example.org/a\nb',
    'https://example.org/a/../b', 'https://example.org/a/%2e%2e/b',
])
def test_known_directories_and_unsafe_urls_are_not_definition_locators(url):
    assert normalize_source_url(url) is None


def test_pine_comments_are_not_confused_with_slashes_in_string_literals():
    a = '''//@version=5
strategy("https://example.org//strategy") // source comment
url = 'x//y'
if close > open
    strategy.entry("L", strategy.long)
'''
    b = a.replace(' // source comment', ' // another comment').replace("url =", "url    =")
    fa, fb = code_fingerprints(a, 'pine'), code_fingerprints(b, 'pine')
    assert fa['syntax_sha256'] == fb['syntax_sha256']
    assert fa['syntax_sha256'] != code_fingerprints(a.replace('x//y', 'x//z'), 'pine')['syntax_sha256']
    assert fa['status'] == STATUS and fa['parse_status'] == 'STRUCTURAL_ONLY'


def test_python_ast_normalization_preserves_strings_direction_and_control_flow(tmp_path):
    marker = tmp_path / 'must-not-exist'
    code = f'''"""documentation"""
from pathlib import Path
Path({str(marker)!r}).write_text("never execute")
direction = "long"
if close > open:
    buy()
'''
    fp = code_fingerprints(code, 'python')
    assert not marker.exists()
    assert fp['syntax_sha256'] == code_fingerprints(code.replace('documentation', 'other doc'), 'python')['syntax_sha256']
    for change in [code.replace('"long"', '"short"'), code.replace('close > open', 'close < open'), code.replace('    buy()', 'buy()')]:
        assert fp['syntax_sha256'] != code_fingerprints(change, 'python')['syntax_sha256']


@pytest.mark.parametrize('language,code,changed', [
    ('pine', 'length = input.int(14)\nx = ta.sma(close, length)', 'length = input.int(21)\nx = ta.sma(close, length)'),
    ('pine', 'length = input(14, title="Length")\nx = ta.sma(close, length)', 'length = input(21, title="Length")\nx = ta.sma(close, length)'),
    ('pine', 'length = input.int(defval=14)\nx = close', 'length = input.int(defval=21)\nx = close'),
    ('python', 'length = 14\nx = sma(close, length)', 'length = 21\nx = sma(close, length)'),
])
def test_only_declared_parameter_changes_generate_family_candidates(language, code, changed):
    a = code_fingerprints(code, language, parameter_names=['length'])
    b = code_fingerprints(changed, language, parameter_names=['length'])
    assert a['syntax_sha256'] != b['syntax_sha256']
    assert a['parameter_candidate_sha256'] == b['parameter_candidate_sha256']
    assert a['parameter_slots'] == ['length']
    assert a['status'] == STATUS


@pytest.mark.parametrize('language,code', [
    ('python', 'length = 14\nx = sma(close, length)'),
    ('pine', 'length = 14\nx = ta.sma(close, length)'),
])
def test_plain_numeric_literals_are_not_automatically_parameters(language, code):
    assert code_fingerprints(code, language)['parameter_candidate_sha256'] is None


@pytest.mark.parametrize('language,code', [
    ('python', 'length = 14\nx = close ** length'),
    ('python', 'length = 14\nx = math.pow(close, length)'),
    ('pine', 'length = input.int(14)\nx = math.pow(close, length)'),
])
def test_exponent_parameters_are_retained_even_if_named_as_parameters(language, code):
    fp = code_fingerprints(code, language, parameter_names=['length'])
    assert fp['parameter_candidate_sha256'] is None
    assert fp['syntax_sha256'] != code_fingerprints(code.replace('14', '21'), language, parameter_names=['length'])['syntax_sha256']


@pytest.mark.parametrize('language,code', [
    ('python', 'length = 14\nexponent = length\nx = close ** exponent'),
    ('pine', 'length = input.int(14)\nexponent = length\nx = math.pow(close, exponent)'),
])
def test_indirect_exponent_parameters_are_not_masked(language, code):
    assert code_fingerprints(code, language, parameter_names=['length'])['parameter_candidate_sha256'] is None


@pytest.mark.parametrize('language,template', [('python', 'length = {}\nx = sma(close, length)'),
                                              ('pine', 'length = input.int({})\nx = ta.sma(close, length)')])
def test_zero_one_and_sign_are_never_erased(language, template):
    for value in ['0', '1', '-1']:
        assert code_fingerprints(template.format(value), language, parameter_names=['length'])['parameter_candidate_sha256'] is None
    a = code_fingerprints(template.format('14'), language, parameter_names=['length'])
    b = code_fingerprints(template.format('-14'), language, parameter_names=['length'])
    assert a['parameter_candidate_sha256'] != b['parameter_candidate_sha256']


def test_parameter_masking_does_not_drop_operator_direction_other_literals_or_pine_indent():
    code = 'length = input.int(14)\nif close > 1\n    x = math.pow(close, 2) * length\n    strategy.entry("L", strategy.long)'
    fp = code_fingerprints(code, 'pine')
    for changed in [code.replace('> 1', '< 1'), code.replace(', 2)', ', 3)'),
                    code.replace('strategy.long', 'strategy.short'), code.replace('    x =', 'x =')]:
        assert fp['parameter_candidate_sha256'] != code_fingerprints(changed, 'pine')['parameter_candidate_sha256']


@pytest.mark.parametrize('language,code', [('python', 'if broken'), ('pine', 's = "unterminated'),
                                        ('rust', 'fn main(){}'), ('python', '# only a comment'), ('pine', '//@version=5')])
def test_unsupported_input_has_no_fingerprints(language, code):
    fp = code_fingerprints(code, language)
    assert fp['status'] == STATUS
    assert fp['syntax_sha256'] is None and fp['parameter_candidate_sha256'] is None


def test_baseline_matches_multiple_urls_once_and_titles_only_as_candidates():
    baseline = [dict(entity_id='old:1', name='Trend Alpha', urls=[
        'https://cn.tradingview.com/script/aB12Cd34-old/', 'https://www.tradingview.com/script/aB12Cd34-new/']),
        dict(entity_id='old:2', name='trend alpha', urls=['https://example.org/other?id=2'])]
    candidates = [dict(record_id='new', name='  TREND   ALPHA ', urls=['https://ru.tradingview.com/script/aB12Cd34-anything/'])]
    before = deepcopy((baseline, candidates))
    result = baseline_candidates(candidates, baseline)
    assert result['status'] == STATUS
    assert len(result['source_matches']) == 1
    assert result['source_matches'][0]['baseline_id'] == 'old:1'
    assert result['title_clusters'][0]['baseline_ids'] == ['old:1', 'old:2']
    assert not result['novelty_assessed'] and not result['equivalence_assessed']
    assert (baseline, candidates) == before


def test_same_git_file_different_symbols_are_not_exact_definition_hits():
    url = 'https://github.com/a/b/blob/main/factors.py'
    baseline = [dict(entity_id='old:symbol', name='a', sources=[dict(url=url, symbol='one')]),
                dict(entity_id='old:unknown', name='b', urls=[url])]
    candidates = [dict(record_id='new', name='c', sources=[dict(url=url, symbol='two')])]
    result = baseline_candidates(candidates, baseline)
    assert [(r['baseline_id'], r['scope']) for r in result['source_matches']] == [
        ('old:unknown', 'SAME_SOURCE_LOCATOR_SCOPE_UNKNOWN')]
    candidates[0]['sources'][0]['symbol'] = 'one'
    result = baseline_candidates(candidates, baseline)
    assert any(r['scope'] == 'EXACT_SOURCE_AND_LOCATOR' for r in result['source_matches'])


def test_empty_matches_do_not_establish_novelty_and_numbered_titles_remain_distinct():
    result = baseline_candidates([dict(record_id='new', name='Alpha 2', urls=['https://example.org/?id=2'])],
                                 [dict(entity_id='old', name='Alpha 1', urls=['https://example.org/?id=1'])])
    assert result['source_matches'] == [] and result['title_clusters'] == []
    assert not result['novelty_assessed']


def test_fingerprint_clusters_report_exact_syntax_and_parameter_candidates_separately():
    records = [dict(record_id=name, code=code, language='python', parameter_names=['length']) for name, code in [
        ('a', 'length = 14\nx = sma(close, length)'),
        ('b', 'length = 21\nx = sma(close, length)'),
        ('c', '# comment\nlength=14\nx=sma(close,length)'),
        ('d', 'length = 14\nx = -sma(close, length)'),
    ]]
    result = fingerprint_clusters(records)
    assert all(c['status'] == STATUS for c in result['clusters'])
    assert {tuple(c['record_ids']) for c in result['clusters']} == {('a', 'c'), ('a', 'b', 'c')}
    assert not result['equivalence_assessed']
    with pytest.raises(ValueError, match='Duplicate candidate'):
        fingerprint_clusters(records + [records[0]])
    with pytest.raises(ValueError, match='Duplicate candidate'):
        baseline_candidates([dict(record_id='a'), dict(record_id='a')], [])
