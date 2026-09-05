#!/usr/bin/env python3
"""Score one generated lesson pack (and optionally its store log) so prompt or pipeline changes
are comparable run to run. Absolute values matter less than deltas against a baseline.

Build metrics (from lesson-plan.json / teaching-guide.md):
  validator errors & warnings, section count in range, max concepts per section,
  support distribution and unsupported ratio, relations count, layer distribution,
  criteria per section, guide length, locator hit rate (does each source_ref.locator
  actually occur in the referenced file?)
Teach metrics (from <store>/lrg/<lesson>.jsonl when --store is given):
  attempts, median elapsed seconds per checkpoint, depth distribution, conflict rate,
  share of high-confidence conflicts, evidence tier mix
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
from collections import Counter
from pathlib import Path


EVALS_DIR = Path(__file__).resolve().parent
SCRIPTS = EVALS_DIR.parent / "skills" / "guided-learning-tutor" / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


validate_lesson = _load("validate_lesson")


def locator_hit(locator: str, text: str) -> bool:
    """A locator counts as found when its first ' / '-separated segment (or the whole string)
    appears in the file, ignoring surrounding whitespace. Headings like '## 4.1' therefore
    match; page-number-only locators will not, which is the point."""
    head = locator.split(" / ")[0].strip()
    return bool(head) and head in text


def build_metrics(pack: Path, sources_root: Path | None, expect: dict | None) -> dict:
    plan_path = pack / "lesson-plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    guide_path = pack / "teaching-guide.md"
    manifest_path = pack / "sources.json"
    manifest = validate_lesson.manifest_paths(json.loads(manifest_path.read_text(encoding="utf-8"))) if manifest_path.is_file() else None
    errors = validate_lesson.validate_plan(plan, manifest)
    warnings = validate_lesson.collect_warnings(plan)
    guide = guide_path.read_text(encoding="utf-8") if guide_path.is_file() else ""
    if guide:
        errors += validate_lesson.validate_guide(guide, plan)
        warnings += validate_lesson.guide_warnings(guide, plan)

    sections = plan.get("sections", []) if isinstance(plan.get("sections"), list) else []
    concepts_per_section = [len(s.get("concepts", []) or []) for s in sections if isinstance(s, dict)]
    refs = [r for s in sections if isinstance(s, dict) for r in (s.get("source_refs") or []) if isinstance(r, dict)]
    refs += [r for rel in (plan.get("relations") or []) if isinstance(rel, dict) for r in (rel.get("source_refs") or []) if isinstance(r, dict)]
    support = Counter(r.get("support") for r in refs)
    layers = Counter(c.get("layer", "mechanism" if plan.get("schema_version") == "1.0" else None)
                     for s in sections if isinstance(s, dict) for c in (s.get("concepts") or []) if isinstance(c, dict))
    criteria = [len(validate_lesson.criteria_texts(s.get("checkpoint"))) for s in sections if isinstance(s, dict)]

    locator_checked = locator_found = 0
    file_cache: dict[str, str] = {}
    if sources_root is not None:
        for ref in refs:
            path, locator = ref.get("path"), ref.get("locator")
            if not isinstance(path, str) or not isinstance(locator, str):
                continue
            if path not in file_cache:
                candidate = sources_root / path
                file_cache[path] = candidate.read_text(encoding="utf-8", errors="replace") if candidate.is_file() else ""
            if not file_cache[path]:
                continue
            locator_checked += 1
            locator_found += locator_hit(locator, file_cache[path])

    metrics = {
        "schema_version": plan.get("schema_version"),
        "validator_errors": len(errors),
        "validator_warnings": len(warnings),
        "sections": len(sections),
        "max_concepts_per_section": max(concepts_per_section, default=0),
        "mean_concepts_per_section": round(statistics.mean(concepts_per_section), 2) if concepts_per_section else 0,
        "source_refs": len(refs),
        "support": dict(support),
        "unsupported_ratio": round(support.get("unsupported", 0) / len(refs), 3) if refs else 0.0,
        "pedagogical_inference_ratio": round(support.get("pedagogical_inference", 0) / len(refs), 3) if refs else 0.0,
        "relations": len(plan.get("relations") or []),
        "layers": dict(layers),
        "criteria_per_section": criteria,
        "guide_chars": len(guide),
        "locator_checked": locator_checked,
        "locator_hit_rate": round(locator_found / locator_checked, 3) if locator_checked else None,
        "errors": errors[:20],
        "warnings": warnings[:20],
    }
    if expect:
        low, high = expect.get("sections", [0, 10**6])
        metrics["expectations"] = {
            "sections_in_range": low <= len(sections) <= high,
            "concepts_within_cap": metrics["max_concepts_per_section"] <= expect.get("max_concepts_per_section", 4),
            "enough_relations": metrics["relations"] >= expect.get("min_relations", 0),
        }
    return metrics


def teach_metrics(store: Path, lesson_id: str) -> dict:
    path = store / "lrg" / f"{lesson_id}.jsonl"
    if not path.is_file():
        return {"attempts": 0}
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    attempts = [e for e in events if e.get("event") == "attempt"]
    elapsed = [e["elapsed_seconds"] for e in attempts if e.get("kind") == "checkpoint" and isinstance(e.get("elapsed_seconds"), int)]
    conflicts = [c for e in attempts for c in (e.get("diff") or {}).get("conflict", [])]
    return {
        "attempts": len(attempts),
        "kinds": dict(Counter(e.get("kind") for e in attempts)),
        "evidence_tiers": dict(Counter(e.get("evidence_tier") for e in attempts)),
        "verdicts": dict(Counter(e.get("verdict") for e in attempts)),
        "depths": dict(Counter(e.get("depth_reached") or "unset" for e in attempts)),
        "median_checkpoint_elapsed_s": statistics.median(elapsed) if elapsed else None,
        "conflicts_per_attempt": round(len(conflicts) / len(attempts), 3) if attempts else 0.0,
        "high_confidence_conflict_share": round(sum(1 for c in conflicts if c.get("confidence_high")) / len(conflicts), 3) if conflicts else None,
        "attempts_with_extraction": sum(1 for e in attempts if e.get("extraction")),
    }


def flatten(prefix: str, value, out: dict) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            flatten(f"{prefix}.{k}" if prefix else str(k), v, out)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        out[prefix] = value


def diff_against(baseline: dict, current: dict) -> list[str]:
    a: dict = {}
    b: dict = {}
    flatten("", baseline, a)
    flatten("", current, b)
    lines = []
    for key in sorted(set(a) | set(b)):
        if key.startswith("build.errors") or key.startswith("build.warnings"):
            continue
        if a.get(key) != b.get(key):
            lines.append(f"  {key}: {a.get(key)} → {b.get(key)}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pack", type=Path, help="Lesson pack directory (contains lesson-plan.json)")
    parser.add_argument("--sources-root", type=Path, help="Directory that source_refs.path values are relative to (enables locator check)")
    parser.add_argument("--material-id", help="Id from materials.json to apply its expectations")
    parser.add_argument("--store", type=Path, help="Knowledge store; adds teach metrics from its LRG log")
    parser.add_argument("--baseline", type=Path, help="Previous result JSON to diff against")
    parser.add_argument("--output", type=Path, help="Write result JSON here")
    args = parser.parse_args()

    expect = None
    if args.material_id:
        materials = json.loads((EVALS_DIR / "materials.json").read_text(encoding="utf-8"))["materials"]
        match = next((m for m in materials if m["id"] == args.material_id), None)
        if match is None:
            print(f"ERROR: unknown material id {args.material_id}", file=sys.stderr)
            return 2
        expect = match.get("expect")
    try:
        plan = json.loads((args.pack / "lesson-plan.json").read_text(encoding="utf-8"))
        result = {"pack": str(args.pack), "build": build_metrics(args.pack, args.sources_root, expect)}
        if args.store:
            result["teach"] = teach_metrics(args.store, plan.get("lesson_id"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    b = result["build"]
    print(f"{args.pack}: schema {b['schema_version']}, {b['sections']} sections, max {b['max_concepts_per_section']} concepts/section, "
          f"{b['relations']} relations, {b['validator_errors']} errors / {b['validator_warnings']} warnings, "
          f"locator hit {b['locator_hit_rate']}, unsupported {b['unsupported_ratio']}")
    if "teach" in result and result["teach"].get("attempts"):
        t = result["teach"]
        print(f"  teach: {t['attempts']} attempts, median checkpoint {t['median_checkpoint_elapsed_s']}s, "
              f"depths {t['depths']}, conflicts/attempt {t['conflicts_per_attempt']}")
    if args.baseline and args.baseline.is_file():
        lines = diff_against(json.loads(args.baseline.read_text(encoding="utf-8")), result)
        print("  vs baseline:" if lines else "  vs baseline: no change")
        for line in lines:
            print(line)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
