from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from _support import EXAMPLE_ROOT, PLUGIN_ROOT, TEMPLATE_PLAN, load_module, lrg_record, score_pack, store_init

score_all = load_module("score_all", PLUGIN_ROOT / "evals")
difficulty_digest = load_module("difficulty_digest", PLUGIN_ROOT / "evals")


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

    def test_organisation_metrics_absent_fields_do_not_crash(self):
        empty = score_pack.organisation_metrics({})
        self.assertEqual(empty, {"section_kinds": {}, "system_map": {"present": False, "components": 0},
                                 "positioned_sections": 0, "mean_steps_per_section": None})
        self.assertEqual(score_pack.organisation_metrics({"sections": None, "big_picture": "x"})["positioned_sections"], 0)

    def test_organisation_metrics_counts_schema_1_6_fields(self):
        plan = {
            "big_picture": {"system_map": {"components": [{"id": "a"}, {"id": "b"}], "links": []}},
            "sections": [
                {"kind": "process", "position": "a", "steps": [{}, {}, {}]},
                {"kind": "process", "steps": [{}]},
                {"kind": "concept", "position": "b"},
                "not-a-section",
            ],
        }
        metrics = score_pack.organisation_metrics(plan)
        self.assertEqual(metrics["section_kinds"], {"process": 2, "concept": 1})
        self.assertEqual(metrics["system_map"], {"present": True, "components": 2})
        self.assertEqual(metrics["positioned_sections"], 2)
        self.assertEqual(metrics["mean_steps_per_section"], 2.0)
        self.assertEqual(score_pack.organisation_metrics({"big_picture": {"system_map": ["x", "y"]}})["system_map"],
                         {"present": True, "components": 2})

    def test_schema_1_6_warnings_are_counted_as_the_validator_cli_counts_them(self):
        # 2026-09-30 DeepSeek build: validate_lesson.py printed 1 warning, score_pack recorded 0.
        plan = json.loads((PLUGIN_ROOT / "skills" / "learn" / "assets" / "structure-example" / "lesson-plan.json")
                          .read_text(encoding="utf-8"))
        system_map = plan["big_picture"]["system_map"]
        system_map["components"] = [c for c in system_map["components"] if c["id"] != "example.accelerator"]
        system_map["links"] = [l for l in system_map["links"] if "example.accelerator" not in (l["from"], l["to"])]
        with tempfile.TemporaryDirectory() as temporary:
            pack = Path(temporary)
            (pack / "lesson-plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            metrics = score_pack.build_metrics(pack, None, None)
        self.assertEqual(metrics["validator_errors"], 0, metrics["errors"])
        self.assertEqual(metrics["validator_warnings"], 1)
        self.assertIn("not on the system map", metrics["warnings"][0])

    def test_shape_metrics_flag_checklist_prompts_deep_sections_and_final_coverage(self):
        crit = lambda n: [{"id": f"c{i}", "text": f"标准{i}", "layer": "mechanism"} for i in range(n)]
        plan = {
            "sections": [
                {"id": "s01", "checkpoint": {"prompt": "为什么 A？B 又怎样？", "criteria": crit(2)},
                 "concepts": [{"id": "a", "name": "多重检验", "role": "core"},
                              {"id": "b", "name": "样本外", "role": "core"},
                              {"id": "c", "name": "数据窥探", "role": "supporting",
                               "check": {"prompt": "?", "criteria": crit(3)}}]},
                {"id": "s02", "checkpoint": {"prompt": "合上材料，解释前视偏差。", "criteria": crit(3)},
                 "concepts": [{"id": "d", "name": "前视", "aliases": ["前视偏差"], "role": "core"}]},
                {"id": "s03", "checkpoint": {"prompt": "解释幸存者。", "criteria": crit(3)},
                 "concepts": [{"id": "e", "name": "幸存者偏差", "role": "core"}]},
                {"id": "s04", "checkpoint": {"prompt": "讲一遍流程。", "criteria": crit(1)}, "concepts": []},
            ],
            "relations": [{"from": "c", "to": "b"}, {"from": "b", "to": "a"}, {"from": "a", "to": "d"},
                          {"from": "d", "to": "e"}, {"from": "e", "to": "d"}],
            "final_challenge": {"prompt": "拿到一份报告", "criteria": ["指出前视偏差", "说出多重检验的惩罚"]},
        }
        with tempfile.TemporaryDirectory() as temporary:
            units = Path(temporary) / "units"
            metrics = score_pack.shape_metrics(plan, units)
            self.assertIsNone(metrics["units_turn_block_close"])
            units.mkdir()
            (units / "s01.md").write_text("# s01\n\n## 轮到你解释\n\n合上本文档作答：…\n\n## 来源\n", encoding="utf-8")
            (units / "s02.md").write_text("# s02\n\n合上\n\n## 轮到你解释\n\n解释前视偏差。\n", encoding="utf-8")
            self.assertEqual(score_pack.shape_metrics(plan, units)["units_turn_block_close"], {"with_close": 1, "units": 2})
        self.assertEqual(metrics["prompt_questions_per_section"], {"s01": 2, "s02": 0, "s03": 0, "s04": 0})
        self.assertEqual(metrics["checklist_prompt_sections"], ["s01"])
        self.assertEqual(metrics["criteria_incl_checks_per_section"], {"s01": 5, "s02": 3, "s03": 3, "s04": 1})
        self.assertEqual(metrics["intra_section_relation_depth"], {"s01": 2, "s02": 0, "s03": 0, "s04": 0})
        self.assertEqual(metrics["final_core_coverage"], {"sections_hit": 2, "sections": 3})
        self.assertEqual(score_pack.shape_metrics({}, Path("/nonexistent"))["final_core_coverage"],
                         {"sections_hit": 0, "sections": 0})

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

    def test_an_unreadable_baseline_reports_an_error_instead_of_a_traceback(self):
        import subprocess, sys
        script = PLUGIN_ROOT / "evals" / "score_pack.py"
        with tempfile.TemporaryDirectory() as temporary:
            baseline = Path(temporary) / "baseline.json"
            baseline.write_text("hello {", encoding="utf-8")
            done = subprocess.run([sys.executable, str(script), str(EXAMPLE_ROOT), "--baseline", str(baseline)],
                                  capture_output=True, text=True)
            self.assertEqual(done.returncode, 1)
            self.assertTrue(done.stderr.startswith("ERROR: "), done.stderr)
            self.assertNotIn("Traceback", done.stderr)
            self.assertIn("sections", done.stdout)  # the pack itself was still scored and printed

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

    def test_cli_prints_n_a_when_no_checkpoint_has_a_duration(self):
        import subprocess, sys
        lesson_id = json.loads((EXAMPLE_ROOT / "lesson-plan.json").read_text(encoding="utf-8"))["lesson_id"]
        with tempfile.TemporaryDirectory() as temporary:
            store = Path(temporary) / "store"
            store_init.init_store(store, [])
            event = lrg_record.build_event(
                lesson_id=lesson_id, section_id="s01", kind="review", attempt_number=1, response="r", feedback="",
                verdict="mastered", confidence=None, criteria_met=[], depth_reached="mechanism", extraction=None,
                comparison={"propositions": [], "diff": {"conflict": []}, "feedback_priority": []}, elapsed_seconds=None,
            )
            lrg_record.append_event(store, lesson_id, event)
            done = subprocess.run([sys.executable, str(PLUGIN_ROOT / "evals" / "score_pack.py"), str(EXAMPLE_ROOT), "--store", str(store)],
                                  capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("median checkpoint n/a,", done.stdout)
            self.assertNotIn("Nones", done.stdout)



class DifficultyDigestTests(unittest.TestCase):
    """What each section asks the learner to rebuild: added prerequisite material may add to it, never lower it."""

    def plan(self) -> dict:
        return json.loads(TEMPLATE_PLAN.read_text(encoding="utf-8"))

    def test_digest_counts_criteria_layers_core_ids_and_checks(self):
        digest = difficulty_digest.digest(self.plan())
        s01 = digest["sections"]["s01"]
        self.assertEqual(s01["n_criteria"], 3)
        self.assertEqual(s01["layers"], {"mechanism": 2, "rationale": 1})
        self.assertEqual(s01["core_ids"], ["learning-design.macro-map", "learning-design.system-boundary"])
        self.assertEqual(len(s01["criteria_sha"]), 3)
        self.assertIn("learning-design.problem-chain", s01["checks"])
        self.assertEqual(digest["final"]["n_criteria"], 2)
        self.assertEqual(digest["final"]["layers"], {"unset": 2})
        self.assertEqual(difficulty_digest.compare(digest, difficulty_digest.digest(self.plan())), ([], []))

    def test_every_kind_of_reduction_is_listed_and_additions_are_allowed(self):
        before = difficulty_digest.digest(self.plan())
        cases = {
            "criteria 3 → 2": lambda p: p["sections"][0]["checkpoint"]["criteria"].pop(),
            "rationale criteria 1 → 0": lambda p: p["sections"][0]["checkpoint"]["criteria"][2].update(layer="fact"),
            "prompt changed": lambda p: p["sections"][0]["checkpoint"].update(prompt="更容易的问题"),
            "criterion text changed or removed (#2)": lambda p: p["sections"][0]["checkpoint"]["criteria"][1].update(text="改写"),
            "core concepts removed: learning-design.macro-map": lambda p: p["sections"][0]["concepts"][1].update(role="supporting"),
            "check[learning-design.problem-chain]: removed": lambda p: p["sections"][0]["concepts"][2].pop("check"),
            "final_challenge: criteria 2 → 1": lambda p: p["final_challenge"]["criteria"].pop(),
            "s01: removed": lambda p: p["sections"].pop(0),
        }
        for expected, change in cases.items():
            with self.subTest(expected):
                plan = self.plan()
                change(plan)
                reductions, _ = difficulty_digest.compare(before, difficulty_digest.digest(plan))
                self.assertTrue(any(expected in line for line in reductions), reductions)
        plan = self.plan()
        plan["sections"][0]["checkpoint"]["criteria"].append({"id": "c4", "text": "验收：用新例子复述", "layer": "mechanism"})
        plan["sections"][0]["concepts"].append({"id": "x.bridge", "name": "补", "role": "bridge", "explanation": "两三句"})
        reductions, additions = difficulty_digest.compare(before, difficulty_digest.digest(plan))
        self.assertEqual(reductions, [])
        self.assertEqual(additions, ["s01: criteria 3 → 4"])

    def test_cli_exit_status_is_1_on_a_reduction_and_0_otherwise(self):
        import subprocess, sys
        script = PLUGIN_ROOT / "evals" / "difficulty_digest.py"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline = root / "digest.json"
            done = subprocess.run([sys.executable, str(script), str(TEMPLATE_PLAN), "--output", str(baseline)], capture_output=True, text=True)
            self.assertEqual((done.returncode, done.stdout, done.stderr), (0, "", ""))
            done = subprocess.run([sys.executable, str(script), str(TEMPLATE_PLAN), "--against", str(baseline)], capture_output=True, text=True)
            self.assertEqual((done.returncode, done.stdout), (0, "0 reductions, 0 additions\n"))
            plan = self.plan()
            plan["sections"][0]["checkpoint"]["criteria"].pop()
            (root / "lesson-plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            done = subprocess.run([sys.executable, str(script), str(root / "lesson-plan.json"), "--against", str(baseline)], capture_output=True, text=True)
            self.assertEqual(done.returncode, 1)
            self.assertIn("REDUCED s01: criteria 3 → 2", done.stdout)
            done = subprocess.run([sys.executable, str(script), str(TEMPLATE_PLAN), "--against", str(TEMPLATE_PLAN)], capture_output=True, text=True)
            self.assertEqual(done.returncode, 2)
            self.assertTrue(done.stderr.startswith("ERROR: "))
            self.assertNotIn("Traceback", done.stderr)

    def test_score_pack_difficulty_fields_and_baseline_diff(self):
        plan = self.plan()
        metrics = score_pack.difficulty_metrics(plan, Path("/nonexistent"), 0)
        self.assertEqual(metrics["criteria_layers_per_section"]["s01"], {"mechanism": 2, "rationale": 1})
        self.assertEqual(set(metrics["checkpoint_digest"]), {s["id"] for s in plan["sections"]} | {"final_challenge"})
        self.assertTrue(all(isinstance(v, int) for v in metrics["checkpoint_digest"].values()))
        self.assertEqual(set(metrics["bridge_items_per_section"].values()), {0})
        self.assertIsNone(metrics["bridge_share"])
        plan["sections"][0]["checkpoint"]["criteria"][2]["layer"] = "fact"
        changed = score_pack.difficulty_metrics(plan, Path("/nonexistent"), 0)
        lines = score_pack.diff_against({"build": metrics}, {"build": changed})
        self.assertEqual([line.split(":")[0].strip() for line in lines],
                         ["build.criteria_layers_per_section.s01.fact", "build.criteria_layers_per_section.s01.rationale"])
        plan["sections"][0]["checkpoint"]["prompt"] = "更容易的问题"
        lines = score_pack.diff_against({"build": metrics}, {"build": score_pack.difficulty_metrics(plan, Path("/nonexistent"), 0)})
        self.assertIn("build.checkpoint_digest.s01", [line.split(":")[0].strip() for line in lines])

    def test_bridge_share_counts_bridge_explanations_and_bridge_sections_against_unit_text(self):
        plan = {"sections": [
            {"id": "s01", "concepts": [{"id": "a", "role": "bridge", "explanation": "x" * 20}, {"id": "b", "role": "core"}]},
            {"id": "s02", "bridge_for": "s03", "concepts": []},
            {"id": "s03", "concepts": []},
        ]}
        with tempfile.TemporaryDirectory() as temporary:
            units = Path(temporary)
            (units / "s02.md").write_text("y" * 30, encoding="utf-8")
            metrics = score_pack.difficulty_metrics(plan, units, 200)
        self.assertEqual(metrics["bridge_items_per_section"], {"s01": 1, "s02": 0, "s03": 0})
        self.assertEqual(metrics["bridge_share"], 0.25)


class BatchScoringTests(unittest.TestCase):
    def _template_pack(self, pack: Path, sections=None) -> None:
        pack.mkdir(parents=True)
        plan = json.loads(TEMPLATE_PLAN.read_text(encoding="utf-8"))
        if sections is not None:
            plan["sections"] = sections
        (pack / "lesson-plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")

    def _tree(self, root: Path) -> None:
        self._template_pack(root / "good")
        broken = root / "broken"
        broken.mkdir()
        (broken / "lesson-plan.json").write_text("hello {", encoding="utf-8")
        listed = root / "listed"
        listed.mkdir()
        (listed / "lesson-plan.json").write_text("[]", encoding="utf-8")
        half = root / "results" / "run1" / "half-built"
        half.mkdir(parents=True)
        (half / "sources.json").write_text("{}", encoding="utf-8")
        self._template_pack(root / "results" / "run1" / "doc-learning-layers")  # 1 section, material expects 3–6
        self._template_pack(root / "no-sections", sections=[])
        (root / "notes").mkdir()
        (root / "notes" / "readme.md").write_text("not a course directory", encoding="utf-8")

    def test_every_course_directory_gets_a_status_and_bad_ones_a_reason(self):
        expectations = score_all.load_expectations(PLUGIN_ROOT / "evals" / "materials.json")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._tree(root)
            packs = score_all.find_course_dirs(root)
            self.assertEqual([p.relative_to(root).as_posix() for p in packs],
                             ["broken", "good", "listed", "no-sections", "results/run1/doc-learning-layers", "results/run1/half-built"])
            rows = {p.relative_to(root).as_posix(): score_all.score_one(p, None, expectations, None) for p in packs}
        self.assertEqual(rows["good"]["status"], "ok")
        self.assertEqual(rows["good"]["result"]["build"]["sections"], 1)
        self.assertEqual(rows["broken"]["status"], "skipped")
        self.assertTrue(rows["broken"]["note"].startswith("invalid JSON"), rows["broken"]["note"])
        self.assertEqual((rows["listed"]["status"], rows["listed"]["note"]), ("skipped", "lesson-plan.json is not a JSON object"))
        self.assertEqual((rows["results/run1/half-built"]["status"], rows["results/run1/half-built"]["note"]), ("skipped", "no lesson-plan.json"))
        self.assertEqual(rows["no-sections"]["status"], "fail")
        self.assertIn("validator errors, first:", rows["no-sections"]["note"])
        material = rows["results/run1/doc-learning-layers"]
        self.assertEqual(material["status"], "fail")
        self.assertIn("expectation not met: sections_in_range", material["note"])

    def test_cli_exit_status_tracks_the_worst_row_and_never_prints_a_traceback(self):
        import subprocess, sys
        script = PLUGIN_ROOT / "evals" / "score_all.py"
        with tempfile.TemporaryDirectory() as temporary:
            clean, mixed, out = Path(temporary) / "clean", Path(temporary) / "mixed", Path(temporary) / "out"
            self._template_pack(clean / "good")
            self._tree(mixed)
            done = subprocess.run([sys.executable, str(script), str(clean), "--output-dir", str(out)], capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("1 course directories: 1 ok, 0 fail, 0 skipped", done.stdout)
            written = json.loads((out / "clean--good.json").read_text(encoding="utf-8"))
            self.assertEqual(written["build"]["sections"], 1)
            done = subprocess.run([sys.executable, str(script), str(mixed)], capture_output=True, text=True)
            self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
            self.assertIn("6 course directories: 1 ok, 2 fail, 3 skipped", done.stdout)
            self.assertNotIn("Traceback", done.stdout + done.stderr)
            done = subprocess.run([sys.executable, str(script), str(mixed / "notes")], capture_output=True, text=True)
            self.assertEqual(done.returncode, 2)
            self.assertTrue(done.stderr.startswith("ERROR: no course directory"), done.stderr)
            done = subprocess.run([sys.executable, str(script), str(Path(temporary) / "missing")], capture_output=True, text=True)
            self.assertEqual(done.returncode, 2)
            self.assertTrue(done.stderr.startswith("ERROR: not a directory"), done.stderr)

    def test_default_run_scores_the_example_and_names_the_unbuilt_materials(self):
        import subprocess, sys
        with tempfile.TemporaryDirectory() as temporary:
            done = subprocess.run([sys.executable, str(PLUGIN_ROOT / "evals" / "score_all.py"), "--output-dir", temporary],
                                  capture_output=True, text=True, cwd=PLUGIN_ROOT)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertRegex(done.stdout, r"\nok +examples/project-consensus +1\.0 +8 ")
            self.assertNotIn("prerequisites", done.stdout)
            self.assertIn("no scored course directory (build them into evals/results/<run>/<id>/): doc-learning-layers", done.stdout)
            scored = json.loads((Path(temporary) / "examples--project-consensus.json").read_text(encoding="utf-8"))
        baseline = json.loads((PLUGIN_ROOT / "evals" / "results" / "example-baseline.json").read_text(encoding="utf-8"))
        self.assertEqual(score_pack.diff_against(baseline, scored), [])

    def _run(self, cwd: Path, *args: str):
        import subprocess, sys
        return subprocess.run([sys.executable, str(PLUGIN_ROOT / "evals" / "score_all.py"), *args], capture_output=True, text=True, cwd=cwd)

    def test_baseline_dir_diffs_each_directory_and_marks_the_ones_without_a_baseline(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            self._template_pack(work / "tree" / "changed")
            self._template_pack(work / "tree" / "same")
            self.assertEqual(self._run(work, "tree", "--output-dir", "base").returncode, 0)
            edited = json.loads((work / "base" / "tree--changed.json").read_text(encoding="utf-8"))
            edited["build"]["sections"] = 3
            (work / "base" / "tree--changed.json").write_text(json.dumps(edited), encoding="utf-8")
            self._template_pack(work / "tree" / "new")
            # the same directory as --output-dir: baselines are read before this run overwrites them
            done = self._run(work, "tree", "--baseline-dir", "base", "--output-dir", "base")
            rewritten = json.loads((work / "base" / "tree--changed.json").read_text(encoding="utf-8"))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(done.stderr, "")
        self.assertIn("\nvs baseline base:\n"
                      "  tree/changed: 1 changed\n"
                      "    build.sections: 3 → 1\n"
                      "  tree/new: no baseline\n"
                      "  tree/same: no change\n"
                      "baseline: 1 no change, 1 changed, 1 no baseline, 0 bad\n", done.stdout)
        self.assertEqual(rewritten["build"]["sections"], 1)
        self.assertEqual(score_pack.diff_against(edited, rewritten), ["  build.sections: 3 → 1"])  # the same diff score_pack --baseline prints

    def test_a_bad_baseline_file_is_an_error_with_exit_1_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            for name in ("broken", "listed", "fine"):
                self._template_pack(work / "tree" / name)
            self.assertEqual(self._run(work, "tree", "--output-dir", "base").returncode, 0)
            (work / "base" / "tree--broken.json").write_text("hello {", encoding="utf-8")
            (work / "base" / "tree--listed.json").write_text("[]", encoding="utf-8")
            done = self._run(work, "tree", "--baseline-dir", "base")
            missing = self._run(work, "tree", "--baseline-dir", "nowhere")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertNotIn("Traceback", done.stdout + done.stderr)
        self.assertIn("3 course directories: 3 ok, 0 fail, 0 skipped", done.stdout)
        errors = done.stderr.splitlines()
        self.assertEqual(len(errors), 2, done.stderr)
        self.assertTrue(errors[0].startswith("ERROR: bad baseline base/tree--broken.json: invalid JSON: "), errors[0])
        self.assertEqual(errors[1], "ERROR: bad baseline base/tree--listed.json: not a JSON object")
        self.assertIn("  tree/broken: bad baseline tree--broken.json\n  tree/fine: no change\n", done.stdout)
        self.assertIn("baseline: 1 no change, 0 changed, 0 no baseline, 2 bad", done.stdout)
        self.assertEqual(missing.returncode, 2)
        self.assertEqual(missing.stderr, "ERROR: baseline directory is not a directory: nowhere\n")

    def test_without_baseline_dir_the_output_and_exit_status_are_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            self._template_pack(work / "clean" / "good")
            self._tree(work / "mixed")
            clean = self._run(work, "clean")
            mixed = self._run(work, "mixed")
            (work / "base").mkdir()
            with_flag = self._run(work, "mixed", "--baseline-dir", "base")
        # captured from score_all.py before --baseline-dir existed (f81eed9)
        self.assertEqual((clean.returncode, clean.stderr), (0, ""))
        self.assertEqual(clean.stdout,
                         "status  course directory  schema  sections  relations  errors/warnings  locator hit  unsupported  note\n"
                         "ok      clean/good        1.5     1         1          0/0              -            0.0\n"
                         "1 course directories: 1 ok, 0 fail, 0 skipped\n")
        self.assertEqual((mixed.returncode, mixed.stderr), (1, ""))
        self.assertTrue(mixed.stdout.endswith("6 course directories: 1 ok, 2 fail, 3 skipped\n"), mixed.stdout)
        self.assertNotIn("baseline", mixed.stdout)
        self.assertEqual(with_flag.returncode, 1)
        self.assertTrue(with_flag.stdout.startswith(mixed.stdout), with_flag.stdout)
        self.assertIn("baseline: 0 no change, 0 changed, 3 no baseline, 0 bad", with_flag.stdout)


gap_ledger = load_module("gap_ledger", PLUGIN_ROOT / "evals")


class GapLedgerTests(unittest.TestCase):
    """One case per disposition rule R1–R6 of the gap ledger, plus the 9-section limit and the CLI."""

    PROFILE = "\n".join([
        "## 一、相关背景", "",
        "| 领域 | 自述水平 | 说过的具体概念 | 证据 |",
        "| --- | --- | --- | --- |",
        "| stats | 未接触 | | 自述 |",
        "| code | 听过 | | 自述 |",
        "| finance | 熟练 | 做空 | 自述 |",
        "| finance.basics | 未接触 | | 自述 |",
    ])

    def lesson(self, n=4):
        return {"lesson_id": "demo", "sections": [{"id": f"s{i:02d}"} for i in range(1, n + 1)]}

    def item(self, pid, concept_id, kind="mech", required_by=("s02",), **extra):
        return {"id": pid, "concept_id": concept_id, "dependency_kind": kind, "required_by": list(required_by), **extra}

    def ledger(self, items, mode="auto", n=4, **inputs):
        plan = {"schema_version": "1.1", "lesson_id": "demo", "assessment_mode": mode, "prerequisites": items}
        return gap_ledger.build_ledger(plan, self.lesson(n), inputs.pop("background", self.PROFILE), **inputs)

    def by_id(self, ledger):
        return {i["id"]: (i["disposition"], i["placed_at"], i["rule"]) for i in ledger["items"]}

    def test_r1_known_needs_tier_3_to_drop_the_reminder(self):
        progress = {"competencies": [{"id": "p01", "status": "ready",
                                      "assessment_attempts": [{"at": "2026-09-01T00:00:00Z", "verdict": "ready", "confidence": 5}]}]}
        ledger = self.ledger([self.item("p01", "stats.mean"), self.item("p02", "finance.short-selling", name="做空")],
                             progress=progress)
        self.assertEqual(self.by_id(ledger), {"p01": ("none", None, "R1"), "p02": ("T0", "s02", "R1")})
        self.assertEqual(ledger["items"][0]["evidence"]["tier"], 4)
        self.assertEqual(ledger["items"][1]["evidence"], {"source": "profile:自述", "tier": 1, "confidence": 3})

    def test_r2_scope_defers_to_an_earlier_course_or_raises_to_t3(self):
        plan = {"courses": [{"id": "intro", "core": ["stats.sqrt-time"]}, {"id": "demo"},
                            {"id": "later", "needs": ["stats.std"]}]}
        ledger = self.ledger([
            self.item("p01", "stats.sqrt-time", "tool"),
            self.item("p02", "stats.std"),
            self.item("p03", "stats.random", "tool", depends_on=["stats.python"]),
            self.item("p04", "code.loop", required_by=["s03"]),
        ], learning_plan=plan)
        self.assertEqual(self.by_id(ledger), {
            "p01": ("defer_to_course", "intro", "R2"),
            "p02": ("T3", "prerequisite-course:p02", "R2"),
            "p03": ("T3", "prerequisite-course:p03", "R2"),
            "p04": ("T1", "s03", "R4"),
        })

    def test_r2_leaves_partial_items_to_r4_even_when_an_earlier_course_teaches_them(self):
        plan = {"courses": [{"id": "intro", "core": ["code.loop"]}, {"id": "demo"}]}
        ledger = self.ledger([self.item("p01", "code.loop")], learning_plan=plan)
        self.assertEqual(self.by_id(ledger), {"p01": ("T1", "s02", "R4")})

    def test_r3_a_missing_definition_is_one_sentence_in_the_first_section_that_needs_it(self):
        ledger = self.ledger([self.item("p01", "finance.basics.strategy", "def", required_by=["s03", "s01"])])
        self.assertEqual(self.by_id(ledger), {"p01": ("T0", "s01", "R3")})

    def test_r4_partial_mechanism_is_a_t1_item_until_the_section_has_three(self):
        items = [self.item(f"p0{i}", f"code.c{i}") for i in range(1, 5)]
        items.append(self.item("p05", "code.c5", required_by=["s01", "s02", "s03"]))
        ledger = self.ledger(items)
        self.assertEqual([d for d, _, _ in self.by_id(ledger).values()], ["T1", "T1", "T1", "T2", "T2"])
        self.assertEqual(ledger["summary"]["t1_per_section"], {"s02": 3})
        self.assertEqual(gap_ledger.check(ledger), [])

    def test_r4_mastered_but_stale_learner_state_reads_as_partial(self):
        state = {"concepts": {"stats.mean": {"attempts": 2, "last_verdict": "mastered", "freshness": "stale",
                                              "evidence_tier": "delayed", "last_evidence_at": "2026-08-01T00:00:00Z"}}}
        ledger = self.ledger([self.item("p01", "stats.mean")], learner_state=state)
        self.assertEqual(self.by_id(ledger), {"p01": ("T1", "s02", "R4")})
        self.assertEqual(ledger["items"][0]["evidence"]["tier"], 3)

    def test_r5_gap_mechanism_is_a_bridge_section_unless_its_cluster_is_too_big(self):
        small = [self.item("p01", "stats.a", cluster="one")]
        big = [self.item(f"q0{i}", f"stats.b{i}", cluster="two") for i in range(1, 5)]
        ledger = self.ledger(small + big)
        self.assertEqual(self.by_id(ledger)["p01"], ("T2", "s02", "R5"))
        self.assertEqual({d for d, _, _ in list(self.by_id(ledger).values())[1:]}, {"T3"})
        self.assertEqual(ledger["summary"]["bridge_sections"], 1)

    def test_r6_unknown_follows_the_assessment_mode(self):
        item = self.item("p01", "physics.force")
        expected = {"always": ("T2", "s02", "R6+R5"), "auto": ("T1", "s02", "R6+R4"), "skip": ("T0", "s02", "R6+R1")}
        for mode, disposition in expected.items():
            with self.subTest(mode=mode):
                ledger = self.ledger([item], mode=mode)
                self.assertEqual(self.by_id(ledger)["p01"], disposition)
                self.assertEqual(ledger["items"][0]["state"], {"always": "gap", "auto": "partial", "skip": "known"}[mode])

    def test_bridge_sections_past_nine_are_raised_to_a_prerequisite_course(self):
        items = [self.item("p01", "stats.a", cluster="one"), self.item("p02", "stats.b", cluster="two"),
                 self.item("p03", "stats.c", cluster="two")]
        ledger = self.ledger(items, n=8)
        self.assertEqual(self.by_id(ledger), {"p01": ("T2", "s02", "R5"),
                                              "p02": ("T3", "prerequisite-course:two", "R5+9"),
                                              "p03": ("T3", "prerequisite-course:two", "R5+9")})
        self.assertEqual(ledger["summary"]["sections"] + ledger["summary"]["bridge_sections"], 9)
        self.assertEqual(gap_ledger.check(ledger), [])

    def test_coverage_is_one_and_check_reports_unknown_sections(self):
        ledger = self.ledger([self.item("p01", "stats.a", required_by=["s99"])])
        self.assertEqual(ledger["summary"]["coverage"], 1.0)
        self.assertEqual(gap_ledger.check(ledger), ["required_by names s99, which is not a section of the lesson plan"])

    def test_cli_exit_codes(self):
        import subprocess, sys
        script = PLUGIN_ROOT / "evals" / "gap_ledger.py"
        prerequisites = PLUGIN_ROOT / "evals" / "prerequisites"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lesson = root / "lesson-plan.json"
            lesson.write_text(json.dumps({"sections": [{"id": "s03"}, {"id": "s05"}]}), encoding="utf-8")
            args = [sys.executable, str(script), str(prerequisites / "prerequisite-plan.json"), str(lesson),
                    "--progress", str(prerequisites / "prerequisite-progress.json"), "--check"]
            done = subprocess.run(args, capture_output=True, text=True)
            self.assertEqual((done.returncode, done.stderr), (0, ""))
            ledger = json.loads(done.stdout)
            self.assertEqual([(i["required_by"], i["disposition"], i["evidence"]["tier"]) for i in ledger["items"]],
                             [(["s03", "s05"], "none", 4), ([], "none", 4)])
            plan = root / "plan.json"
            plan.write_text(json.dumps({"lesson_id": "demo", "prerequisites": [self.item("p01", "stats.a", required_by=["s99"])]}),
                            encoding="utf-8")
            done = subprocess.run([sys.executable, str(script), str(plan), str(lesson), "--check", "--output", str(root / "out.json")],
                                  capture_output=True, text=True)
            self.assertEqual((done.returncode, done.stdout, done.stderr),
                             (1, "", "FAIL: required_by names s99, which is not a section of the lesson plan\n"))
            self.assertTrue((root / "out.json").is_file())
            done = subprocess.run([sys.executable, str(script), str(lesson), str(root / "missing.json")], capture_output=True, text=True)
            self.assertEqual((done.returncode, done.stdout), (2, ""))
            self.assertTrue(done.stderr.startswith("ERROR: "))
