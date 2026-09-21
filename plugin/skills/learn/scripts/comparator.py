#!/usr/bin/env python3
"""Classify one learner attempt against the machine reference graph (one-directional diagnosis).

Input: the model's structured reading of the learner's free-text answer (see
assets/extraction-template.json). The model decides *semantics* (which concepts were
named, which relations asserted, which propositions are correct / partial / wrong);
this script decides *categories* deterministically and never scores.

Output categories (docs/specs/knowledge-store.md §5.1):
  missing              core concept of the section never mentioned (supporting/listed never count as missing)
  partial              concept or proposition only partly covered
  conflict             wrong proposition / wrong relation against explicit|entailed|external reference
  weak_reference       wrong against a pedagogical_inference-only reference → do NOT judge the learner wrong
  representation_only  correct, differently worded → not reported
  beyond_reference     concept or relation the reference does not have → recorded, not judged
  unresolved_refs      names the script could not map to a concept id

`compare_relations` is the whole-lesson entry (chain rebuild at the end of a course): the
relations the learner asserted, as a set, against the public reference edges, as a set.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any


STRONG_SUPPORT = {"explicit", "entailed", "external"}
SYMMETRIC_TYPES = {"contrasts_with"}
CONCEPT_STATUSES = {"correct", "partial", "wrong", "missing"}
RELATION_STATUSES = {"correct", "direction_reversed", "wrong_type", "missing", "extra"}
PROPOSITION_STATUSES = {"correct", "partial", "wrong", "representation_only"}


def normalize(text: str) -> str:
    return unicodedata.normalize("NFC", str(text).strip()).casefold()


def proposition_id(text: str) -> str:
    return "p-" + hashlib.sha1(normalize(text).encode("utf-8")).hexdigest()[:8]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


class Reference:
    """Public + deep MRG for one lesson, plus the store's alias index."""

    def __init__(self, public: dict, deep: dict, alias_index: dict[str, str] | None = None) -> None:
        self.nodes: dict[str, dict] = {}
        for node in public.get("nodes", []) + deep.get("nodes", []):
            self.nodes[node["id"]] = node
        edges = list(public.get("edges", []))
        # the chain rebuild gives the learner this lesson's concept names only, so an edge reaching
        # a concept carried over from an earlier course cannot be stated and is not a reference edge
        self.public_edges: list[dict] = [e for e in edges if e.get("from") in self.nodes and e.get("to") in self.nodes]
        self.edges: list[dict] = edges + list(deep.get("edges", []))
        self.sections = {section["id"]: section for section in public.get("sections", [])}
        self.lookup: dict[str, str] = {}
        for node in self.nodes.values():
            self.lookup[normalize(node["id"])] = node["id"]
            if node.get("name"):
                self.lookup.setdefault(normalize(node["name"]), node["id"])
            for alias in node.get("aliases", []) or []:
                self.lookup.setdefault(normalize(alias), node["id"])
        for alias, cid in (alias_index or {}).items():
            self.lookup.setdefault(normalize(alias), cid)

    def resolve(self, ref: Any) -> str | None:
        if not isinstance(ref, str) or not ref.strip():
            return None
        return self.lookup.get(normalize(ref))

    def section_concepts(self, section_id: str, role: str = "core") -> list[str]:
        """Concept ids of a section by role. Exports without role info treat every concept as core."""
        section = self.sections.get(section_id)
        if section is None:
            raise ValueError(f"section '{section_id}' not found in MRG")
        key = f"{role}_concept_ids"
        if key in section:
            return list(section[key])
        return list(section.get("concept_ids", [])) if role == "core" else []

    def edge_between(self, a: str, b: str) -> dict | None:
        for edge in self.edges:
            if {edge.get("from"), edge.get("to")} == {a, b}:
                return edge
        return None

    def strongest_support(self, concept_ids: list[str], edge: dict | None = None) -> str:
        """Best support type among the involved nodes' refs (and the edge's refs, if any)."""
        supports: set[str] = set()
        refs: list[dict] = []
        for cid in concept_ids:
            node = self.nodes.get(cid)
            if node:
                refs.extend(node.get("source_refs", []))
        if edge:
            refs.extend(edge.get("source_refs", []))
        for ref in refs:
            if isinstance(ref, dict) and ref.get("support"):
                supports.add(ref["support"])
        if supports & STRONG_SUPPORT:
            return "strong"
        if "pedagogical_inference" in supports:
            return "pedagogical_inference"
        return "unsupported"


def compare(reference: Reference, section_id: str, extraction: dict) -> dict:
    diff: dict[str, list] = {
        "missing": [], "partial": [], "conflict": [], "weak_reference": [],
        "representation_only": [], "beyond_reference": [], "unresolved_refs": [], "unmentioned_supporting": [],
    }
    mentioned: set[str] = set()

    for item in extraction.get("concepts", []) or []:
        status = item.get("status")
        if status not in CONCEPT_STATUSES:
            raise ValueError(f"concept status must be one of {sorted(CONCEPT_STATUSES)}: {item}")
        cid = reference.resolve(item.get("ref"))
        if cid is None:
            if status != "missing":
                diff["beyond_reference"].append({"kind": "concept", "ref": item.get("ref"), "status": status})
                diff["unresolved_refs"].append(item.get("ref"))
            continue
        if status != "missing":
            mentioned.add(cid)
        if status == "partial":
            diff["partial"].append({"kind": "concept", "id": cid})
        elif status == "wrong":
            bucket = "conflict" if reference.strongest_support([cid]) == "strong" else "weak_reference"
            diff[bucket].append({"kind": "concept", "id": cid})

    for cid in reference.section_concepts(section_id, "core"):
        if cid not in mentioned:
            diff["missing"].append(cid)
    # supporting concepts are taught but not required in the main answer; listed ones are never expected
    diff["unmentioned_supporting"] = [cid for cid in reference.section_concepts(section_id, "supporting") if cid not in mentioned]

    for item in extraction.get("relations", []) or []:
        status = item.get("status")
        if status not in RELATION_STATUSES:
            raise ValueError(f"relation status must be one of {sorted(RELATION_STATUSES)}: {item}")
        a, b = reference.resolve(item.get("from")), reference.resolve(item.get("to"))
        record = {"kind": "relation", "from": a or item.get("from"), "to": b or item.get("to"), "type": item.get("type"), "status": status}
        if a is None or b is None:
            diff["beyond_reference"].append(record)
            diff["unresolved_refs"].extend(r for r in (item.get("from"), item.get("to")) if reference.resolve(r) is None)
            continue
        edge = reference.edge_between(a, b)
        if status == "correct":
            continue
        if status == "extra" or edge is None:
            diff["beyond_reference"].append(record)
            continue
        if status == "missing":
            diff["missing"].append({"kind": "relation", "id": edge.get("id"), "from": a, "to": b, "type": edge.get("type")})
            continue
        record["reference_type"] = edge.get("type")
        record["reference_from"], record["reference_to"] = edge.get("from"), edge.get("to")
        bucket = "conflict" if reference.strongest_support([a, b], edge) == "strong" else "weak_reference"
        diff[bucket].append(record)

    propositions_out: list[dict] = []
    for item in extraction.get("propositions", []) or []:
        status = item.get("status")
        text = item.get("text")
        if status not in PROPOSITION_STATUSES or not isinstance(text, str) or not text.strip():
            raise ValueError(f"proposition needs non-empty text and status in {sorted(PROPOSITION_STATUSES)}: {item}")
        concept_ids = [reference.resolve(r) for r in item.get("concept_refs", []) or []]
        unresolved = [r for r, cid in zip(item.get("concept_refs", []) or [], concept_ids) if cid is None]
        diff["unresolved_refs"].extend(unresolved)
        concept_ids = [cid for cid in concept_ids if cid]
        pid = item.get("id") or proposition_id(text)
        prop = {"id": pid, "text": text.strip(), "status": status, "concept_ids": concept_ids,
                "confidence_high": bool(item.get("confidence_high", False))}
        propositions_out.append(prop)
        if status == "representation_only":
            diff["representation_only"].append(pid)
        elif status == "partial":
            diff["partial"].append({"kind": "proposition", "id": pid})
        elif status == "wrong":
            if not concept_ids:
                diff["beyond_reference"].append({"kind": "proposition", "id": pid})
            else:
                bucket = "conflict" if reference.strongest_support(concept_ids) == "strong" else "weak_reference"
                diff[bucket].append({"kind": "proposition", "id": pid, "confidence_high": prop["confidence_high"]})

    diff["unresolved_refs"] = sorted({r for r in diff["unresolved_refs"] if isinstance(r, str)})
    return {"section_id": section_id, "diff": diff, "propositions": propositions_out,
            "feedback_priority": feedback_priority(diff)}


def section_pairs(reference: Reference) -> list[tuple[str, str]]:
    """The adjacent section pairs of the problem chain — the links the learner is asked to reproduce."""
    ordered = [s for s in reference.sections.values() if isinstance(s, dict) and not s.get("deferred")]
    ids = [s["id"] for s in ordered if s.get("id")]
    pairs: list[tuple[str, str]] = []
    for index, section in enumerate(ordered):
        depends = [d for d in (section.get("depends_on") or []) if d in ids]
        if not depends and index > 0:
            depends = [ids[index - 1]]  # same fallback the chain diagram draws
        for dep in depends:
            pair = (dep, section.get("id"))
            if pair not in pairs and all(pair):
                pairs.append(pair)
    return pairs


def chain_coverage(reference: Reference, asserted: list[dict]) -> dict:
    """How much of the section chain the learner's edges reach, whatever concepts they chose to name.

    A pair counts as covered when some asserted edge joins the two sections, in either direction:
    direction errors are already reported per concept edge, and what this number measures is
    whether the learner saw that these two sections are linked at all."""
    pairs = section_pairs(reference)
    where = {cid: set(node.get("section_ids") or []) for cid, node in reference.nodes.items()}
    covered: set[tuple[str, str]] = set()
    for item in asserted or []:
        if not isinstance(item, dict):
            continue
        a, b = reference.resolve(item.get("from")), reference.resolve(item.get("to"))
        if a is None or b is None:
            continue
        here, there = where.get(a, set()), where.get(b, set())
        for pair in pairs:
            if (pair[0] in here and pair[1] in there) or (pair[0] in there and pair[1] in here):
                covered.add(pair)
    return {"pairs": len(pairs), "covered": len(covered),
            "ratio": round(len(covered) / len(pairs), 3) if pairs else None,
            "missing_pairs": [list(pair) for pair in pairs if pair not in covered]}


def compare_relations(reference: Reference, asserted: list[dict]) -> dict:
    """Relation set against relation set, over the public edges of the whole lesson.

    Reports three numbers: `section_chain.ratio` (how much of the section chain the learner linked),
    `pair_ratio` (reference edges reached, direction or type wrong included) and `ratio` (exact).
    A course whose sections were all linked correctly can still score near zero on the last one by
    naming a different concept at each end, so feedback uses the first two.

    Each asserted relation is {from, to, type}; any `status` is ignored — the matching is done here.
    A reference edge is matched at most once. Deep-layer edges are not in the denominator: a learner
    relation that only matches one of them is recorded as beyond_reference, not judged."""
    result: dict[str, list] = {"matched": [], "direction_reversed": [], "wrong_type": [], "beyond_reference": [], "missing": [],
                               "unresolved_refs": []}
    used: set[int] = set()
    for item in asserted or []:
        if not isinstance(item, dict):
            raise ValueError(f"relation must be an object: {item}")
        a, b = reference.resolve(item.get("from")), reference.resolve(item.get("to"))
        record = {"from": a or item.get("from"), "to": b or item.get("to"), "type": item.get("type")}
        if a is None or b is None:
            result["beyond_reference"].append(record)
            result["unresolved_refs"].extend(r for r in (item.get("from"), item.get("to")) if reference.resolve(r) is None)
            continue
        candidates = [(i, e) for i, e in enumerate(reference.public_edges)
                      if i not in used and {e.get("from"), e.get("to")} == {a, b}]
        exact = [(i, e) for i, e in candidates if e.get("type") == item.get("type")
                 and ((e.get("from"), e.get("to")) == (a, b) or e.get("type") in SYMMETRIC_TYPES)]
        reversed_ = [(i, e) for i, e in candidates if e.get("type") == item.get("type") and (i, e) not in exact]
        if exact:
            i, e = exact[0]
            used.add(i)
            result["matched"].append(dict(record, id=e.get("id")))
        elif reversed_:
            i, e = reversed_[0]
            used.add(i)
            result["direction_reversed"].append(dict(record, id=e.get("id"), reference_from=e.get("from"), reference_to=e.get("to")))
        elif candidates:
            i, e = candidates[0]
            used.add(i)
            result["wrong_type"].append(dict(record, id=e.get("id"), reference_type=e.get("type")))
        else:
            result["beyond_reference"].append(record)
    for i, e in enumerate(reference.public_edges):
        if i not in used:
            result["missing"].append({"id": e.get("id"), "from": e.get("from"), "to": e.get("to"), "type": e.get("type")})
    result["unresolved_refs"] = sorted({r for r in result["unresolved_refs"] if isinstance(r, str)})
    total = len(reference.public_edges)
    result["reference_edges"] = total
    result["ratio"] = round(len(result["matched"]) / total, 3) if total else None
    # three numbers describe a chain rebuild, not one: which sections the learner linked at all,
    # which reference edges they reached however they named or directed them, and exact matches
    reached = len(result["matched"]) + len(result["direction_reversed"]) + len(result["wrong_type"])
    result["pair_ratio"] = round(reached / total, 3) if total else None
    result["section_chain"] = chain_coverage(reference, asserted)
    return result


def feedback_priority(diff: dict) -> list[str]:
    """Ordered list of what to address first (tutoring protocol: one thing at a time)."""
    order: list[str] = []
    high = [c for c in diff["conflict"] if c.get("confidence_high")]
    if high:
        order.append("conflict:high_confidence")
    if len(diff["conflict"]) > len(high):
        order.append("conflict")
    if diff["missing"]:
        order.append("missing")
    if diff["partial"]:
        order.append("partial")
    if diff["weak_reference"]:
        order.append("weak_reference:do_not_judge_wrong")
    if diff["beyond_reference"]:
        order.append("beyond_reference:record_only")
    return order


def load_reference(store: Path, lesson_id: str) -> Reference:
    public_path = store / "mrg" / f"{lesson_id}.json"
    deep_path = store / "mrg" / f"{lesson_id}.deep.json"
    if not public_path.is_file():
        raise ValueError(f"no MRG export for lesson '{lesson_id}' in {store} (run mrg_export.py first)")
    public = load_json(public_path)
    deep = load_json(deep_path) if deep_path.is_file() else {}
    index_path = store / "concepts" / "index.json"
    alias_index = load_json(index_path).get("alias_index", {}) if index_path.is_file() else {}
    return Reference(public, deep, alias_index)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--lesson-id", required=True)
    parser.add_argument("--section-id", help="Section to diagnose (required unless --chain)")
    parser.add_argument("--extraction", type=Path, required=True, help="Model extraction JSON (assets/extraction-template.json)")
    parser.add_argument("--chain", action="store_true", help="Whole-lesson relation set against the public reference edges (chain rebuild)")
    parser.add_argument("--output", type=Path, help="Write the diff here instead of stdout")
    args = parser.parse_args()
    if not args.chain and not args.section_id:
        parser.error("--section-id is required unless --chain")
    return args


def main() -> int:
    args = parse_args()
    try:
        reference = load_reference(args.store, args.lesson_id)
        extraction = load_json(args.extraction)
        if not isinstance(extraction, dict):
            raise ValueError("extraction root must be an object")
        result = compare_relations(reference, extraction.get("relations") or []) if args.chain \
            else compare(reference, args.section_id, extraction)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
        print(f"OK: diff written to {args.output}")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
