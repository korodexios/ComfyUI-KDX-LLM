"""Local HTTP integration tests for the KDX transport layer.

These tests start a tiny localhost OpenAI-compatible server and exercise
LLMClient.chat() for both non-streaming and streaming responses.
"""

import importlib.util
import json
import os
import sys
import threading
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import requests  # noqa: F401
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = "kdx_http_integration_test"


def _register_package():
    pkg = types.ModuleType(PKG)
    pkg.__path__ = [BASE]
    sys.modules[PKG] = pkg

    core = types.ModuleType(PKG + ".kdx_core")
    core.__path__ = [os.path.join(BASE, "kdx_core")]
    sys.modules[PKG + ".kdx_core"] = core


def _load(name, relpath):
    full = PKG + "." + name
    spec = importlib.util.spec_from_file_location(full, os.path.join(BASE, relpath))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full] = mod
    spec.loader.exec_module(mod)
    return mod


class MockLLMHandler(BaseHTTPRequestHandler):
    def log_message(self, *args, **kwargs):
        pass

    def _json(self, payload, status=200):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/v1/models":
            self._json({
                "data": [
                    {
                        "id": "test-model",
                        "owned_by": "llama.cpp",
                        "status": {"value": "loaded"},
                    }
                ]
            })
        else:
            self._json({"error": "not found"}, status=404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")

        if self.path != "/v1/chat/completions":
            self._json({"error": "not found"}, status=404)
            return

        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            chunks = [
                {"model": "test-model", "choices": [{"delta": {"content": "slovensk"}}]},
                {"model": "test-model", "choices": [{"delta": {"content": "á"}}]},
                {"model": "test-model", "choices": [{"delta": {}, "finish_reason": "stop"}], "usage": {"completion_tokens": 2}},
            ]
            for chunk in chunks:
                self.wfile.write(b"data: " + json.dumps(chunk).encode("utf-8") + b"\n\n")
            self.wfile.write(b"data: [DONE]\n\n")
        else:
            self._json({
                "model": "test-model",
                "choices": [{
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            })


@unittest.skipUnless(_HAS_REQUESTS, "requests is not installed")
class TestHttpIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _register_package()
        _load("kdx_core.sse_parser", os.path.join("kdx_core", "sse_parser.py"))
        cls.http_mod = _load("_http", "_http.py")
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), MockLLMHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_non_stream_chat(self):
        client = self.http_mod.LLMClient(self.base_url, provider="generic")
        resp = client.chat({"model": "test-model", "messages": [{"role": "user", "content": "hi"}], "stream": False})
        self.assertEqual(resp["choices"][0]["message"]["content"], "ok")
        self.assertEqual(resp["usage"]["total_tokens"], 2)

    def test_stream_chat_utf8(self):
        client = self.http_mod.LLMClient(self.base_url, provider="generic")
        resp = client.chat({"model": "test-model", "messages": [{"role": "user", "content": "hi"}], "stream": True})
        self.assertEqual(resp["choices"][0]["message"]["content"], "slovenská")
        self.assertEqual(resp["usage"]["completion_tokens"], 2)

    def test_get_models(self):
        client = self.http_mod.LLMClient(self.base_url, provider="generic")
        models = client.get_models()
        self.assertEqual(models, ["test-model"])

    def test_provider_override_bypasses_discovery(self):
        client = self.http_mod.LLMClient("http://127.0.0.1:1", provider="llama_cpp_router")
        info = client.detect_server_type()
        self.assertEqual(info["type"], "llama_cpp_router")
        self.assertTrue(info["supports_load"])


if __name__ == "__main__":
    unittest.main()
