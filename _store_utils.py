"""Shared helpers for the small JSON stores (profiles, prompts, presets, sessions).

The stores read a missing or broken file as "empty". Without a safeguard the
next save would then overwrite a hand-edited file that only has a typo, and
every saved profile would be gone. ``backup_if_corrupt`` keeps a copy first.
"""

import json
import os
import shutil
import time


def backup_if_corrupt(path: str):
    """Copy ``path`` aside when it exists but is not valid JSON.

    Returns the backup path, or None when no backup was needed (or possible).
    Called right before a store overwrites its file.
    """
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            json.load(f)
        return None
    except (OSError, ValueError):
        pass

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = f"{path}.corrupt-{stamp}.bak"
    try:
        shutil.copy2(path, backup)
    except OSError:
        return None
    print(f"[KDX LLM] {os.path.basename(path)} was not valid JSON; kept a copy at {backup}")
    return backup
