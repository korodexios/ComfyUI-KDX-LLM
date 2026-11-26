"""
KDX LLM CLIENT - Pipeline Validation Script
Validates the data contract integrity of model_profile_node.py ensuring parameters
(GUI nodes & Advanced JSON configs) aren't dropped when no profile exists.
"""
import json
import sys
import types
import importlib.util

import os
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_with_relative_imports():
    """Load model_profile_node.py with its relative import resolved."""
    pkg = types.ModuleType("kdx_llm_pkg")
    pkg.__path__ = [BASE]
    sys.modules["kdx_llm_pkg"] = pkg

    def _load(name, filename):
        spec = importlib.util.spec_from_file_location(
            f"kdx_llm_pkg.{name}", os.path.join(BASE, filename)
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"kdx_llm_pkg.{name}"] = mod
        spec.loader.exec_module(mod)
        return mod

    sampling_store = _load("sampling_store", "sampling_store.py")
    m = _load("model_profile_node", "model_profile_node.py")
    m.__dict__["sampling_store"] = sampling_store
    return m


def run_diagnostics():
    print("KDX LLM Pipeline Validation")

    m = _load_with_relative_imports()
    KDX_LLM_Model_Profile = m.KDX_LLM_Model_Profile
    sampling_store = m.__dict__["sampling_store"]

    # Ensure clean state
    sampling_store.delete("deepseek-coder-v2-unknown")

    node = KDX_LLM_Model_Profile()

    # Scenario: NO persistent profile, GUI sampling nodes + advanced JSON connected
    client_input = {
        "url": "http://127.0.0.1:8080",
        "model": "deepseek-coder-v2-unknown",
    }
    thinking_opts = {"options": {"temperature": 1.2, "top_p": 0.95, "min_p": 0.05}}
    non_thinking_opts = {"options": {"temperature": 0.3, "top_k": 40}}

    result = node.run(
        profile="(none)",
        client=client_input,
        thinking_options=thinking_opts,
        non_thinking_options=non_thinking_opts,
        advanced=True,
        thinking_request_json='{"extra_flag_think": true}',
        non_thinking_request_json='{"extra_flag_nonthink": false}',
    )

    client_out = result[0]
    profile = client_out.get("profile", {})

    errors = []

    # Check 1: Structure Integrity
    if "thinking" not in profile or "non_thinking" not in profile:
        errors.append("FAIL: Base modes (thinking/non_thinking) missing from profile dictionary.")
    if "sampling" not in profile.get("thinking", {}) or "request" not in profile.get("thinking", {}):
        errors.append("FAIL: Unified dictionary structure (sampling/request) broken.")

    # Check 2: GUI Parameter Integrity
    t_samp = profile.get("thinking", {}).get("sampling", {})
    nt_samp = profile.get("non_thinking", {}).get("sampling", {})

    if t_samp.get("temperature") != 1.2 or t_samp.get("min_p") != 0.05:
        errors.append(f"FAIL: Thinking sampling parameters dropped! Got: {t_samp}")
    if nt_samp.get("temperature") != 0.3 or nt_samp.get("top_k") != 40:
        errors.append(f"FAIL: Non-thinking sampling parameters dropped! Got: {nt_samp}")

    # Check 3: JSON Integrity (Advanced Mode)
    if profile.get("thinking", {}).get("request", {}).get("extra_flag_think") is not True:
        errors.append("FAIL: Advanced JSON for thinking request dropped!")
    if profile.get("non_thinking", {}).get("request", {}).get("extra_flag_nonthink") is not False:
        errors.append("FAIL: Advanced JSON for non-thinking request dropped!")

    # Check 4: profile_json output matches client_out['profile']
    pj = json.loads(result[2])
    if pj["profile"] != profile:
        errors.append("FAIL: profile_json output does not match client_out['profile']")
    if len(result) != 3:
        errors.append(f"FAIL: Expected 3 outputs, got {len(result)}")

    # ── Regression: profile base + node override (existing saved profile) ──
    sampling_store.save_profile("regress-model", {
        "thinking": {"sampling": {"temperature": 0.5, "top_k": 20}, "request": {"reasoning": "low"}},
        "non_thinking": {"sampling": {"temperature": 0.3}, "request": {}},
    })
    node2 = KDX_LLM_Model_Profile()
    r2 = node2.run(
        profile="(none)",
        client={"url": "http://127.0.0.1:8080", "model": "regress-model"},
        thinking_options={"options": {"temperature": 1.0, "top_p": 0.95}},
        non_thinking_options=None,
    )
    p2 = r2[0]["profile"]
    if p2["thinking"]["sampling"] != {"temperature": 1.0, "top_k": 20, "top_p": 0.95}:
        errors.append(f"FAIL: Regression — node override merge broken. Got: {p2['thinking']['sampling']}")
    if p2["thinking"]["request"].get("reasoning") != "low":
        errors.append(f"FAIL: Regression — profile reasoning lost. Got: {p2['thinking']['request']}")
    if p2["non_thinking"]["sampling"] != {"temperature": 0.3}:
        errors.append(f"FAIL: Regression — non_thinking profile base lost. Got: {p2['non_thinking']['sampling']}")
    sampling_store.delete("regress-model")

    # ── Invalid JSON must raise ──
    try:
        node.run(profile="(none)", client=client_input, advanced=True,
                 thinking_request_json="{not json")
        errors.append("FAIL: Invalid JSON did not raise ValueError")
    except ValueError:
        pass

    if errors:
        print("\n".join("  " + e for e in errors))
        print("\nVALIDATION FAILED")
        sys.exit(1)

    print("VALIDATION PASSED: All Data Contracts Intact.")
    print("Dictionary Output Structure:")
    print(json.dumps(profile, indent=2))
    sys.exit(0)


if __name__ == '__main__':
    run_diagnostics()
