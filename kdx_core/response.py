"""KDX Core — Unified response model.

KDXLLMResponse is the structured output carried on the Chat node's 9th
output slot (returned type "ANY" in V1, a real custom type in V3).

The V1 STRING slots (0-7) are untouched: slot 3 ("raw") remains a JSON
string dump. This object is additive.
"""

from dataclasses import asdict, dataclass, field
import json
from typing import Any, Dict, List, Optional


@dataclass
class KDXLLMResponse:
    content: str = ""
    reasoning: str = ""
    json_data: Optional[Any] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    model: str = ""
    finish_reason: str = "stop"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    tokens_per_second: float = 0.0
    generation_time: float = 0.0
    raw: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_parsed(cls, result: Dict[str, Any], raw_response: Optional[Dict[str, Any]] = None,
                    metadata: Optional[Dict[str, Any]] = None) -> "KDXLLMResponse":
        """Build a KDXLLMResponse from postprocess.parse_response() output.

        `result` is the dict returned by parse_response (keys: response, thinking,
        json, tool_calls, raw, model_used, prompt_tokens, completion_tokens,
        total_tokens, finish_reason, tokens_per_second, generation_time).
        `raw_response` is the original API response dict (before json.dumps).
        """
        return cls(
            content=result.get("response", ""),
            reasoning=result.get("thinking", ""),
            json_data=result.get("json"),
            tool_calls=result.get("tool_calls") or [],
            model=result.get("model_used", ""),
            finish_reason=result.get("finish_reason") or "stop",
            prompt_tokens=int(result.get("prompt_tokens", 0) or 0),
            completion_tokens=int(result.get("completion_tokens", 0) or 0),
            total_tokens=int(result.get("total_tokens", 0) or 0),
            tokens_per_second=float(result.get("tokens_per_second", 0.0) or 0.0),
            generation_time=float(result.get("generation_time", 0.0) or 0.0),
            raw=raw_response if isinstance(raw_response, dict) else {},
            metadata=metadata if isinstance(metadata, dict) else {},
        )
