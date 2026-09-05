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
store_init = load_module("store_init")
comparator = load_module("comparator")
lrg_record = load_module("lrg_record")
index_match = load_module("index_match")
learner_state_build = load_module("learner_state_build")
review_pool = load_module("review_pool")
score_pack = load_module("score_pack", PLUGIN_ROOT / "evals")

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


class KnowledgeStoreTests(unittest.TestCase):
    def _store_with_template(self, root: Path) -> Path:
        store = root / "store"
        store_init.init_store(store, ["学习设计"])
        store_init.register_lesson(store, TEMPLATE_PLAN)
        public, deep = mrg_export.export(load_template())
        mrg_export.write_json(store / "mrg" / "sample-guided-lesson.json", public)
        mrg_export.write_json(store / "mrg" / "sample-guided-lesson.deep.json", deep)
        return store

    def test_init_creates_layout_and_refuses_reinit(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = Path(temporary) / "store"
            data = store_init.init_store(store, ["计算机科学", " "])
            self.assertEqual(data["domain_roots"], ["计算机科学"])
            for name in ("concepts", "mrg", "lrg", "exports"):
                self.assertTrue((store / name).is_dir())
            self.assertTrue((store / "concepts" / "index.json").is_file())
            with self.assertRaises(ValueError):
                store_init.init_store(store, [])
            store_init.register_lesson(store, TEMPLATE_PLAN)
            store_init.register_lesson(store, TEMPLATE_PLAN)  # idempotent
            self.assertEqual(len(store_init.load_store(store)["lessons"]), 1)

    def test_comparator_classifies_conflict_missing_partial_and_beyond(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self._store_with_template(Path(temporary))
            reference = comparator.load_reference(store, "sample-guided-lesson")
            extraction = json.loads((PLUGIN_ROOT / "skills" / "guided-learning-tutor" / "assets" / "extraction-template.json").read_text(encoding="utf-8"))
            extraction["concepts"].append({"ref": "量子纠缠", "status": "correct"})

            result = comparator.compare(reference, "s01", extraction)
            diff = result["diff"]

            self.assertEqual(diff["missing"], [])  # both section concepts mentioned (one via its name)
            self.assertEqual([c["id"] for c in diff["partial"]], ["learning-design.system-boundary"])
            kinds = sorted(c["kind"] for c in diff["conflict"])
            self.assertEqual(kinds, ["proposition", "relation"])
            self.assertEqual(diff["beyond_reference"][0]["ref"], "量子纠缠")
            self.assertEqual(diff["unresolved_refs"], ["量子纠缠"])
            self.assertEqual(result["feedback_priority"][0], "conflict:high_confidence")
            self.assertTrue(all(p["id"].startswith("p-") for p in result["propositions"]))

    def test_comparator_downgrades_conflicts_against_pedagogical_inference_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self._store_with_template(Path(temporary))
            public = json.loads((store / "mrg" / "sample-guided-lesson.json").read_text(encoding="utf-8"))
            for node in public["nodes"]:
                for ref in node["source_refs"]:
                    ref["support"] = "pedagogical_inference"
            for edge in public["edges"]:
                for ref in edge["source_refs"]:
                    ref["support"] = "pedagogical_inference"
            (store / "mrg" / "sample-guided-lesson.json").write_text(json.dumps(public, ensure_ascii=False), encoding="utf-8")
            reference = comparator.load_reference(store, "sample-guided-lesson")
            extraction = {"extracted_by": "model", "concepts": [], "relations": [],
                          "propositions": [{"text": "一条错误主张", "status": "wrong", "concept_refs": ["宏观地图"]}]}

            diff = comparator.compare(reference, "s01", extraction)["diff"]

            self.assertEqual(diff["conflict"], [])
            self.assertEqual(diff["weak_reference"][0]["kind"], "proposition")
            self.assertEqual(sorted(diff["missing"]), ["learning-design.macro-map", "learning-design.system-boundary"])

    def test_comparator_rejects_unknown_status_and_section(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self._store_with_template(Path(temporary))
            reference = comparator.load_reference(store, "sample-guided-lesson")
            with self.assertRaises(ValueError):
                comparator.compare(reference, "s01", {"concepts": [{"ref": "x", "status": "meh"}]})
            with self.assertRaises(ValueError):
                comparator.compare(reference, "s99", {})

    def test_lrg_append_is_append_only_mirrors_progress_and_never_prints_response(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = self._store_with_template(root)
            reference = comparator.load_reference(store, "sample-guided-lesson")
            extraction = {"extracted_by": "model", "concepts": [{"ref": "宏观地图", "status": "correct"}], "relations": [], "propositions": []}
            comparison = comparator.compare(reference, "s01", extraction)
            secret = "这是不该被展示的原始回答"
            for number, verdict in ((1, "partial"), (2, "mastered")):
                event = lrg_record.build_event(
                    lesson_id="sample-guided-lesson", section_id="s01", kind="checkpoint", attempt_number=number,
                    response=secret, feedback="fb", verdict=verdict, confidence=3, criteria_met=["c1"],
                    depth_reached="mechanism", extraction=extraction, comparison=comparison, elapsed_seconds=120,
                )
                lrg_record.append_event(store, "sample-guided-lesson", event)
            events = lrg_record.read_events(store, "sample-guided-lesson")
            self.assertEqual([e["attempt_number"] for e in events], [1, 2])
            self.assertEqual(events[0]["evidence_tier"], "immediate")
            self.assertEqual(events[0]["diff"]["missing"], ["learning-design.system-boundary"])
            self.assertEqual(lrg_record.evidence_tier("review"), "delayed")
            self.assertEqual(lrg_record.evidence_tier("transfer"), "transfer")
            with self.assertRaises(ValueError):
                lrg_record.build_event(lesson_id="l", section_id="s", kind="quiz", attempt_number=1, response="", feedback="",
                                       verdict="partial", confidence=None, criteria_met=[], depth_reached=None,
                                       extraction=None, comparison=None, elapsed_seconds=None)

            import io, contextlib, argparse
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                lrg_record.command_show(argparse.Namespace(store=store, lesson_id="sample-guided-lesson"))
                store_init.command_show(argparse.Namespace(store=store))
            self.assertNotIn(secret, buffer.getvalue())
            self.assertIn("2 attempts", buffer.getvalue())


class _StoreHelpers:
    def _store(self, root: Path) -> Path:
        store = root / "store"
        store_init.init_store(store, [])
        store_init.register_lesson(store, TEMPLATE_PLAN)
        public, deep = mrg_export.export(load_template())
        mrg_export.write_json(store / "mrg" / "sample-guided-lesson.json", public)
        mrg_export.write_json(store / "mrg" / "sample-guided-lesson.deep.json", deep)
        index = index_match.load_index(store)
        index_match.register_nodes(index, public["nodes"] + deep["nodes"], "sample-guided-lesson")
        index_match.save_index(store, index)
        return store

    def _append(self, store, at, kind, verdict, confidence=None, depth=None, props=None, section="s01"):
        event = lrg_record.build_event(
            lesson_id="sample-guided-lesson", section_id=section, kind=kind, attempt_number=1, response="r", feedback="",
            verdict=verdict, confidence=confidence, criteria_met=[], depth_reached=depth, extraction=None,
            comparison={"propositions": props or [], "diff": {"conflict": []}, "feedback_priority": []}, elapsed_seconds=None,
        )
        event["at"] = at
        lrg_record.append_event(store, "sample-guided-lesson", event)



class RegistryAndLearnerStateTests(_StoreHelpers, unittest.TestCase):
    def test_register_and_recall_without_auto_merge(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self._store(Path(temporary))
            index = index_match.load_index(store)
            self.assertEqual(set(index["concepts"]), {"learning-design.system-boundary", "learning-design.macro-map"})
            self.assertEqual(index["alias_index"]["macro map"], "learning-design.macro-map")

            # second lesson reuses one id (appearance appended) and tries to claim an alias owned by another id
            other = [{"id": "learning-design.macro-map", "name": "宏观地图", "aliases": ["big picture"], "domain_path": ["学习设计"], "layer": "mechanism", "section_ids": ["s01"]},
                     {"id": "cs.other.thing", "name": "别的", "aliases": ["系统边界"], "domain_path": ["计算机科学"], "layer": "fact", "section_ids": ["s02"]}]
            report = index_match.register_nodes(index, other, "lesson-2")
            self.assertEqual(report["created"], ["cs.other.thing"])
            self.assertEqual(report["updated"], ["learning-design.macro-map"])
            self.assertEqual(report["alias_conflicts"][0]["alias"], "系统边界")
            self.assertEqual(index["alias_index"]["系统边界"], "learning-design.system-boundary")  # not re-pointed
            self.assertEqual(len(index["concepts"]["learning-design.macro-map"]["appearances"]), 2)
            self.assertIn("big picture", index["concepts"]["learning-design.macro-map"]["aliases"])

            results = index_match.recall(index, [{"name": "MACRO MAP"}, {"name": "未知概念"}, {"name": "系统边界", "aliases": ["big picture"]}])
            self.assertEqual(results[0]["decision_needed"], "confirm_same")
            self.assertEqual(results[0]["matches"][0]["id"], "learning-design.macro-map")
            self.assertEqual(results[1]["decision_needed"], "none")
            self.assertEqual(results[2]["decision_needed"], "disambiguate")
            with self.assertRaises(ValueError):
                index_match.recall(index, [{"aliases": ["x"]}])

    def test_learner_state_freshness_tiers_depth_and_error_pool(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as temporary:
            store = self._store(Path(temporary))
            prop = {"id": "p-1", "text": "去主体化的错误主张", "status": "wrong", "concept_ids": ["learning-design.macro-map"], "confidence_high": True}
            self._append(store, "2026-01-01T10:00:00Z", "checkpoint", "retry", confidence=5, depth="fact", props=[prop])
            self._append(store, "2026-01-01T11:00:00Z", "checkpoint", "mastered", confidence=2, depth="mechanism")
            self._append(store, "2026-01-20T10:00:00Z", "review", "mastered", confidence=4, depth="rationale")

            state = learner_state_build.build(store, now=datetime(2026, 1, 25, tzinfo=timezone.utc))
            macro = state["concepts"]["learning-design.macro-map"]
            self.assertEqual(macro["attempts"], 3)
            self.assertEqual(macro["evidence_tier"], "delayed")
            self.assertEqual(macro["stability"], 2)          # two distinct success days
            self.assertEqual(macro["freshness"], "fresh")     # window 14 days, 5 days old
            self.assertEqual(macro["depth_max"], "rationale")
            self.assertEqual(macro["depth_latest"], "rationale")
            self.assertEqual(macro["error_propositions"][0]["text"], "去主体化的错误主张")
            self.assertEqual(macro["calibration"], {"overconfident": 1, "underconfident": 1})
            self.assertAlmostEqual(macro["mastery_estimate"], 0.7)
            boundary = state["concepts"]["learning-design.system-boundary"]
            self.assertEqual(boundary["error_propositions"], [])  # proposition only referenced macro-map

            stale = learner_state_build.build(store, now=datetime(2026, 3, 1, tzinfo=timezone.utc))
            self.assertEqual(stale["concepts"]["learning-design.macro-map"]["freshness"], "stale")
            self.assertAlmostEqual(stale["concepts"]["learning-design.macro-map"]["mastery_estimate"], 0.35)

    def test_immediate_only_evidence_is_unknown(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as temporary:
            store = self._store(Path(temporary))
            self._append(store, "2026-01-01T10:00:00Z", "checkpoint", "mastered", depth="mechanism")
            state = learner_state_build.build(store, now=datetime(2026, 1, 2, tzinfo=timezone.utc))
            macro = state["concepts"]["learning-design.macro-map"]
            self.assertEqual(macro["evidence_tier"], "immediate")
            self.assertEqual(macro["freshness"], "unknown")
            self.assertAlmostEqual(macro["mastery_estimate"], 0.08)
            self.assertEqual(learner_state_build.freshness_window(1).days, 7)
            self.assertEqual(learner_state_build.freshness_window(4).days, 56)
            self.assertEqual(learner_state_build.freshness_window(9).days, 180)


class VariantAndReviewTests(_StoreHelpers, unittest.TestCase):
    def test_prerequisite_lookup_maps_freshness_to_action(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as temporary:
            store = self._store(Path(temporary))
            self._append(store, "2026-01-20T10:00:00Z", "review", "mastered", depth="mechanism")
            state = learner_state_build.build(store, now=datetime(2026, 1, 25, tzinfo=timezone.utc))
            store_init.atomic_write(store / "learner-state.json", state)
            plan = {"prerequisites": [{"id": "p01", "name": "macro map"}, {"id": "p02", "name": "哈希函数"}]}

            decisions = index_match.prerequisite_plan_lookup(index_match.load_index(store), plan, index_match.load_learner_state(store))

            self.assertEqual([(d["prerequisite_id"], d["action"]) for d in decisions], [("p01", "variant"), ("p02", "diagnose")])
            self.assertEqual(decisions[0]["concept_id"], "learning-design.macro-map")
            stale = learner_state_build.build(store, now=datetime(2026, 6, 1, tzinfo=timezone.utc))
            decisions = index_match.prerequisite_plan_lookup(index_match.load_index(store), plan, stale["concepts"])
            self.assertEqual(decisions[0]["action"], "variant_then_diagnose")
            with self.assertRaises(ValueError):
                index_match.prerequisite_plan_lookup(index_match.load_index(store), {}, {})

    def test_review_pool_orders_wrong_and_stale_first_and_respects_completed_sections(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as temporary:
            store = self._store(Path(temporary))
            wrong = {"id": "p-w", "text": "错误主张", "status": "wrong", "concept_ids": ["learning-design.macro-map"], "confidence_high": False}
            partial = {"id": "p-p", "text": "不完整主张", "status": "partial", "concept_ids": ["learning-design.system-boundary"], "confidence_high": False}
            self._append(store, "2026-01-01T10:00:00Z", "checkpoint", "partial", props=[partial])
            self._append(store, "2026-01-02T10:00:00Z", "checkpoint", "retry", props=[wrong])
            state = learner_state_build.build(store, now=datetime(2026, 1, 3, tzinfo=timezone.utc))

            items = review_pool.pool(state, "sample-guided-lesson", None, None, 5)
            self.assertEqual([i["id"] for i in items], ["p-w", "p-p"])
            self.assertEqual(items[0]["claim"], "错误主张")
            self.assertNotIn("response", json.dumps(items))
            self.assertEqual(review_pool.pool(state, "sample-guided-lesson", None, {"s02"}, 5), [])
            self.assertEqual(review_pool.pool(state, "sample-guided-lesson", ["learning-design.system-boundary"], None, 5)[0]["id"], "p-p")
            self.assertEqual(len(review_pool.pool(state, None, None, None, 1)), 1)


class EvalScoringTests(unittest.TestCase):
    def test_scores_example_pack_with_locator_check_and_expectations(self):
        metrics = score_pack.build_metrics(EXAMPLE_ROOT, PLUGIN_ROOT.parent, {"sections": [4, 9], "max_concepts_per_section": 4, "min_relations": 0})
        self.assertEqual(metrics["validator_errors"], 0)
        self.assertEqual(metrics["sections"], 8)
        self.assertEqual(metrics["support"], {"explicit": 18})
        self.assertEqual(metrics["layers"], {"mechanism": 24})
        self.assertGreater(metrics["locator_checked"], 0)
        self.assertIsNotNone(metrics["locator_hit_rate"])
        self.assertTrue(all(metrics["expectations"].values()), metrics["expectations"])
        self.assertTrue(score_pack.locator_hit("## 2. 项目要解决的问题 / 第一段", "…\n## 2. 项目要解决的问题\n…"))
        self.assertFalse(score_pack.locator_hit("p. 42", "no page markers here"))

    def test_scores_template_pack_and_diffs_against_baseline(self):
        with tempfile.TemporaryDirectory() as temporary:
            pack = Path(temporary) / "pack"
            pack.mkdir()
            assets = PLUGIN_ROOT / "skills" / "guided-learning-tutor" / "assets"
            (pack / "lesson-plan.json").write_text(TEMPLATE_PLAN.read_text(encoding="utf-8"), encoding="utf-8")
            (pack / "teaching-guide.md").write_text((assets / "teaching-guide-template.md").read_text(encoding="utf-8"), encoding="utf-8")
            metrics = score_pack.build_metrics(pack, None, None)
            self.assertEqual(metrics["relations"], 1)
            self.assertEqual(metrics["layers"], {"fact": 1, "mechanism": 1})
            self.assertIsNone(metrics["locator_hit_rate"])
            changed = dict(metrics, sections=metrics["sections"] + 1)
            lines = score_pack.diff_against({"build": metrics}, {"build": changed})
            self.assertEqual(lines, ["  build.sections: 1 → 2"])

    def test_teach_metrics_from_store_log(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = Path(temporary) / "store"
            store_init.init_store(store, [])
            for number, (kind, verdict, elapsed) in enumerate([("checkpoint", "partial", 200), ("checkpoint", "mastered", 100), ("review", "mastered", 50)], start=1):
                event = lrg_record.build_event(
                    lesson_id="l", section_id="s01", kind=kind, attempt_number=number, response="r", feedback="",
                    verdict=verdict, confidence=None, criteria_met=[], depth_reached="mechanism", extraction=None,
                    comparison={"propositions": [], "diff": {"conflict": [{"kind": "proposition", "id": "p", "confidence_high": True}]}, "feedback_priority": []},
                    elapsed_seconds=elapsed,
                )
                lrg_record.append_event(store, "l", event)
            t = score_pack.teach_metrics(store, "l")
            self.assertEqual(t["attempts"], 3)
            self.assertEqual(t["median_checkpoint_elapsed_s"], 150)
            self.assertEqual(t["conflicts_per_attempt"], 1.0)
            self.assertEqual(t["high_confidence_conflict_share"], 1.0)
            self.assertEqual(score_pack.teach_metrics(store, "missing"), {"attempts": 0})


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
