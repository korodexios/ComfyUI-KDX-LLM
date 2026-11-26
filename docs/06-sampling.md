# KDX LLM — Sampling, Profiles & Reasoning

## Sampling Merge Priority

When multiple sources provide sampling parameters, they are merged in this
order (lowest → highest priority):

```
1. Model profile (saved per-model defaults)
2. Connected Sampling node (Simple / Advanced / Quick Presets)
3. JSON string input (sampling_json_thinking / sampling_json_non_thinking)
4. extra_request_json (overrides everything)
```

Later sources override earlier ones **per parameter**. A parameter not present
in a later source keeps its value from an earlier source.

**File:** `kdx_core/request_builder.py` → `build_chat_payload()`

### Example

```
Profile:        {temperature: 0.7, top_p: 0.9}
Node sampling:  {temperature: 1.0}
JSON string:    {top_k: 50}
extra_request:  {repetition_penalty: 1.2}

Effective:      {temperature: 1.0, top_p: 0.9, top_k: 50, repetition_penalty: 1.2}
                (node overrode temp, JSON added top_k, extra added rep_penalty)
```

---

## Model Profiles

**File:** `model_profile_node.py`, `sampling_store.py`

Profiles are persistent per-model sampling presets stored in a JSON file
(`model_profiles.json` next to the pack, or `KDX_LLM_PROFILES_FILE` env var).

### Structure

```json
{
  "Qwen3.5-27B": {
    "thinking": {
      "sampling": {"temperature": 1.0, "top_p": 0.95, "min_p": 0.05},
      "request":  {"reasoning": "high"}
    },
    "non_thinking": {
      "sampling": {"temperature": 0.3, "top_k": 40},
      "request":  {}
    }
  },
  "Qwen3.5-*": {
    "thinking": {
      "sampling": {"temperature": 0.9},
      "request":  {}
    },
    "non_thinking": {
      "sampling": {"temperature": 0.5},
      "request":  {}
    }
  }
}
```

### Two Modes per Profile

Each profile has `thinking` and `non_thinking` sections. The Chat node selects
the relevant section based on the effective thinking mode (preset + `thinking`
input).

- `sampling` → merged into the request's sampling parameters
- `request` → merged into the request payload directly (e.g. `reasoning`,
  `reasoning_effort`, `chat_template_kwargs`)

### Glob Pattern Matching

Profile keys support glob patterns. Matching precedence (4-tier):

| Tier | Match type | Example |
|------|-----------|---------|
| 1 | Exact | `Qwen3.5-27B` matches `Qwen3.5-27B` |
| 2 | Case-insensitive | `qwen3.5-27b` matches `Qwen3.5-27B` |
| 3 | Suffix (`model-` prefix) | `27B` matches `Qwen3.5-27B` |
| 4 | Glob | `Qwen3.5-*` matches `Qwen3.5-27B`, `Qwen3.5-9B` |

Within the same tier, higher specificity wins (longer glob = more specific).

**File:** `kdx_core/profile_resolver.py` → `resolve_profile(model)`

---

## Quick Presets

**File:** `quick_sampling_node.py`

Built-in presets (no configuration needed):

| Preset | temperature | top_p | min_p | Use case |
|--------|-------------|-------|-------|----------|
| `balanced` | 0.7 | 0.95 | 0.05 | General purpose |
| `creative` | 1.2 | 0.98 | 0.0 | Creative writing |
| `precise` | 0.3 | 0.9 | 0.0 | Factual, deterministic |
| `reasoning` | 1.0 | 0.95 | 0.05 | Reasoning models |
| `json_output` | 0.3 | 0.9 | 0.0 | JSON mode |

User-defined presets are saved to `quick_sampling_presets.json` in ComfyUI's user directory (`ComfyUI/user/kdx_llm/`) when available.

---

## Reasoning Mode

**File:** `chat.py` → `reasoning_mode` input

Per-model reasoning depth control. Values:

| Value | Description |
|-------|-------------|
| `""` (empty) | No reasoning override (use profile default) |
| `auto` | Use the model profile's saved reasoning setting |
| `low` | Minimal reasoning |
| `medium` | Moderate reasoning |
| `high` | Extensive reasoning |
| `xhigh` | Maximum reasoning |
| `spoon` | Qwen-specific: spoon-feeding level |
| `einstein` | Qwen-specific: Einstein level |
| `custom` | Use `reasoning_custom` field value |

### Qwen `i` Prefix Convention

For **non-thinking** models, reasoning values are automatically prefixed with
`i` (e.g. `low` → `ilow`). This is intentional for Qwen instruct models served
via llama.cpp `chat_template_kwargs` — the `i` prefix is part of the Qwen
3.5/3.8 template convention.

- This is **not** the OpenAI `reasoning_effort` field.
- It goes into `chat_template_kwargs`, which non-Qwen servers ignore.
- Do **not** apply to OpenAI-native `reasoning_effort` payloads.

### Where It Lands in the Payload

```python
# In build_chat_payload():
if reasoning_mode and reasoning_mode != "auto":
    value = reasoning_custom if reasoning_mode == "custom" else reasoning_mode
    if not thinking_on:
        value = "i" + value  # Qwen i-prefix convention
    payload["chat_template_kwargs"] = {"reasoning_effort": value}
```

---

## JSON Mode

Set `json_mode = on` (or `auto` with a JSON preset) on the Chat node. The server is asked to return a valid
JSON object. The parsed JSON appears on:
- Slot 2 (`json`) — as a JSON string
- Slot 8 (`response_obj.json_data`) — as a parsed Python object

If the server returns invalid JSON, the `json` field is `None` and the raw
text is in `response`.

---

## `extra_request_json`

Raw JSON merged into the **entire** request payload (not just sampling).
Highest priority — overrides everything else.

```json
{
    "repetition_penalty": 1.5,
    "chat_template_kwargs": {"reasoning_effort": "high"},
    "n": 1
}
```

Must be a JSON **object** (dict). A JSON array or scalar raises `ValueError`.
