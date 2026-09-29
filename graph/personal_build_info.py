"""Read-only build identity; same input manifest as the existing Vite wrapper."""
import hashlib
import json
from pathlib import Path
import re

VERSION = 'quantgraph-web-build/v1'


def source_fingerprint(web):
    web = Path(web)
    paths = set()
    for folder in ['src', 'public', 'generated', 'scripts']:
        directory = web / folder
        if directory.exists():
            for item in directory.rglob('*'):
                if item.is_symlink():
                    raise ValueError('Symlinked build input')
                if item.is_file():
                    paths.add(item.relative_to(web).as_posix())
    for item in web.iterdir():
        if item.name.endswith('.tsbuildinfo'):
            continue
        if item.is_file() and (re.search(r'\.(?:json|[cm]?js|ts|html|css)$', item.name)
                              or item.name == '.npmrc' or re.fullmatch(r'\.env(?:\.(?:local|production|production\.local))?', item.name)):
            paths.add(item.name)
    rows = ''.join(name + '\0' + hashlib.sha256((web / name).read_bytes()).hexdigest() + '\n' for name in sorted(paths))
    return hashlib.sha256(rows.encode()).hexdigest()


def build_info(root):
    web = Path(root) / 'web'
    result = dict(status='MISSING', build_id=None, built_at=None, app_version=None,
                  message='前端构建尚未登记；请使用日常启动命令更新。')
    manifest = web / 'dist/build-info.json'
    if not manifest.is_file():
        return result
    try:
        info = json.loads(manifest.read_text())
        outputs = info['outputs']
        if info['schema_version'] != VERSION or not isinstance(outputs, dict) or 'index.html' not in outputs:
            raise ValueError('Unknown build manifest')
        actual = {p.relative_to(web / 'dist').as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in (web / 'dist').rglob('*') if p.is_file() and p != manifest}
        if actual != outputs:
            raise ValueError('Build files changed')
        current = source_fingerprint(web)
        result.update({key: info.get(key) for key in ['build_id', 'built_at', 'app_version', 'source_fingerprint']})
        result.update(status='CURRENT' if current == info['source_fingerprint'] else 'STALE',
            message='页面与当前源码一致。' if current == info['source_fingerprint'] else '源码已变化，当前服务仍是旧构建；请保存笔记后重新运行日常启动命令。')
    except (OSError, ValueError, KeyError, TypeError):
        result.update(status='INVALID', message='页面构建校验失败，请重新运行日常启动命令；不要继续使用未确认版本。')
    return result
