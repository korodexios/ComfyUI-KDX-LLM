# KDX LLM — Sessions

## Two Session Mechanisms

| Mechanism | Type | DAG-safe? | Use when |
|-----------|------|-----------|----------|
| **Session object** | `KDX_LLM_SESSION` socket | ✅ Immutable | New workflows, branchable graphs |
| **Legacy session_id** | STRING field + in-memory store | ❌ Mutable global | Existing workflows (backward compat) |

When a `KDX_LLM_SESSION` socket is connected to the Chat node, it **overrides**
the `session_id` text field. The object path is the source of truth.

---

## `KDXLLMSession` (Object Path)

**File:** `kdx_core/session.py`

```python
@dataclass
class KDXLLMSession:
    session_id: str
    messages: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### Immutability Rules

- `add_exchange()` returns a **NEW** `KDXLLMSession`. Never mutates `self`.
- `messages` is a plain list but callers must treat it as read-only.
  Every operation copies the list (copy-on-write).
- Trimming keeps whole user/assistant **pairs** (never drops a lone message).
  `max_messages` is coerced to an even number ≥ 2.

### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `add_exchange(user, assistant, max_messages=40)` | new `KDXLLMSession` | Append one user/assistant pair, trim to limit |
| `reset(session_id=None)` | new `KDXLLMSession` | Empty session (same ID by default, or new) |
| `with_metadata(**kwargs)` | new `KDXLLMSession` | Merge metadata |
| `turn_count` (property) | `int` | Number of complete exchanges |
| `is_empty()` | `bool` | True if no messages |
| `messages_for_api()` | `List[dict]` | Defensive copy for API request |
| `to_dict()` | `dict` | `{"session_id", "messages", "metadata"}` |
| `from_dict(data)` (classmethod) | `KDXLLMSession` | Deserialize |
| `__eq__` | `bool` | Value equality |

### Message Format

```python
[
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi! How can I help?"},
    {"role": "user", "content": "What's 2+2?"},
    {"role": "assistant", "content": "4"},
]
```

`content` may be a `str` or a list of content parts (multi-modal:
`[{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {...}}]`).

---

## Chaining Patterns

### Linear chain (2 turns)

```
Chat 1 (prompt="Hello")
  └─ session output ──→ Chat 2 (prompt="How are you?")
                           └─ session output ──→ Chat 3 (prompt="Tell me a joke")
```

Each Chat node appends its exchange to the session. The 10th output is the
updated session.

### Branching (DAG-safe)

```
Chat 1 (prompt="Hello")
  ├─ session output ──→ Chat 2 (prompt="Branch A")
  └─ session output ──→ Chat 3 (prompt="Branch B")
```

Both Chat 2 and Chat 3 receive the **same immutable** session from Chat 1.
Each produces its own updated session. They never share or mutate state.

### Reset mid-graph

```
Chat 1 → session → Session(action="reset") → session → Chat 2
```

The Session node clears the history but preserves the session ID. Chat 2
starts a fresh conversation.

### Import from JSON

```
Session(action="import_json", import_json='[{"role":"user","content":"Hi"},{"role":"assistant","content":"Hello!"}]')
  → session → Chat 1 (prompt="Continue")
```

### Legacy → Object bridge

If Chat 1 uses the legacy `session_id` field (no socket), its 10th output is
still a `KDXLLMSession` (bridged from the in-memory store). You can connect
it to Chat 2's `session` input to transition to the object path:

```
Chat 1 (session_id="abc", no socket)
  └─ session output (bridged KDXLLMSession) ──→ Chat 2 (session input)
```

---

## Legacy Session Store (Backward Compat)

**File:** `session.py` (pack root)

In-memory LRU/TTL store keyed by `session_id` string. It is bounded to 128 sessions and expires entries after 24 hours. Functions:

| Function | Description |
|----------|-------------|
| `new_session_id()` | Generate a UUID string |
| `get_session(sid)` | Get message list for `sid` |
| `add_exchange(sid, user, assistant, max_messages=40)` | Append pair, trim |
| `reset_session(sid)` | Clear messages for `sid` |

**Limitations:**
- Mutable global state (not DAG-safe)
- Lost on ComfyUI restart (in-memory only)
- Bounded by LRU/TTL: old or excess sessions are dropped
- Two branches with the same `session_id` share state

Use the object path for new workflows.

---

## `max_history` Behavior

The `max_history` input on the Chat node (default 40, range 2–200) controls
how many messages are kept in the session. It is coerced to an even number.
When the session exceeds the limit, the **oldest pairs** are dropped.

```
max_history=40 → keep last 20 user/assistant pairs
max_history=10 → keep last 5 pairs
```

---

## Session Node (`KDX_LLM_Session`)

See [`03-nodes.md`](03-nodes.md#-kdx--llm-session) for the full node reference.

| Action | Use case |
|--------|----------|
| `new` | Start a fresh conversation at the top of a workflow |
| `passthrough` | Inspect/forward a session (debugging) |
| `reset` | Clear history mid-graph |
| `import_json` | Seed a conversation from saved JSON |
| `save` | Persist a connected session under `session_name` |
| `load` | Restore a persisted session by `session_name` |
