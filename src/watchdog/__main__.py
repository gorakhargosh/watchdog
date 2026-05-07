"""Allow running watchmedo as ``python -m watchdog``."""

if __name__ == "__main__":
    import sys
    from watchdog.watchmedo import main

    sys.exit(main())
