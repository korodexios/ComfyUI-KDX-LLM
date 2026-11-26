"""Response post-processing utilities.

Clean up LLM output: strip whitespace, extract code blocks, truncate,
or pass through untouched. Chain multiple formatters by wiring output to input.
"""
import json
import re

_THINK_RE = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.DOTALL | re.IGNORECASE)
_CODE_FENCE = re.compile(r"```([a-z0-9]*)\s*\n?(.*?)\n?```", re.DOTALL | re.IGNORECASE)


class KDX_LLM_Response_Formatter:
    """Post-process LLM response text."""

    DESCRIPTION = 'Cleans up the answer text: trim whitespace, take a ```code block```, cut to a length, change case, or remove <think> tags. To take one value from a JSON answer use JSON Extract instead.'

    CATEGORY = "KDX/LLM"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("formatted", "metadata_json")
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "response": ("STRING", {"default": "", "multiline": True, "tooltip": "Raw LLM response text."}),
            "action": ([
                "passthrough",
                "strip_whitespace",
                "extract_first_code_block",
                "extract_all_code_blocks",
                "truncate",
                "lowercase",
                "uppercase",
                "remove_thinking_tags",
            ], {
                "default": "passthrough",
                "tooltip": (
                    "passthrough = no changes. "
                    "strip_whitespace = remove leading/trailing blank lines. "
                    "extract_first_code_block = return content of the first code fence. "
                    "extract_all_code_blocks = return all code fences joined with blank lines. "
                    "truncate = cut to max_length. "
                    "lowercase / uppercase = case conversion. "
                    "remove_thinking_tags = strip thinking/reasoning tags and their content."
                ),
            }),
            "max_length": ("INT", {
                "default": 4000, "min": 10, "max": 1048576,
                "tooltip": "Maximum characters for truncate action.",
            }),
            "truncate_suffix": ("STRING", {
                "default": "...",
                "tooltip": "Text appended when truncated.",
            }),
        }, "optional": {
            "response_obj": ("ANY", {"tooltip": "Optional structured response object from Chat; used if response is empty."}),
        }}

    def run(self, response="", action="passthrough", max_length=4000, truncate_suffix="...", response_obj=None):
        if not response and isinstance(response_obj, dict):
            response = response_obj.get("content", "")
        text = response or ""
        meta = {"action": action, "original_length": len(text)}

        if action == "passthrough":
            pass
        elif action == "strip_whitespace":
            text = text.strip()
        elif action == "extract_first_code_block":
            match = _CODE_FENCE.search(text)
            if match:
                lang = match.group(1) or ""
                text = match.group(2).strip()
                meta["code_lang"] = lang
            else:
                text = ""
                meta["code_lang"] = ""
        elif action == "extract_all_code_blocks":
            blocks = []
            for match in _CODE_FENCE.finditer(text):
                blocks.append(match.group(2).strip())
            text = "\n\n".join(blocks) if blocks else ""
            meta["code_block_count"] = len(blocks)
        elif action == "truncate":
            if len(text) > max_length:
                text = text[:max_length] + truncate_suffix
                meta["truncated"] = True
            else:
                meta["truncated"] = False
        elif action == "lowercase":
            text = text.lower()
        elif action == "uppercase":
            text = text.upper()
        elif action == "remove_thinking_tags":
            text = _THINK_RE.sub("", text).strip()

        meta["output_length"] = len(text)
        return (text, json.dumps(meta, ensure_ascii=False, indent=2))


NODE_CLASS_MAPPINGS = {"KDX_LLM_Response_Formatter": KDX_LLM_Response_Formatter}
NODE_DISPLAY_NAME_MAPPINGS = {"KDX_LLM_Response_Formatter": "✂️ KDX • LLM Response Formatter"}