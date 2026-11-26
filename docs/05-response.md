# KDX LLM — Structured Response

## `KDXLLMResponse`

**File:** `kdx_core/response.py`

The Chat node's 9th output (`response_obj`) is a `KDXLLMResponse` dataclass,
returned as a dict (V1) or a typed custom type (V3).

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `content` | `str` | `""` | Clean response text |
| `reasoning` | `str` | `""` | Reasoning/thinking text |
| `json_data` | `Any` | `None` | Parsed JSON (when `json_mode=True`) |
| `tool_calls` | `List[dict]` | `[]` | Function-calling tool calls |
| `model` | `str` | `""` | Actual model name reported by server |
| `finish_reason` | `str` | `"stop"` | `stop`, `length`, `tool_calls`, etc. |
| `prompt_tokens` | `int` | `0` | Input token count |
| `completion_tokens` | `int` | `0` | Output token count |
| `total_tokens` | `int` | `0` | Total token count |
| `tokens_per_second` | `float` | `0.0` | Generation speed |
| `generation_time` | `float` | `0.0` | Seconds for the API call |
| `raw` | `dict` | `{}` | Original API response dict |
| `metadata` | `dict` | `{}` | Profile key, mode, json_mode, media_mode, request_info |

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `to_dict()` | `dict` | `asdict(self)` — all fields |
| `to_json(indent=2)` | `str` | JSON string |
| `from_parsed(result, raw_response=None, metadata=None)` (classmethod) | `KDXLLMResponse` | Build from `parse_response()` output |

### `from_parsed()` Input Contract

`result` is the dict returned by `postprocess.parse_response()`:

```python
{
    "response": "Hello!",
    "thinking": "Let me think...",
    "json": {"key": "value"},       # or None
    "tool_calls": [...],             # or []
    "raw": "{...}",                  # JSON string
    "model_used": "Qwen3.5-27B",
    "prompt_tokens": 150,
    "completion_tokens": 200,
    "total_tokens": 350,
    "finish_reason": "stop",
    "tokens_per_second": 45.2,
    "generation_time": 4.4,
}
```

`raw_response` is the original API response dict (before `json.dumps`).

### Accessing from a Workflow

In a ComfyUI workflow, the 9th output (`response_obj`) is a dict:

```python
{
    "content": "42",
    "reasoning": "2+2=4",
    "json_data": None,
    "tool_calls": [],
    "model": "Qwen3.5-27B",
    "finish_reason": "stop",
    "prompt_tokens": 10,
    "completion_tokens": 5,
    "total_tokens": 15,
    "tokens_per_second": 50.0,
    "generation_time": 0.1,
    "raw": {"id": "...", "choices": [...]},
    "metadata": {"profile_key": "Qwen3.5-27B", "mode": "thinking", "json_mode": False, ...}
}
```

### 11-Output Slot Map

| Slot | Name | Type | Use |
|------|------|------|-----|
| 0 | `response` | STRING | Quick text access |
| 1 | `thinking` | STRING | Reasoning text |
| 2 | `json` | STRING | JSON string (when `json_mode`) |
| 3 | `raw` | STRING | Full API response (JSON string) |
| 4 | `model_used` | STRING | Which model actually responded |
| 5 | `profile_key` | STRING | Which profile matched |
| 6 | `profile_json` | STRING | Profile as JSON |
| 7 | `request_info` | STRING | Effective request metadata |
| 8 | `response_obj` | ANY | **Structured object** (this doc) |
| 9 | `session` | `KDX_LLM_SESSION` | Updated session for chaining |
| 10 | `tool_calls` | STRING | Tool calls as JSON array |

**Rule of thumb:**
- Need just the text? → Slot 0 (`response`)
- Need token counts, timing, or tool calls? → Slot 8 (`response_obj`)
- Need to chain the conversation? → Slot 9 (`session`)
- Need tool calls as a direct JSON string? → Slot 10 (`tool_calls`)
