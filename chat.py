"""KDX LLM Chat — simple OpenAI-compatible Chat Completions node."""

import json
import time

from ._http import LLMClient
from .media import build_user_content
from .postprocess import parse_response
from .kdx_core.request_builder import build_chat_payload
from .kdx_core.context import (
    HISTORY_MEDIA_MODES,
    estimate_messages_tokens,
    has_media,
    strip_history_media,
    trim_messages,
)
from .kdx_core.response import KDXLLMResponse
from .kdx_core.fingerprint import build_fingerprint_key, canonical_hash
from .kdx_core.session import KDXLLMSession
from .kdx_core.task_prompt import apply_task_prompt
from . import sampling_store
from . import prompt_store
from . import user_prompt_store
from . import session as legacy_session

# Model presets — set defaults for thinking/json_mode
MODEL_PRESETS = {
    "generic": {"thinking": False, "json_mode": False},
    "qwen_thinking": {"thinking": True, "json_mode": False},
    "qwen_json": {"thinking": True, "json_mode": True},
    "deepseek": {"thinking": True, "json_mode": False},
}


class KDX_LLM_Chat:
    DESCRIPTION = 'Sends your prompt to the LLM and returns the answer. Main outputs: response (answer text), thinking (reasoning), json (answer parsed as JSON), session (connect to the next Chat to continue the conversation). An empty prompt skips the call.'

    CATEGORY = "KDX/LLM"
    RETURN_TYPES = (
        "STRING", "STRING", "STRING", "STRING", "STRING", "STRING", "STRING", "STRING",
        "ANY", "KDX_LLM_SESSION", "STRING",
    )
    RETURN_NAMES = (
        "response", "thinking", "json", "raw", "model_used", "profile_key", "profile_json", "request_info",
        "response_obj", "session", "tool_calls",
    )
    OUTPUT_TOOLTIPS = (
        "Clean response text.",
        "Reasoning/thinking text when available.",
        "Parsed JSON string when JSON mode is enabled.",
        "Full normalized API response JSON.",
        "Actual model name reported by the server.",
        "Matched persistent model profile.",
        "Matched profile as JSON.",
        "Effective request metadata for automation.",
        "Structured response object (content, reasoning, json, tool_calls, usage, timings).",
        "Updated conversation session (KDX_LLM_SESSION) for multi-turn chaining.",
        "Tool calls returned by the model as JSON array.",
    )
    FUNCTION = "execute_node"
    # Deliberately NOT an output node: ComfyUI always executes output nodes,
    # so a Chat behind a lazy Switch (e.g. "enhance prompt: off") would still
    # call the LLM every run. Chat runs only when something downstream needs
    # its output; the answer is still shown in the node (UI output). A graph
    # needs some output node (Preview as Text, Save Image, ...) to run.
    OUTPUT_NODE = False
    FALLBACK_URL = "http://127.0.0.1:8080"

    @classmethod
    def INPUT_TYPES(cls):
        presets = list(MODEL_PRESETS.keys())
        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "User message. Empty = skip API call (bypass-safe, saves GPU time).",
                }),
                "model_preset": (presets, {
                    "default": "generic",
                    "tooltip": "Preset that sets defaults for thinking and JSON mode. generic = standard chat; qwen_thinking = reasoning models; qwen_json = thinking + JSON output; deepseek = DeepSeek reasoning.",
                }),
            },
            "optional": {
                "client": ("KDX_LLM_CLIENT", {"tooltip": "Connection, model, context window and saved model profile."}),
                "thinking_sampling": ("KDX_LLM_OPTIONS", {"tooltip": "Sampling override for Thinking mode (from Simple/Advanced/Quick Presets node). If empty, the Client saved profile is used."}),
                "non_thinking_sampling": ("KDX_LLM_OPTIONS", {"tooltip": "Sampling override for Non-thinking mode (from Simple/Advanced/Quick Presets node). If empty, the Client saved profile is used."}),
                "thinking": (["auto", "on", "off"], {
                    "default": "auto",
                    "tooltip": "auto = use model preset default; on = force Thinking mode; off = force Non-thinking mode (overrides preset).",
                }),
                "reasoning_mode": (["", "auto", "low", "medium", "high", "xhigh", "spoon", "einstein", "custom"], {
                    "default": "",
                    "tooltip": "Per-model reasoning depth. Leave empty for default. Select 'custom' to enter a custom value below (or use the field in the Model Profile node).",
                }),
                "reasoning_custom": ("STRING", {
                    "default": "",
                    "tooltip": "Custom reasoning mode (only used when reasoning_mode = custom). Enter any value your model supports.",
                }),
                "system_prompt": ("STRING", {"default": "", "multiline": True, "tooltip": "Direct system prompt text. A System Prompt node can be connected instead for saved profiles."}),
                "system_prompt_profile": ("STRING", {"default": "", "multiline": False, "tooltip": "Saved system prompt text (from System Prompt node)."}),
                "stream": ("BOOLEAN", {"default": True, "tooltip": "Streaming responses (recommended for long outputs)."}),
                "media_mode": (["auto", "none", "image", "audio", "video"], {"default": "auto", "tooltip": "How connected media is sent. auto = detect (image > video > audio > none)."}),
                "image": ("IMAGE", {"tooltip": "Optional image(s) for vision models. A batch sends every image (up to 16)."}),
                "media_settings": ("KDX_LLM_MEDIA", {"tooltip": "Audio/video settings (from Media Settings node)."}),
                "reset_session": ("BOOLEAN", {"default": True, "tooltip": "True = new conversation. False = continue existing conversation (requires a session source)."}),
                "session": ("KDX_LLM_SESSION", {"tooltip": "Connected conversation session (from a Chat node's session output or a Session node). When connected, it OVERRIDES the session_id text field — history flows directly from the object (DAG-safe, branchable). Leave unconnected to use the legacy session_id store."}),
                "session_id": ("STRING", {"default": "", "tooltip": "Conversation ID. Same ID = same conversation history across multiple Chat nodes. Leave empty for stateless mode. Use the 🎲 button to generate a unique ID. (Used only when no KDX_LLM_SESSION socket is connected.)"}),
                "max_history": ("INT", {"default": 40, "min": 2, "max": 200, "tooltip": "Max messages stored in conversation history (pairs of user+assistant). Used for connected session objects and legacy session_id."}),
                "max_prompt_tokens": ("INT", {"default": 0, "min": 0, "max": 1048576, "tooltip": "Optional prompt-token budget. 0 disables trimming. Oldest non-system history is removed first; system prompt and current user message are preserved."}),
                "token_counter": (["heuristic", "tiktoken", "auto"], {"default": "heuristic", "tooltip": "Token estimate mode: heuristic = dependency-free chars/4; tiktoken = use tiktoken if installed; auto = tiktoken if available, otherwise heuristic."}),
                "tools": ("KDX_LLM_TOOLS", {"tooltip": "OpenAI-compatible function-calling tools (from Tool node)."}),
                # ── Advanced (hidden by default via JS) ──
                "sampling_json_thinking": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "Thinking sampling as JSON (alternative to Sampling node). Example: {\"temperature\": 1.0, \"top_p\": 0.95}. Applied after node-based sampling.",
                }),
                "sampling_json_non_thinking": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "Non-thinking sampling as JSON. Example: {\"temperature\": 0.7, \"top_p\": 0.8}. Applied after node-based sampling.",
                }),
                "extra_request_json": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "tooltip": "Raw JSON merged into the API request payload. Example: {\"repetition_penalty\": 1.5}. Applied last — overrides everything.",
                }),
                "json_mode": (["auto", "on", "off"], {"default": "auto", "tooltip": "auto = use model preset; on = force JSON object response; off = disable JSON mode even if preset enables it."}),
                "load_before": ("BOOLEAN", {"default": False, "tooltip": "Load the model before generation (useful for models not currently in RAM)."}),
                "unload_after": ("BOOLEAN", {"default": False, "tooltip": "Unload the model after generation to free VRAM."}),
                "load_timeout": ("INT", {"default": 300, "min": 5, "max": 1800, "tooltip": "Max seconds to wait for model loading."}),
                # New widgets go LAST so widgets_values of saved workflows keep their positions.
                "history_media": (list(HISTORY_MEDIA_MODES), {"default": "latest", "tooltip": "Images/audio from earlier turns in the conversation: latest = re-send only the most recent one (none if this message has its own); all = re-send everything (slow, many tokens); none = never re-send, keep only the text."}),
                # A visible socket (not a widget): a widget's input dot only appears while a wire is dragged onto it.
                "llm_enabled": ("BOOLEAN", {"default": True, "forceInput": True, "tooltip": "LLM on/off switch. Not connected or True = the LLM runs. False = no LLM call (no model load/unload): the response output is the prompt unchanged, other outputs stay empty, the session passes through. Connect any boolean, e.g. llm_enabled of KDX Wildcard Studio or a Boolean node."}),
                "task_prompt": ("STRING", {"default": "", "multiline": True, "forceInput": True, "tooltip": "Optional fixed instructions wrapped around the prompt (e.g. a prompt-enhancer task prompt). {} or {prompt} = the prompt goes there, {prompt_json} = the prompt as a JSON string; with a placeholder {{ and }} mean literal braces (str.format rules). No placeholder = the prompt is added after a blank line. Used only when the LLM runs: with llm_enabled = False the response is the bare prompt, without this text."}),
            },
            "hidden": {"unique_id": "UNIQUE_ID"},
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        # Single source of truth — same canonical hash as V3 fingerprint_inputs.
        # mtime() calls are resolved here and stored in the key by the builder.
        return canonical_hash(build_fingerprint_key({
            **kwargs,
            "profiles_mtime": sampling_store.mtime(),
            "prompts_mtime": prompt_store.mtime(),
            "user_prompts_mtime": user_prompt_store.mtime(),
        }))

    def run(
        self,
        prompt="",
        model_preset="generic",
        client=None,
        thinking_sampling=None,
        non_thinking_sampling=None,
        sampling_json_thinking="",
        sampling_json_non_thinking="",
        extra_request_json="",
        thinking="auto",
        reasoning_mode="auto",
        reasoning_custom="",
        system_prompt="",
        system_prompt_profile="",
        json_mode="auto",
        stream=True,
        media_mode="auto",
        image=None,
        media_settings=None,
        load_before=False,
        unload_after=False,
        load_timeout=300,
        reset_session=True,
        session=None,
        session_id="",
        max_history=40,
        max_prompt_tokens=0,
        token_counter="heuristic",
        history_media="latest",
        tools=None,
        llm_enabled=True,
        task_prompt="",
        _progress=None,
    ):
        llm_off = llm_enabled is False
        if llm_off or not prompt or not prompt.strip():
            # Bypass / LLM switched off: no API call, no model load/unload. The
            # response slot carries the prompt unchanged when the LLM is off
            # (empty when the prompt is empty); everything else stays neutral.
            # An incoming session object is preserved so the chain survives.
            if isinstance(session, KDXLLMSession):
                fallback_session = session
            elif isinstance(session, dict):
                fallback_session = KDXLLMSession.from_dict(session)
            else:
                fallback_session = KDXLLMSession(session_id=session_id or "")
            text = (prompt or "") if llm_off else ""
            return (text, "", "", "", "", "", "", "", KDXLLMResponse().to_dict(), fallback_session, "[]")

        # Apply model preset defaults (user inputs override preset)
        preset = MODEL_PRESETS.get(model_preset, MODEL_PRESETS["generic"])
        # thinking: "auto" = use preset, "on" = force thinking, "off" = force non-thinking
        if thinking == "off":
            thinking_on = False
        elif thinking == "on":
            thinking_on = True
        else:  # "auto" — use preset default
            thinking_on = preset["thinking"]
        # json_mode: tri-state with backward compatibility for old boolean widgets.
        if json_mode is True or json_mode == "on":
            json_on = True
        elif json_mode is False or json_mode == "off":
            json_on = False
        else:
            json_on = preset["json_mode"]

        c = client if isinstance(client, dict) else {}
        base_url = c.get("url", self.FALLBACK_URL)
        model = c.get("model", "")
        api_key = c.get("api_key", "")
        api_key_env = c.get("api_key_env", "KDX_LLM_API_KEY")
        timeout = c.get("timeout", 300)
        max_retries = c.get("max_retries", 2)
        context_length = c.get("context_length", 4096)
        provider = c.get("provider", "auto")

        llm = LLMClient(base_url, api_key=api_key, api_key_env=api_key_env, timeout=timeout, max_retries=max_retries, provider=provider)

        effective_provider = provider
        if effective_provider == "auto":
            try:
                detected = llm.detect_server_type()
                effective_provider = detected.get("type", effective_provider)
            except Exception:
                pass

        profile_key = c.get("profile_key") or None
        profile = c.get("profile") if isinstance(c.get("profile"), dict) else {}
        if model and not profile:
            profile_key, profile = sampling_store.lookup(model)

        # Determine mode first (selects profile mode + sampling node)
        mode = "thinking" if bool(thinking_on) else "non_thinking"
        mode_profile = profile.get(mode, {}) if isinstance(profile, dict) else {}
        profile_request = dict(mode_profile.get("request", {})) if isinstance(mode_profile.get("request"), dict) else {}

        # A connected Sampling node is an explicit workflow override.
        override_node = thinking_sampling if thinking_on else non_thinking_sampling
        override_sampling = dict(override_node.get("options", {})) if isinstance(override_node, dict) else {}

        # JSON string overrides (alternative to Sampling nodes) — validated here
        json_override = sampling_json_thinking if thinking_on else sampling_json_non_thinking
        json_field_name = "sampling_json_thinking" if thinking_on else "sampling_json_non_thinking"
        json_sampling = None
        if json_override and json_override.strip():
            try:
                json_sampling = json.loads(json_override.strip())
            except json.JSONDecodeError as exc:
                raise ValueError(f"KDX LLM: Invalid JSON in '{json_field_name}': {exc}") from exc
            if not isinstance(json_sampling, dict):
                raise ValueError(f"KDX LLM: '{json_field_name}' must be a JSON object, got {type(json_sampling).__name__}")

        # Generic JSON override — validated here, applied last by builder
        extra = None
        if extra_request_json and extra_request_json.strip():
            try:
                extra = json.loads(extra_request_json.strip())
            except json.JSONDecodeError as exc:
                raise ValueError(f"KDX LLM: Invalid JSON in 'extra_request_json': {exc}") from exc
            if not isinstance(extra, dict):
                raise ValueError(f"KDX LLM: 'extra_request_json' must be a JSON object, got {type(extra).__name__}")

        messages = []
        sys_text = (system_prompt_profile or system_prompt or "").strip()
        if sys_text:
            messages.append({"role": "system", "content": sys_text})

        # ── P2.2: resolve the session source (connected socket wins) ──
        # `sess` is the KDXLLMSession used to build the request; `use_session_obj`
        # is True when a KDX_LLM_SESSION socket was connected (object path),
        # False when falling back to the legacy in-memory session_id store.
        use_session_obj = False
        sess = None
        sid = ""
        if session is not None:
            # Connected KDX_LLM_SESSION socket has priority over the widget.
            if isinstance(session, KDXLLMSession):
                sess = session
            elif isinstance(session, dict):
                sess = KDXLLMSession.from_dict(session)
            else:
                sess = KDXLLMSession(session_id=session_id or legacy_session.new_session_id())
            if reset_session:
                sess = sess.reset()
            sid = sess.session_id
            history = sess.messages_for_api()
            use_session_obj = True
        else:
            # Legacy fallback: in-memory store keyed by the session_id string.
            sid = session_id.strip() if session_id else ""
            history = [dict(m) for m in legacy_session.get_session(sid)] if sid and not reset_session else []

        video = audio = None
        v_frame_step, v_max_frames, v_max_size = 1, 60, 512
        a_max_seconds = 30.0
        v_sampling_mode = "uniform"
        v_start_frames = v_end_frames = 0
        if isinstance(media_settings, dict):
            video = media_settings.get("video")
            audio = media_settings.get("audio")
            v_frame_step = media_settings.get("video_frame_step", 1)
            v_max_frames = media_settings.get("video_max_frames", 60)
            v_max_size = media_settings.get("video_max_size", 512)
            a_max_seconds = media_settings.get("audio_max_seconds", 30.0)
            v_sampling_mode = media_settings.get("video_sampling_mode", "uniform")
            v_start_frames = media_settings.get("video_start_frames", 0)
            v_end_frames = media_settings.get("video_end_frames", 0)

        selected_media_mode = media_mode
        if selected_media_mode == "auto":
            selected_media_mode = "image" if image is not None else "video" if video is not None else "audio" if audio is not None else "none"

        # The task prompt wraps the prompt only for the LLM; the bypass above
        # returns the bare prompt, so llm_enabled = False never leaks it.
        user_text = apply_task_prompt(task_prompt, prompt.strip())
        user_content = build_user_content(
            prompt=user_text, image=image, audio=audio, video=video,
            media_mode=selected_media_mode,
            video_frame_step=v_frame_step, video_max_frames=v_max_frames, video_max_size=v_max_size,
            audio_max_seconds=a_max_seconds, video_sampling_mode=v_sampling_mode,
            video_start_frame=v_start_frames, video_end_frame=v_end_frames,
        )
        messages.extend(strip_history_media(history, history_media, current_has_media=has_media(user_content)))
        messages.append({"role": "user", "content": user_content})

        try:
            prompt_budget = int(max_prompt_tokens or 0)
        except (TypeError, ValueError):
            prompt_budget = 0
        if prompt_budget > 0:
            messages = trim_messages(messages, prompt_budget, token_counter)
        prompt_token_estimate = estimate_messages_tokens(messages, token_counter)

        # Build payload + effective sampling via the core builder (single source of truth)
        payload, request_sampling = build_chat_payload(
            model=model,
            messages=messages,
            stream=stream,
            thinking_on=thinking_on,
            profile=profile,
            sampling_override=override_sampling,
            sampling_json_override=json_sampling,
            extra_request_json=extra,
            reasoning_mode=reasoning_mode,
            reasoning_custom=reasoning_custom,
            context_length=context_length,
            json_mode=json_on,
            tools=tools,
            provider=effective_provider,
            send_thinking_flag=thinking in ("on", "off") or model_preset != "generic",
        )

        # P2.2: reset only applies to the legacy store (object path already
        # reset `sess` above when reset_session was True).
        if not use_session_obj and sid and reset_session:
            legacy_session.reset_session(sid)

        if load_before and model:
            load_result = llm.load_model(model, wait=True, wait_timeout=int(load_timeout))
            if load_result.get("status") not in {"ok", "unsupported"}:
                raise RuntimeError(f"KDX LLM: model load failed: {load_result.get('detail', load_result)}")

        unload_result = None
        try:
            t_start = time.time()
            response = llm.chat(payload, on_progress=_progress) if _progress else llm.chat(payload)
            elapsed = time.time() - t_start
        finally:
            # Free VRAM even when generation failed or was cancelled.
            if unload_after and model:
                try:
                    unload_result = llm.unload_model(model)
                except Exception as exc:  # never mask the original error
                    unload_result = {"status": "failed", "detail": str(exc)}
        result = parse_response(response, json_mode=json_on, elapsed_time=elapsed)
        if unload_result and unload_result.get("status") not in {"ok", "unsupported"}:
            result.setdefault("lifecycle", {})["unload"] = unload_result

        # P2.2: build the updated session for the 10th output.
        # - Object path: append to the KDXLLMSession (immutable copy).
        # - Legacy path: append to the in-memory store, then BRIDGE it into a
        #   KDXLLMSession so a legacy widget-driven Chat 1 can still feed its
        #   session output into a Chat 2 socket.
        if use_session_obj:
            assert sess is not None  # use_session_obj is only True on the object path
            updated_session = sess.add_exchange(user_content, result["response"], max_messages=max_history)
        else:
            if sid:
                legacy_session.add_exchange(sid, user_content, result["response"], max_messages=max_history)
                updated_session = KDXLLMSession(
                    session_id=sid,
                    messages=[dict(m) for m in legacy_session.get_session(sid)],
                )
            else:
                # Stateless Chat (no session socket, no session_id): still hand
                # this exchange downstream, so "Chat 1 session -> Chat 2 session"
                # continues the conversation without any extra setup.
                updated_session = KDXLLMSession(session_id="").add_exchange(
                    user_content, result["response"], max_messages=max_history,
                )

        request_info = {
            "model": model,
            "provider": provider,
            "effective_provider": effective_provider,
            "thinking": bool(thinking_on),
            "mode": mode,
            "profile_key": profile_key or "",
            "json_mode": bool(json_on),
            "stream": bool(stream),
            "media_mode": selected_media_mode,
            "sampling": request_sampling,
            "request_overrides": profile_request,
            "prompt_token_estimate": prompt_token_estimate,
            "max_prompt_tokens": prompt_budget,
            "token_counter": token_counter,
            "task_prompt": bool(isinstance(task_prompt, str) and task_prompt.strip()),
            "tools": [
                (tool.get("function") or {}).get("name", "")
                for tool in (tools or {}).get("tools", []) if isinstance(tool, dict)
            ],
        }
        profile_info = {"model": model, "matched_key": profile_key, "profile": profile}
        json_str = json.dumps(result["json"], ensure_ascii=False) if result["json"] is not None else ""

        # Structured response object (9th output, "ANY" in V1 / custom type in V3)
        response_obj = KDXLLMResponse.from_parsed(
            result,
            raw_response=response,
            metadata={
                "profile_key": profile_key or "",
                "mode": mode,
                "json_mode": bool(json_on),
                "media_mode": selected_media_mode,
                "request_info": request_info,
            },
        ).to_dict()

        return (
            result["response"], result["thinking"], json_str, result["raw"], result["model_used"],
            profile_key or "", json.dumps(profile_info, ensure_ascii=False, indent=2),
            json.dumps(request_info, ensure_ascii=False, indent=2),
            response_obj,
            updated_session,
            json.dumps(result.get("tool_calls", []), ensure_ascii=False, indent=2),
        )


    def execute_node(self, unique_id=None, **kwargs):
        """ComfyUI entry point: run() plus the answer shown inside the node.

        While a streamed answer arrives, the partial text is pushed to the
        editor (event ``kdx_llm.stream``); the final text is returned as UI
        output so it also survives cache hits and page reloads.
        """
        llm_off = kwargs.get("llm_enabled") is False
        progress = _stream_preview(unique_id) if kwargs.get("stream", True) and not llm_off else None
        out = self.run(**kwargs, _progress=progress)
        ui = {
            "kdx_response": [out[0]],
            "kdx_thinking": [out[1][-4000:] if out[1] else ""],
            "kdx_llm_off": [llm_off],
        }
        return {"ui": ui, "result": out}


_PREVIEW_INTERVAL = 0.25
_PREVIEW_MAX_CHARS = 20000


def _stream_preview(node_id):
    """Throttled sender for live answer previews; None outside ComfyUI."""
    if node_id is None:
        return None
    try:
        from server import PromptServer
        server = PromptServer.instance
    except Exception:
        return None
    if server is None:
        return None
    last = [0.0]

    def send(content, reasoning):
        now = time.time()
        if now - last[0] < _PREVIEW_INTERVAL:
            return
        last[0] = now
        server.send_sync("kdx_llm.stream", {
            "node": str(node_id),
            "text": (content or "")[-_PREVIEW_MAX_CHARS:],
            "thinking": (reasoning or "")[-4000:],
        })

    return send


NODE_CLASS_MAPPINGS = {"KDX_LLM_Chat": KDX_LLM_Chat}
NODE_DISPLAY_NAME_MAPPINGS = {"KDX_LLM_Chat": "💬 KDX • LLM Chat"}
