from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from _support import SCRIPT_ROOT, load_template, source_manifest, survey_materials, validate_lesson


class SourceManifestTests(unittest.TestCase):
    def test_inventory_skips_sensitive_and_ignored_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
            (root / ".env").write_text("API_KEY=secret\n", encoding="utf-8")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "ignored.js").write_text("ignored\n", encoding="utf-8")

            manifest = source_manifest.build_manifest([root], root, 1024, 1024)
            by_path = {entry["path"]: entry for entry in manifest["files"]}

            self.assertEqual(by_path["src/main.py"]["status"], "included")
            self.assertEqual(by_path[".env"]["status"], "skipped_sensitive")
            self.assertNotIn("node_modules/ignored.js", by_path)
            self.assertNotIn("sha256", by_path[".env"])

    def test_code_named_after_sessions_is_not_a_conversation(self):
        self.assertEqual(source_manifest.classify(Path("app/session.py")), "code")
        self.assertEqual(source_manifest.classify(Path("store/session_store.go")), "code")
        self.assertEqual(source_manifest.classify(Path("notes/obsession.md")), "document")

    def test_exported_conversations_are_detected(self):
        self.assertEqual(source_manifest.classify(Path("exports/chat-2026-01.json")), "conversation")
        self.assertEqual(source_manifest.classify(Path("transcripts/2026-01-01.md")), "conversation")
        self.assertEqual(source_manifest.classify(Path("sessions/index.html")), "conversation")
        self.assertEqual(source_manifest.classify(Path("data/session_metrics.csv")), "data")

    def test_rebasing_an_unreadable_manifest_reports_an_error_instead_of_a_traceback(self):
        import subprocess, sys
        script = SCRIPT_ROOT / "source_manifest.py"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "not-json.json").write_text("hello {", encoding="utf-8")
            (root / "list.json").write_text("[]\n", encoding="utf-8")
            (root / "good.json").write_text(json.dumps({"base_path": "."}) + "\n", encoding="utf-8")
            for target in ("missing.json", "not-json.json", "list.json", "."):
                done = subprocess.run([sys.executable, str(script), "--rebase", str(root / target), "--base", str(root)],
                                      capture_output=True, text=True)
                self.assertEqual(done.returncode, 1, target)
                self.assertTrue(done.stderr.startswith("ERROR: "), (target, done.stderr))
                self.assertNotIn("Traceback", done.stderr, target)
            done = subprocess.run([sys.executable, str(script), "--rebase", str(root / "good.json"), "--base", str(root)],
                                  capture_output=True, text=True, check=True)
            self.assertTrue(done.stdout.startswith("OK: "), done.stdout)
            self.assertEqual(json.loads((root / "good.json").read_text(encoding="utf-8"))["base_path"], ".")


class SurveyMaterialsTests(unittest.TestCase):
    def test_survey_classifies_repos_documents_generated_and_noise(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "upstream"
            (repo / ".git").mkdir(parents=True)
            (repo / "src").mkdir()
            (repo / "src" / "main.rs").write_text("fn main() {}\n", encoding="utf-8")
            (repo / "src" / "lib.rs").write_text("pub mod x;\n", encoding="utf-8")
            (repo / "README.md").write_text("# Upstream\n", encoding="utf-8")
            (repo / "docs").mkdir()
            (repo / "docs" / "spec.md").write_text("# Specification\n", encoding="utf-8")
            (repo / "demos").mkdir()
            (repo / "demos" / "main.c").write_text("int main(){}\n", encoding="utf-8")
            docs = root / "文档"
            docs.mkdir()
            (docs / "5_conversation_record.md").write_text("This session is being continued from a previous conversation. Summary below covers…\n", encoding="utf-8")
            (docs / "2_设计方案.md").write_text("# 设计方案\n\n## 1. 目标\n\n## 2. 架构\n", encoding="utf-8")
            (root / "进展汇报_2026-09-06.md").write_text("# 进展汇报\n\n> 日期：2026-09-06\n\n## 1. 完成度\n", encoding="utf-8")
            (root / "textbook-ch3.md").write_text("# 第三章 内存隔离\n\n习题 3.1\n", encoding="utf-8")
            data = root / "data"
            data.mkdir()
            (data / "big.log").write_text("x" * 100, encoding="utf-8")
            (data / "dump.json").write_text("{}", encoding="utf-8")
            (root / "tmp.log").write_text("log\n", encoding="utf-8")
            (root / ".env").write_text("SECRET=1\n", encoding="utf-8")
            (root / "paper.pdf").write_bytes(b"%PDF-1.4")

            result = survey_materials.survey(root, 1000)
            by_name = {e["name"]: e for e in result["entries"]}

            self.assertEqual(by_name["upstream"]["kind"], "git_repo")
            self.assertEqual(by_name["upstream"]["readme"], "README.md")
            self.assertEqual(by_name["upstream"]["doc_dirs"], ["docs"])
            self.assertEqual(by_name["upstream"]["entry_hints"], ["src/lib.rs", "src/main.rs"])  # demos/main.c skipped
            self.assertEqual(by_name["文档"]["kind"], "document_folder")
            docs_by = {Path(d["path"]).name: d for d in by_name["文档"]["documents"]}
            self.assertEqual(docs_by["5_conversation_record.md"]["likely"], "generated_intermediate")
            self.assertIn("session_summary", docs_by["5_conversation_record.md"]["generated_signals"])
            self.assertNotEqual(docs_by["2_设计方案.md"]["likely"], "generated_intermediate")
            self.assertEqual(by_name["进展汇报_2026-09-06.md"]["likely"], "generated_intermediate")
            self.assertEqual(by_name["textbook-ch3.md"]["likely"], "primary_or_authored")
            self.assertIn("textbook_like", by_name["textbook-ch3.md"]["primary_signals"])
            self.assertEqual(by_name["data"]["kind"], "data_or_logs")
            self.assertEqual(by_name["tmp.log"]["kind"], "log")
            self.assertEqual(by_name[".env"]["kind"], "sensitive_skipped")
            self.assertEqual(by_name["paper.pdf"]["kind"], "document")
            self.assertIn("binary document", by_name["paper.pdf"]["note"])

            md = survey_materials.render_markdown(result)
            self.assertIn("| `upstream` | git_repo |", md)
            self.assertIn("文档夹内明细", md)
            self.assertNotIn("SECRET", md)
            self.assertNotIn("This session is being continued", md)  # no content copied

    def test_survey_ignores_build_dirs_and_marks_release_trees(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rel = root / "release"
            (rel / "node_modules").mkdir(parents=True)
            (rel / "node_modules" / "x.js").write_text("", encoding="utf-8")
            (rel / "bin").mkdir()
            for i in range(5):
                (rel / "bin" / f"lib{i}.so").write_bytes(b"\x00")
            (rel / "bin" / "run.sh").write_text("#!/bin/sh\n", encoding="utf-8")
            result = survey_materials.survey(root, 1000)
            entry = result["entries"][0]
            self.assertEqual(entry["kind"], "release_tree")
            self.assertEqual(entry["files"], 6)

    def test_survey_rejects_a_walk_cap_below_one(self):
        import subprocess, sys
        script = SCRIPT_ROOT / "survey_materials.py"
        with tempfile.TemporaryDirectory() as temporary:
            (Path(temporary) / "docs").mkdir()
            (Path(temporary) / "docs" / "a.md").write_text("# A\n", encoding="utf-8")
            for cap in ("0", "-1"):
                done = subprocess.run([sys.executable, str(script), temporary, "--max-files", cap], capture_output=True, text=True)
                self.assertEqual(done.returncode, 2, cap)
                self.assertIn("--max-files must be at least 1", done.stderr)
                self.assertEqual(done.stdout, "")
            done = subprocess.run([sys.executable, str(script), temporary, "--max-files", "1"], capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("`docs`", done.stdout)


class LayoutTests(unittest.TestCase):
    """A course pack is self-contained: sources.json records the material root relative to itself,
    so validators find the sources in both layouts (<materials>/whetstone/courses/<id>/ and
    <knowledge-base>/courses/<goal>/<id>/ with materials under material/)."""

    def _materials(self, root: Path) -> Path:
        materials = root / "material" / "spec"
        (materials / "examples").mkdir(parents=True)
        (materials / "examples" / "source.md").write_text("## Architecture\n\n## Course ordering\n\n## Appendix\n\n## Deployment notes\n", encoding="utf-8")
        return materials

    def test_base_path_is_relative_to_the_manifest_in_both_layouts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            materials = self._materials(root)
            # knowledge-base layout
            kb_pack = root / "courses" / "目标A" / "c1"
            kb_pack.mkdir(parents=True)
            manifest = source_manifest.build_manifest([materials / "examples"], materials, 1024, 1024, output=kb_pack / "sources.json")
            self.assertEqual(manifest["base_path"], "../../../material/spec")
            self.assertEqual(manifest["roots"], ["examples"])
            (kb_pack / "sources.json").write_text(json.dumps(manifest), encoding="utf-8")
            self.assertEqual(validate_lesson.sources_root_from_manifest(kb_pack / "sources.json", manifest), materials.resolve())
            # standalone layout: <materials>/whetstone/courses/<id>/
            sa_pack = materials / "whetstone" / "courses" / "c1"
            sa_pack.mkdir(parents=True)
            manifest2 = source_manifest.build_manifest([materials / "examples"], materials, 1024, 1024, output=sa_pack / "sources.json")
            self.assertEqual(manifest2["base_path"], "../../..")
            # legacy "." cannot be resolved
            self.assertIsNone(validate_lesson.sources_root_from_manifest(kb_pack / "sources.json", {"base_path": "."}))
            # rebase migrates an old manifest in place, touching only base_path
            (kb_pack / "sources.json").write_text(json.dumps(dict(manifest, base_path=".")), encoding="utf-8")
            self.assertEqual(source_manifest.rebase_manifest(kb_pack / "sources.json", materials), "../../../material/spec")
            rebased = json.loads((kb_pack / "sources.json").read_text(encoding="utf-8"))
            self.assertEqual(rebased["roots"], ["examples"])
            # the coverage check then works with the derived root
            plan = load_template()
            self.assertEqual(validate_lesson.validate_coverage_against_sources(plan, validate_lesson.sources_root_from_manifest(kb_pack / "sources.json", rebased)), [])

