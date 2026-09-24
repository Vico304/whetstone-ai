from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from _support import (
    EXAMPLE_ROOT,
    PLUGIN_ROOT,
    TEMPLATE_PLAN,
    _StoreHelpers,
    comparator,
    index_match,
    learner_state_build,
    learning_state,
    load_template,
    lrg_record,
    mrg_export,
    review_pool,
    store_init,
)


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

    def test_a_correct_section_chain_is_not_scored_as_zero(self):
        """The real failure: every section link stated, a different concept named at each end."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = load_template()
            plan["sections"] = [copy.deepcopy(plan["sections"][0]) for _ in range(2)]
            plan["sections"][0]["id"], plan["sections"][1]["id"] = "s01", "s02"
            plan["sections"][1]["depends_on"], plan["sections"][0]["new_problem"] = ["s01"], "引出下一节"
            plan["sections"][1]["new_problem"] = None
            # each section keeps all four concepts, so a link between them can be named by any pair
            public, deep = mrg_export.export(plan)
            reference = comparator.Reference(public, deep)
            self.assertEqual(comparator.section_pairs(reference), [("s01", "s02")])

            # the reference edge joins system-boundary to macro-map; the learner names another pair
            other = comparator.compare_relations(reference, [
                {"from": "learning-design.problem-chain", "to": "learning-design.appendix", "type": "depends_on"}])
            self.assertEqual(other["ratio"], 0.0)  # exact matching says zero, as it did on the real course
            self.assertEqual(other["section_chain"]["ratio"], 1.0)  # the section chain was in fact reproduced
            self.assertEqual(other["section_chain"]["missing_pairs"], [])

            # wrong direction and wrong type still count as reaching the edge, and are reported
            reached = comparator.compare_relations(reference, [
                {"from": "learning-design.macro-map", "to": "learning-design.system-boundary", "type": "depends_on"}])
            self.assertEqual((reached["ratio"], reached["pair_ratio"]), (0.0, 1.0))

            nothing = comparator.compare_relations(reference, [])
            self.assertEqual(nothing["section_chain"], {"pairs": 1, "covered": 0, "ratio": 0.0,
                                                        "missing_pairs": [["s01", "s02"]]})
            del root  # the fixture needs no store: the reference is built straight from the export

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
