"""Persistent model profiles for KDX LLM Client.

The file is user-editable JSON and intentionally contains no provider-specific
hardcoded model settings. Profiles may use exact model IDs or glob patterns.
"""
import json
import os
import threading

from .kdx_core.profile_resolver import (
    MODES,
    normalize_profile,
    resolve_profile,
)
from ._store_utils import backup_if_corrupt

FILE_NAME = "model_profiles.json"
_lock = threading.Lock()


def store_path():
    env = os.environ.get("KDX_LLM_PROFILES_FILE", "").strip()
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
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    models = data.get("models", data)
    return models if isinstance(models, dict) else {}


def _write(models):
    path = store_path()
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": 3, "models": models}, f, ensure_ascii=False, indent=2)
            f.write("\n")
        backup_if_corrupt(path)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def _mode(value):
    """Deprecated — delegates to kdx_core.profile_resolver._normalize_mode."""
    from .kdx_core.profile_resolver import _normalize_mode
    return _normalize_mode(value)


def normalize(profile):
    """Normalize a profile. Delegates to kdx_core (single source of truth)."""
    return normalize_profile(profile)


def lookup(model):
    """Lookup profile with fixed precedence (exact > case-insensitive > suffix > glob).

    Delegates to kdx_core.profile_resolver — single source of truth.
    """
    if not model:
        return None, {}
    models = _read()
    res = resolve_profile(model, models)
    if res["key"] is not None:
        return res["key"], res["profile"]
    return None, {}


def list_models():
    return sorted(str(k) for k in _read())


def save_profile(model, profile):
    if not model or not isinstance(profile, dict):
        return False
    with _lock:
        models = _read()
        models[model] = normalize(profile)
        return _write(models)


def save_mode(model, mode, sampling, request=None):
    if not model or mode not in MODES or not isinstance(sampling, dict):
        return False
    _, existing = lookup(model)
    existing[mode] = {"sampling": dict(sampling), "request": dict(request or {})}
    return save_profile(model, existing)


def delete(model):
    with _lock:
        models = _read()
        if model not in models:
            return False
        del models[model]
        return _write(models)


def profile_json(model):
    key, profile = lookup(model)
    return json.dumps({"model": model, "matched_key": key, "profile": profile}, ensure_ascii=False, indent=2)
