"""KDX LLM Client — connection and model selection only (dumb client).

Profile management lives in the Model Profile node. This node just carries
the connection settings and the selected model downstream.
"""

from urllib.parse import urlparse

from ._http import normalize_base_url


CONTEXT_OPTIONS = [
    "512", "1024", "2048", "4096", "8192", "16384", "32768", "65536", "131072", "262144",
]

# P2.4: explicit provider override (bypasses discovery probes).
PROVIDER_OPTIONS = [
    "auto",
    "llama_cpp_router",
    "llama_cpp",
    "ollama",
    "vllm",
    "generic",
]

class KDX_LLM_Client:
    DESCRIPTION = "Start here. Where your LLM server runs (URL), which model to use and the API key. Connect 'client' to a Chat node (or through Model Profile). Buttons: select model / load / unload."

    CATEGORY = "KDX/LLM"
    RETURN_TYPES = ("KDX_LLM_CLIENT",)
    RETURN_NAMES = ("client",)
    FUNCTION = "execute"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_url": ("STRING", {
                    "default": "http://127.0.0.1:8080",
                    "tooltip": "OpenAI-compatible server URL. /v1 is optional.",
                }),
            },
            "optional": {
                "model": ("STRING", {
                    "default": "",
                    "tooltip": "Model ID. Use the Select Model button in the node UI.",
                }),
                "context_length": (CONTEXT_OPTIONS, {
                    "default": "4096",
                    "tooltip": "Context window size in tokens. Sent as n_ctx in the request payload.",
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "Bearer token. Leave empty to use the environment variable.",
                }),
                "api_key_env": ("STRING", {
                    "default": "KDX_LLM_API_KEY",
                    "tooltip": "Environment variable used when api_key is empty.",
                }),
                "timeout": ("INT", {
                    "default": 300,
                    "min": 5,
                    "max": 3600,
                    "tooltip": "Request timeout in seconds.",
                }),
                "max_retries": ("INT", {
                    "default": 2,
                    "min": 0,
                    "max": 10,
                    "tooltip": "Retries for failed non-streaming requests.",
                }),
                "provider": (PROVIDER_OPTIONS, {
                    "default": "auto",
                    "tooltip": "Explicit server provider override. 'auto' probes endpoints; other values bypass discovery probes and set lifecycle APIs directly.",
                }),
            },
        }

    @classmethod
    def VALIDATE_INPUTS(cls, base_url):
        """V1 hook (ComfyUI calls the UPPERCASE name); rejects URLs without scheme/host."""
        return cls.validate_inputs(base_url)

    @classmethod
    def validate_inputs(cls, base_url, **_kwargs):
        if base_url is None:
            return True
        try:
            parsed = urlparse(base_url.strip())
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                return "URL must contain an http or https scheme and a host"
        except Exception:
            return "Invalid URL"
        return True

    def execute(
        self,
        base_url,
        model="",
        context_length="4096",
        api_key="",
        api_key_env="KDX_LLM_API_KEY",
        timeout=300,
        max_retries=2,
        provider="auto",
    ):
        model = (model or "").strip()

        client = {
            "url": normalize_base_url(base_url),
            "model": model,
            "context_length": int(context_length),
            "api_key": api_key or "",
            "api_key_env": (api_key_env or "").strip(),
            "timeout": int(timeout),
            "max_retries": int(max_retries),
            "provider": (provider or "auto").strip().lower(),
        }
        return (client,)


NODE_CLASS_MAPPINGS = {"KDX_LLM_Client": KDX_LLM_Client}
NODE_DISPLAY_NAME_MAPPINGS = {"KDX_LLM_Client": "🔌 KDX • LLM Client"}
