"""Tests for KDX LLM Client v4 — postprocess, options, chat, media, tools, session, capabilities, stats, formatter, media_settings, sampling_store."""

import hashlib
import json
import os
import sys
import types
import unittest
import importlib.util

DEV_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V4_DIR = DEV_DIR

# ── Package stub for relative imports ────────────────────────────────
pkg = types.ModuleType("kdx_v4")
pkg.__path__ = [V4_DIR]
sys.modules["kdx_v4"] = pkg

# Stub media module (numpy may not be available)
media_stub = types.ModuleType("kdx_v4.media")
media_stub.build_user_content = lambda **kw: kw.get("prompt", "")
sys.modules["kdx_v4.media"] = media_stub

# ── kdx_core stubs (P1.x / P2.x) ────────────────────────────────────
# chat.py does `from .kdx_core.xxx import ...` which resolves to
# `kdx_v4.kdx_core.xxx`. We pre-register in-memory stubs so the real
# kdx_core modules don't get loaded (they'd pull in real dependencies).
class _RespStub:
    def __init__(self, content="", thinking="", json_obj=None, raw="", model_used="", usage=None):
        self.content = content; self.thinking = thinking; self.json = json_obj
        self.raw = raw; self.model_used = model_used; self.usage = usage or {}
        self.tool_calls = []; self.timings = {}
    def to_dict(self):
        return {"content": self.content, "thinking": self.thinking, "json": self.json,
                "raw": self.raw, "model_used": self.model_used, "usage": self.usage}
    @classmethod
    def from_parsed(cls, result, raw_response="", metadata=None):
        return cls(content=result.get("response", ""), thinking=result.get("thinking", ""),
                   json_obj=result.get("json"), raw=raw_response, model_used=result.get("model_used", ""),
                   usage=result.get("usage") or {})

def _build_chat_payload(model, messages, **kw):
    """Mimic kdx_core.request_builder.build_chat_payload priority chain."""
    thinking_on = kw.get("thinking_on", False)
    mode = "thinking" if thinking_on else "non_thinking"
    profile = kw.get("profile") or {}
    prof = profile.get(mode, {}) if isinstance(profile, dict) else {}
    profile_sampling = prof.get("sampling", {}) if isinstance(prof.get("sampling"), dict) else {}
    # 1. Base sampling from profile
    req = dict(profile_sampling)
    # 2. Node-based sampling override
    if kw.get("sampling_override"):
        req.update(kw["sampling_override"])
    # 3. JSON sampling string override
    if kw.get("sampling_json_override"):
        req.update(kw["sampling_json_override"])
    # Build payload
    payload = {"model": model, "messages": messages, "stream": kw.get("stream", True)}
    if isinstance(prof.get("request"), dict):
        payload.update(prof["request"])
    payload.update(req)
    if kw.get("extra_request_json"):
        payload.update(kw["extra_request_json"])
    return payload, req

def _build_fingerprint_key(key_dict=None, **kw):
    """Mimic kdx_core.fingerprint.build_fingerprint_key — canonical dict key."""
    d = dict(key_dict or {})
    d.update(kw)
    return json.dumps(d, sort_keys=True, default=str)
def _canonical_hash(x): return hashlib.sha256(str(x).encode()).hexdigest()

class _SessionStub:
    def __init__(self, session_id="", messages=None):
        self.session_id = session_id
        self.messages = [dict(m) for m in (messages or [])]
    def add_exchange(self, user, assistant, max_messages=40):
        msgs = list(self.messages) + [{"role": "user", "content": user}, {"role": "assistant", "content": assistant}]
        while len(msgs) > max_messages: msgs = msgs[1:]
        return _SessionStub(self.session_id, msgs)
    def reset(self): return _SessionStub(self.session_id, [])
    def messages_for_api(self): return list(self.messages)
    def to_dict(self): return {"session_id": self.session_id, "messages": list(self.messages)}
    @classmethod
    def from_dict(cls, d):
        return cls(d.get("session_id", ""), [dict(m) for m in (d.get("messages") or [])])

_kc_pkg = types.ModuleType("kdx_v4.kdx_core")
_kc_pkg.__path__ = [os.path.join(V4_DIR, "kdx_core")]
_kc_resp = types.ModuleType("kdx_v4.kdx_core.response"); _kc_resp.KDXLLMResponse = _RespStub
_kc_rb = types.ModuleType("kdx_v4.kdx_core.request_builder"); _kc_rb.build_chat_payload = _build_chat_payload
_kc_fp = types.ModuleType("kdx_v4.kdx_core.fingerprint")
_kc_fp.build_fingerprint_key = _build_fingerprint_key; _kc_fp.canonical_hash = _canonical_hash
_kc_sess = types.ModuleType("kdx_v4.kdx_core.session"); _kc_sess.KDXLLMSession = _SessionStub
_kc_pkg.response = _kc_resp; _kc_pkg.request_builder = _kc_rb
_kc_pkg.fingerprint = _kc_fp; _kc_pkg.session = _kc_sess
sys.modules["kdx_v4.kdx_core"] = _kc_pkg
sys.modules["kdx_v4.kdx_core.response"] = _kc_resp
sys.modules["kdx_v4.kdx_core.request_builder"] = _kc_rb
sys.modules["kdx_v4.kdx_core.fingerprint"] = _kc_fp
sys.modules["kdx_v4.kdx_core.session"] = _kc_sess


def _load(name, filename):
    path = os.path.join(V4_DIR, filename)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Load pure modules first
postprocess = _load("kdx_v4.postprocess", "postprocess.py")
sampling_store = _load("kdx_v4.sampling_store", "sampling_store.py")
session = _load("kdx_v4.session", "session.py")
tools = _load("kdx_v4.tools", "tools.py")
capabilities = _load("kdx_v4.capabilities", "capabilities.py")
stats = _load("kdx_v4.stats", "stats.py")
formatter = _load("kdx_v4.response_formatter", "response_formatter.py")
media_settings = _load("kdx_v4.media_settings", "media_settings.py")
options = _load("kdx_v4.options", "options.py")
client = _load("kdx_v4.client", "client.py")
chat = _load("kdx_v4.chat", "chat.py")
mpn = _load("kdx_v4.model_profile_node", "model_profile_node.py")

# ── postprocess ──────────────────────────────────────────────────────

class TestThinkingExtraction(unittest.TestCase):
    def test_no_tags(self):
        clean, thinking = postprocess.extract_thinking("Just text.")
        self.assertEqual(clean, "Just text.")
        self.assertEqual(thinking, "")

    def test_think_tags(self):
        t_open = chr(60) + "think" + chr(62)
        t_close = chr(60) + "/think" + chr(62)
        text = t_open + "reasoning" + t_close + "\nAnswer: 42"
        clean, thinking = postprocess.extract_thinking(text)
        self.assertEqual(clean, "Answer: 42")
        self.assertEqual(thinking, "reasoning")

    def test_thinking_tags(self):
        text = "<thinking>Reasoning here.</thinking>\nFinal answer."
        clean, thinking = postprocess.extract_thinking(text)
        self.assertEqual(clean, "Final answer.")
        self.assertEqual(thinking, "Reasoning here.")

    def test_multiple_blocks(self):
        t_open = chr(60) + "think" + chr(62)
        t_close = chr(60) + "/think" + chr(62)
        text = t_open + "A." + t_close + "\nMid.\n" + t_open + "B." + t_close + "\nEnd."
        clean, thinking = postprocess.extract_thinking(text)
        self.assertIn("Mid.", clean)
        self.assertIn("End.", clean)
        self.assertNotIn("A.", clean)
        self.assertNotIn("B.", clean)

    def test_empty(self):
        clean, thinking = postprocess.extract_thinking("")
        self.assertEqual(clean, "")
        self.assertEqual(thinking, "")


class TestJSONExtraction(unittest.TestCase):
    def test_pure_json(self):
        data = {"wh_ratio": "9:16"}
        self.assertEqual(postprocess.extract_json(json.dumps(data)), data)

    def test_json_with_prose(self):
        text = 'Result: {"wh_ratio": "16:9"} done.'
        self.assertEqual(postprocess.extract_json(text), {"wh_ratio": "16:9"})

    def test_fenced_json(self):
        text = '```json\n{"model": "SDXL"}\n```'
        self.assertEqual(postprocess.extract_json(text), {"model": "SDXL"})

    def test_no_json(self):
        self.assertIsNone(postprocess.extract_json("no json here"))

    def test_empty(self):
        self.assertIsNone(postprocess.extract_json(""))


class TestParseResponse(unittest.TestCase):
    def test_basic(self):
        resp = {"model": "m", "choices": [{"message": {"role": "assistant", "content": "Hi!"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
        r = postprocess.parse_response(resp)
        self.assertEqual(r["response"], "Hi!")
        self.assertEqual(r["model_used"], "m")
        self.assertEqual(r["prompt_tokens"], 10)
        self.assertEqual(r["completion_tokens"], 5)
        self.assertEqual(r["total_tokens"], 15)

    def test_reasoning_content(self):
        resp = {"model": "m", "choices": [{"message": {"role": "assistant", "content": "42", "reasoning_content": "thinking..."}}]}
        r = postprocess.parse_response(resp)
        self.assertEqual(r["response"], "42")
        self.assertEqual(r["thinking"], "thinking...")

    def test_thinking_tags_in_content(self):
        resp = {"model": "m", "choices": [{"message": {
            "role": "assistant", "content": "<thinking>reason</thinking>\nFinal: 42"}}]}
        r = postprocess.parse_response(resp)
        self.assertEqual(r["response"], "Final: 42")
        self.assertEqual(r["thinking"], "reason")

    def test_json_mode(self):
        resp = {"model": "m", "choices": [{"message": {
            "role": "assistant", "content": '{"wh_ratio": "9:16"}'}}]}
        r = postprocess.parse_response(resp, json_mode=True)
        self.assertEqual(r["json"], {"wh_ratio": "9:16"})

    def test_empty_choices(self):
        r = postprocess.parse_response({"model": "x", "choices": []})
        self.assertEqual(r["response"], "")
        self.assertEqual(r["prompt_tokens"], 0)

    def test_tokens_per_second(self):
        resp = {"model": "t", "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 100}}
        r = postprocess.parse_response(resp, elapsed_time=2.0)
        self.assertEqual(r["tokens_per_second"], 50.0)
        self.assertEqual(r["generation_time"], 2.0)


# ── options (Simple + Advanced Sampling) ─────────────────────────────

class TestSimpleSampling(unittest.TestCase):
    def _make(self):
        return options.KDX_LLM_Simple_Sampling()

    def test_all_disabled_returns_empty(self):
        node = self._make()
        kwargs = {f"{n}_enabled": False for n, *_ in options._SIMPLE_PARAMS}
        kwargs["stop_enabled"] = False
        result = node.execute(base_options=None, **kwargs)
        self.assertEqual(result[0]["options"], {})

    def test_enable_temperature(self):
        node = self._make()
        kwargs = {f"{n}_enabled": False for n, *_ in options._SIMPLE_PARAMS}
        kwargs["temperature_enabled"] = True
        kwargs["temperature"] = 0.5
        kwargs["stop_enabled"] = False
        result = node.execute(base_options=None, **kwargs)
        self.assertEqual(result[0]["options"]["temperature"], 0.5)
        self.assertNotIn("top_p", result[0]["options"])

    def test_stop_sequences(self):
        node = self._make()
        kwargs = {f"{n}_enabled": False for n, *_ in options._SIMPLE_PARAMS}
        kwargs["stop_enabled"] = True
        kwargs["stop"] = "STOP1\nSTOP2\n\n"
        result = node.execute(base_options=None, **kwargs)
        self.assertEqual(result[0]["options"]["stop"], ["STOP1", "STOP2"])

    def test_chaining_preserves_upstream(self):
        node = self._make()
        kwargs1 = {f"{n}_enabled": False for n, *_ in options._SIMPLE_PARAMS}
        kwargs1["temperature_enabled"] = True
        kwargs1["temperature"] = 0.5
        kwargs1["stop_enabled"] = False
        r1 = node.execute(base_options=None, **kwargs1)

        kwargs2 = {f"{n}_enabled": False for n, *_ in options._SIMPLE_PARAMS}
        kwargs2["top_p_enabled"] = True
        kwargs2["top_p"] = 0.8
        kwargs2["stop_enabled"] = False
        r2 = node.execute(base_options=r1[0], **kwargs2)
        self.assertEqual(r2[0]["options"]["temperature"], 0.5)
        self.assertEqual(r2[0]["options"]["top_p"], 0.8)


class TestAdvancedSampling(unittest.TestCase):
    def _make(self):
        return options.KDX_LLM_Advanced_Sampling()

    def test_all_disabled_returns_empty(self):
        node = self._make()
        kwargs = {f"{n}_enabled": False for n, *_ in options._ADVANCED_PARAMS}
        kwargs["mirostat_enabled"] = False
        kwargs["extra_body_enabled"] = False
        result = node.execute(base_options=None, **kwargs)
        self.assertEqual(result[0]["options"], {})

    def test_enable_n_ctx(self):
        node = self._make()
        kwargs = {f"{n}_enabled": False for n, *_ in options._ADVANCED_PARAMS}
        kwargs["n_ctx_enabled"] = True
        kwargs["n_ctx"] = 8192
        kwargs["mirostat_enabled"] = False
        kwargs["extra_body_enabled"] = False
        result = node.execute(base_options=None, **kwargs)
        self.assertEqual(result[0]["options"]["n_ctx"], 8192)

    def test_mirostat_group(self):
        node = self._make()
        kwargs = {f"{n}_enabled": False for n, *_ in options._ADVANCED_PARAMS}
        kwargs["mirostat_enabled"] = True
        kwargs["mirostat"] = 2
        kwargs["mirostat_tau"] = 5.0
        kwargs["mirostat_eta"] = 0.1
        kwargs["extra_body_enabled"] = False
        result = node.execute(base_options=None, **kwargs)
        self.assertEqual(result[0]["options"]["mirostat"], 2)
        self.assertEqual(result[0]["options"]["mirostat_tau"], 5.0)
        self.assertEqual(result[0]["options"]["mirostat_eta"], 0.1)

    def test_extra_body_json(self):
        node = self._make()
        kwargs = {f"{n}_enabled": False for n, *_ in options._ADVANCED_PARAMS}
        kwargs["extra_body_enabled"] = True
        kwargs["extra_body"] = '{"custom_param": 42}'
        kwargs["mirostat_enabled"] = False
        result = node.execute(base_options=None, **kwargs)
        self.assertEqual(result[0]["options"]["custom_param"], 42)

    def test_invalid_extra_body_raises(self):
        """P0.2: invalid extra_body JSON now raises ValueError (was silently ignored)."""
        node = self._make()
        kwargs = {f"{n}_enabled": False for n, *_ in options._ADVANCED_PARAMS}
        kwargs["extra_body_enabled"] = True
        kwargs["extra_body"] = "not json"
        kwargs["mirostat_enabled"] = False
        with self.assertRaises(ValueError) as ctx:
            node.execute(base_options=None, **kwargs)
        self.assertIn("extra_body", str(ctx.exception))


# ── session ──────────────────────────────────────────────────────────

class TestSession(unittest.TestCase):
    def setUp(self):
        session._SESSIONS.clear()

    def test_new_session_empty(self):
        self.assertEqual(session.get_session("abc"), [])

    def test_add_exchange(self):
        session.add_exchange("abc", "hello", "hi")
        h = session.get_session("abc")
        self.assertEqual(len(h), 2)
        self.assertEqual(h[0]["role"], "user")
        self.assertEqual(h[1]["role"], "assistant")

    def test_multi_turn(self):
        session.add_exchange("abc", "q1", "a1")
        session.add_exchange("abc", "q2", "a2")
        self.assertEqual(len(session.get_session("abc")), 4)

    def test_max_messages_trimming(self):
        for i in range(10):
            session.add_exchange("abc", f"q{i}", f"a{i}", max_messages=6)
        h = session.get_session("abc")
        self.assertEqual(len(h), 6)
        self.assertEqual(h[0]["content"], "q7")
        self.assertEqual(h[-1]["content"], "a9")

    def test_reset(self):
        session.add_exchange("abc", "q", "a")
        session.reset_session("abc")
        self.assertEqual(session.get_session("abc"), [])

    def test_independent_sessions(self):
        session.add_exchange("aaa", "a1", "a2")
        session.add_exchange("bbb", "b1", "b2")
        self.assertEqual(len(session.get_session("aaa")), 2)
        self.assertEqual(len(session.get_session("bbb")), 2)

    def test_new_session_id_unique(self):
        id1 = session.new_session_id()
        id2 = session.new_session_id()
        self.assertNotEqual(id1, id2)
        self.assertEqual(len(id1), 12)


# ── tools ────────────────────────────────────────────────────────────

class TestToolNode(unittest.TestCase):
    def test_single_tool(self):
        node = tools.KDX_LLM_Tool()
        r = node.execute(name="get_weather", description="Get weather",
                         parameters='{"type": "object", "properties": {"city": {"type": "string"}}}')
        self.assertEqual(len(r[0]["tools"]), 1)
        self.assertEqual(r[0]["tools"][0]["function"]["name"], "get_weather")

    def test_empty_name(self):
        node = tools.KDX_LLM_Tool()
        r = node.execute(name="", description="x", parameters="{}")
        self.assertEqual(len(r[0]["tools"]), 0)

    def test_extra_tools(self):
        node = tools.KDX_LLM_Tool()
        r = node.execute(name="a", description="", parameters="{}",
                         extra_tools='[{"name": "b", "description": "", "parameters": {}}]')
        self.assertEqual(len(r[0]["tools"]), 2)

    def test_invalid_params_json(self):
        node = tools.KDX_LLM_Tool()
        with self.assertRaises(ValueError):
            node.execute(name="t", description="d", parameters="not json")


# ── capabilities ─────────────────────────────────────────────────────

class TestCapabilities(unittest.TestCase):
    def test_empty(self):
        r = capabilities.detect_capabilities([])
        self.assertEqual(r["server"]["model_count"], 0)

    def test_llama_cpp_style(self):
        data = [{"id": "Qwen", "status": {"value": "loaded"},
                 "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]}}]
        r = capabilities.detect_capabilities(data)
        self.assertTrue(r["server"]["has_status"])
        self.assertTrue(r["models"][0]["vision"])

    def test_format_summary(self):
        data = [{"id": "A", "status": {"value": "loaded"}}]
        caps = capabilities.detect_capabilities(data)
        summary = capabilities.format_summary(caps)
        self.assertIn("Models: 1", summary)
        self.assertIn("A", summary)


# ── stats ────────────────────────────────────────────────────────────

class TestStatsNode(unittest.TestCase):
    def test_empty_raw(self):
        node = stats.KDX_LLM_Stats()
        r = node.run(raw="")
        self.assertEqual(r, (0, 0, 0, "", 0.0, 0.0, "{}"))

    def test_valid_raw(self):
        raw = json.dumps({"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                          "_kdx_timing": {"generation_time": 2.5, "tokens_per_second": 2.0},
                          "choices": [{"finish_reason": "stop"}]})
        node = stats.KDX_LLM_Stats()
        r = node.run(raw=raw)
        self.assertEqual(r[0], 10)
        self.assertEqual(r[4], 2.0)
        self.assertEqual(r[5], 2.5)

    def test_invalid_json(self):
        node = stats.KDX_LLM_Stats()
        r = node.run(raw="not json")
        self.assertEqual(r, (0, 0, 0, "", 0.0, 0.0, "{}"))


# ── response formatter ───────────────────────────────────────────────

class TestResponseFormatter(unittest.TestCase):
    def test_passthrough(self):
        node = formatter.KDX_LLM_Response_Formatter()
        r = node.run(response="hello", action="passthrough")
        self.assertEqual(r[0], "hello")

    def test_strip_whitespace(self):
        node = formatter.KDX_LLM_Response_Formatter()
        r = node.run(response="  hello  ", action="strip_whitespace")
        self.assertEqual(r[0], "hello")

    def test_extract_first_code_block(self):
        node = formatter.KDX_LLM_Response_Formatter()
        r = node.run(response='text\n```python\nx = 1\n```\nmore', action="extract_first_code_block")
        self.assertEqual(r[0], "x = 1")

    def test_extract_all_code_blocks(self):
        node = formatter.KDX_LLM_Response_Formatter()
        r = node.run(response='```\na\n```\n```\nb\n```', action="extract_all_code_blocks")
        self.assertEqual(r[0], "a\n\nb")

    def test_truncate(self):
        node = formatter.KDX_LLM_Response_Formatter()
        r = node.run(response="x" * 100, action="truncate", max_length=10)
        self.assertTrue(r[0].startswith("x" * 10))
        self.assertTrue(r[0].endswith("..."))

    def test_lowercase(self):
        node = formatter.KDX_LLM_Response_Formatter()
        r = node.run(response="HELLO", action="lowercase")
        self.assertEqual(r[0], "hello")

    def test_remove_thinking_tags(self):
        node = formatter.KDX_LLM_Response_Formatter()
        text = chr(60) + "think" + chr(62) + "reasoning" + chr(60) + "/think" + chr(62) + " answer"
        r = node.run(response=text, action="remove_thinking_tags")
        self.assertEqual(r[0], "answer")


# ── media settings ───────────────────────────────────────────────────

class TestMediaSettings(unittest.TestCase):
    def test_default_output(self):
        node = media_settings.KDX_LLM_Media_Settings()
        r = node.execute()
        media = r[0]
        self.assertEqual(media["video_sampling_mode"], "uniform")
        self.assertEqual(media["video_max_frames"], 60)
        self.assertEqual(media["audio_max_seconds"], 30.0)
        self.assertIsNone(media["video"])
        self.assertIsNone(media["audio"])

    def test_no_enable_flags(self):
        """Dead enable_video/enable_audio inputs should be gone."""
        inputs = media_settings.KDX_LLM_Media_Settings.INPUT_TYPES()
        all_inputs = {}
        for section in inputs.values():
            all_inputs.update(section)
        self.assertNotIn("enable_video", all_inputs)
        self.assertNotIn("enable_audio", all_inputs)


# ── sampling store ───────────────────────────────────────────────────

class TestSamplingStore(unittest.TestCase):
    def test_lookup_empty(self):
        key, profile = sampling_store.lookup("")
        self.assertIsNone(key)
        self.assertEqual(profile, {})

    def test_lookup_nonexistent(self):
        key, profile = sampling_store.lookup("nonexistent-model-xyz")
        self.assertIsNone(key)
        self.assertEqual(profile, {})

    def test_normalize(self):
        p = sampling_store.normalize({"thinking": {"temperature": 0.5}})
        self.assertEqual(p["thinking"]["sampling"]["temperature"], 0.5)
        self.assertEqual(p["non_thinking"]["sampling"], {})


# ── client: sampling body wiring ─────────────────────────────────────

class TestClientSamplingWiring(unittest.TestCase):
    """Client node must NOT have thinking_sampling/non_thinking_sampling (Chat owns those)."""

    def test_thinking_sampling_input_removed(self):
        inputs = client.KDX_LLM_Client.INPUT_TYPES()
        all_inputs = {}
        for section in inputs.values():
            all_inputs.update(section)
        self.assertNotIn("thinking_sampling", all_inputs)

    def test_non_thinking_sampling_input_removed(self):
        inputs = client.KDX_LLM_Client.INPUT_TYPES()
        all_inputs = {}
        for section in inputs.values():
            all_inputs.update(section)
        self.assertNotIn("non_thinking_sampling", all_inputs)

    def test_client_dict_has_no_sampling_keys(self):
        node = client.KDX_LLM_Client()
        r = node.execute(base_url="http://127.0.0.1:8080", model="m")
        self.assertNotIn("thinking_sampling", r[0])
        self.assertNotIn("non_thinking_sampling", r[0])


# ── client: JS button logic (mock) ───────────────────────────────────

class TestClientJSButtons(unittest.TestCase):
    """Verify the JS file contains the 4 expected buttons for KDX_LLM_Client."""

    def setUp(self):
        with open(os.path.join(V4_DIR, "web", "kdx_llm.js")) as f:
            self.js = f.read()

    def test_select_model_button(self):
        self.assertIn("select model", self.js)
        self.assertIn("fetchModels", self.js)

    def test_load_button(self):
        self.assertIn("load", self.js)
        self.assertIn("doLoad", self.js)

    def test_unload_button(self):
        self.assertIn("unload", self.js)
        self.assertIn("doUnload", self.js)

    def test_save_profile_button(self):
        self.assertIn("save", self.js)

    def test_delete_profile_button(self):
        self.assertIn("delete", self.js)

    def test_select_profile_button(self):
        self.assertIn("refresh profiles", self.js)

    def test_button_uses_native_widget(self):
        self.assertIn('addWidget("button"', self.js)

    def test_node_created_hook(self):
        self.assertIn("nodeCreated", self.js)
        self.assertIn("KDX_LLM_Client", self.js)

    def test_register_extension(self):
        self.assertIn("registerExtension", self.js)


# ── client: URL normalization edge cases ─────────────────────────────

class TestClientURLNormalization(unittest.TestCase):
    def test_trailing_slash(self):
        node = client.KDX_LLM_Client()
        r = node.execute(base_url="http://127.0.0.1:8080/", model="m")
        self.assertEqual(r[0]["url"], "http://127.0.0.1:8080")

    def test_v1_trailing_slash(self):
        node = client.KDX_LLM_Client()
        r = node.execute(base_url="http://127.0.0.1:8080/v1/", model="m")
        self.assertEqual(r[0]["url"], "http://127.0.0.1:8080")

    def test_https(self):
        node = client.KDX_LLM_Client()
        r = node.execute(base_url="https://api.example.com", model="m")
        self.assertEqual(r[0]["url"], "https://api.example.com")

    def test_empty_url(self):
        node = client.KDX_LLM_Client()
        r = node.execute(base_url="", model="m")
        self.assertEqual(r[0]["url"], "")

    def test_validate_inputs_rejects_bad_scheme(self):
        r = client.KDX_LLM_Client.validate_inputs(base_url="ftp://example.com")
        self.assertIsInstance(r, str)
        self.assertIn("http", r)

    def test_validate_inputs_accepts_http(self):
        r = client.KDX_LLM_Client.validate_inputs(base_url="http://127.0.0.1:8080")
        self.assertTrue(r)


# ── chat: sampling merge priority ────────────────────────────────────

class TestChatSamplingMerge(unittest.TestCase):
    """Chat node merge priority: profile < node sampling < JSON string < extra_request_json.

    After P1.1 the merge logic lives in kdx_core.request_builder.build_chat_payload,
    not in chat.py. We verify the builder handles the priority chain.
    """

    def test_node_sampling_overrides_profile(self):
        """build_chat_payload applies sampling_override after profile sampling."""
        payload, req_sampling = _build_chat_payload(
            model="m", messages=[], stream=True,
            profile={"thinking": {"sampling": {"temperature": 0.5}}},
            sampling_override={"temperature": 0.9},
        )
        self.assertEqual(req_sampling["temperature"], 0.9)

    def test_json_string_overrides_node(self):
        """build_chat_payload applies sampling_json_override after node sampling."""
        payload, req_sampling = _build_chat_payload(
            model="m", messages=[], stream=True,
            sampling_override={"temperature": 0.9},
            sampling_json_override={"temperature": 0.3},
        )
        self.assertEqual(req_sampling["temperature"], 0.3)

    def test_extra_request_json_overrides_all(self):
        """build_chat_payload applies extra_request_json last."""
        payload, req_sampling = _build_chat_payload(
            model="m", messages=[], stream=True,
            sampling_override={"temperature": 0.9},
            extra_request_json={"repetition_penalty": 1.5},
        )
        self.assertEqual(payload["repetition_penalty"], 1.5)


# ── model profile: save/load round-trip ──────────────────────────────

class TestModelProfileNode(unittest.TestCase):
    """Model Profile node: read-only passthrough + profile lookup."""

    def _make(self):
        return mpn.KDX_LLM_Model_Profile()

    def _client(self, model="testmodel"):
        return {"url": "http://127.0.0.1:8080", "model": model, "context_length": 4096}

    def test_return_arity(self):
        self.assertEqual(len(mpn.KDX_LLM_Model_Profile.RETURN_TYPES), 3)
        self.assertEqual(len(mpn.KDX_LLM_Model_Profile.RETURN_NAMES), 3)

    def test_no_client_returns_empty_profile(self):
        node = self._make()
        r = node.run(profile="(none)")
        self.assertEqual(len(r), 3)
        self.assertEqual(r[0]["profile_key"], "")  # client_out has profile_key
        # final_profile always has the full structure (even with empty sampling)
        self.assertIn("thinking", r[0]["profile"])
        self.assertIn("non_thinking", r[0]["profile"])
        self.assertEqual(r[0]["profile"]["thinking"]["sampling"], {})
        self.assertEqual(r[1], "")  # profile_key (empty when no model)
        self.assertIn("profile", r[2])  # profile_json

    def test_profile_lookup_with_client(self):
        """Profile is auto-looked-up from the connected client's model."""
        node = self._make()
        # Save a profile first
        sampling_store.save_profile("testmodel", {
            "thinking": {"sampling": {"temperature": 0.9}, "request": {"reasoning": "high"}},
            "non_thinking": {"sampling": {"temperature": 0.3}, "request": {}},
        })
        try:
            r = node.run(client=self._client())
            self.assertEqual(r[0]["profile_key"], "testmodel")
            self.assertEqual(r[0]["profile"]["thinking"]["sampling"]["temperature"], 0.9)
            self.assertEqual(r[1], "testmodel")  # matched_key
        finally:
            sampling_store.delete("testmodel")

    def test_no_profile_no_override(self):
        """No profile, no connected node = empty profile."""
        node = self._make()
        r = node.run(client=self._client("no_profile_xyz"))
        # final_profile always has the full structure (even with empty sampling)
        self.assertIn("thinking", r[0]["profile"])
        self.assertIn("non_thinking", r[0]["profile"])

    def test_profile_dropdown_overrides_model(self):
        """profile dropdown is the primary lookup key."""
        node = self._make()
        sampling_store.save_profile("custom_key", {
            "thinking": {"sampling": {"temperature": 0.5}, "request": {}},
            "non_thinking": {"sampling": {}, "request": {}},
        })
        try:
            r = node.run(client=self._client(), profile="custom_key")
            self.assertEqual(r[0]["profile_key"], "custom_key")
            self.assertEqual(r[0]["profile"]["thinking"]["sampling"]["temperature"], 0.5)
        finally:
            sampling_store.delete("custom_key")


class TestModelProfileRoundTrip(unittest.TestCase):
    """Profile save/load/delete via sampling_store (server-side, not node)."""

    def test_save_and_load(self):
        sampling_store.save_profile("test_model_rt", {
            "thinking": {"sampling": {"temperature": 0.5}, "request": {}},
            "non_thinking": {"sampling": {"temperature": 0.3}, "request": {}},
        })
        try:
            key, profile = sampling_store.lookup("test_model_rt")
            self.assertEqual(key, "test_model_rt")
            self.assertEqual(profile["thinking"]["sampling"]["temperature"], 0.5)
            self.assertEqual(profile["non_thinking"]["sampling"]["temperature"], 0.3)
        finally:
            sampling_store.delete("test_model_rt")

    def test_delete_removes(self):
        sampling_store.save_profile("test_model_del", {
            "thinking": {"sampling": {"temperature": 0.5}, "request": {}},
            "non_thinking": {"sampling": {}, "request": {}},
        })
        sampling_store.delete("test_model_del")
        key, profile = sampling_store.lookup("test_model_del")
        self.assertIsNone(key)
        self.assertEqual(profile, {})

class TestQuickPresets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qsp = _load("kdx_v4.quick_sampling_presets", "quick_sampling_presets.py")

    def test_builtin_presets_exist(self):
        presets = self.qsp.list_presets()
        for name in ["balanced", "creative", "precise", "reasoning", "json_output"]:
            self.assertIn(name, presets)

    def test_get_preset_returns_dict(self):
        p = self.qsp.get_preset("balanced")
        self.assertIsInstance(p, dict)
        self.assertIn("temperature", p)

    def test_builtin_cannot_be_deleted(self):
        result = self.qsp.delete_preset("balanced")
        self.assertFalse(result)


# ── prompt store (system + user) ─────────────────────────────────────

class TestPromptStore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ps = _load("kdx_v4.prompt_store", "prompt_store.py")

    def test_save_and_get(self):
        self.ps.save("test_prompt_ps", "Hello world", "test description")
        p = self.ps.get("test_prompt_ps")
        self.assertEqual(p["prompt"], "Hello world")
        self.assertEqual(p["description"], "test description")
        self.ps.delete("test_prompt_ps")

    def test_names_sorted(self):
        names = self.ps.names()
        self.assertEqual(names, sorted(names))

    def test_delete_nonexistent(self):
        result = self.ps.delete("nonexistent_xyz")
        self.assertFalse(result)


# ── chat ─────────────────────────────────────────────────────────────

class TestChatNode(unittest.TestCase):
    def test_empty_prompt_returns_empty(self):
        node = chat.KDX_LLM_Chat()
        r = node.run(prompt="")
        self.assertEqual(len(r), 11)
        self.assertEqual(r[0], "")
        self.assertEqual(r[1], "")
        self.assertIsInstance(r[8], dict)  # response_obj (9th output)
        self.assertIsInstance(r[9], _SessionStub)  # session (10th output)
        self.assertEqual(r[10], "[]")  # tool_calls (11th output)

    def test_whitespace_prompt_returns_empty(self):
        node = chat.KDX_LLM_Chat()
        r = node.run(prompt="   ")
        self.assertEqual(len(r), 11)
        self.assertEqual(r[0], "")
        self.assertEqual(r[1], "")
        self.assertIsInstance(r[9], _SessionStub)
        self.assertEqual(r[10], "[]")

    def test_is_changed_hash_differs_on_prompt(self):
        h1 = chat.KDX_LLM_Chat.IS_CHANGED(prompt="hello")
        h2 = chat.KDX_LLM_Chat.IS_CHANGED(prompt="world")
        self.assertNotEqual(h1, h2)

    def test_is_changed_handles_none_client(self):
        h = chat.KDX_LLM_Chat.IS_CHANGED(client=None, thinking_sampling=None,
                                         non_thinking_sampling=None, tools=None)
        self.assertIsInstance(h, str)
        self.assertEqual(len(h), 64)

    def test_return_arity(self):
        self.assertEqual(len(chat.KDX_LLM_Chat.RETURN_TYPES), 11)
        self.assertEqual(len(chat.KDX_LLM_Chat.RETURN_NAMES), 11)


# ── model profile node ───────────────────────────────────────────────


if __name__ == "__main__":
    unittest.main()
