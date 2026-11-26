"""SSE (Server-Sent Events) parser for OpenAI-compatible streaming.

SSEAccumulator:
- feed_bytes(chunk: bytes) -> bool  (True on [DONE])
- build_response() -> dict          (OpenAI-compatible response)

Handles:
- UTF-8 incremental decoding (codepoints split across TCP chunks)
- data: / event: / comment lines
- tool_calls delta reconstruction (by index)
- reasoning_content delta accumulation
- usage / timings / model / finish_reason
- [DONE] sentinel
"""

import codecs
import json


class SSEAccumulator:
    """Accumulates SSE stream into an OpenAI-compatible response dict."""

    def __init__(self, check_interrupt=None):
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._line_buffer = ""
        self._check_interrupt = check_interrupt

        # Accumulated fields
        self._content = ""
        self._reasoning = ""
        self._model = ""
        self._finish_reason = None
        self._usage = {}
        self._timings = {}
        self._tool_calls = {}  # index -> {id, type, function: {name, arguments}}
        self._role = "assistant"

        # SSE framing state
        self._current_event = None
        self._data_lines = []
        self._done = False
        self._saw_data = False

    def feed_bytes(self, chunk: bytes) -> bool:
        """Feed raw bytes. Returns True if [DONE] was seen."""
        text = self._decoder.decode(chunk)
        self._line_buffer += text

        while "\n" in self._line_buffer:
            line, self._line_buffer = self._line_buffer.split("\n", 1)
            if self._check_interrupt:
                self._check_interrupt()
            self._process_line(line.rstrip("\r"))
            if self._done:
                return True

        return self._done

    def _process_line(self, line: str):
        """Process a single SSE line."""
        if not line:
            # Empty line = event boundary
            self._dispatch_event()
            return

        if line.startswith(":"):
            # Comment (e.g. ": OPENAI-BETAS=...") — ignore
            return

        if line.startswith("event:"):
            self._current_event = line[6:].strip()
            return

        if line.startswith("data:"):
            data = line[5:].strip()
            if data == "[DONE]":
                self._done = True
                return
            self._data_lines.append(data)
            self._saw_data = True
            return

        # Other SSE fields (id:, retry:) — ignore for our purposes

    def _dispatch_event(self):
        """Dispatch accumulated event data."""
        event = self._current_event
        data = "\n".join(self._data_lines)
        self._current_event = None
        self._data_lines = []

        if not data:
            return

        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            return

        if not isinstance(payload, dict):
            return

        # Top-level fields
        if "model" in payload:
            self._model = payload["model"]
        if "usage" in payload and isinstance(payload["usage"], dict):
            self._usage.update(payload["usage"])
        if "timings" in payload and isinstance(payload["timings"], dict):
            self._timings.update(payload["timings"])

        # Error event
        if event == "error" or "error" in payload:
            err = payload.get("error", {})
            raise RuntimeError(
                f"SSE error: {err.get('message', str(err)) if isinstance(err, dict) else err}"
            )

        # Choices
        choices = payload.get("choices")
        if not isinstance(choices, list):
            return

        for choice in choices:
            if not isinstance(choice, dict):
                continue

            if "finish_reason" in choice and choice["finish_reason"]:
                self._finish_reason = choice["finish_reason"]

            delta = choice.get("delta")
            if not isinstance(delta, dict):
                continue

            if delta.get("role"):
                self._role = delta["role"]

            if "content" in delta and delta["content"]:
                self._content += delta["content"]

            if "reasoning_content" in delta and delta["reasoning_content"]:
                self._reasoning += delta["reasoning_content"]

            # Tool calls delta
            tool_calls_delta = delta.get("tool_calls")
            if isinstance(tool_calls_delta, list):
                for tc in tool_calls_delta:
                    if not isinstance(tc, dict):
                        continue
                    idx = tc.get("index", 0)
                    if idx not in self._tool_calls:
                        self._tool_calls[idx] = {
                            "id": tc.get("id", ""),
                            "type": tc.get("type", "function"),
                            "function": {"name": "", "arguments": ""},
                        }
                    if tc.get("id"):
                        self._tool_calls[idx]["id"] = tc["id"]
                    if tc.get("type"):
                        self._tool_calls[idx]["type"] = tc["type"]
                    fn = tc.get("function")
                    if isinstance(fn, dict):
                        if fn.get("name"):
                            self._tool_calls[idx]["function"]["name"] = fn["name"]
                        if fn.get("arguments"):
                            self._tool_calls[idx]["function"]["arguments"] += fn["arguments"]

    @property
    def content(self) -> str:
        """Answer text received so far (for live previews)."""
        return self._content

    @property
    def reasoning(self) -> str:
        """Reasoning text received so far (for live previews)."""
        return self._reasoning

    def build_response(self) -> dict:
        """Flush decoder and build the final OpenAI-compatible response.

        MUST call decoder.decode(b"", final=True) to process any remaining
        bytes in the incremental decoder's internal buffer. Also handles
        a final line without trailing newline.
        """
        # Flush the incremental decoder
        remaining = self._decoder.decode(b"", final=True)

        # Combine remaining decoder output with any pending line buffer
        self._line_buffer += remaining

        # Process any complete lines
        while "\n" in self._line_buffer:
            line, self._line_buffer = self._line_buffer.split("\n", 1)
            self._process_line(line.rstrip("\r"))

        # Process any remaining partial line (no trailing newline)
        if self._line_buffer.strip():
            self._process_line(self._line_buffer)
            self._line_buffer = ""

        # Final event boundary (dispatches any pending data)
        self._dispatch_event()

        if not self._saw_data:
            raise RuntimeError("SSE stream: no data received")

        message = {"role": self._role, "content": self._content}
        if self._reasoning:
            message["reasoning_content"] = self._reasoning
        if self._tool_calls:
            message["tool_calls"] = [
                self._tool_calls[i] for i in sorted(self._tool_calls)
            ]

        response = {
            "id": "",
            "object": "chat.completion",
            "model": self._model or "",
            "choices": [{
                "index": 0,
                "message": message,
                "finish_reason": self._finish_reason or "stop",
            }],
        }
        if self._usage:
            response["usage"] = self._usage
        if self._timings:
            response["timings"] = self._timings
        return response
