"""KDX LLM Client — in-process conversation sessions.

The legacy session store is intentionally simple, but it now has a bounded LRU
and TTL so long-running ComfyUI instances do not accumulate unbounded history.
"""

import threading
import time
import uuid
from collections import OrderedDict

_MAX_SESSIONS = 128
_TTL_SECONDS = 24 * 60 * 60

_SESSIONS: "OrderedDict[str, list]" = OrderedDict()
_LOCK = threading.Lock()


def _now() -> float:
    return time.time()


def _purge_locked() -> None:
    cutoff = _now() - _TTL_SECONDS
    expired = [sid for sid, entry in _SESSIONS.items() if entry[0] < cutoff]
    for sid in expired:
        _SESSIONS.pop(sid, None)

    while len(_SESSIONS) > _MAX_SESSIONS:
        _SESSIONS.popitem(last=False)


def _touch_locked(session_id: str) -> list:
    entry = _SESSIONS.get(session_id)
    if entry is None:
        entry = [_now(), []]
    else:
        entry[0] = _now()
    _SESSIONS[session_id] = entry
    _SESSIONS.move_to_end(session_id)
    return entry[1]


def get_session(session_id: str) -> list:
    with _LOCK:
        _purge_locked()
        return _touch_locked(session_id)


def add_exchange(
    session_id: str,
    user_content,
    assistant_text: str,
    max_messages: int = 40,
) -> None:
    """Append a complete user/assistant pair and trim only whole pairs."""
    with _LOCK:
        _purge_locked()
        history = _touch_locked(session_id)
        history.append({"role": "user", "content": user_content})
        history.append({"role": "assistant", "content": assistant_text})

        limit = max(2, int(max_messages))
        if limit % 2:
            limit -= 1

        if len(history) > limit:
            del history[: len(history) - limit]


def reset_session(session_id: str) -> None:
    with _LOCK:
        _SESSIONS.pop(session_id, None)


def new_session_id() -> str:
    return uuid.uuid4().hex[:12]
