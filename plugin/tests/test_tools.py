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
mrg_export = load_module("mrg_export")

TEMPLATE_PLAN = PLUGIN_ROOT / "skills" / "guided-learning-tutor" / "assets" / "lesson-plan-template.json"
EXAMPLE_ROOT = PLUGIN_ROOT / "examples" / "project-consensus"


def load_template():
    return json.loads(TEMPLATE_PLAN.read_text(encoding="utf-8"))


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

    def test_code_named_after_sessions_is_not_a_conversation(self):
        self.assertEqual(source_manifest.classify(Path("app/session.py")), "code")
        self.assertEqual(source_manifest.classify(Path("store/session_store.go")), "code")
        self.assertEqual(source_manifest.classify(Path("notes/obsession.md")), "document")

    def test_exported_conversations_are_detected(self):
        self.assertEqual(source_manifest.classify(Path("exports/chat-2026-01.json")), "conversation")
        self.assertEqual(source_manifest.classify(Path("transcripts/2026-01-01.md")), "conversation")
        self.assertEqual(source_manifest.classify(Path("sessions/index.html")), "conversation")
        self.assertEqual(source_manifest.classify(Path("data/session_metrics.csv")), "data")


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
        leaked = plan["sections"][0]["checkpoint"]["criteria"][0]["text"]
        guide = guide_path.read_text(encoding="utf-8") + f"\n参考答案：{leaked}\n"

        errors = validate_lesson.validate_guide(guide, plan)

        self.assertTrue(any("leaks assessment criterion" in error for error in errors))

    def test_guide_leak_check_ignores_cosmetic_rewording(self):
        plan_path = PLUGIN_ROOT / "skills" / "guided-learning-tutor" / "assets" / "lesson-plan-template.json"
        guide_path = PLUGIN_ROOT / "skills" / "guided-learning-tutor" / "assets" / "teaching-guide-template.md"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        leaked = plan["sections"][0]["checkpoint"]["criteria"][0]["text"]
        # Insert punctuation and whitespace inside the criterion; a verbatim check would miss this.
        disguised = "，\n".join(leaked[i : i + 4] for i in range(0, len(leaked), 4))
        guide = guide_path.read_text(encoding="utf-8") + f"\n{disguised}\n"

        errors = validate_lesson.validate_guide(guide, plan)

        self.assertTrue(any("leaks assessment criterion" in error for error in errors))

    def test_guide_leak_check_catches_partial_verbatim_copy(self):
        plan_path = PLUGIN_ROOT / "skills" / "guided-learning-tutor" / "assets" / "lesson-plan-template.json"
        guide_path = PLUGIN_ROOT / "skills" / "guided-learning-tutor" / "assets" / "teaching-guide-template.md"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        criterion = "学习者需要说明输入如何经过处理步骤转化为可观察的输出结果并解释边界条件"
        plan["sections"][0]["checkpoint"]["criteria"] = [{"id": "c1", "text": criterion, "layer": "mechanism"}]
        guide = guide_path.read_text(encoding="utf-8") + "\n提示：" + criterion[8:30] + "……\n"

        errors = validate_lesson.validate_guide(guide, plan)

        self.assertTrue(any("leaks assessment criterion" in error for error in errors))
        self.assertTrue(validate_lesson.criterion_leaked(criterion, validate_lesson.normalize_text(guide)))
        self.assertFalse(validate_lesson.criterion_leaked(criterion, validate_lesson.normalize_text("完全无关的讲义正文")))

    def test_schema_11_rejects_bad_ids_layers_relations_and_criteria(self):
        plan = load_template()
        self.assertEqual(plan["schema_version"], "1.1")
        plan["sections"][0]["concepts"][0]["id"] = "NoDot"
        plan["sections"][0]["concepts"][1]["layer"] = "vibes"
        plan["sections"][0]["concepts"][1]["domain_path"] = []
        plan["relations"][0]["to"] = "learning-design.missing"
        plan["relations"][0]["type"] = "related_to"
        plan["sections"][0]["checkpoint"]["criteria"].append({"id": "c1", "text": "dup", "layer": "fact"})
        plan["sections"][0]["principle"] = "   "

        errors = validate_lesson.validate_plan(plan)

        joined = "\n".join(errors)
        for needle in ("concepts[0].id", "concepts[1].layer", "domain_path", "relations[0].to",
                       "relations[0].type", "criteria[3].id duplicates", "principle"):
            self.assertIn(needle, joined, joined)

    def test_schema_11_concept_id_reused_with_other_name_is_rejected(self):
        plan = load_template()
        section = dict(plan["sections"][0])
        section["id"] = "s02"
        section["depends_on"] = ["s01"]
        section["concepts"] = [dict(plan["sections"][0]["concepts"][0], name="别的名字")]
        plan["sections"][0]["new_problem"] = "下一步"
        plan["sections"].append(section)

        errors = validate_lesson.validate_plan(plan)

        self.assertTrue(any("reused with a different name" in e for e in errors), errors)

    def test_schema_10_rejects_relations(self):
        plan = json.loads((EXAMPLE_ROOT / "lesson-plan.json").read_text(encoding="utf-8"))
        plan["relations"] = []
        errors = validate_lesson.validate_plan(plan)
        self.assertTrue(any("requires schema_version '1.1'" in e for e in errors))

    def test_guide_leaking_principle_is_rejected_and_meaning_is_warned(self):
        plan = load_template()
        guide_path = PLUGIN_ROOT / "skills" / "guided-learning-tutor" / "assets" / "teaching-guide-template.md"
        guide = guide_path.read_text(encoding="utf-8")
        self.assertEqual(validate_lesson.guide_warnings(guide, plan), [])
        leaked = guide + "\n" + plan["sections"][0]["principle"] + "\n" + plan["sections"][0]["meaning"] + "\n"

        errors = validate_lesson.validate_guide(leaked, plan)
        warnings = validate_lesson.guide_warnings(leaked, plan)

        self.assertTrue(any("principle-layer" in e for e in errors), errors)
        self.assertTrue(any("meaning" in w for w in warnings), warnings)

    def test_criteria_texts_handles_both_versions(self):
        self.assertEqual(validate_lesson.criteria_texts({"criteria": ["a", {"id": "c", "text": "b", "layer": "fact"}]}), ["a", "b"])
        self.assertEqual(validate_lesson.criteria_texts(None), [])

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
        self.assertEqual([item["kind"] for item in attempts], ["checkpoint", "checkpoint"])
        self.assertEqual(state["status"], "completed")
        self.assertIsNone(state["current_section_id"])

    @staticmethod
    def _three_section_state():
        plan_path = PLUGIN_ROOT / "skills" / "guided-learning-tutor" / "assets" / "lesson-plan-template.json"
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


class MrgExportTests(unittest.TestCase):
    def test_export_separates_public_and_deep_layers(self):
        plan = load_template()
        public, deep = mrg_export.export(plan)

        self.assertEqual({n["id"] for n in public["nodes"]}, {"learning-design.system-boundary", "learning-design.macro-map"})
        self.assertEqual([e["type"] for e in public["edges"]], ["depends_on"])
        self.assertEqual(deep["nodes"], [])
        self.assertEqual(deep["sections"][0]["principle"], plan["sections"][0]["principle"])
        self.assertEqual([c["id"] for c in deep["sections"][0]["criteria"]], ["c1", "c2", "c3"])
        public_text = json.dumps(public, ensure_ascii=False)
        for hidden in (plan["sections"][0]["principle"], plan["sections"][0]["meaning"], *plan["sections"][0]["tradeoffs"],
                       *(c["text"] for c in plan["sections"][0]["checkpoint"]["criteria"])):
            self.assertNotIn(hidden, public_text)
        self.assertEqual(public["sections"][0]["concept_ids"], [n["id"] for n in public["nodes"]])

    def test_export_moves_rationale_layer_nodes_to_deep_file(self):
        plan = load_template()
        plan["sections"][0]["concepts"][1]["layer"] = "rationale"
        plan["relations"][0]["layer"] = "principle"
        public, deep = mrg_export.export(plan)
        self.assertEqual([n["id"] for n in public["nodes"]], ["learning-design.system-boundary"])
        self.assertEqual([n["id"] for n in deep["nodes"]], ["learning-design.macro-map"])
        self.assertEqual(public["edges"], [])
        self.assertEqual(len(deep["edges"]), 1)

    def test_export_handles_schema_10_with_generated_ids_and_merged_mentions(self):
        plan = json.loads((EXAMPLE_ROOT / "lesson-plan.json").read_text(encoding="utf-8"))
        public, deep = mrg_export.export(plan)
        self.assertEqual(public["source_schema_version"], "1.0")
        ids = [n["id"] for n in public["nodes"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(i.startswith("weave-consensus-core.") for i in ids))
        self.assertTrue(all(n["layer"] == "mechanism" for n in public["nodes"]))
        self.assertEqual(len(deep["sections"]), len(plan["sections"]))
        self.assertTrue(all(c["id"].startswith("c") for c in deep["sections"][0]["criteria"]))

    def test_slugify_keeps_non_ascii(self):
        self.assertEqual(mrg_export.slugify("  可调用的 心智模型 "), "可调用的-心智模型")
        self.assertEqual(mrg_export.slugify("Chain of Trust!"), "chain-of-trust")


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

    def test_block_list_aliases_and_inline_code_are_handled(self):
        with tempfile.TemporaryDirectory() as temporary:
            pack = Path(temporary)
            concepts = pack / "concepts"
            concepts.mkdir()
            (concepts / "缓存.md").write_text(
                "---\ntitle: 缓存\naliases:\n  - cache\n  - \"Cache Layer\"\nstatus: grounded\n---\n# 缓存\n",
                encoding="utf-8",
            )
            (pack / "teaching-guide.md").write_text(
                "正文提到 [[cache]] 与 [[Cache Layer]]，还有 [[命中率]]。\n"
                "行内代码 `[[不算链接]]` 不应被扫描。\n"
                "~~~\n[[波浪围栏内不算]]\n~~~\n"
                "````md\n```\n[[嵌套围栏内不算]]\n```\n````\n",
                encoding="utf-8",
            )

            result = scan_wikilinks.scan(pack, None)

            self.assertEqual({"cache layer", "cache", "缓存"}, set(result["known_notes"]))
            unresolved = {item["concept"] for item in result["unresolved_links"]}
            self.assertEqual(unresolved, {"命中率"})


if __name__ == "__main__":
    unittest.main()
