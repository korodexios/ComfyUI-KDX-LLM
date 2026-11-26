# KDX LLM — Provider Override

## Why

By default, the `LLMClient` probes the server to detect its type
(`/v1/models`, `/api/version`, `/version`). This works but adds latency and
HTTP calls. If you **know** your server type, set the `provider` input on the
Client node to bypass discovery entirely.

## `PROVIDER_OPTIONS`

**File:** `client.py`

```python
PROVIDER_OPTIONS = ["auto", "llama_cpp_router", "llama_cpp", "ollama", "vllm", "generic"]
```

| Provider | Description |
|----------|-------------|
| `auto` (default) | Auto-detect via HTTP probes |
| `llama_cpp_router` | Multi-model llama.cpp router (2-GPU setup) |
| `llama_cpp` | Single llama.cpp server |
| `ollama` | Ollama server |
| `vllm` | vLLM server |
| `generic` | Unknown / OpenAI-compatible |

## `KNOWN_PROVIDERS`

**File:** `_http.py`

```python
KNOWN_PROVIDERS = {
    "llama_cpp_router": _server_info(
        "llama_cpp_router",
        load="/models/load",
        unload="/models/unload",
    ),
    "ollama": _server_info(
        "ollama",
        load="/api/generate",
        unload="/api/generate",  # keep_alive 0
    ),
    "llama_cpp":  _server_info("llama_cpp"),
    "vllm":       _server_info("vllm"),
    "generic":    _server_info("generic"),
}
```

### Lifecycle Endpoints

| Provider | `load_model` | `unload_model` |
|----------|-------------|----------------|
| `llama_cpp_router` | `POST /models/load` | `POST /models/unload` |
| `ollama` | `POST /api/generate` (keep_alive) | `POST /api/generate` (keep_alive=0) |
| `llama_cpp` | On-demand (no explicit load) | On-demand (no explicit unload) |
| `vllm` | On-demand | On-demand |
| `generic` | On-demand | On-demand |

## How It Works

**File:** `_http.py` → `LLMClient.__init__()` + `detect_server_type()`

```python
class LLMClient:
    def __init__(self, base_url, *, api_key="", api_key_env="KDX_LLM_API_KEY",
                 timeout=300, max_retries=2, provider="auto"):
        ...
        self.provider = provider  # stored

    def detect_server_type(self):
        # If provider is explicitly set (not "auto"), return KNOWN_PROVIDERS
        # immediately — NO HTTP calls.
        if self.provider in KNOWN_PROVIDERS:
            return dict(KNOWN_PROVIDERS[self.provider])  # copy, not reference

        # Otherwise: probe /v1/models, /api/version, /version
        # (existing TTL-cached detection logic)
        ...
```

**Key guarantee:** when `provider != "auto"`, `detect_server_type()` makes
**zero HTTP requests**. The return value is a **copy** of the `KNOWN_PROVIDERS`
entry (mutating it doesn't affect the module-level dict).

## Wiring

The `provider` value flows through:

```
Client node (provider input)
  → KDX_LLM_CLIENT dict (provider field)
    → Chat node: LLMClient(..., provider=provider)
    → server_routes.py: _client_from_body() → LLMClient(..., provider=)
    → diagnostics.py: LLMClient(..., provider=)
```

## Example: 2-GPU llama.cpp Router

```
Client(
    url="http://localhost:8080",
    model="Qwen3.5-27B",
    provider="llama_cpp_router"  # ← no probes, direct /models/load + /models/unload
)
```

The router's load/unload endpoints are used directly. No `/v1/models` or
`/api/version` calls.

## Security Note

Provider override is a **convenience for known servers**. It does not bypass
the `KDX_ALLOWED_HOSTS` host whitelist. The host check in `_is_host_allowed()`
still applies regardless of provider.
