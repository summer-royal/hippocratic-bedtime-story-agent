"""Developer diagnostics. Off by default, so the terminal shows only what the child should see.

Diagnostics can quote the story, so they are printed only when DEVELOPER_LOG=1.
"""

import os
import sys


def developer_log(message: str) -> None:
    """Print a developer message to stderr, but only when DEVELOPER_LOG is set to 1."""
    if os.getenv("DEVELOPER_LOG") == "1":
        print(f"Developer log: {message}", file=sys.stderr)
