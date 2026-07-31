"""Console helpers."""

import sys


def setup_utf8_console():
    """Make the Windows console handle emoji output.

    Uses reconfigure(), which is idempotent — safe to call from every entry
    point even when modules import each other (re-wrapping stdout was not,
    and used to close the underlying stream).
    """
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
