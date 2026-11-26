"""KDX Prompt Template — fill {placeholders} in a prompt from inputs.

Example template:
    Rewrite this image prompt so it is more detailed: {text_1}
    Style: {style}

``{text_1}`` .. ``{text_4}`` come from the optional text inputs (connect any
STRING output, e.g. a prompt node), other names come from the ``variables``
box written as ``name = value`` lines. ``{{`` and ``}}`` produce literal braces,
so JSON examples inside the template stay intact.
"""

import json
import re

_PLACEHOLDER = re.compile(r"\{\{|\}\}|\{([A-Za-z_][A-Za-z0-9_]*)\}")
TEXT_INPUTS = ("text_1", "text_2", "text_3", "text_4")


def parse_variables(raw: str) -> dict:
    """``name = value`` (or ``name: value``) lines -> dict. Blank/# lines ignored."""
    values = {}
    for line in (raw or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*[=:]\s?(.*)$", stripped)
        if not match:
            raise ValueError(f"KDX Prompt Template: cannot read variable line '{stripped}'. Use: name = value")
        values[match.group(1)] = match.group(2).replace("\\n", "\n")
    return values


def render_template(template: str, values: dict):
    """Return (text, missing_names). Unknown placeholders are left untouched."""
    missing = []

    def replace(match):
        token = match.group(0)
        if token == "{{":
            return "{"
        if token == "}}":
            return "}"
        name = match.group(1)
        if name in values:
            return str(values[name])
        if name not in missing:
            missing.append(name)
        return token

    return _PLACEHOLDER.sub(replace, template or ""), missing


class KDX_LLM_Prompt_Template:
    DESCRIPTION = (
        "Builds a prompt from a template with {placeholders}. "
        "Example: 'Rewrite for an image model: {text_1}. Style: {style}'. "
        "{text_1}..{text_4} come from the text inputs (connect any text), other names from the "
        "'variables' box as 'style = cinematic' lines. Use {{ and }} for literal braces. "
        "Connect 'text' to Chat's prompt."
    )
    CATEGORY = "KDX/LLM"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("text", "missing")
    OUTPUT_TOOLTIPS = (
        "The finished prompt with all known placeholders filled in.",
        "Placeholders that had no value (comma separated). Empty when everything was filled.",
    )
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls):
        optional = {
            name: ("STRING", {
                "default": "",
                "multiline": False,
                "tooltip": f"Value for {{{name}}} in the template. Connect any text output here or type it.",
            })
            for name in TEXT_INPUTS
        }
        optional["variables"] = ("STRING", {
            "default": "",
            "multiline": True,
            "tooltip": "Extra placeholders, one per line: style = cinematic  •  mood: calm. "
                       "Write \\n for a line break inside a value.",
        })
        optional["fail_on_missing"] = ("BOOLEAN", {
            "default": False,
            "label_on": "stop with error",
            "label_off": "leave as is",
            "tooltip": "What to do with a {placeholder} that has no value: stop the workflow, or leave it in the text.",
        })
        return {
            "required": {
                "template": ("STRING", {
                    "default": "Rewrite this prompt for an image model, more detailed and vivid: {text_1}",
                    "multiline": True,
                    "tooltip": "Prompt text with {placeholders}. {text_1}..{text_4} = the text inputs; "
                               "other names = lines in 'variables'.",
                }),
            },
            "optional": optional,
        }

    def run(self, template="", text_1="", text_2="", text_3="", text_4="", variables="", fail_on_missing=False):
        values = parse_variables(variables)
        for name, value in zip(TEXT_INPUTS, (text_1, text_2, text_3, text_4)):
            values.setdefault(name, value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))
        text, missing = render_template(template, values)
        if missing and fail_on_missing:
            raise ValueError("KDX Prompt Template: no value for " + ", ".join("{" + m + "}" for m in missing))
        return (text, ", ".join(missing))


NODE_CLASS_MAPPINGS = {"KDX_LLM_Prompt_Template": KDX_LLM_Prompt_Template}
NODE_DISPLAY_NAME_MAPPINGS = {"KDX_LLM_Prompt_Template": "🧩 KDX • Prompt Template"}
