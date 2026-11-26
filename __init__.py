"""KDX LLM Client — ComfyUI node registration."""

import os

_VERSION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")
try:
    with open(_VERSION_FILE, "r", encoding="utf-8") as _version_file:
        VERSION = _version_file.read().strip() or "0.10.5"
except OSError:
    VERSION = "0.10.5"
__version__ = VERSION

from .client import (
    NODE_CLASS_MAPPINGS as CLIENT_NODES,
    NODE_DISPLAY_NAME_MAPPINGS as CLIENT_NAMES,
)
from .options import (
    NODE_CLASS_MAPPINGS as OPTIONS_NODES,
    NODE_DISPLAY_NAME_MAPPINGS as OPTIONS_NAMES,
)
from .user_prompt_node import (
    NODE_CLASS_MAPPINGS as USER_PROMPT_NODES,
    NODE_DISPLAY_NAME_MAPPINGS as USER_PROMPT_NAMES,
)
from .quick_sampling_node import (
    NODE_CLASS_MAPPINGS as QUICK_PRESET_NODES,
    NODE_DISPLAY_NAME_MAPPINGS as QUICK_PRESET_NAMES,
)
from .response_formatter import (
    NODE_CLASS_MAPPINGS as FORMATTER_NODES,
    NODE_DISPLAY_NAME_MAPPINGS as FORMATTER_NAMES,
)
from .chat import (
    NODE_CLASS_MAPPINGS as CHAT_NODES,
    NODE_DISPLAY_NAME_MAPPINGS as CHAT_NAMES,
)
from .media_settings import (
    NODE_CLASS_MAPPINGS as MEDIA_NODES,
    NODE_DISPLAY_NAME_MAPPINGS as MEDIA_NAMES,
)
from .tools import (
    NODE_CLASS_MAPPINGS as TOOLS_NODES,
    NODE_DISPLAY_NAME_MAPPINGS as TOOLS_NAMES,
)
from .diagnostics import (
    NODE_CLASS_MAPPINGS as DIAG_NODES,
    NODE_DISPLAY_NAME_MAPPINGS as DIAG_NAMES,
)
from .stats import (
    NODE_CLASS_MAPPINGS as STATS_NODES,
    NODE_DISPLAY_NAME_MAPPINGS as STATS_NAMES,
)
from .system_prompt_node import (
    NODE_CLASS_MAPPINGS as PROMPT_NODES,
    NODE_DISPLAY_NAME_MAPPINGS as PROMPT_NAMES,
)
from .model_profile_node import (
    NODE_CLASS_MAPPINGS as PROFILE_NODES,
    NODE_DISPLAY_NAME_MAPPINGS as PROFILE_NAMES,
)
from .session_node import (
    NODE_CLASS_MAPPINGS as SESSION_NODES,
    NODE_DISPLAY_NAME_MAPPINGS as SESSION_NAMES,
)
from .json_extract_node import (
    NODE_CLASS_MAPPINGS as JSON_EXTRACT_NODES,
    NODE_DISPLAY_NAME_MAPPINGS as JSON_EXTRACT_NAMES,
)
from .json_fields_node import (
    NODE_CLASS_MAPPINGS as JSON_FIELDS_NODES,
    NODE_DISPLAY_NAME_MAPPINGS as JSON_FIELDS_NAMES,
)
from .prompt_template_node import (
    NODE_CLASS_MAPPINGS as TEMPLATE_NODES,
    NODE_DISPLAY_NAME_MAPPINGS as TEMPLATE_NAMES,
)
from .server_routes import setup_routes
from .v3_adapter import comfy_entrypoint


setup_routes()

# ---------------------------------------------------------------------------
# V1 / V3 registration gate (Option A, per Big LLM decision 2026-10-04)
#
# ComfyUI's loader (nodes.py) is either/or:
#   if NODE_CLASS_MAPPINGS:  register V1; return
#   elif comfy_entrypoint:   register V3
#
# Default: V1 (all nodes via NODE_CLASS_MAPPINGS) — production-safe.
# KDX_LLM_V3=1: suppress NODE_CLASS_MAPPINGS so ComfyUI falls through to
# comfy_entrypoint and registers the V3 Chat node. Intended for dev/test
# only, while comfy_api v0_0_2 is still unstable and the other 12 nodes
# have no V3 adapters yet.
# ---------------------------------------------------------------------------
_V3_ENABLED = os.environ.get("KDX_LLM_V3", "").strip().lower() in ("1", "true", "yes")

if _V3_ENABLED:
    # V3 mode: no V1 dict at module level -> loader uses comfy_entrypoint.
    WEB_DIRECTORY = "./web"
    __all__ = ["WEB_DIRECTORY", "comfy_entrypoint"]
else:
    NODE_CLASS_MAPPINGS = {
        **CLIENT_NODES,
        **OPTIONS_NODES,
        **CHAT_NODES,
        **MEDIA_NODES,
        **TOOLS_NODES,
        **DIAG_NODES,
        **STATS_NODES,
        **PROMPT_NODES,
        **USER_PROMPT_NODES,
        **QUICK_PRESET_NODES,
        **FORMATTER_NODES,
        **PROFILE_NODES,
        **SESSION_NODES,
        **JSON_EXTRACT_NODES,
        **JSON_FIELDS_NODES,
        **TEMPLATE_NODES,
    }

    NODE_DISPLAY_NAME_MAPPINGS = {
        **CLIENT_NAMES,
        **OPTIONS_NAMES,
        **CHAT_NAMES,
        **MEDIA_NAMES,
        **TOOLS_NAMES,
        **DIAG_NAMES,
        **STATS_NAMES,
        **PROMPT_NAMES,
        **USER_PROMPT_NAMES,
        **QUICK_PRESET_NAMES,
        **FORMATTER_NAMES,
        **PROFILE_NAMES,
        **SESSION_NAMES,
        **JSON_EXTRACT_NAMES,
        **JSON_FIELDS_NAMES,
        **TEMPLATE_NAMES,
    }

    WEB_DIRECTORY = "./web"
    __all__ = [
        "NODE_CLASS_MAPPINGS",
        "NODE_DISPLAY_NAME_MAPPINGS",
        "WEB_DIRECTORY",
        "comfy_entrypoint",
    ]
