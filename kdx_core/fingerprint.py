"""KDX Core — deterministic input fingerprint.

Single source of truth for the cacheability hash, shared by:
- V1 ``IS_CHANGED`` (chat.py)
- V3 ``fingerprint_inputs`` (v3_adapter.py)

Design (per P1.3 decision A):
- Only tracks HIDDEN / EXTERNAL state that ComfyUI's graph execution
  signature cannot see: on-disk profile/prompt mtimes, session id, and
  scalar settings. Media tensors are intentionally EXCLUDED — ComfyUI
  invalidates downstream caches on its own when an upstream tensor link
  changes, and hashing large tensors would burn CPU for nothing.
- Canonical representation: ``json.dumps(key, sort_keys=True)`` so key
  ordering never affects the hash.
"""

import hashlib
import json
from typing import Any, Dict


def _session_messages(session: Any) -> list:
    """Safe message list for a connected session object or dict."""
    if session is None:
        return []
    msgs = getattr(session, "messages", None)
    if msgs is None and isinstance(session, dict):
        msgs = session.get("messages")
    return msgs if isinstance(msgs, list) else []


def _session_turns(session: Any) -> int:
    """Safe turn count for the fingerprint.

    A connected KDX_LLM_SESSION socket carries the conversation history, so its
    turn count must be part of the cache key (two calls with different history
    must not share a cache entry). Accepts a KDXLLMSession (has turn_count) or
    a dict (has "messages"). Legacy string session_id is handled separately.
    """
    if session is None:
        return 0
    turns = getattr(session, "turn_count", None)
    if isinstance(turns, int):
        return turns
    return len(_session_messages(session)) // 2


def _content_fingerprint(content: Any) -> Any:
    """Compact, stable fingerprint for message content.

    Media parts can contain huge base64 payloads. Hash those instead of putting
    the full payload into the cache key.
    """
    if isinstance(content, str):
        return ["text", hashlib.sha1(content.encode("utf-8", errors="replace")).hexdigest()]

    if isinstance(content, list):
        parts = []
        for part in content:
            if not isinstance(part, dict):
                parts.append(["raw", hashlib.sha1(str(part).encode("utf-8", errors="replace")).hexdigest()])
                continue

            ptype = str(part.get("type", ""))
            if ptype == "text":
                text = part.get("text", "")
                parts.append(["text", hashlib.sha1(str(text).encode("utf-8", errors="replace")).hexdigest()])
            elif ptype == "image_url":
                image = part.get("image_url") or {}
                url = image.get("url", "") if isinstance(image, dict) else str(image)
                parts.append(["image_url", len(str(url)), hashlib.sha1(str(url).encode("utf-8", errors="replace")).hexdigest()])
            elif ptype == "input_audio":
                audio = part.get("input_audio") or {}
                data = audio.get("data", "") if isinstance(audio, dict) else str(audio)
                fmt = audio.get("format", "") if isinstance(audio, dict) else ""
                parts.append(["input_audio", len(str(data)), str(fmt), hashlib.sha1(str(data).encode("utf-8", errors="replace")).hexdigest()])
            else:
                parts.append([ptype, hashlib.sha1(json.dumps(part, sort_keys=True, default=str).encode("utf-8", errors="replace")).hexdigest()])
        return parts

    return ["raw", hashlib.sha1(str(content).encode("utf-8", errors="replace")).hexdigest()]


def _session_hash(session: Any) -> str:
    """Hash session message roles/content compactly for cache invalidation."""
    messages = _session_messages(session)
    compact = [
        [str(m.get("role", "")), _content_fingerprint(m.get("content", ""))]
        for m in messages
        if isinstance(m, dict)
    ]
    return hashlib.sha1(json.dumps(compact, sort_keys=True, default=str).encode("utf-8", errors="replace")).hexdigest()


def build_fingerprint_key(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Build the deterministic key dict for a Chat node invocation.

    Includes every input that affects the request, plus the on-disk mtimes
    (profiles / prompts / user-prompts) that ComfyUI's graph cannot observe.

    P2.2: a connected ``session`` socket (KDX_LLM_SESSION) contributes its
    turn count to the key; otherwise the legacy ``session_id`` string is used.
    """
    client = kwargs.get("client") or {}
    connected_session = kwargs.get("session")
    return {
        "prompt": kwargs.get("prompt", ""),
        "model_preset": kwargs.get("model_preset", "generic"),
        "thinking": kwargs.get("thinking", False),
        "reasoning_mode": kwargs.get("reasoning_mode", ""),
        "system_prompt": kwargs.get("system_prompt", ""),
        "system_prompt_profile": kwargs.get("system_prompt_profile", ""),
        "json_mode": kwargs.get("json_mode", False),
        "stream": kwargs.get("stream", True),
        "media_mode": kwargs.get("media_mode", "auto"),
        "load_before": kwargs.get("load_before", False),
        "unload_after": kwargs.get("unload_after", False),
        "load_timeout": kwargs.get("load_timeout", 300),
        "reset_session": kwargs.get("reset_session", True),
        # P2.2: connected session socket wins; else legacy session_id string.
        "session_turns": _session_turns(connected_session),
        "session_hash": _session_hash(connected_session),
        "session_id": "" if connected_session is not None else kwargs.get("session_id", ""),
        "max_history": kwargs.get("max_history", 40),
        "history_media": kwargs.get("history_media", "latest"),
        "client": client,
        "thinking_sampling": kwargs.get("thinking_sampling") or {},
        "non_thinking_sampling": kwargs.get("non_thinking_sampling") or {},
        "sampling_json_thinking": kwargs.get("sampling_json_thinking", ""),
        "sampling_json_non_thinking": kwargs.get("sampling_json_non_thinking", ""),
        "extra_request_json": kwargs.get("extra_request_json", ""),
        "tools": kwargs.get("tools") or {},
        "llm_off": kwargs.get("llm_enabled") is False,
        "task_prompt": kwargs.get("task_prompt") or "",
        # Hidden on-disk state ComfyUI cannot see through the graph:
        "profiles_mtime": _safe_mtime(kwargs.get("profiles_mtime")),
        "prompts_mtime": _safe_mtime(kwargs.get("prompts_mtime")),
        "user_prompts_mtime": _safe_mtime(kwargs.get("user_prompts_mtime")),
    }


def _safe_mtime(value: Any) -> Any:
    """mtime may be a float, a callable result, or a mock — normalize to a hashable scalar."""
    if callable(value):
        try:
            value = value()
        except Exception:
            value = 0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0


def canonical_hash(key: Dict[str, Any]) -> str:
    """Stable sha256 over the canonical (sorted-keys) JSON representation."""
    canonical = json.dumps(key, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def fingerprint(kwargs: Dict[str, Any]) -> str:
    """Convenience: build_fingerprint_key + canonical_hash in one call."""
    return canonical_hash(build_fingerprint_key(kwargs))
