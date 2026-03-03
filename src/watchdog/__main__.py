"""Allow running watchmedo as ``python -m watchdog``."""

from watchdog.watchmedo import main

raise SystemExit(main())
