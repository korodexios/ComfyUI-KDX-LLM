"""One-click sampling presets.

Pick a preset (balanced, creative, precise, reasoning, json_output) or save
your own. Wire the output into Chat or Client — no need to configure individual
parameters.

Override with a Simple/Advanced Sampling node chained after this one.
"""
import json
from . import quick_sampling_presets


class KDX_LLM_Quick_Presets:
    DESCRIPTION = "Ready-made sampling settings in one click (balanced, creative, precise…). Connect to Chat's sampling input. action = save stores your own preset."

    CATEGORY = "KDX/LLM"
    RETURN_TYPES = ("KDX_LLM_OPTIONS", "STRING")
    RETURN_NAMES = ("sampling", "preset_info")
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls):
        saved = [p for p in quick_sampling_presets.list_presets() if p != "(none)"]
        presets = ["(none)"] + saved
        return {"required": {
            "preset": (presets, {"default": saved[0] if saved else "(none)", "tooltip": "Select a sampling preset."}),
            "action": (["use", "save", "delete"], {"default": "use", "tooltip": "use = load preset; save = save current values; delete = remove custom preset."}),
            "name": ("STRING", {"default": "", "tooltip": "Name for a new preset when saving."}),
        }, "optional": {
            "base_options": ("KDX_LLM_OPTIONS", {
                "tooltip": "Upstream sampling values. The preset overrides matching keys.",
            }),
            "custom_json": ("STRING", {
                "default": "",
                "multiline": True,
                "tooltip": "Custom sampling JSON to save. Example: {\"temperature\": 0.8, \"top_p\": 0.9}. Used when action=save.",
            }),
        }}

    @classmethod
    def VALIDATE_INPUTS(cls, preset):
        # A deleted custom preset must not break prompt validation; get_preset()
        # returns {} for unknown names.
        return True if isinstance(preset, str) else "preset must be a string"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return json.dumps({
            "preset": kwargs.get("preset", ""),
            "action": kwargs.get("action", "use"),
            "name": kwargs.get("name", ""),
            "custom_json": kwargs.get("custom_json", ""),
            "mtime": quick_sampling_presets.mtime(),
        }, sort_keys=True)

    def run(self, preset="(none)", action="use", name="", base_options=None, custom_json=""):
        # Start from base
        opts = dict(base_options.get("options", {})) if isinstance(base_options, dict) else {}

        if action == "save":
            target = (name or preset).strip()
            if not target or target == "(none)":
                raise ValueError("A preset name is required for saving.")

            # Parse custom JSON if provided
            params = {}
            if custom_json and custom_json.strip():
                try:
                    params = json.loads(custom_json.strip())
                    if not isinstance(params, dict):
                        raise ValueError("KDX LLM: 'custom_json' must be a JSON object")
                except json.JSONDecodeError as e:
                    raise ValueError(f"KDX LLM: Invalid JSON in 'custom_json': {e}") from e
            else:
                # Save current base_options as the preset
                params = dict(opts)

            if not quick_sampling_presets.save_preset(target, params):
                raise RuntimeError(f"Could not save preset '{target}'.")

            preset_info = json.dumps({
                "status": "saved",
                "name": target,
                "params": params,
                "all_presets": quick_sampling_presets.list_presets(),
            }, indent=2)
            return ({"options": params}, preset_info)

        if action == "delete":
            if not quick_sampling_presets.delete_preset(preset):
                return ({}, json.dumps({"status": "not_found_or_builtin", "name": preset}, indent=2))
            return ({}, json.dumps({"status": "deleted", "name": preset}, indent=2))

        # action == "use" (default)
        if preset and preset != "(none)":
            preset_params = quick_sampling_presets.get_preset(preset)
            # Preset overrides base
            opts.update(preset_params)

        preset_info = json.dumps({
            "preset": preset,
            "params": opts,
            "all_presets": quick_sampling_presets.list_presets(),
        }, indent=2)

        return ({"options": opts}, preset_info)


NODE_CLASS_MAPPINGS = {"KDX_LLM_Quick_Presets": KDX_LLM_Quick_Presets}
NODE_DISPLAY_NAME_MAPPINGS = {"KDX_LLM_Quick_Presets": "⚡ KDX • LLM Quick Sampling Presets"}