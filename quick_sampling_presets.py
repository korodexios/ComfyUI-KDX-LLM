"""Quick-access sampling presets with friendly names.

Pre-built presets for common workflows. Save your own, load them instantly.
Each preset stores a flat JSON of sampling parameters.

Wire the output (KDX_LLM_OPTIONS) into the Chat node or Client node.
"""
import json
import os
from ._store_utils import backup_if_corrupt

# Default presets — user-editable. Prefer ComfyUI user directory when available.
def _store_path():
    env = os.environ.get("KDX_LLM_PRESETS_FILE", "").strip()
    if env:
        return os.path.expanduser(env)
    try:
        import folder_paths
        return os.path.join(folder_paths.get_user_directory(), "kdx_llm", "quick_sampling_presets.json")
    except Exception:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "quick_sampling_presets.json")


_PACK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quick_sampling_presets.json")
_PRESET_FILE = _store_path()


def mtime():
    try:
        return os.path.getmtime(_PRESET_FILE)
    except OSError:
        return 0.0

# Built-in defaults (loaded once, never overwritten by user saves)
_BUILTIN = {
    "balanced": {
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 40,
    },
    "creative": {
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 100,
    },
    "precise": {
        "temperature": 0.1,
        "top_p": 0.5,
        "top_k": 20,
    },
    "reasoning": {
        "temperature": 0.5,
        "top_p": 0.9,
        "top_k": 64,
    },
    "json_output": {
        "temperature": 0.0,
        "top_p": 0.1,
        "top_k": 10,
    },
}


def _load():
    try:
        with open(_PRESET_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except (OSError, ValueError):
        return {}


def _save(data):
    try:
        os.makedirs(os.path.dirname(_PRESET_FILE) or ".", exist_ok=True)
        tmp = _PRESET_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        backup_if_corrupt(_PRESET_FILE)
        os.replace(tmp, _PRESET_FILE)
        return True
    except OSError:
        return False


def list_presets():
    """Return all preset names (built-in + user-defined)."""
    user = _load()
    all_names = set(_BUILTIN.keys()) | set(user.keys())
    return sorted(all_names)


def get_preset(name):
    """Return sampling dict for a preset name. Merges user overrides on top of built-in."""
    result = dict(_BUILTIN.get(name, {}))
    user = _load()
    if name in user:
        user_val = user[name]
        if isinstance(user_val, dict):
            result.update(user_val)
    return result


def save_preset(name, params):
    """Save a user-defined preset (overwrites built-in if same name)."""
    if not name or not isinstance(params, dict):
        return False
    data = _load()
    data[name] = dict(params)
    return _save(data)


def delete_preset(name):
    """Remove a user-defined preset. Built-in presets cannot be deleted."""
    if name in _BUILTIN:
        return False  # can't delete built-in
    data = _load()
    if name not in data:
        return False
    del data[name]
    return _save(data)


def _migrate_legacy_pack_file():
    """Copy old pack-local presets into the user directory once."""
    if _PRESET_FILE == _PACK_FILE or not os.path.exists(_PACK_FILE):
        return
    if os.path.exists(_PRESET_FILE):
        return
    try:
        with open(_PACK_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            _save(data)
    except (OSError, ValueError):
        pass


_migrate_legacy_pack_file()
