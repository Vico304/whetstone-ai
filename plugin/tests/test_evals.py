from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from _support import EXAMPLE_ROOT, PLUGIN_ROOT, TEMPLATE_PLAN, load_module, lrg_record, score_pack, store_init

score_all = load_module("score_all", PLUGIN_ROOT / "evals")


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
