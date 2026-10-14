#!/usr/bin/env python3
"""Entry point for the SmartBrew AI touchscreen simulator.

Run with:

    python main.py                 # uses data/machine_state.json
    python main.py /tmp/state.json # uses a different state file
"""

from smartbrew.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
