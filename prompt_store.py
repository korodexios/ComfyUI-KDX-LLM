"""Persistent named system prompts — one text file per prompt.

Folder: ``<ComfyUI user dir>/kdx_llm/system_prompts/`` (or ``$KDX_LLM_PROMPTS_DIR``).

* ``<name>.md`` (or ``<name>.txt``) holds the prompt text exactly as written. Any text and any
  characters are allowed; nothing is parsed, so a prompt cannot break the store or other prompts.
* The file name (without extension) is the profile name shown in the nodes and in KDX Wildcard Studio.
* Optional one-line descriptions live in ``.descriptions.json``. If that file is damaged, only the
  descriptions are lost; the prompts keep working.
* Files are read on every access, so prompts added or edited in a text editor are used at once.

Migration: the older single-file store ``system_prompts.json`` (next to the folder, or
``$KDX_LLM_PROMPTS_FILE``) is split into files on first use and renamed to
``system_prompts.json.migrated``. Existing files with the same name are never overwritten.
"""

import json
import logging
import os
import re
import threading

FILE_NAME = "system_prompts.json"  # legacy single-file store (migrated)
DIR_NAME = "system_prompts"
EXTENSIONS = (".md", ".txt")
DESCRIPTIONS = ".descriptions.json"
MIGRATED_SUFFIX = ".migrated"

log = logging.getLogger("KDX-LLM")
_lock = threading.RLock()
_BAD_NAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


# ---------------------------------------------------------------------------- locations


def _user_base():
    try:
        import folder_paths
        return os.path.join(folder_paths.get_user_directory(), "kdx_llm")
    except Exception:
        return os.path.dirname(os.path.abspath(__file__))


def legacy_path():
    """The old ``system_prompts.json`` (only read for migration)."""
    env = os.environ.get("KDX_LLM_PROMPTS_FILE", "").strip()
    if env:
        return os.path.expanduser(env)
    return os.path.join(_user_base(), FILE_NAME)


def store_dir():
    env = os.environ.get("KDX_LLM_PROMPTS_DIR", "").strip()
    if env:
        return os.path.expanduser(env)
    if os.environ.get("KDX_LLM_PROMPTS_FILE", "").strip():
        # tests / tools that point at a file: keep the folder next to it
        return os.path.splitext(legacy_path())[0]
    return os.path.join(_user_base(), DIR_NAME)


def store_path():
    """Kept for callers that show where prompts live; it is now a folder."""
    return store_dir()


# ---------------------------------------------------------------------------- helpers


def safe_name(name):
    """Profile name usable as a file name: no path separators or reserved characters."""
    name = _BAD_NAME_CHARS.sub("_", (name or "").strip()).strip(" .")
    return name


def _files():
    """``{name: path}``; ``.md`` wins over ``.txt``; hidden files are ignored."""
    folder = store_dir()
    found = {}
    try:
        entries = sorted(os.listdir(folder))
    except OSError:
        return found
    for fn in entries:
        if fn.startswith("."):
            continue
        stem, ext = os.path.splitext(fn)
        if ext.lower() not in EXTENSIONS or not stem:
            continue
        path = os.path.join(folder, fn)
        if not os.path.isfile(path):
            continue
        if stem in found and found[stem].lower().endswith(".md"):
            continue
        found[stem] = path
    return found


def _read_text(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
        return f.read()


def _write_atomic(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)


def _descriptions():
    try:
        with open(os.path.join(store_dir(), DESCRIPTIONS), "r", encoding="utf-8") as f:
            data = json.load(f)
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_descriptions(desc):
    try:
        _write_atomic(os.path.join(store_dir(), DESCRIPTIONS),
                      json.dumps(desc, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    except OSError as e:  # descriptions are optional
        log.warning("[KDX LLM] could not write prompt descriptions: %s", e)


# ---------------------------------------------------------------------------- migration


def migrate():
    """Split the legacy ``system_prompts.json`` into files. Returns the number of prompts written."""
    src = legacy_path()
    if not os.path.isfile(src):
        return 0
    with _lock:
        if not os.path.isfile(src):
            return 0
        try:
            with open(src, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            log.warning("[KDX LLM] %s is not readable, not migrated: %s", src, e)
            return 0
        prompts = data.get("prompts", data) if isinstance(data, dict) else {}
        if not isinstance(prompts, dict):
            prompts = {}
        existing = _files()
        desc = _descriptions()
        written = 0
        for name, value in prompts.items():
            fname = safe_name(str(name))
            if not fname:
                continue
            text = value.get("prompt", "") if isinstance(value, dict) else str(value or "")
            if isinstance(value, dict) and value.get("description") and fname not in desc:
                desc[fname] = str(value["description"])
            if fname in existing:
                continue
            _write_atomic(os.path.join(store_dir(), fname + ".md"), str(text or ""))
            written += 1
        os.makedirs(store_dir(), exist_ok=True)
        if desc:
            _write_descriptions(desc)
        try:
            os.replace(src, src + MIGRATED_SUFFIX)
        except OSError as e:
            log.warning("[KDX LLM] could not rename %s after migration: %s", src, e)
        log.info("[KDX LLM] migrated %d system prompts from %s to %s", written, src, store_dir())
        return written


# ---------------------------------------------------------------------------- public API (unchanged)


def mtime():
    """Changes when a prompt file is added, removed or edited (cache key for the Chat node)."""
    migrate()
    folder = store_dir()
    stamps = []
    for path in [folder, os.path.join(folder, DESCRIPTIONS), *_files().values()]:
        try:
            stamps.append(os.path.getmtime(path))
        except OSError:
            pass
    return max(stamps) if stamps else 0.0


def names():
    migrate()
    return sorted(_files())


def get(name):
    """``{"prompt", "description"}`` or ``{}`` when the profile does not exist."""
    migrate()
    path = _files().get((name or "").strip())
    if not path:
        return {}
    try:
        text = _read_text(path)
    except OSError:
        return {}
    return {"prompt": text, "description": _descriptions().get(name.strip(), "")}


def save(name, prompt, description=""):
    name = safe_name(name)
    if not name:
        return False
    with _lock:
        migrate()
        try:
            current = _files().get(name)
            path = current or os.path.join(store_dir(), name + ".md")
            _write_atomic(path, prompt or "")
        except OSError as e:
            log.warning("[KDX LLM] could not save system prompt %r: %s", name, e)
            return False
        desc = _descriptions()
        if (description or "") != desc.get(name, ""):
            if description:
                desc[name] = description
            else:
                desc.pop(name, None)
            _write_descriptions(desc)
        return True


def delete(name):
    name = (name or "").strip()
    with _lock:
        migrate()
        if not _files().get(name):
            return False
        try:  # both name.md and name.txt, so a .txt does not reappear after deleting the .md
            for ext in EXTENSIONS:
                path = os.path.join(store_dir(), name + ext)
                if os.path.isfile(path):
                    os.remove(path)
        except OSError:
            return False
        desc = _descriptions()
        if desc.pop(name, None) is not None:
            _write_descriptions(desc)
        return True
