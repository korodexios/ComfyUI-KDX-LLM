"""KDX LLM Session — standalone session management, inspection and initialization.

P2.3: a first-class node for creating, inspecting, resetting and importing
conversation sessions (KDXLLMSession objects).

Actions:
- "new"          — create a fresh session (auto or custom ID)
- "passthrough"  — forward a connected session (optionally rename)
- "reset"        — clear messages of a connected session
- "import_json"  — load messages from a JSON string (list or {"messages": [...]})
- "save"         — save a connected session under session_name
- "load"         — load a saved session from session_name

Outputs:
- session       (KDX_LLM_SESSION)
- messages_json (STRING) — full history as JSON for inspection/debugging
- turn_count    (INT)    — number of completed user/assistant turns
"""

import json
from .kdx_core.session import KDXLLMSession
from .session import new_session_id
from . import session_store


class KDX_LLM_Session:
    DESCRIPTION = "Manages a conversation history. new = start fresh, save / load = store or restore a conversation by name, import_json = load messages, reset = clear. Connect 'session' to Chat's session input."

    CATEGORY = "KDX/LLM"
    RETURN_TYPES = ("KDX_LLM_SESSION", "STRING", "INT")
    RETURN_NAMES = ("session", "messages_json", "turn_count")
    OUTPUT_TOOLTIPS = (
        "Active conversation session object (KDX_LLM_SESSION).",
        "Full conversation history as a JSON string for inspection or downstream processing.",
        "Number of completed user/assistant turns.",
    )
    FUNCTION = "execute"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "action": (
                    ["new", "passthrough", "reset", "import_json", "save", "load"],
                    {
                        "default": "new",
                        "tooltip": "new = create fresh session; passthrough = inspect/forward connected session; reset = clear messages; import_json = load custom JSON; save = persist connected session; load = load persisted session.",
                    },
                ),
            },
            "optional": {
                "session": (
                    "KDX_LLM_SESSION",
                    {"tooltip": "Optional upstream session object to inspect, reset or forward."},
                ),
                "custom_id": (
                    "STRING",
                    {
                        "default": "",
                        "tooltip": "Optional custom session ID. If empty, a unique ID is auto-generated.",
                    },
                ),
                "import_json": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "tooltip": "JSON array of messages [{'role': 'user'|'assistant', 'content': '...'}] used when action = import_json.",
                    },
                ),
                "session_name": (
                    "STRING",
                    {
                        "default": "",
                        "tooltip": "Named session key used by action = save or action = load.",
                    },
                ),
            },
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        # Save/load mutate hidden on-disk session state; keep this node live.
        return float("nan")

    def execute(
        self,
        action="new",
        session=None,
        custom_id="",
        import_json="",
        session_name="",
    ):
        sid = custom_id.strip() if custom_id else ""
        name = session_name.strip() if session_name else ""

        if action == "new":
            sess = KDXLLMSession(session_id=sid or new_session_id())

        elif action == "reset":
            if isinstance(session, KDXLLMSession):
                sess = session.reset(session_id=sid or None)
            else:
                sess = KDXLLMSession(session_id=sid or new_session_id())

        elif action == "import_json":
            messages = []
            if import_json and import_json.strip():
                try:
                    parsed = json.loads(import_json.strip())
                    if isinstance(parsed, list):
                        messages = [
                            m for m in parsed
                            if isinstance(m, dict) and "role" in m and "content" in m
                        ]
                    elif isinstance(parsed, dict) and "messages" in parsed and isinstance(parsed["messages"], list):
                        messages = [
                            m for m in parsed["messages"]
                            if isinstance(m, dict) and "role" in m and "content" in m
                        ]
                    else:
                        raise ValueError(
                            "JSON must be a list of message dicts or an object with a 'messages' list"
                        )
                except json.JSONDecodeError as exc:
                    raise ValueError(f"KDX LLM: Invalid JSON in 'import_json': {exc}") from exc

            sess = KDXLLMSession(
                session_id=sid or (session.session_id if isinstance(session, KDXLLMSession) else new_session_id()),
                messages=messages,
            )

        elif action == "save":
            if not name:
                raise ValueError("KDX LLM: 'session_name' is required when action = save.")
            if isinstance(session, KDXLLMSession):
                sess = session
            elif isinstance(session, dict):
                sess = KDXLLMSession.from_dict(session)
            else:
                raise ValueError("KDX LLM: connect a session object to save it.")
            if not session_store.save(name, sess.to_dict()):
                raise RuntimeError(f"KDX LLM: could not save session '{name}'.")

        elif action == "load":
            if not name:
                raise ValueError("KDX LLM: 'session_name' is required when action = load.")
            data = session_store.get(name)
            if not data:
                raise ValueError(f"KDX LLM: saved session '{name}' not found.")
            sess = KDXLLMSession.from_dict(data)
            if sid:
                sess = KDXLLMSession(session_id=sid, messages=sess.messages, metadata=sess.metadata)

        else:  # "passthrough"
            if isinstance(session, KDXLLMSession):
                sess = session
                if sid and sid != sess.session_id:
                    sess = KDXLLMSession(session_id=sid, messages=sess.messages, metadata=sess.metadata)
            else:
                sess = KDXLLMSession(session_id=sid or new_session_id())

        messages_json = json.dumps(sess.messages_for_api(), ensure_ascii=False, indent=2)
        return (sess, messages_json, sess.turn_count)


NODE_CLASS_MAPPINGS = {"KDX_LLM_Session": KDX_LLM_Session}
NODE_DISPLAY_NAME_MAPPINGS = {"KDX_LLM_Session": "🔄 KDX • LLM Session"}
