"""Reusable named system-prompt profiles."""
import json
from . import prompt_store


class KDX_LLM_System_Prompt:
    DESCRIPTION = "Instructions for the model (role, rules, output format). Type the text, or pick a saved one in 'profile'. Connect 'system_prompt' to Chat's system_prompt_profile. action = save / delete manages saved prompts."

    CATEGORY = "KDX/LLM"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("system_prompt", "profile_name")
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls):
        names = ["(none)"] + [n for n in prompt_store.names() if n != "(none)"]
        return {"required": {
            "profile": (names, {"default": "(none)", "tooltip": "(none) = use the text below. Select a saved system prompt."}),
            "action": (["use", "save", "delete"], {"default": "use", "tooltip": "Use, save or delete a named prompt profile."}),
            "name": ("STRING", {"default": "", "tooltip": "Profile name when saving."}),
            "system_prompt": ("STRING", {"default": "", "multiline": True, "tooltip": "Prompt text used when saving."}),
            "description": ("STRING", {"default": "", "tooltip": "Optional description for the saved profile."}),
        }}

    @classmethod
    def VALIDATE_INPUTS(cls, profile):
        # Saved names can be deleted or differ between machines; run() treats an
        # unknown name like "(none)" instead of failing prompt validation.
        return True if isinstance(profile, str) else "profile must be a string"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return json.dumps({"mtime": prompt_store.mtime(), **{k: kwargs.get(k, "") for k in ("profile", "action", "name", "system_prompt", "description")}}, sort_keys=True)

    def run(self, profile="(none)", action="use", name="", system_prompt="", description=""):
        selected = (profile or "").strip()
        if action == "save":
            target = (name or selected).strip()
            if not target or target == "(none)":
                raise ValueError("A system prompt profile name is required.")
            if not prompt_store.save(target, system_prompt, description):
                raise RuntimeError(f"Could not save system prompt profile '{target}'.")
            selected = target
        elif action == "delete":
            if selected and selected != "(none)":
                prompt_store.delete(selected)
            return "", selected
        else:
            saved = prompt_store.get(selected) if selected and selected != "(none)" else {}
            if saved.get("prompt"):
                system_prompt = saved.get("prompt", "")
        return system_prompt or "", selected if selected != "(none)" else ""


NODE_CLASS_MAPPINGS = {"KDX_LLM_System_Prompt": KDX_LLM_System_Prompt}
NODE_DISPLAY_NAME_MAPPINGS = {"KDX_LLM_System_Prompt": "📝 KDX • LLM System Prompt"}