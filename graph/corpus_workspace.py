"""Explicit mutable import workspace, separate from frozen publication snapshots.

Imports append transactionally to one database. They never copy a prior runtime,
modify a frozen runtime, publish a Site or move a current/version pointer.
"""
import argparse
from contextlib import closing, contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import tempfile

from quantgraph.graph.corpus_research import DATABASE, import_manifest

MARKER='.mutable-corpus-workspace.json'
FORMAT='quantgraph-mutable-corpus-workspace/v1'
DEFAULT_RESERVE=5*1024**3


def initialize(runtime):
    """Explicitly create a NEW empty workspace; never adopt a historical one."""
    runtime=Path(runtime)
    runtime.mkdir(mode=0o700,parents=False,exist_ok=False)
    with (runtime/MARKER).open('x') as f:
        json.dump(dict(schema_version=FORMAT,role='mutable_append_only_runtime'),f)
        f.flush();os.fsync(f.fileno())
    return dict(status='INITIALIZED',runtime=str(runtime))


def _check(runtime):
    runtime=Path(runtime)
    if not stat.S_ISDIR(runtime.lstat().st_mode):
        raise ValueError('Workspace must be an explicit non-symlink directory')
    marker=runtime/MARKER
    if marker.is_symlink() or not marker.is_file():
        raise ValueError('Frozen or unmarked runtime cannot be written')
    if json.loads(marker.read_text())!={'schema_version':FORMAT,'role':'mutable_append_only_runtime'}:
        raise ValueError('Unknown mutable workspace marker')
    db=runtime/DATABASE
    if db.exists() or db.is_symlink():
        s=db.lstat()
        if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or not s.st_mode&0o200:
            raise ValueError('Mutable database must be writable, regular and independently allocated')
    return runtime


@contextmanager
def _locked(runtime):
    runtime=_check(runtime)
    fd=os.open(runtime/'.writer.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'a+') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        _check(runtime)
        yield runtime


def _capacity(path,reserve,needed=0):
    if reserve<0 or needed<0 or shutil.disk_usage(path).free<reserve+needed:
        raise ValueError('Insufficient disk space above required reserve')


def append_collection(runtime,manifest_path,expected_sha256,results_dir,audit_dir,*,reserve_bytes=DEFAULT_RESERVE):
    """Append one verified collection using the existing atomic SQLite transaction."""
    with _locked(runtime) as root:
        # Conservatively budget additional tables/indexes, without cloning the DB.
        refs=json.loads(Path(manifest_path).read_text()).get('artifacts',{})
        needed=4*sum(int(r.get('bytes',0)) for r in refs.values())
        _capacity(root,reserve_bytes,needed)
        result=import_manifest(root,manifest_path,expected_sha256,results_dir,audit_dir)
        _check(root)
        return result


def snapshot_runtime(runtime,destination,*,reserve_bytes=DEFAULT_RESERVE):
    """Explicit independent SQLite backup; create-only atomic publication.

    Existing frozen versions remain untouched. This is never called by append.
    """
    destination=Path(destination)
    with _locked(runtime) as root:
        source=root/DATABASE
        if destination.resolve() == root.resolve() or root.resolve() in destination.resolve().parents:
            raise ValueError('Frozen snapshot must be outside the mutable workspace')
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(destination)
        if not destination.parent.is_dir() or destination.parent.is_symlink():
            raise ValueError('Snapshot parent must already be a non-symlink directory')
        _capacity(destination.parent,reserve_bytes,source.stat().st_size+1024**2)
        fd,name=tempfile.mkstemp(prefix='.corpus-snapshot-',dir=destination.parent)
        os.close(fd)
        try:
            with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)) as src, closing(sqlite3.connect(name)) as dst:
                logical_size=src.execute('PRAGMA page_count').fetchone()[0]*src.execute('PRAGMA page_size').fetchone()[0]
                _capacity(destination.parent,reserve_bytes,logical_size+1024**2)
                src.backup(dst)
                dst.execute('PRAGMA journal_mode=DELETE')
                if dst.execute('PRAGMA quick_check').fetchone()[0]!='ok':
                    raise ValueError('Snapshot integrity check failed')
            os.chmod(name,0o400)
            with open(name,'rb') as stream:
                os.fsync(stream.fileno())
                digest=hashlib.file_digest(stream,'sha256').hexdigest()
            os.link(name,destination,follow_symlinks=False)  # Atomic and no overwrite.
        finally:
            os.unlink(name)
        fd=os.open(destination.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
        assert (source.stat().st_dev,source.stat().st_ino)!=(destination.stat().st_dev,destination.stat().st_ino)
        return dict(status='FROZEN',sha256=digest,bytes=destination.stat().st_size)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    commands=p.add_subparsers(dest='command',required=True)
    init=commands.add_parser('init');init.add_argument('runtime',type=Path)
    append=commands.add_parser('append');append.add_argument('runtime',type=Path)
    append.add_argument('--manifest',type=Path,required=True);append.add_argument('--sha256',required=True)
    append.add_argument('--results-dir',type=Path,required=True);append.add_argument('--audit-dir',type=Path,required=True)
    freeze=commands.add_parser('snapshot');freeze.add_argument('runtime',type=Path);freeze.add_argument('destination',type=Path)
    a=p.parse_args()
    if a.command=='init':result=initialize(a.runtime)
    elif a.command=='append':result=append_collection(a.runtime,a.manifest,a.sha256,a.results_dir,a.audit_dir)
    else:result=snapshot_runtime(a.runtime,a.destination)
    print(json.dumps(result))


if __name__=='__main__':main()
