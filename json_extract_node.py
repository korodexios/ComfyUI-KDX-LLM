"""KDX LLM JSON Extract — pull one value out of an LLM JSON answer by key.

Typical use: the Chat node asks the model for JSON such as
``{"rewritten_prompt": "a cat on a roof", "style": "photo"}``. Connect the
Chat ``json`` (or ``response``) output here, type ``rewritten_prompt`` as the
key, and the ``value`` output is the plain prompt text, ready for
CLIP Text Encode.

Key syntax:
- ``rewritten_prompt``     top-level key
- ``scene.lighting``       nested object
- ``shots.0.prompt``       list item (0 = first); ``shots[0].prompt`` also works
Keys are matched exactly first, then case-insensitively (models sometimes
answer ``Rewritten_Prompt``).
"""

import json
import re

from .postprocess import extract_json

_MISSING = object()
_BRACKET_INDEX = re.compile(r"\[(\d+)\]")


def split_key_path(key: str) -> list:
    """``shots[0].prompt`` -> ``["shots", "0", "prompt"]``."""
    normalized = _BRACKET_INDEX.sub(r".\1", (key or "").strip())
    return [part.strip() for part in normalized.split(".") if part.strip()]


def _step(container, part):
    """Resolve one path segment. Returns _MISSING when it does not exist."""
    if isinstance(container, dict):
        if part in container:
            return container[part]
        lowered = part.lower()
        for name, value in container.items():
            if isinstance(name, str) and name.lower() == lowered:
                return value
        return _MISSING
    if isinstance(container, list):
        try:
            index = int(part)
        except ValueError:
            return _MISSING
        if -len(container) <= index < len(container):
            return container[index]
        return _MISSING
    return _MISSING


def _describe_level(container) -> str:
    if isinstance(container, dict):
        keys = ", ".join(str(k) for k in list(container)[:20])
        return f"available keys: {keys}" if keys else "the object is empty"
    if isinstance(container, list):
        return f"the list has {len(container)} item(s) (use 0..{len(container) - 1})" if container else "the list is empty"
    return f"the value there is {type(container).__name__}, not an object or list"


def lookup(data, key: str):
    """Follow ``key`` through ``data``.

    Returns ``(value, None)`` when found, ``(_MISSING, reason)`` otherwise.
    A key whose full text exists literally (even with dots) wins over the path.
    """
    full = (key or "").strip()
    if not full:
        return data, None
    if isinstance(data, dict) and full in data:
        return data[full], None

    current = data
    walked = []
    for part in split_key_path(full):
        nxt = _step(current, part)
        if nxt is _MISSING:
            where = ".".join(walked) or "the top level"
            return _MISSING, f"'{part}' not found at {where}; {_describe_level(current)}"
        current = nxt
        walked.append(part)
    return current, None


def value_to_text(value) -> str:
    """Plain text for STRING outputs: strings as-is, objects/lists as JSON."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False, indent=2)


def value_to_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


class KDX_LLM_JSON_Extract:
    DESCRIPTION = (
        "Pick one value out of a JSON answer by its key. "
        "Example: the model answers {\"rewritten_prompt\": \"a cat on a roof\"} — "
        "set key = rewritten_prompt and the 'value' output is just: a cat on a roof. "
        "Nested keys use dots (scene.lighting), list items use numbers (shots.0.prompt). "
        "Accepts plain JSON, ```json code blocks``` and JSON surrounded by other text."
    )
    CATEGORY = "KDX/LLM"
    RETURN_TYPES = ("STRING", "BOOLEAN", "STRING")
    RETURN_NAMES = ("value", "found", "value_json")
    OUTPUT_TOOLTIPS = (
        (
            "The extracted value as plain text (no quotes). Objects/lists come out as formatted JSON. "
            "If the key is missing you get the 'default' text."
        ),
        "True when the key was found, False when 'default' was used.",
        "The extracted value as JSON (strings keep their quotes). Useful to chain another JSON Extract.",
    )
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "json": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "JSON text to read. Connect the Chat node's 'json' or 'response' output here.",
                }),
                "key": ("STRING", {
                    "default": "",
                    "tooltip": "Which value to take, e.g. rewritten_prompt. "
                               "Nested: scene.lighting  •  list item: shots.0.prompt. "
                               "Empty = return the whole JSON.",
                }),
            },
            "optional": {
                "default": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "Text returned when the key is missing or the input is not JSON.",
                }),
                "fail_if_missing": ("BOOLEAN", {
                    "default": False,
                    "label_on": "stop with error",
                    "label_off": "use default",
                    "tooltip": "What to do when the key is missing: stop the workflow with a clear error, "
                               "or continue with the 'default' text.",
                }),
            },
        }

    def run(self, json="", key="", default="", fail_if_missing=False):
        text = json if isinstance(json, str) else value_to_text(json)
        data = extract_json(text) if text.strip() else None

        if data is None:
            reason = "input is empty" if not text.strip() else "input is not valid JSON"
            return self._missing(reason, text, default, fail_if_missing)

        value, reason = lookup(data, key)
        if value is _MISSING:
            return self._missing(reason, text, default, fail_if_missing)

        return (value_to_text(value), True, value_to_json(value))

    @staticmethod
    def _missing(reason, text, default, fail_if_missing):
        if fail_if_missing:
            preview = text.strip().replace("\n", " ")
            if len(preview) > 200:
                preview = preview[:200] + "…"
            raise ValueError(f"KDX JSON Extract: {reason}. Input starts with: {preview or '(empty)'}")
        return (default or "", False, "")


NODE_CLASS_MAPPINGS = {"KDX_LLM_JSON_Extract": KDX_LLM_JSON_Extract}
NODE_DISPLAY_NAME_MAPPINGS = {"KDX_LLM_JSON_Extract": "🔑 KDX • JSON Extract"}
