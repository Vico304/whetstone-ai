#!/usr/bin/env python3
"""Validate a guided-learning lesson plan and its human-readable guide."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SUPPORT_TYPES = {"explicit", "entailed", "pedagogical_inference", "external", "unsupported"}
SCHEMA_VERSIONS = {"1.0", "1.1", "1.2", "1.3", "1.4", "1.5"}
ROLE_AWARE_VERSIONS = {"1.2", "1.3", "1.4", "1.5"}  # course-planning (spec C) fields
SHAPE_AWARE_VERSIONS = {"1.3", "1.4", "1.5"}  # shape / pool / anchor / probe / branch candidates
PREREQUISITE_VERSIONS = {"1.4", "1.5"}
PREREQUISITE_KEYS = ("prerequisite_of", "blocked_at", "depth")  # 1.4: a course spawned to fill a parent course's gap
SHAPES = {"linear", "skeleton", "branch", "review"}
# 1.5: variation fields on concepts, contested tradeoffs, sub-sections, review courses
ONTOLOGY_TYPES = {"entity", "process", "constraint", "relation"}
CASES_PER_CONCEPT = 2
CONTESTED_SIDES = 2
V15_CONCEPT_KEYS = ("contrast", "cases", "ontology")
REVIEW_KINDS = {"repeat", "deepen"}
REVIEW_LEAK_MIN_CHARS = 20  # a sentence of the reviewed section's solution/mechanism this long must not reappear verbatim
ANCHOR_MARKERS = {"external", "no-anchor"}
# a locator into data or code reaches a key or a symbol, never a passage that explains the concept
DATA_SUFFIXES = {".json", ".yaml", ".yml", ".toml", ".ini", ".env", ".sh", ".py", ".rs", ".go",
                 ".c", ".h", ".cc", ".cpp", ".hpp", ".java", ".ts", ".js", ".rb"}
TEXT_SUFFIXES = {".md", ".markdown", ".mdx", ".adoc", ".asciidoc", ".rst", ".txt"}
THIN_ANCHOR_CHARS = 200  # shorter than this, the passage states the concept instead of explaining it
ANY_HEADING_MD = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
ANY_HEADING_ADOC = re.compile(r"^(={1,6})\s+(.+?)\s*$")
BRANCH_STATUSES = {"candidate", "chosen", "declined"}
MODES = {"full", "fast"}
ROLES = ("core", "supporting", "listed")
DISPOSITIONS = {"core", "supporting", "listed", "appendix", "deferred", "excluded", "pool", "reserve"}
FILE_LEVEL_DISPOSITIONS = {"pool", "reserve", "excluded"}  # may use heading "*" (skeleton courses; external archives anywhere)
EXTERNAL_ARCHIVE_DIR = "external"  # <workspace>/external/<set>/ — fetched sources archived as material
MAX_SUPPORTING_PER_SECTION = 6
MAX_LISTED_EXPLANATION_CHARS = 200
HEADING_MD = re.compile(r"^(#{1,2})\s+(.+?)\s*#*\s*$", re.MULTILINE)
HEADING_ADOC = re.compile(r"^(={1,2})\s+(.+?)\s*$", re.MULTILINE)
LAYERS = ("fact", "mechanism", "rationale", "principle")
PUBLIC_LAYERS = {"fact", "mechanism"}
RELATION_TYPES = {
    "is_a", "part_of", "depends_on", "causes", "enables",
    "implements", "contrasts_with", "instance_of", "prerequisite_for",
}
CONCEPT_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*(\.[a-z0-9][a-z0-9_-]*)+$")
MAX_DOMAIN_DEPTH = 4

MAX_CONCEPTS_PER_SECTION = 4
MAX_SECTIONS_PER_LESSON = 9


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def require_text(container: dict, key: str, location: str, errors: list[str]) -> None:
    if not nonempty(container.get(key)):
        errors.append(f"{location}.{key} must be a non-empty string")


def require_text_list(container: dict, key: str, location: str, errors: list[str], allow_empty: bool = False) -> None:
    value = container.get(key)
    if not isinstance(value, list) or (not value and not allow_empty) or not all(nonempty(item) for item in value):
        suffix = " (empty allowed)" if allow_empty else ""
        errors.append(f"{location}.{key} must be a list of non-empty strings{suffix}")


def schema_version(plan: dict) -> str:
    version = plan.get("schema_version")
    return version if version in SCHEMA_VERSIONS else "1.0"


def plan_shape(plan: dict) -> str:
    """1.3 course shape; older plans and plans without the field are linear."""
    shape = plan.get("shape") if isinstance(plan, dict) else None
    return shape if shape in SHAPES else "linear"


def under_path(path: str, roots: set[str]) -> bool:
    """True when `path` equals one of `roots` or lies below a root directory."""
    path = path.strip("/")
    for root in roots:
        root = root.strip("/")
        if root in {"", "."} or path == root or path.startswith(root + "/"):
            return True
    return False


def wholesale_paths(plan: dict) -> set[str]:
    """Coverage rows with heading "*" cover the whole file or directory."""
    return {
        item["path"] for item in (plan.get("coverage") or []) if isinstance(plan.get("coverage"), list)
        if isinstance(item, dict) and nonempty(item.get("path")) and item.get("heading") == "*"
    }


def pool_paths(plan: dict) -> set[str]:
    return {
        item["path"] for item in (plan.get("coverage") or []) if isinstance(plan.get("coverage"), list)
        if isinstance(item, dict) and nonempty(item.get("path")) and item.get("disposition") == "pool"
    }


def is_external_archive(path: Any) -> bool:
    """True for paths inside an external archive set (any `external/` directory segment)."""
    return isinstance(path, str) and EXTERNAL_ARCHIVE_DIR in [part for part in path.strip("/").split("/") if part]


def external_refs(plan: dict) -> dict:
    """How many source refs (sections, relations, concept-level) carry support 'external', out of all refs."""
    total = external = 0
    ref_lists: list[Any] = []
    for section in plan.get("sections", []) or []:
        if isinstance(section, dict):
            ref_lists.append(section.get("source_refs"))
            for concept in section.get("concepts", []) or []:
                if isinstance(concept, dict):
                    ref_lists.append(concept.get("source_refs"))
    for relation in plan.get("relations", []) or []:
        if isinstance(relation, dict):
            ref_lists.append(relation.get("source_refs"))
    for refs in ref_lists:
        for ref in refs or []:
            if isinstance(ref, dict):
                total += 1
                if ref.get("support") == "external":
                    external += 1
    return {"external": external, "total": total}


def validate_source_refs(refs: Any, location: str, errors: list[str], manifest_paths: set[str] | None) -> None:
    if not isinstance(refs, list) or not refs:
        errors.append(f"{location}.source_refs must be a non-empty list")
        return
    for ref_index, ref in enumerate(refs):
        ref_location = f"{location}.source_refs[{ref_index}]"
        if not isinstance(ref, dict):
            errors.append(f"{ref_location} must be an object")
            continue
        for key in ("path", "locator", "note"):
            require_text(ref, key, ref_location, errors)
        if ref.get("support") not in SUPPORT_TYPES:
            errors.append(f"{ref_location}.support must be one of {sorted(SUPPORT_TYPES)}")
        path = ref.get("path")
        if is_url(path) and ref.get("support") != "external":
            errors.append(f"{ref_location}: a URL path must carry support 'external'")
        if manifest_paths is not None and nonempty(path) and not is_url(path) and path not in manifest_paths:
            errors.append(f"{ref_location}.path '{path}' is absent from the source manifest")


def is_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def validate_concept_v11(concept: dict, location: str, errors: list[str], names_by_id: dict[str, str]) -> None:
    concept_id = concept.get("id")
    if not nonempty(concept_id) or not CONCEPT_ID.match(concept_id):
        errors.append(f"{location}.id must match '<domain>.<concept>' in lowercase ascii, e.g. 'cs.tee.enclave'")
    elif concept_id in names_by_id and names_by_id[concept_id] != concept.get("name"):
        errors.append(f"{location}.id '{concept_id}' is reused with a different name ('{names_by_id[concept_id]}')")
    elif nonempty(concept.get("name")):
        names_by_id[concept_id] = concept["name"]
    if concept.get("layer") not in LAYERS:
        errors.append(f"{location}.layer must be one of {list(LAYERS)}")
    path = concept.get("domain_path")
    if not isinstance(path, list) or not path or len(path) > MAX_DOMAIN_DEPTH or not all(nonempty(item) for item in path):
        errors.append(f"{location}.domain_path must be 1-{MAX_DOMAIN_DEPTH} non-empty strings")
    aliases = concept.get("aliases", [])
    if not isinstance(aliases, list) or not all(nonempty(item) for item in aliases):
        errors.append(f"{location}.aliases must be a list of non-empty strings when present")


def validate_concept_v12(concept: dict, location: str, errors: list[str]) -> None:
    if concept.get("role") not in ROLES:
        errors.append(f"{location}.role must be one of {list(ROLES)}")
    check = concept.get("check")
    if check is not None:
        if concept.get("role") != "supporting":
            errors.append(f"{location}.check is only allowed on supporting concepts")
        if not isinstance(check, dict):
            errors.append(f"{location}.check must be an object")
        else:
            require_text(check, "prompt", f"{location}.check", errors)
            require_text(check, "hint", f"{location}.check", errors)
            validate_criteria(check, f"{location}.check", errors, "1.2")


def validate_concept_v15(concept: dict, location: str, errors: list[str], manifest_paths: set[str] | None) -> None:
    """Variation fields: the nearest confusable neighbour, two structurally alike cases, the ontological category."""
    contrast = concept.get("contrast")
    if contrast is not None:
        if not isinstance(contrast, dict):
            errors.append(f"{location}.contrast must be an object {{with, differs_in}}")
        else:
            with_id = contrast.get("with")
            if not nonempty(with_id) or not CONCEPT_ID.match(with_id):
                errors.append(f"{location}.contrast.with must be a concept id")
            elif with_id == concept.get("id"):
                errors.append(f"{location}.contrast.with must name another concept")
            require_text(contrast, "differs_in", f"{location}.contrast", errors)
    cases = concept.get("cases")
    if cases is not None:
        if not isinstance(cases, list) or len(cases) != CASES_PER_CONCEPT:
            errors.append(f"{location}.cases must be a list of exactly {CASES_PER_CONCEPT} cases (surface-different, structure-alike)")
        else:
            for index, case in enumerate(cases):
                c_location = f"{location}.cases[{index}]"
                if not isinstance(case, dict):
                    errors.append(f"{c_location} must be an object {{summary, source_refs[]}}")
                    continue
                require_text(case, "summary", c_location, errors)
                validate_source_refs(case.get("source_refs"), c_location, errors, manifest_paths)
    ontology = concept.get("ontology")
    if ontology is not None and ontology not in ONTOLOGY_TYPES:
        errors.append(f"{location}.ontology must be one of {sorted(ONTOLOGY_TYPES)}")


def tradeoff_text(item: Any) -> str | None:
    """The text of a tradeoff entry: a string (1.0) or an object {text, contested?, sides?} (1.5)."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict) and isinstance(item.get("text"), str):
        return item["text"]
    return None


def validate_tradeoffs(section: dict, location: str, errors: list[str], version: str, manifest_paths: set[str] | None) -> None:
    items = section.get("tradeoffs")
    if not isinstance(items, list):
        errors.append(f"{location}.tradeoffs must be a list (empty allowed)")
        return
    for index, item in enumerate(items):
        t_location = f"{location}.tradeoffs[{index}]"
        if nonempty(item):
            continue
        if not isinstance(item, dict) or version != "1.5":
            errors.append(f"{t_location} must be a non-empty string" + ("" if version == "1.5" else " (objects need schema 1.5)"))
            continue
        require_text(item, "text", t_location, errors)
        contested = item.get("contested", False)
        if not isinstance(contested, bool):
            errors.append(f"{t_location}.contested must be true or false")
        sides = item.get("sides")
        if contested or sides is not None:
            if not isinstance(sides, list) or len(sides) != CONTESTED_SIDES:
                errors.append(f"{t_location}.sides must list exactly {CONTESTED_SIDES} sides when the tradeoff is contested")
            else:
                for s_index, side in enumerate(sides):
                    s_location = f"{t_location}.sides[{s_index}]"
                    if not isinstance(side, dict):
                        errors.append(f"{s_location} must be an object {{claim, source_refs[]}}")
                        continue
                    require_text(side, "claim", s_location, errors)
                    validate_source_refs(side.get("source_refs"), s_location, errors, manifest_paths)


def validate_v15(plan: dict, section_ids: set[str], errors: list[str]) -> None:
    """Schema 1.5: review courses (shape review + review_of) and sub-sections (parent_section)."""
    shape = plan_shape(plan)
    review_of = plan.get("review_of")
    if shape == "review":
        if not isinstance(review_of, list) or not review_of or not all(nonempty(item) for item in review_of):
            errors.append("root.review_of must list the lesson ids this review course revisits (shape = review)")
        elif plan.get("lesson_id") in review_of:
            errors.append("root.review_of must not contain this course")
    elif review_of is not None:
        errors.append("root.review_of is only allowed when shape = review")
    reviewed = set(review_of) if isinstance(review_of, list) else set()
    parents: dict[str, str] = {}
    for index, section in enumerate(plan.get("sections") or []):
        if not isinstance(section, dict):
            continue
        location = f"sections[{index}]"
        kind = section.get("review_kind")
        if shape == "review":
            if kind not in REVIEW_KINDS:
                errors.append(f"{location}.review_kind must be one of {sorted(REVIEW_KINDS)} in a review course (repeat: revisit; deepen: sub-section)")
            if section.get("parent_section") is None:
                errors.append(f"{location}.parent_section is required in a review course (the reviewed section it revisits or deepens)")
        elif kind is not None:
            errors.append(f"{location}.review_kind is only allowed in a review course")
        parent = section.get("parent_section")
        if parent is None:
            continue
        if not isinstance(parent, dict) or not nonempty(parent.get("lesson_id")) or not nonempty(parent.get("section_id")):
            errors.append(f"{location}.parent_section must be an object {{lesson_id, section_id}}")
            continue
        if parent["lesson_id"] == plan.get("lesson_id"):
            if parent["section_id"] == section.get("id"):
                errors.append(f"{location}.parent_section must not be the section itself")
            elif parent["section_id"] not in section_ids:
                errors.append(f"{location}.parent_section.section_id '{parent['section_id']}' is not a section of this course")
            else:
                parents[section.get("id")] = parent["section_id"]
        elif parent["lesson_id"] not in reviewed:
            errors.append(f"{location}.parent_section.lesson_id '{parent['lesson_id']}' is neither this course nor one listed in review_of")
    for start in parents:
        seen, node = set(), start
        while node in parents:
            if node in seen:
                errors.append(f"sections parent_section chain starting at '{start}' forms a cycle")
                break
            seen.add(node)
            node = parents[node]


def variation_ratio(plan: dict) -> dict:
    """Core concepts with a contrast pair / with two cases, out of all core concepts (unique by id). No threshold."""
    seen: dict[str, dict] = {}
    for section in plan.get("sections", []) or []:
        for concept in (section.get("concepts", []) or []) if isinstance(section, dict) else []:
            if isinstance(concept, dict) and concept.get("role", "core") == "core":
                key = concept.get("id") or concept.get("name")
                if isinstance(key, str):
                    entry = seen.setdefault(key, {"contrast": False, "cases": False})
                    entry["contrast"] = entry["contrast"] or isinstance(concept.get("contrast"), dict)
                    entry["cases"] = entry["cases"] or isinstance(concept.get("cases"), list)
    return {"contrast": sum(1 for e in seen.values() if e["contrast"]), "cases": sum(1 for e in seen.values() if e["cases"]), "total": len(seen)}


def validate_deferred(plan: dict, section_ids: set[str], concept_ids: set[str], errors: list[str]) -> set[str]:
    """Returns the set of deferred section ids."""
    deferred_sections: set[str] = set()
    items = plan.get("deferred", [])
    if not isinstance(items, list):
        errors.append("root.deferred must be a list")
        return deferred_sections
    for index, item in enumerate(items):
        location = f"deferred[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{location} must be an object")
            continue
        require_text(item, "reason", location, errors)
        kind, ident = item.get("type"), item.get("id")
        if kind == "section":
            if ident not in section_ids:
                errors.append(f"{location}.id '{ident}' is not a section id")
            else:
                deferred_sections.add(ident)
        elif kind == "concept":
            if ident not in concept_ids:
                errors.append(f"{location}.id '{ident}' is not a concept id in this lesson")
        else:
            errors.append(f"{location}.type must be 'section' or 'concept'")
    return deferred_sections


def validate_coverage(plan: dict, section_ids: set[str], errors: list[str], allow_empty: bool) -> None:
    shape = plan_shape(plan)
    coverage = plan.get("coverage")
    if not isinstance(coverage, list):
        errors.append("root.coverage must be a list (schema 1.2)")
        return
    if not coverage and not allow_empty and shape != "review":
        errors.append("root.coverage is empty; every source heading needs a disposition (or pass --allow-empty-coverage)")
    for index, item in enumerate(coverage):
        location = f"coverage[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{location} must be an object")
            continue
        require_text(item, "path", location, errors)
        require_text(item, "heading", location, errors)
        disposition = item.get("disposition")
        if disposition not in DISPOSITIONS:
            errors.append(f"{location}.disposition must be one of {sorted(DISPOSITIONS)}")
            continue
        if disposition == "reserve" and shape != "skeleton":
            errors.append(f"{location}.disposition 'reserve' is only allowed in skeleton courses (schema 1.3, shape = skeleton)")
        if disposition == "pool" and shape != "skeleton" and not is_external_archive(item.get("path")):
            errors.append(f"{location}.disposition 'pool' outside a skeleton course is only allowed for external archives "
                          f"(a path under an '{EXTERNAL_ARCHIVE_DIR}/' directory)")
        if item.get("heading") == "*" and disposition not in FILE_LEVEL_DISPOSITIONS:
            errors.append(f"{location}.heading '*' (whole file) is only allowed for {sorted(FILE_LEVEL_DISPOSITIONS)}")
        if disposition in {"core", "supporting", "listed", "appendix"} and item.get("section_id") not in section_ids:
            errors.append(f"{location}.section_id must name a section for disposition '{disposition}'")
        if disposition in {"deferred", "excluded"} and not nonempty(item.get("reason")):
            errors.append(f"{location}.reason is required for disposition '{disposition}'")


def source_headings(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    pattern = HEADING_ADOC if path.suffix.lower() in {".adoc", ".asciidoc"} else HEADING_MD
    return [m.group(2).strip() for m in pattern.finditer(text)]


def validate_coverage_against_sources(plan: dict, sources_root: Path) -> list[str]:
    """Every level-1/2 heading of every text source referenced by the plan must appear in coverage[]."""
    errors: list[str] = []
    coverage = plan.get("coverage") if isinstance(plan.get("coverage"), list) else []
    covered = {(item.get("path"), normalize_text(str(item.get("heading", "")))) for item in coverage if isinstance(item, dict)}
    paths: set[str] = {item["path"] for item in coverage if isinstance(item, dict) and nonempty(item.get("path"))}
    for section in plan.get("sections", []) or []:
        for ref in (section.get("source_refs") or []) if isinstance(section, dict) else []:
            if isinstance(ref, dict) and nonempty(ref.get("path")):
                paths.add(ref["path"])
    wholesale = wholesale_paths(plan)
    for rel in sorted(paths):
        if under_path(rel, wholesale):
            continue  # whole file/directory has a disposition (pool / reserve / excluded)
        path = sources_root / rel
        if not path.is_file() or path.suffix.lower() not in {".md", ".markdown", ".adoc", ".asciidoc", ".txt"}:
            continue
        for heading in source_headings(path):
            if (rel, normalize_text(heading)) not in covered:
                errors.append(f"coverage is missing heading '{heading}' of {rel}")
    return errors


def validate_anchor(concept: dict, location: str, pools: set[str], errors: list[str]) -> None:
    anchor = concept.get("anchor")
    if anchor is None:
        errors.append(f"{location}.anchor is required for core/supporting concepts of a skeleton course "
                      "({path, locator} in the evidence pool, or \"external\" / \"no-anchor\")")
        return
    if isinstance(anchor, str):
        if anchor not in ANCHOR_MARKERS:
            errors.append(f"{location}.anchor must be an object or one of {sorted(ANCHOR_MARKERS)}")
        return
    if not isinstance(anchor, dict):
        errors.append(f"{location}.anchor must be an object or one of {sorted(ANCHOR_MARKERS)}")
        return
    require_text(anchor, "path", f"{location}.anchor", errors)
    require_text(anchor, "locator", f"{location}.anchor", errors)
    if nonempty(anchor.get("path")) and not is_url(anchor["path"]) and not under_path(anchor["path"], pools):
        errors.append(f"{location}.anchor.path '{anchor['path']}' is not under any coverage row with disposition 'pool'")


def validate_branch_candidates(plan: dict, concept_ids: set[str], errors: list[str]) -> None:
    items = plan.get("branch_candidates")
    if not isinstance(items, list) or not items:
        errors.append("root.branch_candidates must be a non-empty list in a skeleton course")
        return
    material_roots = {
        item["path"] for item in (plan.get("coverage") or [])
        if isinstance(item, dict) and nonempty(item.get("path")) and item.get("disposition") in {"pool", "reserve"}
    }
    seen: set[str] = set()
    for index, item in enumerate(items):
        location = f"branch_candidates[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{location} must be an object")
            continue
        require_text(item, "id", location, errors)
        require_text(item, "title", location, errors)
        if nonempty(item.get("id")):
            if item["id"] in seen:
                errors.append(f"{location}.id duplicates '{item['id']}'")
            seen.add(item["id"])
        ids = item.get("concept_ids")
        if not isinstance(ids, list) or not ids or not all(nonempty(c) for c in ids):
            errors.append(f"{location}.concept_ids must be a non-empty list of concept ids")
        else:
            for cid in ids:
                if cid not in concept_ids:
                    errors.append(f"{location}.concept_ids references unknown concept '{cid}'")
        materials = item.get("materials")
        if not isinstance(materials, list) or not all(nonempty(m) for m in materials):
            errors.append(f"{location}.materials must be a list of paths (empty allowed for no-anchor candidates)")
        else:
            for material in materials:
                if not under_path(material, material_roots):
                    errors.append(f"{location}.materials '{material}' is not under any 'pool' or 'reserve' coverage row")
        if item.get("status") not in BRANCH_STATUSES:
            errors.append(f"{location}.status must be one of {sorted(BRANCH_STATUSES)}")
        if "work_relevance" in item and not nonempty(item.get("work_relevance")):
            errors.append(f"{location}.work_relevance must be a non-empty string when present")


def validate_v13(plan: dict, concept_ids: set[str], errors: list[str]) -> None:
    """Schema 1.3: shape, parent_course, per-section probes, concept anchors, branch candidates."""
    shape = plan.get("shape", "linear")
    if shape not in SHAPES:
        errors.append(f"root.shape must be one of {sorted(SHAPES)} (schema 1.3)")
        shape = "linear"
    parent = plan.get("parent_course")
    if shape == "branch" and not nonempty(parent):
        errors.append("root.parent_course must name the skeleton course when shape = branch")
    if shape != "branch" and parent is not None:
        errors.append("root.parent_course is only allowed when shape = branch")
    pools = pool_paths(plan)
    for index, section in enumerate(plan.get("sections") or []):
        if not isinstance(section, dict):
            continue
        location = f"sections[{index}]"
        probe = section.get("probe")
        if shape == "skeleton":
            if not isinstance(probe, dict):
                errors.append(f"{location}.probe is required in a skeleton course (principle-level, no-hint question)")
            else:
                require_text(probe, "prompt", f"{location}.probe", errors)
                validate_criteria(probe, f"{location}.probe", errors, "1.3")
                if "hint" in probe and not nonempty(probe.get("hint")):
                    errors.append(f"{location}.probe.hint must be a non-empty string when present")
        elif probe is not None:
            errors.append(f"{location}.probe is only allowed in skeleton courses")
        for c_index, concept in enumerate(section.get("concepts") or []):
            if not isinstance(concept, dict):
                continue
            c_location = f"{location}.concepts[{c_index}]"
            if shape == "skeleton" and concept.get("role") in {"core", "supporting"}:
                validate_anchor(concept, c_location, pools, errors)
            elif "anchor" in concept and shape != "skeleton":
                errors.append(f"{c_location}.anchor is only allowed in skeleton courses")
    if shape == "skeleton":
        validate_branch_candidates(plan, concept_ids, errors)
    elif "branch_candidates" in plan:
        errors.append("root.branch_candidates is only allowed in skeleton courses")


def is_prerequisite_course(plan: dict) -> bool:
    return isinstance(plan, dict) and nonempty(plan.get("prerequisite_of"))


def validate_v14(plan: dict, errors: list[str]) -> None:
    """Schema 1.4: prerequisite courses — prerequisite_of, blocked_at, depth travel together on a linear course."""
    present = [key for key in PREREQUISITE_KEYS if key in plan]
    if not present:
        return
    missing = [key for key in PREREQUISITE_KEYS if key not in plan]
    if missing:
        errors.append(f"root.{', root.'.join(missing)} required alongside {', '.join(present)} (a prerequisite course carries all three)")
    parent = plan.get("prerequisite_of")
    if "prerequisite_of" in plan and (not nonempty(parent) or parent == plan.get("lesson_id")):
        errors.append("root.prerequisite_of must name the parent course (not this course)")
    if "blocked_at" in plan and not nonempty(plan.get("blocked_at")):
        errors.append("root.blocked_at must name the parent course's blocked section")
    depth = plan.get("depth")
    if "depth" in plan and (isinstance(depth, bool) or not isinstance(depth, int) or depth < 1):
        errors.append("root.depth must be an integer >= 1 (parent depth + 1; the main course is 0)")
    if plan_shape(plan) != "linear":
        errors.append("root.prerequisite_of is only allowed when shape = linear")
    if plan.get("parent_course") is not None:
        errors.append("root.prerequisite_of and root.parent_course are mutually exclusive (prerequisite course vs branch course)")


def orphan_concepts(plan: dict) -> dict:
    """Core concepts (by id) that no relation touches. No threshold: a printed number for the learner to judge."""
    core: set[str] = set()
    for section in plan.get("sections", []) or []:
        for concept in (section.get("concepts", []) or []) if isinstance(section, dict) else []:
            if isinstance(concept, dict) and concept.get("role", "core") == "core" and nonempty(concept.get("id")):
                core.add(concept["id"])
    related: set[str] = set()
    for relation in plan.get("relations", []) or []:
        if isinstance(relation, dict):
            related.update(r for r in (relation.get("from"), relation.get("to")) if isinstance(r, str))
    return {"orphans": sorted(core - related), "total": len(core)}


def fact_ratio(plan: dict) -> dict:
    """Fact-layer concepts / all concepts (unique by id, else name). No threshold: when nearly everything is a
    convention, the next level down is cards, not another course."""
    seen: dict[str, str] = {}
    for section in plan.get("sections", []) or []:
        if not isinstance(section, dict):
            continue
        for concept in section.get("concepts", []) or []:
            if not isinstance(concept, dict):
                continue
            key = concept.get("id") or concept.get("name")
            if isinstance(key, str) and key not in seen:
                seen[key] = concept.get("layer") or "mechanism"
    return {"fact": sum(1 for layer in seen.values() if layer == "fact"), "total": len(seen)}


def grounding(plan: dict) -> dict:
    """Anchored / external / no-anchor counts over core+supporting concepts (skeleton courses)."""
    counts = {"anchored": 0, "external": 0, "no_anchor": 0, "total": 0}
    seen: set[str] = set()
    for section in plan.get("sections") or []:
        for concept in (section.get("concepts") or []) if isinstance(section, dict) else []:
            if not isinstance(concept, dict) or concept.get("role") not in {"core", "supporting"}:
                continue
            key = concept.get("id") or concept.get("name")
            if key in seen:
                continue
            seen.add(key)
            counts["total"] += 1
            anchor = concept.get("anchor")
            if isinstance(anchor, dict):
                counts["anchored"] += 1
            elif anchor == "external":
                counts["external"] += 1
            else:
                counts["no_anchor"] += 1
    return counts


def cross_lesson_edges(plan: dict, concept_ids: set[str]) -> list[str]:
    """Relation ids with an endpoint outside this lesson: carried over from an earlier course."""
    return [relation.get("id") or f"relations[{index}]"
            for index, relation in enumerate(plan.get("relations") or [])
            if isinstance(relation, dict)
            and any(relation.get(end) not in concept_ids for end in ("from", "to"))]


def anchor_passage(path: Path, locator: str) -> str | None:
    """What the locator points at: a heading's own section, or the paragraph its line sits in."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    heading = ANY_HEADING_ADOC if path.suffix.lower() in {".adoc", ".asciidoc"} else ANY_HEADING_MD
    target = normalize_text(locator)
    if not target:
        return None
    start: int | None = None
    level: int | None = None
    for index, line in enumerate(lines):  # an exact heading wins over any line that merely contains the words
        match = heading.match(line)
        if match and normalize_text(match.group(2)) == target:
            start, level = index + 1, len(match.group(1))
            break
    if start is None:
        for index, line in enumerate(lines):
            if target in normalize_text(line):
                match = heading.match(line)
                start, level = (index + 1, len(match.group(1))) if match else (index, None)
                break
    if start is None:
        return None
    body: list[str] = []
    for line in lines[start:]:
        match = heading.match(line)
        if match and (level is None or len(match.group(1)) <= level):
            break
        if level is None and body and not line.strip():
            break  # a plain locator: only the paragraph around it
        body.append(line)
    return "\n".join(body)


def thin_anchors(plan: dict, sources_root: Path) -> tuple[list[str], list[str]]:
    """Anchors that reach a name rather than an explanation. Advisory: never changes the exit code."""
    found: list[str] = []
    per_section: list[str] = []
    for section in plan.get("sections") or []:
        if not isinstance(section, dict):
            continue
        thin = total = 0
        for concept in section.get("concepts") or []:
            if not isinstance(concept, dict) or concept.get("role") not in {"core", "supporting"}:
                continue
            anchor = concept.get("anchor")
            if not isinstance(anchor, dict) or not nonempty(anchor.get("path")) or not nonempty(anchor.get("locator")):
                continue
            rel, locator = anchor["path"], anchor["locator"]
            if is_url(rel):
                continue
            key = concept.get("id") or concept.get("name")
            suffix = Path(rel).suffix.lower()
            if suffix in DATA_SUFFIXES:
                total, thin = total + 1, thin + 1
                found.append(f'thin anchor {key} -> {rel} "{locator}" (data or code file: the locator reaches a key name)')
                continue
            path = sources_root / rel
            if suffix not in TEXT_SUFFIXES or not path.is_file():
                continue  # nothing readable there: not judged
            total += 1
            passage = anchor_passage(path, locator)
            if passage is None:
                thin += 1
                found.append(f'thin anchor {key} -> {rel} "{locator}" (the locator is not in the file)')
                continue
            size = len("".join(passage.split()))
            if size < THIN_ANCHOR_CHARS:
                thin += 1
                found.append(f'thin anchor {key} -> {rel} "{locator}" ({size} characters, under {THIN_ANCHOR_CHARS})')
        if thin:
            per_section.append(f"{section.get('id')} {thin}/{total} concepts on thin anchors")
    return found, per_section


def validate_criteria(checkpoint: dict, location: str, errors: list[str], version: str) -> None:
    criteria = checkpoint.get("criteria")
    if version == "1.0":
        require_text_list(checkpoint, "criteria", location, errors)
        return
    if not isinstance(criteria, list) or not criteria:
        errors.append(f"{location}.criteria must be a non-empty list of objects")
        return
    seen: set[str] = set()
    for index, criterion in enumerate(criteria):
        c_location = f"{location}.criteria[{index}]"
        if not isinstance(criterion, dict):
            errors.append(f"{c_location} must be an object with id, text and layer")
            continue
        require_text(criterion, "id", c_location, errors)
        require_text(criterion, "text", c_location, errors)
        if criterion.get("layer") not in LAYERS:
            errors.append(f"{c_location}.layer must be one of {list(LAYERS)}")
        if nonempty(criterion.get("id")):
            if criterion["id"] in seen:
                errors.append(f"{c_location}.id duplicates '{criterion['id']}'")
            seen.add(criterion["id"])


def registered_concept_ids(store: Path | None) -> set[str] | None:
    """Ids in the store's cross-course registry, or None when no store was given (offline check stays strict)."""
    if store is None:
        return None
    path = store / "concepts" / "index.json"
    if not path.is_file():
        raise ValueError(f"no concept index at {path}; run store_init.py init --store {store}")
    concepts = json.loads(path.read_text(encoding="utf-8")).get("concepts")
    return set(concepts) if isinstance(concepts, dict) else set()


def validate_relations(plan: dict, concept_ids: set[str], errors: list[str], manifest_paths: set[str] | None,
                       registered: set[str] | None = None) -> None:
    relations = plan.get("relations", [])
    if not isinstance(relations, list):
        errors.append("root.relations must be a list")
        return
    seen: set[str] = set()
    for index, relation in enumerate(relations):
        location = f"relations[{index}]"
        if not isinstance(relation, dict):
            errors.append(f"{location} must be an object")
            continue
        require_text(relation, "id", location, errors)
        if nonempty(relation.get("id")):
            if relation["id"] in seen:
                errors.append(f"{location}.id duplicates '{relation['id']}'")
            seen.add(relation["id"])
        for end in ("from", "to"):
            if relation.get(end) in concept_ids:
                continue
            if registered is not None and relation.get(end) in registered:
                continue  # a concept carried over from an earlier course, registered in the store
            errors.append(f"{location}.{end} '{relation.get(end)}' is not a concept id in this lesson"
                          + ("" if registered is None else " and is not registered in the store"))
        if relation.get("from") == relation.get("to") and relation.get("from") is not None:
            errors.append(f"{location} must not connect a concept to itself")
        if relation.get("type") not in RELATION_TYPES:
            errors.append(f"{location}.type must be one of {sorted(RELATION_TYPES)}")
        if relation.get("layer") not in LAYERS:
            errors.append(f"{location}.layer must be one of {list(LAYERS)}")
        if "rationale" in relation and not nonempty(relation.get("rationale")):
            errors.append(f"{location}.rationale must be a non-empty string when present")
        validate_source_refs(relation.get("source_refs"), location, errors, manifest_paths)


def criteria_texts(checkpoint: Any) -> list[str]:
    """Criterion texts for either schema version (strings in 1.0, objects in 1.1)."""
    if not isinstance(checkpoint, dict) or not isinstance(checkpoint.get("criteria"), list):
        return []
    texts: list[str] = []
    for criterion in checkpoint["criteria"]:
        if isinstance(criterion, str):
            texts.append(criterion)
        elif isinstance(criterion, dict) and isinstance(criterion.get("text"), str):
            texts.append(criterion["text"])
    return texts


def validate_plan(plan: Any, manifest_paths: set[str] | None = None, allow_empty_coverage: bool = False,
                  registered: set[str] | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(plan, dict):
        return ["lesson plan root must be an object"]
    if plan.get("schema_version") not in SCHEMA_VERSIONS:
        errors.append(f"schema_version must be one of {sorted(SCHEMA_VERSIONS)}")
    version = schema_version(plan)
    names_by_id: dict[str, str] = {}
    if version in ROLE_AWARE_VERSIONS:
        if plan.get("mode") not in MODES:
            errors.append(f"root.mode must be one of {sorted(MODES)} (schema 1.2)")
        if "outline_confirmed_at" not in plan:
            errors.append("root.outline_confirmed_at must be present (null until the learner confirms the outline)")
        elif plan["outline_confirmed_at"] is not None and not nonempty(plan["outline_confirmed_at"]):
            errors.append("root.outline_confirmed_at must be null or an ISO timestamp")
    for key in ("lesson_id", "title", "learning_goal"):
        require_text(plan, key, "root", errors)

    big_picture = plan.get("big_picture")
    if not isinstance(big_picture, dict):
        errors.append("root.big_picture must be an object")
    else:
        require_text(big_picture, "problem", "big_picture", errors)
        require_text(big_picture, "outcome", "big_picture", errors)
        require_text_list(big_picture, "system_map", "big_picture", errors)

    sections = plan.get("sections")
    if not isinstance(sections, list) or not sections:
        errors.append("root.sections must be a non-empty list")
        sections = []

    seen: set[str] = set()
    for index, section in enumerate(sections):
        location = f"sections[{index}]"
        if not isinstance(section, dict):
            errors.append(f"{location} must be an object")
            continue
        for key in ("id", "title", "problem", "solution", "mechanism", "meaning"):
            require_text(section, key, location, errors)
        section_id = section.get("id")
        if nonempty(section_id):
            if section_id in seen:
                errors.append(f"{location}.id duplicates '{section_id}'")

        depends_on = section.get("depends_on")
        if not isinstance(depends_on, list) or not all(nonempty(item) for item in depends_on):
            errors.append(f"{location}.depends_on must be a list of section ids")
        else:
            for dependency in depends_on:
                if dependency not in seen:
                    errors.append(f"{location}.depends_on references '{dependency}' before it is available")
        if nonempty(section_id):
            seen.add(section_id)

        validate_tradeoffs(section, location, errors, version, manifest_paths)
        new_problem = section.get("new_problem")
        if index < len(sections) - 1 and not nonempty(new_problem):
            errors.append(f"{location}.new_problem must lead into the next section")
        elif index == len(sections) - 1 and new_problem is not None and not nonempty(new_problem):
            errors.append(f"{location}.new_problem must be null or a non-empty string")

        concepts = section.get("concepts")
        if not isinstance(concepts, list) or not concepts:
            errors.append(f"{location}.concepts must be a non-empty list")
        else:
            for concept_index, concept in enumerate(concepts):
                concept_location = f"{location}.concepts[{concept_index}]"
                if not isinstance(concept, dict):
                    errors.append(f"{concept_location} must be an object")
                    continue
                require_text(concept, "name", concept_location, errors)
                require_text(concept, "explanation", concept_location, errors)
                if version != "1.0":
                    validate_concept_v11(concept, concept_location, errors, names_by_id)
                if version in ROLE_AWARE_VERSIONS:
                    validate_concept_v12(concept, concept_location, errors)
                if version == "1.5":
                    validate_concept_v15(concept, concept_location, errors, manifest_paths)
                elif any(key in concept for key in V15_CONCEPT_KEYS):
                    errors.append(f"{concept_location}.contrast / cases / ontology require schema_version '1.5'")

        if "principle" in section and not nonempty(section.get("principle")):
            errors.append(f"{location}.principle must be a non-empty string when present")

        validate_source_refs(section.get("source_refs"), location, errors, manifest_paths)

        checkpoint = section.get("checkpoint")
        if not isinstance(checkpoint, dict):
            errors.append(f"{location}.checkpoint must be an object")
        else:
            require_text(checkpoint, "prompt", f"{location}.checkpoint", errors)
            require_text(checkpoint, "hint", f"{location}.checkpoint", errors)
            validate_criteria(checkpoint, f"{location}.checkpoint", errors, version)

    if version != "1.0":
        validate_relations(plan, set(names_by_id), errors, manifest_paths, registered)
    elif "relations" in plan:
        errors.append("root.relations requires schema_version '1.1'")
    if version in ROLE_AWARE_VERSIONS:
        validate_deferred(plan, seen, set(names_by_id), errors)
        validate_coverage(plan, seen, errors, allow_empty_coverage)
    else:
        for key in ("mode", "coverage", "deferred"):
            if key in plan:
                errors.append(f"root.{key} requires schema_version '1.2'")
    if version in SHAPE_AWARE_VERSIONS:
        validate_v13(plan, set(names_by_id), errors)
    else:
        for key in ("shape", "parent_course", "branch_candidates"):
            if key in plan:
                errors.append(f"root.{key} requires schema_version '1.3'")
    if version in PREREQUISITE_VERSIONS:
        validate_v14(plan, errors)
    else:
        for key in PREREQUISITE_KEYS:
            if key in plan:
                errors.append(f"root.{key} requires schema_version '1.4'")
    if version == "1.5":
        validate_v15(plan, seen, errors)
    else:
        if "review_of" in plan or plan.get("shape") == "review":
            errors.append("root.review_of / shape review require schema_version '1.5'")
        for index, section in enumerate(sections):
            if isinstance(section, dict) and "parent_section" in section:
                errors.append(f"sections[{index}].parent_section requires schema_version '1.5'")

    final_challenge = plan.get("final_challenge")
    if not isinstance(final_challenge, dict):
        errors.append("root.final_challenge must be an object")
    else:
        require_text(final_challenge, "prompt", "final_challenge", errors)
        require_text_list(final_challenge, "criteria", "final_challenge", errors)

    uncertainties = plan.get("uncertainties")
    if not isinstance(uncertainties, list) or not all(nonempty(item) for item in uncertainties):
        errors.append("root.uncertainties must be a list of non-empty strings")
    return errors


def collect_warnings(plan: Any) -> list[str]:
    """Cognitive-load advisories that do not fail validation."""
    warnings: list[str] = []
    if not isinstance(plan, dict):
        return warnings
    sections = plan.get("sections")
    if not isinstance(sections, list):
        return warnings
    if len(sections) > MAX_SECTIONS_PER_LESSON and plan_shape(plan) != "skeleton":
        warnings.append(
            f"lesson has {len(sections)} sections (> {MAX_SECTIONS_PER_LESSON}); "
            "consider a skeleton pass with on-demand expansion"
        )
    role_aware = schema_version(plan) in ROLE_AWARE_VERSIONS
    skeleton = plan_shape(plan) == "skeleton"
    confirmed = plan.get("outline_confirmed_at")
    if role_aware and isinstance(confirmed, str) and re.search(r"T00:00(:00)?(\.0+)?(Z|[+-]\d\d:\d\d)?$", confirmed):
        warnings.append("outline_confirmed_at looks like a placeholder (midnight); record the real time, e.g. `date -u +%FT%TZ`")
    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        concepts = section.get("concepts")
        if not isinstance(concepts, list):
            continue
        if not role_aware:
            if len(concepts) > MAX_CONCEPTS_PER_SECTION:
                warnings.append(
                    f"sections[{index}] introduces {len(concepts)} concepts "
                    f"(> {MAX_CONCEPTS_PER_SECTION}); consider splitting the section"
                )
            continue
        core = [c for c in concepts if isinstance(c, dict) and c.get("role") == "core"]
        supporting = [c for c in concepts if isinstance(c, dict) and c.get("role") == "supporting"]
        if len(core) > MAX_CONCEPTS_PER_SECTION:
            warnings.append(
                f"sections[{index}] has {len(core)} core concepts (> {MAX_CONCEPTS_PER_SECTION}); "
                "demote some to supporting or split the section — do not drop them"
            )
        if len(supporting) > MAX_SUPPORTING_PER_SECTION:
            warnings.append(f"sections[{index}] has {len(supporting)} supporting concepts (> {MAX_SUPPORTING_PER_SECTION})")
        for c_index, concept in enumerate(concepts):
            if isinstance(concept, dict) and concept.get("role") == "supporting" and not isinstance(concept.get("check"), dict):
                warnings.append(f"sections[{index}].concepts[{c_index}] is 'supporting' but has no check question; the learner cannot ask to verify it")
            if skeleton and isinstance(concept, dict) and concept.get("anchor") == "no-anchor":
                warnings.append(f"sections[{index}].concepts[{c_index}] has no anchor in the learner's materials; the learner decides whether to keep it as general background or drop it")
            if isinstance(concept, dict) and concept.get("role") == "listed" and len(str(concept.get("explanation", ""))) > MAX_LISTED_EXPLANATION_CHARS:
                warnings.append(
                    f"sections[{index}].concepts[{c_index}] is 'listed' but its explanation is long "
                    f"(> {MAX_LISTED_EXPLANATION_CHARS} chars); listed concepts get a one-line fact-layer definition only"
                )
    return warnings


def deferred_section_ids(plan: dict) -> set[str]:
    return {item["id"] for item in (plan.get("deferred") or []) if isinstance(item, dict) and item.get("type") == "section"}


def hidden_texts(section: dict) -> list[tuple[str, str]]:
    """(label, text) pairs that must never appear in learner-facing documents of a 1.2 pack."""
    pairs: list[tuple[str, str]] = []
    for criterion in criteria_texts(section.get("checkpoint")):
        pairs.append(("assessment criterion", criterion))
    for criterion in criteria_texts(section.get("probe")):
        pairs.append(("probe criterion", criterion))
    for concept in section.get("concepts") or []:
        if isinstance(concept, dict):
            for criterion in criteria_texts(concept.get("check")):
                pairs.append(("supporting check criterion", criterion))
    if nonempty(section.get("principle")):
        pairs.append(("principle-layer content", section["principle"]))
    if nonempty(section.get("meaning")):
        pairs.append(("rationale-layer meaning", section["meaning"]))
    for tradeoff in section.get("tradeoffs") or []:
        text = tradeoff_text(tradeoff)
        if nonempty(text):
            pairs.append(("rationale-layer tradeoff", text))
    return pairs


MERMAID_BLOCK = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)


def mermaid_blocks(text: str) -> list[str]:
    return [m.group(1) for m in MERMAID_BLOCK.finditer(text)]


def validate_outline(outline: str, plan: dict) -> list[str]:
    """outline.md must show the route and every concept, and hide everything above the public layer."""
    errors: list[str] = []
    normalized = normalize_text(outline)
    if schema_version(plan) == "1.5":  # new courses: the problem chain is also drawn (diagram.py --chain)
        diagrams = normalize_text("\n".join(mermaid_blocks(outline)))
        if not diagrams:
            errors.append("outline must contain a mermaid diagram of the problem chain (paste `diagram.py <plan> --chain`)")
        else:
            deferred = deferred_section_ids(plan)
            for section in plan.get("sections", []) or []:
                if isinstance(section, dict) and nonempty(section.get("id")) and section["id"] not in deferred:
                    title = section.get("title") or ""
                    if normalize_text(section["id"]) not in diagrams and (not title or normalize_text(title) not in diagrams):
                        errors.append(f"outline's mermaid diagram does not show section '{section['id']}'")
    if nonempty(plan.get("title")) and plan["title"] not in outline:
        errors.append(f"outline does not contain title '{plan['title']}'")
    mode = plan.get("mode")
    if mode and mode not in outline and {"full": "完整", "fast": "快速"}.get(mode, "") not in outline:
        errors.append("outline must state the learning mode")
    for index, section in enumerate(plan.get("sections", []) or []):
        if not isinstance(section, dict):
            continue
        if nonempty(section.get("title")) and section["title"] not in outline:
            errors.append(f"outline does not contain section title '{section['title']}'")
        for concept in section.get("concepts") or []:
            if isinstance(concept, dict) and nonempty(concept.get("name")) and normalize_text(concept["name"]) not in normalized:
                errors.append(f"outline does not list concept '{concept['name']}' of sections[{index}]")
        for label, text in hidden_texts(section):
            if criterion_leaked(text, normalized):
                errors.append(f"outline leaks {label} from sections[{index}]")
    if plan_shape(plan) == "skeleton":
        for item in plan.get("branch_candidates") or []:
            if isinstance(item, dict) and nonempty(item.get("title")) and normalize_text(item["title"]) not in normalized:
                errors.append(f"outline does not list branch candidate '{item['title']}'")
    return errors


def reviewed_sections(paths: list[Path] | None) -> dict[tuple[str, str], dict]:
    """{(lesson_id, section_id): section} from the reviewed courses' lesson plans."""
    found: dict[tuple[str, str], dict] = {}
    for path in paths or []:
        plan = json.loads(path.read_text(encoding="utf-8"))
        for section in plan.get("sections", []) or []:
            if isinstance(section, dict) and nonempty(section.get("id")):
                found[(plan.get("lesson_id"), section["id"])] = section
    return found


def review_leaks(section: dict, normalized: str, reviewed: dict[tuple[str, str], dict]) -> list[str]:
    """Sentences of the reviewed section's solution/mechanism that reappear verbatim (a review is not a re-teaching)."""
    parent = section.get("parent_section")
    if not isinstance(parent, dict):
        return []
    source = reviewed.get((parent.get("lesson_id"), parent.get("section_id")))
    if source is None:
        return [f"reviewed section {parent.get('lesson_id')}/{parent.get('section_id')} not found in --reviewed plans"]
    leaks = []
    for key in ("solution", "mechanism"):
        for sentence in re.split(r"[。；;.!?！？\n]", str(source.get(key) or "")):
            piece = normalize_text(sentence)
            if len(piece) >= REVIEW_LEAK_MIN_CHARS and piece in normalized:
                leaks.append(f"{key}: “{sentence.strip()[:40]}…”")
    return leaks


def validate_units(units_dir: Path, plan: dict, reviewed_plans: list[Path] | None = None) -> tuple[list[str], list[str]]:
    """Each non-deferred section needs units/<id>.md with its title, checkpoint and every concept; no leaks."""
    errors: list[str] = []
    warnings: list[str] = []
    deferred = deferred_section_ids(plan)
    reviewed = reviewed_sections(reviewed_plans) if plan_shape(plan) == "review" else {}
    if plan_shape(plan) == "review" and not reviewed_plans:
        warnings.append("review course: pass --reviewed <lesson-plan.json> of each reviewed course to check that unit documents do not repeat their solution/mechanism")
    for index, section in enumerate(plan.get("sections", []) or []):
        if not isinstance(section, dict) or not nonempty(section.get("id")):
            continue
        path = units_dir / f"{section['id']}.md"
        if section["id"] in deferred:
            if path.exists():
                warnings.append(f"units/{section['id']}.md exists although the section is deferred")
            continue
        if not path.is_file():
            errors.append(f"missing unit document units/{section['id']}.md")
            continue
        text = path.read_text(encoding="utf-8")
        normalized = normalize_text(text)
        if nonempty(section.get("title")) and section["title"] not in text:
            errors.append(f"units/{section['id']}.md does not contain its title")
        if "轮到你" not in text and "Your turn" not in text and "Checkpoint" not in text:
            errors.append(f"units/{section['id']}.md must visibly include the learner checkpoint")
        checkpoint_prompt = (section.get("checkpoint") or {}).get("prompt") if isinstance(section.get("checkpoint"), dict) else None
        if nonempty(checkpoint_prompt) and not criterion_leaked(checkpoint_prompt, normalized):
            errors.append(f"units/{section['id']}.md does not contain its checkpoint.prompt (the visible question must be the checkpoint, not a rewrite)")
        probe_prompt = (section.get("probe") or {}).get("prompt") if isinstance(section.get("probe"), dict) else None
        if nonempty(probe_prompt) and criterion_leaked(probe_prompt, normalized):
            errors.append(f"units/{section['id']}.md contains the probe question; probes are asked no-hint before teaching and never printed in unit documents")
        for concept in section.get("concepts") or []:
            if isinstance(concept, dict) and nonempty(concept.get("name")) and normalize_text(concept["name"]) not in normalized:
                errors.append(f"units/{section['id']}.md does not mention concept '{concept['name']}'")
        if "想验收" in text or "说“验收" in text or '说"验收' in text:
            warnings.append(f"units/{section['id']}.md carries a '验收 X' reminder next to a supporting concept; that instruction belongs in outline.md only")
        for label, text_hidden in hidden_texts(section):
            if label.startswith("rationale-layer"):
                if criterion_leaked(text_hidden, normalized):
                    warnings.append(f"units/{section['id']}.md prints {label} verbatim; it should drive questions, not be shown")
            elif criterion_leaked(text_hidden, normalized):
                errors.append(f"units/{section['id']}.md leaks {label}")
        if reviewed:
            for leak in review_leaks(section, normalized, reviewed):
                errors.append(f"units/{section['id']}.md repeats the reviewed section ({leak}); a review section asks first and reveals in a new context")
    return errors, warnings


def sources_root_from_manifest(manifest_path: Path, manifest: Any) -> Path | None:
    """Material root recorded in sources.json: base_path relative to the manifest's own directory.
    "." (legacy: relative to whatever cwd was at generation) cannot be resolved and yields None."""
    if not isinstance(manifest, dict):
        return None
    base = manifest.get("base_path")
    if not nonempty(base) or base.strip() == ".":
        return None
    candidate = Path(base).expanduser()
    if not candidate.is_absolute():
        candidate = manifest_path.resolve().parent / candidate
    return candidate.resolve()


def manifest_paths(manifest: Any) -> set[str]:
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        raise ValueError("source manifest must contain a files list")
    return {
        item["path"]
        for item in manifest["files"]
        if isinstance(item, dict) and nonempty(item.get("path"))
    }


def validate_guide(guide: str, plan: dict) -> list[str]:
    errors: list[str] = []
    normalized_guide = normalize_text(guide)
    for field in (plan.get("title"), *(section.get("title") for section in plan.get("sections", []) if isinstance(section, dict))):
        if nonempty(field) and field not in guide:
            errors.append(f"teaching guide does not contain title '{field}'")
    if "轮到你" not in guide and "Your turn" not in guide and "Checkpoint" not in guide:
        errors.append("teaching guide must visibly include at least one learner checkpoint")
    for index, section in enumerate(plan.get("sections", [])):
        if not isinstance(section, dict):
            continue
        for criterion in criteria_texts(section.get("checkpoint")):
            if nonempty(criterion) and criterion_leaked(criterion, normalized_guide):
                errors.append(
                    f"teaching guide leaks assessment criterion from sections[{index}]: '{criterion}'"
                )
        principle = section.get("principle")
        if nonempty(principle) and criterion_leaked(principle, normalized_guide):
            errors.append(f"teaching guide leaks principle-layer content from sections[{index}]")
    return errors


def guide_warnings(guide: str, plan: dict) -> list[str]:
    """Advisories for 1.1 guides: meaning/tradeoffs belong to the rationale layer and should
    feed questions rather than be printed. Verbatim copies are reported, not failed."""
    warnings: list[str] = []
    if schema_version(plan) == "1.0":
        return warnings
    normalized_guide = normalize_text(guide)
    for index, section in enumerate(plan.get("sections", [])):
        if not isinstance(section, dict):
            continue
        if nonempty(section.get("meaning")) and criterion_leaked(section["meaning"], normalized_guide):
            warnings.append(f"sections[{index}].meaning appears verbatim in the guide; rationale-layer text should drive questions, not be shown")
        for tradeoff in section.get("tradeoffs") or []:
            if nonempty(tradeoff) and criterion_leaked(tradeoff, normalized_guide):
                warnings.append(f"sections[{index}] tradeoff appears verbatim in the guide: '{tradeoff}'")
    return warnings


LEAK_MIN_CHARS = 12
LEAK_WINDOW_CHARS = 16
NORMALIZE_STRIP = re.compile(r"[\s\W_]+", re.UNICODE)


def normalize_text(text: str) -> str:
    """Casefold and drop whitespace/punctuation so cosmetic rewording does not hide a leak."""
    return NORMALIZE_STRIP.sub("", text).casefold()


def criterion_leaked(criterion: str, normalized_guide: str) -> bool:
    """Guardrail, not a proof: catches verbatim and near-verbatim copies.

    A criterion counts as leaked when its normalized form appears in the guide,
    or when a long enough contiguous window of it does (so splitting a criterion
    across two sentences or changing punctuation does not evade the check).
    Paraphrase remains undetectable by construction; that judgment stays with
    the model and the author.
    """
    normalized = normalize_text(criterion)
    if len(normalized) < LEAK_MIN_CHARS:
        return bool(normalized) and normalized in normalized_guide
    if normalized in normalized_guide:
        return True
    if len(normalized) <= LEAK_WINDOW_CHARS:
        return False
    return any(
        normalized[start : start + LEAK_WINDOW_CHARS] in normalized_guide
        for start in range(0, len(normalized) - LEAK_WINDOW_CHARS + 1)
    )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lesson_plan", type=Path)
    parser.add_argument("--guide", type=Path, help="teaching-guide.md (schema 1.0/1.1 packs)")
    parser.add_argument("--outline", type=Path, help="outline.md (schema 1.2+ packs)")
    parser.add_argument("--units-dir", type=Path, help="units/ directory (schema 1.2+ packs)")
    parser.add_argument("--reviewed", type=Path, action="append", help="lesson-plan.json of a reviewed course (review courses; repeatable)")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--sources-root", type=Path, help="Material root for the coverage check; defaults to sources.json base_path (relative to the pack)")
    parser.add_argument("--store", type=Path, help="Knowledge store: relation endpoints registered there may come from an earlier course")
    parser.add_argument("--allow-empty-coverage", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        plan = load_json(args.lesson_plan)
        manifest = load_json(args.manifest) if args.manifest else None
        paths = manifest_paths(manifest) if manifest is not None else None
        sources_root = args.sources_root
        if sources_root is None:
            manifest_path = args.manifest or (args.lesson_plan.parent / "sources.json")
            if manifest_path.is_file():
                sources_root = sources_root_from_manifest(manifest_path, manifest if manifest is not None else load_json(manifest_path))
                if sources_root is not None:
                    print(f"INFO: sources root {sources_root} (from {manifest_path.name} base_path)")
        registered = registered_concept_ids(args.store)
        errors = validate_plan(plan, paths, allow_empty_coverage=args.allow_empty_coverage, registered=registered)
        warnings = collect_warnings(plan)
        if args.guide:
            guide = args.guide.read_text(encoding="utf-8")
            errors.extend(validate_guide(guide, plan))
            warnings.extend(guide_warnings(guide, plan))
        if args.outline:
            errors.extend(validate_outline(args.outline.read_text(encoding="utf-8"), plan))
        if args.units_dir:
            unit_errors, unit_warnings = validate_units(args.units_dir, plan, args.reviewed)
            errors.extend(unit_errors)
            warnings.extend(unit_warnings)
        if sources_root and schema_version(plan) in ROLE_AWARE_VERSIONS:
            errors.extend(validate_coverage_against_sources(plan, sources_root))
        if plan_shape(plan) == "skeleton":
            g = grounding(plan)
            print(f"INFO: grounding {g['anchored']}/{g['total']} core+supporting concepts anchored in the evidence pool "
                  f"({g['external']} external, {g['no_anchor']} no-anchor) — no threshold; the learner judges")
            if sources_root and schema_version(plan) in SHAPE_AWARE_VERSIONS:
                thin, per_section = thin_anchors(plan, sources_root)
                warnings.extend(thin)
                for line in per_section:
                    print(f"INFO: {line} — no threshold; add material or build as is, the learner decides")
        if is_prerequisite_course(plan):
            f = fact_ratio(plan)
            print(f"INFO: prerequisite course of {plan.get('prerequisite_of')} (depth {plan.get('depth')}, blocked at {plan.get('blocked_at')}); "
                  f"fact ratio {f['fact']}/{f['total']} concepts are fact-layer — no threshold; when nearly all are conventions, the next level is cards, not a course")
        if schema_version(plan) == "1.5":
            v = variation_ratio(plan)
            print(f"INFO: variation {v['contrast']}/{v['total']} core concepts have a contrast pair, {v['cases']}/{v['total']} have two cases "
                  f"— no threshold; a concept without them is taught from one example")
        if schema_version(plan) != "1.0":
            o = orphan_concepts(plan)
            if o["orphans"]:
                print(f"INFO: orphan concepts {len(o['orphans'])}/{o['total']} core concepts appear in no relation "
                      f"({', '.join(o['orphans'])}) — no threshold; a chain rebuild cannot reach them")
        if registered is not None and schema_version(plan) != "1.0":
            local = {c["id"] for s in (plan.get("sections") or []) if isinstance(s, dict)
                     for c in (s.get("concepts") or []) if isinstance(c, dict) and nonempty(c.get("id"))}
            crossing = cross_lesson_edges(plan, local)
            if crossing:
                print(f"INFO: relations {len(crossing)} cross-lesson edges ({', '.join(crossing)}) — endpoints registered in the store, "
                      f"not concepts of this lesson; asked at PREDICT, left out of the chain rebuild")
        x = external_refs(plan)
        if x["external"]:
            print(f"INFO: external refs {x['external']}/{x['total']} source refs come from outside the learner's materials "
                  f"— no threshold; the learner judges whether the course drifted")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}")
        return 2
    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"OK: {args.lesson_plan} is a valid guided-learning lesson plan")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
