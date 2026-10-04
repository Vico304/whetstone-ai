from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from _support import (
    EXAMPLE_ROOT,
    PLUGIN_ROOT,
    lesson_section,
    load_template,
    mrg_export,
    validate_lesson,
    validate_prerequisites,
)


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

    def test_outline_leak_error_quotes_the_leaked_text(self):
        plan = load_template()
        outline = (PLUGIN_ROOT / "skills" / "learn" / "assets" / "outline-template.md").read_text(encoding="utf-8")
        tradeoff = "先画全局图再讲细节，代价是开头几分钟看不到任何可运行的代码，学习者容易以为这一节只是目录。"
        plan["sections"][0]["tradeoffs"] = [{"text": tradeoff}]
        self.assertEqual(validate_lesson.validate_outline(outline, plan), [])

        leaked = outline + "\n注意：代价是开头几分钟看不到任何可运行的代码！\n"
        errors = validate_lesson.validate_outline(leaked, plan)

        self.assertIn("outline leaks rationale-layer tradeoff from sections[0]: '代价是开头几分钟看不到任何可运行的代码'", errors)

    def test_leaked_fragment_keeps_original_wording_and_truncates(self):
        text = "Deflated Sharpe ratio, PBO and the haircut all answer one question: how many trials did you run?"
        guide = validate_lesson.normalize_text("Ask: How many TRIALS did you run")

        self.assertEqual(validate_lesson.leaked_fragment(text, guide), "how many trials did you run")
        long_guide = validate_lesson.normalize_text(text)
        fragment = validate_lesson.leaked_fragment(text, long_guide)
        self.assertEqual(fragment, text[: validate_lesson.LEAK_FRAGMENT_CHARS] + "…")
        self.assertIsNone(validate_lesson.leaked_fragment(text, validate_lesson.normalize_text("完全无关的大纲")))

    def test_outline_leak_check_ignores_the_sections_own_concept_names(self):
        # A hidden text that names a long concept collided with "the outline must list every concept":
        # listing the name counted as leaking the text (DeepSeek run 2026-10-04, E2, 25 requests).
        plan = load_template()
        outline = (PLUGIN_ROOT / "skills" / "learn" / "assets" / "outline-template.md").read_text(encoding="utf-8")
        name = "Deflated Sharpe 与 PBO"
        plan["sections"][0]["concepts"].append({"id": "learning-design.deflated-sharpe", "name": name})
        plan["sections"][0]["tradeoffs"] = [{"text": f"{name} 只给出过拟合的概率，不告诉你哪一条策略是真的"}]
        outline = outline + f"\n- {name}\n"
        self.assertTrue(validate_lesson.criterion_leaked(f"{name} 只给出过拟合的概率", validate_lesson.normalize_text(outline)))

        self.assertEqual(validate_lesson.validate_outline(outline, plan), [])

        errors = validate_lesson.validate_outline(outline + "它只给出过拟合的概率，不告诉你哪一条策略是真的\n", plan)
        self.assertIn("outline leaks rationale-layer tradeoff from sections[0]: '只给出过拟合的概率，不告诉你哪一条策略是真的'", errors)

        other = load_template()
        other["sections"][0]["tradeoffs"] = plan["sections"][0]["tradeoffs"]
        errors = validate_lesson.validate_outline(outline, other)
        self.assertTrue(any(e.startswith("outline leaks rationale-layer tradeoff from sections[0]: 'Deflated Sharpe 与 PBO") for e in errors), errors)

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


class OrphanConceptTests(unittest.TestCase):
    def test_orphan_core_concepts_are_counted_not_rejected(self):
        plan = load_template()
        self.assertEqual(validate_lesson.orphan_concepts(plan), {"orphans": [], "total": 2})
        plan["sections"][0]["concepts"].append({"id": "learning-design.lonely", "name": "孤概念", "explanation": "没有关系的核心概念",
                                                "layer": "mechanism", "role": "core", "domain_path": ["学习设计"],
                                                "source_refs": plan["sections"][0]["source_refs"]})
        self.assertEqual(validate_lesson.orphan_concepts(plan)["orphans"], ["learning-design.lonely"])
        self.assertEqual(validate_lesson.validate_plan(plan), [])


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
