#!/usr/bin/env python3
"""Keep outline.md's status in step with learning-progress.json.

  outline_status.py --course <course dir> [--store <store>]

Rewrites the status cell of the problem-chain table (rows `| n | … | … | status |`, n = the n-th
section of the plan) and the block between `<!-- whetstone:status -->` markers: progress, one
line per section (status, attempts, latest verdict, deepest layer), the chain-rebuild ratio when
a store is given, and the sections still to review. The block is appended on first use. Text
after the closing marker — the closing summary the model writes — is never touched.

learning_state.py and lrg_record.py call this after every write to the progress file, so the
outline is current without anyone remembering to update it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

START, END = "<!-- whetstone:status -->", "<!-- /whetstone:status -->"
ROW = re.compile(r"^\|\s*(\d+)\s*\|(.*)\|\s*[^|]*\|\s*$")
STATUS_TEXT = {"pending": "待学", "in_progress": "学习中", "completed": "已完成", "deferred": "本次略过"}
DEPTH_TEXT = {"fact": "事实", "mechanism": "机制", "rationale": "本质", "principle": "思想"}
VERDICT_TEXT = {"mastered": "通过", "partial": "部分", "retry": "重答", "skipped": "跳过"}
DEPTH_ORDER = {"fact": 0, "mechanism": 1, "rationale": 2, "principle": 3}


def load_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} root must be an object")
    return data


def section_view(section: dict, progress_section: dict | None) -> dict:
    attempts = (progress_section or {}).get("attempts") or []
    latest = attempts[-1] if attempts else None
    depths = [a.get("depth_reached") for a in attempts if a.get("depth_reached") in DEPTH_ORDER]
    deepest = max(depths, key=lambda d: DEPTH_ORDER[d]) if depths else None
    status = (progress_section or {}).get("status") or "pending"
    text = STATUS_TEXT.get(status, status)
    if (progress_section or {}).get("blocked_by") and status != "completed":
        text = f"等前置课 {progress_section['blocked_by']}"
    elif status == "completed" and latest:
        text = f"已完成（{(latest.get('at') or '')[:10]}）"
    elif status == "in_progress":
        text = f"学习中（{len(attempts)} 次作答）"
    return {"id": section.get("id"), "title": section.get("title") or "", "status": status, "text": text,
            "attempts": len(attempts), "verdict": VERDICT_TEXT.get((latest or {}).get("verdict"), "—"),
            "depth": DEPTH_TEXT.get(deepest, "—"), "regressed": status == "in_progress" and any(a.get("kind") == "review" for a in attempts)}


def render_block(plan: dict, progress: dict, chain: dict | None) -> str:
    by_id = {s.get("id"): s for s in progress.get("sections", []) if isinstance(s, dict)}
    views = [section_view(s, by_id.get(s.get("id"))) for s in plan.get("sections", []) if isinstance(s, dict)]
    done = sum(1 for v in views if v["status"] == "completed")
    deferred = sum(1 for v in views if v["status"] == "deferred")
    active = sum(1 for v in views if v["status"] == "in_progress")
    completed_at = next((e.get("at") for e in reversed(progress.get("events") or []) if e.get("type") == "lesson_completed"), None)
    course_state = f"已结课（{completed_at[:10]}）" if progress.get("status") == "completed" and completed_at else ("已结课" if progress.get("status") == "completed" else "进行中")
    lines = [START, "", "## 学习情况", "",
             f"- 进度：{done}/{len(views)} 节完成" + (f"，{deferred} 节略过" if deferred else "") + (f"，{active} 节学习中" if active else "")
             + f"；课程{course_state}；更新于 {(progress.get('updated_at') or '')[:10]}"]
    if chain:
        lines.append(f"- 链重建：{chain.get('matched')}/{chain.get('reference_edges')} 条关系对上（{(chain.get('at') or '')[:10]}）"
                     + (f"，漏掉 {len(chain.get('missing') or [])} 条、反向 {len(chain.get('direction_reversed') or [])} 条" if chain.get("reference_edges") else ""))
    to_review = [v for v in views if v["status"] == "in_progress" or (v["status"] == "completed" and v["verdict"] not in ("通过", "跳过"))]
    lines.append("- 仍待复习：" + ("、".join(f"{v['id']} {v['title']}" for v in to_review) if to_review else "无"))
    lines += ["", "| 节 | 状态 | 作答 | 最近判定 | 到达的层 |", "|---|---|---|---|---|"]
    for v in views:
        lines.append(f"| {v['id']} {v['title']} | {v['text']} | {v['attempts']} | {v['verdict']} | {v['depth']} |")
    lines += ["", "结课总结写在下面这行标记之后（已解释成功 / 提示后成功 / 仍待复习 / 材料不确定）。", "", END]
    return "\n".join(lines)


def update_rows(outline: str, plan: dict, progress: dict) -> str:
    by_id = {s.get("id"): s for s in progress.get("sections", []) if isinstance(s, dict)}
    sections = [s for s in plan.get("sections", []) if isinstance(s, dict)]
    out = []
    for line in outline.splitlines():
        match = ROW.match(line)
        if match and 1 <= int(match.group(1)) <= len(sections):
            view = section_view(sections[int(match.group(1)) - 1], by_id.get(sections[int(match.group(1)) - 1].get("id")))
            cells = line.rstrip().rstrip("|").split("|")
            cells[-1] = f" {view['text']} "
            line = "|".join(cells) + "|"
        out.append(line)
    return "\n".join(out) + ("\n" if outline.endswith("\n") else "")


def refresh(course: Path, store: Path | None = None) -> dict:
    outline_path, plan_path, progress_path = course / "outline.md", course / "lesson-plan.json", course / "learning-progress.json"
    if not outline_path.is_file() or not plan_path.is_file() or not progress_path.is_file():
        return {"updated": False, "reason": "outline.md, lesson-plan.json and learning-progress.json are all needed"}
    plan, progress = load_json(plan_path), load_json(progress_path)
    chain = None
    if store is not None:
        state_path = store / "learner-state.json"
        if state_path.is_file():
            chain = ((load_json(state_path).get("lessons") or {}).get(plan.get("lesson_id")) or {}).get("chain_rebuild")
    text = update_rows(outline_path.read_text(encoding="utf-8"), plan, progress)
    block = render_block(plan, progress, chain)
    if START in text and END in text:
        text = text[: text.index(START)] + block + text[text.index(END) + len(END):]
    else:
        text = text.rstrip("\n") + "\n\n" + block + "\n"
    outline_path.write_text(text, encoding="utf-8")
    return {"updated": True, "outline": str(outline_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--course", type=Path, required=True, help="Course directory (outline.md, lesson-plan.json, learning-progress.json)")
    parser.add_argument("--store", type=Path, help="Knowledge store, to include the chain-rebuild ratio")
    args = parser.parse_args()
    try:
        result = refresh(args.course, args.store)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: {result['outline']} status refreshed" if result["updated"] else f"skipped: {result['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
