#!/usr/bin/env python3
"""Build the three release artifacts into dist/:

  whetstone-<version>.plugin        the Claude Desktop / Cowork plugin (package_plugin.py)
  whetstone-skills-<version>.zip    the four skill directories side by side, with README and LICENSE
  whetstone-learn.zip               one standalone skill named `whetstone-learn` for hosts that take a
                                    single-skill zip: the learn skill with README and LICENSE, the
                                    sibling-skill references removed

    python3 package_release.py [--dist dist] [--check]

The version comes from plugin/.claude-plugin/plugin.json. --check builds into a temporary
directory and verifies the standalone skill (name matches the folder, no sibling-skill mention,
every relative link resolves); CI runs it.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PLUGIN = ROOT / "plugin"
SKILLS = PLUGIN / "skills"
STANDALONE = "whetstone-learn"
STANDALONE_DESCRIPTION = "把学习材料变成一条“问题 → 方案 → 新问题 → 下一方案”的可解释学习路径，再让学习者逐节用自己的话重建理解。最终产物应帮助学习者理解每个设计步骤为什么存在，而不只是记住术语。"
SKIP_DIRS = {"__pycache__", "learning-packs"}
SKIP_FILES = {".DS_Store", ".gitignore"}

# text that only makes sense next to the sibling skills: (regex, replacement)
SIBLING_EDITS: list[tuple[str, str]] = [
    (r"`guide` 与 `outline` 技能是这些阶段的独立入口，协议只在本技能维护。", ""),
    (r"`learn` 是总入口，\*\*缺什么补什么\*\*；`guide` 与 `outline` 是从某个阶段重入的壳。阶段协议只在这里维护一份。", "本技能是总入口，**缺什么补什么**。"),
    (r"（clarify 技能维护）", "（学习者自己维护）"),
    (r"交给 clarify 技能写入 `concepts/`", "由学习者自己写进 `concepts/`"),
    (r"由 clarify 技能维护（契约见该技能的 SKILL\.md）：[^。]*。本技能只需遵守：", "由学习者自己维护（完整版插件里有 clarify 技能按节生成）。本技能只需遵守："),
    (r"交给 clarify 技能生成概念笔记", "由学习者自己写进 `concepts/`"),
    (r"- 想展开某个 listed 概念，在任何文档里写 `\[\[概念名\]\]` 后调用 clarify。", "- 想展开某个 listed 概念，在该节主问题前选择细化。"),
    (r"- 概念疑问用 `\[\[wikilink\]\]` 标记，定期调用 clarify", "- 概念疑问在该节主问题前选择细化"),
]
NAME_EDITS: list[tuple[str, str]] = [
    ("/whetstone:learn", "/" + STANDALONE),
    ("/skill:learn", "/skill:" + STANDALONE),
    ("skills/learn", "skills/" + STANDALONE),
    ("$learn", "$" + STANDALONE),
]
FORBIDDEN = re.compile(r"clarify(?! 技能按节生成)|`guide` 与|/whetstone:learn|/skill:learn\b|\$learn\b")
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


def version() -> str:
    return json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]


def wanted(path: Path) -> bool:
    return path.is_file() and not any(p in SKIP_DIRS for p in path.parts) and path.name not in SKIP_FILES and path.suffix != ".pyc"


def copy_tree(src: Path, dst: Path) -> None:
    for path in sorted(src.rglob("*")):
        if wanted(path):
            target = dst / path.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def zip_dir(folder: Path, output: Path) -> int:
    count = 0
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                archive.write(path, (folder.name / path.relative_to(folder)).as_posix())
                count += 1
    return count


def build_standalone(dist: Path) -> Path:
    """The learn skill as one skill named whetstone-learn, with sibling-skill text removed."""
    folder = dist / STANDALONE
    if folder.exists():
        shutil.rmtree(folder)
    copy_tree(SKILLS / "learn", folder)
    for path in sorted(folder.rglob("*")):
        if path.suffix not in {".md", ".json", ".yaml"} or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern, new in SIBLING_EDITS:
            text = re.sub(pattern, new, text)
        for old, new in NAME_EDITS:
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")
    skill = folder / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    text = re.sub(r"^name: .*$", f"name: {STANDALONE}", text, count=1, flags=re.MULTILINE)
    text = re.sub(r"^description: .*$", f"description: {STANDALONE_DESCRIPTION}", text, count=1, flags=re.MULTILINE)
    skill.write_text(text, encoding="utf-8")
    (folder / "README.md").write_text((ROOT / "release" / "README.whetstone-learn.md").read_text(encoding="utf-8").replace("{{version}}", version()), encoding="utf-8")
    shutil.copy2(ROOT / "LICENSE", folder / "LICENSE")
    return folder


def check_standalone(folder: Path) -> list[str]:
    problems: list[str] = []
    head = (folder / "SKILL.md").read_text(encoding="utf-8")[:2000]
    if f"\nname: {folder.name}\n" not in head:
        problems.append(f"SKILL.md name must equal the folder name '{folder.name}'")
    for path in sorted(folder.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        for m in FORBIDDEN.finditer(text):
            problems.append(f"{path.relative_to(folder)}: sibling-skill text left: '{m.group(0)}'")
        for m in LINK.finditer(text):
            target = m.group(1)
            if target.startswith(("http", "<", "mailto:")):
                continue
            if not (path.parent / target).exists():
                problems.append(f"{path.relative_to(folder)}: broken link {target}")
    for name in ("LICENSE", "README.md", "SKILL.md"):
        if not (folder / name).is_file():
            problems.append(f"missing {name}")
    return problems


def build_skills_zip(dist: Path) -> Path:
    folder = dist / "whetstone-skills"
    if folder.exists():
        shutil.rmtree(folder)
    for skill in ("learn", "guide", "outline", "clarify"):
        copy_tree(SKILLS / skill, folder / skill)
    (folder / "README.md").write_text((ROOT / "release" / "README.whetstone-skills.md").read_text(encoding="utf-8").replace("{{version}}", version()), encoding="utf-8")
    shutil.copy2(ROOT / "LICENSE", folder / "LICENSE")
    output = dist / f"whetstone-skills-{version()}.zip"
    zip_dir(folder, output)
    return output


def build_plugin(dist: Path) -> Path:
    import importlib.util
    spec = importlib.util.spec_from_file_location("package_plugin", ROOT / "package_plugin.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    output = dist / f"whetstone-{version()}.plugin"
    module.package(output)
    return output


def build_all(dist: Path) -> list[Path]:
    dist.mkdir(parents=True, exist_ok=True)
    plugin = build_plugin(dist)
    skills = build_skills_zip(dist)
    folder = build_standalone(dist)
    problems = check_standalone(folder)
    if problems:
        raise ValueError("standalone skill:\n  " + "\n  ".join(problems))
    standalone = dist / f"{STANDALONE}.zip"
    zip_dir(folder, standalone)
    return [plugin, skills, standalone]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    parser.add_argument("--check", action="store_true", help="Build into a temporary directory and only report")
    args = parser.parse_args()
    try:
        if args.check:
            with tempfile.TemporaryDirectory() as temporary:
                outputs = build_all(Path(temporary))
                for path in outputs:
                    print(f"OK: {path.name} ({path.stat().st_size} bytes)")
        else:
            for path in build_all(args.dist):
                print(f"OK: {path} ({path.stat().st_size} bytes)")
    except (OSError, ValueError, KeyError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
