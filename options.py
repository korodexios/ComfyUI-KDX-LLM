"""KDX LLM Client — sampling nodes (Simple + Advanced).

Each parameter has its own enable switch. Disabled parameters are not sent,
keeping model/server defaults intact and avoiding sentinel values.

Simple Sampling: temperature, top_p, top_k, min_p, penalties, max_tokens, seed, stop.
Advanced Sampling: n_ctx, repeat_last_n, MiRoStat, thinking_budget, extra_body.

Both output KDX_LLM_OPTIONS and chain via base_options input.
"""

# ── Simple parameters ─────────────────────────────────────────────────
_SIMPLE_PARAMS = (
    ("temperature", "FLOAT", 0.0, 2.0, 0.05, 0.7, "Randomness. Lower = more deterministic."),
    ("top_p", "FLOAT", 0.0, 1.0, 0.01, 0.95, "Nucleus sampling. 1.0 disables the restriction."),
    ("top_k", "INT", 0, 1000, 1, 40, "Maximum candidate tokens. 0 disables it where supported."),
    ("min_p", "FLOAT", 0.0, 1.0, 0.01, 0.0, "Minimum probability sampling. 0 disables it."),
    ("repeat_penalty", "FLOAT", 0.0, 2.0, 0.01, 1.0, "Repetition penalty. 1.0 means no penalty."),
    ("presence_penalty", "FLOAT", -2.0, 2.0, 0.05, 0.0, "Penalizes tokens that already appeared."),
    ("frequency_penalty", "FLOAT", -2.0, 2.0, 0.05, 0.0, "Penalizes repeated token frequency."),
    ("max_tokens", "INT", 1, 1048576, 1, 4096, "Maximum generated tokens."),
    ("seed", "INT", 0, 2147483647, 1, 0, "Seed for reproducible output where supported."),
)

# ── Advanced parameters ──────────────────────────────────────────────
_ADVANCED_PARAMS = (
    ("n_ctx", "INT", 128, 1048576, 1, 4096, "Context window size (tokens). Set per-request where supported."),
    ("repeat_last_n", "INT", 0, 2048, 1, 64, "Sliding window for repeat penalty (0 = unlimited)."),
    ("thinking_budget", "INT", 0, 32768, 1, 0, "Maximum reasoning tokens for thinking models. 0 = server default."),
)

# ── MiRoStat is a 3-param group ──────────────────────────────────────


class KDX_LLM_Simple_Sampling:
    """Core sampling parameters with individual enable switches.

    Wire into the Chat node's thinking_sampling / non_thinking_sampling input,
    or into the Client node's thinking_sampling / non_thinking_sampling input.
    Chain multiple nodes via base_options — downstream overrides upstream.
    """

    DESCRIPTION = "Generation settings (temperature, top_p, max_tokens, seed, stop…). Only parameters switched ON are sent; OFF keeps the server default. Connect to Chat's thinking_sampling or non_thinking_sampling."

    CATEGORY = "KDX/LLM"
    RETURN_TYPES = ("KDX_LLM_OPTIONS",)
    RETURN_NAMES = ("sampling",)
    FUNCTION = "execute"

    @classmethod
    def INPUT_TYPES(cls):
        required = {}
        for name, typ, lo, hi, step, default, tip in _SIMPLE_PARAMS:
            required[f"{name}_enabled"] = ("BOOLEAN", {
                "default": False,
                "label_on": "ON",
                "label_off": "OFF",
                "tooltip": f"Enable {name}. OFF means this parameter is not sent.",
            })
            cfg = {"default": default, "min": lo, "max": hi, "tooltip": tip}
            if typ == "FLOAT":
                cfg["step"] = step
            required[name] = (typ, cfg)

        # Stop sequences
        required["stop_enabled"] = ("BOOLEAN", {
            "default": False,
            "label_on": "ON",
            "label_off": "OFF",
            "tooltip": "Enable custom stop sequences.",
        })
        required["stop"] = ("STRING", {
            "default": "",
            "multiline": True,
            "tooltip": "Stop sequences, one per line.",
        })

        return {
            "required": required,
            "optional": {
                "base_options": ("KDX_LLM_OPTIONS", {
                    "tooltip": "Upstream sampling values to extend. Enabled values in this node override them.",
                }),
            },
        }

    def execute(self, base_options=None, **values):
        opts = dict(base_options.get("options", {})) if isinstance(base_options, dict) else {}

        for name, typ, _lo, _hi, _step, default, _tip in _SIMPLE_PARAMS:
            if not values.get(f"{name}_enabled", False):
                continue
            value = values.get(name, default)
            value = round(float(value), 4) if typ == "FLOAT" else int(value)
            opts[name] = value

        if values.get("stop_enabled", False):
            stops = [line.strip() for line in (values.get("stop") or "").splitlines() if line.strip()]
            if stops:
                opts["stop"] = stops

        return ({"options": opts},)


# ── Keep the legacy name as an alias ─────────────────────────────────
KDX_LLM_Options_Values = KDX_LLM_Simple_Sampling


class KDX_LLM_Advanced_Sampling:
    """Advanced / provider-specific sampling parameters with enable switches.

    Covers llama.cpp-specific options (MiRoStat, repeat_last_n),
    thinking_budget for reasoning models, and raw JSON override (extra_body).
    Chain via base_options — downstream overrides upstream.
    """

    DESCRIPTION = 'Expert generation settings (MiRoStat, repeat_last_n, thinking_budget, raw JSON). Only parameters switched ON are sent. Chain after Simple Sampling via base_options.'

    CATEGORY = "KDX/LLM"
    RETURN_TYPES = ("KDX_LLM_OPTIONS",)
    RETURN_NAMES = ("sampling",)
    FUNCTION = "execute"

    @classmethod
    def INPUT_TYPES(cls):
        required = {}
        for name, typ, lo, hi, step, default, tip in _ADVANCED_PARAMS:
            required[f"{name}_enabled"] = ("BOOLEAN", {
                "default": False,
                "label_on": "ON",
                "label_off": "OFF",
                "tooltip": f"Enable {name}. OFF means this parameter is not sent.",
            })
            cfg = {"default": default, "min": lo, "max": hi, "tooltip": tip}
            if typ == "FLOAT":
                cfg["step"] = step
            required[name] = (typ, cfg)

        # MiRoStat group
        required["mirostat_enabled"] = ("BOOLEAN", {
            "default": False,
            "label_on": "ON",
            "label_off": "OFF",
            "tooltip": "Enable MiRoStat sampling (llama.cpp). Sets all three MiRoStat params.",
        })
        required["mirostat"] = ("INT", {
            "default": 2, "min": 1, "max": 2,
            "tooltip": "1 = MiRoStat 2.0, 2 = MiRoStat 2.1",
        })
        required["mirostat_tau"] = ("FLOAT", {
            "default": 5.0, "min": 0.0, "max": 10.0, "step": 0.5,
            "tooltip": "Target perplexity. Higher = more diverse.",
        })
        required["mirostat_eta"] = ("FLOAT", {
            "default": 0.1, "min": 0.01, "max": 1.0, "step": 0.01,
            "tooltip": "Learning rate for MiRoStat.",
        })

        # Raw JSON override
        required["extra_body_enabled"] = ("BOOLEAN", {
            "default": False,
            "label_on": "ON",
            "label_off": "OFF",
            "tooltip": "Enable raw JSON payload override.",
        })
        required["extra_body"] = ("STRING", {
            "default": "",
            "multiline": True,
            "tooltip": "Raw JSON merged into the API request payload. Example: {\"chat_template_kwargs\": {\"enable_thinking\": true}}",
        })

        return {
            "required": required,
            "optional": {
                "base_options": ("KDX_LLM_OPTIONS", {
                    "tooltip": "Upstream sampling values to extend.",
                }),
            },
        }

    def execute(self, base_options=None, **values):
        opts = dict(base_options.get("options", {})) if isinstance(base_options, dict) else {}

        for name, typ, _lo, _hi, _step, default, _tip in _ADVANCED_PARAMS:
            if not values.get(f"{name}_enabled", False):
                continue
            value = values.get(name, default)
            value = round(float(value), 4) if typ == "FLOAT" else int(value)
            opts[name] = value

        # MiRoStat — all three together
        if values.get("mirostat_enabled", False):
            opts["mirostat"] = int(values.get("mirostat", 2))
            opts["mirostat_tau"] = round(float(values.get("mirostat_tau", 5.0)), 2)
            opts["mirostat_eta"] = round(float(values.get("mirostat_eta", 0.1)), 2)

        # Raw JSON override
        if values.get("extra_body_enabled", False):
            raw = (values.get("extra_body") or "").strip()
            if raw:
                import json
                try:
                    extra = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"KDX LLM: Invalid JSON in 'extra_body': {exc}") from exc
                if not isinstance(extra, dict):
                    raise ValueError(f"KDX LLM: 'extra_body' must be a JSON object, got {type(extra).__name__}")
                opts.update(extra)

        return ({"options": opts},)


# ── Registration ─────────────────────────────────────────────────────
NODE_CLASS_MAPPINGS = {
    "KDX_LLM_Simple_Sampling": KDX_LLM_Simple_Sampling,
    "KDX_LLM_Advanced_Sampling": KDX_LLM_Advanced_Sampling,
    # Legacy alias
    "KDX_LLM_Options_Values": KDX_LLM_Simple_Sampling,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "KDX_LLM_Simple_Sampling": "🎚️ KDX • LLM Sampling (Simple)",
    "KDX_LLM_Advanced_Sampling": "🔬 KDX • LLM Sampling (Advanced)",
    "KDX_LLM_Options_Values": "🎚️ KDX • LLM Sampling (Simple)",
}
