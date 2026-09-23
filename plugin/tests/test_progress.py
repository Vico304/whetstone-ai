from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from _support import (
    PLUGIN_ROOT,
    diagram,
    learning_state,
    lesson_section,
    load_template,
    next_step,
    outline_status,
    validate_lesson,
)


class SectionViewAndNextStepTests(unittest.TestCase):
    def test_lesson_section_prints_one_section_with_hidden_layers_and_final_view(self):
        plan = load_template()
        listing = lesson_section.render_list(plan)
        self.assertIn("- s01 ", listing)
        self.assertIn("core=2", listing)
        view = lesson_section.render_section(plan, "s01")
        section = plan["sections"][0]
        for text in (section["problem"], section["solution"], section["mechanism"], section["checkpoint"]["prompt"], section["meaning"]):
            self.assertIn(text, view)
        for criterion in section["checkpoint"]["criteria"]:
            self.assertIn(criterion["text"], view)
        self.assertIn("验收题", view)          # the supporting concept's own check
        self.assertLess(len(view), len(json.dumps(plan, ensure_ascii=False)))
        with self.assertRaises(ValueError):
            lesson_section.render_section(plan, "s99")
        final = lesson_section.render_final(plan)
        names = lesson_section.shuffled_concept_names(plan)
        self.assertEqual(sorted(names), sorted({c["name"] for c in section["concepts"] if c.get("role", "core") in {"core", "supporting"}}))
        self.assertEqual(names, lesson_section.shuffled_concept_names(plan))  # fixed order per lesson id
        for name in names:
            self.assertIn(f"- {name}", final)
        self.assertNotIn(section["title"], final.split("## 本课概念名")[1])  # no section titles next to the names

    def test_next_step_decides_the_state_from_the_progress_file(self):
        from datetime import datetime, timedelta, timezone
        plan = load_template()
        state = learning_state.create_state(plan)
        now = datetime(2026, 9, 13, 10, tzinfo=timezone.utc)

        def decide(**kwargs):
            return next_step.decide(state, kwargs.pop("plan", plan), kwargs.pop("now", now), kwargs.pop("resume", False))

        first = decide()
        self.assertEqual((first["state"], first["section_id"], first["read"]), ("READY", "s01", "ready.md"))
        self.assertIsNone(first["opener"])  # nothing completed yet: no variant question to ask
        learning_state.append_attempt(state, "s01", "a", "", "partial", 3)
        retry = decide()
        self.assertEqual((retry["state"], retry["read"], retry["last_verdict"]), ("AWAITING_RETRY", "feedback.md", "partial"))
        learning_state.append_attempt(state, "s01", "b", "", "mastered", 4)
        finish = decide()
        self.assertEqual((finish["state"], finish["read"]), ("FINISH", "finish.md"))

        # a second sitting on a longer course: opener first, then the current section
        plan3 = load_template()
        plan3["sections"] = [dict(plan3["sections"][0], id=f"s0{i}") for i in (1, 2, 3)]
        state = learning_state.create_state(plan3)
        learning_state.append_attempt(state, "s01", "a", "", "mastered", None)
        state["updated_at"] = "2026-09-12T10:00:00Z"
        later = decide(plan=plan3)
        self.assertEqual((later["state"], later["section_id"], later["opener"], later["new_sitting"]), ("READY", "s02", "resume.md", True))
        soon = decide(plan=plan3, now=datetime(2026, 9, 12, 10, 30, tzinfo=timezone.utc))
        self.assertIsNone(soon["opener"])
        self.assertEqual(decide(plan=plan3, now=datetime(2026, 9, 12, 10, 30, tzinfo=timezone.utc), resume=True)["opener"], "resume.md")
        learning_state.block_section(state, "s02", "child-course-0")
        blocked = decide(plan=plan3)
        self.assertEqual((blocked["state"], blocked["blocked_by"], blocked["read"]), ("BLOCKED", "child-course-0", "../prerequisite/return.md"))

        # skeleton course: probe round first, until it is marked
        skeleton = dict(plan3, shape="skeleton")
        state = learning_state.create_state(skeleton)
        self.assertEqual(decide(plan=skeleton)["state"], "PROBE")
        # a prerequisite course built from the pre-probe map blocks first: BLOCKED wins over PROBE
        learning_state.block_section(state, "s01", "gap-course-1")
        self.assertEqual(decide(plan=skeleton)["state"], "BLOCKED")
        state = learning_state.create_state(skeleton)
        learning_state.mark_event(state, "probe_completed", "全部照学")
        self.assertEqual(decide(plan=skeleton)["state"], "READY")
        self.assertEqual(state["events"][-1]["type"], "probe_completed")
        with self.assertRaises(ValueError):
            learning_state.mark_event(state, "lunch")

    def test_next_step_cli_prints_quoted_paths_and_the_record_command(self):
        import shlex, subprocess, sys
        with tempfile.TemporaryDirectory() as temporary:
            course = Path(temporary).resolve() / "my course"  # next_step.py resolves --progress; compare resolved to resolved
            course.mkdir()
            plan = load_template()
            (course / "lesson-plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            learning_state.atomic_write(course / "learning-progress.json", learning_state.create_state(plan))
            script = PLUGIN_ROOT / "skills" / "learn" / "scripts" / "next_step.py"
            out = subprocess.run([sys.executable, str(script), "--progress", str(course / "learning-progress.json")],
                                 capture_output=True, text=True, check=True).stdout
            self.assertIn("state: READY  section: s01", out)
            self.assertIn(f"{shlex.quote(str(course / 'lesson-plan.json'))} --section s01", out)  # the course path has a space: quoted
            self.assertRegex(out, r"learning_state\.py'? record --state ")                        # the script path is quoted only if it needs it
            self.assertIn("ready.md", out)
            out = subprocess.run([sys.executable, str(script), "--progress", str(course / "learning-progress.json"), "--store", "/tmp/s t"],
                                 capture_output=True, text=True, check=True).stdout
            self.assertRegex(out, r"lrg_record\.py'? append --store '/tmp/s t'")


class LearningStateTests(unittest.TestCase):
    def test_attempts_are_appended_without_losing_history(self):
        plan_path = PLUGIN_ROOT / "skills" / "learn" / "assets" / "lesson-plan-template.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        state = learning_state.create_state(plan)

        learning_state.append_attempt(state, "s01", "first answer", "one gap", "partial", 3)
        learning_state.append_attempt(state, "s01", "revised answer", "clear", "mastered", 4)

        attempts = state["sections"][0]["attempts"]
        self.assertEqual([item["response"] for item in attempts], ["first answer", "revised answer"])
        self.assertEqual([item["kind"] for item in attempts], ["checkpoint", "checkpoint"])
        self.assertEqual(state["status"], "completed")
        self.assertIsNone(state["current_section_id"])

    def test_identical_responses_are_refused_and_backfill_keeps_the_learner_time(self):
        state = learning_state.create_state(load_template())
        learning_state.append_attempt(state, "s01", "同一段回答", "", "partial", 3, at="2026-09-12T20:00:00+08:00")
        self.assertEqual(state["sections"][0]["attempts"][0]["at"], "2026-09-12T12:00:00Z")
        with self.assertRaises(ValueError):
            learning_state.append_attempt(state, "s01", "同一段回答 ", "", "partial", 3)  # same text, whitespace aside
        learning_state.append_attempt(state, "s01", "同一段回答", "", "mastered", 3, review=True)  # a review may repeat it
        learning_state.append_attempt(state, "s01", "同一段回答", "", "mastered", 3, force=True)
        self.assertEqual(len(state["sections"][0]["attempts"]), 3)
        with self.assertRaises(ValueError):
            learning_state.append_attempt(state, "s02", "x", "", "partial", None, at="2026-09-12T20:00")  # no offset

    def test_criteria_met_and_depth_are_persisted_and_validated(self):
        state = learning_state.create_state(load_template())
        learning_state.append_attempt(state, "s01", "a", "", "partial", 3, criteria_met=["c1", " c2 "], depth_reached="mechanism")
        attempt = state["sections"][0]["attempts"][0]
        self.assertEqual(attempt["criteria_met"], ["c1", "c2"])
        self.assertEqual(attempt["depth_reached"], "mechanism")
        learning_state.append_attempt(state, "s01", "b", "", "mastered", None)
        self.assertEqual(state["sections"][0]["attempts"][1]["criteria_met"], [])
        self.assertIsNone(state["sections"][0]["attempts"][1]["depth_reached"])
        with self.assertRaises(ValueError):
            learning_state.append_attempt(state, "s01", "c", "", "partial", None, depth_reached="deep")
        with self.assertRaises(ValueError):
            learning_state.append_attempt(state, "s01", "c", "", "partial", None, criteria_met=["c1", "c1"])

    @staticmethod
    def _three_section_state():
        plan_path = PLUGIN_ROOT / "skills" / "learn" / "assets" / "lesson-plan-template.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        template = plan["sections"][0]
        plan["sections"] = [
            {**template, "id": "s01", "depends_on": []},
            {**template, "id": "s02", "depends_on": ["s01"]},
            {**template, "id": "s03", "depends_on": ["s02"]},
        ]
        return learning_state.create_state(plan)

    def test_failed_review_does_not_move_position_backwards(self):
        state = self._three_section_state()
        learning_state.append_attempt(state, "s01", "a", "", "mastered", None)
        learning_state.append_attempt(state, "s02", "b", "", "mastered", None)
        self.assertEqual(state["current_section_id"], "s03")

        # resume opener: variant retrieval on s01 fails -> forgetting signal, but learner stays on s03
        learning_state.append_attempt(state, "s01", "forgot", "gap", "retry", 5, review=True)

        self.assertEqual(state["sections"][0]["status"], "in_progress")
        self.assertEqual(state["sections"][0]["attempts"][-1]["kind"], "review")
        self.assertEqual(state["current_section_id"], "s03")
        self.assertEqual(state["status"], "in_progress")

        # finishing s03 then falls back to the regressed section instead of declaring the lesson done
        learning_state.append_attempt(state, "s03", "c", "", "mastered", None)
        self.assertEqual(state["current_section_id"], "s01")
        self.assertEqual(state["status"], "in_progress")

        learning_state.append_attempt(state, "s01", "recovered", "", "mastered", None)
        self.assertEqual(state["status"], "completed")
        self.assertIsNone(state["current_section_id"])
        self.assertEqual(sum(1 for e in state["events"] if e["type"] == "lesson_completed"), 1)

    def test_failed_review_after_completion_reopens_lesson(self):
        state = self._three_section_state()
        for section_id in ("s01", "s02", "s03"):
            learning_state.append_attempt(state, section_id, "ok", "", "mastered", None)
        self.assertEqual(state["status"], "completed")

        learning_state.append_attempt(state, "s02", "hmm", "", "partial", 2, review=True)

        self.assertEqual(state["status"], "in_progress")
        self.assertEqual(state["current_section_id"], "s02")

    def test_current_position_advances_past_completed_sections(self):
        state = self._three_section_state()
        learning_state.append_attempt(state, "s02", "skip ahead", "", "skipped", None)
        self.assertEqual(state["current_section_id"], "s01")
        learning_state.append_attempt(state, "s01", "ok", "", "mastered", None)
        self.assertEqual(state["current_section_id"], "s03")


class OutlineStatusTests(unittest.TestCase):
    def test_outline_status_follows_the_progress_file_and_keeps_the_closing_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            course = Path(temporary) / "course"
            course.mkdir()
            plan = load_template()
            plan["sections"].append(dict(plan["sections"][0], id="s02", title="第二节", depends_on=["s01"]))
            plan["sections"][0]["new_problem"] = "下一节"
            (course / "lesson-plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            outline = (PLUGIN_ROOT / "skills" / "learn" / "assets" / "outline-template.md").read_text(encoding="utf-8")
            outline = outline.replace("| 1 | [[s01\\|从线性材料到总体结构]] | 逐页阅读让局部遮住整体 → 先建立输入、过程、输出的宏观地图 | 待学 |",
                                      "| 1 | [[s01\\|从线性材料到总体结构]] | 逐页阅读让局部遮住整体 → 先建立输入、过程、输出的宏观地图 | 待学 |\n| 2 | 第二节 | 问题 → 方案 | 待学 |")
            outline = outline.replace("## 本课程涉及的全部概念", diagram.chain(plan) + "\n\n## 本课程涉及的全部概念")  # the chain must show s02 too
            (course / "outline.md").write_text(outline, encoding="utf-8")
            state = learning_state.create_state(plan)
            learning_state.atomic_write(course / "learning-progress.json", state)
            learning_state.append_attempt(state, "s01", "a", "", "partial", 3, depth_reached="mechanism")
            learning_state.atomic_write(course / "learning-progress.json", state)
            result = outline_status.refresh(course)
            text = (course / "outline.md").read_text(encoding="utf-8")
            self.assertTrue(result["updated"])
            self.assertIn("| 学习中（1 次作答） |", text)
            self.assertIn("| 2 | 第二节 | 问题 → 方案 | 待学 |", text)
            self.assertIn("- 进度：0/2 节完成，1 节学习中；课程进行中", text)
            self.assertIn("| s01 从线性材料到总体结构 | 学习中（1 次作答） | 1 | 部分 | 机制 |", text)
            self.assertEqual(validate_lesson.validate_outline(text, plan), [])
            # the closing summary written after the block survives the next refresh; recording refreshes on its own
            (course / "outline.md").write_text(text + "\n已解释成功：第一节的因果链。\n", encoding="utf-8")
            learning_state.append_attempt(state, "s01", "b", "", "mastered", 5, depth_reached="rationale")
            learning_state.append_attempt(state, "s02", "c", "", "mastered", 5, depth_reached="mechanism")
            learning_state.atomic_write(course / "learning-progress.json", state)
            learning_state.refresh_outline(course / "learning-progress.json")
            text = (course / "outline.md").read_text(encoding="utf-8")
            self.assertIn("2/2 节完成；课程已结课（", text)
            self.assertIn("| s01 从线性材料到总体结构 | 已完成（", text)
            self.assertIn("已解释成功：第一节的因果链。", text)
            self.assertEqual(text.count(outline_status.START), 1)
            self.assertIn("- 仍待复习：无", text)
            self.assertFalse(outline_status.refresh(Path(temporary))["updated"])   # nothing to do without the three files
