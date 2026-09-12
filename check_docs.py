#!/usr/bin/env python3
"""Documentation checks for this repository. Run from the repository root; CI runs it on every push.

1. Every relative markdown link resolves (plugin/examples, plugin/evals/materials and course workspaces excluded).
2. Vocabulary follows docs/glossary.md: the manual (README.zh-CN.md, docs/guide.md) never uses the design-side
   English terms as words; no document uses the retired coinages; the manual also avoids 宿主 / 学习者 / 小节.
   Text inside fenced blocks and inline code is not checked.
3. Length limits from docs/glossary.md §3 hold.

Exit status 1 on any finding, with one line per finding.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LINK_SKIP = ("plugin/examples/", "plugin/evals/materials/", "whetstone/")

MANUAL = ["README.zh-CN.md", "docs/guide.md"]
PLAIN_ALL = MANUAL + ["README.md", "CHANGELOG.md", "docs/design.md", "docs/evidence.md", "docs/specs/*.md"]

# design-side terms the manual must not use as words (docs/glossary.md §1)
DESIGN_TERMS = re.compile(r"\b(MRG|LRG|SEL|core|supporting|listed|full|fast|material|domain|fact|mechanism|rationale|principle)\b")
# retired coinages nobody uses any more (docs/glossary.md §2)
RETIRED = ["去主体化", "到达层", "覆盖账本", "接缝问题", "单向诊断", "提示渐隐", "证据等级链", "不透明原则", "结构先于规则",
           "规范性基线", "教学包", "课程包", "学习包", "概念注册表", "学习者状态", "前置诊断", "统一管", "弹权限", "随你"]
MANUAL_ONLY_RETIRED = ["宿主", "学习者", "小节"]
LIMITS = {"README.zh-CN.md": 120, "README.md": 120, "docs/guide.md": 350, "docs/design.md": 250}
SPEC_LIMIT = 200

FENCE = re.compile(r"^(`{3,}|~{3,}).*?^\1[ \t]*$", re.DOTALL | re.MULTILINE)
INLINE_CODE = re.compile(r"`[^`\n]*`")
LINK = re.compile(r"\]\(([^)\s#]+)(?:#[^)]*)?\)")


def strip_code(text: str) -> str:
    return INLINE_CODE.sub("", FENCE.sub("", text))


def expand(patterns: list[str]) -> list[Path]:
    files: list[Path] = []
    for pattern in patterns:
        files.extend(sorted(ROOT.glob(pattern)))
    return files


def check_links() -> list[str]:
    findings = []
    for md in ROOT.rglob("*.md"):
        rel = md.relative_to(ROOT).as_posix()
        if rel.startswith(LINK_SKIP) or "/.git/" in md.as_posix():
            continue
        for target in LINK.findall(md.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (md.parent / target).exists():
                findings.append(f"{rel}: link target missing: {target}")
    return findings


def check_terms() -> list[str]:
    findings = []
    for md in expand(PLAIN_ALL):
        rel = md.relative_to(ROOT).as_posix()
        text = strip_code(md.read_text(encoding="utf-8"))
        for word in RETIRED:
            if word in text:
                findings.append(f"{rel}: retired term '{word}' (docs/glossary.md §2)")
        if rel in MANUAL:
            for word in MANUAL_ONLY_RETIRED:
                if word in text:
                    findings.append(f"{rel}: '{word}' is not manual vocabulary (docs/glossary.md §2)")
            for match in DESIGN_TERMS.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{rel}: design term '{match.group(1)}' outside code (near stripped line {line}; docs/glossary.md §1)")
    return findings


def check_lengths() -> list[str]:
    findings = []
    for rel, limit in LIMITS.items():
        path = ROOT / rel
        if path.is_file():
            lines = len(path.read_text(encoding="utf-8").splitlines())
            if lines > limit:
                findings.append(f"{rel}: {lines} lines > {limit} (docs/glossary.md §3)")
    for path in sorted((ROOT / "docs" / "specs").glob("*.md")):
        lines = len(path.read_text(encoding="utf-8").splitlines())
        if lines > SPEC_LIMIT:
            findings.append(f"{path.relative_to(ROOT).as_posix()}: {lines} lines > {SPEC_LIMIT} (docs/glossary.md §3)")
    return findings


def main() -> int:
    findings = check_links() + check_terms() + check_lengths()
    for line in findings:
        print(line)
    print("docs: no findings" if not findings else f"docs: {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
