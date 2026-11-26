"""KDX LLM Client — transport layer for OpenAI-compatible chat servers.

The core API is deliberately provider-neutral: Chat Completions and Models are
used for interoperability. Provider-specific lifecycle APIs are optional and
detected at runtime.
"""

import json
import os
import time

try:
    import requests
except ImportError:
    requests = None


_DETECT_TTL = 60.0
_detect_cache = {}


def _check_interrupt():
    """Let ComfyUI's Cancel button abort a running generation."""
    try:
        import comfy.model_management as mm
    except ImportError:
        return
    mm.throw_exception_if_processing_interrupted()


def _raise_for_status(r):
    if r.status_code < 400:
        return
    try:
        detail = r.text[:1000].strip()
    except Exception:
        detail = ""
    raise requests.exceptions.HTTPError(
        f"HTTP {r.status_code} from {r.url}: {detail}", response=r
    )


def normalize_base_url(base_url: str) -> str:
    """Normalize a provider base URL to its host root.

    Users may enter either http://host:port or http://host:port/v1.
    """
    if not base_url:
        return ""
    url = base_url.strip().rstrip("/")
    if url.endswith("/v1"):
        url = url[:-3].rstrip("/")
    return url


def _server_info(kind, owned_by="", load=None, unload=None):
    return {
        "type": kind,
        "owned_by": owned_by,
        "supports_load": load is not None,
        "load_endpoint": load,
        "supports_unload": unload is not None,
        "unload_endpoint": unload,
    }


# P2.4: explicit provider override — bypasses all discovery HTTP calls.
KNOWN_PROVIDERS = {
    "llama_cpp_router": _server_info("llama_cpp_router", load="/models/load", unload="/models/unload"),
    "ollama": _server_info("ollama", load="/api/generate", unload="/api/generate"),
    "llama_cpp": _server_info("llama_cpp"),
    "vllm": _server_info("vllm"),
    "generic": _server_info("generic"),
}


class LLMClient:
    """Client for OpenAI-compatible /v1/chat/completions servers.

    Works with single-model servers and model routers. Ollama's native
    lifecycle endpoint is used only for optional load/unload operations.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        timeout: int = 300,
        max_retries: int = 2,
        api_key_env: str = "KDX_LLM_API_KEY",
        provider: str = "auto",
    ):
        if requests is None:
            raise ImportError(
                "KDX LLM: 'requests' is not installed. "
                "Install it in the Python environment used by ComfyUI."
            )
        self.base_url = normalize_base_url(base_url)
        env_name = (api_key_env or "KDX_LLM_API_KEY").strip()
        self.api_key = api_key or os.environ.get(env_name, "")
        self.timeout = max(1, int(timeout))
        self.max_retries = max(0, int(max_retries))
        self.provider = (provider or "auto").strip().lower()
        self._session = requests.Session()

    def _headers(self):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _get(self, path, timeout=10):
        return self._session.get(
            f"{self.base_url}{path}",
            headers=self._headers(),
            timeout=timeout,
        )

    def _post(self, path, body, timeout=15, stream=False):
        return self._session.post(
            f"{self.base_url}{path}",
            json=body,
            headers=self._headers(),
            timeout=timeout,
            stream=stream,
        )

    # ── Chat ───────────────────────────────────────────────────────────

    def chat(self, payload: dict, on_progress=None) -> dict:
        """Send a chat completion and always return a non-streaming-shaped dict.

        Streaming requests are intentionally not retried after the HTTP
        request starts. Retrying a partially consumed generation can duplicate
        work or produce two different answers.

        ``on_progress(content, reasoning)`` is called while a streamed answer
        arrives (live preview); errors in the callback never stop generation.
        """
        url = f"{self.base_url}/v1/chat/completions"
        stream = bool(payload.get("stream", False))

        if stream:
            return self._chat_stream(url, payload, on_progress=on_progress)

        retryable = (requests.exceptions.ConnectionError, requests.exceptions.Timeout)
        last_exc = None

        for attempt in range(self.max_retries + 1):
            try:
                return self._chat_single(url, payload)
            except retryable as exc:
                last_exc = exc
            except requests.exceptions.HTTPError as exc:
                if exc.response is not None and exc.response.status_code < 500:
                    raise
                last_exc = exc

            if attempt < self.max_retries:
                time.sleep(min(1.5 * (attempt + 1), 8.0))

        raise ConnectionError(
            f"KDX LLM: request failed after {self.max_retries + 1} attempts: {last_exc}"
        )

    def _chat_single(self, url, payload):
        r = self._session.post(
            url,
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
        )
        try:
            _raise_for_status(r)
            return r.json()
        finally:
            r.close()

    def _chat_stream(self, url, payload, on_progress=None):
        payload = dict(payload)
        payload["stream"] = True

        # This is standard OpenAI-compatible behaviour and is understood by
        # current vLLM/llama.cpp implementations. A provider can override it
        # through the generic request JSON/profile if necessary.
        stream_options = dict(payload.get("stream_options") or {})
        stream_options.setdefault("include_usage", True)
        payload["stream_options"] = stream_options

        from .kdx_core.sse_parser import SSEAccumulator

        r = self._session.post(
            url,
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
            stream=True,
        )

        accumulator = SSEAccumulator(check_interrupt=_check_interrupt)

        try:
            _raise_for_status(r)
            for raw_chunk in r.iter_content(chunk_size=4096, decode_unicode=False):
                _check_interrupt()
                if not raw_chunk:
                    continue
                done = accumulator.feed_bytes(raw_chunk)
                if on_progress is not None:
                    try:
                        on_progress(accumulator.content, accumulator.reasoning)
                    except Exception:
                        pass
                if done:
                    break
        except requests.exceptions.RequestException:
            raise
        finally:
            r.close()

        return accumulator.build_response()

    # ── Models / health / server detection ─────────────────────────────

    def get_models_raw(self) -> list:
        r = self._get("/v1/models")
        try:
            _raise_for_status(r)
            data = r.json()
        finally:
            r.close()

        models = data.get("data", []) if isinstance(data, dict) else []
        return models if isinstance(models, list) else []

    def get_models(self) -> list:
        return [
            str(m.get("id", ""))
            for m in self.get_models_raw()
            if m.get("id")
        ]

    def health(self) -> dict:
        """Return a small, provider-neutral health result."""
        try:
            r = self._get("/health", timeout=5)
            try:
                data = r.json() if r.content else {}
            except ValueError:
                data = {}
            return {
                "ok": r.status_code < 400,
                "status_code": r.status_code,
                "data": data,
            }
        except requests.exceptions.RequestException as exc:
            return {"ok": False, "status_code": 0, "error": str(exc)}

    def _probe_json(self, path, timeout=3):
        try:
            r = self._get(path, timeout=timeout)
            try:
                if r.status_code != 200:
                    return None
                data = r.json()
                return data if isinstance(data, dict) else None
            finally:
                r.close()
        except Exception:
            return None

    def detect_server_type(self) -> dict:
        """Best-effort server identification.

        Detection is advisory. Core chat functionality never depends on the
        detected provider name.

        P2.4: if an explicit ``provider`` override is set (not "auto"), return
        its predefined server info immediately — no HTTP discovery calls.
        """
        # P2.4: explicit provider override bypasses all discovery probes.
        if self.provider in KNOWN_PROVIDERS:
            return dict(KNOWN_PROVIDERS[self.provider])

        cached = _detect_cache.get(self.base_url)
        if cached and time.time() - cached[0] < _DETECT_TTL:
            return cached[1]

        try:
            models = self.get_models_raw()
        except Exception:
            info = _server_info("unknown")
            _detect_cache[self.base_url] = (time.time(), info)
            return info

        owned_values = {
            str(m.get("owned_by", "")).lower()
            for m in models
            if m.get("owned_by")
        }

        # llama.cpp router exposes status on model records and uses its own
        # /models lifecycle endpoints.
        if any(isinstance(m.get("status"), dict) for m in models):
            info = _server_info(
                "llama_cpp_router",
                next(iter(owned_values), ""),
                "/models/load",
                "/models/unload",
            )
        elif "llamacpp" in owned_values or "llama.cpp" in owned_values:
            info = _server_info("llama_cpp", next(iter(owned_values), ""))
        elif self._probe_json("/api/version") is not None:
            info = _server_info(
                "ollama",
                next(iter(owned_values), ""),
                "/api/generate",
                "/api/generate",
            )
        elif self._probe_json("/version") is not None:
            info = _server_info("vllm", next(iter(owned_values), ""))
        else:
            info = _server_info("unknown", next(iter(owned_values), ""))

        _detect_cache[self.base_url] = (time.time(), info)
        return info

    # ── Optional lifecycle operations ─────────────────────────────────

    def unload_model(self, model: str) -> dict:
        if not model:
            return {"status": "failed", "method": "unknown", "detail": "Model is empty"}

        kind = self.detect_server_type()["type"]

        try:
            if kind == "llama_cpp_router":
                r = self._post("/models/unload", {"model": model}, timeout=30)
                try:
                    _raise_for_status(r)
                except requests.exceptions.HTTPError as exc:
                    msg = str(exc).lower()
                    if "not loaded" in msg or "not running" in msg or "not found" in msg:
                        return {
                            "status": "ok",
                            "method": kind,
                            "model": model,
                            "detail": "not loaded",
                        }
                    raise
                finally:
                    r.close()
                return {"status": "ok", "method": kind, "model": model}

            if kind == "ollama":
                r = self._post(
                    "/api/generate",
                    {"model": model, "prompt": "", "stream": False, "keep_alive": 0},
                    timeout=30,
                )
                try:
                    _raise_for_status(r)
                finally:
                    r.close()
                return {"status": "ok", "method": kind, "model": model}

            return {
                "status": "unsupported",
                "method": kind,
                "model": model,
                "detail": f"Server type '{kind}' does not expose a generic unload API.",
            }

        except requests.exceptions.RequestException as exc:
            return {
                "status": "failed",
                "method": kind,
                "model": model,
                "detail": str(exc),
            }

    def load_model(self, model: str, wait: bool = True, wait_timeout: int = 300) -> dict:
        if not model:
            return {"status": "failed", "method": "unknown", "detail": "Model is empty"}

        kind = self.detect_server_type()

        try:
            if kind["type"] == "llama_cpp_router":
                r = self._post(
                    "/models/load",
                    {"model": model},
                    timeout=min(max(wait_timeout, 30), 600),
                )
                try:
                    _raise_for_status(r)
                except requests.exceptions.HTTPError as exc:
                    if "already running" in str(exc).lower():
                        loaded = self._wait_loaded(model, wait_timeout) if wait else True
                        return {
                            "status": "ok",
                            "method": kind["type"],
                            "model": model,
                            "loaded": loaded,
                            "detail": "already running",
                        }
                    raise
                finally:
                    r.close()

                loaded = self._wait_loaded(model, wait_timeout) if wait else False
                return {
                    "status": "ok" if loaded or not wait else "timeout",
                    "method": kind["type"],
                    "model": model,
                    "loaded": loaded,
                }

            if kind["type"] == "ollama":
                r = self._post(
                    "/api/generate",
                    {
                        "model": model,
                        "prompt": "",
                        "stream": False,
                        "keep_alive": "5m",
                    },
                    timeout=wait_timeout if wait else 10,
                )
                try:
                    _raise_for_status(r)
                finally:
                    r.close()
                return {
                    "status": "ok",
                    "method": kind["type"],
                    "model": model,
                    "loaded": True,
                }

            return {
                "status": "unsupported",
                "method": kind["type"],
                "model": model,
                "loaded": False,
                "detail": (
                    f"Server type '{kind['type']}' has no generic explicit load API; "
                    "the model is loaded on demand by the first request."
                ),
            }

        except requests.exceptions.Timeout:
            return {
                "status": "timeout",
                "method": kind["type"],
                "model": model,
                "loaded": False,
            }
        except requests.exceptions.RequestException as exc:
            return {
                "status": "failed",
                "method": kind["type"],
                "model": model,
                "detail": str(exc),
            }

    def _wait_loaded(self, model: str, timeout: int) -> bool:
        deadline = time.time() + max(1, timeout)

        while time.time() < deadline:
            _check_interrupt()
            try:
                for item in self.get_models_raw():
                    if item.get("id") != model:
                        continue

                    state = (item.get("status") or {}).get("value", "")
                    if state in {"loaded", "sleeping"}:
                        return True
                    if state in {"failed", "error"}:
                        return False
            except Exception:
                pass

            time.sleep(1.0)

        return False
