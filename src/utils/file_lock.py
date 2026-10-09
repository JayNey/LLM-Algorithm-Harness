"""Cross-platform exclusive file locking.

Unix uses ``fcntl.flock``; Windows uses ``msvcrt.locking`` on the first
byte of the file (byte-range locks may extend past EOF, so empty files
are lockable); platforms offering neither degrade to a no-op (logged at
debug level) so concurrent-write protection never crashes the caller.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import IO

from src.utils.logging import get_logger

try:  # Unix
    import fcntl
except ImportError:  # pragma: no cover - platform dependent
    fcntl = None  # type: ignore[assignment]

try:  # Windows
    import msvcrt
except ImportError:  # pragma: no cover - platform dependent
    msvcrt = None  # type: ignore[assignment]

logger = get_logger(__name__)


@contextmanager
def exclusive_lock(file_obj: IO[str]) -> Iterator[None]:
    """Hold an exclusive lock on an open file object for the block duration.

    Raises OSError immediately when the platform lock cannot be acquired
    (non-blocking on Windows); the caller's retry policy applies. Degrades
    to a no-op on platforms with no locking primitive.
    """
    if fcntl is not None:
        fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)
    elif msvcrt is not None:
        # msvcrt.locking operates relative to the current file position, so
        # both lock and unlock must target the same anchored offset; buffered
        # writes during the body advance the position (seek() flushes first).
        file_obj.flush()
        anchor = file_obj.tell()
        msvcrt.locking(file_obj.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            yield
        finally:
            file_obj.seek(anchor)
            msvcrt.locking(file_obj.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        logger.debug("file_lock_unavailable", fileno=file_obj.fileno())
        yield
