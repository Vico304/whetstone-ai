"""Bad input at the command line: no traceback, an ``ERROR:`` line on the usual stream, the current exit code.

The rows pin today's behaviour of scripts whose ``main()`` no other test runs; they do not say it is right.
Each row: script, arguments, exit code, stream that carries the message, first-line prefix. The other
stream must stay empty. A JSON file whose root is an array is left out on purpose: four commands still
print a traceback for it, and that fix is pending.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from _support import SCRIPT_ROOT, TEMPLATE_PLAN

ERROR = "ERROR: "

# Run in a scratch directory holding: bad.json (not JSON), resp.txt, badstore/store.json (not JSON),
# badcourse/ (outline.md, lesson-plan.json and learning-progress.json, the two JSON files broken).
# missing.json, missing.md and nostore/ do not exist.
WITHOUT_STORE = [
    ("validate_lesson", ["missing.json"], 2, "stdout", ERROR),
    ("validate_lesson", ["bad.json"], 2, "stdout", ERROR),
    ("learning_state", ["show", "--state", "missing.json"], 1, "stdout", ERROR),
    ("learning_state", ["init", "--lesson-plan", "bad.json", "--output", "out.json"], 1, "stdout", ERROR),
    ("mrg_export", ["missing.json", "--output-dir", "out"], 2, "stdout", ERROR),
    ("mrg_export", ["bad.json", "--output-dir", "out"], 2, "stdout", ERROR),
    ("store_init", ["show", "--store", "nostore"], 1, "stdout", ERROR),
    ("store_init", ["show", "--store", "badstore"], 1, "stdout", ERROR),
    ("lesson_section", ["missing.json", "--list"], 1, "stderr", ERROR),
    ("lesson_section", ["bad.json", "--list"], 1, "stderr", ERROR),
    ("diagram", ["missing.json", "--chain"], 1, "stderr", ERROR),
    ("diagram", ["bad.json", "--chain"], 1, "stderr", ERROR),
    ("comparator", ["--store", "nostore", "--lesson-id", "x", "--section-id", "s", "--extraction", "missing.json"], 1, "stderr", ERROR),
    ("review_outline", ["--store", "nostore", "--lesson-id", "x"], 1, "stderr", ERROR),
    ("review_pool", ["--store", "nostore"], 1, "stderr", ERROR),
    ("review_pool", ["--store", "badstore"], 1, "stderr", ERROR),
    ("cards", ["due", "--store", "nostore"], 1, "stderr", ERROR),
    ("cards", ["build", "--store", "badstore", "--lesson-id", "x"], 1, "stderr", ERROR),
    ("learner_state_build", ["build", "--store", "nostore"], 1, "stderr", ERROR),
    ("learner_state_build", ["build", "--store", "badstore"], 1, "stderr", ERROR),
    ("index_match", ["show", "--store", "nostore"], 1, "stderr", ERROR),
    ("outline_status", ["--course", "badcourse"], 1, "stderr", ERROR),
    ("outline_status", ["--course", "nocourse"], 0, "stdout", "skipped: "),
    ("mermaid_fit", ["missing.md"], 1, "stderr", ERROR),
    ("mermaid_fit", ["badcourse"], 1, "stderr", ERROR),
    ("lrg_record", ["append", "--store", "nostore", "--lesson-id", "x", "--section-id", "s", "--response-file", "resp.txt", "--verdict", "mastered"], 1, "stderr", ERROR),
]

# Run against a store built from the lesson-plan template (store_init init + register, mrg_export), so the
# commands get past the store checks and reach the file they are given. {lesson} and {section} are the
# template's lesson id and first section id.
WITH_STORE = [
    ("comparator", ["--store", "store", "--lesson-id", "{lesson}", "--section-id", "{section}", "--extraction", "bad.json"], 1, "stderr", ERROR),
    ("index_match", ["recall", "--store", "store", "--candidates", "missing.json"], 1, "stderr", ERROR),
    ("index_match", ["recall", "--store", "store", "--candidates", "bad.json"], 1, "stderr", ERROR),
    ("lrg_record", ["append", "--store", "store", "--lesson-id", "{lesson}", "--section-id", "{section}", "--response-file", "missing.txt", "--verdict", "mastered"], 1, "stderr", ERROR),
    ("lrg_record", ["append", "--store", "store", "--lesson-id", "{lesson}", "--section-id", "{section}", "--response-file", "resp.txt", "--verdict", "mastered", "--extraction", "bad.json"], 1, "stderr", ERROR),
    ("cards", ["build", "--store", "store", "--lesson-id", "nosuch"], 1, "stderr", ERROR),
    ("review_outline", ["--store", "store", "--lesson-id", "{lesson}"], 1, "stderr", ERROR),
    ("learner_state_build", ["show", "--store", "store"], 1, "stderr", ERROR),
]


class CliBadInputTests(unittest.TestCase):
    def _run(self, cwd: Path, script: str, args: list[str]) -> subprocess.CompletedProcess:
        env = dict(os.environ, WHETSTONE_HOME=str(cwd / "home"))
        return subprocess.run([sys.executable, str(SCRIPT_ROOT / f"{script}.py"), *args],
                              cwd=cwd, env=env, capture_output=True, text=True)

    def _check(self, cwd: Path, rows, fill=None):
        for script, args, code, stream, prefix in rows:
            args = [a.format(**fill) for a in args] if fill else args
            with self.subTest(script=script, args=" ".join(args)):
                done = self._run(cwd, script, args)
                both = done.stdout + done.stderr
                self.assertNotIn("Traceback", both)
                self.assertEqual(done.returncode, code, both)
                message, other = (done.stdout, done.stderr) if stream == "stdout" else (done.stderr, done.stdout)
                self.assertTrue(message.startswith(prefix), both)
                self.assertEqual(other, "", both)

    def test_missing_and_malformed_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "bad.json").write_text("{not json", encoding="utf-8")
            (root / "resp.txt").write_text("回答", encoding="utf-8")
            (root / "badstore").mkdir()
            (root / "badstore" / "store.json").write_text("{not json", encoding="utf-8")
            course = root / "badcourse"
            course.mkdir()
            (course / "outline.md").write_text("# 大纲\n", encoding="utf-8")
            for name in ("lesson-plan.json", "learning-progress.json"):
                (course / name).write_text("{not json", encoding="utf-8")
            self._check(root, WITHOUT_STORE)

    def test_malformed_files_against_a_real_store(self):
        plan = json.loads(TEMPLATE_PLAN.read_text(encoding="utf-8"))
        fill = {"lesson": plan["lesson_id"], "section": plan["sections"][0]["id"]}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "bad.json").write_text("{not json", encoding="utf-8")
            (root / "resp.txt").write_text("回答", encoding="utf-8")
            for script, args in (
                ("store_init", ["init", "--store", "store"]),
                ("store_init", ["register", "--store", "store", "--lesson-plan", str(TEMPLATE_PLAN)]),
                ("mrg_export", [str(TEMPLATE_PLAN), "--store", "store"]),
            ):
                done = self._run(root, script, args)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self._check(root, WITH_STORE, fill)
            (root / "store" / "learner-state.json").write_text("{not json", encoding="utf-8")
            self._check(root, [
                ("learner_state_build", ["show", "--store", "store"], 1, "stderr", ERROR),
                ("review_outline", ["--store", "store", "--lesson-id", "{lesson}"], 1, "stderr", ERROR),
                ("review_pool", ["--store", "store"], 1, "stderr", ERROR),
            ], fill)


if __name__ == "__main__":
    unittest.main()
