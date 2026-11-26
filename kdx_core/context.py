"""KDX Core — lightweight context estimation and trimming.

Default mode is dependency-free chars/4 heuristic. If tiktoken is installed and
the user selects tiktoken/auto, it uses cl100k_base as a better approximation.
"""

import os
from typing import Any, Dict, List


IMAGE_TOKEN_ESTIMATE = 85
AUDIO_TOKEN_ESTIMATE_DIVISOR = 8  # base64 chars -> rough audio token estimate
_TIKTOKEN_ENCODING = None
_TIKTOKEN_UNAVAILABLE = False


def _tokenizer_mode(tokenizer: Any = None) -> str:
    mode = str(tokenizer or os.environ.get("KDX_LLM_TOKENIZER", "heuristic")).strip().lower()
    if mode not in ("heuristic", "tiktoken", "auto"):
        return "heuristic"
    return mode


def _tiktoken_encoding():
    global _TIKTOKEN_ENCODING, _TIKTOKEN_UNAVAILABLE
    if _TIKTOKEN_ENCODING is not None:
        return _TIKTOKEN_ENCODING
    if _TIKTOKEN_UNAVAILABLE:
        return None
    try:
        import tiktoken
        _TIKTOKEN_ENCODING = tiktoken.get_encoding("cl100k_base")
        return _TIKTOKEN_ENCODING
    except Exception:
        _TIKTOKEN_UNAVAILABLE = True
        return None


def estimate_text_tokens(text: str, tokenizer: str = "heuristic") -> int:
    mode = _tokenizer_mode(tokenizer)
    if mode in ("tiktoken", "auto"):
        enc = _tiktoken_encoding()
        if enc is not None:
            try:
                return len(enc.encode(text or "", disallowed_special=()))
            except Exception:
                pass
    return max(1, (len(text or "") + 3) // 4)


def estimate_content_tokens(content: Any, tokenizer: str = "heuristic") -> int:
    if isinstance(content, str):
        return estimate_text_tokens(content, tokenizer)

    if isinstance(content, list):
        total = 0
        for part in content:
            if not isinstance(part, dict):
                total += estimate_text_tokens(str(part), tokenizer)
                continue

            ptype = part.get("type")
            if ptype == "text":
                total += estimate_text_tokens(part.get("text", ""), tokenizer)
            elif ptype == "image_url":
                total += IMAGE_TOKEN_ESTIMATE
            elif ptype == "input_audio":
                audio = part.get("input_audio") or {}
                data = audio.get("data", "") if isinstance(audio, dict) else str(audio)
                total += max(1, len(str(data)) // AUDIO_TOKEN_ESTIMATE_DIVISOR)
            else:
                total += estimate_text_tokens(str(part), tokenizer)
        return total

    return estimate_text_tokens(str(content), tokenizer)


def estimate_message_tokens(message: Dict[str, Any], tokenizer: str = "heuristic") -> int:
    # OpenAI-like per-message overhead; conservative enough for trimming.
    return 4 + estimate_content_tokens(message.get("content", ""), tokenizer)


def estimate_messages_tokens(messages: List[Dict[str, Any]], tokenizer: str = "heuristic") -> int:
    return sum(estimate_message_tokens(m, tokenizer) for m in messages if isinstance(m, dict)) + 2


def trim_messages(messages: List[Dict[str, Any]], max_tokens: int, tokenizer: str = "heuristic") -> List[Dict[str, Any]]:
    """Trim oldest non-system messages until estimated prompt fits max_tokens.

    System messages and the final user message are preserved. If even those do
    not fit, the original list is returned rather than producing an invalid
    empty prompt.
    """
    if max_tokens <= 0 or not messages:
        return messages

    if estimate_messages_tokens(messages, tokenizer) <= max_tokens:
        return messages

    # Keep all system messages and the last message (current user turn).
    system_messages = [m for m in messages if isinstance(m, dict) and m.get("role") == "system"]
    last_message = messages[-1] if messages else None
    history = [
        m for m in messages[:-1]
        if isinstance(m, dict) and m.get("role") != "system"
    ]

    # Add history from newest to oldest, then restore chronological order.
    selected = []
    for message in reversed(history):
        candidate = system_messages + list(reversed(selected + [message])) + ([last_message] if last_message else [])
        if estimate_messages_tokens(candidate, tokenizer) > max_tokens:
            break
        selected.append(message)

    kept_history = list(reversed(selected))
    # Never start the kept history with an orphaned assistant/tool reply: many
    # chat templates (Gemma, Mistral, ...) require user/assistant alternation
    # and reject a conversation whose first turn is not from the user.
    while kept_history and kept_history[0].get("role") != "user":
        kept_history.pop(0)

    trimmed = system_messages + kept_history
    if last_message:
        trimmed.append(last_message)

    if estimate_messages_tokens(trimmed, tokenizer) > max_tokens:
        return messages

    return trimmed


MEDIA_PART_TYPES = ("image_url", "input_audio", "video_url")
HISTORY_MEDIA_MODES = ("latest", "all", "none")


def _has_media(content: Any) -> bool:
    return isinstance(content, list) and any(
        isinstance(part, dict) and part.get("type") in MEDIA_PART_TYPES for part in content
    )


def _without_media(content: Any) -> Any:
    """Replace media parts with a short text marker; collapse to a plain string."""
    if not _has_media(content):
        return content
    texts = []
    for part in content:
        if not isinstance(part, dict):
            continue
        ptype = part.get("type")
        if ptype == "text":
            texts.append(str(part.get("text", "")))
        elif ptype in MEDIA_PART_TYPES:
            label = "audio" if ptype == "input_audio" else "image"
            texts.append(f"[earlier {label} omitted]")
    return "\n".join(t for t in texts if t)


def strip_history_media(
    history: List[Dict[str, Any]],
    mode: str = "latest",
    current_has_media: bool = False,
) -> List[Dict[str, Any]]:
    """Limit how much media from earlier turns is re-sent.

    Every earlier image/audio is otherwise base64-encoded into each new request,
    which costs time and many prompt tokens.

    - ``all``: keep everything (old behaviour).
    - ``none``: replace all earlier media with a short text marker.
    - ``latest`` (default): keep only the most recent media turn, and none
      at all when the current message brings its own media.
    """
    mode = mode if mode in HISTORY_MEDIA_MODES else "latest"
    if mode == "all":
        return history

    keep_index = -1
    if mode == "latest" and not current_has_media:
        for index in range(len(history) - 1, -1, -1):
            message = history[index]
            if isinstance(message, dict) and _has_media(message.get("content")):
                keep_index = index
                break

    result = []
    for index, message in enumerate(history):
        if isinstance(message, dict) and index != keep_index and _has_media(message.get("content")):
            message = {**message, "content": _without_media(message.get("content"))}
        result.append(message)
    return result


def has_media(content: Any) -> bool:
    return _has_media(content)
