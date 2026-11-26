# KDX LLM — Architecture

## Layered Design

```
┌─────────────────────────────────────────────────────────────┐
│  ComfyUI Node Layer (V1 + V3 adapters)                       │
│  chat.py, client.py, session_node.py, options.py, ...       │
│  — thin wrappers: INPUT_TYPES, execute(), RETURN_TYPES       │
├─────────────────────────────────────────────────────────────┤
│  kdx_core/ — schema-agnostic business logic                  │
│  profile_resolver.py  — 4-tier profile matching              │
│  sse_parser.py        — SSE streaming, incremental UTF-8     │
│  request_builder.py   — payload construction, sampling merge │
│  response.py          — KDXLLMResponse dataclass             │
│  session.py           — KDXLLMSession (immutable)            │
│  fingerprint.py       — canonical hash for cache keys        │
├─────────────────────────────────────────────────────────────┤
│  _http.py — HTTP transport                                   │
│  LLMClient, KNOWN_PROVIDERS, detect_server_type,            │
│  load_model, unload_model, chat (streaming + non-streaming)  │
├─────────────────────────────────────────────────────────────┤
│  Storage layer (JSON files on disk)                          │
│  sampling_store.py, prompt_store.py, user_prompt_store.py   │
└─────────────────────────────────────────────────────────────┘
```

**Key principle:** `kdx_core/` has zero ComfyUI imports. It is pure Python
and can be unit-tested without a ComfyUI runtime. V1 and V3 nodes are thin
adapters calling into `kdx_core`.

## Data Flow (Chat node, single turn)

```
Client node ──→ KDX_LLM_CLIENT dict (url, model, provider, profile_key, ...)
                    │
                    ▼
Chat node.run()
  1. Resolve model preset (thinking/json_mode defaults)
  2. Look up model profile (sampling_store.lookup or client profile)
  3. Resolve session source:
     - KDX_LLM_SESSION socket connected? → object path (DAG-safe)
     - else → legacy in-memory store (session_id string)
  4. Build messages list: [system?, ...session_history, user]
  5. build_chat_payload() → (payload dict, effective_sampling dict)
     - merge: profile → node sampling → JSON string → extra_request_json
  6. Optional: llm.load_model() if load_before=True
  7. llm.chat(payload) → streaming or non-streaming
  8. parse_response() → {response, thinking, json, tool_calls, ...}
  9. Build KDXLLMResponse (9th output)
 10. Build updated KDXLLMSession (10th output)
     - object path: sess.add_exchange(user, assistant)
     - legacy path: store.add_exchange() → bridge into KDXLLMSession
 11. Optional: llm.unload_model() if unload_after=True
 12. Return 10-tuple
```

## File Map

| File | Role | Key exports |
|------|------|-------------|
| `__init__.py` | Node registration, `VERSION` | `NODE_CLASS_MAPPINGS` (15 mappings: 14 display nodes + legacy alias) |
| `chat.py` | Main Chat node | `KDX_LLM_Chat` |
| `client.py` | Client node (URL, model, provider) | `KDX_LLM_Client`, `PROVIDER_OPTIONS` |
| `_http.py` | HTTP transport, SSE, provider detection | `LLMClient`, `KNOWN_PROVIDERS` |
| `session_node.py` | Session manager node | `KDX_LLM_Session` |
| `options.py` | Simple Sampling node | `KDX_LLM_Simple_Sampling` |
| `quick_sampling_node.py` | Quick Presets node | `KDX_LLM_Quick_Presets` |
| `model_profile_node.py` | Model Profile node | `KDX_LLM_Model_Profile` |
| `system_prompt_node.py` | System Prompt node | `KDX_LLM_System_Prompt` |
| `user_prompt_node.py` | User Prompt node | `KDX_LLM_User_Prompt` |
| `media_settings.py` | Media Settings node | `KDX_LLM_Media_Settings` |
| `response_formatter.py` | Response Formatter node | `KDX_LLM_Response_Formatter` |
| `stats.py` | Stats node | `KDX_LLM_Stats` |
| `diagnostics.py` | Diagnostics node | `KDX_LLM_Diagnostics` |
| `tools.py` | Tool node | `KDX_LLM_Tool` |
| `v3_adapter.py` | V3 schema adapter | `KDXLLMV3Extension`, `comfy_entrypoint` |
| `server_routes.py` | ComfyUI server routes | `_client_from_body` |
| `postprocess.py` | Response parsing | `parse_response` |
| `media.py` | Media encoding (image/video/audio → base64) | `build_user_content` |
| `sampling_store.py` | Profile persistence | `lookup()`, `save()`, `mtime()` |
| `prompt_store.py` | System prompt persistence | `lookup()`, `save()`, `mtime()` |
| `user_prompt_store.py` | User prompt persistence | `lookup()`, `save()`, `mtime()` |
| `session.py` | Legacy in-memory session store | `get_session()`, `add_exchange()`, `reset_session()`, `new_session_id()` |

### `kdx_core/`

| File | Role | Key exports |
|------|------|-------------|
| `profile_resolver.py` | 4-tier profile matching | `resolve_profile(model)` |
| `sse_parser.py` | SSE streaming, incremental UTF-8 | `SSEAccumulator`, `parse_sse()` |
| `request_builder.py` | Payload + sampling merge | `build_chat_payload()` |
| `response.py` | Structured response | `KDXLLMResponse` |
| `session.py` | Immutable session | `KDXLLMSession` |
| `fingerprint.py` | Canonical hash | `build_fingerprint_key()`, `canonical_hash()` |

## Custom Types (V1)

These are the wire types between nodes in V1 mode:

| Type | Producer | Consumer | Payload |
|------|----------|----------|---------|
| `KDX_LLM_CLIENT` | Client | Chat, Diagnostics | `{url, model, api_key, api_key_env, timeout, max_retries, context_length, provider, profile_key, profile}` |
| `KDX_LLM_OPTIONS` | Sampling nodes | Chat | `{options: {temperature, top_p, ...}}` |
| `KDX_LLM_TOOLS` | Tool | Chat | `{tools: [{type: "function", function: {...}}]}` |
| `KDX_LLM_MEDIA` | Media Settings | Chat | `{video, audio, video_frame_step, ...}` |
| `KDX_LLM_SESSION` | Chat, Session node | Chat, Session node | `KDXLLMSession` instance |

## Caching (V1)

The Chat node implements `IS_CHANGED` as a canonical hash of all inputs plus
store mtimes (`sampling_store.mtime()`, `prompt_store.mtime()`,
`user_prompt_store.mtime()`). ComfyUI's V1 cache uses this to decide whether
to re-run the node. Same inputs + unchanged stores = cache hit.

In V3 mode, the equivalent is `fingerprint_inputs` (same `build_fingerprint_key`
+ `canonical_hash`).

## Security

Public LLM server hosts must be whitelisted via `KDX_ALLOWED_HOSTS`
(comma-separated hostnames). Localhost, private, and link-local IPs are
allowed by default. See `_http.py` → `_is_host_allowed()`.
