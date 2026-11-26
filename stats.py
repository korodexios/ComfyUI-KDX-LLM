"""Statistics extractor for KDX LLM Chat raw output."""
import json

class KDX_LLM_Stats:
    DESCRIPTION = "Numbers about one answer: tokens used, speed (tokens/s), time and why it stopped. Connect Chat's raw output."

    CATEGORY = "KDX/LLM"
    RETURN_TYPES = ("INT", "INT", "INT", "STRING", "FLOAT", "FLOAT", "STRING")
    RETURN_NAMES = ("prompt_tokens", "completion_tokens", "total_tokens", "finish_reason", "tokens_per_second", "generation_time", "stats_json")
    FUNCTION = "run"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {"raw": ("STRING", {"default": "", "tooltip": "Connect KDX LLM Chat raw output."})},
            "optional": {"response_obj": ("ANY", {"tooltip": "Optional structured response object from Chat."})},
        }

    def run(self, raw="", response_obj=None):
        if not raw and isinstance(response_obj, dict):
            data = response_obj.get("raw") if isinstance(response_obj.get("raw"), dict) else dict(response_obj)
            if "usage" not in data:
                data["usage"] = {
                    "prompt_tokens": response_obj.get("prompt_tokens", 0),
                    "completion_tokens": response_obj.get("completion_tokens", 0),
                    "total_tokens": response_obj.get("total_tokens", 0),
                }
            if "choices" not in data:
                data["choices"] = [{"finish_reason": response_obj.get("finish_reason", "")}]
            if "_kdx_timing" not in data:
                data["_kdx_timing"] = {
                    "tokens_per_second": response_obj.get("tokens_per_second", 0.0),
                    "generation_time": response_obj.get("generation_time", 0.0),
                }
            raw = json.dumps(data)

        if not raw:
            return (0, 0, 0, "", 0.0, 0.0, "{}")
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return (0, 0, 0, "", 0.0, 0.0, "{}")
        usage = data.get("usage") or {}
        prompt = int(usage.get("prompt_tokens", 0) or 0)
        completion = int(usage.get("completion_tokens", 0) or 0)
        total = int(usage.get("total_tokens", prompt + completion) or (prompt + completion))
        choices = data.get("choices") or []
        finish = choices[0].get("finish_reason", "") if choices and isinstance(choices[0], dict) else ""
        timing = data.get("_kdx_timing") or {}
        tps = float(timing.get("tokens_per_second", 0.0) or 0.0)
        elapsed = float(timing.get("generation_time", 0.0) or 0.0)
        payload = {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": total, "finish_reason": finish, "tokens_per_second": tps, "generation_time": elapsed}
        return (prompt, completion, total, finish, tps, elapsed, json.dumps(payload, ensure_ascii=False))

NODE_CLASS_MAPPINGS = {"KDX_LLM_Stats": KDX_LLM_Stats}
NODE_DISPLAY_NAME_MAPPINGS = {"KDX_LLM_Stats": "📈 KDX • LLM Stats"}
