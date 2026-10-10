"""Private, vault-scoped locks and durable uncertain-operation markers."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import time
from private_io import write_private_json


def operation_path(vault, key):
    return Path(vault).resolve().parent / '.state' / 'paid-operations' / key


@contextmanager
def exclusive_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    locked = False
    try:
        os.fchmod(fd, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except BlockingIOError as error:
            raise ValueError('Operation is busy in another run; resume after it finishes. No paid-retry approval is needed for active work.') from error
        yield
    finally:
        if locked:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def require_paid_retry(path, *, authorize_paid_retry=False, legacy=()):
    paths = {Path(path), *(Path(p) for p in legacy)}
    if any(p.exists() for p in paths) and not authorize_paid_retry:
        raise ValueError('Hybrid operation interrupted or failed; paid work may have completed. Explicit paid-retry approval required.')
    return paths


@contextmanager
def pending_operation(path, *, authorize_paid_retry=False, legacy=()):
    """Caller holds the operation lock; interrupted work keeps its marker."""
    paths = require_paid_retry(path, authorize_paid_retry=authorize_paid_retry, legacy=legacy)
    write_private_json(Path(path), {'status': 'pending', 'pid': os.getpid(), 'started_epoch': time.time()})
    yield
    # Only a confirmed result persisted by the caller completes the operation.
    for pending in paths:
        pending.unlink(missing_ok=True)
