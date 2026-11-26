"""KDX LLM Client — provider/model capability inspection."""

import json


def _modalities(meta: dict, key: str) -> list[str]:
    architecture = meta.get("architecture")
    if isinstance(architecture, dict):
        values = architecture.get(key, [])
        if isinstance(values, list):
            return [str(v) for v in values]
    return []


def detect_capabilities(models_data: list[dict]) -> dict:
    """Convert /v1/models data into stable automation-friendly JSON."""
    if not isinstance(models_data, list):
        models_data = []

    models = []
    for raw in models_data:
        if not isinstance(raw, dict):
            continue

        input_mods = _modalities(raw, "input_modalities")
        output_mods = _modalities(raw, "output_modalities")
        status_obj = raw.get("status")
        status = status_obj.get("value", "unknown") if isinstance(status_obj, dict) else "unknown"

        models.append({
            "id": raw.get("id", ""),
            "object": raw.get("object", "model"),
            "created": raw.get("created"),
            "owned_by": raw.get("owned_by", ""),
            "status": status,
            "input_modalities": input_mods,
            "output_modalities": output_mods,
            "vision": "image" in input_mods or "video" in input_mods,
            "audio_input": "audio" in input_mods,
            "video_input": "video" in input_mods,
            "meta": raw.get("meta") if isinstance(raw.get("meta"), dict) else {},
        })

    return {
        "version": 1,
        "server": {
            "model_count": len(models),
            "has_status": any(m["status"] != "unknown" for m in models),
            "has_architecture": any(
                m["input_modalities"] or m["output_modalities"] for m in models
            ),
        },
        "models": models,
    }


def format_summary(capabilities: dict) -> str:
    lines = [
        f"Models: {capabilities.get('server', {}).get('model_count', 0)}"
    ]

    server = capabilities.get("server", {})
    if server.get("has_status"):
        lines.append("Status tracking: yes")
    if server.get("has_architecture"):
        lines.append("Modality info: yes")

    for model in capabilities.get("models", []):
        state = model.get("status", "unknown")
        icon = {
            "loaded": "🟢",
            "loading": "🟡",
            "sleeping": "💤",
            "downloading": "⬇️",
            "failed": "🔴",
            "unloaded": "⬜",
        }.get(state, "⬜")

        mods = []
        if model.get("vision"):
            mods.append("vision")
        if model.get("audio_input"):
            mods.append("audio")
        if model.get("video_input"):
            mods.append("video")

        suffix = f" [{', '.join(mods)}]" if mods else ""
        lines.append(f"{icon} {model.get('id', '')} ({state}){suffix}")

    return "\n".join(lines)


def capabilities_to_json(capabilities: dict) -> str:
    return json.dumps(capabilities, ensure_ascii=False, indent=2)
