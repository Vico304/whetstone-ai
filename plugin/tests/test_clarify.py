from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from _support import CLARIFY_SCRIPT_ROOT, load_template, scan_wikilinks


class ScanWikilinksTests(unittest.TestCase):
    def test_unresolved_links_aliases_and_inbox(self):
        with tempfile.TemporaryDirectory() as temporary:
            pack = Path(temporary)
            concepts = pack / "concepts"
            concepts.mkdir()
            (pack / "teaching-guide.md").write_text(
                "提到 [[虚拟内存]] 与 [[TLB|快表]] 和 [[页表#结构]]。\n"
                "```\n[[代码块内不算]]\n```\n",
                encoding="utf-8",
            )
            (concepts / "页表.md").write_text(
                "---\naliases: [page table]\nstatus: grounded\n---\n# 页表\n引用 [[虚拟内存]]。\n",
                encoding="utf-8",
            )
            (concepts / "_inbox.md").write_text(
                "# 收件箱\n- 缺页中断\n- page table\n", encoding="utf-8"
            )

            result = scan_wikilinks.scan(pack, None)

            unresolved = {item["concept"] for item in result["unresolved_links"]}
            self.assertEqual(unresolved, {"虚拟内存", "TLB"})
            self.assertNotIn("代码块内不算", unresolved)
            self.assertEqual(result["inbox_pending"], ["缺页中断"])
            by_concept = {
                item["concept"]: item["found_in"] for item in result["unresolved_links"]
            }
            self.assertIn("concepts/页表.md", by_concept["虚拟内存"])

    def test_block_list_aliases_and_inline_code_are_handled(self):
        with tempfile.TemporaryDirectory() as temporary:
            pack = Path(temporary)
            concepts = pack / "concepts"
            concepts.mkdir()
            (concepts / "缓存.md").write_text(
                "---\ntitle: 缓存\naliases:\n  - cache\n  - \"Cache Layer\"\nstatus: grounded\n---\n# 缓存\n",
                encoding="utf-8",
            )
            (pack / "teaching-guide.md").write_text(
                "正文提到 [[cache]] 与 [[Cache Layer]]，还有 [[命中率]]。\n"
                "行内代码 `[[不算链接]]` 不应被扫描。\n"
                "~~~\n[[波浪围栏内不算]]\n~~~\n"
                "````md\n```\n[[嵌套围栏内不算]]\n```\n````\n",
                encoding="utf-8",
            )

            result = scan_wikilinks.scan(pack, None)

            self.assertTrue({"cache layer", "cache", "缓存"} <= set(result["known_notes"]))  # plus the other .md stems of the course
            unresolved = {item["concept"] for item in result["unresolved_links"]}
            self.assertEqual(unresolved, {"命中率"})

    def test_scan_groups_pending_concepts_by_unit_and_resolves_unit_notes_by_alias(self):
        with tempfile.TemporaryDirectory() as temporary:
            course = Path(temporary) / "course"
            (course / "units").mkdir(parents=True)
            (course / "concepts").mkdir()
            plan = load_template()
            plan["sections"] = [dict(plan["sections"][0], id="s01"), dict(plan["sections"][0], id="s02", title="第二节")]
            (course / "lesson-plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
            (course / "units" / "s01.md").write_text("讲到 [[前馈网络]] 与 [[词元]]，还有 [[s02]]。\n", encoding="utf-8")
            (course / "units" / "s02.md").write_text("这里提到向量空间。\n", encoding="utf-8")
            (course / "outline.md").write_text("大纲提到 [[宏观地图]]。\n", encoding="utf-8")
            (course / "concepts" / "_inbox.md").write_text("- 向量空间\n- 完全无关的词\n", encoding="utf-8")
            result = scan_wikilinks.scan(course, None)
            units = {u["unit"]: u for u in result["by_unit"]}
            self.assertEqual((units["s01"]["concepts"], units["s01"]["scope"], units["s01"]["note_file"]), (["前馈网络", "宏观地图", "词元"], "cluster", "concepts/s01.md"))  # 宏观地图: marked in the outline, listed by s01 in the plan
            self.assertEqual((units["s02"]["concepts"], units["s02"]["scope"]), (["向量空间"], "isolated"))   # inbox entry, matched by the unit text
            self.assertEqual(units[None]["concepts"], ["完全无关的词"])
            self.assertNotIn("s02", [l["concept"] for l in result["unresolved_links"]])                   # [[s02]] resolves to units/s02.md
            self.assertIn("宏观地图", [l["concept"] for l in result["unresolved_links"]])                   # a plan concept marked in the outline
            # a per-unit note whose aliases list its concepts resolves them
            (course / "concepts" / "s01.md").write_text("---\nunit: s01\naliases: [前馈网络, 词元]\nscope: cluster\n---\n# 第一节\n", encoding="utf-8")
            result = scan_wikilinks.scan(course, None)
            self.assertEqual(units_after := {u["unit"]: u["concepts"] for u in result["by_unit"]}, {"s01": ["宏观地图"], "s02": ["向量空间"], None: ["完全无关的词"]})

    def test_scan_scope_defaults_to_the_course_studied_most_recently(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "courses"
            for name, updated, link in (("old-1", "2026-09-01T10:00:00Z", "[[旧概念]]"), ("new-2", "2026-09-13T10:00:00Z", "[[新概念]]")):
                course = root / "目标" / name
                (course / "concepts").mkdir(parents=True)
                (course / "lesson-plan.json").write_text("{}", encoding="utf-8")
                (course / "learning-progress.json").write_text(json.dumps({"updated_at": updated}), encoding="utf-8")
                (course / "outline.md").write_text(f"提到 {link}。\n", encoding="utf-8")
                (course / "concepts" / "_inbox.md").write_text("- 待办\n" if name == "old-1" else "", encoding="utf-8")
            result = scan_wikilinks.scan_scope(root, None, scan_all=False, chosen=None)
            self.assertTrue(result["current_course"].endswith("new-2"))
            self.assertEqual([i["concept"] for i in result["scanned"][0]["unresolved_links"]], ["新概念"])
            self.assertEqual(len(result["scanned"]), 1)
            self.assertEqual([(o["pack_dir"].split("/")[-1], o["inbox_pending"]) for o in result["other_courses"]], [("old-1", 1)])
            everything = scan_wikilinks.scan_scope(root, None, scan_all=True, chosen=None)
            self.assertEqual(len(everything["scanned"]), 2)
            self.assertEqual(everything["other_courses"], [])
            picked = scan_wikilinks.scan_scope(root, None, scan_all=False, chosen=root / "目标" / "old-1")
            self.assertTrue(picked["current_course"].endswith("old-1"))
            with self.assertRaises(ValueError):
                scan_wikilinks.scan_scope(root, None, scan_all=False, chosen=root / "目标")
            with self.assertRaises(ValueError):
                scan_wikilinks.scan_scope(Path(temporary) / "empty", None, False, None)

    def test_cli_exits_2_for_a_directory_without_courses_as_for_a_missing_one(self):
        import subprocess, sys
        script = CLARIFY_SCRIPT_ROOT / "scan_wikilinks.py"
        with tempfile.TemporaryDirectory() as temporary:
            (Path(temporary) / "empty").mkdir()
            for target in ("empty", "missing"):
                done = subprocess.run([sys.executable, str(script), str(Path(temporary) / target)], capture_output=True, text=True)
                self.assertEqual(done.returncode, 2, target)
                self.assertTrue(done.stdout.startswith("ERROR: "), done.stdout)
                self.assertNotIn('"error"', done.stdout)

