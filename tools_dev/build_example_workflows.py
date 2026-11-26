"""Generate example_workflows/*.json from the current node definitions.

Run from the pack root:  python tools_dev/build_example_workflows.py

Widget values are written in the exact order of each node's INPUT_TYPES, so
the files stay loadable after inputs change — re-run this script then.
ComfyUI lists the files under Templates → custom nodes → ComfyUI-KDX-LLM.
"""

import importlib.util
import json
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = "kdx_examples_build"
WIDGET_TYPES = {"STRING", "INT", "FLOAT", "BOOLEAN"}


def _load_pack():
    pkg = types.ModuleType(PKG)
    pkg.__path__ = [ROOT]
    sys.modules[PKG] = pkg
    core = types.ModuleType(PKG + ".kdx_core")
    core.__path__ = [os.path.join(ROOT, "kdx_core")]
    sys.modules[PKG + ".kdx_core"] = core
    http = types.ModuleType(PKG + "._http")
    http.LLMClient = object
    http.normalize_base_url = lambda url: (url or "").strip().rstrip("/")
    sys.modules[PKG + "._http"] = http
    media = types.ModuleType(PKG + ".media")
    media.build_user_content = lambda **kw: kw.get("prompt", "")
    sys.modules[PKG + ".media"] = media

    def load(name):
        full = f"{PKG}.{name}"
        spec = importlib.util.spec_from_file_location(full, os.path.join(ROOT, name + ".py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[full] = mod
        spec.loader.exec_module(mod)
        return mod

    classes = {}
    for name in ("client", "chat", "prompt_template_node", "json_fields_node", "json_extract_node"):
        classes.update(load(name).NODE_CLASS_MAPPINGS)
    return classes


def is_widget(spec):
    typ = spec[0] if isinstance(spec, tuple) else spec
    return isinstance(typ, list) or typ in WIDGET_TYPES


def input_specs(cls):
    raw = cls.INPUT_TYPES()
    specs = list((raw.get("required") or {}).items()) + list((raw.get("optional") or {}).items())
    return specs


def widget_names(cls):
    return [name for name, spec in input_specs(cls) if is_widget(spec)]


def widget_default(spec):
    typ = spec[0]
    opts = spec[1] if len(spec) > 1 else {}
    if "default" in opts:
        return opts["default"]
    if isinstance(typ, list):
        return typ[0]
    return {"STRING": "", "INT": 0, "FLOAT": 0.0, "BOOLEAN": False}[typ]


class Workflow:
    def __init__(self, classes):
        self.classes = classes
        self.nodes = []
        self.links = []

    def node(self, node_type, pos, size=(400, 300), values=None, title=None, core_inputs=None, core_outputs=None, core_widgets=None):
        node_id = len(self.nodes) + 1
        if node_type in self.classes:
            cls = self.classes[node_type]
            specs = input_specs(cls)
            values = values or {}
            unknown = set(values) - {n for n, s in specs}
            assert not unknown, (node_type, unknown)
            widgets_values = [values.get(n, widget_default(s)) for n, s in specs if is_widget(s)]
            inputs = [{"name": n, "type": s[0], "link": None} for n, s in specs if not is_widget(s)]
            outputs = [
                {"name": name, "type": typ, "links": [], "slot_index": i}
                for i, (name, typ) in enumerate(zip(cls.RETURN_NAMES, cls.RETURN_TYPES))
            ]
            widget_specs = {n: s for n, s in specs if is_widget(s)}
        else:  # core ComfyUI node described by the caller
            widgets_values = list(core_widgets or [])
            inputs = [{"name": n, "type": t, "link": None} for n, t in (core_inputs or [])]
            outputs = [{"name": n, "type": t, "links": [], "slot_index": i} for i, (n, t) in enumerate(core_outputs or [])]
            widget_specs = {}
        node = {
            "id": node_id,
            "type": node_type,
            "pos": list(pos),
            "size": list(size),
            "flags": {},
            "order": node_id - 1,
            "mode": 0,
            "inputs": inputs,
            "outputs": outputs,
            "properties": {"Node name for S&R": node_type},
            "widgets_values": widgets_values,
            "_widget_specs": widget_specs,
        }
        if title:
            node["title"] = title
        self.nodes.append(node)
        return node_id

    def link(self, src_id, src_output, dst_id, dst_input):
        src = self.nodes[src_id - 1]
        dst = self.nodes[dst_id - 1]
        src_slot = next(i for i, o in enumerate(src["outputs"]) if o["name"] == src_output)
        typ = src["outputs"][src_slot]["type"]
        slot = next((i for i, inp in enumerate(dst["inputs"]) if inp["name"] == dst_input), None)
        if slot is None:  # widget converted to an input
            spec = dst["_widget_specs"][dst_input]
            dst["inputs"].append({"name": dst_input, "type": spec[0], "widget": {"name": dst_input}, "link": None})
            slot = len(dst["inputs"]) - 1
        link_id = len(self.links) + 1
        dst["inputs"][slot]["link"] = link_id
        src["outputs"][src_slot]["links"].append(link_id)
        self.links.append([link_id, src_id, src_slot, dst_id, slot, typ])

    def to_json(self):
        nodes = []
        for node in self.nodes:
            node = {k: v for k, v in node.items() if k != "_widget_specs"}
            for out in node["outputs"]:
                if not out["links"]:
                    out["links"] = None
            nodes.append(node)
        return {
            "last_node_id": len(nodes),
            "last_link_id": len(self.links),
            "nodes": nodes,
            "links": self.links,
            "groups": [],
            "config": {},
            "extra": {"ds": {"scale": 0.8, "offset": [0, 0]}},
            "version": 0.4,
        }


PREVIEW = {"core_inputs": [("source", "*")], "core_outputs": [], "core_widgets": []}


def simple_chat(c):
    wf = Workflow(c)
    client = wf.node("KDX_LLM_Client", (40, 60), (360, 400))
    chat = wf.node("KDX_LLM_Chat", (440, 60), (430, 820), {"thinking": "off",
        "prompt": "Write a short, vivid image prompt about a lighthouse in a storm.",
        "system_prompt": "You are a helpful assistant. Answer briefly.",
    })
    show = wf.node("PreviewAny", (920, 60), (420, 300), title="answer", **PREVIEW)
    wf.link(client, "client", chat, "client")
    wf.link(chat, "response", show, "source")
    return wf


def prompt_rewrite_json(c):
    wf = Workflow(c)
    client = wf.node("KDX_LLM_Client", (40, 60), (360, 400))
    template = wf.node("KDX_LLM_Prompt_Template", (40, 500), (360, 400), {
        "template": "Rewrite this image prompt so it is detailed and vivid. Keep the subject: {text_1}",
        "text_1": "a cat sitting on a roof at night",
    })
    fmt = wf.node("KDX_LLM_JSON_Output_Format", (40, 940), (360, 330), {
        "fields": "rewritten_prompt: the improved, detailed image prompt\nnegative_prompt: things the image should avoid",
        "system_prompt": "You are an expert prompt writer for image generation models.",
    })
    chat = wf.node("KDX_LLM_Chat", (440, 60), (430, 820), {"thinking": "off", "prompt": "", "json_mode": "on"})
    fields = wf.node("KDX_LLM_JSON_Fields", (920, 60), (340, 320))
    show_prompt = wf.node("PreviewAny", (1310, 60), (380, 220), title="rewritten_prompt", **PREVIEW)
    show_negative = wf.node("PreviewAny", (1310, 320), (380, 220), title="negative_prompt", **PREVIEW)
    wf.link(client, "client", chat, "client")
    wf.link(template, "text", chat, "prompt")
    wf.link(fmt, "system_prompt", chat, "system_prompt")
    wf.link(chat, "json", fields, "json")
    wf.link(fmt, "fields", fields, "fields")
    wf.link(fields, "field_1", show_prompt, "source")
    wf.link(fields, "field_2", show_negative, "source")
    return wf


def conversation(c):
    wf = Workflow(c)
    client = wf.node("KDX_LLM_Client", (40, 60), (360, 400))
    first = wf.node("KDX_LLM_Chat", (440, 60), (430, 820), {"thinking": "off",
        "prompt": "Give me three short ideas for a fantasy book cover.",
    }, title="Chat 1 — ideas")
    second = wf.node("KDX_LLM_Chat", (920, 60), (430, 820), {"thinking": "off",
        "prompt": "Expand idea number 2 into a detailed image prompt.",
        "reset_session": False,
    }, title="Chat 2 — continues the conversation")
    wf.link(client, "client", first, "client")
    wf.link(client, "client", second, "client")
    show = wf.node("PreviewAny", (1400, 60), (420, 300), title="expanded prompt", **PREVIEW)
    wf.link(first, "session", second, "session")
    wf.link(second, "response", show, "source")
    return wf


def describe_image(c):
    wf = Workflow(c)
    client = wf.node("KDX_LLM_Client", (40, 60), (360, 400))
    image = wf.node(
        "LoadImage", (40, 500), (360, 420),
        core_inputs=[], core_outputs=[("IMAGE", "IMAGE"), ("MASK", "MASK")], core_widgets=["example.png", "image"],
    )
    chat = wf.node("KDX_LLM_Chat", (440, 60), (430, 820), {"thinking": "off",
        "prompt": "Describe this image in one detailed paragraph, suitable as an image-generation prompt.",
    })
    wf.link(client, "client", chat, "client")
    show = wf.node("PreviewAny", (920, 60), (420, 300), title="description", **PREVIEW)
    wf.link(image, "IMAGE", chat, "image")
    wf.link(chat, "response", show, "source")
    return wf


EXAMPLES = {
    "KDX LLM - 1 simple chat": simple_chat,
    "KDX LLM - 2 rewrite prompt as JSON fields": prompt_rewrite_json,
    "KDX LLM - 3 conversation across two Chat nodes": conversation,
    "KDX LLM - 4 describe an image (vision model)": describe_image,
}


def main():
    classes = _load_pack()
    out_dir = os.path.join(ROOT, "example_workflows")
    os.makedirs(out_dir, exist_ok=True)
    for name, build in EXAMPLES.items():
        path = os.path.join(out_dir, name + ".json")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(build(classes).to_json(), f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("wrote", os.path.relpath(path, ROOT))


if __name__ == "__main__":
    main()
