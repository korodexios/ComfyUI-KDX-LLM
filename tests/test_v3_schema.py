"""V3 schema live-check — run INSIDE a ComfyUI runtime.

Verifies the V3 adapter against the real comfy_api: define_schema(),
not_idempotent, output types (io.Custom KDX_LLM_RESPONSE), advanced,
fingerprint_inputs, and the V1/V3 shared-hash contract.

Run (from the ComfyUI root):
    cd /path/to/ComfyUI
    .venv/bin/python custom_nodes/ComfyUI-KDX-LLM/tests/test_v3_schema.py
"""
import asyncio
import importlib.util
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_DIR = os.path.dirname(HERE)

# comfy_api lives in the ComfyUI root (two levels up from the pack dir).
# Add it to sys.path so `from comfy_api.latest import ...` resolves regardless
# of how this script is invoked.
_COMFYUI_ROOT = os.path.dirname(os.path.dirname(PKG_DIR))
if _COMFYUI_ROOT not in sys.path:
    sys.path.insert(0, _COMFYUI_ROOT)

# Load the pack as a proper package so v3_adapter's relative imports resolve.
pkgname = "comfyui_kdx_llm"
pkg = types.ModuleType(pkgname)
pkg.__path__ = [PKG_DIR]
sys.modules[pkgname] = pkg

kcx = types.ModuleType(pkgname + ".kdx_core")
kcx.__path__ = [os.path.join(PKG_DIR, "kdx_core")]
sys.modules[pkgname + ".kdx_core"] = kcx


def _sub(modname, fname):
    spec = importlib.util.spec_from_file_location(
        f"{pkgname}.{modname}", os.path.join(PKG_DIR, fname))
    m = importlib.util.module_from_spec(spec)
    sys.modules[f"{pkgname}.{modname}"] = m
    spec.loader.exec_module(m)
    return m


# kdx_core.fingerprint (pure)
_sub("kdx_core.fingerprint", "kdx_core/fingerprint.py")

# Stubs for chat.py's non-core deps (avoid ComfyUI runtime / network)
media = types.ModuleType(f"{pkgname}.media")
media.build_user_content = lambda **kw: kw.get("prompt", "")
sys.modules[f"{pkgname}.media"] = media
http = types.ModuleType(f"{pkgname}._http")
http.LLMClient = type("LLMClient", (), {"__init__": lambda self, *a, **k: None})
sys.modules[f"{pkgname}._http"] = http
_sub("postprocess", "postprocess.py")
sess = types.ModuleType(f"{pkgname}.session")
sess.reset_session = lambda *a, **k: None
sess.get_session = lambda *a, **k: []
sess.add_exchange = lambda *a, **k: None
sess.new_session_id = lambda: "test-session"
sys.modules[f"{pkgname}.session"] = sess
for nm in ("prompt_store", "user_prompt_store", "sampling_store"):
    st = types.ModuleType(f"{pkgname}.{nm}")
    st.mtime = lambda: 0.0
    if nm == "sampling_store":
        st.lookup = lambda m: (None, {})
    sys.modules[f"{pkgname}.{nm}"] = st
_sub("chat", "chat.py")
va = _sub("v3_adapter", "v3_adapter.py")


def main():
    assert va._HAS_V3, "comfy_api.latest not importable — not in a ComfyUI runtime"
    ext = va.comfy_entrypoint()
    assert ext is not None, "comfy_entrypoint() returned None"
    nodes = asyncio.run(ext.get_node_list())
    assert len(nodes) >= 2, f"expected at least 2 nodes, got {len(nodes)}"
    classes = {}
    for node_cls in nodes:
        node_schema = node_cls.define_schema()
        classes[node_schema.node_id] = (node_cls, node_schema)
    assert "KDX_LLM_Chat" in classes, "V3 Chat node missing"
    assert "KDX_LLM_Session" in classes, "V3 Session node missing"
    cls, schema = classes["KDX_LLM_Chat"]
    session_cls, session_schema = classes["KDX_LLM_Session"]

    print("node_id          =", schema.node_id)
    print("display_name     =", schema.display_name)
    print("not_idempotent   =", schema.not_idempotent)
    print("input count      =", len(schema.inputs))
    print("output count     =", len(schema.outputs))

    # Decision B: Chat is not_idempotent
    assert schema.not_idempotent is True, "Chat must be not_idempotent"

    # P2.2 / P1.1 / tool_calls: Chat has 11 outputs; response_obj is 9th, session is 10th, tool_calls is 11th.
    assert len(schema.outputs) == 11, f"expected 11 outputs, got {len(schema.outputs)}"
    response_obj_type = getattr(schema.outputs[8], "io_type", None)
    session_type = getattr(schema.outputs[9], "io_type", None)
    tool_calls_type = getattr(schema.outputs[10], "io_type", None)
    print("response_obj type =", response_obj_type)
    print("session type      =", session_type)
    print("tool_calls type   =", tool_calls_type)
    assert response_obj_type == "KDX_LLM_RESPONSE", f"9th output type = {response_obj_type}"
    assert session_type == "KDX_LLM_SESSION", f"10th output type = {session_type}"
    assert tool_calls_type == "STRING", f"11th output type = {tool_calls_type}"
    assert len(session_schema.outputs) == 3, f"Session node expected 3 outputs, got {len(session_schema.outputs)}"

    # Decision C: advanced block (json_mode stays visible)
    advanced = sorted(i.id for i in schema.inputs if getattr(i, "advanced", False))
    print("advanced         =", advanced)
    expected_adv = ["extra_request_json", "load_before", "load_timeout", "max_prompt_tokens",
                    "sampling_json_non_thinking", "sampling_json_thinking", "token_counter",
                    "unload_after"]
    assert advanced == expected_adv, f"advanced mismatch: {advanced}"
    assert "json_mode" not in advanced, "json_mode must stay visible"

    # Decision D: link-type inputs (Custom + Image) are link-only.
    # In the V3 API their Input has no force_input param (link-only by nature).
    link_inputs = sorted(
        i.id for i in schema.inputs
        if getattr(getattr(i, "Parent", None), "io_type", None) in
        ("KDX_LLM_CLIENT", "KDX_LLM_OPTIONS", "KDX_LLM_MEDIA", "KDX_LLM_TOOLS", "KDX_LLM_SESSION", "IMAGE")
    )
    print("link-type inputs =", link_inputs)
    expected_links = ["client", "image", "media_settings", "non_thinking_sampling",
                      "session", "thinking_sampling", "tools"]
    assert link_inputs == expected_links, f"link inputs mismatch: {link_inputs}"

    # Decision A: fingerprint_inputs returns a stable, order-independent sha256
    fp = cls.fingerprint_inputs(prompt="x", client={"model": "m"}, profiles_mtime=1.0,
                                prompts_mtime=1.0, user_prompts_mtime=1.0)
    fp2 = cls.fingerprint_inputs(client={"model": "m"}, prompt="x", profiles_mtime=1.0,
                                 prompts_mtime=1.0, user_prompts_mtime=1.0)
    print("fingerprint      =", fp[:16] + "...")
    assert len(fp) == 64 and fp == fp2, "fingerprint must be stable 64-char sha256"

    # Decision A: V1 IS_CHANGED and V3 fingerprint_inputs share the SAME hash.
    # (both resolve mtime to the store value, stubbed 0.0 here)
    _v1_chat = sys.modules[f"{pkgname}.chat"].KDX_LLM_Chat
    v1 = _v1_chat.IS_CHANGED(prompt="x", client={"model": "m"})
    v3 = cls.fingerprint_inputs(prompt="x", client={"model": "m"}, profiles_mtime=0.0,
                                prompts_mtime=0.0, user_prompts_mtime=0.0)
    print("V1 IS_CHANGED    =", v1[:16] + "...")
    print("V3 fingerprint   =", v3[:16] + "...")
    assert v1 == v3, "V1 IS_CHANGED and V3 fingerprint_inputs must match"

    print("\nALL V3 SCHEMA CHECKS PASSED")


if __name__ == "__main__":
    main()
