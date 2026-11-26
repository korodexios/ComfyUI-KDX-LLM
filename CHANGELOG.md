# Changelog

## 0.10.5 - 2026-11-26

### Changed
- Ready for the Comfy Registry: publisher `korodexios`, display name **KDX LLM**, repository URL and a fuller
  description in `pyproject.toml`; `.github/workflows/publish.yml` publishes a release to the registry.
- README: installation (ComfyUI-Manager or git clone), a section on working with KDX Wildcard Studio and
  KDX Resolution, a short Development section; internal planning notes and agent briefings left the repo.

## 0.10.4 - 2026-11-26

### Changed
- KDX Console is now called **KDX Wildcard Studio**: tooltips and docs use the new name (nothing else changes; its
  `llm_enabled` output connects as before).

## 0.10.3 - 2026-11-24

### Added
- Chat input **`task_prompt`** (STRING socket, after `llm_enabled`): fixed instructions wrapped around the
  prompt only when the LLM runs. `{}` or `{prompt}` = the prompt goes there, `{prompt_json}` = the prompt as
  a JSON string; with a placeholder the text follows `str.format` rules (`{{` / `}}` = literal braces). No
  placeholder = the prompt is added after a blank line. With `llm_enabled = False` the `response` is the
  bare prompt, without the task prompt. Fits prompt enhancers such as MiniMax-H3-Image-PE
  (`t2i/task_prompt.txt` works unchanged). `request_info` reports `task_prompt: true/false`.
- Example workflows regenerated (one more Chat widget value).

## 0.10.2 - 2026-11-23

### Changed
- Accent colour is now the KDX blue shared by every KDX pack (dark #6f8dff, light #2f4fd1); green stays
  the colour of a finished / OK state.

## 0.10.1 - 2026-11-23

### Changed
- Node icon: 🎚️ KDX • LLM Sampling (Simple) (🎛️ belongs to KDX Console). Only the display name changed;
  workflows keep working.

## 0.10.0 - 2026-11-19

### Changed
- **System prompts are files:** one `.md` (or `.txt`) per prompt in `user/kdx_llm/system_prompts/`; the file
  name is the profile name. Any text and any characters work, nothing is parsed, and prompts can be added
  or edited in a text editor. Optional descriptions live in `.descriptions.json` (a broken one only loses
  descriptions). Writes are atomic.
- `system_prompts.json` is migrated automatically on first use (kept as `system_prompts.json.migrated`;
  files that already exist are never overwritten). `KDX_LLM_PROMPTS_DIR` sets the folder.

## 0.9.0 - 2026-11-19

### Changed (breaking for workflows saved with 0.8.0)
- Chat input `passthrough` is replaced by **`llm_enabled`** (BOOLEAN socket, always visible like `client`):
  not connected or `True` = LLM runs, `False` = no LLM call and `response` is the prompt unchanged. Same
  meaning as KDX Console's `llm_enabled` output, so the two connect directly; a Boolean node works too.
  A `passthrough` link from 0.8.0 has to be reconnected to `llm_enabled`.
- The answer box shows "⏭ LLM off" (UI output `kdx_llm_off`).

### Fixed
- After an update the browser could keep the old UI module (ComfyUI sends no cache header for `.mjs`): the
  import carries `?v=<VERSION>`, checked by a test.

## 0.8.0 - 2026-11-18

### Added
- Chat input `passthrough` (BOOLEAN, last input, default `False`; widget or wire, V1 and V3). `True` = no LLM call and no model load/unload: `response` is the prompt unchanged, the other outputs are empty as in the empty-prompt bypass, and the session passes through. The node shows a "⏭ Passthrough" note in its answer box. Lets a boolean (e.g. KDX Console's `passthrough` output, 0.2.0+) switch the LLM off without bypassing the node.

### Changed
- The editor UI uses the KDX Console look: green accent, light/dark tokens that follow the ComfyUI palette. Restyled: toasts (now stacked), the model picker (status dots instead of emoji, header with count, Esc closes, opens at the click) and the saved-session picker (one shared component), and the Chat answer box. Node role colours are unchanged.
- The Chat cache hash includes `passthrough`, so every Chat re-runs once after the update.

## 0.7.2 - 2026-11-15

### Fixed
- Chat is no longer an output node (reverts the 0.7.0 change). ComfyUI always executes output nodes, so a Chat behind a lazy Switch ("enhance prompt: off") still called the LLM on every run. Chat now runs only when something downstream needs its output; the answer is still shown inside the node.
- Example workflows 1, 3 and 4 end in a **Preview as Text** node, so they still run (a graph needs an output node); a test checks every example has one.

### Docs
- README: "Turning the LLM on/off with a switch" — every LLM-derived value (e.g. `aspect_ratio` feeding the resolution) must go through a switch, otherwise the LLM is still needed.

## 0.7.1 - 2026-11-14

### Fixed
- Copying/pasting nodes or loading a workflow failed with `Invalid aux_id: Must be valid 'github-username/github-repo-name'` when the pack was cloned through an SSH host alias (deploy keys): ComfyUI-Manager stamps nodes with an `aux_id` taken from the git remote URL (`git@github-kdx:owner/repo`). The web extension now rewrites such values to `owner/repo` (or drops unrecoverable ones) when nodes are loaded or serialized — for every node type, so a whole pasted selection passes.

## 0.7.0 - 2026-11-14

### Added
- 🧩 **Prompt Template**, 📐 **JSON Output Format** and 🗂️ **JSON Fields** nodes for templated prompts and multi-field JSON answers.
- Chat shows the answer inside the node, live while streaming.
- Nodes are coloured by role; Session has its own icon (🔄).
- Four example workflows in `example_workflows/` (shown under ComfyUI templates), generated by `tools_dev/build_example_workflows.py` and checked by tests.
- Chat option `history_media` (latest / all / none) limits re-sending earlier images/audio.
- `tools_dev/live_test.py`: end-to-end check of all nodes against a real server and model (37 checks).
- An IMAGE batch sends every image (up to 16) instead of only the first.
- 🔑 **JSON Extract** node: take one value out of a JSON answer by key (`rewritten_prompt`, `scene.lighting`, `shots.0.prompt`), with `default` / `fail_if_missing` handling.
- Every node has a short `DESCRIPTION` shown in ComfyUI's node info panel (also used by the V3 adapters).
- README "Which node do I need?" table.

### Changed
- Chat's 🔧 advanced toggle also hides `stream`, `media_mode`, `max_history` and `history_media`.
- Chat's ComfyUI entry point is `execute_node` (wraps `run()` and adds UI output).

### Fixed
- A Chat without a session input or `session_id` now outputs a session containing its exchange, so `Chat 1 session → Chat 2 session` continues the conversation (it used to hand over an empty history).
- Chat is an output node, so a workflow of just Client → Chat runs (ComfyUI used to refuse it with "Prompt has no outputs"), including example workflows 1, 3 and 4.
- Chat's 🔧 advanced toggle was created with the legacy `boolean` widget type, which the current ComfyUI frontend does not draw — the advanced settings could not be opened. It is a `toggle` now and its saved state is re-applied when a workflow loads.
- The answer box in the Chat node is taller (min. 150 px) and new Chat nodes grow to fit it.
- Example workflows: nodes no longer overlap, and the Chat nodes use `thinking = off` for fast answers.
- Greyscale (2-D or 1-channel), grey+alpha, RGBA and uint8/float16 images are converted to RGB instead of failing.
- A ```python (or other non-JSON) code block is no longer parsed into the `json` output when JSON mode is off.
- Client URL validation now runs in V1 (`VALIDATE_INPUTS`); the web UI sends the Client's `provider` to the proxy routes.
- Removed leftover debug logging from the web UI and the stale `web/kdx_llm.js.bak`.
- `unload_after` runs even when generation fails or is cancelled.
- History trimming never starts with an orphaned assistant message.
- Store files that are not valid JSON are backed up instead of silently overwritten.
- Saved-name dropdowns (Model Profile, System Prompt, User Prompt, Quick Presets) no longer fail ComfyUI validation with "Value not in list" after a profile is saved, deleted, or the workflow is opened on another machine. `(none)` is always offered and unknown names fall back gracefully.
- Model Profile defaults to `(none)` and auto-matches the Client's model instead of applying the alphabetically first saved profile to any model.
- `thinking = on/off` (and non-generic presets) now always send `chat_template_kwargs.enable_thinking`, so forcing thinking off actually disables it on Qwen3-style templates even without a reasoning mode.
- Web UI proxy routes run blocking HTTP calls in a worker thread; model load (up to 300 s) no longer freezes the ComfyUI server/UI.
- V3 generic adapters pass only the declared arguments to V1 `VALIDATE_INPUTS`.

### Security
- Proxy routes only accept `api_key_env = KDX_LLM_API_KEY` or names listed in `KDX_ALLOWED_KEY_ENVS`.

## 0.6.1 - 2026-11-09

### Fixed
- Model discovery now reports clearer auth errors when `/v1/models` returns 401/403.
- Old Chat workflow values are sanitized before validation: empty INT/combo fields and old boolean `json_mode`.
- Prompt nodes preserve typed text when no saved profile is selected.
- JSON mode avoids llama.cpp `response_format` grammar failures by using a leading system instruction fallback.
- Obvious JSON/code-fence responses are parsed into the `json` output even when `json_mode` is off.
- llama.cpp load/unload no-ops such as `already running` / `not loaded` are treated as successful.
- V3 generic adapters delegate V1 `IS_CHANGED` / `VALIDATE_INPUTS` where available.

### Added
- Generic V3 adapters for remaining V1 nodes with per-node fallback.
- Saved session list/delete UI and session routes.
- Optional `tiktoken` prompt token counting mode.
- `request_info` now includes `provider` and `effective_provider`.

## 0.6.0 - 2026-11-09

### Added
- `KDX_LLM_SESSION` object path for DAG-safe multi-turn conversations.
- `KDX_LLM_Session` node for create/reset/passthrough/import actions.
- Structured `response_obj` output with content, reasoning, JSON, tool calls, usage, and timings.
- Explicit provider override on the Client node.
- `kdx_core` package for request building, response modeling, sessions, fingerprints, SSE parsing, and profile resolution.
- ComfyUI V3 adapter behind `KDX_LLM_V3=1` for Chat and Session nodes.
- Quick preset API endpoint and user-directory preset storage.
- Named session persistence via Session node `save` / `load` actions and `sessions.json`.
- Stats and Response Formatter can consume Chat `response_obj` directly when raw text is not connected.
- GitHub Actions CI workflow for compile, unit, integration, and regression tests.
- Local HTTP integration tests using a mock OpenAI-compatible server.
- Model Profile dropdown now auto-refreshes when the connected Client model changes.
- Optional heuristic `max_prompt_tokens` trimming in Chat to avoid oversized prompts.
- `request_info` now includes `prompt_token_estimate` and `max_prompt_tokens`.
- Historical planning/audit reports moved to `docs/dev/`.
- `py.typed` marker for type-aware consumers.
- Session node UI buttons for listing and deleting saved sessions.
- Chat node now exposes an 11th output `tool_calls` as a JSON array string.
- Optional `tiktoken` token counting mode for `max_prompt_tokens` (`heuristic`, `tiktoken`, `auto`).
- Generic V3 adapters for remaining V1 nodes, with per-node fallback when a `comfy_api` type is unsupported.
- Frontend migration for old Chat workflow values: empty INT fields, empty combo fields, and old boolean `json_mode` are normalized before queueing.
- Graph-wide Chat sanitization after workflow load.
- Prompt nodes preserve typed text when no saved profile is selected.
- JSON mode avoids llama.cpp `response_format` grammar failures by using an instruction fallback.
- Obvious JSON/code-fence responses are parsed into the `json` output even when `json_mode` is off.
- llama.cpp load/unload no-ops such as `already running` / `not loaded` are treated as successful.
- V3 generic adapters now delegate to V1 `IS_CHANGED` / `VALIDATE_INPUTS` where available and force side-effect nodes to re-execute.
- Packaging metadata: `pyproject.toml` and `requirements.txt`.
- Lint/test configuration: `ruff.toml`, `mypy.ini`, and `pytest.ini`.
- `__version__` is exposed and synchronized with the `VERSION` file.

### Fixed
- `json_mode` is now tri-state (`auto`, `on`, `off`) and old boolean workflows remain accepted.
- Client `context_length` no longer overrides explicit `n_ctx` from profiles or sampling nodes.
- Session fingerprints now include compact message content hashes, not only turn counts.
- Model Profile save UI no longer stores unrelated widget values from Quick Presets or Advanced Sampling.
- Qwen `i-prefix` reasoning values are no longer applied globally to all providers.
- Empty Chat bypass now returns a consistent structured response object.
- Legacy in-memory sessions are bounded with LRU/TTL and thread-safe locking.
- Tool node JSON validation now raises clear errors instead of silently ignoring invalid JSON.
- Version metadata is unified to `0.6.0`.
- Existing tests were repaired and new real-core contract tests were added.
- `load_before` no longer fails for providers that only load models on demand.
- Quick Presets save action now outputs the saved sampling options instead of an empty object.
