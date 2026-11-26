"""KDX LLM Client — tool/function calling node.

Defines OpenAI-compatible tools that the LLM can invoke.
Wire into the Chat node's 'tools' input.

Example — a single tool:
    name: get_weather
    description: Get the current weather for a city
    parameters: {"type": "object", "properties": {"city": {"type": "string"}}}

Example — multiple tools (one per line, JSON array):
    [{"name": "tool_a", ...}, {"name": "tool_b", ...}]
"""

import json


class KDX_LLM_Tool:
    """Define tools (functions) the LLM can call during chat.

    Accepts either a single tool definition or a JSON array of tools.
    The output is a KDX_LLM_TOOLS object that wires into the Chat node.
    """

    DESCRIPTION = "Describes functions the model may call (function calling). Connect to Chat's tools input; the model's calls appear in Chat's tool_calls output."

    CATEGORY = "KDX/LLM"
    RETURN_TYPES = ("KDX_LLM_TOOLS",)
    RETURN_NAMES = ("tools",)
    FUNCTION = "execute"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "name": ("STRING", {
                    "default": "",
                    "tooltip": "Tool name (e.g. 'get_weather')",
                }),
                "description": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "What the tool does — the LLM reads this to decide when to call it",
                }),
                "parameters": ("STRING", {
                    "default": "{}",
                    "multiline": True,
                    "tooltip": (
                        "JSON Schema for the tool's parameters. "
                        "Example: {\"type\": \"object\", \"properties\": {\"city\": {\"type\": \"string\"}}}"
                    ),
                }),
            },
            "optional": {
                "extra_tools": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": (
                        "Optional: additional tools as a JSON array. "
                        "Example: [{\"name\": \"tool_b\", \"description\": \"...\", \"parameters\": {...}}]"
                    ),
                }),
            },
        }

    def execute(self, name="", description="", parameters="{}", extra_tools=""):
        tools = []

        # Primary tool
        if name and name.strip():
            try:
                params = json.loads(parameters) if parameters.strip() else {}
            except json.JSONDecodeError as exc:
                raise ValueError(f"KDX LLM: Invalid JSON in 'parameters': {exc}") from exc
            if not isinstance(params, dict):
                raise ValueError(f"KDX LLM: 'parameters' must be a JSON object, got {type(params).__name__}")
            tools.append({
                "type": "function",
                "function": {
                    "name": name.strip(),
                    "description": (description or "").strip(),
                    "parameters": params,
                },
            })

        # Extra tools (JSON array)
        if extra_tools and extra_tools.strip():
            try:
                extra = json.loads(extra_tools.strip())
            except json.JSONDecodeError as exc:
                raise ValueError(f"KDX LLM: Invalid JSON in 'extra_tools': {exc}") from exc
            if not isinstance(extra, list):
                raise ValueError(f"KDX LLM: 'extra_tools' must be a JSON array, got {type(extra).__name__}")
            for index, t in enumerate(extra):
                if not isinstance(t, dict) or not t.get("name"):
                    raise ValueError(f"KDX LLM: extra_tools[{index}] must be an object with a 'name'")
                params = t.get("parameters", {})
                if not isinstance(params, dict):
                    raise ValueError(f"KDX LLM: extra_tools[{index}].parameters must be a JSON object")
                tools.append({
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": params,
                    },
                })

        return ({"tools": tools},)


NODE_CLASS_MAPPINGS = {
    "KDX_LLM_Tool": KDX_LLM_Tool,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "KDX_LLM_Tool": "🛠️ KDX • LLM Tool",
}
