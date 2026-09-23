"""
Auto-restart example using Watchdog.

This example watches a directory for file changes and automatically
restarts a long-running subprocess (like a server) when files change.

Useful for: Development servers that need to restart on config changes.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from watchdog.tricks import AutoRestartTrick


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(message)s",
    )
    
    if len(sys.argv) < 2:
        print("Usage: python autorestart_example.py <path> <command>")
        print("Example: python autorestart_example.py . python server.py")
        sys.exit(1)
    
    path_to_watch = sys.argv[1]
    command = " ".join(sys.argv[2:])
    
    trick = AutoRestartTrick(
        command=command.split(),
        patterns=["*.py", "*.txt", "*.yaml"],
        ignore_patterns=["*.pyc"],
        stop_signal="SIGTERM",
        debounce_interval_seconds=1,
    )
    
    trick.start()
    
    try:
        while True:
            pass
    except KeyboardInterrupt:
        trick.stop()
        print("Stopped.")


if __name__ == "__main__":
    main()