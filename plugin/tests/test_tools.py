from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = PLUGIN_ROOT / "skills" / "guided-learning-tutor" / "scripts"
CLARIFY_SCRIPT_ROOT = PLUGIN_ROOT / "skills" / "clarify" / "scripts"


def load_module(name: str, root: Path = SCRIPT_ROOT):
    spec = importlib.util.spec_from_file_location(name, root / f"{name}.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


source_manifest = load_module("source_manifest")
validate_lesson = load_module("validate_lesson")
learning_state = load_module("learning_state")
validate_prerequisites = load_module("validate_prerequisites")
prerequisite_state = load_module("prerequisite_state")
scan_wikilinks = load_module("scan_wikilinks", CLARIFY_SCRIPT_ROOT)


class SourceManifestTests(unittest.TestCase):
    def test_inventory_skips_sensitive_and_ignored_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
            (root / ".env").write_text("API_KEY=secret\n", encoding="utf-8")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "ignored.js").write_text("ignored\n", encoding="utf-8")

            manifest = source_manifest.build_manifest([root], root, 1024, 1024)
            by_path = {entry["path"]: entry for entry in manifest["files"]}

            self.assertEqual(by_path["src/main.py"]["status"], "included")
            self.assertEqual(by_path[".env"]["status"], "skipped_sensitive")
            self.assertNotIn("node_modules/ignored.js", by_path)
            self.assertNotIn("sha256", by_path[".env"])


class LessonValidationTests(unittest.TestCase):
    def test_template_is_valid_and_matches_guide(self):
        plan_path = PLUGIN_ROOT / "skills" / "guided-learning-tutor" / "assets" / "lesson-plan-template.json"
        guide_path = PLUGIN_ROOT / "skills" / "guided-learning-tutor" / "assets" / "teaching-guide-template.md"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))

        self.assertEqual(validate_lesson.validate_plan(plan), [])
        self.assertEqual(validate_lesson.validate_guide(guide_path.read_text(encoding="utf-8"), plan), [])

    def test_project_consensus_example_is_valid_and_traceable(self):
        example_root = PLUGIN_ROOT / "examples" / "project-consensus"
        plan = json.loads((example_root / "lesson-plan.json").read_text(encoding="utf-8"))
        guide = (example_root / "teaching-guide.md").read_text(encoding="utf-8")
        manifest = json.loads((example_root / "sources.json").read_text(encoding="utf-8"))
        paths = validate_lesson.manifest_paths(manifest)

        self.assertEqual(validate_lesson.validate_plan(plan, paths), [])
        self.assertEqual(validate_lesson.validate_guide(guide, plan), [])

    def test_forward_dependency_is_rejected(self):
        plan_path = PLUGIN_ROOT / "skills" / "guided-learning-tutor" / "assets" / "lesson-plan-template.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["sections"][0]["depends_on"] = ["s02"]

        errors = validate_lesson.validate_plan(plan)

        self.assertTrue(any("before it is available" in error for error in errors))

    def test_self_dependency_is_rejected(self):
        plan_path = PLUGIN_ROOT / "skills" / "guided-learning-tutor" / "assets" / "lesson-plan-template.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["sections"][0]["depends_on"] = ["s01"]

        errors = validate_lesson.validate_plan(plan)

        self.assertTrue(any("before it is available" in error for error in errors))

    def test_guide_leaking_criteria_is_rejected(self):
        plan_path = PLUGIN_ROOT / "skills" / "guided-learning-tutor" / "assets" / "lesson-plan-template.json"
        guide_path = PLUGIN_ROOT / "skills" / "guided-learning-tutor" / "assets" / "teaching-guide-template.md"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        leaked = plan["sections"][0]["checkpoint"]["criteria"][0]
        guide = guide_path.read_text(encoding="utf-8") + f"\n参考答案：{leaked}\n"

        errors = validate_lesson.validate_guide(guide, plan)

        self.assertTrue(any("leaks assessment criterion" in error for error in errors))

    def test_cognitive_load_warnings(self):
        plan_path = PLUGIN_ROOT / "skills" / "guided-learning-tutor" / "assets" / "lesson-plan-template.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        section = plan["sections"][0]
        section["concepts"] = [
            {"name": f"概念{i}", "explanation": "占位解释"} for i in range(5)
        ]

        warnings = validate_lesson.collect_warnings(plan)

        self.assertTrue(any("concepts" in warning for warning in warnings))
        self.assertEqual(validate_lesson.collect_warnings({"sections": []}), [])


class LearningStateTests(unittest.TestCase):
    def test_attempts_are_appended_without_losing_history(self):
        plan_path = PLUGIN_ROOT / "skills" / "guided-learning-tutor" / "assets" / "lesson-plan-template.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        state = learning_state.create_state(plan)

        learning_state.append_attempt(state, "s01", "first answer", "one gap", "partial", 3)
        learning_state.append_attempt(state, "s01", "revised answer", "clear", "mastered", 4)

        attempts = state["sections"][0]["attempts"]
        self.assertEqual([item["response"] for item in attempts], ["first answer", "revised answer"])
        self.assertEqual(state["status"], "completed")
        self.assertIsNone(state["current_section_id"])


class PrerequisiteValidationTests(unittest.TestCase):
    def test_prerequisite_templates_are_valid(self):
        asset_root = PLUGIN_ROOT / "skills" / "guided-learning-tutor" / "assets"
        plan = json.loads((asset_root / "prerequisite-plan-template.json").read_text(encoding="utf-8"))
        guide = (asset_root / "prerequisite-guide-template.md").read_text(encoding="utf-8")

        self.assertEqual(validate_prerequisites.validate_plan(plan), [])
        self.assertEqual(validate_prerequisites.validate_guide(guide), [])

    def test_duplicate_prerequisite_id_is_rejected(self):
        plan_path = (
            PLUGIN_ROOT
            / "skills"
            / "guided-learning-tutor"
            / "assets"
            / "prerequisite-plan-template.json"
        )
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["prerequisites"].append(dict(plan["prerequisites"][0]))

        errors = validate_prerequisites.validate_plan(plan)

        self.assertTrue(any("duplicates" in error for error in errors))


class PrerequisiteStateTests(unittest.TestCase):
    def test_assessment_sources_and_bridge_attempts_preserve_history(self):
        plan_path = (
            PLUGIN_ROOT
            / "skills"
            / "guided-learning-tutor"
            / "assets"
            / "prerequisite-plan-template.json"
        )
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        state = prerequisite_state.create_state(plan)

        prerequisite_state.append_assessment(
            state,
            "p01",
            "I can name the parts but not explain the transformation.",
            "The causal relation is missing.",
            "gap",
            4,
        )
        prerequisite_state.append_assessment(
            state,
            "p01",
            "The processing step changes an input into an observable result.",
            "The relation is present but the boundary remains fragile.",
            "fragile",
            3,
        )
        prerequisite_state.add_source(
            state,
            "p01",
            "Authoritative system model",
            "Example Standards Body",
            "https://example.com/system-model",
            "official_or_primary",
            "Supports the input-processing-output distinction.",
        )
        prerequisite_state.append_bridge(
            state,
            "p01",
            "A first bridge attempt",
            "One relation still needs revision.",
            "retry",
            3,
        )
        prerequisite_state.append_bridge(
            state,
            "p01",
            "A revised bridge attempt",
            "The boundaries and causal link are now usable.",
            "ready",
            4,
        )

        competency = state["competencies"][0]
        self.assertEqual(
            [item["response"] for item in competency["assessment_attempts"]],
            [
                "I can name the parts but not explain the transformation.",
                "The processing step changes an input into an observable result.",
            ],
        )
        self.assertEqual(len(competency["supplement_sources"]), 1)
        self.assertEqual([item["verdict"] for item in competency["bridge_attempts"]], ["retry", "ready"])
        self.assertEqual(state["status"], "ready_for_main_course")
        self.assertEqual(state["phase"], "ready")
        self.assertIsNone(state["current_prerequisite_id"])


class ScanWikilinksTests(unittest.TestCase):
    def test_unresolved_links_aliases_and_inbox(self):
        with tempfile.TemporaryDirectory() as temporary:
            pack = Path(temporary)
            concepts = pack / "concepts"
            concepts.mkdir()
            (pack / "teaching-guide.md").write_text(
                "提到 [[虚拟内存]] 与 [[TLB|快表]] 和 [[页表#结构]]。\n"
                "```\n[[代码块内不算]]\n```\n",
                encoding="utf-8",
            )
            (concepts / "页表.md").write_text(
                "---\naliases: [page table]\nstatus: grounded\n---\n# 页表\n引用 [[虚拟内存]]。\n",
                encoding="utf-8",
            )
            (concepts / "_inbox.md").write_text(
                "# 收件箱\n- 缺页中断\n- page table\n", encoding="utf-8"
            )

            result = scan_wikilinks.scan(pack, None)

            unresolved = {item["concept"] for item in result["unresolved_links"]}
            self.assertEqual(unresolved, {"虚拟内存", "TLB"})
            self.assertNotIn("代码块内不算", unresolved)
            self.assertEqual(result["inbox_pending"], ["缺页中断"])
            by_concept = {
                item["concept"]: item["found_in"] for item in result["unresolved_links"]
            }
            self.assertIn("concepts/页表.md", by_concept["虚拟内存"])


if __name__ == "__main__":
    unittest.main()
