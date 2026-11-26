# KDX LLM — Node Reference

All nodes are in the `KDX/LLM` category. 14 nodes total.

---

## 🔌 KDX • LLM Client

**File:** `client.py`

Connects to an OpenAI-compatible LLM server. Produces a `KDX_LLM_CLIENT` dict
consumed by the Chat node.

### Inputs

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `url` | STRING | — | Server base URL (e.g. `http://localhost:8080`) |
| `model` | STRING | — | Model name (auto-populated from server model list) |
| `api_key` | STRING | `""` | Bearer token (empty for local servers) |
| `api_key_env` | STRING | `"KDX_LLM_API_KEY"` | Env var name for the API key (if `api_key` is empty) |
| `context_length` | INT | `4096` | Context window size (512–262144) |
| `timeout` | INT | `300` | HTTP timeout in seconds |
| `max_retries` | INT | `2` | Retry count on transient failures |
| `provider` | COMBO | `"auto"` | Provider override: `auto`, `llama_cpp_router`, `ollama`, `llama_cpp`, `vllm`, `generic`. See [`07-provider.md`](07-provider.md). |

### Outputs

| Name | Type | Description |
|------|------|-------------|
| `client` | `KDX_LLM_CLIENT` | Dict: `{url, model, api_key, api_key_env, timeout, max_retries, context_length, provider, profile_key, profile}` |

### Example

```
Client(url="http://localhost:8080", model="Qwen3.5-27B", provider="llama_cpp_router")
  → client output → Chat node
```

---

## 💬 KDX • LLM Chat

**File:** `chat.py`

The main chat node. Sends a prompt to the LLM and returns 11 outputs.

### Inputs

**Required:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `prompt` | STRING (multiline) | `""` | User message. Empty = bypass (no API call). |
| `model_preset` | COMBO | `"generic"` | `generic`, `qwen_thinking`, `qwen_json`, `deepseek` — sets thinking/json_mode defaults |

**Optional:**

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `client` | `KDX_LLM_CLIENT` | — | From Client node |
| `thinking_sampling` | `KDX_LLM_OPTIONS` | — | Sampling override for thinking mode |
| `non_thinking_sampling` | `KDX_LLM_OPTIONS` | — | Sampling override for non-thinking mode |
| `thinking` | COMBO | `"auto"` | `auto` (use preset), `on`, `off` |
| `reasoning_mode` | COMBO | `""` | `""`, `auto`, `low`, `medium`, `high`, `xhigh`, `spoon`, `einstein`, `custom` |
| `reasoning_custom` | STRING | `""` | Custom reasoning value (when `reasoning_mode=custom`) |
| `system_prompt` | STRING (multiline) | `""` | Direct system prompt text |
| `system_prompt_profile` | STRING | `""` | Saved system prompt name (from System Prompt node) |
| `stream` | BOOLEAN | `True` | Streaming responses |
| `media_mode` | COMBO | `"auto"` | `auto`, `none`, `image`, `audio`, `video` |
| `image` | IMAGE | — | Optional image for multi-modal |
| `media_settings` | `KDX_LLM_MEDIA` | — | From Media Settings node |
| `session` | `KDX_LLM_SESSION` | — | Connected session object (overrides `session_id`) |
| `session_id` | STRING | `""` | Legacy session ID (used only when no `session` socket) |
| `reset_session` | BOOLEAN | `True` | `True` = new conversation, `False` = continue |
| `max_history` | INT | `40` | Max messages in history (2–200, even) |
| `max_prompt_tokens` | INT | `0` | Optional prompt-token budget; `0` disables trimming |
| `token_counter` | COMBO | `"heuristic"` | `heuristic`, `tiktoken`, or `auto` token estimate mode |
| `tools` | `KDX_LLM_TOOLS` | — | From Tool node |
| `sampling_json_thinking` | STRING (multiline) | `""` | JSON sampling for thinking mode |
| `sampling_json_non_thinking` | STRING (multiline) | `""` | JSON sampling for non-thinking mode |
| `extra_request_json` | STRING (multiline) | `""` | Raw JSON merged into payload (highest priority) |
| `json_mode` | COMBO | `"auto"` | `auto` follows model preset; `on` forces JSON object response; `off` disables JSON mode even if preset enables it |
| `load_before` | BOOLEAN | `False` | Load model before generation |
| `unload_after` | BOOLEAN | `False` | Unload model after generation |
| `load_timeout` | INT | `300` | Max seconds to wait for model load |
| `history_media` | COMBO | `"latest"` | Media from earlier turns: `latest`, `all`, `none` |
| `llm_enabled` | BOOLEAN socket | `True` | LLM on/off. Not connected or `True` = LLM runs; `False` = no LLM call, `response` = `prompt` unchanged. See [Switching the LLM off](#switching-the-llm-off). |
| `task_prompt` | STRING socket | `""` | Fixed instructions wrapped around `prompt`, used only when the LLM runs. See [Task prompt](#task-prompt). |

### Outputs (10 slots)

| Slot | Name | Type | Description |
|------|------|------|-------------|
| 0 | `response` | STRING | Clean response text |
| 1 | `thinking` | STRING | Reasoning/thinking text |
| 2 | `json` | STRING | Parsed JSON (when `json_mode=True`) |
| 3 | `raw` | STRING | Full normalized API response (JSON string) |
| 4 | `model_used` | STRING | Actual model name reported by server |
| 5 | `profile_key` | STRING | Matched model profile key |
| 6 | `profile_json` | STRING | Matched profile as JSON |
| 7 | `request_info` | STRING | Effective request metadata (JSON) |
| 8 | `response_obj` | ANY | `KDXLLMResponse` dict. See [`05-response.md`](05-response.md). |
| 9 | `session` | `KDX_LLM_SESSION` | Updated `KDXLLMSession` for chaining |
| 10 | `tool_calls` | STRING | Tool calls returned by the model as JSON array |

### Bypass Behavior

If `prompt` is empty/whitespace, the node returns an empty 11-tuple without
calling the API. The incoming `session` is preserved (bypass-safe for
conditional workflows).

### Switching the LLM off

`llm_enabled` is an input **socket** (always visible on the node, like `client`). Connect any BOOLEAN:

| `llm_enabled` | Chat |
|---|---|
| not connected | LLM runs (as before) |
| `True` | LLM runs |
| `False` | no API call, no model load/unload; `response` = the input `prompt` **unchanged** |

With `False`, every other output is the same as in the empty-prompt bypass (empty strings, empty
`response_obj`, `tool_calls = "[]"`), the incoming `session` passes through, and the answer box shows
"⏭ LLM off" (UI output `kdx_llm_off`).

Typical sources: KDX Wildcard Studio's `llm_enabled` output (the LLM pill in its panel), or a core **Boolean** node —
one Boolean can drive several Chats and other switches at once (directly or through Set/Get nodes).

### Task prompt

Some prompt-enhancer models wrap the user's text in a long, fixed task prompt (e.g. MiniMax-H3-Image-PE:
`prompt/t2i/task_prompt.txt` ends with `input_text: {}`). Connect that text to `task_prompt` and the user's
text to `prompt` (instead of joining them first), so the LLM switch returns only the user's text.

| `task_prompt` contains | Message sent to the LLM |
|---|---|
| nothing (not connected / empty) | `prompt` |
| `{}` or `{prompt}` | task prompt with the prompt in that place; `{{` / `}}` become `{` / `}` (`str.format` rules) |
| `{prompt_json}` | same, the prompt inserted as a JSON string (`"..."`, quotes escaped) |
| no placeholder | task prompt as written + blank line + `prompt` |

Other `{names}` stay untouched. With `llm_enabled = False` the `response` is the bare `prompt` — the task
prompt is never passed on. The system prompt stays separate (`system_prompt` / `system_prompt_profile`).

MiniMax-H3-Image-PE text-to-image: `t2i/system_prompt.txt` → `system_prompt`, `t2i/task_prompt.txt` →
`task_prompt` (unchanged), user text → `prompt`, then JSON Extract `expanded_caption`. To get the user's text
there too when the LLM is off, connect the same user text to JSON Extract's `default`.
For image edit, the task prompt has no placeholder; to match MiniMax's layout, end your copy with
`User Editing Instruction (JSON string):` + `{prompt_json}` + `User Aspect Ratio Selection:` lines.

### IS_CHANGED

Canonical hash of all inputs (including `llm_enabled` and `task_prompt`) + `sampling_store.mtime()`
+ `prompt_store.mtime()` + `user_prompt_store.mtime()`. Same inputs + unchanged
stores = cache hit. Updating to 0.8.0 changes every hash once (one cache miss).

---

## 🔄 KDX • LLM Session

**File:** `session_node.py`

Standalone session management: create, reset, import, pass through, save, or load
conversation sessions.

### Inputs

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `action` | COMBO | `"new"` | `new`, `passthrough`, `reset`, `import_json`, `save`, `load` |
| `session` | `KDX_LLM_SESSION` | — | Optional upstream session |
| `custom_id` | STRING | `""` | Custom session ID (empty = auto-generate) |
| `import_json` | STRING (multiline) | `""` | JSON messages (for `import_json` action) |
| `session_name` | STRING | `""` | Named session key (for `save` / `load` actions) |

### Outputs

| Name | Type | Description |
|------|------|-------------|
| `session` | `KDX_LLM_SESSION` | The session object |
| `messages_json` | STRING | Full history as JSON (for inspection) |
| `turn_count` | INT | Number of completed user/assistant turns |

### Actions

| Action | Behavior |
|--------|----------|
| `new` | Create a fresh empty session (auto or custom ID) |
| `passthrough` | Forward a connected session unchanged (optionally rename) |
| `reset` | Clear messages of a connected session (preserves ID) |
| `import_json` | Load messages from a JSON string |
| `save` | Persist a connected session under `session_name` |
| `load` | Restore a persisted session by `session_name` |

**`import_json` format:** either a list `[{"role": "user", "content": "..."}]`
or an object `{"messages": [...]}`.

### Example: Start a new conversation

```
Session(action="new") → session output → Chat node
```

### Example: Reset a conversation mid-graph

```
Chat 1 → session output → Session(action="reset") → session output → Chat 2
```

---

## 🎛️ KDX • LLM Simple Sampling

**File:** `options.py`

Core sampling parameters with per-parameter ON/OFF switches.

### Inputs

Each parameter has an `_enabled` boolean and a value:

| Parameter | Type | Range | Default | Description |
|-----------|------|-------|---------|-------------|
| `temperature` | FLOAT | 0.0–2.0 | 0.7 | Randomness |
| `top_p` | FLOAT | 0.0–1.0 | 0.95 | Nucleus sampling |
| `top_k` | INT | 0–200 | 40 | Top-K (0 = disabled) |
| `min_p` | FLOAT | 0.0–1.0 | 0.0 | Minimum probability |
| `repeat_penalty` | FLOAT | 0.0–2.0 | 1.0 | Repetition penalty |
| `presence_penalty` | FLOAT | -2.0–2.0 | 0.0 | Presence penalty |
| `frequency_penalty` | FLOAT | -2.0–2.0 | 0.0 | Frequency penalty |
| `max_tokens` | INT | 1–1000000 | 0 | Max completion tokens (0 = unlimited) |
| `stop` | STRING | — | `""` | Stop sequences (comma-separated) |
| `seed` | INT | — | -1 | Random seed (-1 = random) |

### Output

| Name | Type | Description |
|------|------|-------------|
| `options` | `KDX_LLM_OPTIONS` | `{options: {only_enabled_params}}` |

Only enabled parameters are included in the output dict.

---

## 🔬 KDX • LLM Advanced Sampling

**File:** `options.py`

Provider-specific parameters: MiRoStat, `repeat_last_n`, `thinking_budget`,
`min_tokens`, `dry_run`, `extra_body` JSON.

### Output

Same as Simple Sampling: `KDX_LLM_OPTIONS`.

---

## ⚡ KDX • LLM Quick Presets

**File:** `quick_sampling_node.py`

One-click presets + user-defined presets.

### Presets

| Preset | Description |
|--------|-------------|
| `balanced` | General-purpose defaults |
| `creative` | High temperature, high top_p |
| `precise` | Low temperature, low top_p |
| `reasoning` | Optimized for reasoning models |
| `json_output` | Optimized for JSON mode |

### Output

`KDX_LLM_OPTIONS` (same type as Simple/Advanced Sampling).

---

## 💾 KDX • LLM Model Profile

**File:** `model_profile_node.py`

Persistent per-model sampling profiles with glob pattern matching.

### Actions

| Action | Description |
|--------|-------------|
| `lookup` | Look up a profile for the connected model |
| `save` | Save current sampling as a profile |
| `delete` | Delete a profile |
| `list` | List all profiles |

### Glob Patterns

Profiles support glob patterns in the model key:
- `Qwen3.5-*` matches `Qwen3.5-27B`, `Qwen3.5-9B`, etc.
- `*` matches anything

Matching precedence (4-tier): exact → case-insensitive → suffix (`model-`) → glob.

---

## 📝 KDX • LLM System Prompt

**File:** `system_prompt_node.py`

Save, load, and delete reusable system prompts.

System prompts are plain text files, one per prompt, in `ComfyUI/user/kdx_llm/system_prompts/`:

```
user/kdx_llm/system_prompts/
  krea2_sfw.md        <- the whole prompt, exactly as written
  krea2_art.md
  my_writer.txt       <- .txt works too
```

- The file name is the profile name in the dropdowns (System Prompt node, Chat, KDX Wildcard Studio).
- Any text is allowed — headings, quotes, braces, backslashes, emoji, many lines. Nothing is parsed.
- Add or edit a file in any text editor; it is used on the next run. Back up the folder to keep your prompts.
- Optional one-line descriptions are kept in `.descriptions.json`; if it breaks, only descriptions are lost.
- An older `system_prompts.json` is split into these files automatically and kept as
  `system_prompts.json.migrated`.

### Actions

`save`, `load`, `delete`, `list`

### Output

`STRING` — the prompt text (for `load`), or a status string.

---

## 📋 KDX • LLM User Prompt

**File:** `user_prompt_node.py`

Same as System Prompt, but for user-facing prompts.

---

## 🎬 KDX • LLM Media Settings

**File:** `media_settings.py`

Video frame extraction and audio configuration for multi-modal LLMs.

### Inputs

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `video` | VIDEO | — | Input video |
| `audio` | AUDIO | — | Input audio |
| `video_frame_step` | INT | `1` | Frame sampling step |
| `video_max_frames` | INT | `60` | Max frames to extract |
| `video_max_size` | INT | `512` | Max frame size (px) |
| `audio_max_seconds` | FLOAT | `30.0` | Max audio duration |
| `video_sampling_mode` | COMBO | `"uniform"` | `uniform`, `start`, `end` |

### Output

`KDX_LLM_MEDIA` dict.

---

## ✂️ KDX • LLM Response Formatter

**File:** `response_formatter.py`

Post-process LLM output.

### Actions

| Action | Description |
|--------|-------------|
| `passthrough` | No change |
| `strip_whitespace` | Remove leading/trailing whitespace |
| `extract_first_code_block` | Extract first fenced code block |
| `extract_all_code_blocks` | Extract all fenced code blocks |
| `truncate` | Truncate to N characters |
| `lowercase` | Convert to lowercase |
| `uppercase` | Convert to uppercase |
| `remove_thinking_tags` | Remove `<tool_call>...</tool_call>` content |

### Output

`STRING` — formatted response.

Chain multiple formatters: wire output → input for sequential processing.

---

## 🛠️ KDX • LLM Tool

**File:** `tools.py`

Define OpenAI-compatible function-calling tools.

### Inputs

| Name | Type | Description |
|------|------|-------------|
| `tool_name` | STRING | Function name |
| `description` | STRING | Function description |
| `parameters_json` | STRING (multiline) | JSON Schema for parameters |

### Output

`KDX_LLM_TOOLS` — `{tools: [{type: "function", function: {...}}]}`

---

## 🔍 KDX • LLM Diagnostics

**File:** `diagnostics.py`

Server health check, model list, capability detection.

### Inputs

| Name | Type | Description |
|------|------|-------------|
| `client` | `KDX_LLM_CLIENT` | From Client node |

### Outputs

| Name | Type | Description |
|------|------|-------------|
| `diagnostics` | STRING (JSON) | Server info, model list, capabilities, warnings |

---

## 📈 KDX • LLM Stats

**File:** `stats.py`

Token usage, generation time, tokens/second.

### Inputs

| Name | Type | Description |
|------|------|-------------|
| `raw` | STRING | Raw response JSON (from Chat node's `raw` output) |

### Outputs

| Name | Type | Description |
|------|------|-------------|
| `stats` | STRING (JSON) | `{prompt_tokens, completion_tokens, total_tokens, elapsed, tokens_per_second}` |

---

## 🔑 KDX • JSON Extract

**File:** `json_extract_node.py`

Take one value out of a JSON answer by key. Example: the model answers
`{"rewritten_prompt": "a cat on a roof"}`; with `key = rewritten_prompt` the `value`
output is `a cat on a roof`.

### Inputs

| Name | Type | Description |
|------|------|-------------|
| `json` | STRING | JSON text — connect Chat's `json` or `response` output. Code fences and surrounding text are tolerated. |
| `key` | STRING | Key path: `rewritten_prompt`, `scene.lighting`, `shots.0.prompt` / `shots[0].prompt`. Empty = whole JSON. Exact match first, then case-insensitive. |
| `default` | STRING (optional) | Returned when the key is missing or the input is not JSON. |
| `fail_if_missing` | BOOLEAN (optional) | Stop with an error (listing available keys) instead of using `default`. |

### Outputs

| Name | Type | Description |
|------|------|-------------|
| `value` | STRING | Plain text (strings without quotes; objects/lists as formatted JSON). |
| `found` | BOOLEAN | True when the key was found. |
| `value_json` | STRING | The value as JSON — chain into another JSON Extract. Empty when not found. |

---

## 🧩 KDX • Prompt Template

**File:** `prompt_template_node.py`

Fills `{placeholders}` in `template`. `{text_1}`…`{text_4}` come from the optional text inputs, other names from
`variables` (`name = value` per line, `\n` for a line break). `{{` / `}}` are literal braces.

| Output | Description |
|--------|-------------|
| `text` | The finished prompt. |
| `missing` | Placeholders without a value (comma separated). With `fail_on_missing` the node stops instead. |

---

## 📐 KDX • JSON Output Format

**File:** `json_fields_node.py`

`fields`: one per line, `name` or `name: description`. Optional `system_prompt` is kept and the JSON
instructions are appended.

| Output | Description |
|--------|-------------|
| `system_prompt` | Connect to Chat's `system_prompt`. |
| `fields` | Field names, one per line — connect to JSON Fields' `fields`. |

---

## 🗂️ KDX • JSON Fields

**File:** `json_fields_node.py`

Reads `json` (Chat's `json` or `response`) and returns up to 6 fields listed in `fields`, in that order.
Nested keys use dots. Outputs are relabelled with the field names in the editor.

| Output | Description |
|--------|-------------|
| `field_1` … `field_6` | Values as plain text; `default` when missing. |
| `all_found` | True when every listed field was found. |
| `missing` | Missing field names. With `fail_if_missing` the node stops instead. |
