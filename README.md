# KDX LLM for ComfyUI

**Version:** 0.10.5

LLM nodes for ComfyUI that talk to any OpenAI-compatible server: rewrite or enhance image prompts, describe
images, hold conversations and turn JSON answers into separate text outputs, all inside a workflow.

Works with llama.cpp, Ollama, vLLM, LM Studio and any server exposing `/v1/chat/completions`.
The LLM server is yours: the nodes send requests only to the URL you enter in the Client node.

- **18 nodes** in the **KDX/LLM** menu.
- No extra Python packages: `requests`, `numpy` and `Pillow` are already in every ComfyUI install.
- Works on its own; pairs with [KDX Wildcard Studio](https://github.com/korodexios/ComfyUI-KDX-Wildcard-Studio)
  and [KDX Resolution](https://github.com/korodexios/ComfyUI-KDX-Resolution) (see
  [Working with other KDX packs](#working-with-other-kdx-packs)).

## Installation

**ComfyUI-Manager:** search for **KDX LLM** and install it.

**Manual:**

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/korodexios/ComfyUI-KDX-LLM.git
# restart ComfyUI
```

Update: `git pull` in that folder, restart ComfyUI, then reload the browser tab (Ctrl+F5).
You also need a running OpenAI-compatible LLM server (for example `llama-server` from llama.cpp, or Ollama).

## Features

- **Model lifecycle** — select, load, unload models directly from the node UI
- **Per-model sampling profiles** — persistent thinking/non-thinking presets with glob pattern matching
- **Quick presets** — built-in sampling presets (balanced, creative, precise, reasoning, json_output) plus user-defined presets
- **Prompt management** — save and load system prompts and user prompts by name
- **Multi-modal** — image, video frames, and audio inputs for vision/audio LLMs
- **Conversation sessions** — multi-turn conversations with configurable history limits
- **Session objects** — DAG-safe, immutable `KDXLLMSession` that also works with the older `session_id` text field
- **Function calling** — OpenAI-compatible tool definitions
- **JSON mode** — structured JSON output with automatic extraction
- **Context window control** — configurable from 512 to 262144 tokens
- **Streaming** — robust SSE streaming with incremental UTF-8 decoder, retry logic, and server detection
- **Provider override** — explicit provider selection skips the server-type probes
- **Response post-processing** — strip whitespace, extract code blocks, truncate, remove thinking tags
- **Structured response** — 9th output slot: `KDXLLMResponse` with content, reasoning, json, tool_calls, usage, timings
- **V3 ready** — ComfyUI V3 schema adapter behind `KDX_LLM_V3=1` environment switch

## Nodes

| Node | Description |
|------|-------------|
| 🔌 **LLM Client** | Server URL, model selection, context window, API key, persistent model profile, provider override |
| 🎛️ **LLM Sampling (Simple)** | Core sampling params with per-parameter ON/OFF switches |
| 🔬 **LLM Sampling (Advanced)** | Provider-specific params: MiRoStat, repeat_last_n, thinking_budget, raw JSON override |
| ⚡ **Quick Sampling Presets** | One-click presets — balanced, creative, precise, reasoning, json_output |
| 💬 **LLM Chat** | Main chat node — model presets, prompts, thinking toggle, streaming, media, sessions, tools |
| 🔄 **LLM Session** | Session manager: create, reset, import, or pass through, save and load conversation sessions |
| 📝 **System Prompt** | Save, load, and delete reusable system prompts |
| 📋 **User Prompt** | Save, load, and delete reusable user prompts |
| 💾 **Model Profile** | Persistent per-model sampling profiles with glob pattern matching |
| ✂️ **Response Formatter** | Post-process LLM output: strip, extract code, truncate, remove thinking tags |
| 🎬 **Media Settings** | Video frame extraction and audio config for multi-modal LLMs |
| 🛠️ **LLM Tool** | Define OpenAI-compatible function-calling tools |
| 🔍 **Diagnostics** | Server health check, model list, capability detection |
| 📈 **Stats** | Token usage, generation time, tokens/second |
| 🔑 **JSON Extract** | Take one value out of a JSON answer by key (`rewritten_prompt`, `scene.lighting`, `shots.0.prompt`) |
| 🧩 **Prompt Template** | Build a prompt from a template with `{placeholders}` filled from inputs and `name = value` lines |
| 📐 **JSON Output Format** | Turn a list of fields into system-prompt instructions so the model answers with exactly those JSON keys |
| 🗂️ **JSON Fields** | Split a JSON answer into up to 6 separate text outputs (labelled with the field names) |

Every node also shows a short "what is this for" description in ComfyUI's node info panel.

Nodes are coloured by role so a graph is easy to read: **blue** = connection (Client, Model Profile,
Diagnostics), **purple** = settings (Sampling, Presets, Media, Tool), **green** = prompts,
**cyan** = Chat / Session, **pale blue** = working with the answer (JSON Extract/Fields, Formatter, Stats).
Colours you set yourself are kept.

The Chat node shows the answer inside the node — live while it streams. Less common options
(streaming, media mode, history limits, JSON sampling, load/unload) are behind the **🔧 advanced** toggle.

### Example workflows

Open **Workflow → Browse Templates** (or the Templates panel) and pick **ComfyUI-KDX-LLM**:

1. **simple chat** — Client → Chat.
2. **rewrite prompt as JSON fields** — Prompt Template + JSON Output Format → Chat → JSON Fields.
3. **conversation across two Chat nodes** — the second Chat continues the first one's conversation.
4. **describe an image** — Load Image → Chat (needs a vision model).

Select your model in the Client node (📡 select model) before running. The files live in
`example_workflows/` and are generated by `python tools_dev/build_example_workflows.py`.

### Which node do I need?

| I want to… | Use |
|------------|-----|
| connect to my LLM server and pick a model | 🔌 Client |
| ask the model something and get the answer | 💬 Chat |
| change temperature, max_tokens, seed… | 🎛️ Sampling (Simple) or ⚡ Quick Presets → Chat |
| remember settings per model | 💾 Model Profile (between Client and Chat) |
| give the model a role / rules | 📝 System Prompt → Chat `system_prompt_profile` |
| reuse a saved question | 📋 User Prompt → Chat `prompt` |
| continue a conversation | Chat `session` output → next Chat `session` input (or 🔄 Session) |
| get one field from a JSON answer (e.g. a rewritten prompt) | Chat `json` → 🔑 JSON Extract |
| get several fields from a JSON answer at once | 📐 JSON Output Format → Chat `system_prompt`; Chat `json` → 🗂️ JSON Fields |
| put text from other nodes into a prompt | 🧩 Prompt Template → Chat `prompt` |
| clean the answer text (code block, trim, remove `<think>`) | ✂️ Response Formatter |
| send an image | Chat `image` input |
| send audio or video | 🎬 Media Settings → Chat |
| find out why nothing works | 🔍 Diagnostics |
| see tokens and speed | Chat `raw` → 📈 Stats |

## Working with other KDX packs

Every KDX pack works on its own; they are built to fit together. Example workflows that use all of them come
with KDX Wildcard Studio (**4 all KDX nodes**, **5 Z-Image Turbo with LLM and Resolution**).

### KDX Wildcard Studio (prompts)

[KDX Wildcard Studio](https://github.com/korodexios/ComfyUI-KDX-Wildcard-Studio) builds the prompt from wildcard
templates; KDX LLM can rewrite it before it reaches the sampler.

```
🎛️ Wildcard Studio ── prompt ──────▶ 💬 Chat prompt
                   ── system_prompt ─▶ 💬 Chat system_prompt
                   ── llm_enabled ───▶ 💬 Chat llm_enabled
💬 Chat response ──▶ CLIP Text Encode
```

- Each Wildcard Studio category can carry a **system prompt profile**: the list comes from KDX LLM's saved
  system prompts (`ComfyUI/user/kdx_llm/system_prompts/`, see [System Prompts](#system-prompts)).
- The **LLM** switch in the Wildcard Studio panel drives Chat's `llm_enabled`: off = no LLM call, and Chat's
  `response` is the Wildcard Studio prompt unchanged. No Switch node needed.
- Use Chat's `task_prompt` for fixed instructions around the prompt (for example a prompt-enhancer template);
  it is added only while the LLM runs.

### KDX Resolution (image size)

[KDX Resolution](https://github.com/korodexios/ComfyUI-KDX-Resolution) turns an aspect ratio into a size on the
model's grid. Let the LLM choose the ratio as part of a JSON answer:

```
📐 JSON Output Format (rewritten_prompt, aspect_ratio) → 💬 Chat ── json ──▶ 🗂️ JSON Fields
🗂️ JSON Fields aspect_ratio ──▶ 🔎 AR Extractor → 🎯 AutoRes Core → Empty Latent Image
🗂️ JSON Fields rewritten_prompt ──▶ CLIP Text Encode
```

KDX Resolution's **Prompt Extractor** can also read the ratio, size and prompt straight from Chat's
`response` (`prompt_key = rewritten_prompt`, `ar_key = aspect_ratio`). If you switch the LLM off, give the
aspect ratio its own fallback (see [Turning the LLM on/off with a switch](#turning-the-llm-onoff-with-a-switch)).

## Quick Start

### Minimal workflow

```
🔌 Client (URL + model + context) → 💬 Chat (preset + prompt)
```

1. Add **LLM Client** — set server URL and model name
2. Add **LLM Chat** — select a model preset and type your prompt
3. Queue and run

### Adding sampling control

```
🎛️ Simple Sampling (enable the params you need)
    → 💬 Chat (thinking_sampling or non_thinking_sampling input)
```

Each parameter has its own ON/OFF switch. Only enabled parameters are sent to the server, keeping model defaults intact.

### JSON sampling (alternative to nodes)

The Chat node accepts JSON string inputs as an alternative to Sampling nodes:

- `sampling_json_thinking` — JSON for thinking mode (e.g., `{"temperature": 1.0, "top_p": 0.95}`)
- `sampling_json_non_thinking` — JSON for non-thinking mode
- `extra_request_json` — raw JSON merged into the entire request payload (highest priority)

Priority (lowest → highest):
1. Saved model profile
2. Connected Sampling node
3. JSON string input
4. extra_request_json

### Multi-turn conversations

Set the same `session_id` on multiple Chat nodes to share a conversation thread.
Use the 🎲 button to generate a unique session ID.

```
Chat Node 1: session_id = "chat_abc", reset_session = True  → starts conversation
Chat Node 2: session_id = "chat_abc", reset_session = False → continues conversation
```

### Session objects (DAG-safe multi-turn)

For branchable, DAG-safe session chaining, connect a `KDX_LLM_SESSION` socket
instead of using the `session_id` text field:

```
💬 Chat (session output) → 💬 Chat (session input)
```

The Chat node's 10th output is a `KDXLLMSession` object. Connect it to the
next Chat node's `session` input to continue the conversation. This is
DAG-safe (immutable) and branchable.

The 🔄 **LLM Session** node provides standalone session management:

| Action | Description |
|--------|-------------|
| `new` | Create a fresh empty session |
| `passthrough` | Pass through an incoming session unchanged |
| `reset` | Reset an incoming session to empty (preserves session_id) |
| `import_json` | Import a session from a JSON string |
| `save` | Save a connected session under `session_name` |
| `load` | Load a saved session from `session_name` |

The Session node also has UI buttons for listing saved sessions and deleting the currently named session.

### Structured response (9th output)

The Chat node's 9th output is a structured `KDXLLMResponse` object with:
- `content` — clean response text
- `thinking` — reasoning/thinking text
- `json` — parsed JSON (when JSON mode is on)
- `tool_calls` — function-calling tool calls
- `usage` — token usage stats
- `timings` — elapsed time, tokens/second

Use this for programmatic access to response metadata without parsing strings.

### Tool calls output (11th output)

The Chat node also exposes `tool_calls` as a JSON array string. This is convenient for automation when you only need the requested tool calls, without unpacking the full structured response object.

### Provider override

The Client node has a `provider` input that lets you explicitly declare the
server type, bypassing the discovery probes:

| Provider | Load endpoint | Unload endpoint |
|----------|--------------|-----------------|
| `auto` (default) | Auto-detected via HTTP probes | Auto-detected |
| `llama_cpp_router` | `/models/load` | `/models/unload` |
| `ollama` | `/api/generate` | `/api/generate` (keep_alive 0) |
| `llama_cpp` | On-demand | On-demand |
| `vllm` | On-demand | On-demand |
| `generic` | On-demand | On-demand |

Set `provider` to a known type when you already know the server — this skips
the `/v1/models` + `/api/version` + `/version` probe calls entirely.

## Sampling Merge Priority

When multiple sources provide sampling parameters, they are merged in this order:

1. **Model profile** (saved per-model defaults)
2. **Connected Sampling node** (Simple, Advanced, or Quick Presets)
3. **JSON string** (sampling_json_thinking / sampling_json_non_thinking)
4. **extra_request_json** (overrides everything)

Later sources override earlier ones for the same parameter.

## Saving Profiles

### System Prompts

```
📝 System Prompt → type prompt → set action = save → give it a name → queue
```

Later, select the saved profile from the dropdown to auto-fill.

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

### User Prompts

Same workflow as System Prompts, but for user-facing prompts.

### Model Profiles

Use the 💾 **LLM Model Profile** node to load, save, and delete persistent per-model profiles:

```
🔌 Client → 💾 Model Profile → 💬 Chat
🎛️ Simple/Advanced/Quick Sampling → 💾 Model Profile (thinking_options / non_thinking_options)
```

Use the **💾 save** button on the Model Profile node. The node reads connected sampling nodes and stores thinking/non-thinking sampling plus optional advanced request JSON under the selected model key or a suffixed key such as `model-test`.

Glob patterns are supported (e.g., `Qwen3.5-*` matches all Qwen 3.5 models).

## Context Window

The Client node sets the default context window: 512 → 262144 tokens, sent as `n_ctx`. An explicit `n_ctx` from a model profile, Advanced Sampling node, sampling JSON, or `extra_request_json` overrides the Client default.

The Chat node also has optional `max_prompt_tokens`. It trims oldest non-system history before sending the request. `0` disables trimming. System prompt and the current user message are preserved.

Token counting modes:

| Mode | Behavior |
|------|----------|
| `heuristic` | dependency-free chars/4 estimate |
| `tiktoken` | uses `tiktoken` `cl100k_base` if installed |
| `auto` | uses `tiktoken` if available, otherwise heuristic |

Install optional tokenizer support with:

```bash
pip install "comfyui-kdx-llm[tokenizer]"
```
or simply:

```bash
pip install tiktoken
```

## Model Presets

The Chat node includes presets that set defaults for thinking mode and JSON output:

| Preset | Thinking | JSON mode | Use case |
|--------|----------|-----------|----------|
| `generic` | OFF | OFF | Standard chat |
| `qwen_thinking` | ON | OFF | Qwen reasoning models |
| `qwen_json` | ON | ON | Qwen reasoning + JSON output |
| `deepseek` | ON | OFF | DeepSeek reasoning models |

The Chat node also has a tri-state `json_mode` input: `auto`, `on`, or `off`.
`auto` follows the preset; `off` can disable JSON mode even for `qwen_json`.

## Reasoning Mode

The Chat node supports per-model reasoning depth via the `reasoning_mode` input:

- `""` (empty) — default (no reasoning override)
- `auto` — use the model profile's saved reasoning setting
- `low`, `medium`, `high`, `xhigh` — standard reasoning levels
- `spoon`, `einstein` — Qwen-specific reasoning levels
- `custom` — use the value from `reasoning_custom`

For non-thinking Qwen models served through llama.cpp-style providers, values may be automatically prefixed with `i` (e.g., `low` → `ilow`) per the Qwen `chat_template_kwargs` convention. This is not applied globally to vLLM/Ollama/generic providers. You can force or disable it per profile with:

```json
{"request": {"qwen_i_prefix": true}}
```

or:

```json
{"request": {"qwen_i_prefix": false}}
```

## Response Formatting

```
💬 Chat (response output) → ✂️ Response Formatter → clean output
```

Available actions: `passthrough`, `strip_whitespace`, `extract_first_code_block`,
`extract_all_code_blocks`, `truncate`, `lowercase`, `uppercase`, `remove_thinking_tags`.

Chain multiple formatters by wiring output to input for sequential processing.

## Asking for several JSON fields

```
📐 JSON Output Format ──system_prompt──▶ 💬 Chat ──json──▶ 🗂️ JSON Fields ──field_1, field_2…──▶
         └──────────────fields────────────────────────────────┘
```

Write one field per line in **JSON Output Format**, optionally with a description:

```
rewritten_prompt: the improved, detailed image prompt
negative_prompt: things the image should avoid
```

It adds instructions to your system prompt asking for exactly those keys. **JSON Fields** then splits the
answer into separate outputs in the same order; the outputs are renamed to the field names in the editor.

## Turning the LLM on/off with a switch

Chat runs only when something downstream needs one of its outputs, so a core **Switch** node
(`ComfySwitchNode`, its inputs are lazy) can skip the LLM completely:

```
                 ┌────────────── on_false ◀── your original prompt
Boolean "enhance" ┤
                 └─ switch ──▶ Switch ──▶ CLIP Text Encode / sampler
                               on_true ◀── Chat → JSON Fields (rewritten_prompt)
```

**Every** value that comes from the LLM must go through a switch driven by the same boolean. If, for
example, `aspect_ratio` from the LLM feeds the resolution node directly, the image size needs the LLM and
Chat runs even with *enhance* off — give that value its own Switch (`on_false` = a fixed ratio such as
`2:3`, `on_true` = the LLM field) and drive both switches from one **Boolean** node.

Set/Get nodes (KJNodes) are only shortcuts in the editor; they do not force anything to run.

**Simpler, for a plain prompt chain:** connect a BOOLEAN to Chat's `llm_enabled` socket (a Boolean node, or
KDX Wildcard Studio's `llm_enabled` output). With `False` Chat makes no LLM call and its `response` is your prompt
unchanged, so the same wire feeds CLIP Text Encode either way. Not connected = LLM on. This does not cover LLM-only values such as JSON fields — those still need a Switch.

Chat is not an output node: a workflow needs an output such as **Preview as Text** (core `PreviewAny`),
Save Image or Preview Image to run. The answer is still shown inside the Chat node.

## Prompt templates

**Prompt Template** fills `{placeholders}`: `{text_1}`…`{text_4}` come from the text inputs (connect any text
output), other names from the `variables` box as `style = cinematic` lines. `{{` and `}}` give literal braces,
so JSON examples in the template are safe. Unfilled placeholders are listed in the `missing` output.

## Extracting a value from a JSON answer

```
💬 Chat (json output) → 🔑 JSON Extract (key: rewritten_prompt) → value → CLIP Text Encode
```

If the model answers `{"rewritten_prompt": "a cat on a roof, golden hour", "style": "photo"}`,
the `value` output is just `a cat on a roof, golden hour` (no quotes).

- Nested keys use dots: `scene.lighting`; list items use numbers: `shots.0.prompt` (or `shots[0].prompt`).
- Keys match exactly first, then case-insensitively.
- Plain JSON, ```` ```json ```` code blocks and JSON surrounded by other text are all accepted.
- Missing key: `value` = the `default` text and `found` = false, or set `fail_if_missing` to stop with an
  error that lists the available keys.
- `value_json` keeps the value as JSON, so you can chain another JSON Extract on an object or list.

## Conversation history and media

- `max_prompt_tokens` trims the oldest history first and never leaves an assistant reply at the start
  (templates like Gemma/Mistral require user/assistant alternation).
- `history_media` (advanced) controls images/audio from earlier turns: `latest` (default) re-sends only the
  most recent one, and none when the new message has its own; `all` re-sends everything; `none` keeps text only.
- `unload_after` frees the model even when generation fails or is cancelled.

## File Storage

If a store file (profiles, prompts, presets, sessions) is not valid JSON — for example after a manual edit —
it is copied to `<file>.corrupt-<time>.bak` before the next save overwrites it.

All saved profiles and prompts are stored in ComfyUI's user directory (`ComfyUI/user/kdx_llm/`):

| File | Content |
|------|---------|
| `model_profiles.json` | Per-model sampling profiles |
| `system_prompts/` | Named system prompts, one `.md`/`.txt` file each (see *System Prompts* above) |
| `user_prompts.json` | Named user prompts |
| `quick_sampling_presets.json` | User-defined sampling presets; an old pack-local file is migrated here once |
| `sessions.json` | Named saved conversation sessions |

Paths can be overridden via environment variables:
- `KDX_LLM_PROFILES_FILE`
- `KDX_LLM_PROMPTS_DIR` (system prompt folder)
- `KDX_LLM_USER_PROMPTS_FILE`
- `KDX_LLM_PRESETS_FILE`
- `KDX_LLM_SESSIONS_FILE`

## V3 Compatibility

The pack includes a ComfyUI V3 schema adapter (`v3_adapter.py`) behind the
`KDX_LLM_V3` environment variable:

```bash
KDX_LLM_V3=1 python main.py  # V3 mode (dev/test only)
```

By default, the pack uses the V1 registration path (`NODE_CLASS_MAPPINGS`),
which works on all ComfyUI versions and registers the full node set. The V3
path is dormant until `comfy_api` v0_0_2 stabilizes.

Current V3 mode registers custom Chat and Session adapters plus best-effort generic
adapters for the remaining V1 nodes. Unsupported node types are skipped individually
if the installed `comfy_api` version cannot represent them.

## Security

Public LLM server hosts must be explicitly whitelisted via the `KDX_ALLOWED_HOSTS` environment variable (comma-separated hostnames). Localhost, private, and link-local IP addresses are allowed by default.

The web UI proxy routes (model list, load/unload) only read the API key from `KDX_LLM_API_KEY`. If a Client node uses a different `api_key_env`, add that variable name to `KDX_ALLOWED_KEY_ENVS` (comma-separated); otherwise the request is rejected. This stops a remote caller from making ComfyUI send an arbitrary environment secret to a host of its choosing.

## Development

```bash
uv sync                       # dev environment with pytest and ruff
uv run pytest -q              # unit and HTTP integration tests (no ComfyUI needed)
uv run ruff check .
```

### Testing against a real model

```bash
python tools_dev/live_test.py --url http://127.0.0.1:8080 --model <model-id>
python tools_dev/live_test.py --url ... --model ... --only json,session,vision
```

Runs the nodes directly (no ComfyUI needed) against a real OpenAI-compatible server: chat with and without
streaming, Slovak text, JSON mode, templates and JSON fields, sessions (chaining, save/load, reset, trimming),
vision (single image, batch, greyscale), tool calling, sampling limits and stop sequences, saved prompts and
diagnostics. Saved data goes to a temporary folder. Exit code 1 when any check fails.

## Requirements

- Python 3.10+
- `requests` (HTTP client)
- `numpy` + `Pillow` (media processing — only needed when using image/video/audio inputs)

ComfyUI venvs normally already contain these. For non-ComfyUI installs:

```bash
pip install -r requirements.txt
```

## License

MIT License — see [LICENSE](LICENSE) for details.
