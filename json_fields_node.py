"""Structured output helpers: ask the model for named JSON fields, then split them.

Workflow:
    📐 JSON Output Format (fields) ──system_prompt──▶ 💬 Chat ──json──▶ 🧩 JSON Fields
                            └────────fields──────────────────────────────┘

Fields are written one per line (or comma separated), optionally with a short
description after a colon:

    rewritten_prompt: the improved, detailed image prompt
    negative_prompt: things to avoid
    style
"""

import re

from .json_extract_node import _MISSING, lookup, value_to_text
from .postprocess import extract_json

MAX_FIELDS = 6
_NAME = re.compile(r"^[A-Za-z0-9_.\[\]-]+$")


def parse_fields(raw: str):
    """Return [(name, description)] from lines / commas; 'name: description' allowed."""
    fields = []
    text = (raw or "").strip()
    if not text:
        return fields
    # One field per line; a single line may also hold comma-separated names.
    lines = text.splitlines()
    if len(lines) == 1 and ":" not in lines[0]:
        lines = lines[0].split(",")
    for line in lines:
        item = line.strip().lstrip("-*•").strip()
        if not item or item.startswith("#"):
            continue
        name, _, description = item.partition(":")
        name = name.strip().strip('"').strip("'")
        if not name:
            continue
        if not _NAME.match(name):
            raise ValueError(
                f"KDX JSON fields: '{name}' is not a valid field name. "
                "Use letters, digits and _ (e.g. rewritten_prompt)."
            )
        if name not in [f[0] for f in fields]:
            fields.append((name, description.strip()))
    return fields


def build_instruction(fields) -> str:
    lines = [
        "Respond with only a JSON object - no markdown, no code fences, no text before or after it.",
        "Use exactly these keys:",
    ]
    for name, description in fields:
        lines.append(f'- "{name}": {description}' if description else f'- "{name}"')
    lines.append("Every value must be a string unless stated otherwise.")
    return "\n".join(lines)


class KDX_LLM_JSON_Output_Format:
    DESCRIPTION = (
        "Tells the model to answer as JSON with the fields you list, e.g. "
        "'rewritten_prompt: the improved prompt' and 'negative_prompt'. "
        "Connect 'system_prompt' to Chat's system_prompt input and 'fields' to a JSON Fields node, "
        "which then gives you each field as its own output."
    )
    CATEGORY = "KDX/LLM"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("system_prompt", "fields")
    OUTPUT_TOOLTIPS = (
        "Your system prompt plus the JSON instructions. Connect to Chat's system_prompt.",
        "The field names, one per line. Connect to JSON Fields' 'fields' input so both nodes stay in sync.",
    )
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "fields": ("STRING", {
                    "default": "rewritten_prompt: the improved, detailed image prompt\nnegative_prompt: things the image should avoid",
                    "multiline": True,
                    "tooltip": "One field per line: name, optionally followed by ': description' "
                               "telling the model what to put there. Up to 6 fields come out of JSON Fields.",
                }),
            },
            "optional": {
                "system_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "Your own instructions (role, style, rules). The JSON format instructions are added after it.",
                }),
            },
        }

    def run(self, fields="", system_prompt=""):
        parsed = parse_fields(fields)
        if not parsed:
            raise ValueError("KDX JSON Output Format: list at least one field, e.g. rewritten_prompt")
        instruction = build_instruction(parsed)
        combined = f"{system_prompt.strip()}\n\n{instruction}" if (system_prompt or "").strip() else instruction
        return (combined, "\n".join(name for name, _ in parsed))


class KDX_LLM_JSON_Fields:
    DESCRIPTION = (
        "Splits a JSON answer into separate text outputs, one per field (up to 6). "
        "Write the field names (or connect 'fields' from JSON Output Format), connect Chat's 'json' output, "
        "and field_1, field_2, ... carry the values in the same order. "
        "Output labels are renamed to the field names in the editor."
    )
    CATEGORY = "KDX/LLM"
    RETURN_TYPES = ("STRING",) * MAX_FIELDS + ("BOOLEAN", "STRING")
    RETURN_NAMES = tuple(f"field_{i}" for i in range(1, MAX_FIELDS + 1)) + ("all_found", "missing")
    OUTPUT_TOOLTIPS = tuple(
        f"Value of field number {i} from the 'fields' list (plain text, no quotes)." for i in range(1, MAX_FIELDS + 1)
    ) + (
        "True when every listed field was found in the JSON.",
        "Names of fields that were missing (comma separated).",
    )
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "json": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "JSON text to read. Connect Chat's 'json' or 'response' output.",
                }),
                "fields": ("STRING", {
                    "default": "rewritten_prompt\nnegative_prompt",
                    "multiline": True,
                    "tooltip": "Field names in output order, one per line (or comma separated). "
                               "Nested keys work too: scene.lighting",
                }),
            },
            "optional": {
                "default": ("STRING", {
                    "default": "",
                    "tooltip": "Text used for a field that is missing.",
                }),
                "fail_if_missing": ("BOOLEAN", {
                    "default": False,
                    "label_on": "stop with error",
                    "label_off": "use default",
                    "tooltip": "Stop the workflow when a listed field is missing, instead of using 'default'.",
                }),
            },
        }

    def run(self, json="", fields="", default="", fail_if_missing=False):
        names = [name for name, _ in parse_fields(fields)]
        if len(names) > MAX_FIELDS:
            raise ValueError(f"KDX JSON Fields: at most {MAX_FIELDS} fields, got {len(names)}. Use another JSON Fields node for the rest.")

        text = json if isinstance(json, str) else value_to_text(json)
        data = extract_json(text) if text.strip() else None

        values, missing = [], []
        for name in names:
            value = _MISSING if data is None else lookup(data, name)[0]
            if value is _MISSING:
                missing.append(name)
                values.append(default or "")
            else:
                values.append(value_to_text(value))

        if missing and fail_if_missing:
            reason = "the input is not valid JSON" if data is None else "missing field(s): " + ", ".join(missing)
            raise ValueError(f"KDX JSON Fields: {reason}")

        values += [""] * (MAX_FIELDS - len(values))
        return tuple(values) + (not missing and bool(names), ", ".join(missing))


NODE_CLASS_MAPPINGS = {
    "KDX_LLM_JSON_Output_Format": KDX_LLM_JSON_Output_Format,
    "KDX_LLM_JSON_Fields": KDX_LLM_JSON_Fields,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "KDX_LLM_JSON_Output_Format": "📐 KDX • JSON Output Format",
    "KDX_LLM_JSON_Fields": "🗂️ KDX • JSON Fields",
}
