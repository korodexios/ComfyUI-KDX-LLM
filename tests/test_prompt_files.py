"""System prompts as one file per prompt (prompt_store.py): any text, migration, robustness."""

import importlib.util
import json
import os
import shutil
import tempfile
import time
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_store():
    spec = importlib.util.spec_from_file_location("kdx_prompt_store_files", os.path.join(BASE, "prompt_store.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class PromptFilesBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="kdx_prompts_")
        self.dir = os.path.join(self.tmp, "system_prompts")
        self.legacy = os.path.join(self.tmp, "system_prompts.json")
        self._env = {k: os.environ.get(k) for k in ("KDX_LLM_PROMPTS_DIR", "KDX_LLM_PROMPTS_FILE")}
        os.environ["KDX_LLM_PROMPTS_DIR"] = self.dir
        os.environ["KDX_LLM_PROMPTS_FILE"] = self.legacy
        self.ps = load_store()

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name, text):
        os.makedirs(self.dir, exist_ok=True)
        with open(os.path.join(self.dir, name), "w", encoding="utf-8", newline="") as f:
            f.write(text)


class TestPromptFiles(PromptFilesBase):
    WILD = '# Title\n\n"quotes" \\back\\slash {braces} |pipe| $$ ::  tab\there\r\nemoji 🐱 ž č\n---\n{"json": true}\n'

    def test_any_text_round_trips_exactly(self):
        self.assertTrue(self.ps.save("wild", self.WILD, "all the characters"))
        self.assertEqual(self.ps.get("wild"), {"prompt": self.WILD, "description": "all the characters"})
        with open(os.path.join(self.dir, "wild.md"), encoding="utf-8", newline="") as f:
            self.assertEqual(f.read(), self.WILD)

    def test_hand_written_files_are_profiles(self):
        self.write("krea.md", "write a prompt")
        self.write("plain.txt", "plain text prompt")
        self.write("both.md", "from md")
        self.write("both.txt", "from txt")
        self.write("notes.json", "{}")
        self.write(".hidden.md", "x")
        self.assertEqual(self.ps.names(), ["both", "krea", "plain"])
        self.assertEqual(self.ps.get("plain")["prompt"], "plain text prompt")
        self.assertEqual(self.ps.get("both")["prompt"], "from md")
        self.assertEqual(self.ps.get("missing"), {})

    def test_bom_is_ignored(self):
        self.write("bom.md", "﻿hello")
        self.assertEqual(self.ps.get("bom")["prompt"], "hello")

    def test_unsafe_names_become_file_names(self):
        self.assertTrue(self.ps.save('a/b:c*?"<>|', "x"))
        self.assertEqual(self.ps.names(), ["a_b_c______"])
        self.assertFalse(self.ps.save("  ", "x"))
        self.assertTrue(self.ps.save("../escape", "x"))  # stays inside the folder
        self.assertTrue(os.path.isfile(os.path.join(self.dir, "_escape.md")))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "escape.md")))
        self.assertFalse(self.ps.save("..", "x"))

    def test_save_updates_existing_txt_in_place(self):
        self.write("keep.txt", "old")
        self.ps.save("keep", "new")
        self.assertFalse(os.path.exists(os.path.join(self.dir, "keep.md")))
        self.assertEqual(self.ps.get("keep")["prompt"], "new")

    def test_delete_removes_all_variants_and_description(self):
        self.ps.save("gone", "x", "desc")
        self.write("gone.txt", "y")
        self.assertTrue(self.ps.delete("gone"))
        self.assertEqual(self.ps.names(), [])
        self.assertFalse(self.ps.delete("gone"))
        with open(os.path.join(self.dir, ".descriptions.json"), encoding="utf-8") as f:
            self.assertNotIn("gone", json.load(f))

    def test_broken_descriptions_do_not_break_prompts(self):
        self.ps.save("p", "text", "d")
        self.write(".descriptions.json", "{ not json")
        self.assertEqual(self.ps.get("p"), {"prompt": "text", "description": ""})
        self.assertTrue(self.ps.save("p2", "t2", "d2"))
        self.assertEqual(self.ps.get("p2")["description"], "d2")

    def test_mtime_changes_on_edit_add_remove(self):
        self.ps.save("a", "1")
        m1 = self.ps.mtime()
        path = os.path.join(self.dir, "a.md")
        os.utime(path, (time.time() + 10, time.time() + 10))
        m2 = self.ps.mtime()
        self.assertGreater(m2, m1)
        self.write("b.md", "2")
        later = time.time() + 20
        os.utime(self.dir, (later, later))
        self.assertGreater(self.ps.mtime(), m2)


class TestMigration(PromptFilesBase):
    def legacy_json(self, data):
        with open(self.legacy, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def test_json_is_split_into_files_once(self):
        self.legacy_json({"version": 1, "prompts": {
            "krea2_sfw": {"prompt": 'Line 1\n"quoted" {x}', "description": "SFW writer"},
            "plain": "string value",
            "bad/name": {"prompt": "p"},
        }})
        self.assertEqual(self.ps.names(), ["bad_name", "krea2_sfw", "plain"])
        self.assertEqual(self.ps.get("krea2_sfw"), {"prompt": 'Line 1\n"quoted" {x}', "description": "SFW writer"})
        self.assertFalse(os.path.exists(self.legacy))
        self.assertTrue(os.path.exists(self.legacy + ".migrated"))
        self.assertEqual(self.ps.migrate(), 0)

    def test_existing_files_win_over_json(self):
        self.write("same.md", "edited by hand")
        self.legacy_json({"prompts": {"same": {"prompt": "old json"}}})
        self.assertEqual(self.ps.get("same")["prompt"], "edited by hand")

    def test_corrupt_json_is_left_alone(self):
        with open(self.legacy, "w", encoding="utf-8") as f:
            f.write("{ broken")
        self.assertEqual(self.ps.names(), [])
        self.assertTrue(os.path.exists(self.legacy))
        self.assertTrue(self.ps.save("new", "works"))
        self.assertEqual(self.ps.names(), ["new"])


if __name__ == "__main__":
    unittest.main()
