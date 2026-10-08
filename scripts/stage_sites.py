#!/usr/bin/env python3
"""Stage the same reviewed Graph application in an already-opened private Site.

This copies application code only; private assets and project identity remain
operator-selected deployment inputs, never public repository source.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def seed(assets):
    manifest = json.loads((assets/'catalog/manifest.json').read_text())
    refs = []
    for eid, row in manifest.items():
        path = assets/'catalog/details'/f"{row['file']}.json.gz"
        data = json.loads(gzip.decompress(path.read_bytes()))
        knowledge = data.get('knowledge', {})
        rule = knowledge.get('original_rule')
        if rule is None:
            rule = data.get('strategy', {}).get('original_rule')
        refs.append(dict(kind=data['kind'], entity_id=eid, entity_type=data['entity_type'],
            definition_revision=data['definition_revision'], name=data['name'], native_ids=data.get('source_native_ids', []),
            stable_knowledge_id=data.get('stable_knowledge_id', eid),
            definition_hash=digest(dict(formula=data.get('formula'), original_rule=rule, definition=knowledge.get('original_definition')))))
    research = json.loads((assets/'data/manifest.json').read_text())
    results = []
    for key, file in research['details'].items():
        path = assets/'data/implementations'/f'{file}.json.gz'
        data = json.loads(gzip.decompress(path.read_bytes()))
        rid, variant = key.split('|', 1)
        assert data['run_id'] == rid and data['variant_id'] == variant
        results.append(dict(origin_run_id=rid, variant_id=variant, record_id=data['id'],
            manifest_sha256=data['lineage']['manifest_sha256'], detail_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    assets_pin = {str(p.relative_to(assets)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(assets.rglob('*')) if p.is_file()}
    baseline = 'bundled-' + digest(assets_pin)
    return dict(batch_id=baseline, refs=refs, results=results, asset_manifest_sha256=digest(assets_pin))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--checkout', type=Path, required=True)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--expected-project', required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    src, dest, assets = args.source.resolve(), args.checkout.resolve(), args.assets.resolve()
    hosting_path = dest/'.openai/hosting.json'
    hosting = json.loads(hosting_path.read_text())
    if hosting.get('project_id') != args.expected_project or not (dest/'.git').exists():
        raise ValueError('Expected the already-opened existing Site checkout')
    generated = seed(assets)
    for folder in ('web/src', 'sites/worker', 'sites/db', 'sites/drizzle', 'sites/tests'):
        target = dest/folder
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(src/folder, target)
    for file in ('web/index.html', 'web/tsconfig.json', 'sites/build.mjs', 'sites/drizzle.config.ts', 'sites/README.md', 'sites/seed.example.json'):
        (dest/file).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src/file, dest/file)
    shutil.copyfile(src/'sites/package.json', dest/'package.json')
    shutil.copyfile(src/'sites/package-lock.json', dest/'package-lock.json')
    (dest/'sites/seed.generated.json').write_text(canonical(generated))
    if assets != dest/'public':
        if (dest/'public').exists():
            raise ValueError('Existing private assets must not be replaced implicitly')
        shutil.copytree(assets, dest/'public')
    hosting.pop('static', None)
    hosting.update(d1='DB', r2='BUCKET', capabilities=list(dict.fromkeys(hosting.get('capabilities', []) + ['mcp'])))
    hosting_path.write_text(json.dumps(hosting, indent=2))
    # Remove the obsolete forked product source; its native Git history remains.
    for old in ('src', 'tests', 'vite.config.ts', 'vitest.config.ts'):
        path = dest/old
        if path.is_dir():
            shutil.rmtree(path)
        elif path.is_file():
            path.unlink()
    args.receipt.write_text(json.dumps(dict(project_id=args.expected_project, baseline=generated['batch_id'],
        definitions=len(generated['refs']), execution_versions=len(generated['results']),
        application_source='QuantGraph web/src and sites/', private_assets_in_public_git=False), indent=2))
    print(args.receipt.read_text())


if __name__ == '__main__':
    main()
