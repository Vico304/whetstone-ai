from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = PLUGIN_ROOT / "skills" / "learn" / "scripts"
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
lesson_section = load_module("lesson_section")
next_step = load_module("next_step")
review_outline = load_module("review_outline")
cards = load_module("cards")
diagram = load_module("diagram")
outline_status = load_module("outline_status")
store_sync = load_module("store_sync")
score_pack = load_module("score_pack", PLUGIN_ROOT / "evals")
survey_materials = load_module("survey_materials")

TEMPLATE_PLAN = PLUGIN_ROOT / "skills" / "learn" / "assets" / "lesson-plan-template.json"
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
    def test_template_is_valid_and_matches_outline_and_units(self):
        assets = PLUGIN_ROOT / "skills" / "learn" / "assets"
        plan = load_template()

        self.assertEqual(plan["schema_version"], "1.5")
        self.assertEqual(validate_lesson.validate_plan(plan), [])
        self.assertEqual(validate_lesson.collect_warnings(plan), [])
        self.assertEqual(validate_lesson.validate_outline((assets / "outline-template.md").read_text(encoding="utf-8"), plan), [])
        errors, warnings = validate_lesson.validate_units(assets / "units-template", plan)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_project_consensus_example_is_valid_and_traceable(self):
        example_root = PLUGIN_ROOT / "examples" / "project-consensus"
        plan = json.loads((example_root / "lesson-plan.json").read_text(encoding="utf-8"))
        guide = (example_root / "teaching-guide.md").read_text(encoding="utf-8")
        manifest = json.loads((example_root / "sources.json").read_text(encoding="utf-8"))
        paths = validate_lesson.manifest_paths(manifest)

        self.assertEqual(validate_lesson.validate_plan(plan, paths), [])
        self.assertEqual(validate_lesson.validate_guide(guide, plan), [])

    def test_forward_dependency_is_rejected(self):
        plan_path = PLUGIN_ROOT / "skills" / "learn" / "assets" / "lesson-plan-template.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["sections"][0]["depends_on"] = ["s02"]

        errors = validate_lesson.validate_plan(plan)

        self.assertTrue(any("before it is available" in error for error in errors))

    def test_self_dependency_is_rejected(self):
        plan_path = PLUGIN_ROOT / "skills" / "learn" / "assets" / "lesson-plan-template.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["sections"][0]["depends_on"] = ["s01"]

        errors = validate_lesson.validate_plan(plan)

        self.assertTrue(any("before it is available" in error for error in errors))

    def test_guide_leaking_criteria_is_rejected(self):
        plan_path = PLUGIN_ROOT / "skills" / "learn" / "assets" / "lesson-plan-template.json"
        guide_path = PLUGIN_ROOT / "skills" / "learn" / "assets" / "units-template" / "s01.md"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        leaked = plan["sections"][0]["checkpoint"]["criteria"][0]["text"]
        guide = guide_path.read_text(encoding="utf-8") + f"\n参考答案：{leaked}\n"

        errors = validate_lesson.validate_guide(guide, plan)

        self.assertTrue(any("leaks assessment criterion" in error for error in errors))

    def test_guide_leak_check_ignores_cosmetic_rewording(self):
        plan_path = PLUGIN_ROOT / "skills" / "learn" / "assets" / "lesson-plan-template.json"
        guide_path = PLUGIN_ROOT / "skills" / "learn" / "assets" / "units-template" / "s01.md"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        leaked = plan["sections"][0]["checkpoint"]["criteria"][0]["text"]
        # Insert punctuation and whitespace inside the criterion; a verbatim check would miss this.
        disguised = "，\n".join(leaked[i : i + 4] for i in range(0, len(leaked), 4))
        guide = guide_path.read_text(encoding="utf-8") + f"\n{disguised}\n"

        errors = validate_lesson.validate_guide(guide, plan)

        self.assertTrue(any("leaks assessment criterion" in error for error in errors))

    def test_guide_leak_check_catches_partial_verbatim_copy(self):
        plan_path = PLUGIN_ROOT / "skills" / "learn" / "assets" / "lesson-plan-template.json"
        guide_path = PLUGIN_ROOT / "skills" / "learn" / "assets" / "units-template" / "s01.md"
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
        guide_path = PLUGIN_ROOT / "skills" / "learn" / "assets" / "units-template" / "s01.md"
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
        plan = json.loads((EXAMPLE_ROOT / "lesson-plan.json").read_text(encoding="utf-8"))  # 1.0: every concept counts
        plan["sections"][0]["concepts"] = [{"name": f"概念{i}", "explanation": "占位解释"} for i in range(5)]
        warnings = validate_lesson.collect_warnings(plan)
        self.assertTrue(any("concepts" in warning for warning in warnings))
        self.assertEqual(validate_lesson.collect_warnings({"sections": []}), [])

    def test_schema_12_role_aware_warnings_and_rules(self):
        plan = load_template()
        section = plan["sections"][0]
        core = section["concepts"][0]
        section["concepts"] = [dict(core, id=f"learning-design.c{i}", name=f"核心{i}", role="core") for i in range(5)] + [
            dict(core, id=f"learning-design.s{i}", name=f"配角{i}", role="supporting") for i in range(7)
        ] + [dict(core, id="learning-design.long", name="长列出", role="listed", explanation="机" * 250)]
        plan["relations"] = []
        warnings = validate_lesson.collect_warnings(plan)
        self.assertTrue(any("5 core concepts" in w and "do not drop" in w for w in warnings), warnings)
        self.assertTrue(any("7 supporting" in w for w in warnings), warnings)
        self.assertTrue(any("'listed' but its explanation is long" in w for w in warnings), warnings)
        self.assertEqual(validate_lesson.validate_plan(plan), [])

        bad = load_template()
        bad["mode"] = "sprint"
        del bad["outline_confirmed_at"]
        bad["sections"][0]["concepts"][0]["role"] = "hero"
        bad["sections"][0]["concepts"][0]["check"] = {"prompt": "x", "hint": "y", "criteria": [{"id": "k", "text": "t", "layer": "fact"}]}
        bad["deferred"] = [{"type": "section", "id": "s99", "reason": "r"}, {"type": "concept", "id": "learning-design.macro-map"}]
        bad["coverage"] = [{"path": "a.md", "heading": "H", "disposition": "core"}, {"path": "a.md", "heading": "I", "disposition": "excluded"}]
        errors = validate_lesson.validate_plan(bad)
        joined = "\n".join(errors)
        for needle in ("root.mode", "outline_confirmed_at", "concepts[0].role", "check is only allowed on supporting",
                       "deferred[0].id 's99'", "deferred[1].reason", "coverage[0].section_id", "coverage[1].reason"):
            self.assertIn(needle, joined, joined)

        old = json.loads((EXAMPLE_ROOT / "lesson-plan.json").read_text(encoding="utf-8"))
        old["mode"] = "full"
        self.assertTrue(any("requires schema_version '1.2'" in e for e in validate_lesson.validate_plan(old)))

    def test_external_url_refs_bypass_manifest_and_need_external_support(self):
        plan = load_template()
        plan["sections"][0]["source_refs"].append({"path": "https://example.com/spec", "locator": "§3", "support": "external", "note": "上游说明"})
        self.assertEqual(validate_lesson.validate_plan(plan, {"examples/source.md"}), [])
        plan["sections"][0]["source_refs"][-1]["support"] = "explicit"
        errors = validate_lesson.validate_plan(plan, {"examples/source.md"})
        self.assertTrue(any("URL path must carry support 'external'" in e for e in errors), errors)

    def test_supporting_without_check_and_placeholder_confirmation_warn(self):
        plan = load_template()
        del plan["sections"][0]["concepts"][2]["check"]
        plan["outline_confirmed_at"] = "2026-09-07T00:00:00+08:00"
        warnings = validate_lesson.collect_warnings(plan)
        self.assertTrue(any("has no check question" in w for w in warnings), warnings)
        self.assertTrue(any("placeholder" in w for w in warnings), warnings)
        self.assertEqual(validate_lesson.validate_plan(plan), [])

    def test_coverage_against_source_headings(self):
        plan = load_template()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "examples").mkdir()
            (root / "examples" / "source.md").write_text("## Architecture\n\n## Course ordering\n\n## Appendix\n\n## Deployment notes\n", encoding="utf-8")
            self.assertEqual(validate_lesson.validate_coverage_against_sources(plan, root), [])
            (root / "examples" / "source.md").write_text("## Architecture\n\n## Interrupts and page faults\n", encoding="utf-8")
            (root / "examples" / "source.adoc").write_text("= Spec\n\n== Timer interrupts\n", encoding="utf-8")
            plan["coverage"].append({"path": "examples/source.adoc", "heading": "Spec", "disposition": "excluded", "reason": "标题页"})
            errors = validate_lesson.validate_coverage_against_sources(plan, root)
            self.assertTrue(any("Timer interrupts" in e for e in errors), errors)
            self.assertTrue(any("Interrupts and page faults" in e for e in errors), errors)
        self.assertEqual(validate_lesson.source_headings.__name__, "source_headings")

    def test_outline_and_units_validation_catch_missing_and_leaks(self):
        assets = PLUGIN_ROOT / "skills" / "learn" / "assets"
        plan = load_template()
        outline = (assets / "outline-template.md").read_text(encoding="utf-8")
        stripped = outline.replace("附录", "").replace("完整（full）", "").replace("mode: full", "mode: ")
        errors = validate_lesson.validate_outline(stripped, plan)
        self.assertTrue(any("does not list concept '附录'" in e for e in errors), errors)
        self.assertTrue(any("learning mode" in e for e in errors), errors)
        leaked = outline + "\n" + plan["sections"][0]["meaning"] + "\n" + plan["sections"][0]["concepts"][2]["check"]["criteria"][0]["text"]
        errors = validate_lesson.validate_outline(leaked, plan)
        self.assertTrue(any("rationale-layer meaning" in e for e in errors), errors)
        self.assertTrue(any("supporting check criterion" in e for e in errors), errors)

        with tempfile.TemporaryDirectory() as temporary:
            units = Path(temporary)
            errors, _ = validate_lesson.validate_units(units, plan)
            self.assertTrue(any("missing unit document units/s01.md" in e for e in errors))
            text = (assets / "units-template" / "s01.md").read_text(encoding="utf-8")
            (units / "s01.md").write_text(text.replace("问题链", "") + plan["sections"][0]["tradeoffs"][0], encoding="utf-8")
            errors, warnings = validate_lesson.validate_units(units, plan)
            self.assertTrue(any("does not mention concept '问题链'" in e for e in errors), errors)
            self.assertTrue(any("rationale-layer tradeoff" in w for w in warnings), warnings)
            plan["deferred"] = [{"type": "section", "id": "s01", "reason": "快速模式略过"}]
            errors, warnings = validate_lesson.validate_units(units, plan)
            self.assertEqual(errors, [])
            self.assertTrue(any("deferred" in w for w in warnings))


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
            course = Path(temporary) / "my course"
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


class OrphanConceptTests(unittest.TestCase):
    def test_orphan_core_concepts_are_counted_not_rejected(self):
        plan = load_template()
        self.assertEqual(validate_lesson.orphan_concepts(plan), {"orphans": [], "total": 2})
        plan["sections"][0]["concepts"].append({"id": "learning-design.lonely", "name": "孤概念", "explanation": "没有关系的核心概念",
                                                "layer": "mechanism", "role": "core", "domain_path": ["学习设计"],
                                                "source_refs": plan["sections"][0]["source_refs"]})
        self.assertEqual(validate_lesson.orphan_concepts(plan)["orphans"], ["learning-design.lonely"])
        self.assertEqual(validate_lesson.validate_plan(plan), [])


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


class MrgExportTests(unittest.TestCase):
    def test_export_separates_public_and_deep_layers(self):
        plan = load_template()
        public, deep = mrg_export.export(plan)

        self.assertEqual({n["id"] for n in public["nodes"]},
                         {"learning-design.system-boundary", "learning-design.macro-map", "learning-design.problem-chain", "learning-design.appendix"})
        self.assertEqual({n["id"]: n["role"] for n in public["nodes"]}["learning-design.appendix"], "listed")
        self.assertEqual(public["sections"][0]["core_concept_ids"], ["learning-design.system-boundary", "learning-design.macro-map"])
        self.assertEqual(public["sections"][0]["supporting_concept_ids"], ["learning-design.problem-chain"])
        self.assertEqual(deep["sections"][0]["supporting_checks"][0]["concept_id"], "learning-design.problem-chain")
        self.assertEqual([e["type"] for e in public["edges"]], ["depends_on"])
        self.assertEqual(deep["nodes"], [])
        self.assertEqual(deep["sections"][0]["principle"], plan["sections"][0]["principle"])
        self.assertEqual([c["id"] for c in deep["sections"][0]["criteria"]], ["c1", "c2", "c3"])
        public_text = json.dumps(public, ensure_ascii=False)
        for hidden in (plan["sections"][0]["principle"], plan["sections"][0]["meaning"], *plan["sections"][0]["tradeoffs"],
                       *(c["text"] for c in plan["sections"][0]["checkpoint"]["criteria"]),
                       *(c["text"] for c in plan["sections"][0]["concepts"][2]["check"]["criteria"])):
            self.assertNotIn(hidden, public_text)
        self.assertEqual(public["sections"][0]["concept_ids"], [n["id"] for n in public["nodes"]])

    def test_export_moves_rationale_layer_nodes_to_deep_file(self):
        plan = load_template()
        plan["sections"][0]["concepts"][1]["layer"] = "rationale"
        plan["relations"][0]["layer"] = "principle"
        public, deep = mrg_export.export(plan)
        self.assertEqual([n["id"] for n in public["nodes"]], ["learning-design.system-boundary", "learning-design.problem-chain", "learning-design.appendix"])
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
            extraction = json.loads((PLUGIN_ROOT / "skills" / "learn" / "assets" / "extraction-template.json").read_text(encoding="utf-8"))
            extraction["concepts"].append({"ref": "量子纠缠", "status": "correct"})

            result = comparator.compare(reference, "s01", extraction)
            diff = result["diff"]

            self.assertEqual(diff["missing"], [])  # both core concepts mentioned (one via its name)
            self.assertEqual(diff["unmentioned_supporting"], ["learning-design.problem-chain"])
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
            self.assertNotIn("evidence_tier", events[0])  # derived per concept at build time, not stored per event
            self.assertEqual((events[0]["elapsed_seconds"], events[0]["elapsed_source"]), (120, "model"))
            self.assertEqual(events[0]["diff"]["missing"], ["learning-design.system-boundary"])
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
            self.assertEqual(set(index["concepts"]), {"learning-design.system-boundary", "learning-design.macro-map", "learning-design.problem-chain", "learning-design.appendix"})
            self.assertEqual(index["concepts"]["learning-design.appendix"]["appearances"][0]["role"], "listed")
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

    def test_evidence_tier_comes_from_the_interval_not_the_kind(self):
        from datetime import datetime, timedelta, timezone
        utc, cst = timezone.utc, timezone(timedelta(hours=8))
        with tempfile.TemporaryDirectory() as temporary:
            store = self._store(Path(temporary))
            self._append(store, "2026-09-12T12:00:00Z", "checkpoint", "mastered", depth="mechanism")
            self._append(store, "2026-09-12T12:30:00Z", "review", "mastered", depth="mechanism")   # same sitting
            self._append(store, "2026-09-12T12:40:00Z", "final", "mastered", depth="mechanism")    # same sitting
            state = learner_state_build.build(store, now=datetime(2026, 9, 13, tzinfo=utc), tz=cst)
            macro = state["concepts"]["learning-design.macro-map"]
            self.assertEqual((macro["evidence_tier"], macro["freshness"]), ("immediate", "unknown"))
            self.assertEqual(macro["stability"], 1)
            # 20 h 51 min later: an earlier local day (Sept 12 evening -> Sept 13 afternoon in UTC+8) and > 8 h
            self._append(store, "2026-09-13T09:16:00Z", "variant", "mastered", depth="mechanism")
            state = learner_state_build.build(store, now=datetime(2026, 9, 13, 10, tzinfo=utc), tz=cst)
            macro = state["concepts"]["learning-design.macro-map"]
            self.assertEqual((macro["evidence_tier"], macro["freshness"], macro["stability"]), ("delayed", "fresh", 2))
            # a transfer question after a real interval counts as transfer; a checkpoint never does
            self._append(store, "2026-09-15T09:00:00Z", "transfer", "mastered", depth="rationale")
            state = learner_state_build.build(store, now=datetime(2026, 9, 16, tzinfo=utc), tz=cst)
            self.assertEqual(state["concepts"]["learning-design.macro-map"]["evidence_tier"], "transfer")
            self.assertIn("earlier local day", state["tier_rule"])
            self._append(store, "2026-09-17T09:00:00Z", "checkpoint", "mastered", depth="rationale")
            state = learner_state_build.build(store, now=datetime(2026, 9, 17, 10, tzinfo=utc), tz=cst)
            self.assertEqual(state["concepts"]["learning-design.macro-map"]["evidence_tier"], "immediate")
        # the day boundary is local: 18:00 -> 04:00 next day in UTC+8 is a night apart, but one UTC day (10:00 -> 20:00)
        prev, cur = datetime(2026, 9, 12, 10, tzinfo=utc), datetime(2026, 9, 12, 20, tzinfo=utc)
        self.assertTrue(learner_state_build.is_delayed(prev, cur, cst))
        self.assertFalse(learner_state_build.is_delayed(prev, cur, utc))
        self.assertFalse(learner_state_build.is_delayed(prev, prev + timedelta(hours=1), cst))  # midnight straddled, no night
        self.assertEqual(learner_state_build.tier_for("review", None, cur, cst), "immediate")
        self.assertEqual(learner_state_build.parse_offset("+08:00").utcoffset(None), timedelta(hours=8))
        with self.assertRaises(ValueError):
            learner_state_build.parse_offset("Asia/Shanghai")

    def test_fringe_and_summary_come_from_prerequisite_edges_and_latest_verdicts(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as temporary:
            store = self._store(Path(temporary))
            a, b, c = "chain.a", "chain.b", "chain.c"
            mrg_export.write_json(store / "mrg" / "chain-lesson.json", {
                "lesson_id": "chain-lesson", "layers": ["fact", "mechanism"],
                "sections": [{"id": s, "concept_ids": [cid]} for s, cid in (("s01", a), ("s02", b), ("s03", c))],
                "nodes": [{"id": cid, "name": cid, "layer": "mechanism"} for cid in (a, b, c)],
                "edges": [{"id": "e1", "from": a, "to": b, "type": "prerequisite_for", "layer": "mechanism"},
                          {"id": "e2", "from": c, "to": b, "type": "depends_on", "layer": "mechanism"},
                          {"id": "e3", "from": a, "to": c, "type": "contrasts_with", "layer": "mechanism"}],
            })

            def attempt(at, section, verdict, confidence=None):
                event = lrg_record.build_event(
                    lesson_id="chain-lesson", section_id=section, kind="checkpoint", attempt_number=1, response="r", feedback="",
                    verdict=verdict, confidence=confidence, criteria_met=[], depth_reached="mechanism", extraction=None,
                    comparison=None, elapsed_seconds=None)
                event["at"] = at
                lrg_record.append_event(store, "chain-lesson", event)

            attempt("2026-09-01T10:00:00Z", "s01", "mastered", confidence=5)
            attempt("2026-09-01T10:30:00Z", "s01", "retry", confidence=5)      # a ends weak, and overconfident
            attempt("2026-09-01T11:00:00Z", "s02", "mastered", confidence=3)   # b mastered on top of weak a
            state = learner_state_build.build(store, now=datetime(2026, 9, 2, tzinfo=timezone.utc), tz=timezone.utc)
            fringe = state["fringe"]
            self.assertEqual(fringe["suspect"], [{"id": b, "weak_prerequisites": [a]}])
            self.assertEqual(fringe["suspect_edges"], [{"from": a, "to": b, "type": "prerequisite_for", "lesson_id": "chain-lesson", "from_verdict": "retry"}])
            self.assertEqual(fringe["outer"], [{"id": c, "status": "untested", "prerequisites": [b]}])  # b mastered, c untested
            summary = state["summary"]
            self.assertEqual((summary["mastered"], summary["suspect"], summary["outer"]), (1, 1, 1))
            self.assertEqual((summary["overconfident_attempts"], summary["high_confidence_attempts"]), (1, 2))
            self.assertEqual(summary["delayed_or_transfer"], 0)
            self.assertEqual(learner_state_build.concept_status(None), "untested")
            # once a is mastered again nothing is suspect; b stays mastered so c is still next
            attempt("2026-09-01T12:00:00Z", "s01", "mastered")
            state = learner_state_build.build(store, now=datetime(2026, 9, 2, tzinfo=timezone.utc), tz=timezone.utc)
            self.assertEqual(state["fringe"]["suspect"], [])
            self.assertEqual([o["id"] for o in state["fringe"]["outer"]], [c])
            pools = review_pool.suspect_pool(state, "chain-lesson", 5)
            self.assertEqual(pools, [])
            self.assertEqual(review_pool.stale_pool(state, None, 5), [])

    def test_chain_rebuild_compares_relation_sets_and_feeds_state_and_review_pool(self):
        import argparse, io, contextlib
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = self._store(root)
            reference = comparator.load_reference(store, "sample-guided-lesson")
            boundary, macro = "learning-design.system-boundary", "learning-design.macro-map"
            exact = comparator.compare_relations(reference, [{"from": "系统边界", "to": "宏观地图", "type": "depends_on"}])
            self.assertEqual((exact["ratio"], exact["reference_edges"], exact["matched"][0]["id"]), (1.0, 1, "r01"))
            self.assertEqual(exact["missing"], [])
            reversed_ = comparator.compare_relations(reference, [{"from": macro, "to": boundary, "type": "depends_on"}])
            self.assertEqual((reversed_["ratio"], len(reversed_["direction_reversed"])), (0.0, 1))
            wrong = comparator.compare_relations(reference, [{"from": boundary, "to": macro, "type": "causes"},
                                                             {"from": boundary, "to": "未知概念", "type": "enables"}])
            self.assertEqual(wrong["wrong_type"][0]["reference_type"], "depends_on")
            self.assertEqual((len(wrong["beyond_reference"]), wrong["unresolved_refs"]), (1, ["未知概念"]))
            empty = comparator.compare_relations(reference, [])
            self.assertEqual((empty["ratio"], [m["id"] for m in empty["missing"]]), (0.0, ["r01"]))
            with self.assertRaises(ValueError):
                comparator.compare_relations(reference, ["not an object"])

            (root / "final.txt").write_text("整体重述", encoding="utf-8")
            (root / "chain.json").write_text(json.dumps({"extracted_by": "model", "concepts": [], "propositions": [],
                                                         "relations": [{"from": macro, "to": boundary, "type": "depends_on"}]}), encoding="utf-8")
            args = dict(store=store, lesson_id="sample-guided-lesson", section_id="s01", kind="final", response_file=root / "final.txt",
                        feedback_file=None, verdict="partial", confidence=None, criteria_met=None, depth=None, extraction=root / "chain.json",
                        no_compare=False, progress=None, elapsed_seconds=None, rigor=None, concept=None, at="2026-09-05T10:00:00+08:00",
                        force=False, chain=True)
            with contextlib.redirect_stdout(io.StringIO()):
                lrg_record.command_append(argparse.Namespace(**args))
            with self.assertRaises(ValueError):
                lrg_record.command_append(argparse.Namespace(**dict(args, kind="checkpoint")))
            event = lrg_record.read_events(store, "sample-guided-lesson")[-1]
            self.assertEqual((event["chain"]["ratio"], len(event["chain"]["direction_reversed"])), (0.0, 1))
            self.assertNotIn("diff", event)
            state = learner_state_build.build(store, now=datetime(2026, 9, 6, tzinfo=timezone.utc), tz=timezone.utc)
            rebuild = state["lessons"]["sample-guided-lesson"]["chain_rebuild"]
            self.assertEqual((rebuild["ratio"], rebuild["matched"], rebuild["reference_edges"], rebuild["missing"]), (0.0, 0, 1, []))
            self.assertEqual(rebuild["direction_reversed"], [{"from": boundary, "to": macro, "type": "depends_on"}])  # the reference direction
            edges = review_pool.missing_edges(state, "sample-guided-lesson", 5)
            self.assertEqual((edges[0]["lesson_id"], edges[0]["status"]), ("sample-guided-lesson", "direction_reversed"))
            self.assertEqual(review_pool.missing_edges(state, "other", 5), [])
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                lrg_record.command_show(argparse.Namespace(store=store, lesson_id="sample-guided-lesson"))
            self.assertIn("chain rebuild: 0/1", buffer.getvalue())
            self.assertNotIn("整体重述", buffer.getvalue())

    def test_lrg_append_measures_elapsed_backfills_and_refuses_duplicates(self):
        import argparse, io, contextlib
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = self._store(root)
            (root / "r1.txt").write_text("第一次回答", encoding="utf-8")
            (root / "r2.txt").write_text("第二次回答", encoding="utf-8")

            def append(response, kind="checkpoint", **overrides):
                args = dict(store=store, lesson_id="sample-guided-lesson", section_id="s01", kind=kind, response_file=root / response,
                            feedback_file=None, verdict="partial", confidence=None, criteria_met=None, depth=None, extraction=None,
                            no_compare=False, progress=None, elapsed_seconds=None, rigor=None, concept=None, at=None, force=False,
                            chain=False)
                args.update(overrides)
                with contextlib.redirect_stdout(io.StringIO()):
                    lrg_record.command_append(argparse.Namespace(**args))

            append("r1.txt", at="2026-09-12T20:00:00+08:00")
            append("r2.txt", at="2026-09-12T20:04:00+08:00")
            append("r1.txt", kind="review", at="2026-09-13T02:00:00+08:00")  # 5 h 56 min later: beyond the cap
            events = lrg_record.read_events(store, "sample-guided-lesson")
            self.assertEqual([e["at"] for e in events], ["2026-09-12T12:00:00Z", "2026-09-12T12:04:00Z", "2026-09-12T18:00:00Z"])
            self.assertTrue(all("recorded_at" in e for e in events))
            self.assertNotIn("elapsed_seconds", events[0])
            self.assertEqual((events[1]["elapsed_seconds"], events[1]["elapsed_source"]), (240, "log"))
            self.assertNotIn("elapsed_seconds", events[2])
            with self.assertRaises(ValueError):
                append("r1.txt", at="2026-09-12T20:05:00+08:00")  # same section, kind and text
            append("r1.txt", at="2026-09-12T20:05:00+08:00", force=True)
            append("r1.txt", kind="variant", at="2026-09-12T20:06:00+08:00", elapsed_seconds=30)  # another kind is not a duplicate
            events = lrg_record.read_events(store, "sample-guided-lesson")
            self.assertEqual(len(events), 5)
            self.assertEqual((events[-1]["elapsed_seconds"], events[-1]["elapsed_source"]), (30, "model"))
            with self.assertRaises(ValueError):
                append("r2.txt", at="2026-09-12 20:07")  # no offset
            with self.assertRaises(ValueError):
                lrg_record.build_event(lesson_id="l", section_id="s", kind="checkpoint", attempt_number=1, response="", feedback="",
                                       verdict="partial", confidence=None, criteria_met=[], depth_reached=None,
                                       extraction=None, comparison=None, elapsed_seconds=-1)
            self.assertEqual(learner_state_build.freshness_window(9).days, 180)


class VariantAndReviewTests(_StoreHelpers, unittest.TestCase):
    def test_prerequisite_lookup_maps_freshness_to_action(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as temporary:
            store = self._store(Path(temporary))
            self._append(store, "2026-01-10T10:00:00Z", "checkpoint", "mastered", depth="mechanism")  # the teaching day
            self._append(store, "2026-01-20T10:00:00Z", "review", "mastered", depth="mechanism")
            state = learner_state_build.build(store, now=datetime(2026, 1, 25, tzinfo=timezone.utc), tz=timezone.utc)
            store_init.atomic_write(store / "learner-state.json", state)
            plan = {"prerequisites": [{"id": "p01", "name": "macro map"}, {"id": "p02", "name": "哈希函数"}]}

            decisions = index_match.prerequisite_plan_lookup(index_match.load_index(store), plan, index_match.load_learner_state(store))

            self.assertEqual([(d["prerequisite_id"], d["action"]) for d in decisions], [("p01", "variant"), ("p02", "diagnose")])
            self.assertEqual(decisions[0]["concept_id"], "learning-design.macro-map")
            stale = learner_state_build.build(store, now=datetime(2026, 6, 1, tzinfo=timezone.utc), tz=timezone.utc)
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
            assets = PLUGIN_ROOT / "skills" / "learn" / "assets"
            (pack / "lesson-plan.json").write_text(TEMPLATE_PLAN.read_text(encoding="utf-8"), encoding="utf-8")
            (pack / "outline.md").write_text((assets / "outline-template.md").read_text(encoding="utf-8"), encoding="utf-8")
            (pack / "units").mkdir()
            (pack / "units" / "s01.md").write_text((assets / "units-template" / "s01.md").read_text(encoding="utf-8"), encoding="utf-8")
            metrics = score_pack.build_metrics(pack, None, None)
            self.assertEqual(metrics["validator_errors"], 0, metrics["errors"])
            self.assertEqual(metrics["relations"], 1)
            self.assertEqual(metrics["layers"], {"fact": 2, "mechanism": 2})
            self.assertEqual(metrics["roles"], {"core": 2, "supporting": 1, "listed": 1})
            self.assertEqual(metrics["max_core_per_section"], 2)
            self.assertEqual(metrics["max_concepts_per_section"], 4)
            self.assertEqual(metrics["coverage"], {"core": 1, "supporting": 1, "listed": 1, "excluded": 1})
            self.assertEqual(metrics["units_present"], "1/1")
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


class ModeAndRolesTests(_StoreHelpers, unittest.TestCase):
    def test_deferred_sections_are_skipped_in_progress(self):
        plan = load_template()
        template = plan["sections"][0]
        plan["sections"] = [dict(template, id="s01", depends_on=[], new_problem="下一步"),
                            dict(template, id="s02", depends_on=["s01"], new_problem="再下一步"),
                            dict(template, id="s03", depends_on=["s02"])]
        plan["mode"] = "fast"
        plan["deferred"] = [{"type": "section", "id": "s02", "reason": "快速模式略过"}]
        state = learning_state.create_state(plan)
        self.assertEqual(state["mode"], "fast")
        self.assertEqual([x["status"] for x in state["sections"]], ["pending", "deferred", "pending"])
        learning_state.append_attempt(state, "s01", "a", "", "mastered", None)
        self.assertEqual(state["current_section_id"], "s03")
        with self.assertRaises(ValueError):
            learning_state.append_attempt(state, "s02", "b", "", "mastered", None)
        learning_state.append_attempt(state, "s03", "c", "", "mastered", None)
        self.assertEqual(state["status"], "completed")
        plan["deferred"] = [{"type": "section", "id": sid, "reason": "r"} for sid in ("s01", "s02", "s03")]
        with self.assertRaises(ValueError):
            learning_state.create_state(plan)

    def test_lrg_rigor_and_supporting_kind(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self._store(Path(temporary))
            event = lrg_record.build_event(
                lesson_id="sample-guided-lesson", section_id="s01", kind="supporting", attempt_number=1, response="r",
                feedback="", verdict="mastered", confidence=None, criteria_met=["k1"], depth_reached="mechanism",
                extraction=None, comparison=None, elapsed_seconds=None, rigor="fast",
                target_concept_ids=["learning-design.problem-chain"],
            )
            self.assertEqual(event["rigor"], "fast")
            self.assertEqual(event["target_concept_ids"], ["learning-design.problem-chain"])
            with self.assertRaises(ValueError):
                lrg_record.build_event(lesson_id="l", section_id="s", kind="supporting", attempt_number=1, response="", feedback="",
                                       verdict="mastered", confidence=None, criteria_met=[], depth_reached=None,
                                       extraction=None, comparison=None, elapsed_seconds=None)
            with self.assertRaises(ValueError):
                lrg_record.build_event(lesson_id="l", section_id="s", kind="checkpoint", attempt_number=1, response="", feedback="",
                                       verdict="mastered", confidence=None, criteria_met=[], depth_reached=None,
                                       extraction=None, comparison=None, elapsed_seconds=None, rigor="sloppy")
            lrg_record.append_event(store, "sample-guided-lesson", event)
            from datetime import datetime, timezone
            state = learner_state_build.build(store, now=datetime.now(timezone.utc))
            chain = state["concepts"]["learning-design.problem-chain"]
            self.assertEqual(chain["rigor_max"], "fast")
            self.assertEqual(chain["attempts"], 1)

    def test_supporting_record_lands_on_its_concept_only(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as temporary:
            store = self._store(Path(temporary))
            gap = lrg_record.build_event(  # a gap taught on the spot, defined in another course
                lesson_id="sample-guided-lesson", section_id="s01", kind="supporting", attempt_number=1,
                response="没听过这个词", feedback="", verdict="retry", confidence=None, criteria_met=[],
                depth_reached="fact", extraction=None, comparison=None, elapsed_seconds=None,
                target_concept_ids=["llm-serving.sliding-window-cache"],
            )
            lrg_record.append_event(store, "sample-guided-lesson", gap)
            state = learner_state_build.build(store, now=datetime.now(timezone.utc))
            self.assertEqual(state["concepts"]["llm-serving.sliding-window-cache"]["last_verdict"], "retry")
            for around in ("learning-design.system-boundary", "learning-design.macro-map"):
                self.assertNotIn(around, state["concepts"])  # the section around it keeps its own verdicts

    def test_fast_rigor_downgrades_prerequisite_action(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as temporary:
            store = self._store(Path(temporary))
            event = lrg_record.build_event(
                lesson_id="sample-guided-lesson", section_id="s01", kind="review", attempt_number=1, response="r", feedback="",
                verdict="mastered", confidence=None, criteria_met=[], depth_reached="mechanism", extraction=None,
                comparison=None, elapsed_seconds=None, rigor="fast",
            )
            lrg_record.append_event(store, "sample-guided-lesson", dict(event, kind="checkpoint", at="2026-01-10T10:00:00Z"))  # the teaching day, fast too
            event["at"] = "2026-01-20T10:00:00Z"
            lrg_record.append_event(store, "sample-guided-lesson", event)
            state = learner_state_build.build(store, now=datetime(2026, 1, 22, tzinfo=timezone.utc), tz=timezone.utc)
            self.assertEqual(state["concepts"]["learning-design.macro-map"]["freshness"], "fresh")
            plan = {"prerequisites": [{"id": "p01", "name": "macro map"}]}
            decisions = index_match.prerequisite_plan_lookup(index_match.load_index(store), plan, state["concepts"])
            self.assertEqual(decisions[0]["freshness"], "stale")
            self.assertEqual(decisions[0]["action"], "variant_then_diagnose")
            self.assertEqual(decisions[0]["rigor_max"], "fast")
            # a later full-rigor success restores full credit
            event2 = dict(event, rigor="full", at="2026-01-21T10:00:00Z", attempt_number=2)
            lrg_record.append_event(store, "sample-guided-lesson", event2)
            state = learner_state_build.build(store, now=datetime(2026, 1, 22, tzinfo=timezone.utc), tz=timezone.utc)
            decisions = index_match.prerequisite_plan_lookup(index_match.load_index(store), plan, state["concepts"])
            self.assertEqual(decisions[0]["action"], "variant")


class SurveyMaterialsTests(unittest.TestCase):
    def test_survey_classifies_repos_documents_generated_and_noise(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "upstream"
            (repo / ".git").mkdir(parents=True)
            (repo / "src").mkdir()
            (repo / "src" / "main.rs").write_text("fn main() {}\n", encoding="utf-8")
            (repo / "src" / "lib.rs").write_text("pub mod x;\n", encoding="utf-8")
            (repo / "README.md").write_text("# Upstream\n", encoding="utf-8")
            (repo / "docs").mkdir()
            (repo / "docs" / "spec.md").write_text("# Specification\n", encoding="utf-8")
            (repo / "demos").mkdir()
            (repo / "demos" / "main.c").write_text("int main(){}\n", encoding="utf-8")
            docs = root / "文档"
            docs.mkdir()
            (docs / "5_conversation_record.md").write_text("This session is being continued from a previous conversation. Summary below covers…\n", encoding="utf-8")
            (docs / "2_设计方案.md").write_text("# 设计方案\n\n## 1. 目标\n\n## 2. 架构\n", encoding="utf-8")
            (root / "进展汇报_2026-09-06.md").write_text("# 进展汇报\n\n> 日期：2026-09-06\n\n## 1. 完成度\n", encoding="utf-8")
            (root / "textbook-ch3.md").write_text("# 第三章 内存隔离\n\n习题 3.1\n", encoding="utf-8")
            data = root / "data"
            data.mkdir()
            (data / "big.log").write_text("x" * 100, encoding="utf-8")
            (data / "dump.json").write_text("{}", encoding="utf-8")
            (root / "tmp.log").write_text("log\n", encoding="utf-8")
            (root / ".env").write_text("SECRET=1\n", encoding="utf-8")
            (root / "paper.pdf").write_bytes(b"%PDF-1.4")

            result = survey_materials.survey(root, 1000)
            by_name = {e["name"]: e for e in result["entries"]}

            self.assertEqual(by_name["upstream"]["kind"], "git_repo")
            self.assertEqual(by_name["upstream"]["readme"], "README.md")
            self.assertEqual(by_name["upstream"]["doc_dirs"], ["docs"])
            self.assertEqual(by_name["upstream"]["entry_hints"], ["src/lib.rs", "src/main.rs"])  # demos/main.c skipped
            self.assertEqual(by_name["文档"]["kind"], "document_folder")
            docs_by = {Path(d["path"]).name: d for d in by_name["文档"]["documents"]}
            self.assertEqual(docs_by["5_conversation_record.md"]["likely"], "generated_intermediate")
            self.assertIn("session_summary", docs_by["5_conversation_record.md"]["generated_signals"])
            self.assertNotEqual(docs_by["2_设计方案.md"]["likely"], "generated_intermediate")
            self.assertEqual(by_name["进展汇报_2026-09-06.md"]["likely"], "generated_intermediate")
            self.assertEqual(by_name["textbook-ch3.md"]["likely"], "primary_or_authored")
            self.assertIn("textbook_like", by_name["textbook-ch3.md"]["primary_signals"])
            self.assertEqual(by_name["data"]["kind"], "data_or_logs")
            self.assertEqual(by_name["tmp.log"]["kind"], "log")
            self.assertEqual(by_name[".env"]["kind"], "sensitive_skipped")
            self.assertEqual(by_name["paper.pdf"]["kind"], "document")
            self.assertIn("binary document", by_name["paper.pdf"]["note"])

            md = survey_materials.render_markdown(result)
            self.assertIn("| `upstream` | git_repo |", md)
            self.assertIn("文档夹内明细", md)
            self.assertNotIn("SECRET", md)
            self.assertNotIn("This session is being continued", md)  # no content copied

    def test_survey_ignores_build_dirs_and_marks_release_trees(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rel = root / "release"
            (rel / "node_modules").mkdir(parents=True)
            (rel / "node_modules" / "x.js").write_text("", encoding="utf-8")
            (rel / "bin").mkdir()
            for i in range(5):
                (rel / "bin" / f"lib{i}.so").write_bytes(b"\x00")
            (rel / "bin" / "run.sh").write_text("#!/bin/sh\n", encoding="utf-8")
            result = survey_materials.survey(root, 1000)
            entry = result["entries"][0]
            self.assertEqual(entry["kind"], "release_tree")
            self.assertEqual(entry["files"], 6)


class PrerequisiteValidationTests(unittest.TestCase):
    def test_prerequisite_templates_are_valid(self):
        asset_root = PLUGIN_ROOT / "skills" / "learn" / "assets"
        plan = json.loads((asset_root / "prerequisite-plan-template.json").read_text(encoding="utf-8"))
        guide = (asset_root / "prerequisite-guide-template.md").read_text(encoding="utf-8")

        self.assertEqual(validate_prerequisites.validate_plan(plan), [])
        self.assertEqual(validate_prerequisites.validate_guide(guide), [])

    def test_duplicate_prerequisite_id_is_rejected(self):
        plan_path = (
            PLUGIN_ROOT
            / "skills"
            / "learn"
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
            / "learn"
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

            self.assertTrue({"cache layer", "cache", "缓存"} <= set(result["known_notes"]))  # plus the other .md stems of the course
            unresolved = {item["concept"] for item in result["unresolved_links"]}
            self.assertEqual(unresolved, {"命中率"})

    def test_scan_groups_pending_concepts_by_unit_and_resolves_unit_notes_by_alias(self):
        with tempfile.TemporaryDirectory() as temporary:
            course = Path(temporary) / "course"
            (course / "units").mkdir(parents=True)
            (course / "concepts").mkdir()
            plan = load_template()
            plan["sections"] = [dict(plan["sections"][0], id="s01"), dict(plan["sections"][0], id="s02", title="第二节")]
            (course / "lesson-plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            (course / "units" / "s01.md").write_text("讲到 [[前馈网络]] 与 [[词元]]，还有 [[s02]]。\n", encoding="utf-8")
            (course / "units" / "s02.md").write_text("这里提到向量空间。\n", encoding="utf-8")
            (course / "outline.md").write_text("大纲提到 [[宏观地图]]。\n", encoding="utf-8")
            (course / "concepts" / "_inbox.md").write_text("- 向量空间\n- 完全无关的词\n", encoding="utf-8")
            result = scan_wikilinks.scan(course, None)
            units = {u["unit"]: u for u in result["by_unit"]}
            self.assertEqual((units["s01"]["concepts"], units["s01"]["scope"], units["s01"]["note_file"]), (["前馈网络", "宏观地图", "词元"], "cluster", "concepts/s01.md"))  # 宏观地图: marked in the outline, listed by s01 in the plan
            self.assertEqual((units["s02"]["concepts"], units["s02"]["scope"]), (["向量空间"], "isolated"))   # inbox entry, matched by the unit text
            self.assertEqual(units[None]["concepts"], ["完全无关的词"])
            self.assertNotIn("s02", [l["concept"] for l in result["unresolved_links"]])                   # [[s02]] resolves to units/s02.md
            self.assertIn("宏观地图", [l["concept"] for l in result["unresolved_links"]])                   # a plan concept marked in the outline
            # a per-unit note whose aliases list its concepts resolves them
            (course / "concepts" / "s01.md").write_text("---\nunit: s01\naliases: [前馈网络, 词元]\nscope: cluster\n---\n# 第一节\n", encoding="utf-8")
            result = scan_wikilinks.scan(course, None)
            self.assertEqual(units_after := {u["unit"]: u["concepts"] for u in result["by_unit"]}, {"s01": ["宏观地图"], "s02": ["向量空间"], None: ["完全无关的词"]})

    def test_scan_scope_defaults_to_the_course_studied_most_recently(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "courses"
            for name, updated, link in (("old-1", "2026-09-01T10:00:00Z", "[[旧概念]]"), ("new-2", "2026-09-13T10:00:00Z", "[[新概念]]")):
                course = root / "目标" / name
                (course / "concepts").mkdir(parents=True)
                (course / "lesson-plan.json").write_text("{}", encoding="utf-8")
                (course / "learning-progress.json").write_text(json.dumps({"updated_at": updated}), encoding="utf-8")
                (course / "outline.md").write_text(f"提到 {link}。\n", encoding="utf-8")
                (course / "concepts" / "_inbox.md").write_text("- 待办\n" if name == "old-1" else "", encoding="utf-8")
            result = scan_wikilinks.scan_scope(root, None, scan_all=False, chosen=None)
            self.assertTrue(result["current_course"].endswith("new-2"))
            self.assertEqual([i["concept"] for i in result["scanned"][0]["unresolved_links"]], ["新概念"])
            self.assertEqual(len(result["scanned"]), 1)
            self.assertEqual([(o["pack_dir"].split("/")[-1], o["inbox_pending"]) for o in result["other_courses"]], [("old-1", 1)])
            everything = scan_wikilinks.scan_scope(root, None, scan_all=True, chosen=None)
            self.assertEqual(len(everything["scanned"]), 2)
            self.assertEqual(everything["other_courses"], [])
            picked = scan_wikilinks.scan_scope(root, None, scan_all=False, chosen=root / "目标" / "old-1")
            self.assertTrue(picked["current_course"].endswith("old-1"))
            with self.assertRaises(ValueError):
                scan_wikilinks.scan_scope(root, None, scan_all=False, chosen=root / "目标")
            self.assertIn("error", scan_wikilinks.scan_scope(Path(temporary) / "empty", None, False, None))


if __name__ == "__main__":
    unittest.main()


SKELETON_PLAN = PLUGIN_ROOT / "skills" / "learn" / "assets" / "skeleton-example" / "lesson-plan.json"
SKELETON_OUTLINE = PLUGIN_ROOT / "skills" / "learn" / "assets" / "skeleton-example" / "outline.md"


def load_skeleton():
    return json.loads(SKELETON_PLAN.read_text(encoding="utf-8"))


class CourseOrganisationTests(unittest.TestCase):
    """Schema 1.6: a course may mix a problem chain with structure and process sections."""

    def plan(self) -> dict:
        """A 1.6 plan: one structure section placing two parts, one process section, one chain section."""
        plan = load_template()
        plan["schema_version"] = "1.6"
        chain = copy.deepcopy(plan["sections"][0])
        chain["id"], chain["new_problem"] = "s03", None
        refs = copy.deepcopy(chain["source_refs"])
        checkpoint = copy.deepcopy(chain["checkpoint"])

        def concept(cid, name, role, ontology):
            return {"id": cid, "name": name, "role": role, "layer": "fact", "domain_path": ["学习设计"],
                    "ontology": ontology, "explanation": f"{name}在系统里的位置。"}

        structure = {
            "id": "s01", "kind": "structure", "title": "系统由哪些部分组成", "depends_on": [],
            "problem": "后面要比较几条路径，先要知道这套系统由哪些部分组成、谁连谁。",
            "mechanism": "宿主进程调用运行时，运行时把任务交给加速器。",
            "meaning": "有了这张图，后面每一节都能指出自己在讲哪一块。",
            "tradeoffs": [], "position": "org.host",
            "concepts": [concept("org.host", "宿主进程", "supporting", "entity"),
                         concept("org.runtime", "运行时", "supporting", "entity"),
                         concept("org.accelerator", "加速器", "listed", "entity")],
            "source_refs": copy.deepcopy(refs), "checkpoint": copy.deepcopy(checkpoint),
        }
        process = {
            "id": "s02", "kind": "process", "title": "跟随一次任务跑一遍", "depends_on": ["s01"],
            "problem": "名词认识了，一次任务实际怎么走？",
            "mechanism": "提交、执行、取回三步，每步换一个参与者。",
            "meaning": "能追踪一次运行，才谈得上比较几条路径。",
            "tradeoffs": [],
            "concepts": [{"id": "org.submit-run", "name": "一次任务的提交与取回", "role": "core", "layer": "mechanism",
                          "domain_path": ["学习设计"], "ontology": "process", "explanation": "被追踪的那一种运行方式。"},
                         concept("org.host", "宿主进程", "supporting", "entity")],
            "steps": [{"actor": "org.host", "target": "org.runtime", "action": "提交任务", "changes": "任务进入队列"},
                      {"actor": "org.runtime", "target": "org.accelerator", "action": "执行并取回", "changes": "结果回到宿主内存"}],
            "source_refs": copy.deepcopy(refs), "checkpoint": copy.deepcopy(checkpoint),
        }
        chain["depends_on"] = ["s02"]
        plan["sections"] = [structure, process, chain]
        plan["big_picture"]["system_map"] = {
            "components": [{"id": "org.host"}, {"id": "org.runtime", "parent": "org.host"}, {"id": "org.accelerator"}],
            "links": [{"from": "org.runtime", "to": "org.accelerator", "label": "把任务交给它执行"}],
        }
        return plan

    def errors(self, plan: dict, **kwargs) -> list[str]:
        return validate_lesson.validate_plan(plan, allow_empty_coverage=True, **kwargs)

    def test_three_kinds_coexist_and_older_plans_are_untouched(self):
        self.assertEqual(self.errors(self.plan()), [])
        self.assertEqual(validate_lesson.section_kind({}), "chain")  # no field: a problem chain
        self.assertEqual(validate_lesson.validate_plan(load_template()), [])  # the 1.5 template is unchanged
        old = load_template()
        old["sections"][0]["kind"] = "structure"
        self.assertTrue(any("requires schema_version '1.6'" in e for e in validate_lesson.validate_plan(old)))

    def test_a_structure_section_has_no_solution_and_no_new_problem(self):
        plan = self.plan()
        plan["sections"][0]["solution"] = "某个方案"
        self.assertTrue(any("solution is not allowed in a structure section" in e for e in self.errors(plan)))
        plan = self.plan()
        plan["sections"][0]["new_problem"] = "引出下一节"
        self.assertTrue(any("new_problem is not allowed in a structure section" in e for e in self.errors(plan)))
        plan = self.plan()
        plan["sections"][0]["tradeoffs"] = ["某个代价"]
        self.assertTrue(any("tradeoffs must be empty in a structure section" in e for e in self.errors(plan)))
        plan = self.plan()  # a chain section still needs its solution
        del plan["sections"][2]["solution"]
        self.assertTrue(any("sections[2].solution" in e for e in self.errors(plan)))

    def test_a_structure_sections_parts_are_concepts_on_the_map(self):
        plan = self.plan()
        plan["sections"][0]["concepts"][0]["role"] = "core"
        self.assertTrue(any("must be supporting or listed in a structure section" in e for e in self.errors(plan)))
        plan = self.plan()
        del plan["sections"][0]["concepts"][0]["ontology"]
        self.assertTrue(any("must declare ontology" in e for e in self.errors(plan)))
        plan = self.plan()  # a concept of the structure section that is not on the map is advisory, not an error
        plan["sections"][0]["concepts"].append(
            {"id": "org.aside", "name": "旁注", "role": "listed", "layer": "fact",
             "domain_path": ["学习设计"], "explanation": "不在图上的一条。"})
        warnings: list = []
        self.assertEqual(validate_lesson.validate_plan(plan, allow_empty_coverage=True, warnings=warnings), [])
        self.assertTrue(any("not on the system map" in w for w in warnings), warnings)

    def test_system_map_components_are_concept_ids(self):
        plan = self.plan()
        plan["big_picture"]["system_map"]["components"].append({"id": "other-course.fabric"})
        self.assertTrue(any("other-course.fabric" in e for e in self.errors(plan)))
        self.assertEqual(self.errors(plan, registered={"other-course.fabric"}), [])
        plan = self.plan()
        plan["big_picture"]["system_map"]["components"][1]["parent"] = "org.nowhere"
        self.assertTrue(any("is not a component" in e for e in self.errors(plan)))
        plan = self.plan()
        components = plan["big_picture"]["system_map"]["components"]
        components[0]["parent"], components[1]["parent"] = "org.runtime", "org.host"
        self.assertTrue(any("is inside itself" in e for e in self.errors(plan)))
        plan = self.plan()
        plan["big_picture"]["system_map"]["links"][0]["label"] = "  "
        self.assertTrue(any("links[0].label" in e for e in self.errors(plan)))

    def test_a_structure_section_requires_the_structured_map(self):
        plan = self.plan()
        plan["sections"] = plan["sections"][2:]  # no structure section: the legacy list of steps is still fine
        plan["sections"][0]["depends_on"] = []
        plan["coverage"] = [dict(item, section_id="s03") if item.get("section_id") else item
                            for item in plan["coverage"]]
        plan["big_picture"]["system_map"] = ["提交", "执行", "取回"]
        self.assertEqual(self.errors(plan), [])
        plan = self.plan()
        plan["big_picture"]["system_map"] = ["提交", "执行", "取回"]
        self.assertTrue(any("must be {components, links} when the course has a structure section" in e
                            for e in self.errors(plan)))

    def test_a_process_section_tracks_one_run_step_by_step(self):
        plan = self.plan()
        plan["sections"][1]["steps"] = plan["sections"][1]["steps"][:1]
        self.assertTrue(any("steps must be a list of at least 2" in e for e in self.errors(plan)))
        plan = self.plan()
        plan["sections"][1]["steps"][0]["actor"] = "org.nobody"
        self.assertTrue(any("actor 'org.nobody' is not a concept id" in e for e in self.errors(plan)))
        plan = self.plan()
        plan["sections"][1]["concepts"][0]["ontology"] = "entity"
        self.assertTrue(any("must have one core concept with ontology 'process'" in e for e in self.errors(plan)))
        plan = self.plan()  # taking part in the run without being on the map is advisory
        plan["sections"][1]["concepts"].append(
            {"id": "org.scheduler", "name": "调度器", "role": "supporting", "layer": "fact",
             "domain_path": ["学习设计"], "explanation": "不在图上。",
             "check": {"prompt": "它做什么？", "criteria": [{"id": "k1", "text": "说出职责", "layer": "fact"}], "hint": "-"}})
        plan["sections"][1]["steps"][0]["actor"] = "org.scheduler"
        warnings: list = []
        self.assertEqual(validate_lesson.validate_plan(plan, allow_empty_coverage=True, warnings=warnings), [])
        self.assertTrue(any("is not on the system map" in w for w in warnings), warnings)

    def test_position_names_the_component_this_section_opens_up(self):
        plan = self.plan()
        plan["sections"][2]["position"] = "org.accelerator"
        self.assertEqual(self.errors(plan), [])
        plan["sections"][2]["position"] = "org.nowhere"
        self.assertTrue(any("position 'org.nowhere' is not a component" in e for e in self.errors(plan)))

    def test_parts_are_left_out_of_the_orphan_count_and_the_chain_roster(self):
        plan = self.plan()
        orphans = validate_lesson.orphan_concepts(plan)
        self.assertNotIn("org.host", orphans["orphans"])  # a part is joined by the map's links, not by relations
        names = lesson_section.shuffled_concept_names(plan)
        self.assertNotIn("运行时", names)  # only in the structure section: a reference, not something to rebuild
        self.assertIn("宿主进程", names)  # it also takes part in the process section
        self.assertIn("一次任务的提交与取回", names)

    def test_the_new_fields_are_rejected_before_16(self):
        for key, value in (("kind", "process"), ("steps", []), ("position", "x")):
            plan = load_template()
            plan["sections"][0][key] = value
            self.assertTrue(any(f"sections[0].{key} requires schema_version '1.6'" in e
                                for e in validate_lesson.validate_plan(plan)), key)
        plan = load_template()
        plan["big_picture"]["system_map"] = {"components": [], "links": []}
        self.assertTrue(any("requires schema_version '1.6'" in e for e in validate_lesson.validate_plan(plan)))


class SkeletonCourseTests(unittest.TestCase):
    """Schema 1.3 (spec D): shape, evidence pool, anchors, probes, branch candidates."""

    def test_example_skeleton_validates_and_reports_grounding(self):
        plan = load_skeleton()
        self.assertEqual(validate_lesson.validate_plan(plan), [])
        self.assertEqual(validate_lesson.validate_outline(SKELETON_OUTLINE.read_text(encoding="utf-8"), plan), [])
        self.assertEqual(validate_lesson.plan_shape(plan), "skeleton")
        self.assertEqual(validate_lesson.grounding(plan), {"anchored": 3, "external": 1, "no_anchor": 1, "total": 5})
        warnings = validate_lesson.collect_warnings(plan)
        self.assertTrue(any("no anchor" in w for w in warnings), warnings)
        # no section-count advisory for skeleton courses: size follows the domain, not a cap
        plan["sections"] = plan["sections"] * 6
        self.assertFalse(any("sections (>" in w for w in validate_lesson.collect_warnings(plan)))

    def _thin_anchor_sources(self, root: Path) -> Path:
        prose = "Continuous batching keeps the accelerator busy by admitting a new request as soon as another finishes. " * 3
        (root / "doc.md").write_text(
            "# Continuous batching from first principles\n\n"
            "## Continuous batching\n\n" + prose + "\n\n"
            "## Enable the cache\n\nSet `enable_cache = true`.\n", encoding="utf-8")
        (root / "config.json").write_text('{"index_topk": 2048}\n', encoding="utf-8")
        return root

    def _thin_anchor_plan(self) -> dict:
        def concept(cid, role, path, locator):
            return {"id": cid, "name": cid.split(".")[-1], "role": role, "anchor": {"path": path, "locator": locator}}
        return {"sections": [{"id": "s01", "concepts": [
            concept("x.explained", "core", "doc.md", "## Continuous batching"),
            concept("x.one-liner", "core", "doc.md", "## Enable the cache"),
            concept("x.key-name", "supporting", "config.json", '"index_topk"'),
            concept("x.listed-only", "listed", "config.json", '"never judged"'),
        ]}]}

    def test_thin_anchors_flag_key_names_and_one_line_passages(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self._thin_anchor_sources(Path(temporary))
            found, per_section = validate_lesson.thin_anchors(self._thin_anchor_plan(), root)
            self.assertEqual(per_section, ["s01 2/3 concepts on thin anchors"])  # listed concepts are not judged
            self.assertTrue(any("x.key-name" in f and "data or code file" in f for f in found), found)
            self.assertTrue(any("x.one-liner" in f and f"under {validate_lesson.THIN_ANCHOR_CHARS}" in f for f in found), found)
            self.assertFalse(any("x.explained" in f for f in found), found)

    def test_anchor_passage_takes_the_heading_section_not_the_title_line(self):
        with tempfile.TemporaryDirectory() as temporary:
            doc = self._thin_anchor_sources(Path(temporary)) / "doc.md"
            # the file's own title line contains the same words: the exact heading must win
            passage = validate_lesson.anchor_passage(doc, "## Continuous batching")
            self.assertGreater(len("".join(passage.split())), validate_lesson.THIN_ANCHOR_CHARS)
            self.assertNotIn("from first principles", passage)
            self.assertNotIn("Enable the cache", passage)  # stops at the next heading of the same level
            self.assertIsNone(validate_lesson.anchor_passage(doc, "## A heading that is not there"))

    def test_cross_lesson_relation_needs_the_store(self):
        plan = load_template()
        plan["relations"].append({
            "id": "r-cross", "from": plan["sections"][0]["concepts"][0]["id"], "to": "other-course.macro-map",
            "type": "depends_on", "layer": "mechanism", "rationale": "沿用前一门课的概念",
            "source_refs": list(plan["relations"][0]["source_refs"]),
        })
        errors = validate_lesson.validate_plan(plan)  # offline: an unknown endpoint is still an error
        self.assertTrue(any("other-course.macro-map" in e for e in errors), errors)
        self.assertEqual(validate_lesson.validate_plan(plan, registered={"other-course.macro-map"}), [])
        self.assertEqual(validate_lesson.validate_plan(plan, registered=set())[0].count("not registered in the store"), 1)
        local = {c["id"] for s in plan["sections"] for c in s["concepts"]}
        self.assertEqual(validate_lesson.cross_lesson_edges(plan, local), ["r-cross"])

    def test_cross_lesson_edges_are_taught_at_predict_and_left_out_of_the_chain(self):
        plan = load_template()
        section = plan["sections"][0]
        plan["relations"].append({
            "id": "r-cross", "from": section["concepts"][0]["id"], "to": "other-course.macro-map",
            "type": "depends_on", "layer": "mechanism", "rationale": "它是本节机制的前一步",
            "source_refs": list(plan["relations"][0]["source_refs"]),
        })
        view = lesson_section.render_section(plan, section["id"])
        self.assertIn("## 跨课关系", view)
        self.assertIn("other-course.macro-map", view)
        self.assertIn("它是本节机制的前一步", view)
        public, deep = mrg_export.export(plan)
        self.assertIn("r-cross", [e["id"] for e in public["edges"]])  # exported, so the section view can use it
        reference = comparator.Reference(public, deep)
        self.assertNotIn("r-cross", [e["id"] for e in reference.public_edges])  # but not a chain-rebuild reference edge
        self.assertIn("r-cross", [e["id"] for e in reference.edges])

    def test_skeleton_requirements_are_enforced(self):
        plan = load_skeleton()
        del plan["sections"][0]["probe"]
        del plan["sections"][0]["concepts"][0]["anchor"]
        plan["sections"][1]["concepts"][0]["anchor"] = {"path": "teeapp/src/ra", "locator": "verify"}  # reserve, not pool
        plan["branch_candidates"][0]["concept_ids"].append("cs.tee.nonexistent")
        plan["branch_candidates"][1]["materials"] = ["somewhere/else"]
        plan["coverage"].append({"path": "occlum/README.md", "heading": "*", "disposition": "core", "section_id": "s01"})
        errors = validate_lesson.validate_plan(plan)
        for needle in ("sections[0].probe is required", "concepts[0].anchor is required",
                       "not under any coverage row with disposition 'pool'", "unknown concept 'cs.tee.nonexistent'",
                       "'somewhere/else' is not under any 'pool' or 'reserve'", "heading '*' (whole file) is only allowed"):
            self.assertTrue(any(needle in e for e in errors), (needle, errors))

    def test_skeleton_fields_are_rejected_elsewhere(self):
        plan = load_skeleton()
        plan["shape"] = "linear"
        errors = validate_lesson.validate_plan(plan)
        for needle in ("probe is only allowed in skeleton", "anchor is only allowed in skeleton",
                       "branch_candidates is only allowed in skeleton", "disposition 'pool' outside a skeleton course"):
            self.assertTrue(any(needle in e for e in errors), (needle, errors))
        plan = load_skeleton()
        plan["shape"] = "branch"
        errors = validate_lesson.validate_plan(plan)
        self.assertTrue(any("parent_course must name the skeleton course" in e for e in errors), errors)
        old = load_template()
        old["schema_version"], old["shape"] = "1.2", "skeleton"
        for key in ("contrast", "cases", "ontology"):
            old["sections"][0]["concepts"][0].pop(key, None)
        self.assertTrue(any("requires schema_version '1.3'" in e for e in validate_lesson.validate_plan(old)))

    def test_external_archive_pool_rows_are_allowed_in_any_shape(self):
        plan = load_template()
        plan["coverage"].append({"path": "whetstone/external/llm-basics_20260911/01_roofline.md", "heading": "*", "disposition": "pool"})
        self.assertEqual(validate_lesson.validate_plan(plan, {"examples/source.md"}), [])
        plan["coverage"].append({"path": "docs/other.md", "heading": "*", "disposition": "pool"})
        errors = validate_lesson.validate_plan(plan, {"examples/source.md"})
        self.assertTrue(any("'pool' outside a skeleton course is only allowed for external archives" in e for e in errors), errors)
        plan["coverage"].pop()
        plan["coverage"].append({"path": "whetstone/external/x/y.md", "heading": "*", "disposition": "reserve"})
        errors = validate_lesson.validate_plan(plan, {"examples/source.md"})
        self.assertTrue(any("'reserve' is only allowed in skeleton" in e for e in errors), errors)
        self.assertTrue(validate_lesson.is_external_archive("external/x/y.md"))
        self.assertFalse(validate_lesson.is_external_archive("material/external-notes.md"))

    def test_external_refs_are_counted(self):
        plan = load_template()
        before = validate_lesson.external_refs(plan)
        plan["sections"][0]["source_refs"].append({"path": "whetstone/external/s_20260911/a.md", "locator": "## A", "support": "external", "note": "补充"})
        after = validate_lesson.external_refs(plan)
        self.assertEqual(after["total"], before["total"] + 1)
        self.assertEqual(after["external"], before["external"] + 1)

    def test_probe_criteria_never_leak_into_outline(self):
        plan = load_skeleton()
        outline = SKELETON_OUTLINE.read_text(encoding="utf-8")
        leaked = outline + "\n" + plan["sections"][0]["probe"]["criteria"][0]["text"]
        errors = validate_lesson.validate_outline(leaked, plan)
        self.assertTrue(any("probe criterion" in e for e in errors), errors)
        errors = validate_lesson.validate_outline(outline.replace("分支：项目里的远程证明链路", "x"), plan)
        self.assertTrue(any("branch candidate" in e for e in errors), errors)

    def test_wholesale_coverage_skips_heading_check(self):
        plan = load_skeleton()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "occlum" / "docs").mkdir(parents=True)
            (root / "occlum" / "docs" / "ra.md").write_text("## Remote attestation\n\n## Something uncovered\n", encoding="utf-8")
            plan["sections"][1]["source_refs"][0]["path"] = "occlum/docs/ra.md"
            self.assertEqual(validate_lesson.validate_coverage_against_sources(plan, root), [])
            plan["coverage"][0]["heading"] = "Overview"  # no longer wholesale
            plan["coverage"][0]["disposition"] = "excluded"
            plan["coverage"][0]["reason"] = "x"
            errors = validate_lesson.validate_coverage_against_sources(plan, root)
            self.assertTrue(any("Something uncovered" in e for e in errors), errors)

    def test_export_carries_anchors_and_branches(self):
        public, deep = mrg_export.export(load_skeleton())
        self.assertEqual(public["shape"], "skeleton")
        self.assertEqual(public["grounding"]["anchored"], 3)
        self.assertEqual([b["id"] for b in public["branch_candidates"]], ["b1", "b2"])
        nodes = {n["id"]: n for n in public["nodes"]}
        self.assertEqual(nodes["cs.tee.enclave"]["anchor"], "anchored")
        self.assertTrue(any(r.get("note") == "skeleton anchor" for r in nodes["cs.tee.enclave"]["source_refs"]))
        self.assertEqual(nodes["cs.tee.trust-root"]["anchor"], "external")
        self.assertEqual(public["sections"][0]["probe_prompt"], load_skeleton()["sections"][0]["probe"]["prompt"])

    def test_defer_after_probe_and_probe_kind(self):
        state = learning_state.create_state(load_skeleton())
        learning_state.defer_section(state, "s01", "原理探测通过，学习者选择跳过")
        self.assertEqual(state["current_section_id"], "s02")
        self.assertEqual(state["sections"][0]["status"], "deferred")
        with self.assertRaises(ValueError):
            learning_state.defer_section(state, "s01", "again")
        learning_state.append_attempt(state, "s02", "r", "", "mastered", None)
        with self.assertRaises(ValueError):
            learning_state.defer_section(state, "s02", "has attempts")
        self.assertEqual(state["status"], "completed")
        event = lrg_record.build_event(
            lesson_id="tee-skeleton-1", section_id="s01", kind="probe", attempt_number=1, response="r", feedback="",
            verdict="mastered", confidence=None, criteria_met=["p1", "p2"], depth_reached="rationale",
            extraction=None, comparison=None, elapsed_seconds=None,
        )
        self.assertEqual(event["kind"], "probe")

    def test_unit_must_show_checkpoint_not_probe(self):
        plan = load_skeleton()
        section = plan["sections"][0]
        body = "# " + section["title"] + "\n\n" + "\n".join(f"- {c['name']}" for c in section["concepts"]) + "\n\n## 轮到你解释\n\n"
        with tempfile.TemporaryDirectory() as temporary:
            units = Path(temporary)
            (units / "s01.md").write_text(body + section["probe"]["prompt"] + "\n", encoding="utf-8")
            (units / "s02.md").write_text("# " + plan["sections"][1]["title"] + "\n## 轮到你\n" + plan["sections"][1]["checkpoint"]["prompt"] + "\n"
                                          + "\n".join(c["name"] for c in plan["sections"][1]["concepts"]), encoding="utf-8")
            errors, _ = validate_lesson.validate_units(units, plan)
            self.assertTrue(any("s01.md contains the probe question" in e for e in errors), errors)
            self.assertTrue(any("s01.md does not contain its checkpoint.prompt" in e for e in errors), errors)
            self.assertFalse(any("s02.md" in e for e in errors), errors)
            (units / "s01.md").write_text(body + section["checkpoint"]["prompt"] + "\n", encoding="utf-8")
            errors, _ = validate_lesson.validate_units(units, plan)
            self.assertEqual(errors, [])


class LearnerHomeTests(_StoreHelpers, unittest.TestCase):
    """Local-first store: every write stays in the workspace; the learner home is a derived aggregate."""

    def test_push_aggregates_two_workspaces_without_raw_answers(self):
        from datetime import datetime, timezone
        now = datetime(2026, 1, 22, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            home = root / "home"
            ws1 = root / "tee" / "whetstone"
            ws2 = root / "riscv" / "whetstone"
            ws1.mkdir(parents=True); ws2.mkdir(parents=True)
            s1, s2 = self._store(ws1), self._store(ws2)
            wrong = {"id": "p1", "text": "宏观地图能解释设计理由", "status": "wrong", "concept_ids": ["learning-design.macro-map"]}
            self._append(s1, "2026-01-20T10:00:00Z", "transfer", "mastered", depth="mechanism", props=[wrong])
            self._append(s2, "2026-01-21T10:00:00Z", "review", "mastered", depth="rationale")
            self._append(s2, "2026-01-10T10:00:00Z", "checkpoint", "mastered")
            r1 = store_sync.push(s1, home, now=now)
            r2 = store_sync.push(s2, home, now=now)
            self.assertTrue(r1["slug"].startswith("tee-") and r2["slug"].startswith("riscv-"))
            self.assertEqual(r2["workspaces"], 2)
            state = json.loads((home / "learner-state.json").read_text(encoding="utf-8"))
            macro = state["concepts"]["learning-design.macro-map"]
            self.assertEqual(sorted(macro["workspaces"]), sorted([r1["slug"], r2["slug"]]))
            self.assertEqual(macro["attempts"], 3)              # 1 in ws1 + 2 in ws2
            self.assertEqual(macro["stability"], 3)             # success days add across workspaces (1 + 2)
            self.assertEqual(macro["evidence_tier"], "delayed")  # latest success is the ws2 review on Jan 21
            self.assertEqual(macro["freshness"], "fresh")
            self.assertEqual(macro["depth_max"], "rationale")
            self.assertEqual(macro["rigor_max"], "full")
            self.assertEqual(len(macro["error_propositions"]), 1)
            self.assertEqual(macro["error_propositions"][0]["workspace"], r1["slug"])
            # the home never contains a raw answer, only derived state and the registry
            for path in home.rglob("*"):
                if path.is_file():
                    self.assertNotIn('"response"', path.read_text(encoding="utf-8"), path)
            self.assertFalse((home / "lrg").exists())
            index = json.loads((home / "concepts" / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(len(index["concepts"]), 4)
            self.assertEqual(sorted(index["concepts"]["learning-design.macro-map"]["workspaces"]), sorted([r1["slug"], r2["slug"]]))
            # rebuild from snapshots alone reproduces the aggregate (no access to the workspaces needed)
            (home / "learner-state.json").unlink()
            store_sync.rebuild(home, now)
            again = json.loads((home / "learner-state.json").read_text(encoding="utf-8"))
            self.assertEqual(again["concepts"]["learning-design.macro-map"]["attempts"], 3)
            # readers accept the home in place of a store
            index_home = index_match.load_index(home)
            decisions = index_match.prerequisite_plan_lookup(index_home, {"prerequisites": [{"id": "p01", "name": "macro map"}]},
                                                             index_match.load_learner_state(home))
            self.assertEqual(decisions[0]["action"], "variant")
            items = review_pool.pool(review_pool.load_state(home), None, None, None, 5)
            self.assertEqual([i["id"] for i in items], ["p1"])
            # a workspace is never written by push beyond its own derived learner-state
            self.assertTrue((s1 / "learner-state.json").is_file())
            self.assertFalse((s1 / "workspaces.json").exists())

    def test_home_defaults_and_slug_label(self):
        import os
        with tempfile.TemporaryDirectory() as temporary:
            os.environ["WHETSTONE_HOME"] = temporary
            try:
                self.assertEqual(store_sync.default_home(), Path(temporary))
            finally:
                del os.environ["WHETSTONE_HOME"]
            self.assertTrue(store_sync.workspace_slug(Path("/x/tee_dsh/whetstone")).startswith("tee_dsh-"))
            self.assertTrue(store_sync.workspace_slug(Path("/x/tee_dsh/whetstone/store")).startswith("tee_dsh-"))


class LayoutTests(unittest.TestCase):
    """A course pack is self-contained: sources.json records the material root relative to itself,
    so validators find the sources in both layouts (<materials>/whetstone/courses/<id>/ and
    <knowledge-base>/courses/<goal>/<id>/ with materials under material/)."""

    def _materials(self, root: Path) -> Path:
        materials = root / "material" / "spec"
        (materials / "examples").mkdir(parents=True)
        (materials / "examples" / "source.md").write_text("## Architecture\n\n## Course ordering\n\n## Appendix\n\n## Deployment notes\n", encoding="utf-8")
        return materials

    def test_base_path_is_relative_to_the_manifest_in_both_layouts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            materials = self._materials(root)
            # knowledge-base layout
            kb_pack = root / "courses" / "目标A" / "c1"
            kb_pack.mkdir(parents=True)
            manifest = source_manifest.build_manifest([materials / "examples"], materials, 1024, 1024, output=kb_pack / "sources.json")
            self.assertEqual(manifest["base_path"], "../../../material/spec")
            self.assertEqual(manifest["roots"], ["examples"])
            (kb_pack / "sources.json").write_text(json.dumps(manifest), encoding="utf-8")
            self.assertEqual(validate_lesson.sources_root_from_manifest(kb_pack / "sources.json", manifest), materials.resolve())
            # standalone layout: <materials>/whetstone/courses/<id>/
            sa_pack = materials / "whetstone" / "courses" / "c1"
            sa_pack.mkdir(parents=True)
            manifest2 = source_manifest.build_manifest([materials / "examples"], materials, 1024, 1024, output=sa_pack / "sources.json")
            self.assertEqual(manifest2["base_path"], "../../..")
            # legacy "." cannot be resolved
            self.assertIsNone(validate_lesson.sources_root_from_manifest(kb_pack / "sources.json", {"base_path": "."}))
            # rebase migrates an old manifest in place, touching only base_path
            (kb_pack / "sources.json").write_text(json.dumps(dict(manifest, base_path=".")), encoding="utf-8")
            self.assertEqual(source_manifest.rebase_manifest(kb_pack / "sources.json", materials), "../../../material/spec")
            rebased = json.loads((kb_pack / "sources.json").read_text(encoding="utf-8"))
            self.assertEqual(rebased["roots"], ["examples"])
            # the coverage check then works with the derived root
            plan = load_template()
            self.assertEqual(validate_lesson.validate_coverage_against_sources(plan, validate_lesson.sources_root_from_manifest(kb_pack / "sources.json", rebased)), [])


class PrerequisiteCourseTests(_StoreHelpers, unittest.TestCase):
    """Schema 1.4: a course spawned to fill a parent course's gap (prerequisite_of / blocked_at / depth)."""

    def _prerequisite_plan(self):
        plan = load_template()
        plan["schema_version"] = "1.4"
        for key in ("contrast", "cases", "ontology"):
            plan["sections"][0]["concepts"][0].pop(key, None)  # a 1.4 plan has no 1.5 fields
        plan["lesson_id"] = "linear-algebra-min-0"
        plan["prerequisite_of"] = "sample-guided-lesson"
        plan["blocked_at"] = "s01"
        plan["depth"] = 1
        return plan

    def test_prerequisite_fields_validate_together_on_a_linear_1_4_course(self):
        plan = self._prerequisite_plan()
        self.assertEqual(validate_lesson.validate_plan(plan, {"examples/source.md"}), [])
        self.assertTrue(validate_lesson.is_prerequisite_course(plan))
        ratio = validate_lesson.fact_ratio(plan)
        self.assertEqual(ratio["total"], len({c.get("id") or c["name"] for s in plan["sections"] for c in s["concepts"]}))
        self.assertGreaterEqual(ratio["fact"], 1)

        old = self._prerequisite_plan()
        old["schema_version"] = "1.2"
        self.assertTrue(any("requires schema_version '1.4'" in e for e in validate_lesson.validate_plan(old)), "1.2 must reject 1.4 keys")

        for broken, needle in (
            ({"depth": None}, "root.depth required alongside"),
            ({"depth": 0}, "integer >= 1"),
            ({"prerequisite_of": "linear-algebra-min-0"}, "not this course"),
            ({"blocked_at": ""}, "blocked_at must name"),
            ({"shape": "skeleton"}, "only allowed when shape = linear"),
            ({"parent_course": "some-skeleton"}, "mutually exclusive"),
        ):
            plan = self._prerequisite_plan()
            for key, value in broken.items():
                if value is None:
                    del plan[key]
                else:
                    plan[key] = value
            errors = validate_lesson.validate_plan(plan, {"examples/source.md"})
            self.assertTrue(any(needle in e for e in errors), (needle, errors))

    def test_register_records_the_relation_and_export_carries_it(self):
        plan = self._prerequisite_plan()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = root / "store"
            store_init.init_store(store, [])
            plan_path = root / "courses" / "linear-algebra-min-0" / "lesson-plan.json"
            plan_path.parent.mkdir(parents=True)
            plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            data = store_init.register_lesson(store, plan_path)
            entry = next(l for l in data["lessons"] if l["lesson_id"] == "linear-algebra-min-0")
            self.assertEqual((entry["prerequisite_of"], entry["blocked_at"], entry["depth"]), ("sample-guided-lesson", "s01", 1))
            data = store_init.register_lesson(store, plan_path)  # idempotent, relation kept
            entry = next(l for l in data["lessons"] if l["lesson_id"] == "linear-algebra-min-0")
            self.assertEqual(entry["depth"], 1)
            self.assertEqual(index_match.prerequisite_courses_of(store, "sample-guided-lesson"), {"linear-algebra-min-0"})
            self.assertEqual(index_match.prerequisite_courses_of(store, "other"), set())
            self.assertEqual(index_match.prerequisite_courses_of(None, "sample-guided-lesson"), set())
        public, deep = mrg_export.export(plan)
        self.assertEqual(public["prerequisite_of"], "sample-guided-lesson")
        self.assertEqual((deep["blocked_at"], deep["depth"]), ("s01", 1))

    def test_concepts_learned_in_a_prerequisite_course_get_a_variant_not_a_diagnosis(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = self._store(root)
            child_plan = self._prerequisite_plan()
            child_path = root / "child" / "lesson-plan.json"
            child_path.parent.mkdir()
            child_path.write_text(json.dumps(child_plan, ensure_ascii=False), encoding="utf-8")
            store_init.register_lesson(store, child_path)
            # the child course taught macro-map, but only with immediate (checkpoint) evidence
            event = lrg_record.build_event(
                lesson_id="linear-algebra-min-0", section_id="s01", kind="checkpoint", attempt_number=1, response="r", feedback="",
                verdict="mastered", confidence=None, criteria_met=[], depth_reached="mechanism", extraction=None,
                comparison=None, elapsed_seconds=None, target_concept_ids=["learning-design.macro-map"],
            )
            event["at"] = "2026-01-20T10:00:00Z"
            lrg_record.append_event(store, "linear-algebra-min-0", event)
            state = learner_state_build.build(store, now=datetime(2026, 1, 21, tzinfo=timezone.utc))
            self.assertEqual(state["concepts"]["learning-design.macro-map"]["freshness"], "unknown")
            plan = {"prerequisites": [{"id": "p01", "name": "macro map"}, {"id": "p02", "name": "哈希函数"}]}
            without = index_match.prerequisite_plan_lookup(index_match.load_index(store), plan, state["concepts"])
            self.assertEqual(without[0]["action"], "diagnose")
            courses = index_match.prerequisite_courses_of(store, "sample-guided-lesson")
            with_rule = index_match.prerequisite_plan_lookup(index_match.load_index(store), plan, state["concepts"], courses)
            self.assertEqual((with_rule[0]["action"], with_rule[0]["via_prerequisite_course"]), ("variant", "linear-algebra-min-0"))
            self.assertEqual((with_rule[1]["action"], with_rule[1]["via_prerequisite_course"]), ("diagnose", None))

    def test_block_and_unblock_a_parent_section(self):
        state = learning_state.create_state(load_template())
        learning_state.block_section(state, "s01", "linear-algebra-min-0")
        self.assertEqual(state["blocked"]["by"], "linear-algebra-min-0")
        self.assertEqual(state["current_section_id"], "s01")
        with self.assertRaises(ValueError):
            learning_state.append_attempt(state, "s01", "a", "", "mastered", None)
        with self.assertRaises(ValueError):
            learning_state.block_section(state, "s01", "again")
        self.assertEqual(learning_state.unblock_section(state, "s01"), "linear-algebra-min-0")
        self.assertNotIn("blocked", state)
        learning_state.append_attempt(state, "s01", "a", "", "mastered", None)
        types = [e["type"] for e in state["events"]]
        self.assertLess(types.index("section_blocked"), types.index("section_unblocked"))
        self.assertLess(types.index("section_unblocked"), types.index("attempt_recorded"))
        with self.assertRaises(ValueError):
            learning_state.unblock_section(state, "s01")

    def test_diagnostic_answers_are_immediate_evidence(self):
        from datetime import datetime, timezone
        long_ago = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(learner_state_build.tier_for("diagnostic", long_ago, datetime(2026, 2, 1, tzinfo=timezone.utc), timezone.utc), "immediate")
        event = lrg_record.build_event(
            lesson_id="sample-guided-lesson", section_id="s01", kind="diagnostic", attempt_number=1, response="r", feedback="",
            verdict="partial", confidence=None, criteria_met=[], depth_reached="fact", extraction=None, comparison=None, elapsed_seconds=None,
        )
        self.assertEqual(event["kind"], "diagnostic")


class Schema15Tests(unittest.TestCase):
    """Schema 1.5: contrast / cases / ontology, contested tradeoffs, sub-sections, review courses."""

    @staticmethod
    def plan15():
        plan = load_template()
        plan["schema_version"] = "1.5"
        refs = plan["sections"][0]["source_refs"]
        boundary = plan["sections"][0]["concepts"][0]
        boundary["contrast"] = {"with": "learning-design.macro-map", "differs_in": "边界说的是范围，地图说的是范围内的关系"}
        boundary["cases"] = [{"summary": "一份 REST 服务的输入与输出", "source_refs": refs},
                             {"summary": "一条数据流水线的输入与输出", "source_refs": refs}]
        boundary["ontology"] = "constraint"
        plan["sections"][0]["tradeoffs"] = [
            "边界画得越窄，地图越准，但越容易漏掉外部依赖",
            {"text": "材料对是否先画边界说法不一", "contested": True,
             "sides": [{"claim": "先画边界再画地图", "source_refs": refs}, {"claim": "先画地图再收边界", "source_refs": refs}]},
        ]
        return plan

    def test_variation_fields_validate_and_export(self):
        plan = self.plan15()
        self.assertEqual(validate_lesson.validate_plan(plan), [])
        self.assertEqual(validate_lesson.variation_ratio(plan), {"contrast": 1, "cases": 1, "total": 2})
        public, deep = mrg_export.export(plan)
        node = next(n for n in public["nodes"] if n["id"] == "learning-design.system-boundary")
        self.assertEqual((node["ontology"], node["contrast"]["with"], len(node["cases"])), ("constraint", "learning-design.macro-map", 2))
        self.assertEqual(deep["sections"][0]["tradeoffs"][1]["contested"], True)
        view = lesson_section.render_section(plan, "s01")
        self.assertIn("易混对: learning-design.macro-map", view)
        self.assertIn("案例 2: 一条数据流水线", view)
        self.assertIn("材料在此处不一致", view)
        # the leak check reads the text of an object tradeoff like a string one
        pairs = validate_lesson.hidden_pairs(plan["sections"][0]) if hasattr(validate_lesson, "hidden_pairs") else None
        errors = validate_lesson.validate_units(PLUGIN_ROOT / "skills" / "learn" / "assets" / "units-template", plan)[0]
        self.assertTrue(all("tradeoff" not in e for e in errors), errors)

    def test_variation_field_errors(self):
        plan = self.plan15()
        boundary = plan["sections"][0]["concepts"][0]
        boundary["contrast"] = {"with": "learning-design.system-boundary", "differs_in": "x"}
        boundary["cases"] = [boundary["cases"][0]]
        boundary["ontology"] = "thing"
        plan["sections"][0]["tradeoffs"][1]["sides"] = plan["sections"][0]["tradeoffs"][1]["sides"][:1]
        errors = "\n".join(validate_lesson.validate_plan(plan))
        for needle in ("contrast.with must name another concept", "exactly 2 cases", "ontology must be one of", "exactly 2 sides"):
            self.assertIn(needle, errors)
        old = self.plan15()
        old["schema_version"] = "1.4"
        errors = "\n".join(validate_lesson.validate_plan(old))
        self.assertIn("require schema_version '1.5'", errors)
        self.assertIn("objects need schema 1.5", errors)

    def test_sub_sections_and_review_courses(self):
        plan = self.plan15()
        second = json.loads(json.dumps(plan["sections"][0]))
        second["id"], second["depends_on"] = "s01.1", ["s01"]
        second["parent_section"] = {"lesson_id": plan["lesson_id"], "section_id": "s01"}
        plan["sections"][0]["new_problem"], second["new_problem"] = "边界之内还有什么要深化", None
        plan["sections"].append(second)
        self.assertEqual(validate_lesson.validate_plan(plan), [])
        self.assertIn("子节，深化 sample-guided-lesson 的 s01", lesson_section.render_section(plan, "s01.1"))
        self.assertEqual(mrg_export.export(plan)[0]["sections"][1]["parent_section"]["section_id"], "s01")
        plan["sections"][0]["parent_section"] = {"lesson_id": plan["lesson_id"], "section_id": "s01.1"}
        self.assertTrue(any("cycle" in e for e in validate_lesson.validate_plan(plan)))
        plan["sections"][0].pop("parent_section")
        second["parent_section"] = {"lesson_id": "other-course", "section_id": "u02"}
        self.assertTrue(any("neither this course nor one listed in review_of" in e for e in validate_lesson.validate_plan(plan)))

        review = self.plan15()
        review["shape"], review["review_of"], review["coverage"] = "review", ["tee-skeleton-1", "other-course"], []
        review["sections"][0]["parent_section"] = {"lesson_id": "other-course", "section_id": "u02"}
        errors = validate_lesson.validate_plan(review)
        self.assertTrue(any("review_kind must be one of" in e for e in errors), errors)
        review["sections"][0]["review_kind"] = "repeat"
        self.assertEqual(validate_lesson.validate_plan(review), [])   # empty coverage is fine: the material is the reviewed courses
        self.assertIn("复习节，重访 other-course 的 u02", lesson_section.render_section(review, "s01"))
        linear_kind = self.plan15()
        linear_kind["sections"][0]["review_kind"] = "repeat"
        self.assertTrue(any("only allowed in a review course" in e for e in validate_lesson.validate_plan(linear_kind)))
        self.assertEqual(mrg_export.export(review)[0]["review_of"], ["tee-skeleton-1", "other-course"])
        review["review_of"] = [review["lesson_id"]]
        self.assertTrue(any("must not contain this course" in e for e in validate_lesson.validate_plan(review)))
        review["review_of"] = ["other-course"]
        review["probe"] = None
        review["sections"][0]["probe"] = {"prompt": "p", "criteria": [{"id": "p1", "text": "t", "layer": "mechanism"}]}
        self.assertTrue(any("probe is only allowed in skeleton courses" in e for e in validate_lesson.validate_plan(review)))
        linear = self.plan15()
        linear["review_of"] = ["x"]
        self.assertTrue(any("only allowed when shape = review" in e for e in validate_lesson.validate_plan(linear)))

    def test_prerequisite_clusters_may_carry_a_dependency_kind(self):
        plan = json.loads((PLUGIN_ROOT / "skills" / "learn" / "assets" / "prerequisite-plan-template.json").read_text(encoding="utf-8"))
        plan["prerequisites"][0]["dependency_kind"] = "tool"
        self.assertEqual(validate_prerequisites.validate_plan(plan), [])
        plan["prerequisites"][0]["dependency_kind"] = "skill"
        self.assertTrue(any("dependency_kind must be one of" in e for e in validate_prerequisites.validate_plan(plan)))

    def test_review_units_must_not_repeat_the_reviewed_solution_or_mechanism(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reviewed = load_template()
            (root / "reviewed.json").write_text(json.dumps(reviewed, ensure_ascii=False), encoding="utf-8")
            review = self.plan15()
            review["lesson_id"], review["shape"], review["review_of"], review["coverage"] = "sample-review-1", "review", ["sample-guided-lesson"], []
            section = review["sections"][0]
            section["parent_section"], section["review_kind"] = {"lesson_id": "sample-guided-lesson", "section_id": "s01"}, "repeat"
            section["solution"], section["mechanism"] = "换一个情境重述：先划定范围，再把范围内的步骤排成流程", "在新情境里，地图仍然是把细节挂到位置上的工具"
            self.assertEqual(validate_lesson.validate_plan(review), [])
            units = root / "units"
            units.mkdir()
            template = (PLUGIN_ROOT / "skills" / "learn" / "assets" / "units-template" / "s01.md").read_text(encoding="utf-8")
            leaky = template + "\n\n" + reviewed["sections"][0]["mechanism"] + "。\n"  # the reviewed mechanism sentence reappears verbatim
            (units / "s01.md").write_text(leaky, encoding="utf-8")
            errors, warnings = validate_lesson.validate_units(units, review, [root / "reviewed.json"])
            self.assertTrue(any("repeats the reviewed section" in e for e in errors), errors)
            (units / "s01.md").write_text(template, encoding="utf-8")  # reworded in the template: no verbatim sentence
            errors, warnings = validate_lesson.validate_units(units, review, [root / "reviewed.json"])
            self.assertFalse(any("repeats the reviewed section" in e for e in errors), errors)
            _, warnings = validate_lesson.validate_units(units, review, None)
            self.assertTrue(any("--reviewed" in w for w in warnings))


class ReviewOutlineTests(_StoreHelpers, unittest.TestCase):
    def test_review_outline_groups_weak_items_by_section_and_gates_sub_units(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as temporary:
            store = self._store(Path(temporary))
            wrong = {"id": "p-w", "text": "边界是从地图里读出来的", "status": "wrong", "concept_ids": ["learning-design.system-boundary"]}
            self._append(store, "2026-09-01T10:00:00Z", "checkpoint", "mastered", depth="mechanism", props=[wrong])
            state = learner_state_build.build(store, now=datetime(2026, 9, 2, tzinfo=timezone.utc), tz=timezone.utc)
            store_init.atomic_write(store / "learner-state.json", state)
            result = review_outline.outline(store, ["sample-guided-lesson"])
            self.assertEqual(result["reviewed"][0]["lesson_id"], "sample-guided-lesson")
            cluster = result["clusters"][0]
            self.assertEqual(cluster["section_id"], "s01")
            self.assertEqual([r["kind"] for r in cluster["reasons"]], ["error_proposition"])
            self.assertEqual(result["stable_sections"], [])  # only immediate evidence so far
            # two delayed successes on every core concept, one reaching rationale → the section may grow a sub-section
            self._append(store, "2026-09-03T10:00:00Z", "review", "mastered", depth="rationale")
            self._append(store, "2026-09-05T10:00:00Z", "review", "mastered", depth="mechanism")
            state = learner_state_build.build(store, now=datetime(2026, 9, 6, tzinfo=timezone.utc), tz=timezone.utc)
            self.assertEqual(state["concepts"]["learning-design.macro-map"]["delayed_successes"], 2)
            store_init.atomic_write(store / "learner-state.json", state)
            result = review_outline.outline(store, ["sample-guided-lesson"])
            self.assertEqual([s["section_id"] for s in result["stable_sections"]], ["s01"])
            self.assertEqual(result["stable_sections"][0]["listed_concept_ids"], ["learning-design.appendix"])
            self.assertEqual(result["rules"]["sub_units_per_review"], 1)
            with self.assertRaises(ValueError):
                review_outline.outline(store, ["no-such-course"])


class FactCardTests(_StoreHelpers, unittest.TestCase):
    def test_cards_come_from_fact_and_listed_concepts_and_recall_touches_one_concept(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as temporary:
            store = self._store(Path(temporary))
            result = cards.build(store, "sample-guided-lesson")
            self.assertEqual(sorted(result["added"]), ["learning-design.appendix", "learning-design.system-boundary"])  # listed + fact; never mechanism
            self.assertEqual(cards.build(store, "sample-guided-lesson")["added"], [])  # idempotent
            data = cards.load_cards(store, "sample-guided-lesson")
            card = next(c for c in data["cards"] if c["concept_id"] == "learning-design.system-boundary")
            self.assertEqual((card["section_id"], card["layer"]), ("s01", "fact"))
            self.assertTrue(card["answer"])
            now = datetime(2026, 9, 10, tzinfo=timezone.utc)
            items = cards.due(store, ["sample-guided-lesson"], now, 5)
            self.assertEqual([i["reason"] for i in items], ["never recalled", "never recalled"])

            def recall(at, verdict, cid="learning-design.system-boundary"):
                event = lrg_record.build_event(
                    lesson_id="sample-guided-lesson", section_id="s01", kind="recall", attempt_number=1, response="r", feedback="",
                    verdict=verdict, confidence=None, criteria_met=[], depth_reached="fact", extraction=None, comparison=None,
                    elapsed_seconds=None, target_concept_ids=[cid])
                event["at"] = at
                lrg_record.append_event(store, "sample-guided-lesson", event)

            with self.assertRaises(ValueError):
                lrg_record.build_event(lesson_id="l", section_id="s", kind="recall", attempt_number=1, response="", feedback="",
                                       verdict="mastered", confidence=None, criteria_met=[], depth_reached=None,
                                       extraction=None, comparison=None, elapsed_seconds=None)
            recall("2026-09-10T10:00:00Z", "mastered")
            items = cards.due(store, ["sample-guided-lesson"], datetime(2026, 9, 12, tzinfo=timezone.utc), 5)
            self.assertEqual([i["concept_id"] for i in items], ["learning-design.appendix"])  # the recalled card waits 7 days
            items = cards.due(store, ["sample-guided-lesson"], datetime(2026, 9, 18, tzinfo=timezone.utc), 5)
            self.assertEqual({i["concept_id"] for i in items}, {"learning-design.appendix", "learning-design.system-boundary"})
            recall("2026-09-18T10:00:00Z", "retry")
            items = cards.due(store, ["sample-guided-lesson"], datetime(2026, 9, 18, 12, tzinfo=timezone.utc), 5)
            self.assertIn("last recall was retry", [i["reason"] for i in items])
            # the recall events touched only their concept: the section's mechanism concept has no attempts
            state = learner_state_build.build(store, now=datetime(2026, 9, 19, tzinfo=timezone.utc), tz=timezone.utc)
            self.assertNotIn("learning-design.macro-map", state["concepts"])
            boundary = state["concepts"]["learning-design.system-boundary"]
            self.assertEqual((boundary["attempts"], boundary["last_verdict"], boundary["depth_max"]), (2, "retry", "fact"))
            self.assertEqual(cards.lesson_ids_with_cards(store), ["sample-guided-lesson"])


class DiagramTests(unittest.TestCase):
    def test_diagrams_use_public_fields_only_and_the_outline_must_carry_the_chain(self):
        plan = load_template()
        plan["sections"] = [dict(plan["sections"][0], id="s01"), dict(plan["sections"][0], id="s02", title="第二节", depends_on=["s01"]),
                            dict(plan["sections"][0], id="s03", title="第三节", depends_on=["s01"])]
        plan["deferred"] = [{"type": "section", "id": "s03", "reason": "略过"}]
        chain = diagram.chain(plan)
        self.assertTrue(chain.startswith("```mermaid\nflowchart TD") and chain.endswith("```"))
        self.assertIn('S_s01["1 从线性材料到总体结构"]', chain)
        self.assertIn("S_s01 --> S_s02", chain)
        self.assertNotIn("S_s03[", chain)                       # deferred sections are not drawn
        self.assertIn("本次略过：s03", chain)
        for hidden in (plan["sections"][0]["meaning"], plan["sections"][0]["checkpoint"]["criteria"][0]["text"]):
            self.assertNotIn(hidden, chain)
        system = diagram.system(plan)
        self.assertIn('M1["输入范围"]', system)
        self.assertIn("M4 --> M5", system)
        graph = diagram.section_graph(plan, "s01")
        self.assertIn("-- depends_on -->", graph)
        self.assertIn("问题链（supporting）", graph)
        plan["relations"][0]["layer"] = "rationale"
        self.assertIn("没有公开层的关系边", diagram.section_graph(plan, "s01"))   # rationale-layer edges are never drawn
        with self.assertRaises(ValueError):
            diagram.section_graph(plan, "s99")
        with self.assertRaises(ValueError):
            diagram.system(dict(plan, big_picture={"system_map": []}))

        outline = (PLUGIN_ROOT / "skills" / "learn" / "assets" / "outline-template.md").read_text(encoding="utf-8")
        base = load_template()
        self.assertEqual(validate_lesson.validate_outline(outline, base), [])
        stripped = validate_lesson.MERMAID_BLOCK.sub("", outline)
        errors = validate_lesson.validate_outline(stripped, base)
        self.assertTrue(any("mermaid diagram of the problem chain" in e for e in errors), errors)
        old = dict(base, schema_version="1.2")
        old["sections"][0]["concepts"][0] = {k: v for k, v in old["sections"][0]["concepts"][0].items() if k not in ("contrast", "cases", "ontology")}
        self.assertEqual(validate_lesson.validate_outline(stripped, old), [])   # older courses are not asked for a diagram
        two = load_template()
        two["sections"].append(dict(two["sections"][0], id="s02", title="没画进图的节", depends_on=["s01"]))
        two["sections"][0]["new_problem"] = "下一节"
        errors = validate_lesson.validate_outline(outline + "\n第二节标题：没画进图的节\n", two)
        self.assertTrue(any("does not show section 's02'" in e for e in errors), errors)


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


class ReleasePackagingTests(unittest.TestCase):
    def test_standalone_skill_is_renamed_and_self_contained(self):
        release = load_module("package_release", PLUGIN_ROOT.parent)
        with tempfile.TemporaryDirectory() as temporary:
            folder = release.build_standalone(Path(temporary))
            self.assertEqual(folder.name, "whetstone-learn")
            self.assertEqual(release.check_standalone(folder), [])
            head = (folder / "SKILL.md").read_text(encoding="utf-8")[:1200]
            self.assertIn("\nname: whetstone-learn\n", head)
            self.assertIn("description: " + release.STANDALONE_DESCRIPTION, head)
            self.assertTrue((folder / "LICENSE").is_file() and (folder / "README.md").is_file())
            self.assertIn(release.version(), (folder / "README.md").read_text(encoding="utf-8"))
            plan_template = (folder / "assets" / "learning-plan-template.md").read_text(encoding="utf-8")
            self.assertIn("/whetstone-learn 学习", plan_template)
            self.assertEqual(sorted(p.name for p in (folder / "scripts").glob("*.py")), sorted(p.name for p in (PLUGIN_ROOT / "skills" / "learn" / "scripts").glob("*.py")))

