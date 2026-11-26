"""KDX LLM Client — connection and capability diagnostics."""

from .capabilities import (
    detect_capabilities,
    format_summary,
    capabilities_to_json,
)
from ._http import LLMClient


class KDX_LLM_Diagnostics:
    DESCRIPTION = 'Checks the connection: is the server up, what type it is, which models it has and what they support (vision, audio). Use it when something does not work.'

    CATEGORY = "KDX/LLM"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("summary", "json")
    FUNCTION = "run"

    OUTPUT_TOOLTIPS = (
        "Human-readable server/model capability summary.",
        "Structured JSON suitable for automation.",
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_url": ("STRING", {
                    "default": "http://127.0.0.1:8080",
                    "tooltip": "OpenAI-compatible server URL.",
                }),
            },
            "optional": {
                "client": ("KDX_LLM_CLIENT", {
                    "tooltip": "Use the connected Client configuration.",
                }),
                "api_key": ("STRING", {
                    "default": "",
                    "tooltip": "Optional bearer token override.",
                }),
                "api_key_env": ("STRING", {
                    "default": "KDX_LLM_API_KEY",
                    "tooltip": "Environment variable used when api_key is empty.",
                }),
                "timeout": ("INT", {
                    "default": 10,
                    "min": 2,
                    "max": 60,
                    "tooltip": "Connection timeout.",
                }),
            },
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        # Diagnostics are intentionally always evaluated.
        return float("nan")

    def run(
        self,
        base_url,
        client=None,
        api_key="",
        api_key_env="KDX_LLM_API_KEY",
        timeout=10,
    ):
        if client is not None:
            base_url = client.get("url", base_url)
            api_key = client.get("api_key", api_key)
            api_key_env = client.get("api_key_env", api_key_env)
            timeout = client.get("timeout", timeout)
            provider = client.get("provider", "auto")
        else:
            provider = "auto"

        try:
            llm = LLMClient(
                base_url,
                api_key=api_key,
                api_key_env=api_key_env,
                timeout=timeout,
                max_retries=0,
                provider=provider,
            )
            models_raw = llm.get_models_raw()
            capabilities = detect_capabilities(models_raw)
            server_info = llm.detect_server_type()
            health = llm.health()

            summary = format_summary(capabilities)
            summary += f"\n\nServer type: {server_info['type']}"
            if server_info.get("owned_by"):
                summary += f"\nOwned by: {server_info['owned_by']}"

            if server_info.get("supports_load"):
                summary += f"\nLoad API: {server_info['load_endpoint']}"
            if server_info.get("supports_unload"):
                summary += f"\nUnload API: {server_info['unload_endpoint']}"

            summary += f"\nHealth: {'ok' if health.get('ok') else 'unavailable'}"

            result = {
                "version": 1,
                "server": server_info,
                "health": health,
                "capabilities": capabilities,
            }

            return summary, capabilities_to_json(result)

        except Exception as exc:
            return f"Connection failed: {exc}", "{}"


NODE_CLASS_MAPPINGS = {
    "KDX_LLM_Diagnostics": KDX_LLM_Diagnostics,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "KDX_LLM_Diagnostics": "🔍 KDX • LLM Diagnostics",
}
