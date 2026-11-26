"""KDX LLM Client — ComfyUI-side HTTP proxy for the web UI.

The browser cannot reliably call arbitrary LLM servers because of CORS. These
small proxy routes run inside ComfyUI and reuse the same Python client as the
Chat node.

Security:
- localhost/private/link-local targets are allowed by default
- public hosts must be explicitly listed in KDX_ALLOWED_HOSTS
- request API keys are accepted only in POST bodies, never query strings
- ``api_key_env`` from a request may only name KDX_LLM_API_KEY or a variable
  listed in KDX_ALLOWED_KEY_ENVS, so a caller cannot make the proxy send an
  arbitrary environment secret (e.g. OPENAI_API_KEY) to a host it chooses
- blocking HTTP calls run in a worker thread so they never stall ComfyUI's
  aiohttp event loop (UI, websocket, queue)
"""

import asyncio
import ipaddress
import os
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    requests = None

from aiohttp import web
from server import PromptServer

from ._http import LLMClient, normalize_base_url
from . import prompt_store
from . import user_prompt_store
from . import sampling_store
from . import quick_sampling_presets
from . import session_store
from .kdx_core.profile_resolver import match_all_profiles
import json


def _allowed_hosts() -> set[str]:
    env = os.environ.get("KDX_ALLOWED_HOSTS", "")
    return {
        host.strip().lower()
        for host in env.split(",")
        if host.strip()
    }


def _url_allowed(url: str) -> bool:
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"}:
            return False
        if parsed.username or parsed.password:
            return False
    except Exception:
        return False

    if not host:
        return False

    if host in _allowed_hosts():
        return True

    try:
        address = ipaddress.ip_address(host)
        return (
            address.is_private
            or address.is_loopback
            or address.is_link_local
        )
    except ValueError:
        return host in {"localhost", "localhost.localdomain"}


def _resolve_url(url: str) -> str:
    normalized = normalize_base_url(url)
    if not normalized:
        raise ValueError("URL is empty")

    if not _url_allowed(normalized):
        raise ValueError(
            "Target host is not allowed. Add the hostname to KDX_ALLOWED_HOSTS "
            "if this is an intentional public/external endpoint."
        )

    return normalized


DEFAULT_KEY_ENV = "KDX_LLM_API_KEY"


def _allowed_key_envs() -> set[str]:
    env = os.environ.get("KDX_ALLOWED_KEY_ENVS", "")
    names = {name.strip() for name in env.split(",") if name.strip()}
    names.add(DEFAULT_KEY_ENV)
    return names


def _resolve_key_env(name: str) -> str:
    name = (name or "").strip() or DEFAULT_KEY_ENV
    if name not in _allowed_key_envs():
        raise ValueError(
            f"api_key_env '{name}' is not allowed for web UI requests. "
            "Use KDX_LLM_API_KEY or add the variable name to KDX_ALLOWED_KEY_ENVS."
        )
    return name


async def _run_blocking(func, *args, **kwargs):
    """Run a blocking (requests-based) call off the event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)


def _body_value(body: dict, key: str, default=""):
    value = body.get(key, default)
    return value if isinstance(value, str) else default


def _error_message(exc: Exception) -> str:
    msg = str(exc)
    lowered = msg.lower()
    if "401" in lowered or "authentication" in lowered or "api key" in lowered:
        msg += " — check the API key in the Client node or set KDX_LLM_API_KEY in the ComfyUI environment."
    elif "403" in lowered:
        msg += " — the server rejected the request; check API key or host permissions."
    return msg


def _client_from_body(body: dict) -> LLMClient:
    url = _resolve_url(_body_value(body, "url", "http://127.0.0.1:8080"))
    api_key = _body_value(body, "api_key", "")
    api_key_env = _resolve_key_env(_body_value(body, "api_key_env", DEFAULT_KEY_ENV))
    provider = _body_value(body, "provider", "auto") or "auto"

    return LLMClient(
        url,
        api_key=api_key,
        api_key_env=api_key_env,
        timeout=int(body.get("timeout", 30) or 30),
        max_retries=0,
        provider=provider,
    )


def _model_rows(models: list[dict]) -> list[dict]:
    result = []

    for model in models:
        if not isinstance(model, dict):
            continue

        architecture = model.get("architecture")
        architecture = architecture if isinstance(architecture, dict) else {}

        status = model.get("status")
        status = status.get("value", "unknown") if isinstance(status, dict) else "unknown"

        result.append({
            "id": model.get("id", ""),
            "status": status,
            "owned_by": model.get("owned_by", ""),
            "input_modalities": architecture.get("input_modalities", []),
            "output_modalities": architecture.get("output_modalities", []),
        })

    return result


def setup_routes():
    """Register routes once during plugin import."""
    routes = PromptServer.instance.routes

    @routes.get("/kdx_llm/prompts")
    async def get_prompt_profiles(request):
        return web.json_response({"status": "ok", "profiles": prompt_store.names(), "mtime": prompt_store.mtime()})

    @routes.get("/kdx_llm/user-prompts")
    async def get_user_prompt_profiles(request):
        return web.json_response({"status": "ok", "profiles": user_prompt_store.names(), "mtime": user_prompt_store.mtime()})

    @routes.post("/kdx_llm/models")
    async def get_models(request):
        try:
            body = await request.json()
            client = _client_from_body(body)
            models = await _run_blocking(client.get_models_raw)
            server = await _run_blocking(client.detect_server_type)

            return web.json_response({
                "status": "ok",
                "models": _model_rows(models),
                "server": server,
            })
        except Exception as exc:
            return web.json_response({
                "status": "error",
                "models": [],
                "error": _error_message(exc),
            }, status=400)

    # Backward-compatible GET endpoint for older installed web code.
    @routes.get("/kdx_llm/models")
    async def get_models_legacy(request):
        try:
            body = {
                "url": request.query.get("url", "http://127.0.0.1:8080"),
            }
            client = _client_from_body(body)
            models = await _run_blocking(client.get_models_raw)
            server = await _run_blocking(client.detect_server_type)
            return web.json_response({
                "status": "ok",
                "models": _model_rows(models),
                "server": server,
            })
        except Exception as exc:
            return web.json_response({
                "status": "error",
                "models": [],
                "error": _error_message(exc),
            }, status=400)

    @routes.post("/kdx_llm/running")
    async def get_running(request):
        try:
            body = await request.json()
            client = _client_from_body(body)
            models = await _run_blocking(client.get_models_raw)
            running = [
                model.get("id", "")
                for model in models
                if (model.get("status") or {}).get("value")
                in {"loaded", "loading", "sleeping"}
            ]
            return web.json_response({
                "status": "ok",
                "running": running,
                "server": await _run_blocking(client.detect_server_type),
            })
        except Exception as exc:
            return web.json_response({
                "status": "error",
                "running": [],
                "error": str(exc),
            }, status=400)

    @routes.get("/kdx_llm/running")
    async def get_running_legacy(request):
        try:
            client = _client_from_body({
                "url": request.query.get("url", "http://127.0.0.1:8080"),
            })
            models = await _run_blocking(client.get_models_raw)
            running = [
                model.get("id", "")
                for model in models
                if (model.get("status") or {}).get("value")
                in {"loaded", "loading", "sleeping"}
            ]
            return web.json_response({"running": running})
        except Exception as exc:
            return web.json_response({
                "running": [],
                "error": str(exc),
            }, status=400)

    @routes.post("/kdx_llm/load")
    async def do_load(request):
        try:
            body = await request.json()
            model = _body_value(body, "model", "").strip()
            if not model:
                raise ValueError("Model is empty")

            client = _client_from_body(body)
            result = await _run_blocking(
                client.load_model,
                model,
                wait=bool(body.get("wait", True)),
                wait_timeout=int(body.get("wait_timeout", 300) or 300),
            )
            return web.json_response(result)
        except Exception as exc:
            return web.json_response({
                "status": "error",
                "error": str(exc),
            }, status=400)

    @routes.get("/kdx_llm/sessions")
    async def get_sessions(request):
        return web.json_response({
            "status": "ok",
            "sessions": session_store.names(),
            "mtime": session_store.mtime(),
        })

    @routes.post("/kdx_llm/sessions/delete")
    async def delete_session(request):
        try:
            body = await request.json()
            name = _body_value(body, "name", "").strip()
            if not name:
                raise ValueError("Session name is empty")
            deleted = session_store.delete(name)
            return web.json_response({
                "status": "ok" if deleted else "not_found",
                "deleted": deleted,
                "name": name,
            })
        except Exception as exc:
            return web.json_response({
                "status": "error",
                "error": str(exc),
            }, status=400)

    @routes.get("/kdx_llm/presets")
    async def get_sampling_presets(request):
        name = request.query.get("name", "")
        if name:
            return web.json_response({
                "status": "ok",
                "name": name,
                "params": quick_sampling_presets.get_preset(name),
                "mtime": quick_sampling_presets.mtime(),
            })
        return web.json_response({
            "status": "ok",
            "presets": quick_sampling_presets.list_presets(),
            "mtime": quick_sampling_presets.mtime(),
        })

    @routes.get("/kdx_llm/profiles")
    async def get_model_profiles(request):
        model = request.query.get("model", "")
        models = sampling_store._read()
        result = match_all_profiles(model, models)
        return web.json_response({"status": "ok", "profiles": result, "mtime": sampling_store.mtime()})

    @routes.post("/kdx_llm/profiles/save")
    async def save_model_profile(request):
        try:
            body = await request.json()
            model = (body.get("model") or "").strip()
            key = (body.get("key") or model).strip() or model
            profile = body.get("profile")
            if not model or not isinstance(profile, dict):
                raise ValueError("model and profile are required")
            if not sampling_store.save_profile(key, profile):
                raise RuntimeError(f"Could not save model profile '{key}'.")
            return web.json_response({"status": "ok", "key": key})
        except Exception as exc:
            return web.json_response({"status": "error", "error": str(exc)}, status=400)

    @routes.post("/kdx_llm/profiles/delete")
    async def delete_model_profile(request):
        try:
            body = await request.json()
            key = (body.get("key") or "").strip()
            if not key:
                raise ValueError("key is required")
            if not sampling_store.delete(key):
                raise RuntimeError(f"Profile '{key}' not found.")
            return web.json_response({"status": "ok", "deleted": key})
        except Exception as exc:
            return web.json_response({"status": "error", "error": str(exc)}, status=400)

    @routes.post("/kdx_llm/unload")
    async def do_unload(request):
        try:
            body = await request.json()
            model = _body_value(body, "model", "").strip()
            if not model:
                raise ValueError("Model is empty")

            client = _client_from_body(body)
            result = await _run_blocking(client.unload_model, model)
            return web.json_response(result)
        except Exception as exc:
            return web.json_response({
                "status": "error",
                "error": str(exc),
            }, status=400)
