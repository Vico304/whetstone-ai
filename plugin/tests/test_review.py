from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from _support import (
    SCRIPT_ROOT,
    _StoreHelpers,
    cards,
    index_match,
    learner_state_build,
    lrg_record,
    review_outline,
    review_pool,
    store_init,
    store_sync,
)


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

    def test_cli_labels_indexed_concepts_and_learner_states_apart(self):
        import subprocess, sys
        script = SCRIPT_ROOT / "store_sync.py"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "ws").mkdir()
            store = self._store(root / "ws")
            self._append(store, "2026-01-20T10:00:00Z", "checkpoint", "mastered", depth="mechanism")
            home = root / "home"
            pushed = subprocess.run([sys.executable, str(script), "push", "--store", str(store), "--home", str(home)],
                                    capture_output=True, text=True)
            self.assertEqual(pushed.returncode, 0, pushed.stderr)
            self.assertIn("4 indexed concepts, ", pushed.stdout)
            state = json.loads((home / "learner-state.json").read_text(encoding="utf-8"))
            shown = subprocess.run([sys.executable, str(script), "show", "--home", str(home)], capture_output=True, text=True)
            self.assertEqual(shown.returncode, 0, shown.stderr)
            self.assertIn(f"learner states: {len(state['concepts'])} (fresh=", shown.stdout)
            self.assertNotIn("\nconcepts:", shown.stdout)
