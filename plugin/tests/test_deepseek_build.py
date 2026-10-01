"""The DeepSeek build driver: sandbox, token cap, ledger and key handling, all without a network."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _support import PLUGIN_ROOT, load_module

deepseek_build = load_module("deepseek_build", PLUGIN_ROOT / "evals")
SECRET = "sk-test-not-a-real-key-4242"


def call(n: int, name: str, **arguments) -> dict:
    return {"id": f"c{n}", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


def usage(prompt: int, out: int, hit: int) -> dict:
    return {"prompt_tokens": prompt, "completion_tokens": out, "prompt_cache_hit_tokens": hit,
            "prompt_cache_miss_tokens": prompt - hit}


class DeepSeekBuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "src").mkdir()
        (self.tmp / "src" / "notes.md").write_text("# 材料\n\n一段材料。\n", encoding="utf-8")
        self.case_path = self.tmp / "case.json"
        self.case_path.write_text(json.dumps({
            "id": "t1", "materials_root": str(self.tmp / "src"), "materials": ["notes.md"],
            "request": "建课，到大纲停下。", "auto_reply": "你定。", "max_auto_replies": 1}), encoding="utf-8")
        self.out = self.tmp / "out"

    def run_main(self, replies: list[dict], *extra: str) -> tuple[int, str, str]:
        path = self.tmp / f"replies-{len(list(self.tmp.glob('replies-*')))}.json"
        path.write_text(json.dumps(replies), encoding="utf-8")
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {deepseek_build.KEY_ENV: SECRET}), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = deepseek_build.main(["--case", str(self.case_path), "--out-dir", str(self.out),
                                        "--replies", str(path), *extra])
        return code, stdout.getvalue(), stderr.getvalue()

    def ledger(self) -> dict:
        return json.loads((self.out / "t1" / "ledger.json").read_text(encoding="utf-8"))

    def test_stops_at_the_outline_pause_and_books_every_request(self):
        sandbox = self.out / "t1" / "sandbox"
        plan = sandbox / "workspace" / "courses" / "c" / "lesson-plan.json"
        replies = [
            {"message": {"role": "assistant", "content": "", "tool_calls": [
                call(1, "read_file", path=str(sandbox / "skill" / "learn" / "SKILL.md")),
                call(2, "write_file", path=str(plan), content='{"schema_version": "1.6"'),
                call(3, "write_file", path=str(plan), content="}", append=True),
                call(5, "write_file", path=str(plan.parent / "outline.md"), content="# 大纲\n"),
                call(4, "run_command", argv=["python3", str(sandbox / "skill" / "learn" / "scripts" / "validate_lesson.py"), str(plan)])]},
             "usage": usage(1000, 200, 0), "finish_reason": "tool_calls"},
            {"message": {"role": "assistant", "content": "大纲在这里，请确认。"}, "usage": usage(1500, 50, 1000)},
        ]
        code, stdout, _ = self.run_main(replies)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(plan.read_text(encoding="utf-8")), {"schema_version": "1.6"})
        ledger = self.ledger()
        self.assertEqual(ledger["stop_reason"], "outline")
        self.assertEqual(ledger["totals"], {"input": 2500, "output": 250, "cache_hit": 1000, "cache_miss": 1500,
                                            "requests": 2, "all": 2750})
        self.assertIn("outline; 2 requests", stdout)
        tool_outputs = [m["content"] for m in json.loads((self.out / "t1" / "messages.json").read_text(encoding="utf-8"))
                        if m["role"] == "tool"]
        self.assertIn("Guided Learning Tutor", tool_outputs[0])
        self.assertTrue(tool_outputs[4].startswith("exit "))
        for path in (self.out / "t1").rglob("*"):
            if path.is_file():
                self.assertNotIn(SECRET, path.read_text(encoding="utf-8", errors="replace"), path)

    def test_token_cap_stops_before_the_request_that_would_pass_it(self):
        replies = [{"message": {"role": "assistant", "content": "", "tool_calls": [call(1, "list_dir", path=".")]},
                    "usage": usage(4000, 100, 0)}] * 3
        code, _, _ = self.run_main(replies, "--max-total-tokens", "12000", "--max-output-tokens", "1000")
        self.assertEqual(code, 1)
        ledger = self.ledger()
        self.assertEqual(ledger["stop_reason"], "token_cap")
        self.assertLessEqual(ledger["totals"]["all"], 12000)
        self.assertEqual(ledger["totals"]["requests"], 2)  # a third (8200 + ~4200 + 1000) would pass 12000

    def test_a_half_written_plan_or_a_plan_without_outline_is_not_the_pause(self):
        sandbox = deepseek_build.Sandbox(self.tmp / "box")
        sandbox.build(deepseek_build.load_case(mock.Mock(case=str(self.case_path), material_id=None)))
        course = sandbox.workspace / "courses" / "c"
        course.mkdir(parents=True)
        (course / "lesson-plan.json").write_text('{"sections": [', encoding="utf-8")
        (course / "outline.md").write_text("# 大纲\n", encoding="utf-8")
        self.assertFalse(sandbox.outline_ready())
        (course / "lesson-plan.json").write_text("{}", encoding="utf-8")
        self.assertTrue(sandbox.outline_ready())
        (course / "outline.md").rename(course / "notes.md")
        self.assertFalse(sandbox.outline_ready())

    def test_host_notes_warn_against_the_two_waste_patterns_of_the_calibration_run(self):
        # 2026-09 calibration run: the model read validate_lesson.py (~15k tokens kept in context) and lost one
        # reply to an 8192-token cut while writing lesson-plan.json in one go.
        prompt = deepseek_build.system_prompt(deepseek_build.Sandbox(self.tmp / "box"))
        self.assertIn("--help", prompt)
        self.assertIn("不必读 scripts/ 下的源码", prompt)
        self.assertIn("一开始就分块写", prompt)
        self.assertIn("append=true", prompt)

    def test_a_cut_reply_with_only_thinking_stays_out_of_the_context(self):
        # 2026-09-30 run, request 11: 8192 tokens of thinking, no text, no tool call; it then rode along in 17 requests.
        replies = [
            {"message": {"role": "assistant", "content": "", "reasoning_content": "想" * 500},
             "usage": {**usage(1000, 16384, 0), "completion_tokens_details": {"reasoning_tokens": 16384}},
             "finish_reason": "length"},
            {"message": {"role": "assistant", "content": "", "reasoning_content": "写骨架",
                         "tool_calls": [call(1, "list_dir", path=".")]},
             "usage": usage(1100, 300, 1000), "finish_reason": "length"},
            {"message": {"role": "assistant", "content": "你想学什么？"}, "usage": usage(1300, 20, 1000)},
            {"message": {"role": "assistant", "content": "好的。"}, "usage": usage(1400, 20, 1000)},
        ]
        path = self.tmp / "replies-cut.json"
        path.write_text(json.dumps(replies), encoding="utf-8")
        client = deepseek_build.ScriptedClient(path)
        case = deepseek_build.load_case(mock.Mock(case=str(self.case_path), material_id=None))
        summary = deepseek_build.drive(case, client, self.out, 10**6, 10, 16384)
        second, third = client.calls[1], client.calls[2]
        self.assertNotIn("想" * 500, json.dumps(second, ensure_ascii=False))
        self.assertEqual([m["role"] for m in second], ["system", "user"])  # note folded into the request turn
        self.assertTrue(second[-1]["content"].endswith(deepseek_build.CUT_THINKING_ONLY))
        # a cut reply that did call a tool keeps its thinking: the tool loop needs it back
        self.assertEqual([m["role"] for m in third], ["system", "user", "assistant", "tool"])
        self.assertEqual(third[2]["reasoning_content"], "写骨架")
        rows = summary["requests"]
        self.assertEqual([(r["in_context"], r["reasoning_chars"]) for r in rows[:2]], [(False, 500), (True, 3)])
        self.assertEqual(rows[0]["reasoning_tokens"], 16384)
        lines = (self.out / "t1" / "transcript.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(json.loads(lines[0])["message"]["reasoning_content"], "想" * 500)  # kept for review

    def test_output_cap_defaults_to_16384_and_the_host_note_follows_it(self):
        self.assertEqual(deepseek_build.DEFAULT_MAX_OUTPUT, 16384)
        box = deepseek_build.Sandbox(self.tmp / "box")
        self.assertIn("最多约 16000 token", deepseek_build.system_prompt(box))
        self.assertIn("最多约 8000 token", deepseek_build.system_prompt(box, 8192))

    def test_learner_turns_get_the_fixed_reply_then_the_run_stops(self):
        replies = [{"message": {"role": "assistant", "content": "你想学什么？"}, "usage": usage(10, 5, 0)}] * 2
        code, _, _ = self.run_main(replies)
        self.assertEqual(code, 1)
        self.assertEqual(self.ledger()["stop_reason"], "learner_turns")
        messages = json.loads((self.out / "t1" / "messages.json").read_text(encoding="utf-8"))
        self.assertEqual([m["content"] for m in messages if m["role"] == "user"][1:], ["你定。"])

    def test_tools_stay_inside_the_sandbox(self):
        sandbox = deepseek_build.Sandbox(self.tmp / "box")
        sandbox.build(deepseek_build.load_case(mock.Mock(case=str(self.case_path), material_id=None)))
        run = deepseek_build.run_tool
        self.assertIn("outside the sandbox", run(sandbox, "write_file", json.dumps({"path": str(self.tmp / "x.md"), "content": "x"})))
        self.assertIn("outside the sandbox", run(sandbox, "read_file", json.dumps({"path": "../../case.json"})))
        self.assertIn("read-only", run(sandbox, "write_file", json.dumps({"path": str(sandbox.skill / "SKILL.md"), "content": "x"})))
        self.assertIn("read-only", run(sandbox, "write_file", json.dumps({"path": str(sandbox.materials / "notes.md"), "content": "x"})))
        self.assertIn("only", run(sandbox, "run_command", json.dumps({"argv": ["bash", "-c", "env"]})))
        self.assertIn("only run the skill", run(sandbox, "run_command", json.dumps({"argv": ["python3", "-c", "print(1)"]})))
        script = str(sandbox.skill / "scripts" / "validate_lesson.py")
        self.assertIn("outside the sandbox", run(sandbox, "run_command", json.dumps({"argv": ["python3", script, "/etc/passwd"]})))
        self.assertFalse((self.tmp / "x.md").exists())

    def test_commands_do_not_inherit_the_key(self):
        sandbox = deepseek_build.Sandbox(self.tmp / "box")
        sandbox.build(deepseek_build.load_case(mock.Mock(case=str(self.case_path), material_id=None)))
        with mock.patch.dict(os.environ, {deepseek_build.KEY_ENV: SECRET}), \
                mock.patch.object(deepseek_build.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            deepseek_build.run_command(sandbox, ["date", "-u"])
        self.assertNotIn(SECRET, json.dumps(run.call_args.kwargs["env"]))

    def test_client_reads_the_key_only_from_the_environment_and_never_shows_it(self):
        with mock.patch.dict(os.environ, {deepseek_build.KEY_ENV: ""}):
            with self.assertRaises(deepseek_build.ModelError):
                deepseek_build.DeepSeekClient()
        with mock.patch.dict(os.environ, {deepseek_build.KEY_ENV: SECRET}):
            client = deepseek_build.DeepSeekClient()
        self.assertNotIn(SECRET, repr(client))
        self.assertIsInstance(client, deepseek_build.ModelClient)

    def test_dry_run_needs_no_key_and_sends_nothing(self):
        stdout = io.StringIO()
        with mock.patch.dict(os.environ, {deepseek_build.KEY_ENV: ""}), contextlib.redirect_stdout(stdout), \
                mock.patch.object(deepseek_build.urllib.request, "urlopen") as urlopen:
            code = deepseek_build.main(["--case", str(self.case_path), "--out-dir", str(self.out), "--dry-run"])
        self.assertEqual(code, 0)
        urlopen.assert_not_called()
        estimate = json.loads((self.out / "dry-run-t1.json").read_text(encoding="utf-8"))
        self.assertLess(estimate["low"]["input"], estimate["high"]["input"])
        self.assertEqual(estimate["low"]["input"], estimate["low"]["cache_hit"] + estimate["low"]["cache_miss"])
        self.assertFalse((self.out / "t1").exists())

    def test_estimate_counts_cjk_heavier_than_ascii(self):
        self.assertEqual(deepseek_build.estimate_tokens("中文字符"), 2)
        self.assertEqual(deepseek_build.estimate_tokens("abcdefghij"), 3)


if __name__ == "__main__":
    unittest.main()
