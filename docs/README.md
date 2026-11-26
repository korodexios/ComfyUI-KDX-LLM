# KDX LLM — Documentation

Reference documentation for the KDX LLM node pack. Start with the [main README](../README.md) for
installation, the node list and how the pack works with KDX Wildcard Studio and KDX Resolution.

| File | Contents |
|------|----------|
| [`01-quick-start.md`](01-quick-start.md) | Install, first workflow, minimal setup |
| [`02-architecture.md`](02-architecture.md) | `kdx_core` layer, node topology, data flow |
| [`03-nodes.md`](03-nodes.md) | Every node: inputs, outputs, types, examples |
| [`04-sessions.md`](04-sessions.md) | Session objects, the older `session_id` field, chaining patterns |
| [`05-response.md`](05-response.md) | `KDXLLMResponse`, the 11 Chat outputs, JSON access |
| [`06-sampling.md`](06-sampling.md) | Merge priority, profiles, presets, reasoning mode |
| [`07-provider.md`](07-provider.md) | Provider override, known providers, model load/unload |
| [`08-v3.md`](08-v3.md) | ComfyUI V3 adapter behind the `KDX_LLM_V3` switch |

All source paths are relative to the pack root (the directory containing `__init__.py`).

Repository: https://github.com/korodexios/ComfyUI-KDX-LLM
