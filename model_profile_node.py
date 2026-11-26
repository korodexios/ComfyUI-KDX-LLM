"""KDX LLM Model Profile — profile management + client passthrough.

This node manages persistent per-model sampling profiles:
- Load / save / delete profiles
- Pass through the Client connection to downstream Chat nodes
- Sampling nodes (connected to Chat) override profile sampling

If no sampling nodes are connected, the profile sampling is used as-is.
If sampling nodes ARE connected, they override the profile sampling.
"""
import json
from . import sampling_store


class KDX_LLM_Model_Profile:
    DESCRIPTION = "Remembers sampling settings per model. Put it between Client and Chat. profile = (none) automatically uses the saved profile for the Client's model. Connect Sampling nodes and press 'save' to store a profile."

    CATEGORY = "KDX/LLM"
    RETURN_TYPES = (
        "KDX_LLM_CLIENT",
        "STRING", "STRING",
    )
    RETURN_NAMES = (
        "client",
        "profile_name", "profile_json",
    )
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls):
        models = ["(none)"] + [m for m in sampling_store.list_models() if m != "(none)"]
        return {
            "required": {
                "profile": (models, {
                    "default": "(none)",
                    "tooltip": "Saved model profile. (none) = auto-match the profile for the Client's model.",
                }),
            },
            "optional": {
                "client": ("KDX_LLM_CLIENT", {
                    "tooltip": "Connection from the Client node. Auto-detects the model.",
                }),
                "profile_name": ("STRING", {
                    "default": "",
                    "tooltip": "Profile suffix. Empty = save under model ID. e.g. 'test' → key 'model-test'.",
                }),
                # ── Sampling nodes (override profile when connected) ──
                "thinking_options": ("KDX_LLM_OPTIONS", {
                    "tooltip": "Sampling for Thinking mode (from Simple/Advanced/Quick Presets node). Overrides profile when connected.",
                }),
                "non_thinking_options": ("KDX_LLM_OPTIONS", {
                    "tooltip": "Sampling for Non-thinking mode. Overrides profile when connected.",
                }),
                # ── Advanced ──
                "advanced": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "Show expert JSON request overrides.",
                }),
                "thinking_request_json": ("STRING", {
                    "default": "", "multiline": True,
                    "tooltip": "Expert JSON merged into Thinking requests.",
                }),
                "non_thinking_request_json": ("STRING", {
                    "default": "", "multiline": True,
                    "tooltip": "Expert JSON merged into Non-thinking requests.",
                }),
            },
        }

    @classmethod
    def VALIDATE_INPUTS(cls, profile):
        # Profile names live in a user-editable file and the web UI adds the
        # model ID / "(none)" dynamically, so the combo list can legitimately
        # differ from the saved value. Accept any string; run() falls back to
        # the Client's model when the selected profile no longer exists.
        return True if isinstance(profile, str) else "profile must be a string"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return json.dumps({
            "mtime": sampling_store.mtime(),
            "profile": kwargs.get("profile", ""),
            "profile_name": kwargs.get("profile_name", ""),
            "client": kwargs.get("client") or {},
            "thinking_options": kwargs.get("thinking_options") or {},
            "non_thinking_options": kwargs.get("non_thinking_options") or {},
        }, sort_keys=True, default=str)

    def run(
        self,
        profile="(none)",
        client=None,
        profile_name="",
        thinking_options=None,
        non_thinking_options=None,
        advanced=False,
        thinking_request_json="",
        non_thinking_request_json="",
    ):
        def parse(raw, label):
            if not raw or not raw.strip():
                return {}
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{label} is not valid JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{label} must be a JSON object")
            return value

        # ── Resolve model from client ──
        model = ""
        if isinstance(client, dict) and client.get("model"):
            model = client["model"]
        model = (model or "").strip()

        # ── Resolve profile key (priority: profile dropdown > model) ──
        # profile_name is only used by the JS save button, NOT for lookup.
        key = (profile if profile and profile != "(none)" else model).strip() or model
        matched_key, profile_data = sampling_store.lookup(key) if key else (None, {})
        if not profile_data and key != model:
            matched_key, profile_data = sampling_store.lookup(model) if model else (None, {})
        effective_key = matched_key or key

        # Normalize profile_data to ensure safe dictionary access for missing profiles
        if not profile_data:
            profile_data = {
                "thinking": {"sampling": {}, "request": {}},
                "non_thinking": {"sampling": {}, "request": {}}
            }

        # ── Extract sampling from connected nodes ──
        think = dict(thinking_options.get("options", {})) if isinstance(thinking_options, dict) else {}
        nonthink = dict(non_thinking_options.get("options", {})) if isinstance(non_thinking_options, dict) else {}

        # ── Merge: profile is base, connected nodes override ──
        out_think_sampling = dict(profile_data.get("thinking", {}).get("sampling", {}))
        out_think_sampling.update(think)

        out_nonthink_sampling = dict(profile_data.get("non_thinking", {}).get("sampling", {}))
        out_nonthink_sampling.update(nonthink)

        # ── Merge Request Configs ──
        out_think_request = dict(profile_data.get("thinking", {}).get("request", {}))
        out_nonthink_request = dict(profile_data.get("non_thinking", {}).get("request", {}))

        # ── Advanced JSON Override Mode ──
        if advanced:
            out_think_request.update(parse(thinking_request_json, "thinking_request_json"))
            out_nonthink_request.update(parse(non_thinking_request_json, "non_thinking_request_json"))

        # ── Construct final UNIFIED LLM PROFILE dictionary ──
        final_profile = {
            "thinking": {
                "sampling": out_think_sampling,
                "request": out_think_request
            },
            "non_thinking": {
                "sampling": out_nonthink_sampling,
                "request": out_nonthink_request
            }
        }

        # ── Build client passthrough ──
        client_out = dict(client) if isinstance(client, dict) else {}
        client_out["profile_key"] = effective_key
        client_out["profile"] = final_profile

        profile_json = json.dumps(
            {"model": model, "matched_key": effective_key, "profile": final_profile},
            ensure_ascii=False, indent=2,
        )

        return (
            client_out,
            effective_key,
            profile_json,
        )


NODE_CLASS_MAPPINGS = {"KDX_LLM_Model_Profile": KDX_LLM_Model_Profile}
NODE_DISPLAY_NAME_MAPPINGS = {"KDX_LLM_Model_Profile": "💾 KDX • LLM Model Profile"}