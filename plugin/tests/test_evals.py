from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from _support import EXAMPLE_ROOT, PLUGIN_ROOT, TEMPLATE_PLAN, lrg_record, score_pack, store_init


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

