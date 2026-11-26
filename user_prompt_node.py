"""Reusable named user-prompt profiles.

Save and load frequently used prompts. Wire the output into the Chat node's
prompt input — or just use the built-in prompt field for quick one-off tests.

Workflow:
  1. Type your prompt in the node (or leave empty to use the saved version).
  2. Set action = save + give it a name → saved for next time.
  3. Later: select the saved profile → prompt field auto-fills.
"""
import json
from . import user_prompt_store


class KDX_LLM_User_Prompt:
    DESCRIPTION = "Reusable user message. Type the text or pick a saved one in 'profile', then connect 'user_prompt' to Chat's prompt. action = save / delete manages saved prompts."

    CATEGORY = "KDX/LLM"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("user_prompt", "profile_name")
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls):
        names = ["(none)"] + [n for n in user_prompt_store.names() if n != "(none)"]
        return {"required": {
            "profile": (names, {"default": "(none)", "tooltip": "(none) = use the text below. Select a saved user prompt."}),
            "action": (["use", "save", "delete"], {"default": "use", "tooltip": "Use, save or delete a named prompt profile."}),
            "name": ("STRING", {"default": "", "tooltip": "Profile name when saving."}),
            "user_prompt": ("STRING", {"default": "", "multiline": True, "tooltip": "Prompt text used when saving."}),
            "description": ("STRING", {"default": "", "tooltip": "Optional description for the saved profile."}),
        }}

    @classmethod
    def VALIDATE_INPUTS(cls, profile):
        # Saved names can be deleted or differ between machines; run() treats an
        # unknown name like "(none)" instead of failing prompt validation.
        return True if isinstance(profile, str) else "profile must be a string"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return json.dumps({
            "mtime": user_prompt_store.mtime(),
            **{k: kwargs.get(k, "") for k in ("profile", "action", "name", "user_prompt", "description")}
        }, sort_keys=True)

    def run(self, profile="(none)", action="use", name="", user_prompt="", description=""):
        selected = (profile or "").strip()
        if action == "save":
            target = (name or selected).strip()
            if not target or target == "(none)":
                raise ValueError("A user prompt profile name is required.")
            if not user_prompt_store.save(target, user_prompt, description):
                raise RuntimeError(f"Could not save user prompt profile '{target}'.")
            selected = target
        elif action == "delete":
            if selected and selected != "(none)":
                user_prompt_store.delete(selected)
            return "", selected
        else:
            saved = user_prompt_store.get(selected) if selected and selected != "(none)" else {}
            if saved.get("prompt"):
                user_prompt = saved.get("prompt", "")
        return user_prompt or "", selected if selected != "(none)" else ""


NODE_CLASS_MAPPINGS = {"KDX_LLM_User_Prompt": KDX_LLM_User_Prompt}
NODE_DISPLAY_NAME_MAPPINGS = {"KDX_LLM_User_Prompt": "📋 KDX • LLM User Prompt"}