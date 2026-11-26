# KDX LLM — Quick Start

## Requirements

- ComfyUI (any recent version)
- Python 3.10+
- An OpenAI-compatible LLM server (llama.cpp, Ollama, vLLM, LM Studio, etc.)

## Installation

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/korodexios/ComfyUI-KDX-LLM.git
```

Or install **KDX LLM** from ComfyUI-Manager. Restart ComfyUI. The nodes appear under the **KDX → LLM** category.

No extra pip installs needed — `requests`, `numpy`, and `Pillow` are already
in every ComfyUI venv.

## First Workflow (2 nodes)

1. **Add a 🔌 LLM Client node**
   - `url` → your server address (e.g. `http://localhost:8080`)
   - `model` → model name as shown by the server
   - `context_length` → e.g. `8192`

2. **Add a 💬 LLM Chat node**
   - Connect the Client's `client` output to Chat's `client` input
   - Type a prompt
   - Queue and run

You get 11 outputs: `response`, `thinking`, `json`, `raw`, `model_used`,
`profile_key`, `profile_json`, `request_info`, `response_obj`, `session`, `tool_calls`.

## Adding Sampling Control (3 nodes)

1. Add a 🎛️ **Simple Sampling** node
2. Enable the parameters you want (each has its own ON/OFF switch)
3. Connect its `options` output to Chat's `thinking_sampling` (or `non_thinking_sampling`)

## Multi-Turn Conversation

**Option A — legacy (session_id string):**
Set the same `session_id` on multiple Chat nodes. `reset_session=True` on the
first node, `reset_session=False` on the rest.

**Option B — session object (DAG-safe, recommended for new workflows):**
Connect Chat 1's `session` output (10th slot) to Chat 2's `session` input.
No text fields needed. The session object flows through the graph.

See [`04-sessions.md`](04-sessions.md) for full details.

## JSON Mode

1. Set `json_mode` to `on` on the Chat node (or use `auto` with a `qwen_json` preset)
2. The LLM must output a valid JSON object
3. The parsed JSON appears on the `json` output (3rd slot)

## Provider Override

If you know your server type, set the `provider` input on the Client node
(e.g. `llama_cpp_router`). This skips the discovery probes and uses the
predefined lifecycle endpoints directly. See [`07-provider.md`](07-provider.md).
