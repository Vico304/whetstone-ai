#!/usr/bin/env python3
"""Create a source inventory without copying source contents."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".next",
    ".venv",
    ".vinext",
    ".wrangler",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "vendor",
}

TEXT_EXTENSIONS = {
    ".adoc", ".c", ".cc", ".cfg", ".cpp", ".cs", ".css", ".csv",
    ".go", ".h", ".hpp", ".html", ".ini", ".java", ".js", ".json",
    ".jsx", ".kt", ".kts", ".lua", ".md", ".mdx", ".php", ".properties",
    ".py", ".rb", ".rs", ".rst", ".scss", ".sh", ".sql", ".swift",
    ".tex", ".toml", ".ts", ".tsx", ".txt", ".xml", ".yaml", ".yml",
}

DOCUMENT_EXTENSIONS = {".adoc", ".epub", ".md", ".mdx", ".pdf", ".rst", ".tex", ".txt"}
CODE_EXTENSIONS = {
    ".c", ".cc", ".cpp", ".cs", ".css", ".go", ".h", ".hpp", ".html",
    ".java", ".js", ".jsx", ".kt", ".kts", ".lua", ".php", ".py", ".rb",
    ".rs", ".scss", ".sh", ".sql", ".swift", ".ts", ".tsx",
}
DATA_EXTENSIONS = {".csv", ".ini", ".json", ".properties", ".toml", ".xml", ".yaml", ".yml"}
SENSITIVE_EXACT = {
    ".env", ".npmrc", ".pypirc", "authorized_keys", "credentials", "id_dsa",
    "id_ecdsa", "id_ed25519", "id_rsa", "known_hosts", "netrc",
}
SENSITIVE_SUFFIXES = {".der", ".key", ".p12", ".pfx", ".pem"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def is_sensitive(path: Path) -> bool:
    name = path.name.lower()
    return (
        name in SENSITIVE_EXACT
        or name.startswith(".env.")
        or path.suffix.lower() in SENSITIVE_SUFFIXES
        or name.endswith("credentials.json")
        or name.endswith("service-account.json")
    )


CONVERSATION_NAME_TOKENS = ("chat", "conversation", "session", "transcript")
CONVERSATION_DIRS = {"chats", "conversations", "sessions", "transcripts"}
CONVERSATION_EXTENSIONS = DOCUMENT_EXTENSIONS | {".json", ".jsonl", ".html", ".xml", ".yaml", ".yml"}
NAME_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def classify(path: Path) -> str:
    """Classify by extension first; only exported-looking files can be conversations.

    Source code is never a conversation record even when its name mentions
    sessions (``session.py``, ``session_store.go``). Name tokens are matched as
    whole words so ``sessions`` and ``chat-2026`` count but ``obsession`` does not.
    """
    suffix = path.suffix.lower()
    if suffix in CODE_EXTENSIONS and suffix != ".html":
        return "code"
    if suffix in CONVERSATION_EXTENSIONS:
        stem_tokens = set(NAME_TOKEN_SPLIT.split(path.stem.lower()))
        lowered_dirs = {part.lower() for part in path.parts[:-1]}
        name_hit = any(token in stem_tokens or f"{token}s" in stem_tokens for token in CONVERSATION_NAME_TOKENS)
        if name_hit or lowered_dirs.intersection(CONVERSATION_DIRS):
            return "conversation"
    if suffix in CODE_EXTENSIONS:
        return "code"
    if suffix in DOCUMENT_EXTENSIONS:
        return "document"
    if suffix in DATA_EXTENSIONS:
        return "data"
    return "binary_or_unknown"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def portable_path(path: Path, base: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(base.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def iter_files(inputs: Iterable[Path]) -> tuple[list[Path], list[dict[str, str]]]:
    files: list[Path] = []
    problems: list[dict[str, str]] = []
    for source in inputs:
        if not source.exists():
            problems.append({"path": str(source), "reason": "not_found"})
            continue
        if source.is_symlink():
            problems.append({"path": str(source), "reason": "symlink_skipped"})
            continue
        if source.is_file():
            files.append(source)
            continue
        for root, dirnames, filenames in os.walk(source, followlinks=False):
            dirnames[:] = sorted(name for name in dirnames if name not in IGNORED_DIRS)
            root_path = Path(root)
            for filename in sorted(filenames):
                candidate = root_path / filename
                if candidate.is_symlink():
                    problems.append({"path": str(candidate), "reason": "symlink_skipped"})
                elif candidate.is_file():
                    files.append(candidate)
    unique = {item.resolve(): item for item in files}
    return [unique[key] for key in sorted(unique, key=lambda item: item.as_posix())], problems


def build_manifest(inputs: list[Path], base: Path, max_text_bytes: int, max_hash_bytes: int) -> dict:
    files, problems = iter_files(inputs)
    entries: list[dict] = []
    for path in files:
        relative = portable_path(path, base)
        if is_sensitive(path):
            entries.append({
                "path": relative,
                "kind": "sensitive",
                "status": "skipped_sensitive",
            })
            continue
        stat = path.stat()
        kind = classify(path)
        is_text = path.suffix.lower() in TEXT_EXTENSIONS
        status = "included" if is_text and stat.st_size <= max_text_bytes else "metadata_only"
        entry = {
            "path": relative,
            "kind": kind,
            "status": status,
            "bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
            "text_candidate": is_text,
        }
        if stat.st_size <= max_hash_bytes:
            entry["sha256"] = sha256(path)
        else:
            entry["hash_status"] = "skipped_oversize"
        if is_text and stat.st_size > max_text_bytes:
            entry["note"] = "Text candidate exceeds the configured analysis size limit."
        entries.append(entry)

    counts = Counter(entry["status"] for entry in entries)
    return {
        "schema_version": "1.0",
        "generated_at": utc_now(),
        "base_path": base.resolve().as_posix(),
        "roots": [portable_path(path, base) for path in inputs],
        "files": entries,
        "problems": problems,
        "summary": {
            "total_files": len(entries),
            "included": counts["included"],
            "metadata_only": counts["metadata_only"],
            "skipped_sensitive": counts["skipped_sensitive"],
            "problems": len(problems),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", nargs="+", type=Path, help="Files or directories to inventory")
    parser.add_argument("--base", type=Path, default=Path.cwd(), help="Base path for portable paths")
    parser.add_argument("--output", type=Path, help="Write JSON here; stdout when omitted")
    parser.add_argument("--max-text-bytes", type=int, default=2 * 1024 * 1024)
    parser.add_argument("--max-hash-bytes", type=int, default=50 * 1024 * 1024)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_text_bytes < 1 or args.max_hash_bytes < 1:
        raise SystemExit("Size limits must be positive integers.")
    manifest = build_manifest(args.sources, args.base, args.max_text_bytes, args.max_hash_bytes)
    payload = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0 if not manifest["problems"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
