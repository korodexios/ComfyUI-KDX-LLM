"""KDX Core — merge a task prompt (fixed instructions) with the user prompt.

Some prompt-enhancer models ship a long task prompt that wraps the user's
text, e.g. MiniMax-H3-Image-PE: ``t2i/task_prompt.txt`` ends with
``input_text: {}`` and is filled with Python ``str.format``. Keeping the task
prompt on its own Chat input lets the LLM switch return the bare user prompt.

Placeholders in the task prompt:
- ``{}`` or ``{prompt}``  -> the user prompt as is
- ``{prompt_json}``       -> the user prompt as a JSON string (``"..."``)

When the task prompt has a placeholder it is read like ``str.format``:
``{{`` and ``}}`` become ``{`` and ``}``; other ``{names}`` stay untouched.
Without a placeholder the text is left exactly as written and the user
prompt is appended after a blank line.
"""

import json
import re

_FORMAT_TOKEN = re.compile(r"\{\{|\}\}|\{(prompt|prompt_json)?\}")
_PLACEHOLDER = re.compile(r"(?<!\{)\{(?:prompt|prompt_json)?\}(?!\})")


def has_placeholder(task_prompt: str) -> bool:
    """True when the task prompt contains {}, {prompt} or {prompt_json}."""
    return bool(_PLACEHOLDER.search(task_prompt or ""))


def apply_task_prompt(task_prompt: str, prompt: str) -> str:
    """Return the user message sent to the LLM. Empty task prompt = prompt."""
    task = task_prompt if isinstance(task_prompt, str) else ""
    if not task.strip():
        return prompt
    if not has_placeholder(task):
        return task.rstrip() + "\n\n" + prompt

    def replace(match):
        token = match.group(0)
        if token == "{{":
            return "{"
        if token == "}}":
            return "}"
        if match.group(1) == "prompt_json":
            return json.dumps(prompt, ensure_ascii=False)
        return prompt

    return _FORMAT_TOKEN.sub(replace, task)
