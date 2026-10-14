"""JSON-file persistence for the machine's state.

Satisfies NFR-09: ingredient levels, accounts, transactions and the event log
survive a restart. The whole state is held in one JSON file, which is adequate
for a single-machine prototype and keeps the data inspectable by hand during
demonstrations.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

DEFAULT_STATE_PATH = Path("data") / "machine_state.json"


def load_state(path: str | os.PathLike[str] = DEFAULT_STATE_PATH) -> dict[str, Any]:
    """Read the persisted machine state from disk.

    Input:
        path (str | PathLike): Location of the state file. Defaults to
            data/machine_state.json relative to the working directory.

    Returns:
        dict: The parsed state, or an empty dict when the file does not exist
        yet or cannot be parsed (a corrupt file is treated as a cold start
        rather than crashing the machine).
    """
    p = Path(path)
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(
    state: dict[str, Any], path: str | os.PathLike[str] = DEFAULT_STATE_PATH
) -> Path:
    """Write the machine state to disk atomically.

    The state is written to a temporary file in the same directory and then
    moved into place, so a power cut during the write cannot leave a
    half-written state file behind.

    Input:
        state (dict): JSON-serialisable state produced by Machine.snapshot().
        path (str | PathLike): Destination file.

    Returns:
        Path: The path actually written.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, ensure_ascii=False)
        os.replace(tmp_name, p)
    except BaseException:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise
    return p
