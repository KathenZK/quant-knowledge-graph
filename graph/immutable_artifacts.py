"""Create-only byte-addressed storage for frozen exports, never live databases.

Each consumer path is an ordinary, read-only file. To edit one intentionally,
replace that path with a new independent file; never chmod/write a shared inode.
Sources are copied from validated bytes, not linked from mutable input paths.
"""
import errno
import fcntl
import hashlib
import os
from pathlib import Path
import stat
import tempfile


def _sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _directory(path):
    path = Path(os.path.abspath(path))
    for part in [*reversed(path.parents), path]:
        try:
            part.mkdir(mode=0o700)
            _sync_directory(part.parent)
        except FileExistsError:
            pass
        if not stat.S_ISDIR(part.lstat().st_mode):
            raise ValueError('Object store components must be non-symlink directories')
    return path


def _verify(path, expected, size):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o222 or info.st_size != size:
            raise ValueError('Existing immutable object has unsafe type, mode or size')
        value = hashlib.file_digest(stream, 'sha256').hexdigest()
        if value != expected:
            raise ValueError('Existing immutable object digest mismatch')
    return info


def materialize_immutable(data, destination, object_store):
    """Publish exact bytes once, then link a NEW destination on the same device.

    Corrupt/writable existing objects fail closed, without repair or overwrite.
    A failed export may leave a valid unused object; garbage collection needs a
    separate dependency audit and authorization.
    """
    if data.startswith(b'SQLite format 3\x00'):
        raise ValueError('Live or frozen SQLite containers are not export objects')
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    root = _directory(object_store)
    digest = hashlib.sha256(data).hexdigest()
    shard = _directory(root / digest[:2])
    obj = shard / digest
    if destination.parent.stat().st_dev != shard.stat().st_dev:
        raise OSError(errno.EXDEV, 'Object store and exports must share a filesystem')
    if not obj.exists() and not obj.is_symlink():
        fd, temporary = tempfile.mkstemp(prefix='.object-', dir=shard)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fchmod(stream.fileno(), 0o400)
                os.fsync(stream.fileno())
            try:
                os.link(temporary, obj, follow_symlinks=False)
            except FileExistsError:
                pass  # A concurrent publisher must still pass full validation.
        finally:
            os.unlink(temporary)
    info = _verify(obj, digest, len(data))
    os.link(obj, destination, follow_symlinks=False)
    try:
        linked = _verify(destination, digest, len(data))
        if (linked.st_dev, linked.st_ino) != (info.st_dev, info.st_ino):
            raise ValueError('Immutable object changed while linking')
    except Exception:
        destination.unlink()
        raise
    directory_fd = os.open(shard, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return dict(sha256=digest, bytes=len(data))


def publish_export_directory(staging, destination):
    """Atomic directory publish, serialized against cooperating exporters.

    Recheck under the shared lock; do not replace any existing destination.
    Uncoordinated writers must never operate in frozen export namespaces.
    """
    staging, destination = Path(staging), Path(destination)
    with (staging/'import-manifest.json').open('rb') as stream:
        os.fsync(stream.fileno())
    _sync_directory(staging)
    fd = os.open(destination.parent/'.corpus-export-publish.lock', os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(destination)
        os.rename(staging, destination)
        _sync_directory(destination.parent)
