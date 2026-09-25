"""Fail closed before committing/pushing the public tree. Prints paths, never secrets."""
from pathlib import Path
import json
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
files=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
problems=[]
for name in filter(None,files):
    p=ROOT/name
    if name.startswith(('datasets/normalized/','datasets/curated/')):
        problems.append((name,'private data layer'))
    if name.startswith('datasets/raw/sources/') and not name.startswith('datasets/raw/sources/qlib/'):
        problems.append((name,'unapproved raw source'))
    if name.startswith('reports/') and name!='reports/PUBLIC_RELEASE.md':
        problems.append((name,'local report'))
    if p.is_file():
        data=subprocess.check_output(['git','show',':'+name],cwd=ROOT)
        if len(data)>50*1024*1024:problems.append((name,'oversized blob'))
        if b'\x00' not in data:
            # Split fragments prevent the checker source itself from matching.
            patterns=[rb'gh[pousr]_[A-Za-z0-9]{30,}',rb'github_pat_[A-Za-z0-9_]{30,}',rb'AKIA[A-Z0-9]{16}',
                      b'-----BEGIN '+rb'(?:RSA |EC |OPENSSH )?PRIVATE KEY-----', b'/' + b'Users/' + rb'[^/\s]+/']
            if any(re.search(pattern,data) for pattern in patterns):problems.append((name,'credential or private path pattern'))
if problems:
    for path,reason in problems:print(path+': '+reason)
    raise SystemExit(1)
print(json.dumps({'status':'PASS','tracked_files':len([x for x in files if x]),'scope':'public tree paths and credential/private-path patterns'}))
