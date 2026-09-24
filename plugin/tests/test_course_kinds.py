from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from _support import (
    SKELETON_OUTLINE,
    STRUCTURE_OUTLINE,
    STRUCTURE_PLAN,
    comparator,
    diagram,
    learning_state,
    lesson_section,
    load_skeleton,
    load_template,
    lrg_record,
    mermaid_fit,
    mrg_export,
    validate_lesson,
)


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

    def test_the_system_map_is_drawn_with_containment_and_labelled_links(self):
        plan = self.plan()
        drawn = diagram.system(plan)
        self.assertIn('subgraph C_org_host["宿主进程"]', drawn)  # parent becomes a subgraph: containment reads as nesting
        self.assertIn('C_org_runtime["运行时"]', drawn)
        self.assertIn('-- "把任务交给它执行" -->', drawn)  # the author's own words, not truncated
        plan["sections"] = plan["sections"][2:]
        plan["big_picture"]["system_map"] = ["提交", "执行", "取回"]
        legacy = diagram.system(plan)
        self.assertIn("flowchart TD", legacy)  # a chain of steps side by side is as wide as the chain is long
        self.assertIn("M1 --> M2", legacy)
        sideways = legacy.replace("flowchart TD", "flowchart LR")
        self.assertLess(mermaid_fit.estimate_width(legacy), mermaid_fit.estimate_width(sideways))

    def test_a_structure_section_draws_only_the_parts_it_places(self):
        plan = self.plan()
        plan["sections"][0]["concepts"] = plan["sections"][0]["concepts"][:2]  # host and runtime, not the accelerator
        drawn = diagram.section_graph(plan, "s01")
        self.assertIn("C_org_runtime", drawn)
        self.assertIn("subgraph C_org_host", drawn)  # the parent is kept so the nesting still reads
        self.assertNotIn("C_org_accelerator", drawn)

    def test_a_process_section_draws_the_run_step_by_step(self):
        drawn = diagram.section_graph(self.plan(), "s02")
        self.assertIn("sequenceDiagram", drawn)
        self.assertIn("participant P_org_host as 宿主进程", drawn)
        self.assertEqual(drawn.index("P_org_host as"), min(drawn.index(f"P_org_{n} as") for n in ("host", "runtime", "accelerator")))
        self.assertIn("P_org_host->>P_org_runtime: 提交任务", drawn)
        self.assertIn("Note over P_org_runtime: 任务进入队列", drawn)
        self.assertNotIn("Note right of", drawn)   # a note to the right of the last actor runs off the diagram

    def test_the_problem_chain_shows_all_three_kinds(self):
        drawn = diagram.chain(self.plan())
        self.assertIn("1 系统由哪些部分组成（结构）", drawn)
        self.assertIn("2 跟随一次任务跑一遍（过程）", drawn)
        self.assertIn("S_s01 --> S_s02", drawn)
        self.assertNotIn("（结构）", drawn.split("S_s03")[1])  # a chain section carries no mark

    def test_the_finish_view_carries_the_map_and_the_section_view_its_position(self):
        plan = self.plan()
        final = lesson_section.render_final(plan)
        self.assertIn("路线重建", final)
        self.assertIn("运行时（`org.runtime`），在 宿主进程 里", final)
        self.assertIn("运行时 → 加速器：把任务交给它执行", final)
        view = lesson_section.render_section(plan, "s01")
        self.assertIn("返回位置", view)
        self.assertIn("宿主进程", view)
        steps_view = lesson_section.render_section(plan, "s02")
        self.assertIn("步骤（过程讲解节", steps_view)
        self.assertIn("宿主进程 → 运行时：提交任务", steps_view)  # names, not concept ids

    def test_the_shipped_structure_example_validates(self):
        plan = json.loads(STRUCTURE_PLAN.read_text(encoding="utf-8"))
        self.assertEqual(validate_lesson.validate_plan(plan), [])
        self.assertEqual(validate_lesson.validate_outline(STRUCTURE_OUTLINE.read_text(encoding="utf-8"), plan), [])
        self.assertEqual([validate_lesson.section_kind(s) for s in plan["sections"]], ["structure", "chain"])
        self.assertIn("subgraph", diagram.system(plan))  # the map is drawn from components, not from a list of steps

    def test_a_skeleton_courses_structure_section_has_no_probe(self):
        plan = self.plan()
        plan["shape"] = "skeleton"
        probe = {"prompt": "不看材料：这一步为什么必要？",
                 "criteria": [{"id": "p1", "text": "说出它回应的限制", "layer": "mechanism"}]}
        for section in plan["sections"]:
            section["probe"] = copy.deepcopy(probe)
        errors = self.errors(plan)  # the structure section's answer is already on the outline's map
        self.assertTrue(any("sections[0].probe is not allowed in a structure section" in e for e in errors), errors)
        del plan["sections"][0]["probe"]
        errors = self.errors(plan)
        self.assertFalse(any(".probe" in e for e in errors), errors)
        del plan["sections"][1]["probe"]  # the process section still needs one: its steps are not on the outline
        self.assertTrue(any("sections[1].probe is required" in e for e in self.errors(plan)), self.errors(plan))

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
