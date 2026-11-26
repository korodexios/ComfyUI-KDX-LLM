"""KDX LLM — ComfyUI V3 adapter (dual registration, V1 stays untouched).

This module provides the V3 (comfy_api.latest) schema for the nodes, exposed
through ``comfy_entrypoint()``. The V1 ``NODE_CLASS_MAPPINGS`` in __init__.py
is fully preserved — existing workflows keep working.

P1.3 decisions implemented here:
- A: fingerprint_inputs delegates to kdx_core.fingerprint (same hash as V1 IS_CHANGED)
- B: not_idempotent=True on KDX_LLM_Chat only
- C: advanced=True on the advanced block (json_mode stays visible)
- D: force_input=True on link-type inputs (client, sampling, tools, media, image)
- E: KDX_LLM_RESPONSE declared as io.Custom("KDX_LLM_RESPONSE") typed output

The V3 node classes REUSE the V1 logic: execute() delegates to the existing
V1 class's run(). No business logic is duplicated.

Import guard: comfy_api is only available inside a ComfyUI runtime. When it's
absent (unit tests, agent-VM), ``comfy_entrypoint`` is left as None and the
node list empty — V1 registration is unaffected.
"""

import inspect

try:
    from comfy_api.latest import ComfyExtension, io
    _HAS_V3 = True
except Exception:  # pragma: no cover - comfy_api not installed outside ComfyUI
    _HAS_V3 = False
    ComfyExtension = object  # dummy base so the subclass below still constructs
    io = None

from .kdx_core.fingerprint import fingerprint
from . import prompt_store, sampling_store, user_prompt_store
from .chat import KDX_LLM_Chat as _V1Chat, MODEL_PRESETS as _CHAT_PRESETS
from .session_node import KDX_LLM_Session as _V1Session


def _accepted_kwargs(func, kwargs):
    """Filter kwargs to the parameters ``func`` declares (unless it takes **kwargs).

    V1 ``VALIDATE_INPUTS`` usually names only the inputs it validates (ComfyUI
    passes exactly those), while the V3 hook receives every input.
    """
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return kwargs
    params = sig.parameters.values()
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params):
        return kwargs
    return {k: v for k, v in kwargs.items() if k in sig.parameters}


def _build_chat_node():
    """Build the V3 KDX_LLM_Chat schema (only when comfy_api is available)."""

    class KDX_LLM_Chat_V3(io.ComfyNode):
        @classmethod
        def define_schema(cls) -> io.Schema:
            return io.Schema(
                node_id="KDX_LLM_Chat",
                display_name="💬 KDX • LLM Chat (V3)",
                category="KDX/LLM",
                description=_V1Chat.DESCRIPTION,
                not_idempotent=True,  # decision B: only Chat hits network + session state
                is_output_node=False,  # run only when needed downstream (lazy switches stay lazy)
                inputs=[
                    # ── Required ──
                    io.String.Input("prompt", multiline=True,
                                    tooltip="User message. Empty = skip API call (bypass-safe)."),
                    io.Combo.Input("model_preset", options=list(_CHAT_PRESETS.keys()), default="generic",
                                   tooltip="Preset setting defaults for thinking and JSON mode."),
                    # ── Link-type inputs (decision D: link-only slots in V3).
                    #    Custom + Image inputs are inherently link-only in the V3
                    #    API (their Input.__init__ has no force_input param), so the
                    #    "force_input=True" intent is satisfied implicitly. ──
                    io.Custom("KDX_LLM_CLIENT").Input("client", optional=True,
                                                      tooltip="Connection, model, context window and saved profile."),
                    io.Custom("KDX_LLM_OPTIONS").Input("thinking_sampling", optional=True,
                                                       tooltip="Sampling override for Thinking mode."),
                    io.Custom("KDX_LLM_OPTIONS").Input("non_thinking_sampling", optional=True,
                                                       tooltip="Sampling override for Non-thinking mode."),
                    io.Image.Input("image", optional=True,
                                   tooltip="Optional image for multi-modal models."),
                    io.Custom("KDX_LLM_MEDIA").Input("media_settings", optional=True,
                                                     tooltip="Audio/video settings."),
                    io.Custom("KDX_LLM_TOOLS").Input("tools", optional=True,
                                                     tooltip="OpenAI-compatible function-calling tools."),
                    # ── Scalar widgets (NOT force_input) ──
                    io.Combo.Input("thinking", options=["auto", "on", "off"], default="auto",
                                   tooltip="auto = preset default; on/off = force."),
                    io.Combo.Input("reasoning_mode",
                                   options=["", "auto", "low", "medium", "high", "xhigh", "spoon", "einstein", "custom"],
                                   default="", tooltip="Per-model reasoning depth."),
                    io.String.Input("reasoning_custom", default="",
                                    tooltip="Custom reasoning value (used when reasoning_mode = custom)."),
                    io.String.Input("system_prompt", default="", multiline=True,
                                    tooltip="Direct system prompt text."),
                    io.String.Input("system_prompt_profile", default="",
                                    tooltip="Saved system prompt (from System Prompt node)."),
                    io.Boolean.Input("stream", default=True,
                                     tooltip="Streaming responses (recommended)."),
                    io.Combo.Input("media_mode", options=["auto", "none", "image", "audio", "video"],
                                   default="auto", tooltip="How connected media is sent."),
                    io.Boolean.Input("reset_session", default=True,
                                     tooltip="True = new conversation; False = continue (needs a session source)."),
                    # P2.2: connected session socket (overrides the session_id widget).
                    io.Custom("KDX_LLM_SESSION").Input("session", optional=True,
                                                       tooltip="Connected conversation session. Overrides session_id when connected (DAG-safe, branchable)."),
                    io.String.Input("session_id", default="",
                                    tooltip="Conversation ID. Same ID = same history. (Used only when no session socket is connected.)"),
                    io.Int.Input("max_history", default=40, min=2, max=200,
                                 tooltip="Max messages in conversation history."),
                    io.Int.Input("max_prompt_tokens", default=0, min=0, max=1048576,
                                 tooltip="Optional prompt-token budget. 0 disables trimming.", advanced=True),
                    io.Combo.Input("token_counter", options=["heuristic", "tiktoken", "auto"], default="heuristic",
                                   tooltip="Token estimate mode.", advanced=True),
                    io.Combo.Input("json_mode", options=["auto", "on", "off"], default="auto",
                                   tooltip="auto = model preset; on/off = force JSON mode. (visible — decision C)"),
                    # ── Advanced block (advanced=True, decision C) ──
                    io.String.Input("sampling_json_thinking", default="", multiline=True, advanced=True,
                                    tooltip="Thinking sampling as JSON."),
                    io.String.Input("sampling_json_non_thinking", default="", multiline=True, advanced=True,
                                    tooltip="Non-thinking sampling as JSON."),
                    io.String.Input("extra_request_json", default="", multiline=True, advanced=True,
                                    tooltip="Raw JSON merged into the request. Applied last."),
                    io.Boolean.Input("load_before", default=False, advanced=True,
                                     tooltip="Load model before generation."),
                    io.Boolean.Input("unload_after", default=False, advanced=True,
                                     tooltip="Unload model after generation."),
                    io.Int.Input("load_timeout", default=300, min=5, max=1800, advanced=True,
                                 tooltip="Max seconds to wait for model loading."),
                    io.Combo.Input("history_media", options=["latest", "all", "none"], default="latest", advanced=True,
                                   tooltip="Media from earlier turns: latest = only the most recent; all = everything; none = text only."),
                    # New inputs go LAST (positional widgets_values).
                    io.Boolean.Input("llm_enabled", default=True, optional=True, force_input=True,
                                     tooltip="LLM on/off. Not connected or True = LLM runs. False = no LLM call: "
                                             "response = prompt unchanged, other outputs empty, session passes through."),
                    io.String.Input("task_prompt", default="", multiline=True, optional=True, force_input=True,
                                    tooltip="Optional fixed instructions wrapped around the prompt. {} / {prompt} = prompt, "
                                            "{prompt_json} = prompt as JSON string; no placeholder = prompt appended. "
                                            "Not used when llm_enabled = False (response = bare prompt)."),
                ],
                outputs=[
                    io.String.Output("response", tooltip="Clean response text."),
                    io.String.Output("thinking", tooltip="Reasoning/thinking text."),
                    io.String.Output("json", tooltip="Parsed JSON string (JSON mode)."),
                    io.String.Output("raw", tooltip="Full normalized API response JSON."),
                    io.String.Output("model_used", tooltip="Actual model name reported by the server."),
                    io.String.Output("profile_key", tooltip="Matched persistent model profile."),
                    io.String.Output("profile_json", tooltip="Matched profile as JSON."),
                    io.String.Output("request_info", tooltip="Effective request metadata."),
                    # decision E: typed custom output (V3) — V1 uses "ANY"
                    io.Custom("KDX_LLM_RESPONSE").Output("response_obj",
                                                         tooltip="Structured response object (content, reasoning, usage, tool_calls)."),
                    # P2.2: updated conversation session for multi-turn chaining.
                    io.Custom("KDX_LLM_SESSION").Output("session",
                                                        tooltip="Updated conversation session for chaining into the next Chat node."),
                    io.String.Output("tool_calls",
                                     tooltip="Tool calls returned by the model as JSON array."),
                ],
            )

        @classmethod
        def execute(cls, **kwargs) -> "io.NodeOutput":
            # Reuse V1 logic verbatim — no duplication.
            out = _V1Chat().run(**kwargs)
            return io.NodeOutput(*out)

        @classmethod
        def fingerprint_inputs(cls, **kwargs) -> str:
            # decision A: same canonical hash as V1 IS_CHANGED.
            return fingerprint({
                **kwargs,
                "profiles_mtime": sampling_store.mtime(),
                "prompts_mtime": prompt_store.mtime(),
                "user_prompts_mtime": user_prompt_store.mtime(),
            })

    return KDX_LLM_Chat_V3


def _build_session_node():
    """Build the V3 KDX_LLM_Session schema (P2.3). Delegates to the V1 node."""

    class KDX_LLM_Session_V3(io.ComfyNode):
        @classmethod
        def define_schema(cls) -> io.Schema:
            return io.Schema(
                node_id="KDX_LLM_Session",
                display_name="🔄 KDX • LLM Session (V3)",
                category="KDX/LLM",
                description=_V1Session.DESCRIPTION,
                inputs=[
                    io.Combo.Input("action",
                                   options=["new", "passthrough", "reset", "import_json", "save", "load"],
                                   default="new",
                                   tooltip="new = fresh session; passthrough = forward; reset = clear; import_json = load JSON; save/load = persisted named session."),
                    io.Custom("KDX_LLM_SESSION").Input("session", optional=True,
                                                       tooltip="Optional upstream session to inspect, reset or forward."),
                    io.String.Input("custom_id", default="",
                                    tooltip="Optional custom session ID. Empty = auto-generated."),
                    io.String.Input("import_json", default="", multiline=True,
                                    tooltip="JSON messages for action=import_json."),
                    io.String.Input("session_name", default="",
                                    tooltip="Named session key for action=save or action=load."),
                ],
                outputs=[
                    io.Custom("KDX_LLM_SESSION").Output("session",
                                                        tooltip="Resulting conversation session object."),
                    io.String.Output("messages_json",
                                     tooltip="Full conversation history as JSON."),
                    io.Int.Output("turn_count",
                                  tooltip="Number of completed user/assistant turns."),
                ],
            )

        @classmethod
        def fingerprint_inputs(cls, **kwargs) -> float:
            # Save/load mutate hidden on-disk session state; keep this node live.
            return float("nan")

        @classmethod
        def execute(cls, **kwargs) -> "io.NodeOutput":
            # Reuse V1 logic verbatim — no duplication.
            out = _V1Session().execute(**kwargs)
            return io.NodeOutput(*out)

    return KDX_LLM_Session_V3


_GENERIC_SKIP = {"KDX_LLM_Chat", "KDX_LLM_Session", "KDX_LLM_Options_Values"}
_NOT_IDEMPOTENT = {
    "KDX_LLM_Client",
    "KDX_LLM_Diagnostics",
    "KDX_LLM_System_Prompt",
    "KDX_LLM_User_Prompt",
    "KDX_LLM_Quick_Presets",
}


def _v1_node_specs():
    """Collect V1 node classes that can be wrapped generically in V3."""
    from . import (
        client,
        options,
        media_settings,
        tools,
        diagnostics,
        stats,
        system_prompt_node,
        user_prompt_node,
        quick_sampling_node,
        response_formatter,
        model_profile_node,
        json_extract_node,
        json_fields_node,
        prompt_template_node,
    )

    modules = [
        client, options, media_settings, tools, diagnostics, stats,
        system_prompt_node, user_prompt_node, quick_sampling_node,
        response_formatter, model_profile_node, json_extract_node,
        json_fields_node, prompt_template_node,
    ]
    specs = []
    for mod in modules:
        mappings = getattr(mod, "NODE_CLASS_MAPPINGS", {}) or {}
        displays = getattr(mod, "NODE_DISPLAY_NAME_MAPPINGS", {}) or {}
        for node_id, cls in mappings.items():
            if node_id in _GENERIC_SKIP:
                continue
            specs.append((node_id, displays.get(node_id, node_id), cls))
    return specs


def _input_from_v1(name: str, spec, optional: bool = False):
    if isinstance(spec, tuple) and spec:
        typ = spec[0]
        opts = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
    else:
        typ = spec
        opts = {}

    tooltip = opts.get("tooltip", "")
    advanced = bool(opts.get("advanced", False))
    kwargs = {"tooltip": tooltip, "advanced": advanced}
    if optional:
        kwargs["optional"] = True

    if isinstance(typ, list):
        return io.Combo.Input(name, options=typ, default=opts.get("default", typ[0] if typ else ""), **kwargs)

    if typ == "STRING":
        return io.String.Input(name, default=opts.get("default", ""), multiline=bool(opts.get("multiline", False)), **kwargs)

    if typ == "INT":
        return io.Int.Input(
            name,
            default=int(opts.get("default", 0)),
            min=int(opts.get("min", -1000000)),
            max=int(opts.get("max", 1000000)),
            step=int(opts.get("step", 1)),
            **kwargs,
        )

    if typ == "FLOAT":
        return io.Float.Input(
            name,
            default=float(opts.get("default", 0.0)),
            min=float(opts.get("min", -1000000.0)),
            max=float(opts.get("max", 1000000.0)),
            step=float(opts.get("step", 0.01)),
            **kwargs,
        )

    if typ == "BOOLEAN":
        return io.Boolean.Input(name, default=bool(opts.get("default", False)), **kwargs)

    if typ == "IMAGE":
        return io.Image.Input(name, **kwargs)

    if typ == "AUDIO":
        audio_cls = getattr(io, "Audio", None)
        if audio_cls is not None:
            return audio_cls.Input(name, **kwargs)
        return io.Custom("AUDIO").Input(name, **kwargs)

    if isinstance(typ, str) and typ not in ("STRING", "INT", "FLOAT", "BOOLEAN", "IMAGE", "AUDIO", "ANY"):
        return io.Custom(typ).Input(name, **kwargs)

    return io.String.Input(name, default=opts.get("default", ""), **kwargs)


def _output_from_v1(name: str, typ: str):
    if typ == "STRING":
        return io.String.Output(name)
    if typ == "INT":
        return io.Int.Output(name)
    if typ == "FLOAT":
        return io.Float.Output(name)
    if typ == "BOOLEAN":
        return io.Boolean.Output(name)
    if typ == "IMAGE":
        return io.Image.Output(name)
    if typ == "AUDIO":
        audio_cls = getattr(io, "Audio", None)
        if audio_cls is not None:
            return audio_cls.Output(name)
        return io.Custom("AUDIO").Output(name)
    if typ == "ANY":
        return io.Custom("ANY").Output(name)
    return io.Custom(typ).Output(name)


def _build_generic_node(node_id: str, display_name: str, v1_class):
    try:
        raw = v1_class.INPUT_TYPES()
    except Exception:
        return None

    inputs = []
    for name, spec in (raw.get("required") or {}).items():
        inputs.append(_input_from_v1(name, spec, optional=False))
    for name, spec in (raw.get("optional") or {}).items():
        inputs.append(_input_from_v1(name, spec, optional=True))

    return_types = tuple(getattr(v1_class, "RETURN_TYPES", ()) or ())
    return_names = tuple(getattr(v1_class, "RETURN_NAMES", return_types) or return_types)
    outputs = [
        _output_from_v1(name, typ)
        for name, typ in zip(return_names, return_types)
    ]

    class GenericV3Node(io.ComfyNode):
        @classmethod
        def define_schema(cls) -> "io.Schema":
            return io.Schema(
                node_id=node_id,
                display_name=display_name,
                category=getattr(v1_class, "CATEGORY", "KDX/LLM"),
                description=getattr(v1_class, "DESCRIPTION", "") or f"V3 adapter for {node_id}.",
                not_idempotent=node_id in _NOT_IDEMPOTENT,
                inputs=inputs,
                outputs=outputs,
            )

        @classmethod
        def fingerprint_inputs(cls, **kwargs):
            v1_is_changed = getattr(v1_class, "IS_CHANGED", None)
            if v1_is_changed is not None:
                try:
                    return v1_is_changed(**kwargs)
                except Exception:
                    pass
            if node_id in _NOT_IDEMPOTENT:
                import time
                return time.time()
            return None

        @classmethod
        def validate_inputs(cls, **kwargs):
            v1_validate = getattr(v1_class, "VALIDATE_INPUTS", None)
            if v1_validate is not None:
                try:
                    return v1_validate(**_accepted_kwargs(v1_validate, kwargs))
                except Exception as exc:
                    return str(exc)
            return True

        @classmethod
        def execute(cls, **kwargs) -> "io.NodeOutput":
            function_name = getattr(v1_class, "FUNCTION", "run")
            out = getattr(v1_class(), function_name)(**kwargs)
            return io.NodeOutput(*out)

    return GenericV3Node


class KDXLLMV3Extension(ComfyExtension):
    """ComfyExtension returning the V3 node list.

    Must subclass the REAL comfy_api ComfyExtension (not a plain object) —
    ComfyUI's loader checks ``isinstance(result, ComfyExtension)`` and skips
    the pack otherwise. When comfy_api is unavailable the base is a dummy
    object so the class still constructs (and comfy_entrypoint returns None).
    """

    def __init__(self):
        super().__init__() if _HAS_V3 else None
        self._nodes = []
        if _HAS_V3:
            self._nodes.append(_build_chat_node())
            self._nodes.append(_build_session_node())

            for node_id, display_name, v1_class in _v1_node_specs():
                try:
                    node_cls = _build_generic_node(node_id, display_name, v1_class)
                    if node_cls is not None:
                        # Validate early; if a node type is unsupported by this
                        # comfy_api version, skip only that node instead of
                        # breaking the whole V3 extension.
                        node_cls.define_schema()
                        self._nodes.append(node_cls)
                except Exception:
                    pass

    async def get_node_list(self):
        return self._nodes


def comfy_entrypoint():
    """V3 entrypoint. Returns None when comfy_api is unavailable (V1-only env)."""
    if not _HAS_V3:
        return None
    return KDXLLMV3Extension()


__all__ = ["comfy_entrypoint", "KDXLLMV3Extension"]
