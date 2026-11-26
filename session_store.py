"""Persistent named conversation sessions for KDX LLM Client.

This is optional persistence for KDXLLMSession objects. The DAG session object
stays the normal source of truth inside a workflow; this store lets users save
and reload a conversation by name.
"""

import json
import os
import threading
from ._store_utils import backup_if_corrupt

FILE_NAME = "sessions.json"
_lock = threading.Lock()


def store_path():
    env = os.environ.get("KDX_LLM_SESSIONS_FILE", "").strip()
    if env:
        return os.path.expanduser(env)
    try:
        import folder_paths
        return os.path.join(folder_paths.get_user_directory(), "kdx_llm", FILE_NAME)
    except Exception:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), FILE_NAME)


def mtime():
    try:
        return os.path.getmtime(store_path())
    except OSError:
        return 0.0


def _read():
    try:
        with open(store_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        sessions = data.get("sessions", data) if isinstance(data, dict) else {}
        return sessions if isinstance(sessions, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(sessions):
    path = store_path()
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "sessions": sessions}, f, ensure_ascii=False, indent=2)
            f.write("\n")
        backup_if_corrupt(path)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def names():
    return sorted(_read())


def get(name):
    value = _read().get(name, {})
    return value if isinstance(value, dict) else {}


def save(name, session):
    name = (name or "").strip()
    if not name or not isinstance(session, dict):
        return False
    if "messages" not in session or not isinstance(session.get("messages"), list):
        return False
    with _lock:
        data = _read()
        data[name] = session
        return _write(data)


def delete(name):
    name = (name or "").strip()
    if not name:
        return False
    with _lock:
        data = _read()
        if name not in data:
            return False
        del data[name]
        return _write(data)
