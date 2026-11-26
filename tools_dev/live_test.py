"""Live end-to-end test of the KDX LLM nodes against a real OpenAI-compatible server.

Runs the node classes directly (no ComfyUI needed) and checks real model answers.

    python tools_dev/live_test.py --url http://127.0.0.1:8080 --model <model-id>
    python tools_dev/live_test.py ... --only json,session      # run a subset

Needs requests, numpy and Pillow. Saved profiles/prompts/sessions go to a
temporary folder, never to your ComfyUI user directory. Exit code 1 when a
check fails.
"""

import argparse
import importlib
import importlib.util
import json
import os
import sys
import tempfile
import time
import traceback
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = "kdx_llm_live"


def load_pack():
    """Import the pack's modules without ComfyUI (no __init__/server routes)."""
    pkg = types.ModuleType(PKG)
    pkg.__path__ = [ROOT]
    sys.modules[PKG] = pkg
    core = types.ModuleType(PKG + ".kdx_core")
    core.__path__ = [os.path.join(ROOT, "kdx_core")]
    sys.modules[PKG + ".kdx_core"] = core
    mods = {}
    for name in (
        "client", "chat", "session_node", "options", "quick_sampling_node", "system_prompt_node",
        "prompt_template_node", "json_fields_node", "json_extract_node", "response_formatter",
        "stats", "tools", "diagnostics", "model_profile_node", "media_settings",
    ):
        mods[name] = importlib.import_module(f"{PKG}.{name}")
    return mods


class Runner:
    def __init__(self):
        self.results = []

    def check(self, cond, what, detail=""):
        self.results.append((bool(cond), what, detail))
        mark = "PASS" if cond else "FAIL"
        print(f"    [{mark}] {what}" + (f" — {detail}" if detail and not cond else ""))
        return cond

    def case(self, name, fn):
        print(f"\n== {name}")
        t0 = time.time()
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - report and continue with the next case
            self.results.append((False, f"{name}: exception", repr(exc)))
            print(f"    [FAIL] exception: {exc!r}")
            traceback.print_exc(limit=3)
        print(f"    ({time.time() - t0:.1f}s)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("KDX_LIVE_URL", "http://127.0.0.1:8080"))
    ap.add_argument("--model", default=os.environ.get("KDX_LIVE_MODEL", ""))
    ap.add_argument("--only", default="", help="comma separated case keys")
    args = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="kdx_live_")
    for env, fname in (
        ("KDX_LLM_PROFILES_FILE", "profiles.json"), ("KDX_LLM_PROMPTS_FILE", "prompts.json"),
        ("KDX_LLM_USER_PROMPTS_FILE", "user_prompts.json"), ("KDX_LLM_SESSIONS_FILE", "sessions.json"),
        ("KDX_LLM_PRESETS_FILE", "presets.json"),
    ):
        os.environ[env] = os.path.join(tmp, fname)

    m = load_pack()
    r = Runner()
    client = m["client"].KDX_LLM_Client().execute(base_url=args.url, model=args.model, context_length="8192", timeout=300)[0]
    Chat = m["chat"].KDX_LLM_Chat

    def ask(prompt, **kw):
        kw.setdefault("thinking", "off")
        kw.setdefault("stream", True)
        kw.setdefault("client", client)
        out = Chat().run(prompt=prompt, **kw)
        return out

    def c_basic():
        for stream in (True, False):
            out = ask("Reply with exactly the word: banana", stream=stream)
            r.check("banana" in out[0].lower(), f"answer (stream={stream})", repr(out[0][:120]))
            r.check(out[1] == "", f"no thinking when thinking=off (stream={stream})", repr(out[1][:120]))
            info = json.loads(out[7])
            r.check(info["thinking"] is False and info["mode"] == "non_thinking", "request_info says non-thinking")
            stats = m["stats"].KDX_LLM_Stats().run(raw=out[3])
            r.check(stats[1] > 0 and stats[2] > 0, "Stats node reads token counts", str(stats[:3]))

    def c_unicode():
        out = ask("Napíš presne túto vetu a nič iné: Žltý kôň úpel ďábelské ódy. 🐱")
        r.check("Žltý kôň" in out[0] and "�" not in out[0], "Slovak diacritics + emoji survive streaming", repr(out[0][:120]))

    def c_json():
        out = ask('Return a JSON object with keys "city" (string) and "population" (number) for Bratislava.', json_mode="on")
        data = json.loads(out[2]) if out[2] else None
        r.check(isinstance(data, dict) and "city" in data, "json output parsed (json_mode=on)", repr(out[0][:200]))
        val = m["json_extract_node"].KDX_LLM_JSON_Extract().run(json=out[2], key="city")
        r.check(val[1] and "bratislava" in val[0].lower(), "JSON Extract city", repr(val))

    def c_fields():
        tmpl = m["prompt_template_node"].KDX_LLM_Prompt_Template().run(
            template="Rewrite this image prompt, detailed and vivid, max 40 words. Subject: {text_1}. Style: {style}",
            text_1="a lighthouse in a storm", variables="style = oil painting")
        r.check(tmpl[1] == "" and "lighthouse" in tmpl[0], "template filled", repr(tmpl))
        system, fields = m["json_fields_node"].KDX_LLM_JSON_Output_Format().run(
            fields="rewritten_prompt: the improved prompt\nnegative_prompt: what to avoid\nmood: one word",
            system_prompt="You are an expert prompt writer.")
        out = ask(tmpl[0], system_prompt=system, json_mode="on")
        res = m["json_fields_node"].KDX_LLM_JSON_Fields().run(json=out[2] or out[0], fields=fields)
        r.check(res[6] is True, "all JSON fields found", f"missing={res[7]!r} answer={out[0][:200]!r}")
        r.check(len(res[0]) > 20 and not res[0].startswith("{"), "field_1 is plain prompt text", repr(res[0][:120]))

    def c_session():
        a = ask("Remember the secret word PELICAN. Reply only with OK.")
        b = ask("What was the secret word? Reply with just the word.", session=a[9], reset_session=False)
        r.check("pelican" in b[0].lower(), "Chat 1 → session → Chat 2 remembers", repr(b[0][:120]))
        c = ask("And what did I ask you to reply with the first time? One word.", session=b[9], reset_session=False)
        r.check("ok" in c[0].lower(), "third turn sees full history", repr(c[0][:120]))
        r.check(c[9].turn_count == 3, "session has 3 turns", str(c[9].turn_count))
        S = m["session_node"].KDX_LLM_Session()
        S.execute(action="save", session=c[9], session_name="live_test")
        loaded = S.execute(action="load", session_name="live_test")[0]
        d = ask("What was the secret word? Just the word.", session=loaded, reset_session=False)
        r.check("pelican" in d[0].lower(), "saved + loaded session still works", repr(d[0][:120]))
        e = ask("What was the secret word? Just the word.", session=c[9], reset_session=True)
        r.check("pelican" not in e[0].lower(), "reset_session=True starts fresh", repr(e[0][:120]))

    def c_legacy_session():
        sid = "live-" + str(int(time.time()))
        ask("My name is Alex. Reply only OK.", session_id=sid, reset_session=True)
        b = ask("What is my name? One word.", session_id=sid, reset_session=False)
        r.check("alex" in b[0].lower(), "legacy session_id remembers", repr(b[0][:120]))

    def c_trim():
        history = m["chat"].KDXLLMSession(session_id="t")
        for i in range(12):
            history = history.add_exchange(f"Filler message number {i}. " + "lorem ipsum " * 60, "Noted.")
        history = history.add_exchange("The code word is ZEBRA.", "OK, ZEBRA.")
        out = ask("What is the code word? One word.", session=history, reset_session=False, max_prompt_tokens=600)
        info = json.loads(out[7])
        r.check(info["prompt_token_estimate"] <= 600, "trimmed under budget", str(info["prompt_token_estimate"]))
        r.check("zebra" in out[0].lower(), "newest history kept after trimming", repr(out[0][:120]))

    def c_vision():
        import numpy as np
        img = np.zeros((1, 256, 256, 3), dtype=np.float32)
        img[..., 0] = 1.0  # pure red
        out = ask("What single colour fills this image? One word.", image=img)
        r.check("red" in out[0].lower(), "vision: sees red image", repr(out[0][:120]))
        info = json.loads(out[7])
        r.check(info["media_mode"] == "image", "media_mode auto → image")
        follow = ask("What colour was the image I showed you? One word.", session=out[9], reset_session=False)
        r.check("red" in follow[0].lower(), "follow-up turn remembers the image (history_media=latest)", repr(follow[0][:120]))

    def c_vision_batch():
        import numpy as np
        batch = np.zeros((2, 128, 128, 3), dtype=np.float32)
        batch[0, ..., 2] = 1.0  # blue
        batch[1, ..., 1] = 1.0  # green
        out = ask("I sent two images. Name the colour of each, in order, as two words separated by a comma.", image=batch)
        ans = out[0].lower()
        r.check("blue" in ans and "green" in ans, "batch of 2 images both sent", repr(out[0][:120]))
        grey = np.full((96, 96), 0.0, dtype=np.float32)  # (H, W) black, no channel axis
        out = ask("What colour is this image? One word.", image=grey)
        r.check("black" in out[0].lower() or "dark" in out[0].lower(), "2-D greyscale image accepted", repr(out[0][:120]))

    def c_tools():
        tools = m["tools"].KDX_LLM_Tool().execute(
            name="get_weather", description="Get the current weather for a city.",
            parameters='{"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}')[0]
        out = ask("What is the weather in Bratislava right now? Use the tool.", tools=tools)
        calls = json.loads(out[10])
        r.check(bool(calls) and calls[0]["function"]["name"] == "get_weather", "tool call returned", out[10][:200])
        if calls:
            argsj = json.loads(calls[0]["function"]["arguments"] or "{}")
            r.check("bratislava" in str(argsj).lower(), "tool arguments parsed", str(argsj))

    def c_sampling():
        simple = m["options"].KDX_LLM_Simple_Sampling().execute(
            max_tokens_enabled=True, max_tokens=8, temperature_enabled=True, temperature=0.2,
            top_p=0.95, top_k=40, min_p=0.0, repeat_penalty=1.0, presence_penalty=0.0, frequency_penalty=0.0,
            seed=0, stop_enabled=False, stop="")[0]
        out = ask("Count from 1 to 100 separated by commas.", non_thinking_sampling=simple)
        stats = m["stats"].KDX_LLM_Stats().run(raw=out[3])
        r.check(stats[3] == "length" and stats[1] <= 10, "max_tokens=8 respected (finish_reason=length)", str(stats[:4]))
        stop = m["options"].KDX_LLM_Simple_Sampling().execute(stop_enabled=True, stop="5")[0]
        out = ask("Count from 1 to 10 separated by commas, nothing else.", non_thinking_sampling=stop)
        r.check("6" not in out[0], "stop sequence respected", repr(out[0][:80]))
        preset = m["quick_sampling_node"].KDX_LLM_Quick_Presets().run(preset="precise")[0]
        out = ask("Reply with exactly the word: apple", non_thinking_sampling=preset)
        info = json.loads(out[7])
        r.check("apple" in out[0].lower() and info["sampling"], "Quick preset applied", str(info["sampling"]))

    def c_profile_and_prompts():
        prof = m["model_profile_node"].KDX_LLM_Model_Profile().run(profile="(none)", client=client)
        r.check(prof[0].get("url") == client["url"], "Model Profile passes client through")
        sp = m["system_prompt_node"].KDX_LLM_System_Prompt()
        sp.run(profile="(none)", action="save", name="pirate", system_prompt="Always answer like a pirate, starting with 'Arr'.")
        text = sp.run(profile="pirate", action="use")[0]
        out = ask("Say hello in one short sentence.", client=prof[0], system_prompt_profile=text)
        r.check("arr" in out[0].lower(), "saved system prompt used", repr(out[0][:120]))
        fmt = m["response_formatter"].KDX_LLM_Response_Formatter()
        code = ask("Write a Python one-liner that prints hi, in a ```python code block.")
        block = fmt.run(response=code[0], action="extract_first_code_block")[0]
        r.check("print" in block and "```" not in block, "Response Formatter extracts code", repr(block[:80]))

    def c_diag():
        summary, js = m["diagnostics"].KDX_LLM_Diagnostics().run(base_url=args.url, client=client)
        data = json.loads(js)
        r.check(data.get("capabilities", {}).get("server", {}).get("model_count", 0) > 0, "Diagnostics lists models", summary[:120])

    def c_thinking_on():
        out = ask("What is 17 * 3? Answer with the number.", thinking="on", model_preset="qwen_thinking")
        r.check("51" in out[0], "thinking=on still answers", repr(out[0][:80]))
        print(f"    (info) reasoning length with thinking=on: {len(out[1])}")

    def c_llm_switch():
        prompt = "a lighthouse in a storm, oil painting "
        t0 = time.time()
        out = ask(prompt, llm_enabled=False, load_before=True, unload_after=True)
        r.check(out[0] == prompt, "llm_enabled=False returns the prompt unchanged", repr(out[0]))
        r.check(out[4] == "" and out[7] == "", "llm_enabled=False made no request (no model_used / request_info)")
        r.check(time.time() - t0 < 0.5, "llm_enabled=False is instant (no load/unload)")
        out = ask("Reply with exactly the word: banana", llm_enabled=True)
        r.check("banana" in out[0].lower(), "llm_enabled=True calls the LLM", repr(out[0][:80]))

    cases = {
        "basic": ("basic chat, stream + non-stream", c_basic),
        "llm_switch": ("llm_enabled on/off", c_llm_switch),
        "unicode": ("unicode streaming", c_unicode),
        "json": ("JSON mode + JSON Extract", c_json),
        "fields": ("Prompt Template + JSON Output Format + JSON Fields", c_fields),
        "session": ("session chaining + Session save/load + reset", c_session),
        "legacy": ("legacy session_id", c_legacy_session),
        "trim": ("max_prompt_tokens trimming", c_trim),
        "vision": ("vision + image in history", c_vision),
        "batch": ("image batch + greyscale image", c_vision_batch),
        "tools": ("tool calling", c_tools),
        "sampling": ("sampling: max_tokens, stop, quick preset", c_sampling),
        "prompts": ("Model Profile, System Prompt store, Response Formatter", c_profile_and_prompts),
        "diag": ("Diagnostics", c_diag),
        "thinking": ("thinking=on sanity", c_thinking_on),
    }
    selected = [k.strip() for k in args.only.split(",") if k.strip()] or list(cases)
    print(f"KDX LLM live test → {args.url}  model={args.model!r}  stores in {tmp}")
    for key in selected:
        name, fn = cases[key]
        r.case(f"{key}: {name}", fn)

    failed = [x for x in r.results if not x[0]]
    print(f"\n{len(r.results) - len(failed)}/{len(r.results)} checks passed")
    for _, what, detail in failed:
        print(f"  FAIL {what}: {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
