"""Real core contract tests for KDX LLM.

These tests avoid ComfyUI/network dependencies and exercise the actual
kdx_core modules plus the Chat node with a fake transport.
"""

import importlib.util
import json
import os
import sys
import types
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = "kdx_core_contract_test"


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


_register_package()

# Stub modules that would otherwise pull ComfyUI/network/media dependencies.
media = types.ModuleType(PKG + ".media")
media.build_user_content = lambda **kw: kw.get("prompt", "")
sys.modules[PKG + ".media"] = media

http = types.ModuleType(PKG + "._http")
class _TransportStub:
    def __init__(self, *args, **kwargs):
        pass
http.LLMClient = _TransportStub
http.normalize_base_url = lambda url: (url or "").strip().rstrip("/")
sys.modules[PKG + "._http"] = http

for core_name in ("session", "response", "request_builder", "fingerprint", "sse_parser", "profile_resolver", "context", "task_prompt"):
    _load("kdx_core." + core_name, os.path.join("kdx_core", core_name + ".py"))

for name in ("session", "prompt_store", "user_prompt_store", "sampling_store", "postprocess", "quick_sampling_presets", "session_store"):
    _load(name, name + ".py")

chat = _load("chat", "chat.py")
session_node = _load("session_node", "session_node.py")
rb = sys.modules[PKG + ".kdx_core.request_builder"]
fp = sys.modules[PKG + ".kdx_core.fingerprint"]
sse = sys.modules[PKG + ".kdx_core.sse_parser"]
ctx = sys.modules[PKG + ".kdx_core.context"]
tp = sys.modules[PKG + ".kdx_core.task_prompt"]
qsp = sys.modules[PKG + ".quick_sampling_presets"]
session_store = sys.modules[PKG + ".session_store"]
KDXLLMSession = sys.modules[PKG + ".kdx_core.session"].KDXLLMSession


class FakeLLM:
    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    def chat(self, payload):
        return {
            "model": "test-model",
            "choices": [{
                "message": {"role": "assistant", "content": '{"ok": true}'},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        }

    def load_model(self, *args, **kwargs):
        return {"status": "ok"}

    def unload_model(self, *args, **kwargs):
        return {"status": "ok"}


chat.LLMClient = FakeLLM


class TestJsonModeTriState(unittest.TestCase):
    def _run(self, json_mode):
        return chat.KDX_LLM_Chat().run(
            prompt="hi",
            model_preset="qwen_json",
            client={"url": "http://x", "model": "m", "context_length": 128, "provider": "auto"},
            json_mode=json_mode,
            stream=False,
        )

    def test_auto_uses_preset(self):
        out = self._run("auto")
        self.assertEqual(out[2], '{"ok": true}')

    def test_off_disables_forced_json_but_still_parses_obvious_json(self):
        out = self._run("off")
        self.assertEqual(out[2], '{"ok": true}')
        info = json.loads(out[7])
        self.assertFalse(info["json_mode"])

    def test_backward_boolean_false_disables_forced_json_but_still_parses_obvious_json(self):
        out = self._run(False)
        self.assertEqual(out[2], '{"ok": true}')
        info = json.loads(out[7])
        self.assertFalse(info["json_mode"])

    def test_backward_boolean_true_enables(self):
        out = self._run(True)
        self.assertEqual(out[2], '{"ok": true}')


class _ExplodingLLM:
    """Transport that fails the test on any construction or call."""

    def __init__(self, *args, **kwargs):
        raise AssertionError("llm_enabled=False must not create an LLM client")


class TestLlmSwitchOff(unittest.TestCase):
    def setUp(self):
        chat.LLMClient = _ExplodingLLM

    def tearDown(self):
        chat.LLMClient = FakeLLM

    def test_off_skips_client_and_returns_prompt_unchanged(self):
        prompt = "  a cat\non a roof  "
        out = chat.KDX_LLM_Chat().run(
            prompt=prompt,
            client={"url": "http://x", "model": "m"},
            load_before=True,
            unload_after=True,
            llm_enabled=False,
        )
        self.assertEqual(len(out), 11)
        self.assertEqual(out[0], prompt)
        self.assertEqual(out[1:8], ("",) * 7)
        self.assertIsInstance(out[8], dict)
        self.assertEqual(out[10], "[]")

    def test_off_preserves_connected_session(self):
        sess = KDXLLMSession(session_id="s1").add_exchange("u", "a")
        out = chat.KDX_LLM_Chat().run(prompt="hi", session=sess, llm_enabled=False)
        self.assertEqual(out[9], sess)

    def test_off_with_empty_prompt_returns_empty(self):
        out = chat.KDX_LLM_Chat().run(prompt="", llm_enabled=False)
        self.assertEqual(out[0], "")

    def test_execute_node_reports_llm_off_in_ui(self):
        res = chat.KDX_LLM_Chat().execute_node(prompt="hi", llm_enabled=False)
        self.assertEqual(res["ui"]["kdx_llm_off"], [True])
        self.assertEqual(res["result"][0], "hi")


class TestLlmSwitchOn(unittest.TestCase):
    def test_not_connected_true_and_none_call_llm(self):
        for kwargs in ({}, {"llm_enabled": True}, {"llm_enabled": None}):
            out = chat.KDX_LLM_Chat().run(
                prompt="hi", client={"url": "http://x", "model": "m"}, stream=False, **kwargs,
            )
            self.assertEqual(out[0], '{"ok": true}')

    def test_execute_node_ui_flag_false_by_default(self):
        res = chat.KDX_LLM_Chat().execute_node(prompt="hi", client={"url": "http://x", "model": "m"}, stream=False)
        self.assertEqual(res["ui"]["kdx_llm_off"], [False])

    def test_input_is_optional_boolean_socket_default_true(self):
        optional = chat.KDX_LLM_Chat.INPUT_TYPES()["optional"]
        # New sockets are appended after llm_enabled (saved workflows keep their slots).
        self.assertEqual(list(optional)[-2:], ["llm_enabled", "task_prompt"])
        typ, opts = optional["llm_enabled"]
        self.assertEqual(typ, "BOOLEAN")
        self.assertIs(opts["default"], True)
        self.assertIs(opts.get("forceInput"), True)  # always-visible socket, not a widget

    def test_fingerprint_includes_switch(self):
        base = {"prompt": "hi"}
        self.assertNotEqual(fp.fingerprint({**base, "llm_enabled": False}), fp.fingerprint({**base, "llm_enabled": True}))
        # Not connected hashes like an explicit True.
        self.assertEqual(fp.fingerprint(base), fp.fingerprint({**base, "llm_enabled": True}))
        h1 = chat.KDX_LLM_Chat.IS_CHANGED(prompt="hi", llm_enabled=False)
        h2 = chat.KDX_LLM_Chat.IS_CHANGED(prompt="hi", llm_enabled=True)
        self.assertNotEqual(h1, h2)


class _CapturingLLM(FakeLLM):
    payloads = []

    def chat(self, payload):
        _CapturingLLM.payloads.append(payload)
        return super().chat(payload)


class TestTaskPrompt(unittest.TestCase):
    def test_merge_rules(self):
        self.assertEqual(tp.apply_task_prompt("", "cat"), "cat")
        self.assertEqual(tp.apply_task_prompt("  \n", "cat"), "cat")
        self.assertEqual(tp.apply_task_prompt("Rules.\n\n", "cat"), "Rules.\n\ncat")
        self.assertEqual(tp.apply_task_prompt("in: {prompt}!", "cat"), "in: cat!")
        self.assertEqual(tp.apply_task_prompt('q: {prompt_json}', 'say "hi"'), 'q: "say \\"hi\\""')

    def test_minimax_t2i_format_rules(self):
        task = 'Return {{"expanded_caption": "..."}}.\n\ninput_text: {}\noutput_text:'
        self.assertEqual(
            tp.apply_task_prompt(task, "a {red} cat"),
            'Return {"expanded_caption": "..."}.\n\ninput_text: a {red} cat\noutput_text:',
        )

    def test_no_placeholder_keeps_braces_as_written(self):
        task = 'Output {"a": 1} and {{b}}.'
        self.assertEqual(tp.apply_task_prompt(task, "cat"), task + "\n\ncat")
        self.assertFalse(tp.has_placeholder("literal {{prompt}} and {name}"))

    def test_llm_off_returns_bare_prompt(self):
        chat.LLMClient = _ExplodingLLM
        try:
            out = chat.KDX_LLM_Chat().run(prompt="a cat", task_prompt="Expand: {}", llm_enabled=False)
        finally:
            chat.LLMClient = FakeLLM
        self.assertEqual(out[0], "a cat")

    def test_llm_on_sends_merged_message(self):
        chat.LLMClient = _CapturingLLM
        _CapturingLLM.payloads = []
        try:
            out = chat.KDX_LLM_Chat().run(
                prompt="  a cat  ", task_prompt="Expand: {}", system_prompt="sys",
                client={"url": "http://x", "model": "m"}, stream=False,
            )
        finally:
            chat.LLMClient = FakeLLM
        messages = _CapturingLLM.payloads[-1]["messages"]
        self.assertEqual(messages[0], {"role": "system", "content": "sys"})
        self.assertEqual(messages[-1], {"role": "user", "content": "Expand: a cat"})
        self.assertIs(json.loads(out[7])["task_prompt"], True)

    def test_fingerprint_includes_task_prompt(self):
        self.assertNotEqual(
            fp.fingerprint({"prompt": "hi", "task_prompt": "A {}"}),
            fp.fingerprint({"prompt": "hi", "task_prompt": "B {}"}),
        )
        self.assertEqual(fp.fingerprint({"prompt": "hi"}), fp.fingerprint({"prompt": "hi", "task_prompt": ""}))


class TestRequestBuilder(unittest.TestCase):
    def test_sampling_n_ctx_overrides_client_context(self):
        payload, _ = rb.build_chat_payload(
            model="m",
            messages=[],
            stream=False,
            thinking_on=False,
            sampling_override={"n_ctx": 8192},
            context_length=4096,
        )
        self.assertEqual(payload["n_ctx"], 8192)

    def test_client_context_used_when_no_explicit_n_ctx(self):
        payload, _ = rb.build_chat_payload(
            model="m",
            messages=[],
            stream=False,
            thinking_on=False,
            context_length=4096,
        )
        self.assertEqual(payload["n_ctx"], 4096)

    def test_qwen_i_prefix_for_llama_cpp(self):
        payload, _ = rb.build_chat_payload(
            model="Qwen3.5-7B",
            messages=[],
            stream=False,
            thinking_on=False,
            reasoning_mode="low",
            context_length=0,
            provider="llama_cpp",
        )
        self.assertEqual(payload["chat_template_kwargs"]["reasoning_effort"], "ilow")

    def test_no_i_prefix_for_vllm(self):
        payload, _ = rb.build_chat_payload(
            model="Qwen3.5-7B",
            messages=[],
            stream=False,
            thinking_on=False,
            reasoning_mode="low",
            context_length=0,
            provider="vllm",
        )
        self.assertEqual(payload["chat_template_kwargs"]["reasoning_effort"], "low")

    def test_profile_flag_forces_i_prefix(self):
        payload, _ = rb.build_chat_payload(
            model="OtherModel",
            messages=[],
            stream=False,
            thinking_on=False,
            profile={"non_thinking": {"sampling": {}, "request": {"qwen_i_prefix": True}}},
            reasoning_mode="low",
            context_length=0,
            provider="vllm",
        )
        self.assertEqual(payload["chat_template_kwargs"]["reasoning_effort"], "ilow")
        self.assertNotIn("qwen_i_prefix", payload)

    def test_json_mode_uses_response_format_for_openai_like_provider(self):
        payload, _ = rb.build_chat_payload(
            model="m",
            messages=[{"role": "user", "content": "hi"}],
            stream=False,
            thinking_on=False,
            context_length=0,
            json_mode=True,
            provider="vllm",
        )
        self.assertEqual(payload["response_format"], {"type": "json_object"})

    def test_json_mode_avoids_response_format_for_llama_cpp(self):
        payload, _ = rb.build_chat_payload(
            model="m",
            messages=[{"role": "user", "content": "hi"}],
            stream=False,
            thinking_on=False,
            context_length=0,
            json_mode=True,
            provider="llama_cpp",
        )
        self.assertNotIn("response_format", payload)
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertIn("valid JSON object", payload["messages"][0]["content"])


class TestFingerprint(unittest.TestCase):
    def test_same_turn_count_different_messages_changes_hash(self):
        session_a = {"session_id": "s", "messages": [
            {"role": "user", "content": "A"},
            {"role": "assistant", "content": "1"},
        ]}
        session_b = {"session_id": "s", "messages": [
            {"role": "user", "content": "B"},
            {"role": "assistant", "content": "2"},
        ]}
        ha = fp.canonical_hash(fp.build_fingerprint_key({"prompt": "x", "session": session_a}))
        hb = fp.canonical_hash(fp.build_fingerprint_key({"prompt": "x", "session": session_b}))
        self.assertNotEqual(ha, hb)

    def test_media_base64_changes_changes_hash_without_embedding_full_payload(self):
        session_a = {"session_id": "s", "messages": [
            {"role": "user", "content": [
                {"type": "text", "text": "look"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,AAA"}},
            ]},
            {"role": "assistant", "content": "ok"},
        ]}
        session_b = {"session_id": "s", "messages": [
            {"role": "user", "content": [
                {"type": "text", "text": "look"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,BBB"}},
            ]},
            {"role": "assistant", "content": "ok"},
        ]}
        key = fp.build_fingerprint_key({"prompt": "x", "session": session_a})
        ha = fp.canonical_hash(key)
        hb = fp.canonical_hash(fp.build_fingerprint_key({"prompt": "x", "session": session_b}))
        self.assertNotEqual(ha, hb)
        self.assertNotIn("AAA", json.dumps(key))


class TestSSEParser(unittest.TestCase):
    def test_utf8_split_across_chunks(self):
        acc = sse.SSEAccumulator()
        part1 = json.dumps({"choices": [{"delta": {"content": "slovensk"}}]})
        part2 = json.dumps({"choices": [{"delta": {"content": "á"}}]})
        raw = ("data: " + part1 + "\n\ndata: " + part2 + "\n\ndata: [DONE]\n\n").encode("utf-8")
        for i in range(0, len(raw), 3):
            acc.feed_bytes(raw[i:i + 3])
        resp = acc.build_response()
        self.assertEqual(resp["choices"][0]["message"]["content"], "slovenská")


class TestContextTrimming(unittest.TestCase):
    def test_disabled_keeps_messages(self):
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "old reply"},
            {"role": "user", "content": "new"},
        ]
        self.assertEqual(ctx.trim_messages(msgs, 0), msgs)

    def test_trims_oldest_history_but_keeps_system_and_current_user(self):
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
            {"role": "assistant", "content": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},
            {"role": "user", "content": "current question"},
        ]
        trimmed = ctx.trim_messages(msgs, 30)
        self.assertEqual(trimmed[0]["role"], "system")
        self.assertEqual(trimmed[-1]["content"], "current question")
        self.assertLess(len(trimmed), len(msgs))

    def test_tokenizer_param_falls_back_without_tiktoken(self):
        self.assertGreater(ctx.estimate_text_tokens("hello world", tokenizer="tiktoken"), 0)
        self.assertGreater(ctx.estimate_text_tokens("hello world", tokenizer="auto"), 0)

    def test_image_parts_use_fixed_estimate_not_base64_length(self):
        small = [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + ("A" * 10000)}}]}]
        tokens = ctx.estimate_messages_tokens(small)
        self.assertLess(tokens, 200)


class TestQuickPresetsStore(unittest.TestCase):
    def test_mtime_callable(self):
        self.assertIsInstance(qsp.mtime(), float)


class TestSessionPersistence(unittest.TestCase):
    def test_save_and_load_named_session(self):
        name = "kdx_test_session"
        session_node_module = session_node
        try:
            sess = KDXLLMSession(session_id="abc")
            sess = sess.add_exchange("hello", "hi there")
            out = session_node_module.KDX_LLM_Session().execute(
                action="save",
                session=sess,
                session_name=name,
            )
            self.assertEqual(out[2], 1)

            loaded = session_node_module.KDX_LLM_Session().execute(
                action="load",
                session_name=name,
            )
            self.assertEqual(loaded[2], 1)
            self.assertEqual(loaded[0].messages[0]["content"], "hello")
            self.assertEqual(loaded[0].messages[1]["content"], "hi there")
        finally:
            session_store.delete(name)



# ── Audit fixes (0.6.2) ────────────────────────────────────────────────

import asyncio
import tempfile

model_profile_node = _load("model_profile_node", "model_profile_node.py")
system_prompt_node = _load("system_prompt_node", "system_prompt_node.py")
user_prompt_node = _load("user_prompt_node", "user_prompt_node.py")
quick_sampling_node = _load("quick_sampling_node", "quick_sampling_node.py")
sampling_store_mod = sys.modules[PKG + ".sampling_store"]


def _load_server_routes():
    """Load server_routes with ComfyUI's PromptServer (and aiohttp if absent) stubbed."""
    if "server" not in sys.modules:
        server = types.ModuleType("server")
        server.PromptServer = type("PromptServer", (), {"instance": None})
        sys.modules["server"] = server
    try:
        import aiohttp.web
    except ImportError:
        aiohttp = types.ModuleType("aiohttp")
        aiohttp.web = types.ModuleType("aiohttp.web")
        sys.modules["aiohttp"] = aiohttp
        sys.modules["aiohttp.web"] = aiohttp.web
    _load("_http_real", "_http.py")
    sys.modules[PKG + "._http"].normalize_base_url = sys.modules[PKG + "._http_real"].normalize_base_url
    return _load("server_routes", "server_routes.py")


class TestProfileDropdownValidation(unittest.TestCase):
    """Saved-name combos must not fail ComfyUI's 'Value not in list' check."""

    def test_none_always_offered_and_default(self):
        for node_cls in (
            model_profile_node.KDX_LLM_Model_Profile,
            system_prompt_node.KDX_LLM_System_Prompt,
            user_prompt_node.KDX_LLM_User_Prompt,
        ):
            spec = node_cls.INPUT_TYPES()["required"]["profile"]
            self.assertEqual(spec[0][0], "(none)", node_cls.__name__)
            self.assertEqual(spec[1]["default"], "(none)", node_cls.__name__)
        presets = quick_sampling_node.KDX_LLM_Quick_Presets.INPUT_TYPES()["required"]["preset"][0]
        self.assertIn("(none)", presets)

    def test_validate_inputs_accepts_unknown_names(self):
        self.assertIs(model_profile_node.KDX_LLM_Model_Profile.VALIDATE_INPUTS(profile="deleted-profile"), True)
        self.assertIs(system_prompt_node.KDX_LLM_System_Prompt.VALIDATE_INPUTS(profile="gone"), True)
        self.assertIs(user_prompt_node.KDX_LLM_User_Prompt.VALIDATE_INPUTS(profile="gone"), True)
        self.assertIs(quick_sampling_node.KDX_LLM_Quick_Presets.VALIDATE_INPUTS(preset="gone"), True)

    def test_unknown_prompt_profile_keeps_typed_text(self):
        out = system_prompt_node.KDX_LLM_System_Prompt().run(profile="gone", system_prompt="typed")
        self.assertEqual(out[0], "typed")


class TestModelProfileSelection(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("KDX_LLM_PROFILES_FILE")
        os.environ["KDX_LLM_PROFILES_FILE"] = os.path.join(self._tmp.name, "profiles.json")
        sampling_store_mod.save_profile("aaa-qwen", {"non_thinking": {"sampling": {"temperature": 0.1}}})
        sampling_store_mod.save_profile("llama-3", {"non_thinking": {"sampling": {"temperature": 0.9}}})

    def tearDown(self):
        if self._old is None:
            os.environ.pop("KDX_LLM_PROFILES_FILE", None)
        else:
            os.environ["KDX_LLM_PROFILES_FILE"] = self._old
        self._tmp.cleanup()

    def test_default_none_uses_clients_model_profile(self):
        default = model_profile_node.KDX_LLM_Model_Profile.INPUT_TYPES()["required"]["profile"][1]["default"]
        out = model_profile_node.KDX_LLM_Model_Profile().run(profile=default, client={"model": "llama-3"})
        self.assertEqual(out[1], "llama-3")
        self.assertEqual(out[0]["profile"]["non_thinking"]["sampling"]["temperature"], 0.9)

    def test_deleted_profile_falls_back_to_model(self):
        out = model_profile_node.KDX_LLM_Model_Profile().run(profile="deleted", client={"model": "llama-3"})
        self.assertEqual(out[1], "llama-3")


class _RecordingLLM(FakeLLM):
    last_payload = None

    def chat(self, payload):
        _RecordingLLM.last_payload = payload
        return super().chat(payload)


class TestThinkingFlag(unittest.TestCase):
    def setUp(self):
        self._orig = chat.LLMClient
        chat.LLMClient = _RecordingLLM

    def tearDown(self):
        chat.LLMClient = self._orig

    def _payload(self, **kw):
        chat.KDX_LLM_Chat().run(
            prompt="hi",
            client={"url": "http://x", "model": "qwen3", "provider": "llama_cpp"},
            stream=False,
            **kw,
        )
        return _RecordingLLM.last_payload

    def test_thinking_off_disables_template_thinking(self):
        payload = self._payload(thinking="off", reasoning_mode="")
        self.assertIs(payload["chat_template_kwargs"]["enable_thinking"], False)

    def test_thinking_on_enables_template_thinking(self):
        payload = self._payload(thinking="on", reasoning_mode="")
        self.assertIs(payload["chat_template_kwargs"]["enable_thinking"], True)

    def test_generic_auto_sends_no_template_kwargs(self):
        payload = self._payload(thinking="auto", reasoning_mode="")
        self.assertNotIn("chat_template_kwargs", payload)

    def test_builder_keeps_existing_template_kwargs(self):
        payload, _ = rb.build_chat_payload(
            model="m", messages=[], stream=False, thinking_on=False,
            profile={"non_thinking": {"request": {"chat_template_kwargs": {"foo": 1}}}},
            send_thinking_flag=True,
        )
        self.assertEqual(payload["chat_template_kwargs"], {"foo": 1, "enable_thinking": False})


class TestServerRoutesHardening(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.routes = _load_server_routes()

    def test_default_key_env_allowed(self):
        self.assertEqual(self.routes._resolve_key_env(""), "KDX_LLM_API_KEY")
        self.assertEqual(self.routes._resolve_key_env("KDX_LLM_API_KEY"), "KDX_LLM_API_KEY")

    def test_arbitrary_key_env_rejected(self):
        with self.assertRaises(ValueError):
            self.routes._resolve_key_env("OPENAI_API_KEY")

    def test_allowlisted_key_env_accepted(self):
        old = os.environ.get("KDX_ALLOWED_KEY_ENVS")
        os.environ["KDX_ALLOWED_KEY_ENVS"] = "MY_LLM_KEY, OTHER"
        try:
            self.assertEqual(self.routes._resolve_key_env("MY_LLM_KEY"), "MY_LLM_KEY")
        finally:
            if old is None:
                os.environ.pop("KDX_ALLOWED_KEY_ENVS", None)
            else:
                os.environ["KDX_ALLOWED_KEY_ENVS"] = old

    def test_blocking_calls_run_off_event_loop(self):
        import threading
        loop_thread = []

        async def main():
            loop_thread.append(threading.get_ident())
            return await self.routes._run_blocking(threading.get_ident)

        worker = asyncio.run(main())
        self.assertNotEqual(worker, loop_thread[0])


json_extract_node = _load("json_extract_node", "json_extract_node.py")


class TestJsonExtract(unittest.TestCase):
    def _run(self, text, key, **kw):
        return json_extract_node.KDX_LLM_JSON_Extract().run(json=text, key=key, **kw)

    def test_top_level_string_without_quotes(self):
        value, found, value_json = self._run('{"rewritten_prompt": "a cat on a roof", "style": "photo"}', "rewritten_prompt")
        self.assertEqual(value, "a cat on a roof")
        self.assertTrue(found)
        self.assertEqual(value_json, '"a cat on a roof"')

    def test_code_fence_and_surrounding_text(self):
        text = 'Here you go:\n```json\n{"rewritten_prompt": "x"}\n```'
        self.assertEqual(self._run(text, "rewritten_prompt")[0], "x")
        self.assertEqual(self._run('Sure! {"a": 1} hope it helps', "a")[0], "1")

    def test_nested_and_list_paths(self):
        text = '{"scene": {"lighting": "soft"}, "shots": [{"prompt": "p0"}, {"prompt": "p1"}]}'
        self.assertEqual(self._run(text, "scene.lighting")[0], "soft")
        self.assertEqual(self._run(text, "shots.1.prompt")[0], "p1")
        self.assertEqual(self._run(text, "shots[0].prompt")[0], "p0")

    def test_case_insensitive_fallback(self):
        self.assertEqual(self._run('{"Rewritten_Prompt": "y"}', "rewritten_prompt")[0], "y")

    def test_literal_dotted_key_wins(self):
        self.assertEqual(self._run('{"a.b": "literal", "a": {"b": "path"}}', "a.b")[0], "literal")

    def test_object_value_and_scalars(self):
        value, _, value_json = self._run('{"o": {"k": [1, 2]}, "t": true, "n": null}', "o")
        self.assertEqual(json.loads(value), {"k": [1, 2]})
        self.assertEqual(json.loads(value_json), {"k": [1, 2]})
        self.assertEqual(self._run('{"t": true}', "t")[0], "true")
        self.assertEqual(self._run('{"n": null}', "n")[:2], ("", True))

    def test_empty_key_returns_whole_json(self):
        self.assertEqual(json.loads(self._run('{"a": 1}', "")[0]), {"a": 1})

    def test_missing_key_uses_default(self):
        self.assertEqual(self._run('{"a": 1}', "b", default="fallback"), ("fallback", False, ""))
        self.assertEqual(self._run("not json at all", "a", default="d")[:2], ("d", False))
        self.assertEqual(self._run("", "a")[:2], ("", False))

    def test_fail_if_missing_lists_available_keys(self):
        with self.assertRaises(ValueError) as ctx:
            self._run('{"scene": {"lighting": "soft"}}', "scene.camera", fail_if_missing=True)
        self.assertIn("camera", str(ctx.exception))
        self.assertIn("lighting", str(ctx.exception))

    def test_list_index_out_of_range(self):
        self.assertFalse(self._run('{"shots": []}', "shots.0")[1])


class TestNodeDescriptions(unittest.TestCase):
    def test_every_registered_node_has_a_description(self):
        modules = [
            "chat", "session_node", "model_profile_node", "system_prompt_node", "user_prompt_node",
            "quick_sampling_node", "json_extract_node", "prompt_template_node", "json_fields_node",
        ]
        for extra in ("client", "options", "media_settings", "tools", "stats", "response_formatter", "diagnostics"):
            modules.append(_load(extra, extra + ".py").__name__.split(".")[-1])
        for name in modules:
            mod = sys.modules[PKG + "." + name]
            for node_id, cls in mod.NODE_CLASS_MAPPINGS.items():
                self.assertTrue(getattr(cls, "DESCRIPTION", "").strip(), node_id)


# ── Reliability (0.7.0) ────────────────────────────────────────────────

store_utils = _load("_store_utils", "_store_utils.py")


class TestTrimKeepsAlternation(unittest.TestCase):
    def test_trimmed_history_never_starts_with_assistant(self):
        msgs = [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "u1 " + "x" * 400},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
            {"role": "assistant", "content": "a2"},
            {"role": "user", "content": "now"},
        ]
        # Budget fits system + a1 + u2 + a2 + now, but not u1.
        budget = ctx.estimate_messages_tokens([msgs[0]] + msgs[2:])
        out = ctx.trim_messages(msgs, budget)
        roles = [m["role"] for m in out]
        self.assertEqual(roles, ["system", "user", "assistant", "user"])
        self.assertEqual(out[1]["content"], "u2")


class TestHistoryMedia(unittest.TestCase):
    IMG = {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,AAAA"}}

    def _hist(self):
        return [
            {"role": "user", "content": [{"type": "text", "text": "first"}, self.IMG]},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": [{"type": "text", "text": "second"}, self.IMG]},
            {"role": "assistant", "content": "a2"},
        ]

    def test_latest_keeps_only_most_recent_media(self):
        out = ctx.strip_history_media(self._hist(), "latest")
        self.assertIsInstance(out[0]["content"], str)
        self.assertIn("first", out[0]["content"])
        self.assertIn("omitted", out[0]["content"])
        self.assertIsInstance(out[2]["content"], list)

    def test_latest_drops_all_when_current_has_media(self):
        out = ctx.strip_history_media(self._hist(), "latest", current_has_media=True)
        self.assertFalse(any(ctx.has_media(m["content"]) for m in out))

    def test_all_and_none(self):
        self.assertEqual(ctx.strip_history_media(self._hist(), "all"), self._hist())
        self.assertFalse(any(ctx.has_media(m["content"]) for m in ctx.strip_history_media(self._hist(), "none")))

    def test_original_history_not_mutated(self):
        hist = self._hist()
        ctx.strip_history_media(hist, "none")
        self.assertIsInstance(hist[0]["content"], list)


class _FailingLLM(FakeLLM):
    unloaded = []

    def chat(self, payload):
        raise RuntimeError("boom")

    def unload_model(self, model):
        _FailingLLM.unloaded.append(model)
        return {"status": "ok"}


class TestUnloadAfterOnError(unittest.TestCase):
    def test_unload_runs_even_when_chat_fails(self):
        orig = chat.LLMClient
        chat.LLMClient = _FailingLLM
        _FailingLLM.unloaded = []
        try:
            with self.assertRaises(RuntimeError):
                chat.KDX_LLM_Chat().run(prompt="hi", client={"url": "http://x", "model": "m"}, unload_after=True, stream=False)
        finally:
            chat.LLMClient = orig
        self.assertEqual(_FailingLLM.unloaded, ["m"])


class TestCorruptStoreBackup(unittest.TestCase):
    def test_backup_created_only_for_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = os.path.join(tmp, "good.json")
            bad = os.path.join(tmp, "bad.json")
            with open(good, "w", encoding="utf-8") as f:
                f.write('{"a": 1}')
            with open(bad, "w", encoding="utf-8") as f:
                f.write('{"a": 1,,}')
            self.assertIsNone(store_utils.backup_if_corrupt(good))
            self.assertIsNone(store_utils.backup_if_corrupt(os.path.join(tmp, "missing.json")))
            backup = store_utils.backup_if_corrupt(bad)
            self.assertTrue(backup and os.path.isfile(backup))
            with open(backup, encoding="utf-8") as f:
                self.assertEqual(f.read(), '{"a": 1,,}')

    def test_saving_profile_keeps_copy_of_broken_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "profiles.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write('{"models": {"keep-me": {}},}')
            old = os.environ.get("KDX_LLM_PROFILES_FILE")
            os.environ["KDX_LLM_PROFILES_FILE"] = path
            try:
                self.assertTrue(sampling_store_mod.save_profile("new", {}))
            finally:
                if old is None:
                    os.environ.pop("KDX_LLM_PROFILES_FILE", None)
                else:
                    os.environ["KDX_LLM_PROFILES_FILE"] = old
            backups = [n for n in os.listdir(tmp) if ".corrupt-" in n]
            self.assertEqual(len(backups), 1)

# ── Prompt Template / JSON Output Format / JSON Fields ─────────────────

prompt_template_node = _load("prompt_template_node", "prompt_template_node.py")
json_fields_node = _load("json_fields_node", "json_fields_node.py")


class TestPromptTemplate(unittest.TestCase):
    def _run(self, **kw):
        return prompt_template_node.KDX_LLM_Prompt_Template().run(**kw)

    def test_fills_inputs_and_variables(self):
        text, missing = self._run(
            template="Rewrite: {text_1}\nStyle: {style}",
            text_1="a cat",
            variables="style = cinematic\n# comment\nmood: calm",
        )
        self.assertEqual(text, "Rewrite: a cat\nStyle: cinematic")
        self.assertEqual(missing, "")

    def test_literal_braces_and_json_kept(self):
        text, _ = self._run(template='Answer as {{"prompt": "..."}} about {text_1}', text_1="dogs")
        self.assertEqual(text, 'Answer as {"prompt": "..."} about dogs')

    def test_missing_placeholder_left_or_error(self):
        text, missing = self._run(template="Hi {name}")
        self.assertEqual((text, missing), ("Hi {name}", "name"))
        with self.assertRaises(ValueError):
            self._run(template="Hi {name}", fail_on_missing=True)

    def test_bad_variable_line(self):
        with self.assertRaises(ValueError):
            self._run(template="x", variables="this is not a variable")


class TestJsonOutputFormatAndFields(unittest.TestCase):
    def test_parse_fields_lines_commas_descriptions(self):
        self.assertEqual(
            json_fields_node.parse_fields("rewritten_prompt: the prompt\n- negative_prompt\n\nstyle"),
            [("rewritten_prompt", "the prompt"), ("negative_prompt", ""), ("style", "")],
        )
        self.assertEqual([n for n, _ in json_fields_node.parse_fields("a, b ,c")], ["a", "b", "c"])
        with self.assertRaises(ValueError):
            json_fields_node.parse_fields("bad name with spaces")

    def test_output_format_builds_system_prompt(self):
        system, fields = json_fields_node.KDX_LLM_JSON_Output_Format().run(
            fields="rewritten_prompt: improved prompt\nstyle", system_prompt="You are an art director."
        )
        self.assertTrue(system.startswith("You are an art director."))
        self.assertIn('"rewritten_prompt": improved prompt', system)
        self.assertIn('"style"', system)
        self.assertEqual(fields, "rewritten_prompt\nstyle")

    def test_fields_split_in_order(self):
        out = json_fields_node.KDX_LLM_JSON_Fields().run(
            json='```json\n{"negative_prompt": "blur", "rewritten_prompt": "a cat", "n": 3}\n```',
            fields="rewritten_prompt\nnegative_prompt\nn",
        )
        self.assertEqual(out[:3], ("a cat", "blur", "3"))
        self.assertEqual(out[3:6], ("", "", ""))
        self.assertEqual(out[6:], (True, ""))
        self.assertEqual(len(out), len(json_fields_node.KDX_LLM_JSON_Fields.RETURN_TYPES))

    def test_fields_missing_default_and_error(self):
        out = json_fields_node.KDX_LLM_JSON_Fields().run(json='{"a": "x"}', fields="a, b", default="?")
        self.assertEqual(out[:2], ("x", "?"))
        self.assertEqual(out[6:], (False, "b"))
        with self.assertRaises(ValueError):
            json_fields_node.KDX_LLM_JSON_Fields().run(json="not json", fields="a", fail_if_missing=True)

    def test_too_many_fields(self):
        with self.assertRaises(ValueError):
            json_fields_node.KDX_LLM_JSON_Fields().run(json="{}", fields="a,b,c,d,e,f,g")

# ── Answer preview inside the Chat node ────────────────────────────────


class _StreamingLLM(FakeLLM):
    def chat(self, payload, on_progress=None):
        if on_progress:
            on_progress("par", "")
            on_progress("partial answer", "thinking...")
        return {
            "model": "m",
            "choices": [{"message": {"role": "assistant", "content": "partial answer"}, "finish_reason": "stop"}],
        }


class _FakeServer:
    def __init__(self):
        self.events = []

    def send_sync(self, event, data):
        self.events.append((event, data))


class TestChatPreview(unittest.TestCase):
    def setUp(self):
        self._orig = chat.LLMClient
        chat.LLMClient = _StreamingLLM
        self._server_mod = sys.modules.get("server")
        server = types.ModuleType("server")
        self.fake = _FakeServer()
        server.PromptServer = type("PromptServer", (), {"instance": self.fake})
        sys.modules["server"] = server
        self._interval = chat._PREVIEW_INTERVAL
        chat._PREVIEW_INTERVAL = 0.0

    def tearDown(self):
        chat.LLMClient = self._orig
        chat._PREVIEW_INTERVAL = self._interval
        if self._server_mod is None:
            sys.modules.pop("server", None)
        else:
            sys.modules["server"] = self._server_mod

    def test_execute_node_returns_ui_and_result(self):
        out = chat.KDX_LLM_Chat().execute_node(
            unique_id="7", prompt="hi", client={"url": "http://x", "model": "m"}, stream=True,
        )
        self.assertEqual(out["ui"]["kdx_response"], ["partial answer"])
        self.assertEqual(out["result"][0], "partial answer")
        self.assertEqual(len(out["result"]), len(chat.KDX_LLM_Chat.RETURN_TYPES))
        self.assertEqual([e[0] for e in self.fake.events], ["kdx_llm.stream", "kdx_llm.stream"])
        self.assertEqual(self.fake.events[-1][1], {"node": "7", "text": "partial answer", "thinking": "thinking..."})

    def test_no_preview_when_not_streaming(self):
        chat.KDX_LLM_Chat().execute_node(unique_id="7", prompt="hi", client={"url": "http://x", "model": "m"}, stream=False)
        self.assertEqual(self.fake.events, [])

    def test_function_is_execute_node(self):
        self.assertEqual(chat.KDX_LLM_Chat.FUNCTION, "execute_node")
        self.assertIs(chat.KDX_LLM_Chat.OUTPUT_NODE, False)
        self.assertEqual(chat.KDX_LLM_Chat.INPUT_TYPES()["hidden"], {"unique_id": "UNIQUE_ID"})


class TestSSEProgressAccessors(unittest.TestCase):
    def test_content_and_reasoning_grow(self):
        acc = sse.SSEAccumulator()
        acc.feed_bytes(b'data: {"choices":[{"delta":{"reasoning_content":"r"}}]}\n\n')
        acc.feed_bytes(b'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n')
        self.assertEqual((acc.content, acc.reasoning), ("Hel", "r"))

# ── Example workflows stay in sync with node definitions ──────────────


class TestExampleWorkflows(unittest.TestCase):
    WIDGET_TYPES = {"STRING", "INT", "FLOAT", "BOOLEAN"}

    def _classes(self):
        classes = {}
        for name in ("client", "chat", "prompt_template_node", "json_fields_node", "json_extract_node"):
            mod = sys.modules.get(PKG + "." + name) or _load(name, name + ".py")
            classes.update(mod.NODE_CLASS_MAPPINGS)
        return classes

    def test_widget_values_match_input_types(self):
        folder = os.path.join(BASE, "example_workflows")
        files = [f for f in os.listdir(folder) if f.endswith(".json")]
        self.assertGreaterEqual(len(files), 4)
        classes = self._classes()
        for fname in files:
            with open(os.path.join(folder, fname), encoding="utf-8") as f:
                wf = json.load(f)
            nodes = {n["id"]: n for n in wf["nodes"]}
            for node in wf["nodes"]:
                cls = classes.get(node["type"])
                if cls is None:
                    continue
                raw = cls.INPUT_TYPES()
                specs = list(raw.get("required", {}).items()) + list(raw.get("optional", {}).items())
                widgets = [(n, s) for n, s in specs if isinstance(s[0], list) or s[0] in self.WIDGET_TYPES]
                self.assertEqual(len(node["widgets_values"]), len(widgets), f"{fname}: {node['type']}")
                for (name, spec), value in zip(widgets, node["widgets_values"]):
                    if isinstance(spec[0], list):
                        self.assertIn(value, spec[0], f"{fname}: {node['type']}.{name}")
            self.assertTrue(
                any(n["type"] in ("PreviewAny", "SaveImage", "PreviewImage") for n in wf["nodes"]),
                f"{fname}: needs an output node (Chat is not one)",
            )
            for link_id, src, src_slot, dst, dst_slot, _typ in wf["links"]:
                self.assertEqual(nodes[dst]["inputs"][dst_slot]["link"], link_id, fname)
                self.assertIn(link_id, nodes[src]["outputs"][src_slot]["links"], fname)

# ── Session chaining without any session setup (found in live test) ───


class TestStatelessSessionChaining(unittest.TestCase):
    def setUp(self):
        self._orig = chat.LLMClient
        chat.LLMClient = _RecordingLLM

    def tearDown(self):
        chat.LLMClient = self._orig

    def test_chat1_session_output_carries_the_exchange_into_chat2(self):
        client = {"url": "http://x", "model": "m"}
        first = chat.KDX_LLM_Chat().run(prompt="Remember PELICAN.", client=client, stream=False)
        session_out = first[9]
        self.assertEqual([m["role"] for m in session_out.messages], ["user", "assistant"])
        self.assertEqual(session_out.messages[0]["content"], "Remember PELICAN.")

        chat.KDX_LLM_Chat().run(
            prompt="What was the word?", client=client, stream=False, session=session_out, reset_session=False,
        )
        sent = [m["content"] for m in _RecordingLLM.last_payload["messages"]]
        self.assertEqual(sent[0], "Remember PELICAN.")
        self.assertEqual(sent[-1], "What was the word?")

# ── Media robustness, JSON detection, client validation ───────────────


class TestMediaImages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import numpy  # noqa: F401
            import PIL  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("numpy/Pillow not installed")
        cls.media = _load("media_real", "media.py")

    def _decode(self, b64):
        import base64
        import io

        from PIL import Image
        return Image.open(io.BytesIO(base64.b64decode(b64)))

    def test_grey_rgba_and_uint8_images_encode(self):
        import numpy as np
        shapes = [
            np.full((32, 48), 0.5, dtype=np.float32),            # (H, W)
            np.full((32, 48, 1), 0.5, dtype=np.float32),         # grey channel
            np.full((1, 32, 48, 4), 0.5, dtype=np.float32),      # RGBA batch of 1
            np.full((32, 48, 3), 128, dtype=np.uint8),           # uint8
            np.full((32, 48, 3), 0.5, dtype=np.float16),         # half precision
        ]
        for arr in shapes:
            img = self._decode(self.media.tensor_to_base64(arr))
            self.assertEqual((img.mode, img.size), ("RGB", (48, 32)), arr.shape)

    def test_batch_sends_every_image(self):
        import numpy as np
        batch = np.zeros((3, 16, 16, 3), dtype=np.float32)
        parts = self.media.build_user_content(prompt="p", image=batch, media_mode="image")
        self.assertEqual([p["type"] for p in parts], ["text", "image_url", "image_url", "image_url"])
        big = np.zeros((40, 8, 8, 3), dtype=np.float32)
        parts = self.media.build_user_content(prompt="p", image=big, media_mode="image")
        self.assertEqual(len(parts) - 1, self.media.MAX_BATCH_IMAGES)


class TestJsonDetection(unittest.TestCase):
    def test_python_fence_is_not_json_but_json_fence_is(self):
        pp = sys.modules[PKG + ".postprocess"]
        def resp(text):
            return {"choices": [{"message": {"content": text}}]}
        self.assertIsNone(pp.parse_response(resp("```python\nx = {'a': 1}\n```"))["json"])
        self.assertEqual(pp.parse_response(resp('```json\n{"a": 1}\n```'))["json"], {"a": 1})
        self.assertEqual(pp.parse_response(resp('```\n{"a": 1}\n```'))["json"], {"a": 1})
        self.assertEqual(pp.parse_response(resp('{"a": 1}'))["json"], {"a": 1})
        # json_mode=on still digs JSON out of anything
        self.assertEqual(pp.parse_response(resp("Sure: {\"a\": 1}"), json_mode=True)["json"], {"a": 1})


class TestClientValidation(unittest.TestCase):
    def test_v1_validate_inputs_hook(self):
        client_mod = sys.modules.get(PKG + ".client") or _load("client", "client.py")
        cls = client_mod.KDX_LLM_Client
        self.assertIs(cls.VALIDATE_INPUTS(base_url="http://10.0.0.1:8080"), True)
        self.assertIsInstance(cls.VALIDATE_INPUTS(base_url="10.0.0.1:8080"), str)

if __name__ == "__main__":
    unittest.main()


class TestWebCache(unittest.TestCase):
    """ComfyUI sends no Cache-Control for .mjs: relative module imports carry ?v=<VERSION>."""

    def test_relative_module_imports_are_versioned(self):
        import re
        with open(os.path.join(BASE, "VERSION"), encoding="utf-8") as f:
            version = f.read().strip()
        found = 0
        for dirpath, _dirs, files in os.walk(os.path.join(BASE, "web")):
            for name in files:
                if not name.endswith((".js", ".mjs")):
                    continue
                with open(os.path.join(dirpath, name), encoding="utf-8") as f:
                    for spec in re.findall(r'from\s+"(\./[^"]+\.mjs[^"]*)"', f.read()):
                        found += 1
                        self.assertTrue(spec.endswith(f"?v={version}"), f"{name}: {spec}")
        self.assertGreaterEqual(found, 1)
