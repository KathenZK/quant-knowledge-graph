"""Synthetic fixtures only: no uploaded corpus rule text is distributed by tests."""
import csv
import io
import json
import os
from pathlib import Path
import tarfile

import pytest
from pydantic import ValidationError

from quantgraph import FactorDB
from quantgraph.collectors.grokbot.collector import read_bundle, preserve_bundle, sha256
from quantgraph.graph.grokbot import import_grokbot, verify_grokbot, normalize_bundle, source_groups, legacy_screens
from quantgraph.models.entities import StrategyProvenance, StrategyFactor
from quantgraph.normalize.strategy.parser import parse_rule
from quantgraph.normalize.strategy.metadata import canonical_url, market_taxonomy

RSI_URL = 'https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/relative-strength-index-rsi'
ABS_URL = 'https://www.naaim.org/wp-content/uploads/2013/10/00D_Absolute-Momentum_gary_antonacci.pdf'


def fixture_row(id='SYNTH-1', rule='日频：若 RSI(7)>53 → 满仓 QQQ，否则 SHV。', url=RSI_URL, market='美股/ETF'):
    return {'id': id, '名称': 'Synthetic test ' + id, '市场': market, '规则': rule, '作者或机构': 'Fixture only',
            '标题': 'Synthetic rules, not an upstream strategy claim', 'source_url': url,
            '提出日期': '1978-01-01', '页码或文件': 'fixture', '可回测': '高', '别名来源': ''}


def pack(tmp_path, rows, screens=None, unsafe=None):
    files = {}
    def csv_bytes(records):
        f = io.StringIO(newline='')
        writer = csv.DictWriter(f, fieldnames=list(records[0]))
        writer.writeheader(); writer.writerows(records)
        return f.getvalue().encode()
    files['quant-master-draft.csv'] = csv_bytes(rows)
    if screens:
        files['validation/strategy-validation-batch1.csv'] = csv_bytes(screens)
    if unsafe:
        files[unsafe] = b'test'
    path = tmp_path / 'fixture.tar.gz'
    with tarfile.open(path, 'w:gz') as archive:
        for name, data in files.items():
            entry = tarfile.TarInfo(name); entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
    return path


@pytest.fixture
def bundle(tmp_path):
    rows = [fixture_row(), fixture_row('SYNTH-2', '日频：若 RSI(7)>59 → 满仓 QQQ，否则 SHV。'),
            fixture_row('SYNTH-3', '月末：若 QQQ过去9月总分收益>BIL同期 → 满仓 QQQ，否则 BIL。', ABS_URL),
            fixture_row('SYNTH-4', '月末：若 GLD过去9月总分收益>BIL同期 → 满仓 GLD，否则 BIL。', ABS_URL),
            fixture_row('SYNTH-5', 'Undefined proprietary signal; do not guess an AST.', 'https://example.org/unknown')]
    screens = [{'id': 'SYNTH-1', 'proxy_and_rule': 'Synthetic proxy rule', 'data_note': 'Safe leg held at zero return',
                'total_return': '0.42', 'bucket': '仍有效'},
               {'id': 'SYNTH-5', 'proxy_and_rule': 'Unknown implementation', 'data_note': 'unverified', 'total_return': '-0.1', 'bucket': '失败'}]
    return pack(tmp_path, rows, screens)


def test_count_conservation_raw_bytes_dates_and_determinism(tmp_path, bundle):
    before = bundle.read_bytes()
    root = tmp_path / 'repo'
    result = import_grokbot(root, bundle)
    assert bundle.read_bytes() == before
    assert result['report']['raw_records'] == result['report']['normalized_records'] == 5
    assert result['report']['curated_variants'] == 4
    assert result['verification']['raw_unchanged']
    assert import_grokbot(root, bundle)['release_id'] == result['release_id']
    data = read_bundle(bundle)
    rows, _, _ = normalize_bundle(data)
    assert [r['raw_record'] for r in rows] == data['rows']
    for r in rows:
        v = r['variant']
        assert v['original_rule_text'] == r['raw_record']['规则']
        assert v['concept_origin_date'] is v['source_publication_date'] is v['variant_created_at'] is None
        assert v['raw_proposed_date'] == '1978-01-01'


def test_rsi_bot_derivation_and_parameter_axes(bundle):
    rows, _, _ = normalize_bundle(read_bundle(bundle))
    one, two = [r['variant'] for r in rows[:2]]
    assert one['provenance_type'] == two['provenance_type'] == 'BOT_DERIVED'
    assert one['source_support'] == 'INDICATOR_DEFINITION'
    assert one['strategy_template_id'] == two['strategy_template_id']
    assert one['strategy_variant_id'] != two['strategy_variant_id']
    assert one['variation_axes'] == ['PARAMETER_VARIANT']
    assert one['rule_ast']['condition']['right']['value'] == 53
    assert one['rule_ast']['condition']['left']['smoothing'] is None
    assert not one['executable']


def test_absolute_momentum_family_and_asset_variants(bundle):
    rows, concepts, _ = normalize_bundle(read_bundle(bundle))
    one, two = [r['variant'] for r in rows[2:4]]
    assert one['strategy_concept_id'] == two['strategy_concept_id']
    assert one['strategy_template_id'] == two['strategy_template_id']
    assert one['provenance_type'] == 'BOT_DERIVED'
    assert one['variation_axes'] == ['ASSET_VARIANT']
    assert one['rule_ast']['lookback'] == {'value': 9, 'unit': 'months'}
    assert any(c['canonical_name'] == 'absolute_momentum' for c in concepts)


def test_citation_family_does_not_fabricate_ast(tmp_path):
    path = pack(tmp_path, [fixture_row(rule='Unspecified implementation of absolute momentum', url=ABS_URL)])
    rows, concepts, templates = normalize_bundle(read_bundle(path))
    assert concepts[0]['canonical_name'] == 'absolute_momentum'
    assert rows[0]['variant']['rule_ast'] is None
    assert rows[0]['variant']['parse_status'] == 'REVIEW' and not templates


def test_shared_sources_are_not_deduplicated(bundle):
    rows, _, _ = normalize_bundle(read_bundle(bundle))
    groups = source_groups(rows)
    assert len(groups) == 3
    assert sum(g['record_count'] for g in groups) == 5
    assert sum(g['record_count'] > 1 for g in groups) == 2
    assert len({r['variant']['strategy_variant_id'] for r in rows}) == 5


@pytest.mark.parametrize('text', [
    'Buy when it looks strong.',
    '日频：若 Magic(7)>53 → 满仓 QQQ，否则 SHV。',
    '日频：若 RSI(7)>53 且 volume>100 → 满仓 QQQ，否则 SHV。',
    '日频：若 RSI(7)>53 → 满仓 QQQ，否则 SHV。再加3%止损。',
    '日频：若 RSI(0)>53 → 满仓 QQQ，否则 SHV。',
    '本条只写测试。日频：若 RSI(7)>53 → 满仓 QQQ，否则 SHV。不是旧规则；但是加止损。',
    '月末：若 QQQ过去9月总分收益>BIL同期 → 满仓 GLD，否则 BIL。',
    '本条只写测试。附带杠杆条件。日频：若 RSI(7)>53 → 满仓 QQQ，否则 SHV。',
])
def test_unknown_or_partial_rules_do_not_invent_ast(text):
    result = parse_rule(text)
    assert result['parse_status'] == 'REVIEW'
    assert result['normalized_rule'] is result['rule_ast'] is None


@pytest.mark.parametrize('text,kind', [
    ('日频：若 SMA(9)>SMA(31) → 满仓 QQQ，否则 SHV。', 'threshold_switch'),
    ('日频：若 收盘>EMA(17) → 满仓 QQQ，否则 SHV。', 'threshold_switch'),
    ('日频：若 CCI(17)<-72 → 满仓 QQQ，否则 SHV。', 'threshold_switch'),
    ('月末：比较 QQQ 与 GLD 过去9个月总分收益，满仓较高者。', 'relative_momentum_rotation'),
])
def test_supported_grammar(text, kind):
    result = parse_rule(text)
    assert result['parse_status'] == 'PARSED' and result['rule_ast']['type'] == kind
    assert not result['executable']
    assert result['rule_ast']['execution_timing'] is None


def test_parser_does_not_infer_position_size():
    ast = parse_rule('日频：RSI(7)>53→QQQ否则SHV。')['rule_ast']
    assert ast['then']['allocation'] is ast['else']['allocation'] is None


def test_market_taxonomy_keeps_multi_market_scope_and_unknowns():
    assert market_taxonomy('加密/美股通用')['asset_class'] == ['crypto', 'equity']
    assert market_taxonomy('未定义市场')['asset_class'] == ['unknown']
    assert market_taxonomy('美股/ETF')['instruments'] == ['ETF']


def test_url_aggregation_preserves_distinct_fragments():
    assert canonical_url('HTTPS://EXAMPLE.ORG/a?q=1#x') == 'https://example.org/a?q=1#x'
    assert canonical_url('https://example.org/a#x') != canonical_url('https://example.org/a#y')
    assert canonical_url('file:///etc/passwd') is None
    assert canonical_url('https://name:secret@example.org') is None


def test_legacy_screens_are_not_reproduction_or_attribution(bundle):
    data = read_bundle(bundle)
    rows, _, _ = normalize_bundle(data)
    screens, unmatched = legacy_screens(data, rows)
    assert len(screens) == 2 and not unmatched
    assert {s['result_kind'] for s in screens} == {'LEGACY_GROKBOT_SCREEN'}
    assert all(s['contract_uri'] is None for s in screens)
    assert screens[0]['metrics']['reported']['data_note'] == 'Safe leg held at zero return'
    assert screens[0]['metrics']['reported']['total_return'] == '0.42'


def test_private_graph_factor_links_sdk_and_license_isolation(tmp_path, bundle):
    root = tmp_path / 'repo'; result = import_grokbot(root, bundle)
    release = root / 'datasets/curated/grokbot/releases' / result['release_id']
    db = FactorDB(database=release / 'quantgraph.sqlite')
    strategies = db.find_strategies()
    assert len(strategies) == 4
    for strategy in strategies:
        links = db.get_strategy_factors(strategy['strategy_id'])
        assert links and all(x['attribution_status'] == 'RULE_LINK_ONLY' and x['backtest_result_id'] is None for x in links)
        assert db.get_variant(links[0]['variant_id'])['commercial_use'] == 'REVIEW_REQUIRED'
    variants = [json.loads(s) for s in (release / 'strategy_variants.jsonl').read_text().splitlines()]
    v = variants[0]
    assert db.get_entity('StrategyVariant', v['strategy_variant_id']) == v
    assert {e['relation'] for e in db.relationships(v['strategy_variant_id'])} >= {'VARIANT_OF', 'DERIVED_FROM', 'SOURCED_FROM'}
    for file in (release / 'commercial').glob('*.jsonl'):
        assert file.read_text() == ''
    assert not (root / 'datasets/public').exists()
    report = (root / 'reports/grok_strategy_import_v1.json').read_text()
    assert 'Synthetic test' not in report and RSI_URL not in report and '53' not in json.dumps(json.loads(report)['limitations'])


def test_raw_and_normalized_tamper_are_rejected(tmp_path, bundle):
    root = tmp_path / 'repo'; result = import_grokbot(root, bundle)
    report = result['report']
    normalized = root / 'datasets/normalized/grokbot' / report['input_sha256'] / report['importer_code_sha256'] / 'records.jsonl'
    normalized.write_text(normalized.read_text() + '\n')
    with pytest.raises(ValueError, match='Normalized checksum'):
        verify_grokbot(root)
    raw = root / 'datasets/raw/sources/grokbot' / report['input_sha256'] / 'input.tar.gz'
    raw.write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='Immutable raw'):
        preserve_bundle(root, read_bundle(bundle))


def test_duplicate_ids_and_unsafe_archives_fail_closed(tmp_path):
    path = pack(tmp_path, [fixture_row(), fixture_row()])
    with pytest.raises(ValueError, match='duplicate native ID'):
        read_bundle(path)
    path = pack(tmp_path, [fixture_row()], unsafe='../escape.txt')
    with pytest.raises(ValueError, match='Unsafe archive'):
        read_bundle(path)


def test_unknown_provenance_and_enum_contract(bundle):
    rows, _, _ = normalize_bundle(read_bundle(bundle))
    assert rows[-1]['variant']['provenance_type'] == 'UNKNOWN'
    assert {x.value for x in StrategyProvenance} == {'SOURCE_NATIVE', 'SOURCE_IMPLEMENTATION', 'SOURCE_DERIVED', 'BOT_DERIVED', 'PARAMETER_VARIANT', 'MARKET_VARIANT', 'ASSET_VARIANT', 'UNKNOWN'}
    with pytest.raises(ValidationError):
        StrategyFactor(strategy_id='s',factor_id='f',variant_id='v',role='signal',confidence=1,evidence='test',source='fixture',attribution_status='EMPIRICALLY_TESTED')


@pytest.mark.skipif(not os.getenv('GROKBOT_TEST_ARCHIVE'), reason='Private corpus is not distributed in the public repository')
def test_real_corpus_conservation_and_known_regressions(tmp_path):
    archive = Path(os.environ['GROKBOT_TEST_ARCHIVE'])
    before = sha256(archive.read_bytes())
    result = import_grokbot(tmp_path / 'full', archive)
    report = result['report']
    assert report['raw_records'] == report['normalized_records'] == 5813
    assert report['source_url_statistics']['raw_unique'] == 4035
    assert report['legacy_screens'] == 30 and report['legacy_screens_unmatched'] == 0
    rows, _, _ = normalize_bundle(read_bundle(archive))
    by_id = {r['variant']['source_native_id']: r['variant'] for r in rows}
    rsi, momentum = by_id['M5850'], by_id['M5853']
    assert rsi['provenance_type'] == 'BOT_DERIVED' and rsi['rule_ast']['condition']['right']['value'] == 55
    assert momentum['rule_ast']['type'] == 'absolute_momentum'
    assert sum(r['variant']['strategy_concept_id'] == momentum['strategy_concept_id'] for r in rows) >= 30
    assert sha256(archive.read_bytes()) == before


def test_public_aggregate_report_rejects_content_leaks(tmp_path, bundle):
    from quantgraph.graph.grokbot_report import validate_public_report
    report = import_grokbot(tmp_path / 'repo', bundle)['report']
    assert validate_public_report(report)
    for mutated in [dict(report, raw_rule='private text'), dict(report, limitations=['private text']),
                    dict(report, license_distribution={'private text': 1})]:
        with pytest.raises(ValueError):
            validate_public_report(mutated)


def test_checked_in_report_is_aggregate_only():
    from quantgraph.db import project_root
    from quantgraph.graph.grokbot_report import validate_public_report
    from quantgraph.graph.grokbot import report_markdown
    root = project_root()
    report = json.loads((root / 'reports/grok_strategy_import_v1.json').read_text())
    assert validate_public_report(report)
    assert (root / 'reports/grok_strategy_import_v1.md').read_text() == report_markdown(report)


def test_legacy_backtest_cannot_be_promoted_to_factor_attribution(tmp_path, bundle):
    from quantgraph.graph.grokbot import curate_corpus
    from quantgraph.graph.store import write_graph
    from quantgraph.graph.verify import verify_graph
    data = read_bundle(bundle)
    rows, concepts, templates = normalize_bundle(data)
    screens, _ = legacy_screens(data, rows)
    tables = curate_corpus(rows, concepts, templates, screens, data)
    link = next(x for x in tables['strategy_factor'] if x['strategy_id'] == screens[0]['strategy_id'])
    link.update(attribution_status='EMPIRICALLY_TESTED', backtest_result_id=screens[0]['backtest_result_id'])
    write_graph(tmp_path / 'invalid', tables)
    with pytest.raises(ValueError, match='Legacy screen'):
        verify_graph(tmp_path / 'invalid')
