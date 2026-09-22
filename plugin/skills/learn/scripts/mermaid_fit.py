#!/usr/bin/env python3
"""Keep a Mermaid diagram narrow enough to read at note width.

Width is not a property a model can see: it is what the layout engine does to a topology.
So the structural decisions that drive it are made here, in code.

  mermaid_fit.py <file|-> [--width 96] [--report]      normalise a diagram written by hand
  from mermaid_fit import fit_direction, estimate_width   pick a direction while generating one

Two shapes are understood: `flowchart` / `graph` (TD, TB, LR, RL) and `sequenceDiagram`.
Any other line is passed through untouched and listed in the report, so this stays a
normaliser and never grows into a half-finished Mermaid parser.

Widths are counted in monospace columns; a full-width character counts as two. The numbers
are a relative measure of one layout against another, not a pixel prediction.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

WIDE = re.compile(r"[ᄀ-ᅟ⺀-꓏가-힣豈-﫿︰-﹯＀-｠￠-￦]")
BREAK = re.compile(r"<br\s*/?>")

NODE_PAD = 4          # a box's padding and border
RANK_GAP = 8          # separation between ranks, where edge labels also sit
NODE_GAP = 3          # separation between siblings inside one rank
GROUP_PAD = 4         # a subgraph's own frame
ACTOR_GAP = 6
DEFAULT_BUDGET = 96
MAX_LABEL = 16        # an edge label wider than this is wrapped
MAX_NODE = 24         # a node name wider than this is wrapped

FLOW_DIRECTIONS = ("TD", "TB", "LR", "RL")
VERTICAL = {"TD", "TB"}
SHAPES = [("[[", "]]"), ("[(", ")]"), ("([", "])"), ("((", "))"), ("{{", "}}"),
          ("[", "]"), ("(", ")"), ("{", "}"), (">", "]")]

HEADER = re.compile(r"^\s*(?P<kind>flowchart|graph|sequenceDiagram)\b\s*(?P<dir>[A-Z]{2})?\s*$")
SUBGRAPH = re.compile(r"^\s*subgraph\s+(?P<rest>.+?)\s*$")
END = re.compile(r"^\s*end\s*$")
PIPE_EDGE = re.compile(r"^\s*(?P<left>.+?)\s*(?P<arrow>-{2,3}>|-\.->|={2,3}>)\s*\|(?P<label>[^|]*)\|\s*(?P<right>.+?)\s*$")
MID_EDGE = re.compile(r"^\s*(?P<left>.+?)\s+(?P<opener>--|==)\s+(?P<label>.+?)\s+(?P<arrow>-{2,3}>|-{2,3}|={2,3}>)\s+(?P<right>.+?)\s*$")
PLAIN_EDGE = re.compile(r"^\s*(?P<left>.+?)\s*(?P<arrow>-{2,3}>|-\.->|={2,3}>|-\.-|-{3}|={3})\s*(?P<right>.+?)\s*$")
PARTICIPANT = re.compile(r"^\s*(?P<kw>participant|actor)\s+(?P<id>\S+)(?:\s+as\s+(?P<label>.+?))?\s*$")
MESSAGE = re.compile(r"^\s*(?P<left>[^\s:]+)\s*(?P<arrow>-{1,2}>>?|-{1,2}[)xX]|--?>>?)\s*(?P<right>[^\s:]+)\s*:\s*(?P<label>.*?)\s*$")
NOTE = re.compile(r"^\s*Note\s+(?P<where>over|right of|left of)\s+(?P<who>[^:]+?)\s*:\s*(?P<label>.*?)\s*$")


# ---------------------------------------------------------------- measuring

def text_width(text: Any) -> int:
    """Columns the text occupies, counting a full-width character as two and honouring <br/>."""
    widest = 0
    for line in BREAK.split(str(text or "")):
        widest = max(widest, sum(2 if WIDE.match(ch) else 1 for ch in line))
    return widest


def split_node(token: str) -> tuple[str, str, str, str] | None:
    """`C_x["name"]` -> (id, '[', 'name', ']'); None when the token is a bare id or something else."""
    token = token.strip()
    for opener, closer in SHAPES:
        cut = token.find(opener)
        if cut > 0 and token.endswith(closer):
            node_id = token[:cut].strip()
            label = token[cut + len(opener):len(token) - len(closer)]
            if node_id and re.fullmatch(r"[A-Za-z0-9_.\-]+", node_id):
                return node_id, opener, label, closer
    return None


def unquote(label: str) -> tuple[str, bool]:
    label = label.strip()
    if len(label) >= 2 and label[0] == label[-1] == '"':
        return label[1:-1], True
    return label, False


# ---------------------------------------------------------------- parsing

class Diagram:
    """One diagram, understood as far as it needs to be and passed through where it is not."""

    def __init__(self) -> None:
        self.kind: str | None = None
        self.direction = "TD"
        self.header_indent = ""
        self.before: list[str] = []      # lines before the header (a ```mermaid fence, a comment)
        self.after: list[str] = []       # lines after the body (the closing fence)
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.items: list[dict] = []      # the body, in the order it was written
        self.actors: list[dict] = []
        self.unhandled: list[str] = []

    # -- flowchart pieces ------------------------------------------------

    def node(self, token: str, indent: str) -> tuple[str, bool]:
        """Register a node written as `id[label]`; return its id and whether it carried a declaration."""
        parsed = split_node(token)
        if parsed is None:
            return token.strip(), False
        node_id, opener, raw_label, closer = parsed
        label, quoted = unquote(raw_label)
        self.nodes.setdefault(node_id, {"opener": opener, "closer": closer, "label": label,
                                        "quoted": quoted, "indent": indent, "group": None})
        return node_id, True

    def edge(self, left: str, right: str, label: str, arrow: str, form: str, indent: str) -> dict:
        quoted = False
        if label:
            label, quoted = unquote(label)
        left_id, left_inline = self.node(left, indent)
        right_id, right_inline = self.node(right, indent)
        record = {"from": left_id, "to": right_id, "label": label, "quoted": quoted, "arrow": arrow,
                  "form": form, "indent": indent, "left_inline": left_inline, "right_inline": right_inline}
        self.edges.append(record)
        return record


def parse(text: str) -> Diagram:
    diagram = Diagram()
    lines = text.splitlines()
    stack: list[list[dict]] = [diagram.items]
    groups: list[dict] = []
    started = False
    for line in lines:
        if not started:
            header = HEADER.match(line)
            if header is None:
                diagram.before.append(line)
                continue
            diagram.kind = "sequence" if header.group("kind") == "sequenceDiagram" else "flowchart"
            diagram.header_indent = line[:len(line) - len(line.lstrip())]
            if header.group("dir") in FLOW_DIRECTIONS:
                diagram.direction = header.group("dir")
            started = True
            continue
        if line.strip().startswith("```"):
            diagram.after.append(line)
            continue
        if diagram.kind == "sequence":
            parse_sequence_line(diagram, line)
            continue
        parse_flow_line(diagram, line, stack, groups)
    if not started:
        diagram.before = lines
    return diagram


def parse_flow_line(diagram: Diagram, line: str, stack: list[list[dict]], groups: list[dict]) -> None:
    indent = line[:len(line) - len(line.lstrip())]
    body = line.strip()
    if not body or body.startswith("%%"):
        stack[-1].append({"type": "raw", "line": line})
        return
    opened = SUBGRAPH.match(line)
    if opened:
        group = {"type": "group", "raw": opened.group("rest"), "indent": indent, "items": [],
                 "depth": len(stack) - 1, "members": set()}
        groups.append(group)
        stack[-1].append(group)
        stack.append(group["items"])
        return
    if END.match(line) and len(stack) > 1:
        stack.pop()
        return
    for form, pattern in (("pipe", PIPE_EDGE), ("mid", MID_EDGE), ("plain", PLAIN_EDGE)):
        found = pattern.match(line)
        if found is None:
            continue
        label = found.groupdict().get("label") or ""
        record = diagram.edge(found.group("left"), found.group("right"), label, found.group("arrow"), form, indent)
        stack[-1].append({"type": "edge", "edge": record})
        remember(diagram, groups, stack, record["from"])
        remember(diagram, groups, stack, record["to"])
        return
    if split_node(body) is not None:
        node_id, _ = diagram.node(body, indent)
        stack[-1].append({"type": "node", "id": node_id})
        remember(diagram, groups, stack, node_id)
        return
    if re.fullmatch(r"[A-Za-z0-9_.\-]+", body):
        diagram.nodes.setdefault(body, {"opener": "[", "closer": "]", "label": body,
                                        "quoted": False, "indent": indent, "group": None})
        stack[-1].append({"type": "node", "id": body})
        remember(diagram, groups, stack, body)
        return
    diagram.unhandled.append(body)
    stack[-1].append({"type": "raw", "line": line})


def remember(diagram: Diagram, groups: list[dict], stack: list[list[dict]], node_id: str) -> None:
    """A node belongs to the innermost subgraph it was first written in."""
    if len(stack) <= 1 or node_id not in diagram.nodes:
        return
    for group in reversed(groups):
        if group["items"] is stack[-1]:
            group["members"].add(node_id)
            if diagram.nodes[node_id]["group"] is None:
                diagram.nodes[node_id]["group"] = id(group)
            return


def parse_sequence_line(diagram: Diagram, line: str) -> None:
    body = line.strip()
    if not body or body.startswith("%%"):
        diagram.items.append({"type": "raw", "line": line})
        return
    indent = line[:len(line) - len(line.lstrip())]
    found = PARTICIPANT.match(line)
    if found:
        actor = {"id": found.group("id"), "label": found.group("label") or found.group("id"),
                 "kw": found.group("kw"), "indent": indent}
        diagram.actors.append(actor)
        diagram.items.append({"type": "actor", "actor": actor})
        return
    found = NOTE.match(line)
    if found:
        note = {"where": found.group("where"), "who": found.group("who").strip(),
                "label": found.group("label"), "indent": indent}
        diagram.items.append({"type": "note", "note": note})
        return
    found = MESSAGE.match(line)
    if found:
        message = {"from": found.group("left"), "to": found.group("right"), "arrow": found.group("arrow"),
                   "label": found.group("label"), "indent": indent}
        diagram.items.append({"type": "message", "message": message})
        return
    diagram.unhandled.append(body)
    diagram.items.append({"type": "raw", "line": line})


# ---------------------------------------------------------------- rendering

def node_token(diagram: Diagram, node_id: str) -> str:
    node = diagram.nodes.get(node_id)
    if node is None:
        return node_id
    label = f'"{node["label"]}"' if node["quoted"] else node["label"]
    return f'{node_id}{node["opener"]}{label}{node["closer"]}'


def edge_line(diagram: Diagram, edge: dict) -> str:
    left = node_token(diagram, edge["from"]) if edge["left_inline"] else edge["from"]
    right = node_token(diagram, edge["to"]) if edge["right_inline"] else edge["to"]
    if not edge["label"]:
        return f'{edge["indent"]}{left} {edge["arrow"]} {right}'
    label = f'"{edge["label"]}"' if edge["quoted"] else edge["label"]
    if edge["form"] == "pipe":
        return f'{edge["indent"]}{left} {edge["arrow"]}|{label}| {right}'
    opener = "==" if edge["arrow"].startswith("=") else "--"
    return f'{edge["indent"]}{left} {opener} {label} {edge["arrow"]} {right}'


def render_items(diagram: Diagram, items: list[dict]) -> list[str]:
    lines: list[str] = []
    for item in items:
        kind = item["type"]
        if kind == "raw":
            lines.append(item["line"])
        elif kind == "node":
            lines.append(f'{diagram.nodes[item["id"]]["indent"]}{node_token(diagram, item["id"])}')
        elif kind == "edge":
            lines.append(edge_line(diagram, item["edge"]))
        elif kind == "group":
            lines.append(f'{item["indent"]}subgraph {item["raw"]}')
            lines += render_items(diagram, item["items"])
            lines.append(f'{item["indent"]}end')
        elif kind == "actor":
            actor = item["actor"]
            lines.append(f'{actor["indent"]}{actor["kw"]} {actor["id"]} as {actor["label"]}')
        elif kind == "note":
            note = item["note"]
            lines.append(f'{note["indent"]}Note {note["where"]} {note["who"]}: {note["label"]}')
        elif kind == "message":
            message = item["message"]
            lines.append(f'{message["indent"]}{message["from"]}{message["arrow"]}{message["to"]}: {message["label"]}')
    return lines


def render(diagram: Diagram) -> str:
    lines = list(diagram.before)
    if diagram.kind == "flowchart":
        lines.append(f"{diagram.header_indent}flowchart {diagram.direction}")
    elif diagram.kind == "sequence":
        lines.append(f"{diagram.header_indent}sequenceDiagram")
    lines += render_items(diagram, diagram.items)
    lines += diagram.after
    return "\n".join(lines)


# ---------------------------------------------------------------- width

def layer(diagram: Diagram) -> dict[str, int]:
    """Longest-path ranks; an edge that would push a node past every other is a back edge and is dropped."""
    rank = {node_id: 0 for node_id in diagram.nodes}
    for _ in range(len(rank)):
        moved = False
        for edge in diagram.edges:
            tail, head = edge["from"], edge["to"]
            if tail in rank and head in rank and rank[head] < rank[tail] + 1:
                rank[head] = rank[tail] + 1
                moved = True
        if not moved:
            break
    return rank


def group_count(diagram: Diagram) -> int:
    return len({node["group"] for node in diagram.nodes.values() if node["group"] is not None})


def flow_width(diagram: Diagram, direction: str | None = None) -> int:
    direction = direction or diagram.direction
    if not diagram.nodes:
        return 0
    box = {node_id: text_width(node["label"]) + NODE_PAD for node_id, node in diagram.nodes.items()}
    rank = layer(diagram)
    by_rank: dict[int, list[str]] = {}
    for node_id, value in rank.items():
        by_rank.setdefault(value, []).append(node_id)
    if direction in VERTICAL:   # ranks stack downwards: width is the widest single rank
        widest = 0
        for members in by_rank.values():
            here = sum(box[m] for m in members) + NODE_GAP * (len(members) - 1)
            here += GROUP_PAD * len({diagram.nodes[m]["group"] for m in members if diagram.nodes[m]["group"]})
            widest = max(widest, here)
        return widest
    order = sorted(by_rank)      # ranks march sideways: width is every rank plus every gap
    total = 0
    for index, value in enumerate(order):
        total += max(box[m] for m in by_rank[value])
        if index + 1 < len(order):
            labels = [text_width(e["label"]) for e in diagram.edges if e["label"]
                      and rank.get(e["from"]) == value and rank.get(e["to"]) == order[index + 1]]
            total += max([RANK_GAP] + labels)
    return total + GROUP_PAD * group_count(diagram)


def sequence_width(diagram: Diagram) -> int:
    labels = {actor["id"]: actor["label"] for actor in diagram.actors}
    order = [actor["id"] for actor in diagram.actors]
    for item in diagram.items:   # a message may name an actor that was never declared
        if item["type"] == "message":
            for end in ("from", "to"):
                if item["message"][end] not in labels:
                    labels[item["message"][end]] = item["message"][end]
                    order.append(item["message"][end])
    if not order:
        return 0
    span = sum(text_width(labels[a]) + NODE_PAD for a in order) + ACTOR_GAP * (len(order) - 1)
    widest_message = max([text_width(i["message"]["label"]) + NODE_PAD
                          for i in diagram.items if i["type"] == "message"] or [0])
    side = max([text_width(i["note"]["label"]) + NODE_PAD for i in diagram.items
                if i["type"] == "note" and i["note"]["where"] != "over"] or [0])
    return max(span, widest_message) + side


def width_of(diagram: Diagram, direction: str | None = None) -> int:
    if diagram.kind == "sequence":
        return sequence_width(diagram)
    if diagram.kind == "flowchart":
        return flow_width(diagram, direction)
    return 0


def estimate_width(text: str) -> int:
    """Columns the diagram would occupy, as a relative measure of one layout against another."""
    return width_of(parse(text))


def fit_direction(body: str | list[str], prefer: str = "TD") -> str:
    """The narrower of TD and LR for a flowchart body — called while generating one, on the text itself."""
    text = body if isinstance(body, str) else "\n".join(body)
    widths = {name: estimate_width(f"flowchart {name}\n{text}") for name in ("TD", "LR")}
    if widths["TD"] == widths["LR"]:
        return prefer
    return min(widths, key=lambda name: widths[name])


# ---------------------------------------------------------------- rewriting

def wrap(text: str, limit: int) -> str:
    """Break a label by hand with <br/>; `wrap` in Mermaid decides for itself and cannot be relied on."""
    text = str(text or "")
    if BREAK.search(text) or text_width(text) <= limit:
        return text
    lines: list[str] = []
    current = ""
    for char in text:
        if current and text_width(current + char) > limit:
            head, current = break_at(current)
            lines.append(head)
        current += char
    if current:
        lines.append(current)
    return "<br/>".join(line.strip() for line in lines if line.strip())


def break_at(current: str) -> tuple[str, str]:
    """Break a full line: at its last space if it has one, else before a trailing run of letters
    or digits, so a word is never cut in half; a line that is one long word is cut as it stands."""
    cut = current.rfind(" ")
    if cut > 0:
        return current[:cut], current[cut + 1:]
    tail = re.search(r"[0-9A-Za-z]+$", current)
    if tail and tail.start() > 0:
        return current[:tail.start()], current[tail.start():]
    return current, ""


def notes_over(diagram: Diagram) -> int:
    """`Note right of` runs off the right of the last actor; `Note over` stays inside the diagram."""
    changed = 0
    for item in diagram.items:
        if item["type"] == "note" and item["note"]["where"] != "over":
            item["note"]["where"] = "over"
            changed += 1
    return changed


def wrap_names(diagram: Diagram, limit: int = MAX_NODE) -> int:
    changed = 0
    for node in diagram.nodes.values():
        folded = wrap(node["label"], limit)
        if folded != node["label"]:
            node["label"] = folded
            node["quoted"] = True
            changed += 1
    for actor in diagram.actors:
        folded = wrap(actor["label"], limit)
        if folded != actor["label"]:
            actor["label"] = folded
            changed += 1
    return changed


def wrap_labels(diagram: Diagram, limit: int = MAX_LABEL) -> int:
    changed = 0
    for edge in diagram.edges:
        folded = wrap(edge["label"], limit)
        if folded != edge["label"]:
            edge["label"] = folded
            edge["quoted"] = True
            changed += 1
    return changed


def strip_redundant_labels(diagram: Diagram) -> int:
    """An edge whose label only repeats what an endpoint already says costs width and adds nothing."""
    changed = 0
    for edge in diagram.edges:
        label = BREAK.sub("", edge["label"]).strip()
        if not label:
            continue
        ends = [BREAK.sub("", diagram.nodes.get(end, {}).get("label", "")).strip()
                for end in (edge["from"], edge["to"])]
        if any(end and (label in end or end in label) for end in ends):
            edge["label"] = ""
            changed += 1
    return changed


def group_members(group: dict) -> set[str]:
    members = set(group["members"])
    for item in group["items"]:
        if item["type"] == "group":
            members |= group_members(item)
    return members


def flatten_crossing_groups(diagram: Diagram) -> int:
    """Mermaid ignores a subgraph's own `direction` as soon as an edge crosses its border, and the
    frame still costs a rank. Such a subgraph buys nothing, so it is drawn as a node instead: the
    frame becomes a box and containment becomes a dotted link, so nothing is lost."""
    dissolved = 0

    def walk(items: list[dict]) -> list[dict]:
        nonlocal dissolved
        out: list[dict] = []
        for item in items:
            if item["type"] != "group":
                out.append(item)
                continue
            item["items"] = walk(item["items"])
            members = group_members(item)
            if not any((edge["from"] in members) != (edge["to"] in members) for edge in diagram.edges):
                out.append(item)
                continue
            dissolved += 1
            out += dissolve(diagram, item)
        return out

    diagram.items = walk(diagram.items)
    return dissolved


def dissolve(diagram: Diagram, group: dict) -> list[dict]:
    """The frame's own box, then what it held, then a dotted link per child that had no link already."""
    parsed = split_node(group["raw"])
    group_id = parsed[0] if parsed else group["raw"].strip()
    opener, closer = (parsed[1], parsed[3]) if parsed else ("[", "]")
    label, quoted = unquote(parsed[2]) if parsed else (group_id, False)
    diagram.nodes.setdefault(group_id, {"opener": opener, "closer": closer, "label": label,
                                        "quoted": quoted, "indent": group["indent"], "group": None})
    out: list[dict] = [{"type": "node", "id": group_id}]
    children = list(group["members"])
    for inner in group["items"]:
        if inner["type"] == "group":
            nested = split_node(inner["raw"])
            children.append(nested[0] if nested else inner["raw"].strip())
        if inner["type"] == "raw" and inner["line"].startswith(group["indent"] + "    "):
            inner["line"] = group["indent"] + inner["line"][len(group["indent"]) + 4:]
        out.append(inner)
    linked = {(e["from"], e["to"]) for e in diagram.edges} | {(e["to"], e["from"]) for e in diagram.edges}
    for child in sorted(children):
        if child in diagram.nodes:
            indent = diagram.nodes[child]["indent"]
            diagram.nodes[child]["indent"] = indent[:-4] if len(indent) >= 4 else indent
            if diagram.nodes[child]["group"] == id(group):
                diagram.nodes[child]["group"] = None
        if (group_id, child) in linked:
            continue
        edge = {"from": group_id, "to": child, "label": "", "quoted": False, "arrow": "-.-",
                "form": "plain", "indent": group["indent"], "left_inline": False, "right_inline": False}
        diagram.edges.append(edge)
        out.append({"type": "edge", "edge": edge})
    return out


def flip(diagram: Diagram) -> bool:
    if diagram.kind != "flowchart":
        return False
    prefer = diagram.direction if diagram.direction in VERTICAL else "LR"
    chosen = "TD" if flow_width(diagram, "TD") < flow_width(diagram, "LR") else (
        "LR" if flow_width(diagram, "LR") < flow_width(diagram, "TD") else prefer)
    if chosen != diagram.direction and not (chosen in VERTICAL and diagram.direction in VERTICAL):
        diagram.direction = chosen
        return True
    return False


def fit(text: str, budget: int = DEFAULT_BUDGET) -> tuple[str, dict]:
    """Normalise one diagram: always-safe rules first, then a ladder run only as far as the budget needs."""
    diagram = parse(text)
    if diagram.kind is None:
        return text, {"kind": None, "before": 0, "after": 0, "actions": [], "unhandled": []}
    report: dict[str, Any] = {"kind": diagram.kind, "before": width_of(diagram), "actions": [],
                              "unhandled": list(diagram.unhandled), "budget": budget}
    started_as = diagram.direction
    moved = notes_over(diagram)
    if moved:
        report["actions"].append(f"Note right of / left of → Note over ×{moved}")
    flip(diagram)
    ladder = [("节点名折行", lambda: wrap_names(diagram)),
              ("边标签折行", lambda: wrap_labels(diagram)),
              ("剥离与端点重复的边标签", lambda: strip_redundant_labels(diagram)),
              ("展平有跨界边的 subgraph", lambda: flatten_crossing_groups(diagram))]
    for name, rule in ladder:
        if width_of(diagram) <= budget:
            break
        count = rule()
        if count:
            report["actions"].append(f"{name} ×{count}")
            flip(diagram)
    if diagram.direction != started_as:
        report["actions"].insert(0, f"方向 {started_as} → {diagram.direction}")
    report["after"] = width_of(diagram)
    return render(diagram), report


FENCE = re.compile(r"^(?P<indent>\s*)```\s*mermaid\s*$", re.IGNORECASE)


def fit_document(text: str, budget: int = DEFAULT_BUDGET) -> tuple[str, list[dict]]:
    """Every ```mermaid block in a note; a bare diagram with no fence is treated as the whole text."""
    lines = text.splitlines()
    if not any(FENCE.match(line) for line in lines):
        fitted, report = fit(text, budget)
        return fitted, [report] if report["kind"] else []
    out: list[str] = []
    reports: list[dict] = []
    index = 0
    while index < len(lines):
        if FENCE.match(lines[index]):
            close = index + 1
            while close < len(lines) and not lines[close].strip().startswith("```"):
                close += 1
            fitted, report = fit("\n".join(lines[index + 1:close]), budget)
            out.append(lines[index])
            out += fitted.splitlines()
            if close < len(lines):
                out.append(lines[close])
            reports.append(report)
            index = close + 1
            continue
        out.append(lines[index])
        index += 1
    return "\n".join(out) + ("\n" if text.endswith("\n") else ""), reports


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="a file holding the diagram or the note around it; - reads stdin")
    parser.add_argument("--width", type=int, default=DEFAULT_BUDGET, help=f"budget in columns (default {DEFAULT_BUDGET})")
    parser.add_argument("--report", action="store_true", help="print what changed, and the width before and after, to stderr")
    parser.add_argument("--in-place", action="store_true", help="write the result back to the file")
    args = parser.parse_args()
    try:
        text = sys.stdin.read() if args.source == "-" else Path(args.source).read_text(encoding="utf-8")
    except OSError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    fitted, reports = fit_document(text, args.width)
    if args.in_place and args.source != "-":
        Path(args.source).write_text(fitted, encoding="utf-8")
    else:
        sys.stdout.write(fitted if fitted.endswith("\n") else fitted + "\n")
    if args.report:
        for number, report in enumerate(reports, start=1):
            print(f"[{number}] {report['kind']}: {report['before']} → {report['after']} 列（预算 {report['budget']}）", file=sys.stderr)
            for action in report["actions"]:
                print(f"    {action}", file=sys.stderr)
            for line in report["unhandled"]:
                print(f"    原样保留（本工具不认识）: {line}", file=sys.stderr)
            if report["after"] > report["budget"]:
                print("    仍然超预算：拆成两张图，或把下钻部分另写一篇用 wikilink 串起来", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
