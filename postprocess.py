"""KDX LLM Client — response normalization and reasoning/JSON extraction."""

import json
import re

_THINK_RE = re.compile(
    r"<think(?:ing)?>(.*?)</think(?:ing)?>",
    re.DOTALL | re.IGNORECASE,
)
_CLOSE_RE = re.compile(r"</think(?:ing)?>", re.IGNORECASE)
_OPEN_RE = re.compile(r"<think(?:ing)?>", re.IGNORECASE)
_FENCE_RE = re.compile(
    r"^```(?:json)?\s*(.*?)\s*```$",
    re.DOTALL | re.IGNORECASE,
)


def extract_thinking(text: str):
    """Split visible answer and inline <think>/<thinking> content."""
    text = text or ""

    matches = _THINK_RE.findall(text)
    if matches:
        answer = _THINK_RE.sub("", text).strip()
        thinking = "\n\n".join(match.strip() for match in matches)
        return answer, thinking

    closing = None
    for match in _CLOSE_RE.finditer(text):
        closing = match

    if closing:
        thinking = _OPEN_RE.sub("", text[:closing.start()]).strip()
        answer = text[closing.end():].strip()
        return answer, thinking

    return text.strip(), ""


def extract_json(text: str):
    """Parse plain, fenced, or embedded JSON from a response."""
    if not text:
        return None

    source = text.strip()
    fence = _FENCE_RE.match(source)
    if fence:
        source = fence.group(1)

    try:
        return json.loads(source)
    except (TypeError, ValueError):
        pass

    decoder = json.JSONDecoder()
    for index, char in enumerate(source):
        if char not in "{[":
            continue
        try:
            return decoder.raw_decode(source[index:])[0]
        except (TypeError, ValueError):
            continue

    return None


def _content_to_text(content) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        chunks = []
        for part in content:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str):
                chunks.append(text)
        return "".join(chunks)

    return ""


def _looks_like_json(text: str) -> bool:
    """Obvious JSON answers: starts with { / [ or a ```json (or bare ```) fence.

    A ```python block that happens to contain a dict literal is not JSON.
    """
    if text.startswith(("{", "[")):
        return True
    if text.startswith("```"):
        first_line = text[3:].split("\n", 1)[0].strip().lower()
        return first_line in ("", "json", "jsonc") or first_line.startswith(("{", "["))
    return False


def parse_response(
    response: dict,
    json_mode: bool = False,
    elapsed_time: float = 0.0,
) -> dict:
    response = dict(response or {})

    usage = response.get("usage") or {}
    prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
    completion_tokens = int(usage.get("completion_tokens", 0) or 0)
    total_tokens = int(
        usage.get("total_tokens", prompt_tokens + completion_tokens)
        or (prompt_tokens + completion_tokens)
    )

    choices = response.get("choices") or []
    finish_reason = (
        choices[0].get("finish_reason") or ""
        if choices and isinstance(choices[0], dict)
        else ""
    )

    timings = response.get("timings") or {}
    if timings.get("predicted_per_second") is not None:
        try:
            tokens_per_second = round(float(timings["predicted_per_second"]), 2)
        except (TypeError, ValueError):
            tokens_per_second = 0.0
    elif elapsed_time > 0 and completion_tokens > 0:
        tokens_per_second = round(completion_tokens / elapsed_time, 2)
    else:
        tokens_per_second = 0.0

    response["_kdx_timing"] = {
        "generation_time": round(float(elapsed_time), 6),
        "tokens_per_second": tokens_per_second,
    }

    result = {
        "response": "",
        "thinking": "",
        "json": None,
        "tool_calls": [],
        "raw": json.dumps(response, ensure_ascii=False, indent=2),
        "model_used": response.get("model", ""),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "finish_reason": finish_reason,
        "tokens_per_second": tokens_per_second,
        "generation_time": elapsed_time,
    }

    if not choices:
        return result

    message = choices[0].get("message") or {}
    content = _content_to_text(message.get("content"))

    reasoning = message.get("reasoning_content") or message.get("reasoning") or ""
    if isinstance(reasoning, list):
        reasoning = _content_to_text(reasoning)

    if isinstance(reasoning, str) and reasoning.strip():
        content, _ = extract_thinking(content)
        thinking_text = reasoning.strip()
    else:
        content, thinking_text = extract_thinking(content)

    result["response"] = content.strip()
    result["thinking"] = thinking_text
    result["tool_calls"] = message.get("tool_calls") or []

    response_text = result["response"].lstrip()
    if json_mode or _looks_like_json(response_text):
        result["json"] = extract_json(result["response"])

    return result
