"""Offline duplicate *candidate* retrieval, never an equivalence/admission rule.

URL keys describe source locations, not definitions: one file/paper may contain
many definitions. Callers retain symbols/locators with ``source_key``. No source
code is executed. Fingerprints are deliberately conservative and incomplete.
"""
import ast
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
import re
import unicodedata
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit


STATUS = 'HEURISTIC_CANDIDATE'
VERSION = 'collection-dedup/v1'
_DOI = re.compile(r'10\.\d{4,9}/[^\s<>"?#]+', re.I)
_TRACKING = {'fbclid', 'gclid', 'dclid', 'msclkid', 'mc_cid', 'mc_eid', '_ga'}
_DIRECTORIES = {'', 'scripts', 'script', 'strategies', 'strategy', 'strategy-library',
                'indicators', 'indicator', 'library', 'collections', 'search', 'topics'}


def normalize_source_url(url, *, ref=None):
    """Return a source-location key, or None for invalid/known directory URLs.

    GitHub refs are ignored for retrieval, not version identity. Supply ``ref``
    for branches containing slashes; that boundary cannot be inferred from a URL.
    Generic keys preserve business queries and remove only known tracking keys.
    A generic page key is not proof that the page contains a definition.
    """
    if not isinstance(url, str) or not url.strip():
        return None
    value = url.strip()
    if any(ord(char) < 32 for char in value) or (ref is not None and not isinstance(ref, str)):
        return None
    bare = re.sub(r'^doi:\s*', '', value, flags=re.I)
    if _DOI.fullmatch(bare):
        return 'doi:' + bare.casefold()
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or '').casefold()
        if (parsed.scheme.casefold() not in {'http', 'https'} or not host or re.search(r'\s', host)
                or parsed.username or parsed.password):
            return None
        port = parsed.port
    except ValueError:
        return None
    if port not in {None, 80, 443}:
        return None
    path = unquote(parsed.path)
    if any(part in {'.', '..'} for part in path.split('/')) or '\\' in path:
        return None
    if host in {'doi.org', 'www.doi.org', 'dx.doi.org'}:
        doi = path.lstrip('/')
        return 'doi:' + doi.casefold() if _DOI.fullmatch(doi) else None
    if host in {'github.com', 'www.github.com', 'raw.githubusercontent.com'}:
        parts = path.strip('/').split('/')
        if len(parts) < 4:
            return None
        owner, repo = parts[:2]
        if host != 'raw.githubusercontent.com':
            if parts[2] not in {'blob', 'raw'}:
                return None
            remainder = '/'.join(parts[3:])
        else:
            remainder = '/'.join(parts[2:])
        # New GitHub raw URLs can spell out refs/heads or refs/tags.
        remainder = re.sub(r'^refs/(?:heads|tags)/', '', remainder)
        if ref is not None:
            if not ref or not remainder.startswith(ref + '/'):
                return None
            file_path = remainder[len(ref) + 1:]
        else:
            _, separator, file_path = remainder.partition('/')
            if not separator:
                return None
        if not owner or not repo or not file_path or file_path.endswith('/'):
            return None
        return f'github:{owner.casefold()}/{repo.casefold()}/{file_path}'
    if host == 'tradingview.com' or host.endswith('.tradingview.com'):
        match = re.fullmatch(r'/(?:[a-z]{2}(?:-[a-z]{2})?/)?script/([A-Za-z0-9]{8})(?:-[^/]+)?/?', path, re.I)
        return 'tradingview:' + match[1] if match else None
    if host in {'fmz.com', 'www.fmz.com'}:
        match = re.fullmatch(r'/(?:lang/[a-z-]+/)?strategy/([0-9]+)/?', path, re.I)
        return 'fmz:' + str(int(match[1])) if match else None
    query = [(key, val) for key, val in parse_qsl(parsed.query, keep_blank_values=True)
             if not key.casefold().startswith('utm_') and key.casefold() not in _TRACKING]
    # Keep duplicate business parameters and their order; some applications care.
    leaf = path.rstrip('/').rsplit('/', 1)[-1].casefold()
    business_id = any((key.casefold().endswith('id') or key.casefold() in {'code', 'symbol', 'slug'}) and val for key, val in query)
    if leaf in _DIRECTORIES and not business_id:
        return None
    # Do not decode reserved path bytes: /a%2Fb may identify a different resource.
    return 'url:' + urlunsplit((parsed.scheme.casefold(), host, parsed.path or '/', urlencode(query), ''))


def source_key(url, *, symbol=None, locator=None, ref=None):
    """Preserve caller-supplied definition locators separately from URL identity."""
    if any(value is not None and (not isinstance(value, str) or not value.strip()) for value in [symbol, locator]):
        raise ValueError('Symbols and locators must be nonempty strings or None')
    key = normalize_source_url(url, ref=ref)
    return (key, symbol, locator) if key is not None else None


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def _literal(node):
    if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
        return node if abs(node.value) not in {0, 1} else None
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        return _literal(node.operand)
    return None


def _protect_dependencies(protected, assignments):
    """Follow simple name dependencies; over-protecting is preferable to merging."""
    while True:
        expanded = protected | {name for target in protected for name in assignments.get(target, ())}
        if expanded == protected:
            return expanded
        protected = expanded


def _python(code, parameter_names):
    tree = ast.parse(code)
    # Ignore actual docstrings, never arbitrary string expressions or literals.
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and ast.get_docstring(node) is not None:
            node.body.pop(0)
    if not tree.body:
        raise ValueError('Empty source')
    exact = ast.dump(tree, include_attributes=False)
    protected, assignments = set(), defaultdict(set)
    for node in ast.walk(tree):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        for target in targets:
            if isinstance(target, ast.Name) and node.value is not None:
                assignments[target.id].update(n.id for n in ast.walk(node.value) if isinstance(n, ast.Name))
        exponent = node.right if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow) else None
        if isinstance(node, ast.Call) and ((isinstance(node.func, ast.Name) and node.func.id == 'pow')
                or (isinstance(node.func, ast.Attribute) and node.func.attr == 'pow')) and len(node.args) > 1:
            exponent = node.args[1]
        if exponent is not None:
            protected.update(n.id for n in ast.walk(exponent) if isinstance(n, ast.Name))
    protected = _protect_dependencies(protected, assignments)
    slots = set()
    # Only explicitly named module configuration assignments; no local constants.
    for node in tree.body:
        target = node.targets[0] if isinstance(node, ast.Assign) and len(node.targets) == 1 else node.target if isinstance(node, ast.AnnAssign) else None
        if isinstance(target, ast.Name) and target.id in parameter_names - protected and node.value is not None:
            literal = _literal(node.value)
            if literal is not None:
                literal.value = '$PARAMETER'
                slots.add(target.id)
    return exact, ast.dump(tree, include_attributes=False), slots


_PINE_TOKEN = re.compile(
    r'(?P<string>"(?:\\.|[^"\\\r\n])*"|\'(?:\\.|[^\'\\\r\n])*\')'
    r'|(?P<comment>//[^\r\n]*)|(?P<space>[ \t]+)'
    r'|(?P<number>(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)'
    r'|(?P<name>[A-Za-z_]\w*)|(?P<op>:=|==|!=|<=|>=|=>|\+=|-=|\*=|/=|\*\*|[^\w\s\'"`\\])')


def _pine(code, parameter_names):
    lines = []
    for line in code.splitlines():
        if re.fullmatch(r'\s*//@version=\d+\s*', line):
            lines.append([['directive', line.strip()]])
            continue
        tokens, position = [], 0
        while position < len(line):
            match = _PINE_TOKEN.match(line, position)
            if not match:
                raise ValueError('Unsupported Pine token or unterminated string')
            position = match.end()
            if match.lastgroup == 'comment':
                break
            if match.lastgroup != 'space':
                tokens.append([match.lastgroup, match.group()])
        if tokens:
            indent = len(line.expandtabs(4)) - len(line.expandtabs(4).lstrip())
            lines.append([['indent', indent], *tokens])
    exact = deepcopy(lines)
    if not any(line[0][0] == 'indent' for line in lines):
        raise ValueError('Empty source')
    protected, assignments = set(), defaultdict(set)
    for tokens in lines:
        assignment = next((i for i, t in enumerate(tokens) if t[1] == '='), None)
        if assignment is not None and assignment > 1 and tokens[assignment - 1][0] == 'name':
            assignments[tokens[assignment - 1][1]].update(text for kind, text in tokens[assignment + 1:] if kind == 'name')
        for i, token in enumerate(tokens):
            if token[1] in {'**', '^'} and i + 1 < len(tokens):
                # Pine uses math.pow; retain names following other exponent-like
                # tokens too, without pretending this tokenizer is a compiler.
                protected.update(text for kind, text in tokens[i + 1:] if kind == 'name')
            if token == ['name', 'pow'] and i + 1 < len(tokens) and tokens[i + 1][1] == '(':
                depth, argument = 1, 0
                for kind, text in tokens[i + 2:]:
                    if text == '(':
                        depth += 1
                    elif text == ')':
                        depth -= 1
                    if depth == 0:
                        break
                    if text == ',' and depth == 1:
                        argument += 1
                    elif argument == 1 and kind == 'name':
                        protected.add(text)
    protected = _protect_dependencies(protected, assignments)
    slots = set()
    for tokens in lines:
        # Only whole top-level assignments, including typed/var declarations.
        if tokens[0] != ['indent', 0]:
            continue
        assignment = next((i for i, t in enumerate(tokens) if t[1] == '='), None)
        if assignment is None or assignment < 2 or tokens[assignment - 1][0] != 'name':
            continue
        name = tokens[assignment - 1][1]
        if name in protected:
            continue
        rhs = tokens[assignment + 1:]
        auto = bool(rhs and rhs[0] == ['name', 'input'])
        if auto:
            # Restrict inference to literal input/default declarations.
            if len(rhs) > 1 and rhs[1][1] == '.':
                if len(rhs) < 4 or rhs[2][1] not in {'int', 'float'}:
                    continue
                start = 4
            else:
                start = 2
            if start > len(rhs) or rhs[start - 1][1] != '(':
                continue
            if rhs[start:start + 2] == [['name', 'defval'], ['op', '=']]:
                start += 2
        elif name in parameter_names:
            start = 0
        else:
            continue
        if start < len(rhs) and rhs[start][1] in {'+', '-'}:
            start += 1
        if start >= len(rhs) or rhs[start][0] != 'number' or abs(float(rhs[start][1])) in {0, 1}:
            continue
        rest = rhs[start + 1:]
        if (auto and (not rest or rest[0][1] not in {',', ')'})) or (not auto and rest):
            continue
        rhs[start][1] = '$PARAMETER'
        slots.add(name)
    return exact, lines, slots


def code_fingerprints(code, language, *, parameter_names=()):
    """Return syntax and parameter-family retrieval hashes, never equivalence.

    Python masks only named top-level literal assignments. Pine also recognizes
    top-level input/input.int/input.float defaults. Signs, operators, strings,
    indentation, 0/1, literal exponents and named exponent parameters survive.
    Unsupported syntax has no fingerprints; no source is imported or executed.
    """
    result = dict(status=STATUS, algorithm=VERSION, language=language,
                  syntax_sha256=None, parameter_candidate_sha256=None, parameter_slots=[])
    if language not in {'python', 'pine'}:
        return {**result, 'parse_status': 'UNSUPPORTED_LANGUAGE'}
    try:
        exact, family, slots = (_python if language == 'python' else _pine)(code, set(parameter_names))
    except (SyntaxError, ValueError, TypeError, OverflowError):
        return {**result, 'parse_status': 'UNSUPPORTED_SYNTAX'}
    return {**result, 'parse_status': 'STRUCTURAL_ONLY', 'syntax_sha256': _hash([language, exact]),
            'parameter_candidate_sha256': _hash([language, family]) if slots else None,
            'parameter_slots': sorted(slots)}


def _identity(record):
    if record.get('entity_id'):
        return record['entity_id']
    rid = record['record_id']
    namespace = record.get('identity_namespace')
    return namespace + ':' + rid if namespace else rid


def _sources(record):
    items = [dict(url=url) for url in record.get('urls', [])]
    items.extend(record.get('sources', []))
    return {key for source in items if (key := source_key(source.get('url'), symbol=source.get('symbol'),
            locator=source.get('locator'), ref=source.get('ref'))) is not None}


def _title(record):
    # No translation, fuzzy cutoff, numeric stripping or generic-name guessing.
    return ' '.join(unicodedata.normalize('NFKC', record.get('name', '')).casefold().split())


def baseline_candidates(candidates, baseline_records):
    """Compare records with baseline ``records``; return source/title candidates.

    Records have entity_id or (identity_namespace, record_id), name, urls and/or
    sources[{url,symbol?,locator?,ref?}]. Missing baseline symbol detail is reported
    as unknown scope, not treated as evidence that every definition in a file is
    the same. Empty matches never establish novelty.
    """
    locations, titles = defaultdict(list), defaultdict(set)
    for record in baseline_records:
        rid = _identity(record)
        for key in _sources(record):
            locations[key[0]].append((rid, key))
        if title := _title(record):
            titles[title].add(rid)
    matches, title_matches, seen = {}, {}, set()
    for record in candidates:
        rid = _identity(record)
        if rid in seen:
            raise ValueError('Duplicate candidate identity')
        seen.add(rid)
        for key in _sources(record):
            for old, old_key in locations[key[0]]:
                # Two explicitly different symbols/locators cannot be exact hits.
                if any(a is not None and b is not None and a != b for a, b in zip(key[1:], old_key[1:])):
                    continue
                scope = 'EXACT_SOURCE_AND_LOCATOR' if key == old_key and any(key[1:]) else 'SAME_SOURCE_LOCATOR_SCOPE_UNKNOWN'
                matches[(rid, old, key[0], scope)] = dict(candidate_id=rid, baseline_id=old, source_id=key[0], scope=scope)
        title = _title(record)
        if title and titles.get(title):
            cluster = title_matches.setdefault(title, dict(title_key=title, candidate_ids=set(), baseline_ids=titles[title]))
            cluster['candidate_ids'].add(rid)
    return dict(status=STATUS, algorithm=VERSION, source_matches=[matches[k] for k in sorted(matches)],
                title_clusters=[{**v, 'candidate_ids': sorted(v['candidate_ids']), 'baseline_ids': sorted(v['baseline_ids'])}
                                for _, v in sorted(title_matches.items())], novelty_assessed=False, equivalence_assessed=False)


def fingerprint_clusters(records):
    """Group supplied {identity, code, language, parameter_names?} candidates."""
    groups, fingerprints = defaultdict(set), {}
    for record in records:
        rid = _identity(record)
        if rid in fingerprints:
            raise ValueError('Duplicate candidate identity')
        fp = code_fingerprints(record['code'], record['language'], parameter_names=record.get('parameter_names', ()))
        fingerprints[rid] = fp
        for kind in ['syntax_sha256', 'parameter_candidate_sha256']:
            if fp[kind]:
                groups[(kind, fp[kind])].add(rid)
    clusters = []
    for (kind, fingerprint), members in sorted(groups.items()):
        if len(members) < 2:
            continue
        if kind == 'parameter_candidate_sha256' and len({fingerprints[r]['syntax_sha256'] for r in members}) < 2:
            continue
        clusters.append(dict(kind=kind, fingerprint=fingerprint, record_ids=sorted(members), status=STATUS))
    return dict(status=STATUS, algorithm=VERSION, clusters=clusters, fingerprints=fingerprints,
                novelty_assessed=False, equivalence_assessed=False)
