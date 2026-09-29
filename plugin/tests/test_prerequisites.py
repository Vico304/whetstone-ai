from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from _support import (
    EXAMPLE_ROOT,
    PLUGIN_ROOT,
    _StoreHelpers,
    index_match,
    learner_state_build,
    learning_state,
    load_template,
    lrg_record,
    mrg_export,
    prerequisite_state,
    store_init,
    validate_lesson,
    validate_prerequisites,
)

PREREQUISITE_EXAMPLE = PLUGIN_ROOT / "evals" / "prerequisites"


class PrerequisiteValidationTests(unittest.TestCase):
    def test_prerequisite_templates_are_valid(self):
        asset_root = PLUGIN_ROOT / "skills" / "learn" / "assets"
        plan = json.loads((asset_root / "prerequisite-plan-template.json").read_text(encoding="utf-8"))
        guide = (asset_root / "prerequisite-guide-template.md").read_text(encoding="utf-8")

        self.assertEqual(validate_prerequisites.validate_plan(plan), [])
        self.assertEqual(validate_prerequisites.validate_guide(guide), [])

    def test_schema_1_1_accepts_the_gap_ledger_fields_and_checks_them(self):
        plan = json.loads((PREREQUISITE_EXAMPLE / "prerequisite-plan.json").read_text(encoding="utf-8"))
        plan["prerequisites"][0].update(concept_id="math.directed-graph", cluster="graphs",
                                        required_by=["s03", "s05"], depth_required="tool", depends_on=["p02"])
        self.assertEqual(validate_prerequisites.validate_plan(plan), [])  # 1.0 still ignores fields it does not know
        plan["schema_version"] = "1.1"
        self.assertEqual(validate_prerequisites.validate_plan(plan), [])
        plan["prerequisites"][0].update(depth_required="principle", required_by="s03", cluster="")
        self.assertEqual(validate_prerequisites.validate_plan(plan), [
            "prerequisites[0].cluster must be a non-empty string",
            "prerequisites[0].required_by must be a list of non-empty strings",
            "prerequisites[0].depth_required must be one of ['fact', 'mechanism', 'tool']",
        ])
        plan["schema_version"] = "1.0"
        self.assertEqual(validate_prerequisites.validate_plan(plan), [])
        plan["schema_version"] = "1.2"
        self.assertEqual(validate_prerequisites.validate_plan(plan), ["schema_version must be one of ['1.0', '1.1']"])

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


class PrerequisiteExampleTests(unittest.TestCase):
    """evals/prerequisites holds a prerequisite plan and progress file for the example pack, so evals reach both prerequisite scripts."""

    SCRIPT_ROOT = PLUGIN_ROOT / "skills" / "learn" / "scripts"
    TIMESTAMPS = {"at", "created_at", "updated_at", "accessed_at"}

    def _run(self, script, *args):
        import subprocess, sys
        return subprocess.run([sys.executable, str(self.SCRIPT_ROOT / script), *map(str, args)], capture_output=True, text=True)

    def _without_timestamps(self, value):
        if isinstance(value, dict):
            return {key: self._without_timestamps(item) for key, item in value.items() if key not in self.TIMESTAMPS}
        if isinstance(value, list):
            return [self._without_timestamps(item) for item in value]
        return value

    def test_example_plan_validates_against_the_example_manifest(self):
        plan_path = PREREQUISITE_EXAMPLE / "prerequisite-plan.json"
        done = self._run("validate_prerequisites.py", plan_path, "--manifest", EXAMPLE_ROOT / "sources.json")
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertTrue(done.stdout.startswith("OK: "), done.stdout)

        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        lesson = json.loads((EXAMPLE_ROOT / "lesson-plan.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["lesson_id"], lesson["lesson_id"])
        headings = set((EXAMPLE_ROOT / "source" / "consensus.md").read_text(encoding="utf-8").splitlines())
        for prerequisite in plan["prerequisites"]:
            for ref in prerequisite["source_refs"]:
                self.assertIn(ref["locator"], headings, f"{prerequisite['id']} locator is not a heading in the source")

    def test_example_progress_is_what_the_cli_writes_for_the_example_plan(self):
        example = json.loads((PREREQUISITE_EXAMPLE / "prerequisite-progress.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "prerequisite-progress.json"
            done = self._run("prerequisite_state.py", "init", "--prerequisite-plan", PREREQUISITE_EXAMPLE / "prerequisite-plan.json", "--output", state)
            self.assertEqual(done.returncode, 0, done.stdout)

            # Replay the attempts in the order the example's event log recorded them.
            commands = {"prerequisite_assessment_recorded": ("record", "assessment_attempts"),
                        "prerequisite_bridge_recorded": ("bridge", "bridge_attempts")}
            competencies = {item["id"]: item for item in example["competencies"]}
            used: dict[tuple[str, str], int] = {}
            for number, event in enumerate(example["events"][1:]):
                command, field = commands[event["type"]]
                prerequisite_id = event["prerequisite_id"]
                index = used.get((prerequisite_id, field), 0)
                used[(prerequisite_id, field)] = index + 1
                attempt = competencies[prerequisite_id][field][index]
                response, feedback = root / f"r{number}.txt", root / f"f{number}.txt"
                response.write_text(attempt["response"], encoding="utf-8")
                feedback.write_text(attempt["feedback"], encoding="utf-8")
                done = self._run("prerequisite_state.py", command, "--state", state, "--prerequisite-id", prerequisite_id,
                                 "--response-file", response, "--feedback-file", feedback,
                                 "--verdict", attempt["verdict"], "--confidence", attempt["confidence"])
                self.assertEqual(done.returncode, 0, done.stdout)

            written = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(self._without_timestamps(written), self._without_timestamps(example))
            shown = self._run("prerequisite_state.py", "show", "--state", PREREQUISITE_EXAMPLE / "prerequisite-progress.json")
            self.assertEqual(shown.returncode, 0, shown.stdout)
            self.assertIn("status: ready_for_main_course", shown.stdout)


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

