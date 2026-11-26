"""Persistent named user-prompt profiles.

Mirrors system_prompt_node.py — same save/load/delete pattern,
but for user-facing prompts (the actual questions/messages you send).
"""
import json
import os
import threading
from ._store_utils import backup_if_corrupt

FILE_NAME = "user_prompts.json"
_lock = threading.Lock()


def store_path():
    env = os.environ.get("KDX_LLM_USER_PROMPTS_FILE", "").strip()
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
        prompts = data.get("prompts", data) if isinstance(data, dict) else {}
        return prompts if isinstance(prompts, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(prompts):
    path = store_path()
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "prompts": prompts}, f, ensure_ascii=False, indent=2)
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


def save(name, prompt, description=""):
    name = (name or "").strip()
    if not name:
        return False
    with _lock:
        data = _read()
        data[name] = {"prompt": prompt or "", "description": description or ""}
        return _write(data)


def delete(name):
    with _lock:
        data = _read()
        if name not in data:
            return False
        del data[name]
        return _write(data)
