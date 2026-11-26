"""KDX Core — Immutable conversation session.

P2: session as a first-class ComfyUI data-flow citizen (KDX_LLM_SESSION).

This dataclass is the *immutable-friendly* session carried across the graph.
It replaces the hidden in-memory store (``session.py`` at pack root) as the
DAG-safe representation: each ``add_exchange`` returns a NEW instance, so two
branches forking from the same upstream session never share or mutate state.

The legacy in-memory store stays for backward compat (existing graphs that use
the ``session_id`` string + ``reset_session`` widget). When a ``KDX_LLM_SESSION``
socket is connected to the Chat node, this object is the source of truth and
the store is bypassed.

Immutability rules (important for DAG correctness):
- ``add_exchange`` never mutates ``self``; it returns a new ``KDXLLMSession``.
- ``messages`` is a plain list of dicts but callers must treat it as read-only
  (we copy it on every operation). ``frozenset`` of tuples is an option but the
  dict contents (user content can be a list for multi-modal) make that awkward;
  copy-on-write is the pragmatic choice.
- Trimming keeps whole user/assistant PAIRS (never drops a lone message), and
  ``max_messages`` is coerced to an even number >= 2.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _even_limit(max_messages: "int | float | str") -> int:
    """Coerce to an even integer >= 2 (trim keeps whole pairs).

    Accepts int/float/str defensively — widget values arrive as whatever the
    user typed; ``int()`` handles all three (and raises on garbage, which the
    node layer catches before calling this).
    """
    limit = max(2, int(max_messages))
    if limit % 2:
        limit -= 1
    return limit


@dataclass
class KDXLLMSession:
    """Immutable conversation session.

    ``messages`` is a list of ``{"role": ..., "content": ...}`` dicts in
    chronological order. ``content`` may be a ``str`` or a list of content
    parts (multi-modal: text + image_url). ``metadata`` carries arbitrary
    per-session state (system rules, source, created_at, ...).
    """

    session_id: str
    messages: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ── Immutability-friendly operations ──────────────────────────────

    def add_exchange(
        self,
        user_content: Any,
        assistant_content: Any,
        max_messages: int = 40,
    ) -> "KDXLLMSession":
        """Return a NEW session with one user/assistant pair appended.

        Trims to ``max_messages`` whole pairs (oldest dropped first). Never
        mutates ``self``.
        """
        new_messages = list(self.messages)
        new_messages.append({"role": "user", "content": user_content})
        new_messages.append({"role": "assistant", "content": assistant_content})

        limit = _even_limit(max_messages)
        if len(new_messages) > limit:
            new_messages = new_messages[-limit:]

        return KDXLLMSession(
            session_id=self.session_id,
            messages=new_messages,
            metadata=dict(self.metadata),
        )

    def reset(self, session_id: Optional[str] = None) -> "KDXLLMSession":
        """Return a NEW empty session (same id by default, or a fresh one).

        Keeps ``metadata`` unless a new id is supplied (a fresh start usually
        wants a clean slate, but callers may want to preserve rules).
        """
        new_id = session_id if session_id is not None else self.session_id
        return KDXLLMSession(
            session_id=new_id,
            messages=[],
            metadata=dict(self.metadata),
        )

    def with_metadata(self, **kwargs: Any) -> "KDXLLMSession":
        """Return a NEW session with merged metadata (kwargs override)."""
        merged = dict(self.metadata)
        merged.update(kwargs)
        return KDXLLMSession(
            session_id=self.session_id,
            messages=list(self.messages),
            metadata=merged,
        )

    # ── Introspection ─────────────────────────────────────────────────

    @property
    def turn_count(self) -> int:
        """Number of complete user/assistant exchanges."""
        return len(self.messages) // 2

    def is_empty(self) -> bool:
        return len(self.messages) == 0

    def messages_for_api(self) -> List[Dict[str, Any]]:
        """A defensive copy of the message list, ready to send to the API.

        Returns a fresh list so downstream mutation cannot leak into the
        session object held by an upstream node.
        """
        return [dict(m) for m in self.messages]

    # ── Serialization (for P2.3 export / persistence) ─────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "messages": [dict(m) for m in self.messages],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KDXLLMSession":
        return cls(
            session_id=str(data.get("session_id", "")),
            messages=[dict(m) for m in (data.get("messages") or [])],
            metadata=dict(data.get("metadata") or {}),
        )

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, KDXLLMSession):
            return NotImplemented
        return (
            self.session_id == other.session_id
            and self.messages == other.messages
            and self.metadata == other.metadata
        )


__all__ = ["KDXLLMSession"]
