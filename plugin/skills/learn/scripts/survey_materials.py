#!/usr/bin/env python3
"""Survey a directory of candidate learning materials without reading their substance.

Produces an inventory the guide skill turns into advice: which entries are git
repositories (size, languages, README/docs), which are documents (headings, size, date),
which look like AI-generated intermediates or conversation records (signals, not verdicts),
and which are data/logs/binaries to ignore. Reads at most the first 4 KB of each text
document for signals; never copies content into the output.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


IGNORED_DIRS = {".git", ".hg", ".svn", "node_modules", "target", "build", "dist", "out", "__pycache__",
                ".venv", "venv", ".idea", ".vscode", ".obsidian", "bazel-bin", "bazel-out", "coverage"}
DOC_EXT = {".md", ".markdown", ".adoc", ".asciidoc", ".rst", ".txt", ".tex", ".pdf", ".docx", ".epub"}
CODE_EXT = {".c", ".cc", ".cpp", ".h", ".hpp", ".rs", ".go", ".py", ".java", ".kt", ".js", ".ts", ".tsx",
            ".jsx", ".rb", ".php", ".swift", ".sh", ".bazel", ".bzl", ".cmake", ".mk", ".s", ".asm"}
DATA_EXT = {".json", ".jsonl", ".csv", ".tsv", ".yaml", ".yml", ".toml", ".ini", ".xml", ".sql", ".db", ".sqlite"}
LOG_EXT = {".log", ".out", ".err", ".trace"}
BINARY_EXT = {".rpm", ".deb", ".so", ".a", ".o", ".bin", ".img", ".iso", ".tar", ".gz", ".zip", ".7z", ".jar",
              ".class", ".pyc", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".mp4", ".wav", ".pdfa"}
SENSITIVE = {".env", ".pem", ".key", ".p12", ".pfx", "id_rsa", "credentials"}

GENERATED_SIGNALS = [
    (re.compile(r"this session is being continued|summary below covers|primary request and intent", re.I), "session_summary", 3),
    (re.compile(r"^\s*>\s*(状态|日期|范围|评估范围|适用对象|文档性质)[:：]", re.M), "status_frontmatter", 2),
    (re.compile(r"(会话|对话)(记录|总结)|conversation[_ ]record|transcript", re.I), "conversation_record", 3),
    (re.compile(r"handoff|交接|进展汇报|阶段进度|实施记录|验证记录|简报|evaluation report", re.I), "work_log", 2),
    (re.compile(r"claude|chatgpt|gpt-|copilot|assistant", re.I), "ai_mention", 1),
    (re.compile(r"\d{4}[-_]\d{2}[-_]\d{2}"), "dated_filename_or_body", 1),
    (re.compile(r"^#{1,2}\s*\d+(\.\d+)*[\s.、]", re.M), "numbered_sections", 0),
]
PRIMARY_SIGNALS = [
    (re.compile(r"\bRFC\b|specification|规范|standard|IEEE|ISO/IEC", re.I), "spec_like"),
    (re.compile(r"^(#|=)\s*(abstract|introduction|references|bibliography)", re.I | re.M), "paper_like"),
    (re.compile(r"chapter|第[一二三四五六七八九十\d]+章|exercise|习题", re.I), "textbook_like"),
]
ENTRY_BASENAMES = {"main.c", "main.cc", "main.cpp", "main.rs", "main.go", "main.py", "app.py", "lib.rs",
                   "server.py", "server.rs", "server.go", "Main.java", "index.ts", "index.js", "mod.rs"}
ENTRY_SKIP_PARTS = {"demo", "demos", "example", "examples", "test", "tests", "benchmark", "benchmarks", "sample",
                    "samples", "javadoc", ".github", "third_party", "vendor", "deployment", "patched_file"}


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def walk(root: Path, max_files: int):
    count = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS and not d.startswith(".DS"))
        for name in filenames:
            if name == ".DS_Store":
                continue
            count += 1
            if count > max_files:
                return
            yield Path(dirpath) / name


def doc_profile(path: Path) -> dict:
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:4096]
    except OSError:
        head = ""
    signals: list[str] = []
    score = 0
    for pattern, label, weight in GENERATED_SIGNALS:
        if pattern.search(head) or pattern.search(path.name):
            signals.append(label)
            score += weight
    primary = [label for pattern, label in PRIMARY_SIGNALS if pattern.search(head)]
    headings = re.findall(r"^(?:#{1,3}|={1,3})\s+(.+?)\s*$", head, re.M)[:6]
    return {
        "headings": headings,
        "generated_signals": signals,
        "generated_score": score,
        "primary_signals": primary,
        "likely": "generated_intermediate" if score >= 3 else ("primary_or_authored" if primary and score < 2 else "unclear"),
    }


def survey_dir(path: Path, max_files: int) -> dict:
    files = list(walk(path, max_files))
    exts = Counter(p.suffix.lower() for p in files)
    size = 0
    docs: list[Path] = []
    entry_hints: list[str] = []
    for p in files:
        try:
            size += p.stat().st_size
        except OSError:
            continue
        if p.suffix.lower() in DOC_EXT and p.suffix.lower() not in {".pdf", ".docx", ".epub"}:
            docs.append(p)
        rel = p.relative_to(path)
        if (p.name in ENTRY_BASENAMES and not any(part.lower() in ENTRY_SKIP_PARTS for part in rel.parts)
                and len(entry_hints) < 8):
            entry_hints.append(rel.as_posix())
    code = sum(n for e, n in exts.items() if e in CODE_EXT)
    top_langs = [f"{e.lstrip('.')}:{n}" for e, n in exts.most_common() if e in CODE_EXT][:4]
    readme = next((p.relative_to(path).as_posix() for p in files if p.name.lower().startswith("readme")), None)
    doc_dirs = sorted({p.relative_to(path).parts[0] for p in docs if len(p.relative_to(path).parts) > 1
                       and p.relative_to(path).parts[0].lower() in {"docs", "doc", "documentation", "design", "spec", "specs", "wiki"}})
    return {
        "files": len(files), "truncated": len(files) >= max_files, "size": size, "size_human": human(size),
        "code_files": code, "doc_files": len(docs), "top_languages": top_langs, "readme": readme,
        "doc_dirs": doc_dirs, "entry_hints": entry_hints,
        "data_or_log_files": sum(n for e, n in exts.items() if e in DATA_EXT | LOG_EXT),
        "binary_files": sum(n for e, n in exts.items() if e in BINARY_EXT),
    }


def classify_entry(path: Path, max_files: int) -> dict:
    name = path.name
    entry: dict = {"name": name, "path": str(path)}
    if path.is_dir():
        is_repo = (path / ".git").exists()
        profile = survey_dir(path, max_files)
        entry.update(profile)
        if is_repo:
            entry["kind"] = "git_repo"
        elif profile["doc_files"] and profile["code_files"] == 0 and profile["data_or_log_files"] <= profile["doc_files"]:
            entry["kind"] = "document_folder"
            entry["documents"] = [classify_entry(p, max_files) for p in sorted(path.rglob("*"))
                                  if p.is_file() and p.suffix.lower() in DOC_EXT and not any(part in IGNORED_DIRS for part in p.parts)][:60]
        elif profile["code_files"] and profile["doc_files"] == 0 and profile["binary_files"] > profile["code_files"]:
            entry["kind"] = "release_tree"
        elif profile["code_files"]:
            entry["kind"] = "code_tree"
        elif profile["data_or_log_files"] or profile["binary_files"]:
            entry["kind"] = "data_or_logs"
        else:
            entry["kind"] = "other_folder"
        return entry
    suffix = path.suffix.lower()
    try:
        stat = path.stat()
        entry["size"] = stat.st_size
        entry["size_human"] = human(stat.st_size)
        entry["modified"] = datetime.fromtimestamp(stat.st_mtime, timezone.utc).date().isoformat()
    except OSError:
        pass
    if name.lower() in SENSITIVE or suffix in SENSITIVE:
        entry["kind"] = "sensitive_skipped"
    elif suffix in DOC_EXT:
        entry["kind"] = "document"
        if suffix in {".pdf", ".docx", ".epub"}:
            entry["note"] = "binary document; needs conversion before it can be a source"
        else:
            entry.update(doc_profile(path))
    elif suffix in LOG_EXT:
        entry["kind"] = "log"
    elif suffix in DATA_EXT:
        entry["kind"] = "data"
    elif suffix in CODE_EXT:
        entry["kind"] = "code_file"
    elif suffix in BINARY_EXT:
        entry["kind"] = "binary"
    else:
        entry["kind"] = "other"
    return entry


def survey(root: Path, max_files: int) -> dict:
    entries = [classify_entry(p, max_files) for p in sorted(root.iterdir()) if p.name != ".DS_Store" and p.name not in IGNORED_DIRS]
    kinds = Counter(e["kind"] for e in entries)
    total = sum(e.get("size", 0) for e in entries)
    return {
        "schema_version": "1.0",
        "root": str(root),
        "surveyed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "summary": {"entries": len(entries), "kinds": dict(kinds), "total_size": total, "total_size_human": human(total)},
        "entries": entries,
    }


def render_markdown(result: dict) -> str:
    lines = [f"# 材料清单：{result['root']}", "",
             f"共 {result['summary']['entries']} 个顶层条目，{result['summary']['total_size_human']}；类型：" +
             ", ".join(f"{k} {v}" for k, v in result["summary"]["kinds"].items()), "",
             "| 条目 | 类型 | 规模 | 要点 |", "|---|---|---|---|"]
    for e in result["entries"]:
        kind = e["kind"]
        if kind == "git_repo" or kind in {"code_tree", "release_tree"}:
            note = f"{e['files']} 文件；{' '.join(e['top_languages']) or '无代码'}；README {'有' if e.get('readme') else '无'}；docs 目录 {', '.join(e['doc_dirs']) or '无'}"
            if e.get("entry_hints"):
                note += f"；入口线索 {', '.join(e['entry_hints'][:3])}"
        elif kind == "document_folder":
            gen = sum(1 for d in e.get("documents", []) if d.get("likely") == "generated_intermediate")
            note = f"{e['doc_files']} 份文档，其中 {gen} 份带生成文档信号"
        elif kind == "document":
            note = f"{e.get('modified', '')}；{e.get('likely', '')}；信号 {', '.join(e.get('generated_signals', [])) or '无'}；首标题 {e.get('headings', [''])[0] if e.get('headings') else '无'}"
        elif kind in {"data_or_logs", "log", "data", "binary"}:
            note = "不作为学习材料"
        else:
            note = e.get("note", "")
        lines.append(f"| `{e['name']}` | {kind} | {e.get('size_human', '')} | {note} |")
    lines.append("")
    docs_in_folders = [(e["name"], d) for e in result["entries"] if e["kind"] == "document_folder" for d in e.get("documents", [])]
    if docs_in_folders:
        lines += ["## 文档夹内明细", "", "| 文件 | 日期 | 大小 | 判断 | 信号 |", "|---|---|---|---|---|"]
        for folder, d in docs_in_folders:
            lines.append(f"| `{folder}/{Path(d['path']).name}` | {d.get('modified', '')} | {d.get('size_human', '')} | {d.get('likely', '')} | {', '.join(d.get('generated_signals', []))} |")
        lines.append("")
    lines.append("> `likely` 只是文件名与前 4 KB 的信号，不是结论；由向导结合学习者说明再定级。")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, help="Write JSON here")
    parser.add_argument("--markdown", type=Path, help="Write a Markdown table here")
    parser.add_argument("--max-files", type=int, default=20000, help="Per-directory walk cap")
    args = parser.parse_args()
    if not args.root.is_dir():
        print(f"ERROR: not a directory: {args.root}", file=sys.stderr)
        return 2
    result = survey(args.root.resolve(), args.max_files)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = render_markdown(result)
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(md, encoding="utf-8")
    if not args.output and not args.markdown:
        print(md, end="")
    else:
        print(f"OK: {result['summary']['entries']} entries, {result['summary']['total_size_human']}"
              + (f" → {args.output}" if args.output else "") + (f", {args.markdown}" if args.markdown else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
