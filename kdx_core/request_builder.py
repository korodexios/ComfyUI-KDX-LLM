"""KDX Core — Payload and sampling builder.

Extracts the payload/sampling merge logic out of chat.py into a pure,
unit-testable function. No ComfyUI imports.

Merge priority (later wins):
    1. profile sampling / request
    2. connected Sampling node (thinking_sampling / non_thinking_sampling)
    3. JSON string override (sampling_json_thinking / sampling_json_non_thinking)
    4. extra_request_json (absolute priority — applied last)

reasoning_mode / chat_template_kwargs handling (Qwen i-prefix convention)
lives here too.
"""

from typing import Any, Dict, Optional, Tuple

CONTROL_REQUEST_KEYS = {"qwen_i_prefix"}


def _is_llama_provider(provider: str) -> bool:
    provider = (provider or "").strip().lower()
    return provider in ("llama_cpp", "llama_cpp_router", "llamacpp", "llama.cpp")


def _should_use_qwen_i_prefix(model: str, provider: str, profile_request: Dict[str, Any], thinking_on: bool) -> bool:
    """Apply Qwen llama.cpp i-prefix convention only where it is expected."""
    if thinking_on:
        return False

    flag = profile_request.get("qwen_i_prefix") if isinstance(profile_request, dict) else None
    if flag is False:
        return False
    if flag is True:
        return True

    provider = (provider or "").strip().lower()
    if provider in ("vllm", "ollama", "generic"):
        return False

    return "qwen" in (model or "").lower()


def build_chat_payload(
    model: str,
    messages: list,
    stream: bool,
    thinking_on: bool,
    profile: Optional[Dict[str, Any]] = None,
    sampling_override: Optional[Dict[str, Any]] = None,
    sampling_json_override: Optional[Dict[str, Any]] = None,
    extra_request_json: Optional[Dict[str, Any]] = None,
    reasoning_mode: str = "",
    reasoning_custom: str = "",
    context_length: int = 4096,
    json_mode: bool = False,
    tools: Optional[Dict[str, Any]] = None,
    provider: str = "auto",
    send_thinking_flag: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Build the final API payload and effective sampling metadata.

    Args:
        model: model id sent to the server.
        messages: full OpenAI-style message list (system + history + user).
        stream: streaming flag.
        thinking_on: whether thinking mode is active (selects profile mode).
        profile: normalized profile dict {thinking: {...}, non_thinking: {...}}.
        sampling_override: flat sampling dict from a connected Sampling node.
        sampling_json_override: parsed JSON sampling dict (already validated).
        extra_request_json: parsed raw JSON dict (already validated). Last word.
        reasoning_mode: "" / "auto" / "low" / ... / "custom".
        reasoning_custom: custom reasoning value (used when mode == "custom").
        context_length: context window (n_ctx). Default 4096.
        json_mode: force JSON object response.
        tools: KDX_LLM_TOOLS dict {"tools": [...]} (NOT a bare list).
        provider: explicit/auto provider name, used for Qwen i-prefix gating.
        send_thinking_flag: always send ``chat_template_kwargs.enable_thinking``
            (set when the user forced thinking on/off or picked a reasoning
            preset). Without it the flag is only sent together with a
            reasoning effort, so plain OpenAI-style servers get no extra keys.

    Returns:
        (payload, effective_sampling)
    """
    mode = "thinking" if thinking_on else "non_thinking"
    prof = profile.get(mode, {}) if isinstance(profile, dict) else {}
    if not isinstance(prof, dict):
        prof = {}
    profile_sampling = prof.get("sampling", {}) if isinstance(prof.get("sampling"), dict) else {}
    profile_request = prof.get("request", {}) if isinstance(prof.get("request"), dict) else {}

    # 1. Base sampling from profile
    request_sampling: Dict[str, Any] = dict(profile_sampling)

    # 2. Node-based sampling override (explicit workflow override)
    if sampling_override and isinstance(sampling_override, dict):
        request_sampling.update(sampling_override)

    # 3. JSON sampling string override (validated dict)
    if sampling_json_override and isinstance(sampling_json_override, dict):
        request_sampling.update(sampling_json_override)

    # 4. Root payload
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": bool(stream),
    }
    filtered_profile_request = {
        k: v for k, v in profile_request.items()
        if k not in CONTROL_REQUEST_KEYS
    }
    payload.update(filtered_profile_request)
    payload.update(request_sampling)

    # Context window (n_ctx) — Client default only. Explicit profile/sampling n_ctx wins.
    try:
        ctx = int(context_length or 0)
    except (TypeError, ValueError):
        ctx = 0
    if ctx > 0 and "n_ctx" not in payload:
        payload["n_ctx"] = ctx

    # JSON mode — applied AFTER request_sampling so a profile response_format
    # is overridden when json_mode is explicitly on.
    if json_mode:
        if _is_llama_provider(provider):
            # llama.cpp can fail to initialize a grammar for response_format on
            # some templates/models. Use an explicit instruction instead and let
            # the response parser extract JSON. Keep system messages at the
            # beginning because many chat templates require that.
            messages = list(payload.get("messages") or [])
            instruction = "Respond with a valid JSON object only."
            if messages and isinstance(messages[0], dict) and messages[0].get("role") == "system":
                first = dict(messages[0])
                content = first.get("content", "")
                if isinstance(content, str):
                    if instruction not in content:
                        first["content"] = (content + "\n" + instruction).strip()
                    messages[0] = first
                else:
                    messages.insert(1, {"role": "system", "content": instruction})
            else:
                messages.insert(0, {"role": "system", "content": instruction})
            payload["messages"] = messages
        else:
            payload["response_format"] = {"type": "json_object"}

    # Tools (KDX_LLM_TOOLS dict shape, not a bare list)
    if isinstance(tools, dict) and tools.get("tools"):
        payload["tools"] = tools["tools"]

    # Reasoning / chat_template_kwargs
    reasoning_val = reasoning_mode
    if reasoning_val == "custom":
        reasoning_val = (reasoning_custom or "").strip()
    elif not reasoning_val or reasoning_val == "auto":
        # Fall back to the saved profile's reasoning setting
        reasoning_val = prof.get("request", {}).get("reasoning", "") if isinstance(prof, dict) else ""

    if reasoning_val and reasoning_val != "auto":
        chat_kwargs = payload.get("chat_template_kwargs")
        if not isinstance(chat_kwargs, dict):
            chat_kwargs = {}
        # Qwen i-prefix convention: non-thinking Qwen models served through
        # llama.cpp often expect an "i" prefix (e.g. "ilow"). Do not apply this
        # globally to vLLM/Ollama/OpenAI-style providers. A profile request key
        # "qwen_i_prefix": true/false can force/disable it explicitly.
        use_i_prefix = _should_use_qwen_i_prefix(model, provider, profile_request, thinking_on)
        if use_i_prefix and reasoning_val and not reasoning_val.startswith("i"):
            chat_kwargs["reasoning_effort"] = f"i{reasoning_val}"
        else:
            chat_kwargs["reasoning_effort"] = reasoning_val
        chat_kwargs["enable_thinking"] = bool(thinking_on)
        payload["chat_template_kwargs"] = chat_kwargs
    elif send_thinking_flag:
        # Thinking on/off must reach the chat template even without a
        # reasoning effort, otherwise e.g. Qwen3 keeps thinking when the user
        # selected thinking = off.
        chat_kwargs = payload.get("chat_template_kwargs")
        chat_kwargs = dict(chat_kwargs) if isinstance(chat_kwargs, dict) else {}
        chat_kwargs["enable_thinking"] = bool(thinking_on)
        payload["chat_template_kwargs"] = chat_kwargs

    # 5. Raw extra request JSON (absolute priority — last word)
    if extra_request_json and isinstance(extra_request_json, dict):
        payload.update(extra_request_json)

    return payload, request_sampling
